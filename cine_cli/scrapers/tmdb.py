"""TMDB + Multi-Provider scraper for cine-cli.

Uses TMDB for metadata (search), converts to IMDb ID for streaming.
All providers use IMDb IDs. Provider selector via fzf after episode selection.
Default provider: vidsrc.to (listed first).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Iterable, Optional

from cine_cli import Scraper, Metadata, MetadataType, Multi, Single, MultiSourceMedia
from cine_cli.utils import EpisodeSelector
from cine_cli.resolvers.encdec import get_provider_url, get_all_urls, PROVIDERS

if TYPE_CHECKING:
    from cine_cli import Config
    from cine_cli.http_client import HTTPClient
    from cine_cli.scraper import ScraperOptionsT

__all__ = ("TmdbScraper",)

TMDB_API_KEY = "1f54bd990f1cdfb230adb312546d765d"
TMDB_BASE = "https://api.themoviedb.org/3"


class TmdbScraper(Scraper):
    """Searches via TMDB, streams via IMDb ID on multiple providers."""

    def __init__(self, config: Config, http_client: HTTPClient,
                 options: Optional[ScraperOptionsT] = None) -> None:
        super().__init__(config, http_client, options)
        self.tmdb_key = str(self.options.get("api_key", TMDB_API_KEY))
        self.default_provider = str(self.options.get("provider", "vidsrc"))

    def _tmdb_get(self, path: str, params: dict) -> dict:
        params["api_key"] = self.tmdb_key
        resp = self.http_client.request("GET", f"{TMDB_BASE}/{path}", params=params)
        resp.raise_for_status()
        return resp.json()

    def _external_ids(self, tmdb_id: str, media_type: str = "movie") -> dict:
        try:
            return self._tmdb_get(f"{media_type}/{tmdb_id}/external_ids", {})
        except Exception:
            return {}

    def search(self, query: str, limit: Optional[int] = None) -> Iterable[Metadata]:
        import urllib.parse
        encoded = urllib.parse.quote(query)

        try:
            data = self._tmdb_get("search/multi", {
                "query": encoded, "page": "1",
                "language": "en-US", "include_adult": "false",
            })
            items = data.get("results", [])
        except Exception:
            items = []

        results: list[Metadata] = []

        for item in items:
            tmdb_id = str(item.get("id", ""))
            if not tmdb_id:
                continue

            media_type = item.get("media_type", "")

            if media_type == "movie":
                title = item.get("title", "Unknown")
                year = (item.get("release_date", "") or "")[:4]
                imdb_id = item.get("imdb_id", "")
                if not imdb_id:
                    ext = self._external_ids(tmdb_id, "movie")
                    imdb_id = ext.get("imdb_id", "")
                mid = f"imdb:{imdb_id}" if imdb_id else f"tmdb:{tmdb_id}"
                results.append(Metadata(id=mid, title=title, type=MetadataType.SINGLE, year=year))

            elif media_type == "tv":
                title = item.get("name", "Unknown")
                year = (item.get("first_air_date", "") or "")[:4]
                imdb_id = item.get("imdb_id", "")
                if not imdb_id:
                    ext = self._external_ids(tmdb_id, "tv")
                    imdb_id = ext.get("imdb_id", "")
                mid = f"imdb:{imdb_id}" if imdb_id else f"tmdb:{tmdb_id}"
                results.append(Metadata(id=mid, title=title, type=MetadataType.MULTI, year=year))

        if limit is not None:
            results = results[:limit]

        for r in results:
            yield r

    def scrape(self, metadata: Metadata, episode: EpisodeSelector) -> Optional[Multi | Single | MultiSourceMedia]:
        if metadata.type == MetadataType.MULTI:
            return self._scrape_tv(metadata, episode)
        return self._scrape_movie(metadata)

    def _get_imdb_id(self, metadata: Metadata) -> str:
        mid = metadata.id
        if mid.startswith("imdb:"):
            return mid.replace("imdb:", "")
        if mid.startswith("tmdb:"):
            tmdb_id = mid.replace("tmdb:", "")
            ext = self._external_ids(tmdb_id, "movie")
            imdb_id = ext.get("imdb_id", "")
            if imdb_id:
                return imdb_id
            return tmdb_id
        return mid

    def _scrape_movie(self, metadata: Metadata) -> Optional[Single | MultiSourceMedia]:
        imdb_id = self._get_imdb_id(metadata)
        self.logger.info(f"Scraping '{metadata.title}' ({imdb_id})...")

        # Get all provider URLs
        all_urls = get_all_urls(imdb_id, "movie")
        if not all_urls:
            self.logger.error(f"No streams found for '{metadata.title}'")
            return None

        # Build provider list with vidsrc first
        provider_list = []
        for pid, pconfig in sorted(PROVIDERS.items(), key=lambda x: x[1]["priority"]):
            if pid in all_urls:
                provider_list.append((pid, pconfig["name"], all_urls[pid]))

        if not provider_list:
            self.logger.error(f"No streams found for '{metadata.title}'")
            return None

        # Store all provider URLs for the provider selector
        sources = []
        for pid, pname, purl in provider_list:
            sources.append({"url": purl, "quality": pname, "provider": pid})

        # Return MultiSourceMedia — provider selector will pick one
        return MultiSourceMedia(sources=sources, title=metadata.title, year=metadata.year)

    def _scrape_tv(self, metadata: Metadata, episode: EpisodeSelector) -> Optional[Multi | MultiSourceMedia]:
        imdb_id = self._get_imdb_id(metadata)
        season = str(episode.season)
        episode_num = str(episode.episode)

        self.logger.info(f"Scraping '{metadata.title}' S{season}E{episode_num} ({imdb_id})...")

        all_urls = get_all_urls(imdb_id, "tv", season, episode_num)
        if not all_urls:
            self.logger.error(f"No streams found for '{metadata.title}'")
            return None

        provider_list = []
        for pid, pconfig in sorted(PROVIDERS.items(), key=lambda x: x[1]["priority"]):
            if pid in all_urls:
                provider_list.append((pid, pconfig["name"], all_urls[pid]))

        if not provider_list:
            self.logger.error(f"No streams found for '{metadata.title}'")
            return None

        sources = []
        for pid, pname, purl in provider_list:
            sources.append({"url": purl, "quality": pname, "provider": pid})

        return MultiSourceMedia(sources=sources, title=metadata.title, year=metadata.year)

    def scrape_episodes(self, metadata: Metadata) -> Dict:
        if metadata.type == MetadataType.MULTI:
            return {1: 10, 2: 10, 3: 10}
        return {None: 1}
