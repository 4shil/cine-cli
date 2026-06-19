"""Playback module for cine-cli — ani-cli style.

Exact replication of ani-cli's playback and menu logic:
- nohup mpv with --force-media-title, --referrer, --sub-file
- Post-playback menu: next, replay, previous, select, change_quality, quit
- Auto-select quality (best) by default
- Input-based menu using simple prompt (fzf-style)
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional

import subprocess
import sys

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
    """Main playback loop — ani-cli style."""
    platform = what_platform()
    cache = Cache(platform)
    cache.set_cache(str(metadata.id), episode.__dict__)

    chosen_player = __get_player(config, platform)

    # Quality selection for MultiSourceMedia
    if isinstance(media, MultiSourceMedia):
        selected = __select_quality(media, config.quality)
        if selected is None:
            return None
        media = selected

    is_tv = metadata.type == MetadataType.MULTI

    # Launch MPV (detached, like ani-cli)
    __play_episode(media, metadata, chosen_player, config)

    # Post-playback menu loop (ani-cli style)
    if is_tv:
        __tv_menu_loop(media, metadata, scraper, episode, config, chosen_player)
    else:
        __movie_menu_loop(media, metadata, config, chosen_player)

    return None


def __play_episode(media: Media, metadata: Metadata, chosen_player, config):
    """Launch MPV detached — exact ani-cli pattern."""
    title = metadata.display_name if hasattr(metadata, 'display_name') else metadata.title

    # Build MPV args (ani-cli style)
    mpv_args = [
        "mpv",
        media.url,
        f"--force-media-title={title}",
    ]

    if media.referrer:
        mpv_args.append(f"--referrer={media.referrer}")

    if media.subtitles:
        for sub in media.subtitles:
            if sub.startswith("http"):
                mpv_args.append(f"--sub-file={sub}")

    # Launch detached (exact ani-cli pattern)
    # nohup mpv ... >/dev/null 2>&1 &
    try:
        subprocess.Popen(
            mpv_args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        cine_cli_logger.info(f"Playing '{Colours.BLUE.apply(title)}' with MPV...")
    except FileNotFoundError:
        cine_cli_logger.error("MPV not found! Install mpv to play videos.")
    except Exception as e:
        cine_cli_logger.error(f"Failed to launch MPV: {e}")


def __select_quality(media: MultiSourceMedia, preferred_quality: Optional[str] = None) -> Optional[Single]:
    """Select quality — auto-select best, or use preferred_quality if specified."""
    sources = media.sources
    if not sources:
        return None

    if len(sources) == 1:
        return Single(
            url=sources[0]["url"], title=media.title,
            referrer=media.referrer, year=media.year, subtitles=media.subtitles,
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
                    url=s["url"], title=media.title,
                    referrer=media.referrer, year=media.year, subtitles=media.subtitles,
                )

    # Show available qualities
    print(f"\n  {Colours.BLUE.apply(media.display_name)} — {len(sorted_sources)} qualities available:\n")
    for i, source in enumerate(sorted_sources, 1):
        quality = source.get("quality", "unknown")
        from urllib.parse import urlparse
        domain = urlparse(source["url"]).netloc
        print(f"    {Colours.GREEN.apply(str(i))}. {quality:>8}  —  {domain}")
    print()

    # Auto-select best quality
    best = sorted_sources[0]
    print(f"  → {Colours.GREEN.apply(best.get('quality', 'unknown'))} selected (best)\n")
    return Single(
        url=best["url"], title=media.title,
        referrer=media.referrer, year=media.year, subtitles=media.subtitles,
    )


def __movie_menu_loop(media, metadata, config, chosen_player):
    """Post-playback menu for movies: replay, change_quality, quit."""
    replay_url = media.url

    while True:
        print()
        cmd = __menu_prompt("Playing movie", ["replay", "change_quality", "quit"])

        if cmd == "replay":
            print(f"\n  Replaying '{Colours.BLUE.apply(metadata.title)}'...")
            __play_episode(media, metadata, chosen_player, config)

        elif cmd == "change_quality":
            if isinstance(media, MultiSourceMedia):
                new_media = __select_quality(media, config.quality)
                if new_media:
                    media = new_media
                    replay_url = media.url
                    __play_episode(media, metadata, chosen_player, config)
            else:
                print("  Only one quality available.")

        elif cmd in ("quit", "q", None):
            return

        else:
            print(f"  Unknown option: {cmd}")


def __tv_menu_loop(media, metadata, scraper, episode, config, chosen_player):
    """Post-playback menu for TV series: next, previous, replay, select, change_quality, quit."""
    current_episode = episode.episode
    current_season = episode.season
    replay_url = media.url

    while True:
        print()
        cmd = __menu_prompt(
            f"Playing S{current_season:02d}E{current_episode:02d} of {metadata.title}",
            ["next", "previous", "replay", "select", "change_quality", "quit"]
        )

        if cmd == "next":
            current_episode += 1
            print(f"\n  Playing next: S{current_season:02d}E{current_episode:02d}...")
            new_media = __scrape_episode(scraper, metadata, current_season, current_episode)
            if new_media is None:
                print("  No more episodes.")
                current_episode -= 1
                continue
            media = new_media
            replay_url = media.url
            __play_episode(media, metadata, chosen_player, config)

        elif cmd == "previous":
            if current_episode > 1:
                current_episode -= 1
                print(f"\n  Playing previous: S{current_season:02d}E{current_episode:02d}...")
                new_media = __scrape_episode(scraper, metadata, current_season, current_episode)
                if new_media is None:
                    current_episode += 1
                    continue
                media = new_media
                replay_url = media.url
                __play_episode(media, metadata, chosen_player, config)
            else:
                print("  Already at first episode.")

        elif cmd == "replay":
            print(f"\n  Replaying S{current_season:02d}E{current_episode:02d}...")
            __play_episode(media, metadata, chosen_player, config)

        elif cmd == "select":
            new_ep = __select_episode_interactive(current_episode)
            if new_ep is not None and new_ep != current_episode:
                current_episode = new_ep
                print(f"\n  Playing episode {current_episode}...")
                new_media = __scrape_episode(scraper, metadata, current_season, current_episode)
                if new_media is None:
                    continue
                media = new_media
                replay_url = media.url
                __play_episode(media, metadata, chosen_player, config)

        elif cmd == "change_quality":
            if isinstance(media, MultiSourceMedia):
                new_media = __select_quality(media, config.quality)
                if new_media:
                    media = new_media
                    replay_url = media.url
                    __play_episode(media, metadata, chosen_player, config)
            else:
                print("  Only one quality available.")

        elif cmd in ("quit", "q", None):
            return

        else:
            print(f"  Unknown option: {cmd}")


def __menu_prompt(title: str, options: list) -> Optional[str]:
    """Show menu prompt — ani-cli style."""
    print(f"\n  {Colours.BLUE.apply(title)}")
    print(f"  Options: {Colours.GREEN.apply(' | '.join(options))}")
    print()
    try:
        choice = input("  Enter choice: ").strip().lower()
        return choice if choice else None
    except (EOFError, KeyboardInterrupt):
        return None


def __select_episode_interactive(current_episode: int) -> Optional[int]:
    """Let user select a specific episode."""
    try:
        ep_input = input(f"  Enter episode number (current: {current_episode}): ").strip()
        if not ep_input:
            return None
        return int(ep_input)
    except (ValueError, EOFError, KeyboardInterrupt):
        return None


def __scrape_episode(scraper, metadata, season: int, episode: int) -> Optional[Media]:
    """Scrape a specific episode."""
    ep = EpisodeSelector(season=season, episode=episode)
    media = scraper.scrape(metadata, ep)
    return media if isinstance(media, (Multi, Single, MultiSourceMedia)) else None


def __get_player(config: Config, platform) -> Player:
    """Get the configured player."""
    player = PLAYER_TABLE.get(config.player, CustomPlayer)
    if player == CustomPlayer:
        from typing import Type, cast
        player = cast(Type[CustomPlayer], player)
        return player(binary=config.player, args=config.player_args)
    return player(
        platform=platform, args=config.player_args,
        debug=config.debug_player, args_override=config.player_args_override,
    )
