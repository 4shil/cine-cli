from __future__ import annotations
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from typing import Optional

    from ..media import Media
    from ..utils.platform import SUPPORTED_PLATFORMS, Literal

import shutil
import subprocess
from devgoldyutils import Colours

from ..errors import ReferrerNotSupportedError

from .player import Player

__all__ = ("MPV",)

DIRECT_MEDIA_MARKERS = (
    ".m3u8", ".mp4", ".mkv", ".webm", ".mov", ".avi",
    ".mp3", ".m4a", ".flac", ".ogg", "manifest.mpd",
)

BROWSER_ONLY_MARKERS = (
    "/embed/", "vidsrc.", "vsembed.", "multiembed.", "autoembed.",
)

class MPV(Player):
    def __init__(
        self,
        platform: SUPPORTED_PLATFORMS,
        args: Optional[List[str]] = None,
        args_override: bool = False,
        debug: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(
            platform = platform,
            args = args,
            debug = debug,
            args_override = args_override,
        )

    @property
    def display_name(self) -> str:
        return Colours.PURPLE.apply("MPV")

    def _get_args(self, platform: Literal["Windows", "Linux", "Android", "Darwin"], media: Media):
        if platform == "Android":
            return []

        args = [
            f"--force-media-title={media.display_name}",
            "--input-terminal=no",
            "--keep-running",
        ]

        if media.referrer is not None:
            args.append(f"--referrer={media.referrer}")

        if media.subtitles is not None:
            for subtitle in media.subtitles:
                args.append(f"--sub-file={subtitle}")

        if self.debug is False:
            args.append("--no-terminal")

        args = self.handle_additional_args(args, self.args)

        return args

    def _is_direct_media_url(self, url: str) -> bool:
        normalized = url.lower().split("?", 1)[0]
        return any(marker in normalized for marker in DIRECT_MEDIA_MARKERS)

    def _is_browser_only_url(self, url: str) -> bool:
        normalized = url.lower()
        return not self._is_direct_media_url(url) and any(marker in normalized for marker in BROWSER_ONLY_MARKERS)

    def _open_browser(self, media: Media) -> Optional[subprocess.Popen]:
        """Open browser-only embed pages in a real browser.

        ani-cli resolves direct media links before calling MPV. cine-cli's current
        TMDB scraper can return browser embed pages such as vidsrc.to/embed/*.
        MPV cannot play those HTML pages, so falling back to the browser is better
        than launching MPV and immediately exiting silently.
        """

        if self.platform == "Darwin":
            command = ["open", media.url]
        elif self.platform == "Windows":
            command = ["cmd", "/c", "start", "", media.url]
        else:
            browser = shutil.which("zen-browser") or shutil.which("xdg-open")
            if browser is None:
                browser = shutil.which("firefox") or shutil.which("brave")

            if browser is None:
                return None

            command = [browser, media.url]

        return subprocess.Popen(
            command,
            stdin = subprocess.DEVNULL,
            stdout = subprocess.DEVNULL,
            stderr = subprocess.DEVNULL,
            start_new_session = True,
        )

    def play(self, media: Media) -> Optional[subprocess.Popen]:
        """Plays this media in the MPV media player."""

        if self.platform == "Android":

            if media.referrer is not None:
                raise ReferrerNotSupportedError(
                    "The MPV player on Android does not support passing referrers, so this media cannot be played. :("
                )

            return subprocess.Popen(
                [
                    "am",
                    "start",
                    "-n",
                    "is.xyz.mpv/is.xyz.mpv.MPVActivity",
                    "-e",
                    "filepath",
                    media.url,
                ]
            )

        elif self.platform == "Linux" or self.platform == "Windows" or self.platform == "Darwin" or self.platform == "FreeBSD":
            if self._is_browser_only_url(media.url):
                return self._open_browser(media)

            default_args = [
                "mpv",
                media.url
            ]

            if media.audio_url is not None:
                default_args.append(f"--audio-file={media.audio_url}")

            if self.debug:
                return subprocess.Popen(
                    default_args + self._get_args(self.platform, media),
                )

            # Replicate ani-cli's: nohup mpv ... >/dev/null 2>&1 &
            # start_new_session=True creates a new session, fully detaching from the terminal.
            # MPV uses --input-terminal=no and --no-terminal so it doesn't try to control stdin/stdout.
            # This prevents "inappropriate ioctl for device" (ENOTTY) errors
            # when running inside GUI terminals that aren't real PTYs.
            return subprocess.Popen(
                default_args + self._get_args(self.platform, media),
                stdin = subprocess.DEVNULL,
                stdout = subprocess.DEVNULL,
                stderr = subprocess.DEVNULL,
                start_new_session = True,
            )

        return None
