from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional, List

    from ..media import Media
    from ..utils.platform import SUPPORTED_PLATFORMS

import subprocess
from devgoldyutils import Colours

from .player import Player

__all__ = ("IINA",)

class IINA(Player):
    def __init__(
        self, 
        platform: SUPPORTED_PLATFORMS, 
        args: Optional[List[str]] = None, 
        args_override: bool = False, 
        debug: bool = False, 
        **kwargs
    ) -> None:
        super().__init__(
            platform = platform, 
            args = args, 
            debug = debug,
            args_override = args_override
        )

    @property
    def display_name(self):
        return Colours.GREY.apply("IINA")

    def play(self, media: Media) -> Optional[subprocess.Popen]:
        """Plays this media in the IINA media player for MacOS."""

        if self.platform == "Darwin":
            default_args = [
                "iina", 
                "--keep-running", 
                media.url
            ]

            if media.audio_url is not None: # TODO: This will need testing.
                default_args.append(f"--mpv-audio-file={media.audio_url}")

            additional_args = [
                f"--mpv-force-media-title={media.display_name}",
            ]

            if media.referrer is not None:
                additional_args.append(f"--mpv-referrer={media.referrer}")

            if media.subtitles is not None: # TODO: This will need testing.

                for subtitle in media.subtitles:
                    additional_args.append(f"--mpv-sub-file={subtitle}")

            if self.debug is False:
                additional_args.append("--no-stdin")

            additional_args = self.handle_additional_args(additional_args, self.args)

            return subprocess.Popen(
                default_args + additional_args
            )

        return None