from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Dict

import json
from pathlib import Path

__all__ = ("Lang", "lang_exists",)

iso_file = Path(__file__).parent.joinpath("iso_639.json")

with iso_file.open("r", encoding="utf-8") as f:
    iso_data = json.load(f)

def lang_exists(alpha2: str) -> bool:
    return alpha2 in iso_data

class Lang():
    def __init__(self, alpha2: str):
        self.data: Dict[str, str] = iso_data.get(alpha2.lower(), {})

    @property
    def name(self):
        return self.data.get("name")
    
    @property
    def nativeName(self):
        return self.data.get("nativeName")

    @property
    def iso639_1(self):
        return self.data.get("639-1")
    
    @property
    def iso639_2(self):
        return self.data.get("639-2")