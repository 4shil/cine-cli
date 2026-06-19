"""Playback module for cine-cli — exact ani-cli UI replication.

Uses fzf for all selection (quality, menu, episode select).
Falls back to auto-select when fzf is not available.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional

import subprocess
import sys
import os

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

    # Post-playback menu loop (ani-cli style with fzf)
    if is_tv:
        __tv_menu_loop(media, metadata, scraper, episode, config, chosen_player)
    else:
        __movie_menu_loop(media, metadata, config, chosen_player)

    return None


def __fzf(prompt: str, choices: str, multi: bool = False) -> Optional[str]:
    """Run fzf with given prompt and choices. Returns selected line or None."""
    if not __has_fzf():
        return None

    args = ["fzf", "--reverse", "--cycle", "--prompt", prompt]
    if multi:
        args += ["-m"]

    try:
        result = subprocess.run(
            args,
            input=choices,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def __has_fzf() -> bool:
    """Check if fzf is available."""
    try:
        subprocess.run(["fzf", "--version"], capture_output=True, timeout=5, check=True)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def __play_episode(media: Media, metadata: Metadata, chosen_player, config):
    """Launch MPV detached — exact ani-cli pattern."""
    title = metadata.display_name if hasattr(metadata, 'display_name') else metadata.title

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
    """Select quality using fzf — ani-cli style."""
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

    # Build choices for fzf (ani-cli style: numbered list)
    choices_lines = []
    for i, source in enumerate(sorted_sources, 1):
        quality = source.get("quality", "unknown")
        from urllib.parse import urlparse
        domain = urlparse(source["url"]).netloc
        choices_lines.append(f"{i}. {quality:>8}  —  {domain}")
    choices = "\n".join(choices_lines)

    # Show fzf selector
    selected = __fzf(f"Select quality for {media.title}: ", choices)

    if selected:
        # Parse selection: "1. 1080p  —  domain" -> index 0
        try:
            idx = int(selected.split(".")[0].strip()) - 1
            if 0 <= idx < len(sorted_sources):
                s = sorted_sources[idx]
                return Single(
                    url=s["url"], title=media.title,
                    referrer=media.referrer, year=media.year, subtitles=media.subtitles,
                )
        except (ValueError, IndexError):
            pass

    # Fallback: auto-select best
    best = sorted_sources[0]
    return Single(
        url=best["url"], title=media.title,
        referrer=media.referrer, year=media.year, subtitles=media.subtitles,
    )


def __movie_menu_loop(media, metadata, config, chosen_player):
    """Post-playback menu for movies — ani-cli style fzf menu."""
    replay_url = media.url

    while True:
        choices = "\n".join(["replay", "change_quality", "quit"])
        cmd = __fzf(f"Playing {metadata.title}... ", choices)

        if cmd is None:
            # fzf not available or cancelled — auto-quit
            return

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

        elif cmd == "quit":
            return

        else:
            print(f"  Unknown option: {cmd}")


def __tv_menu_loop(media, metadata, scraper, episode, config, chosen_player):
    """Post-playback menu for TV series — ani-cli style fzf menu."""
    current_episode = episode.episode
    current_season = episode.season
    replay_url = media.url

    while True:
        choices = "\n".join(["next", "previous", "replay", "select", "change_quality", "quit"])
        cmd = __fzf(f"Playing S{current_season:02d}E{current_episode:02d} of {metadata.title}... ", choices)

        if cmd is None:
            return

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
            new_ep = __select_episode_fzf(current_episode)
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

        elif cmd == "quit":
            return

        else:
            print(f"  Unknown option: {cmd}")


def __select_episode_fzf(current_episode: int) -> Optional[int]:
    """Select episode using fzf — ani-cli style."""
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
