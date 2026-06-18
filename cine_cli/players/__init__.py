from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Dict, Type

from .player import *

from .mpv import *
from .vlc import *
from .iina import *
from .syncplay import *
from .custom_player import *

PLAYER_TABLE: Dict[str, Type[Player]] = {
    "mpv": MPV, 
    "vlc": VLC, 
    "syncplay": SyncPlay, 
    "iina": IINA
}