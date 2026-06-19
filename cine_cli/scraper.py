from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Dict, Literal, Iterable, Optional

    from .config import Config
    from .utils import EpisodeSelector
    from .http_client import HTTPClient
    from .media import Metadata, Multi, Single
    from .media import Metadata, Multi, Single, MultiSourceMedia
    ScraperOptionsT = Dict[str, str | bool]
    ScrapeEpisodesT = Dict[int, int] | Dict[None, Literal[1]]
    ScrapeResultT = Optional[Multi | Single | MultiSourceMedia]

from bs4 import BeautifulSoup
from abc import ABC, abstractmethod
from devgoldyutils import LoggerAdapter

from .logger import cine_cli_logger

__all__ = (
    "Scraper",
)

class Scraper(ABC):
    """A base class for building scrapers from."""
    def __init__(
            self, 
            config: Config, 
            http_client: HTTPClient, 
            options: Optional[ScraperOptionsT] = None
        ) -> None:

        self.config = config
        self.http_client = http_client
        self.options = options or {}

        self.logger = LoggerAdapter(cine_cli_logger, prefix = self.__class__.__name__)

        super().__init__()

    def soup(self, html: str, **kwargs) -> BeautifulSoup:
        """A ready to use beautiful soup instance."""
        return BeautifulSoup(html, self.config.parser, **kwargs)

    @abstractmethod
    def search(self, query: str, limit: Optional[int] = None) -> Iterable[Metadata]:
        """Where your searching for media should be done. Should return or yield Metadata."""
        ...

    @abstractmethod
    def scrape(self, metadata: Metadata, episode: EpisodeSelector) -> ScrapeResultT:
        """
        Where your scraping for the media should be performed. 
        Should return an instance of `Media()` but return `None` if the media is unavailable.
        """
        ...

    def scrape_episodes(self, metadata: Metadata) -> ScrapeEpisodesT:
        """Returns episode count for each season in that Media."""
        return {None: 1}