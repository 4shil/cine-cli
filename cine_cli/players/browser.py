from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional, List

    from ..media import Media
    from ..utils.platform import SUPPORTED_PLATFORMS

import shutil
import subprocess
from devgoldyutils import Colours

from .player import Player

__all__ = ("Browser",)

class Browser(Player):
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
        return Colours.PURPLE.apply("Browser")

    def _command(self, url: str) -> Optional[List[str]]:
        if self.platform == "Darwin":
            return ["open", url]

        if self.platform == "Windows":
            return ["cmd", "/c", "start", "", url]

        browser = shutil.which("zen-browser") or shutil.which("xdg-open")
        if browser is None:
            browser = shutil.which("firefox") or shutil.which("brave") or shutil.which("chromium")

        if browser is None:
            return None

        command = [browser, url]
        return self.handle_additional_args(command, self.args)

    def play(self, media: Media) -> Optional[subprocess.Popen]:
        """Open media in the system browser.

        This is useful for browser-only embed pages like vidsrc.to/embed/* where
        MPV/VLC receive HTML instead of a direct HLS/MP4 stream.
        """

        command = self._command(media.url)
        if command is None:
            return None

        return subprocess.Popen(
            command,
            stdin = subprocess.DEVNULL,
            stdout = subprocess.DEVNULL,
            stderr = subprocess.DEVNULL,
            start_new_session = True,
        )
