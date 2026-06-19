"""Playback module for cine-cli.

Handles player launch and post-playback menu loop (next/replay/previous/select/quit).
Designed to replicate ani-cli's playback experience.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Type, cast, Optional

import subprocess
import time

if TYPE_CHECKING:
    from typing import Literal
    from ..config import Config

from devgoldyutils import Colours

from ..media import Media, Metadata, Multi, Single, MultiSourceMedia, MetadataType
from ..logger import cine_cli_logger
from ..cache import Cache
from ..utils import what_platform, EpisodeSelector
from ..players import PLAYER_TABLE, CustomPlayer, Player


def play(media: Media, metadata: Metadata, scraper, episode, config) -> Optional[Literal["search"]]:
    """Main playback loop — launches MPV and shows post-playback menu."""
    platform = what_platform()
    cache = Cache(platform)
    cache.set_cache(str(metadata.id), episode.__dict__)

    chosen_player = __get_player(config, platform)

    # Quality selection for MultiSourceMedia
    selected_media = media
    if isinstance(media, MultiSourceMedia):
        selected = __select_quality(media, config.quality)
        if selected is None:
            return None
        selected_media = selected

    # Determine if this is TV or movie
    is_tv = metadata.type == MetadataType.MULTI

    # Launch MPV
    popen = __launch_player(selected_media, chosen_player)

    if popen is None:
        return None

    cine_cli_logger.info(
        f"Playing '{Colours.BLUE.apply(selected_media.display_name)}' "
        f"with {chosen_player.display_name}..."
    )

    # Post-playback menu loop (ani-cli style)
    if is_tv:
        __tv_menu_loop(selected_media, metadata, scraper, episode, config, chosen_player, popen)
    else:
        __movie_menu_loop(selected_media, metadata, scraper, episode, config, chosen_player, popen)

    return None


def __launch_player(media: Media, chosen_player) -> Optional[subprocess.Popen]:
    """Launch the player and return the process handle."""
    try:
        popen = chosen_player.play(media)

        actual_player = chosen_player.display_name
        popen_args = popen.args if popen is not None else []
        if isinstance(popen_args, (list, tuple)) and len(popen_args) > 0:
            command = str(popen_args[0])
            if command.endswith("xdg-open") or "zen-browser" in command or "firefox" in command or "brave" in command:
                actual_player = Colours.PURPLE.apply("Browser")

        cine_cli_logger.debug(f"Called player with these args -> '{' '.join(popen.args) if popen else ''}'")
        return popen
    except FileNotFoundError as e:
        cine_cli_logger.error(
            f"The player '{chosen_player.display_name}' was not found! {e}"
        )
        return None


def __select_quality(media: MultiSourceMedia, preferred_quality: Optional[str] = None) -> Optional[Single]:
    """Select quality — auto-select best, or use preferred_quality if specified."""
    sources = media.sources

    if len(sources) == 0:
        return None

    if len(sources) == 1:
        return Single(
            url=sources[0]["url"],
            title=media.title,
            referrer=media.referrer,
            year=media.year,
            subtitles=media.subtitles,
        )

    # Sort by quality (highest first)
    quality_order = {"4k": 2160, "2160p": 2160, "1080p": 1080, "720p": 720, "480p": 480, "360p": 360, "unknown": 0}
    sorted_sources = sorted(
        sources,
        key=lambda s: quality_order.get(s.get("quality", "unknown").lower(), 0),
        reverse=True,
    )

    # Auto-select if preferred quality matches
    if preferred_quality:
        pq = preferred_quality.lower()
        for s in sorted_sources:
            if s.get("quality", "").lower() == pq:
                return Single(
                    url=s["url"],
                    title=media.title,
                    referrer=media.referrer,
                    year=media.year,
                    subtitles=media.subtitles,
                )

    # Show available qualities
    print(f"\n  {Colours.BLUE.apply(media.display_name)} — {len(sorted_sources)} qualities available:\n")
    for i, source in enumerate(sorted_sources, 1):
        quality = source.get("quality", "unknown")
        from urllib.parse import urlparse
        domain = urlparse(source["url"]).netloc
        print(f"    {Colours.GREEN.apply(str(i))}. {quality:>8}  —  {domain}")

    print()

    # Auto-select best quality (stdin not available in non-interactive terminals)
    best = sorted_sources[0]
    print(f"  → {Colours.GREEN.apply(best.get('quality', 'unknown'))} selected (best)\n")
    return Single(
        url=best["url"],
        title=media.title,
        referrer=media.referrer,
        year=media.year,
        subtitles=media.subtitles,
    )


def __movie_menu_loop(media, metadata, scraper, episode, config, chosen_player, popen):
    """Post-playback menu for movies: replay, change quality, quit."""
    replay_url = media.url

    while True:
        print()
        cmd = __menu_prompt("Playing movie", ["replay", "change_quality", "quit"])

        if cmd == "replay":
            print(f"\n  Replaying '{Colours.BLUE.apply(metadata.title)}'...")
            popen = __launch_player(media, chosen_player)
            if popen is None:
                return
            continue

        elif cmd == "change_quality":
            if isinstance(media, MultiSourceMedia):
                new_media = __select_quality(media, config.quality)
                if new_media:
                    media = new_media
                    replay_url = media.url
                    print(f"\n  Playing with new quality...")
                    popen = __launch_player(media, chosen_player)
                    if popen is None:
                        return
            else:
                print("  Only one quality available.")
            continue

        elif cmd == "quit" or cmd == "q" or cmd is None:
            print("  Goodbye!")
            return

        else:
            print(f"  Unknown option: {cmd}")


def __tv_menu_loop(media, metadata, scraper, episode, config, chosen_player, popen):
    """Post-playback menu for TV series: next, previous, replay, select episode, change quality, quit."""
    current_episode = episode.episode
    current_season = episode.season

    while True:
        print()
        options = ["next", "previous", "replay", "select_episode", "change_quality", "quit"]
        cmd = __menu_prompt(
            f"Playing S{current_season:02d}E{current_episode:02d} of {metadata.title}",
            options
        )

        if cmd == "next":
            current_episode += 1
            print(f"\n  Playing next episode: S{current_season:02d}E{current_episode:02d}...")
            new_media = __scrape_episode(scraper, metadata, current_season, current_episode)
            if new_media is None:
                print("  No more episodes or failed to fetch. Going back.")
                current_episode -= 1
                continue
            media = new_media
            popen = __launch_player(media, chosen_player)
            if popen is None:
                return

        elif cmd == "previous":
            if current_episode > 1:
                current_episode -= 1
                print(f"\n  Playing previous episode: S{current_season:02d}E{current_episode:02d}...")
                new_media = __scrape_episode(scraper, metadata, current_season, current_episode)
                if new_media is None:
                    print("  Failed to fetch. Going back.")
                    current_episode += 1
                    continue
                media = new_media
                popen = __launch_player(media, chosen_player)
                if popen is None:
                    return
            else:
                print("  Already at first episode.")

        elif cmd == "replay":
            print(f"\n  Replaying S{current_season:02d}E{current_episode:02d}...")
            popen = __launch_player(media, chosen_player)
            if popen is None:
                return

        elif cmd == "select_episode":
            new_ep = __select_episode_interactive(metadata, current_season, current_episode)
            if new_ep is not None:
                current_episode = new_ep
                print(f"\n  Playing episode {current_episode}...")
                new_media = __scrape_episode(scraper, metadata, current_season, current_episode)
                if new_media is None:
                    print("  Failed to fetch. Going back.")
                    continue
                media = new_media
                popen = __launch_player(media, chosen_player)
                if popen is None:
                    return

        elif cmd == "change_quality":
            if isinstance(media, MultiSourceMedia):
                new_media = __select_quality(media, config.quality)
                if new_media:
                    media = new_media
                    print(f"\n  Playing with new quality...")
                    popen = __launch_player(media, chosen_player)
                    if popen is None:
                        return
            else:
                print("  Only one quality available.")
            continue

        elif cmd == "quit" or cmd == "q" or cmd is None:
            print("  Goodbye!")
            return

        else:
            print(f"  Unknown option: {cmd}")


def __menu_prompt(title: str, options: list) -> Optional[str]:
    """Show a simple text-based menu prompt."""
    from devgoldyutils import Colours

    print(f"\n  {Colours.BLUE.apply(title)}")
    print(f"  Options: {Colours.GREEN.apply(' | '.join(options))}")
    print()

    try:
        choice = input("  Enter choice: ").strip().lower()
        return choice if choice else None
    except (EOFError, KeyboardInterrupt):
        return None


def __select_episode_interactive(metadata, season: int, current_episode: int) -> Optional[int]:
    """Let user select a specific episode."""
    try:
        ep_input = input(f"  Enter episode number (current: {current_episode}): ").strip()
        if not ep_input:
            return None
        ep_num = int(ep_input)
        if ep_num < 1:
            print("  Invalid episode number.")
            return None
        return ep_num
    except (ValueError, EOFError, KeyboardInterrupt):
        return None


def __scrape_episode(scraper, metadata, season: int, episode: int) -> Optional[Media]:
    """Scrape a specific episode from a TV series."""
    ep = EpisodeSelector(season=season, episode=episode)
    media = scraper.scrape(metadata, ep)
    return media if isinstance(media, (Multi, Single, MultiSourceMedia)) else None


def __get_player(config: Config, platform) -> Player:
    """Get the configured player."""
    from ..players import Player as PlayerBase
    player = PLAYER_TABLE.get(config.player, CustomPlayer)

    if player == CustomPlayer:
        player = cast(Type[CustomPlayer], player)
        return player(
            binary=config.player,
            args=config.player_args
        )

    return player(
        platform=platform,
        args=config.player_args,
        debug=config.debug_player,
        args_override=config.player_args_override,
    )
