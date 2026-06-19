"""Built-in TMDB + Videasy scraper for cine-cli.

Uses TMDB for metadata and Videasy for direct .m3u8 stream URLs.
No browser embeds, no Turnstile — just clean HLS streams.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Iterable, Optional

from cine_cli import Scraper, Metadata, MetadataType, Multi, Single
from cine_cli.utils import EpisodeSelector
from cine_cli.resolvers.videasy import VideasyResolver

if TYPE_CHECKING:
    from cine_cli import Config
    from cine_cli.http_client import HTTPClient
    from cine_cli.scraper import ScraperOptionsT

__all__ = ("TmdbScraper",)

TMDB_API_KEY = "1f54bd990f1cdfb230adb312546d765d"
TMDB_BASE = "https://api.themoviedb.org/3"


class TmdbScraper(Scraper):
    """Searches movies and TV shows via TMDB, streams via Videasy."""

    def __init__(
        self,
        config: Config,
        http_client: HTTPClient,
        options: Optional[ScraperOptionsT] = None,
    ) -> None:
        super().__init__(config, http_client, options)
        self.tmdb_key = str(self.options.get("api_key", TMDB_API_KEY))
        self.videasy = VideasyResolver()

    # ------------------------------------------------------------------ #
    #  TMDB API helpers
    # ------------------------------------------------------------------ #

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

    def _external_ids(self, tmdb_id: int, media_type: str = "movie") -> dict:
        try:
            return self._tmdb_get(f"{media_type}/{tmdb_id}/external_ids", {})
        except Exception:
            return {}

    # ------------------------------------------------------------------ #
    #  Scraper interface
    # ------------------------------------------------------------------ #

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
            imdb_id = item.get("imdb_id", "")

            if not imdb_id:
                ext = self._external_ids(tmdb_id, "movie")
                imdb_id = ext.get("imdb_id", "")

            if imdb_id:
                results.append(Metadata(
                    id=imdb_id, title=title, type=MetadataType.SINGLE,
                    image_url=image_url, year=year,
                ))
            else:
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
                id=str(tmdb_id), title=title, type=MetadataType.MULTI,
                image_url=image_url, year=year,
            ))

        if limit is not None:
            results = results[:limit]

        for r in results:
            yield r

    def scrape(self, metadata: Metadata, episode: EpisodeSelector) -> Optional[Multi | Single]:
        if metadata.type == MetadataType.MULTI:
            return self._scrape_tv(metadata, episode)
        return self._scrape_movie(metadata)

    def _scrape_movie(self, metadata: Metadata) -> Optional[Single]:
        imdb_id = metadata.id
        tmdb_id = imdb_id

        # If we have a TMDB ID, convert to IMDb
        if imdb_id.startswith("tmdb:"):
            tmdb_id = imdb_id.replace("tmdb:", "")
        elif not imdb_id.startswith("tt"):
            tmdb_id = f"tt{int(imdb_id):07d}"

        # Try Videasy resolver
        self.logger.info(f"Scraping '{metadata.title}' via Videasy...")
        stream_url = self.videasy.get_best_stream(
            tmdb_id=tmdb_id,
            title=metadata.title,
            media_type="movie",
            year=metadata.year or "",
        )

        if stream_url:
            return Single(
                url=stream_url,
                title=metadata.title,
                referrer="https://www.vidking.net/",
                year=metadata.year,
            )

        self.logger.error(f"No streams found for '{metadata.title}'")
        return None

    def _scrape_tv(self, metadata: Metadata, episode: EpisodeSelector) -> Optional[Multi]:
        imdb_id = metadata.id
        tmdb_id = imdb_id

        if imdb_id.isdigit():
            tmdb_id = f"tt{int(imdb_id):07d}"

        self.logger.info(f"Scraping '{metadata.title}' S{episode.season}E{episode.episode} via Videasy...")
        stream_url = self.videasy.get_best_stream(
            tmdb_id=tmdb_id,
            title=metadata.title,
            media_type="tv",
            year=metadata.year or "",
            season=str(episode.season),
            episode=str(episode.episode),
        )

        if stream_url:
            return Multi(
                url=stream_url,
                title=metadata.title,
                referrer="https://www.vidking.net/",
                episode=episode,
                subtitles=None,
            )

        self.logger.error(f"No streams found for '{metadata.title}'")
        return None

    def scrape_episodes(self, metadata: Metadata) -> Dict:
        if metadata.type == MetadataType.MULTI:
            return {1: 1}
        return {None: 1}
