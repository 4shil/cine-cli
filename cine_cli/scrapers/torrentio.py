"""Torrentio scraper — uses Torrentio for stream resolution + local torrent-to-HTTP streaming."""
from __future__ import annotations

import os
import subprocess
import time
import signal
import socket
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

TMDB_API_KEY = "1f54bd990f1cdfb230adb312546d765d"
TMDB_BASE = "https://api.themoviedb.org/3"
TORRENTIO_BASE = "https://torrentio.strem.fun"
TORRENTIO_CONFIG = "providers=yts,eztv,rarbg,1337x,thepiratebay|qualityfilter=480p,720p,1080p|sort=qualitysize"

# Port range for torrent HTTP servers
TORRENT_PORT_START = 18080
TORRENT_PORT_END = 18099


def _find_free_port() -> int:
    """Find a free port in the torrent port range."""
    for port in range(TORRENT_PORT_START, TORRENT_PORT_END + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return TORRENT_PORT_START


class TorrentioScraper(Scraper):
    """Searches via TMDB, resolves streams via Torrentio, serves via local HTTP.

    Flow:
    1. Search TMDB for metadata (same as TmdbScraper)
    2. Query Torrentio for streams using IMDb ID
    3. Pick best stream (prefer direct URL, fallback to torrent)
    4. If torrent: start local torrent-to-HTTP server
    5. Return Single/Multi with localhost URL for MPV/VLC
    """

    def __init__(
        self,
        config: Config,
        http_client: HTTPClient,
        options: Optional[ScraperOptionsT] = None,
    ) -> None:
        super().__init__(config, http_client, options)
        self.tmdb_key = str(self.options.get("api_key", TMDB_API_KEY))
        self.torrentio_config = str(self.options.get("torrentio_config", TORRENTIO_CONFIG))
        self.save_path = str(self.options.get("save_path", "/tmp/cine-cli-torrents"))
        self._torrent_processes: list[subprocess.Popen] = []

    def __del__(self):
        """Clean up torrent processes on exit."""
        for p in self._torrent_processes:
            try:
                p.terminate()
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    #  TMDB API helpers (same as TmdbScraper)
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
        """Query Torrentio for streams."""
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
        """Pick best stream. Prefer direct URLs, then torrents at preferred quality."""
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

        # Prefer direct URL at preferred quality
        for s in direct:
            if quality(s) == prefer_quality:
                return s
        if direct:
            return direct[0]

        # Then torrent at preferred quality
        for s in torrents:
            if quality(s) == prefer_quality:
                return s
        if torrents:
            return torrents[0]

        return None

    # ------------------------------------------------------------------ #
    #  Torrent-to-HTTP streaming
    # ------------------------------------------------------------------ #

    def _start_torrent_stream(self, info_hash: str, file_idx: int = 0) -> tuple[str, subprocess.Popen] | None:
        """Start a torrent-to-HTTP server. Returns (url, process)."""
        port = _find_free_port()
        # Use the standalone torrent stream server script
        torrent_script = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "torrent_stream_server.py"
        )
        torrent_script = os.path.normpath(torrent_script)

        if not os.path.exists(torrent_script):
            # Fallback: try common locations
            for fallback in [
                "/home/ashil/Coding/cine-cli/torrent_stream_server.py",
                os.path.expanduser("~/.local/bin/torrent_stream_server.py"),
            ]:
                if os.path.exists(fallback):
                    torrent_script = fallback
                    break

        cmd = [
            "python3", torrent_script,
            info_hash,
            "--port", str(port),
            "--file-idx", str(file_idx),
        ]

        self.logger.debug(f"[torrent] Starting: {' '.join(cmd)}")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        self._torrent_processes.append(proc)

        # Wait for server to be ready AND have enough data for playback
        url = f"http://127.0.0.1:{port}"
        min_buffer = 50 * 1024 * 1024  # 50MB minimum buffer before playback
        for _ in range(180):  # Up to 3 minutes
            try:
                with urllib.request.urlopen(f"{url}/status", timeout=2) as r:
                    status = json.loads(r.read())
                    file_on_disk = status.get("file_on_disk", 0)
                    progress = status.get("progress", 0)
                    peers = status.get("num_peers", 0)
                    dl_rate = status.get("download_rate_kb", 0)

                    if file_on_disk >= min_buffer or progress >= 95:
                        self.logger.info(
                            f"[torrent] Ready: {url} "
                            f"(progress={progress:.1f}%, "
                            f"on_disk={file_on_disk//(1024*1024)}MB, "
                            f"peers={peers}, "
                            f"dl={dl_rate}KB/s)"
                        )
                        return url, proc
                    else:
                        self.logger.info(
                            f"[torrent] Downloading... {progress:.1f}% "
                            f"({file_on_disk//(1024*1024)}MB on disk, "
                            f"{peers} peers, {dl_rate}KB/s)"
                        )
            except Exception:
                pass
            if proc.poll() is not None:
                out = proc.stdout.read() if proc.stdout else ""
                self.logger.error(f"[torrent] Server process died: {out[:500]}")
                return None
            time.sleep(2)

        # If we couldn't confirm readiness, return anyway — it might still work
        self.logger.warning(f"[torrent] Server may not be ready yet: {url}")
        return url, proc

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
                return Multi(
                    url=stream["url"], title=metadata.title,
                    referrer=None, episode=episode, subtitles=None,
                )

            if stream.get("infoHash"):
                result = self._start_torrent_stream(stream["infoHash"], stream.get("fileIdx", 0))
                if result is None:
                    return None
                url, _ = result
                return Multi(
                    url=url, title=metadata.title,
                    referrer=None, episode=episode, subtitles=None,
                )
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
            return Single(
                url=stream["url"], title=metadata.title,
                referrer=None, year=metadata.year,
            )

        # Torrent — start local HTTP server
        if stream.get("infoHash"):
            self.logger.info(f"[torrentio] Starting torrent stream: {stream.get('name', 'unknown')}")
            result = self._start_torrent_stream(stream["infoHash"], stream.get("fileIdx", 0))
            if result is None:
                self.logger.error("[torrentio] Failed to start torrent server")
                return None
            url, _ = result
            return Single(
                url=url, title=metadata.title,
                referrer=None, year=metadata.year,
            )

        return None

    def scrape_episodes(self, metadata: Metadata) -> Dict:
        if metadata.type == MetadataType.MULTI:
            return {1: 1}
        return {None: 1}
