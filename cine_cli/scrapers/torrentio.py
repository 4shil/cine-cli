"""Torrentio scraper — uses Torrentio for stream resolution + aria2c for download.

Flow:
1. Search TMDB for metadata
2. Query Torrentio for streams using IMDb ID
3. Pick best stream (prefer direct URL, fallback to torrent)
4. If torrent: download with aria2c
5. Open downloaded file in player (MPV/VLC/browser)
"""
from __future__ import annotations

import os
import subprocess
import time
import signal
import shutil
import urllib.parse
from typing import TYPE_CHECKING, Dict, Iterable, Optional

from cine_cli import Scraper, Metadata, MetadataType, Multi, Single
from cine_cli.utils import EpisodeSelector
from cine_cli.logger import cine_cli_logger

if TYPE_CHECKING:
    from cine_cli import Config
    from cine_cli.http_client import HTTPClient
    from cine_cli.scraper import ScraperOptionsT

__all__ = ("TorrentioScraper",)

import json
import urllib.request
import re

TMDB_API_KEY = "1f54bd990f1cdfb230adb312546d765d"
TMDB_BASE = "https://api.themoviedb.org/3"
TORRENTIO_BASE = "https://torrentio.strem.fun"
TORRENTIO_CONFIG = "providers=yts,eztv,rarbg,1337x,thepiratebay|qualityfilter=480p,720p,1080p|sort=qualitysize"

DOWNLOAD_DIR = "/tmp/cine-cli-downloads"
ARIA2C_TIMEOUT = 600  # 10 minutes max download


class TorrentioScraper(Scraper):
    """Searches via TMDB, resolves streams via Torrentio, downloads with aria2c."""

    def __init__(
        self,
        config: Config,
        http_client: HTTPClient,
        options: Optional[ScraperOptionsT] = None,
    ) -> None:
        super().__init__(config, http_client, options)
        self.tmdb_key = str(self.options.get("api_key", TMDB_API_KEY))
        self.torrentio_config = str(self.options.get("torrentio_config", TORRENTIO_CONFIG))
        self._download_process: Optional[subprocess.Popen] = None

    def __del__(self):
        if self._download_process:
            try:
                self._download_process.terminate()
            except Exception:
                pass

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
    #  Torrentio resolver
    # ------------------------------------------------------------------ #

    def _torrentio_query(self, media_type: str, imdb_id: str) -> list[dict]:
        url = f"{TORRENTIO_BASE}/{self.torrentio_config}/stream/{media_type}/{imdb_id}.json"
        self.logger.debug(f"[torrentio] Querying: {url[:120]}...")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cine-cli/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read())
            return data.get("streams", [])
        except Exception as e:
            self.logger.error(f"[torrentio] Query failed: {e}")
            return []

    def _pick_stream(self, streams: list[dict], prefer_quality: str = "1080p") -> Optional[dict]:
        if not streams:
            return None
        direct = [s for s in streams if s.get("url")]
        torrents = [s for s in streams if s.get("infoHash")]

        def quality(s):
            name = s.get("name", "")
            for q in ("4k", "2160p", "1080p", "720p", "480p"):
                if q in name:
                    return q
            return ""

        def seeders(s):
            """Extract seeder count from title."""
            title = s.get("title", "")
            m = re.search(r"👤\s*(\d+)", title)
            return int(m.group(1)) if m else 0

        # Sort torrents by seeders (descending), then prefer quality
        torrents_sorted = sorted(torrents, key=lambda s: (-seeders(s), quality(s) != prefer_quality))

        # Prefer direct URL at preferred quality
        for s in direct:
            if quality(s) == prefer_quality:
                return s
        if direct:
            return direct[0]

        # Pick torrent with most seeders at preferred quality
        for s in torrents_sorted:
            if quality(s) == prefer_quality:
                return s
        if torrents_sorted:
            return torrents_sorted[0]

        return None

    # ------------------------------------------------------------------ #
    #  Download with aria2c
    # ------------------------------------------------------------------ #

    def _download_torrent(self, info_hash: str, title: str) -> Optional[str]:
        """Download torrent using aria2c. Returns path to downloaded file."""
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

        # Clean up old downloads
        if os.path.exists(DOWNLOAD_DIR):
            shutil.rmtree(DOWNLOAD_DIR)
        os.makedirs(DOWNLOAD_DIR)

        magnet = (
            f"magnet:?xt=urn:btih:{info_hash}"
            f"&dn={urllib.parse.quote(title)}"
            "&tr=udp://tracker.opentrackr.org:1337/announce"
            "&tr=udp://open.stealth.si:80/announce"
            "&tr=udp://tracker.torrent.eu.org:451/announce"
            "&tr=udp://exodus.desync.com:6969/announce"
        )

        cmd = [
            "aria2c",
            "--dir", DOWNLOAD_DIR,
            "--seed-time=0",
            "--bt-stop-timeout=300",
            "--max-connection-per-server=16",
            "--min-split-size=1M",
            "--split=16",
            "--max-overall-download-limit=0",
            "--continue=true",
            "--file-allocation=none",
            "--summary-interval=5",
            "--console-log-level=notice",
            "--quiet=false",
            magnet,
        ]

        self.logger.info(f"[download] Starting aria2c download...")
        self._download_process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )

        # Monitor download with non-blocking reads
        downloaded_file = None
        start_time = time.time()

        while time.time() - start_time < ARIA2C_TIMEOUT:
            if self._download_process.poll() is not None:
                break

            # Check for completed video files
            for root, dirs, files in os.walk(DOWNLOAD_DIR):
                for f in files:
                    if f.endswith((".mp4", ".mkv", ".avi", ".webm", ".mov")):
                        fp = os.path.join(root, f)
                        sz = os.path.getsize(fp)
                        if sz > 10 * 1024 * 1024:
                            downloaded_file = fp
                            self.logger.info(f"[download] Found: {f} ({sz/(1024*1024):.0f} MB)")

            # Non-blocking read of aria2c output
            import select as _select
            if self._download_process.stdout and _select.select([self._download_process.stdout], [], [], 0)[0]:
                try:
                    line = self._download_process.stdout.readline()
                    if line:
                        line = line.strip()
                        if "%" in line or "MB" in line:
                            self.logger.info(f"[aria2c] {line[:120]}")
                except Exception:
                    pass

            time.sleep(2)

        # Check if download completed
        if downloaded_file and os.path.exists(downloaded_file):
            self.logger.info(f"[download] Complete: {downloaded_file}")
            return downloaded_file

        # Check for any video file
        for root, dirs, files in os.walk(DOWNLOAD_DIR):
            for f in files:
                if f.endswith((".mp4", ".mkv", ".avi", ".webm", ".mov")):
                    fp = os.path.join(root, f)
                    sz = os.path.getsize(fp)
                    if sz > 1024 * 1024:  # At least 1MB
                        return fp

        self.logger.error("[download] Failed to download file")
        return None

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
            imdb_id = metadata.id
            if imdb_id.isdigit():
                imdb_id = f"tt{int(imdb_id):07d}"
            streams = self._torrentio_query("series", f"{imdb_id}:{episode.season}:{episode.episode}")
            stream = self._pick_stream(streams)
            if stream is None:
                return None

            if stream.get("url"):
                return Multi(url=stream["url"], title=metadata.title,
                             referrer=None, episode=episode, subtitles=None)

            if stream.get("infoHash"):
                file_path = self._download_torrent(stream["infoHash"], metadata.title)
                if file_path:
                    return Multi(url=f"file://{file_path}", title=metadata.title,
                                 referrer=None, episode=episode, subtitles=None)
            return None

        # Movie
        imdb_id = metadata.id
        if imdb_id.startswith("tmdb:"):
            self.logger.error("[torrentio] Cannot resolve without IMDb ID")
            return None
        if not imdb_id.startswith("tt"):
            imdb_id = f"tt{int(imdb_id):07d}"

        streams = self._torrentio_query("movie", imdb_id)
        stream = self._pick_stream(streams)

        if stream is None:
            self.logger.error(f"[torrentio] No streams found for {imdb_id}")
            return None

        # Direct URL (debrid)
        if stream.get("url"):
            return Single(url=stream["url"], title=metadata.title,
                          referrer=None, year=metadata.year)

        # Torrent → download → play local file
        if stream.get("infoHash"):
            self.logger.info(f"[torrentio] Downloading torrent...")
            file_path = self._download_torrent(stream["infoHash"], metadata.title)
            if file_path:
                return Single(url=f"file://{file_path}", title=metadata.title,
                              referrer=None, year=metadata.year)

        return None

    def scrape_episodes(self, metadata: Metadata) -> Dict:
        if metadata.type == MetadataType.MULTI:
            return {1: 1}
        return {None: 1}
