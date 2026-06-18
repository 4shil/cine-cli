from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    ...

from enum import Enum

__all__ = ("Quality", )

class Quality(Enum):
    SD = 480
    HD = 720
    FHD = 1080
    QHD = 1440
    UHD = 2160

    _2K = QHD
    _4K = UHD

    AUTO = 0

    def __init__(self, pixel: int) -> None:
        ...

    def apply_p(self) -> str:
        """Returns that enum but with an ending p."""
        return f"{self.value}p"