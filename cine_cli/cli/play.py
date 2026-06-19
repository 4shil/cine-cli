"""Playback module for cine-cli — exact ani-cli UI/UX replication.

Default player: browser (xdg-open)
Selection: fzf for all menus (provider, quality, playback menu)
Menu loop: next/replay/previous/select/change_quality/quit
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional

import subprocess
import os
import sys

if TYPE_CHECKING:
    from typing import Literal

from devgoldyutils import Colours

from ..media import Media, Metadata, Multi, Single, MultiSourceMedia, MetadataType
from ..logger import cine_cli_logger
from ..cache import Cache
from ..utils import what_platform, EpisodeSelector
from ..players import PLAYER_TABLE, CustomPlayer, Player


def play(media: Media, metadata: Metadata, scraper, episode, config) -> Optional[Literal["search"]]:
    """Main playback loop — ani-cli style with fzf menus and browser playback."""
    platform = what_platform()
    cache = Cache(platform)
    cache.set_cache(str(metadata.id), episode.__dict__)

    is_tv = metadata.type == MetadataType.MULTI

    # If MultiSourceMedia, select quality via fzf
    if isinstance(media, MultiSourceMedia):
        selected = __select_quality_fzf(media)
        if selected is None:
            return None
        media = selected

    # Play (opens in browser or configured player)
    __play(media, metadata, config)

    # Post-playback menu loop
    if is_tv:
        __tv_menu_loop(media, metadata, scraper, episode, config)
    else:
        __movie_menu_loop(media, metadata, config)
    return None


def __play(media: Media, metadata: Metadata, config):
    """Open stream URL in browser (default) or configured player."""
    title = metadata.display_name if hasattr(metadata, 'display_name') else metadata.title
    url = media.url

    cine_cli_logger.info(f"Playing '{Colours.BLUE.apply(title)}'...")

    player = config.player.lower() if config.player else "browser"

    if player in ("browser", "chrome", "firefox", "brave", "xdg-open"):
        # Open in default browser — exact ani-cli pattern for external players
        __open_browser(url, title)
    elif player == "mpv":
        __open_mpv(url, title, media.referrer, config)
    elif player == "vlc":
        __open_vlc(url, title, config)
    else:
        # Custom player
        try:
            subprocess.Popen([player, url], env=os.environ.copy())
        except FileNotFoundError:
            cine_cli_logger.error(f"Player '{player}' not found, falling back to browser")
            __open_browser(url, title)


def __open_browser(url: str, title: str):
    """Open URL in default browser using xdg-open."""
    try:
        env = os.environ.copy()
        subprocess.Popen(
            ["xdg-open", url],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        cine_cli_logger.debug(f"Opened in browser: {url[:80]}...")
    except FileNotFoundError:
        cine_cli_logger.error("xdg-open not found! Install xdg-utils.")
    except Exception as e:
        cine_cli_logger.error(f"Failed to open browser: {e}")


def __open_mpv(url: str, title: str, referrer: str = None, config=None):
    """Launch MPV — exact ani-cli nohup pattern."""
    import shlex
    import time

    cmd = ["mpv", url, f"--force-media-title={title}"]
    if referrer:
        cmd.append(f"--referrer={referrer}")
    cmd.append("--force-window=immediate")

    env = os.environ.copy()
    escaped = " ".join(shlex.quote(c) for c in cmd)
    shell_cmd = f"nohup {escaped} >/dev/null 2>&1 &"

    try:
        subprocess.Popen(shell_cmd, shell=True, env=env)
        time.sleep(1)
    except Exception as e:
        cine_cli_logger.error(f"MPV launch failed: {e}, falling back to browser")
        __open_browser(url, title)


def __open_vlc(url: str, title: str, config=None):
    """Launch VLC."""
    try:
        env = os.environ.copy()
        subprocess.Popen(
            ["vlc", url],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        cine_cli_logger.error("VLC not found, falling back to browser")
        __open_browser(url, title)


def __fzf(prompt: str, choices: str) -> Optional[str]:
    """Run fzf with prompt and choices. Returns selected line or None (cancelled/unavailable)."""
    try:
        result = subprocess.run(
            ["fzf", "--reverse", "--cycle", "--prompt", prompt],
            input=choices,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def __select_quality_fzf(media: MultiSourceMedia) -> Optional[Single]:
    """Select quality via fzf — ani-cli style numbered list."""
    sources = media.sources
    if not sources:
        return None
    if len(sources) == 1:
        s = sources[0]
        return Single(url=s["url"], title=media.title, referrer=media.referrer,
                       year=media.year, subtitles=media.subtitles)

    # Sort by quality (highest first)
    qo = {"4k": 4, "2160p": 4, "1080p": 3, "720p": 2, "480p": 1, "360p": 0}
    sorted_srcs = sorted(sources, key=lambda s: qo.get(s.get("quality","").lower(), -1), reverse=True)

    # Build fzf choices
    from urllib.parse import urlparse
    lines = []
    for i, s in enumerate(sorted_srcs, 1):
        q = s.get("quality", "?")
        domain = urlparse(s["url"]).netloc[:40]
        lines.append(f"{i}. {q:>6}  {domain}")

    selected = __fzf(f"Select quality: ", "\n".join(lines))
    if selected:
        try:
            idx = int(selected.split(".")[0].strip()) - 1
            if 0 <= idx < len(sorted_srcs):
                s = sorted_srcs[idx]
                return Single(url=s["url"], title=media.title, referrer=media.referrer,
                               year=media.year, subtitles=media.subtitles)
        except (ValueError, IndexError):
            pass

    # Cancelled — return best quality as fallback
    s = sorted_srcs[0]
    return Single(url=s["url"], title=media.title, referrer=media.referrer,
                   year=media.year, subtitles=media.subtitles)


def __movie_menu_loop(media: Media, metadata: Metadata, config):
    """Post-playback menu for movies — ani-cli style."""
    url = media.url
    while True:
        cmd = __fzf(f"Playing {metadata.title}... ", "\n".join(["next", "replay", "change_quality", "quit"]))
        if cmd is None:
            return
        if cmd == "replay":
            __play(media, metadata, config)
        elif cmd == "change_quality":
            if isinstance(media, MultiSourceMedia):
                new_media = __select_quality_fzf(media)
                if new_media:
                    media = new_media
                    __play(media, metadata, config)
        elif cmd in ("quit", "next"):
            return
        else:
            print(f"  Unknown: {cmd}")


def __tv_menu_loop(media: Media, metadata: Metadata, scraper, episode: EpisodeSelector, config):
    """Post-playback menu for TV — ani-cli style."""
    cur_ep = episode.episode
    cur_season = episode.season

    while True:
        cmd = __fzf(f"S{cur_season:02d}E{cur_ep:02d} {metadata.title}... ",
                     "\n".join(["next", "replay", "previous", "select_episode", "change_quality", "quit"]))
        if cmd is None:
            return

        if cmd == "next":
            cur_ep += 1
            new_media = __scrape_episode(scraper, metadata, cur_season, cur_ep)
            if new_media is None:
                print("  No more episodes.")
                cur_ep -= 1
                continue
            media = new_media
            __play(media, metadata, config)

        elif cmd == "previous":
            if cur_ep > 1:
                cur_ep -= 1
                new_media = __scrape_episode(scraper, metadata, cur_season, cur_ep)
                if new_media is None:
                    cur_ep += 1
                    continue
                media = new_media
                __play(media, metadata, config)
            else:
                print("  Already at episode 1.")

        elif cmd == "replay":
            __play(media, metadata, config)

        elif cmd == "select_episode":
            new_ep = __prompt_episode(cur_ep)
            if new_ep and new_ep != cur_ep:
                cur_ep = new_ep
                new_media = __scrape_episode(scraper, metadata, cur_season, cur_ep)
                if new_media is None:
                    continue
                media = new_media
                __play(media, metadata, config)

        elif cmd == "change_quality":
            if isinstance(media, MultiSourceMedia):
                new_media = __select_quality_fzf(media)
                if new_media:
                    media = new_media
                    __play(media, metadata, config)
            else:
                print("  Only one quality.")

        elif cmd == "quit":
            return
        else:
            print(f"  Unknown: {cmd}")


def __prompt_episode(current: int) -> Optional[int]:
    """Prompt for episode number."""
    try:
        raw = input(f"  Episode ({current}): ").strip()
        return int(raw) if raw else None
    except (ValueError, EOFError, KeyboardInterrupt):
        return None


def __scrape_episode(scraper, metadata, season: int, episode: int) -> Optional[Media]:
    ep = EpisodeSelector(season=season, episode=episode)
    result = scraper.scrape(metadata, ep)
    if isinstance(result, (Multi, Single, MultiSourceMedia)):
        return result
    return None
