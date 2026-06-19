"""TMDB + Multi-Provider scraper for cine-cli.

Uses TMDB for metadata, multiple providers for streaming.
Default: browser playback via provider website URLs.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Iterable, Optional

from cine_cli import Scraper, Metadata, MetadataType, Multi, Single, MultiSourceMedia
from cine_cli.utils import EpisodeSelector
from cine_cli.resolvers.encdec import MultiProviderResolver, PROVIDERS

if TYPE_CHECKING:
    from cine_cli import Config
    from cine_cli.http_client import HTTPClient
    from cine_cli.scraper import ScraperOptionsT

__all__ = ("TmdbScraper",)

TMDB_API_KEY = "1f54bd990f1cdfb230adb312546d765d"
TMDB_BASE = "https://api.themoviedb.org/3"


class TmdbScraper(Scraper):
    """Searches via TMDB, streams via multiple providers."""

    def __init__(self, config: Config, http_client: HTTPClient,
                 options: Optional[ScraperOptionsT] = None) -> None:
        super().__init__(config, http_client, options)
        self.tmdb_key = str(self.options.get("api_key", TMDB_API_KEY))
        self.provider = str(self.options.get("provider", ""))
        self.encdec = MultiProviderResolver()

    def _tmdb_get(self, path: str, params: dict) -> dict:
        params["api_key"] = self.tmdb_key
        resp = self.http_client.request("GET", f"{TMDB_BASE}/{path}", params=params)
        resp.raise_for_status()
        return resp.json()

    def _search_movie(self, query: str, page: int = 1) -> list[dict]:
        data = self._tmdb_get("search/movie", {
            "query": query, "page": str(page),
            "language": "en-US", "include_adult": "false",
        })
        return data.get("results", [])

    def _search_tv(self, query: str, page: int = 1) -> list[dict]:
        data = self._tmdb_get("search/tv", {
            "query": query, "page": str(page),
            "language": "en-US", "include_adult": "false",
        })
        return data.get("results", [])

    def search(self, query: str, limit: Optional[int] = None) -> Iterable[Metadata]:
        import urllib.parse
        encoded = urllib.parse.quote(query)
        movies = self._search_movie(encoded)
        tv_shows = self._search_tv(encoded)
        results: list[Metadata] = []

        for item in movies:
            tmdb_id = item["id"]
            title = item.get("title", "Unknown")
            year = (item.get("release_date", "") or "")[:4]
            poster = item.get("poster_path", "") or ""
            image_url = f"https://image.tmdb.org/t/p/w500{poster}" if poster else ""
            results.append(Metadata(
                id=f"tmdb:{tmdb_id}", title=title, type=MetadataType.SINGLE,
                image_url=image_url, year=year,
            ))

        for item in tv_shows:
            tmdb_id = item["id"]
            title = item.get("name", "Unknown")
            year = (item.get("first_air_date", "") or "")[:4]
            poster = item.get("poster_path", "") or ""
            image_url = f"https://image.tmdb.org/t/p/w500{poster}" if poster else ""
            results.append(Metadata(
                id=f"tmdb:{tmdb_id}", title=title, type=MetadataType.MULTI,
                image_url=image_url, year=year,
            ))

        if limit is not None:
            results = results[:limit]

        for r in results:
            yield r

    def scrape(self, metadata: Metadata, episode: EpisodeSelector) -> Optional[Multi | Single | MultiSourceMedia]:
        if metadata.type == MetadataType.MULTI:
            return self._scrape_tv(metadata, episode)
        return self._scrape_movie(metadata)

    def _scrape_movie(self, metadata: Metadata) -> Optional[Single | MultiSourceMedia]:
        tmdb_id = metadata.id
        if tmdb_id.startswith("tmdb:"):
            tmdb_id = tmdb_id.replace("tmdb:", "")

        self.logger.info(f"Scraping '{metadata.title}'...")

        # Get browser URLs for all providers
        urls = self.encdec.get_all_browser_urls(tmdb_id, "movie")

        if not urls:
            self.logger.error(f"No streams found for '{metadata.title}'")
            return None

        # Build sources list
        sources = []
        for pid, url in urls.items():
            pname = PROVIDERS.get(pid, {}).get("name", pid)
            sources.append({"url": url, "quality": pname})

        if len(sources) == 1:
            return Single(url=sources[0]["url"], title=metadata.title, year=metadata.year)

        return MultiSourceMedia(sources=sources, title=metadata.title, year=metadata.year)

    def _scrape_tv(self, metadata: Metadata, episode: EpisodeSelector) -> Optional[Multi | MultiSourceMedia]:
        tmdb_id = metadata.id
        if tmdb_id.startswith("tmdb:"):
            tmdb_id = tmdb_id.replace("tmdb:", "")

        self.logger.info(f"Scraping '{metadata.title}' S{episode.season}E{episode.episode}...")

        urls = self.encdec.get_all_browser_urls(tmdb_id, "tv",
                                                 str(episode.season), str(episode.episode))

        if not urls:
            self.logger.error(f"No streams found for '{metadata.title}'")
            return None

        sources = []
        for pid, url in urls.items():
            pname = PROVIDERS.get(pid, {}).get("name", pid)
            sources.append({"url": url, "quality": pname})

        if len(sources) == 1:
            return Multi(url=sources[0]["url"], title=metadata.title,
                         episode=episode, subtitles=None)

        return Multi(url=sources[0]["url"] if sources else "", title=metadata.title,
                     episode=episode, subtitles=None)

    def scrape_episodes(self, metadata: Metadata) -> Dict:
        if metadata.type == MetadataType.MULTI:
            return {1: 1}
        return {None: 1}
