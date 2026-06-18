from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional, List

    from ..media import Media
    from ..utils.platform import SUPPORTED_PLATFORMS

import subprocess
from devgoldyutils import Colours
from abc import ABC, abstractmethod

__all__ = ("Player",)

class Player(ABC):
    """A base class for all players in cine-cli."""
    def __init__(
        self, 
        platform: Optional[SUPPORTED_PLATFORMS] = None, 
        args: Optional[List[str]] = None, 
        args_override: bool = False, 
        debug: bool = False, 
        **kwargs
    ) -> None:
        self.platform = platform
        self.args = args or []
        self.args_override = args_override
        self.debug = debug

        super().__init__()

    @property
    def display_name(self) -> str:
        return Colours.PINK_GREY.apply(self.__class__.__name__)

    @abstractmethod
    def play(self, media: Media) -> Optional[subprocess.Popen]:
        """Method to be overridden with code to play media in that specific player."""
        ...

    def handle_additional_args(self, default_args: List[str], additional_args: List[str]) -> List[str]:
        handled_args = default_args

        if self.args_override is True:
            return additional_args

        for arg in additional_args:

            if arg not in handled_args:
                handled_args.append(arg)

        return handled_args