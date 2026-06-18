from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional, List

    from ..media import Media

import subprocess
from devgoldyutils import Colours, LoggerAdapter

from ..logger import cine_cli_logger
from .player import Player

__all__ = ("CustomPlayer",)

logger = LoggerAdapter(cine_cli_logger, prefix = Colours.GREY.apply("CustomPlayer"))

class CustomPlayer(Player):
    """
    This player is invoked if you set a player that is not supported by cine-cli in the config, allowing users to invoke their own players.
    """
    def __init__(
        self, 
        binary: str, 
        args: Optional[List[str]] = None, 
        debug: bool = False, 
        **kwargs
    ) -> None:
        self.binary = binary

        super().__init__(
            args = args, 
            debug = debug
        )

    def play(self, media: Media) -> subprocess.Popen:
        """Plays this media in a custom player."""
        logger.debug(f"Launching your custom media player '{self.binary}'...")

        return subprocess.Popen(
            [self.binary, media.url] + self.args
        )