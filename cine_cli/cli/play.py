"""Playback module for cine-cli.

Default: open stream URL in default browser (xdg-open).
No menus, no MPV, no extra prompts — just open and play.
Use --player mpv to use MPV instead.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional

import subprocess
import os

if TYPE_CHECKING:
    from typing import Literal

from devgoldyutils import Colours

from ..media import Media, Metadata, Multi, Single, MultiSourceMedia, MetadataType
from ..logger import cine_cli_logger
from ..cache import Cache
from ..utils import what_platform, EpisodeSelector


def play(media: Media, metadata: Metadata, scraper, episode, config) -> Optional[Literal["search"]]:
    """Play media — open URL in browser or configured player."""
    platform = what_platform()
    cache = Cache(platform)
    cache.set_cache(str(metadata.id), episode.__dict__)

    # Quality selection for MultiSourceMedia
    if isinstance(media, MultiSourceMedia):
        selected = __select_quality_fzf(media)
        if selected is None:
            return None
        media = selected

    # Play
    __play(media, metadata, config)
    return None


def __play(media: Media, metadata: Metadata, config):
    """Open stream URL in browser (default) or configured player."""
    title = metadata.display_name if hasattr(metadata, 'display_name') else metadata.title
    url = media.url
    player = (config.player or "browser").lower()

    cine_cli_logger.info(f"Playing '{Colours.BLUE.apply(title)}'...")

    env = os.environ.copy()

    if player in ("browser", "xdg-open", "chrome", "firefox", "brave", "zen"):
        try:
            subprocess.Popen(["xdg-open", url], env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            cine_cli_logger.error("xdg-open not found!")
    elif player == "mpv":
        import shlex, time
        cmd = ["mpv", url, f"--force-media-title={title}", "--force-window=immediate"]
        if media.referrer:
            cmd.append(f"--referrer={media.referrer}")
        escaped = " ".join(shlex.quote(c) for c in cmd)
        subprocess.Popen(f"nohup {escaped} >/dev/null 2>&1 &", shell=True, env=env)
        time.sleep(1)
    elif player == "vlc":
        try:
            subprocess.Popen(["vlc", url], env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            cine_cli_logger.error("VLC not found, falling back to browser")
            subprocess.Popen(["xdg-open", url], env=env)
    else:
        # Custom player
        try:
            subprocess.Popen([player, url], env=env)
        except FileNotFoundError:
            cine_cli_logger.error(f"Player '{player}' not found, falling back to browser")
            subprocess.Popen(["xdg-open", url], env=env)


def __select_quality_fzf(media: MultiSourceMedia) -> Optional[Single]:
    """Select quality via fzf. Auto-select best if fzf unavailable."""
    sources = media.sources
    if not sources:
        return None
    if len(sources) == 1:
        s = sources[0]
        return Single(url=s["url"], title=media.title, referrer=media.referrer,
                       year=media.year, subtitles=media.subtitles)

    # Sort by quality (highest first)
    qo = {"4k": 4, "2160p": 4, "1080p": 3, "720p": 2, "480p": 1, "360p": 0}
    sorted_srcs = sorted(sources, key=lambda s: qo.get(s.get("quality", "").lower(), -1), reverse=True)

    # Try fzf
    from urllib.parse import urlparse
    lines = []
    for i, s in enumerate(sorted_srcs, 1):
        q = s.get("quality", "?")
        domain = urlparse(s["url"]).netloc[:40]
        lines.append(f"{i}. {q:>6}  {domain}")

    selected = __fzf("Select quality: ", "\n".join(lines))
    if selected:
        try:
            idx = int(selected.split(".")[0].strip()) - 1
            if 0 <= idx < len(sorted_srcs):
                s = sorted_srcs[idx]
                return Single(url=s["url"], title=media.title, referrer=media.referrer,
                               year=media.year, subtitles=media.subtitles)
        except (ValueError, IndexError):
            pass

    # Fallback: best quality
    s = sorted_srcs[0]
    return Single(url=s["url"], title=media.title, referrer=media.referrer,
                   year=media.year, subtitles=media.subtitles)


def __fzf(prompt: str, choices: str) -> Optional[str]:
    """Run fzf. Returns selected line or None."""
    try:
        result = subprocess.run(
            ["fzf", "--reverse", "--cycle", "--prompt", prompt],
            input=choices, capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
