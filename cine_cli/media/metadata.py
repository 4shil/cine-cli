from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import List, Callable, Optional, Tuple

from enum import Enum
from devgoldyutils import Colours
from dataclasses import dataclass, field

__all__ = (
    "MetadataType", 
    "Metadata", 
    "ExtraMetadata", 
    "AiringType"
)

class MetadataType(Enum):
    MULTI = 0
    """Media with multiple seasons and episodes."""
    SINGLE = 1
    """Media with no seasons and episodes. Like a film or short animation."""

class AiringType(Enum):
    DONE = 0
    ONGOING = 1
    PRODUCTION = 2
    RELEASED = 3
    CANCELED = 4

@dataclass
class Metadata:
    """Search results from the providers."""
    id: str
    title: str
    """Title of the Series, Film or TV Station."""
    type: MetadataType
    """The type of metadata. Is it a Series, Film or LIVE TV Station?"""
    image_url: Optional[str] = field(default = None)
    """Image URL to a banner, cover or thumbnail of this media."""
    year: Optional[str] = field(default = None)
    """Year the Series or Film was released."""

    extra_func: Callable[[], Optional[ExtraMetadata]] = field(default = lambda: None)
    """Callback that returns extra metadata."""

    @property
    def display_name(self) -> str:
        return f"{Colours.BLUE if self.type == MetadataType.SINGLE else Colours.PINK_GREY}{self.title}" \
            f"{Colours.RESET}" + (f" ({self.year})" if self.year is not None else "")

    def get_extra(self) -> Optional[ExtraMetadata]:
        """Returns extra metadata."""
        return self.extra_func()

@dataclass
class ExtraMetadata():
    """More in-depth metadata about media."""
    description: Optional[str]
    """Description of Series, Film or TV Station."""
    alternate_titles: List[str] | Tuple[str, str] | None = field(default = None)

    cast: List[str] | None = field(default = None)
    genres: List[str] | None = field(default = None)
    airing: AiringType | None = field(default = None)