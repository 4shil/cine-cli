"""Torrentio resolver — queries Torrentio for streams and returns playable info."""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional, List

if TYPE_CHECKING:
    from ..media import Media

import json
import urllib.request
import urllib.parse

from ..logger import cine_cli_logger

__all__ = ("TorrentioResolver",)

DEFAULT_BASE_URL = "https://torrentio.strem.fun"
DEFAULT_CONFIG = "providers=yts,eztv,rarbg,1337x,thepiratebay|qualityfilter=480p,720p,1080p|sort=qualitysize"


class TorrentioStream:
    """Represents a single stream from Torrentio."""

    def __init__(self, data: dict):
        self.name: str = data.get("name", "")
        self.title: str = data.get("title", "")
        self.info_hash: Optional[str] = data.get("infoHash")
        self.file_idx: int = data.get("fileIdx", 0)
        self.url: Optional[str] = data.get("url")  # Direct URL (debrid)
        self.filename: str = data.get("behaviorHints", {}).get("filename", "")
        self.binge_group: str = data.get("behaviorHints", {}).get("bingeGroup", "")

    @property
    def quality(self) -> str:
        """Extract quality label from name."""
        parts = self.name.replace("\n", " ").split()
        for p in parts:
            if p in ("4k", "2160p", "1080p", "720p", "480p", "360p"):
                return p
        return "unknown"

    @property
    def has_direct_url(self) -> bool:
        return bool(self.url)

    @property
    def has_torrent(self) -> bool:
        return bool(self.info_hash)

    def __repr__(self):
        return f"<TorrentioStream quality={self.quality} hash={self.info_hash[:16] if self.info_hash else None} url={'yes' if self.url else 'no'}>"


class TorrentioResolver:
    """Queries Torrentio for movie/TV streams.

    Returns TorrentioStream objects that can be:
    - Direct URL (debrid) -> pass straight to MPV/VLC
    - infoHash (torrent) -> use torrent_stream.py to serve over HTTP
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        config: str = DEFAULT_CONFIG,
        debrid_api_key: Optional[str] = None,
        debrid_service: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.config = config
        self.debrid_api_key = debrid_api_key
        self.debrid_service = debrid_service

    def _build_url(self) -> str:
        url = f"{self.base_url}/{self.config}"
        if self.debrid_api_key and self.debrid_service:
            url += f"|{self.debrid_service}={self.debrid_api_key}"
        return url

    def _api_url(self, media_type: str, imdb_id: str) -> str:
        base = self._build_url()
        return f"{base}/stream/{media_type}/{imdb_id}.json"

    def resolve_movie(self, imdb_id: str, timeout: int = 20) -> List[TorrentioStream]:
        """Resolve streams for a movie by IMDb ID."""
        url = self._api_url("movie", imdb_id)
        cine_cli_logger.debug(f"[torrentio] Querying: {url[:120]}...")
        return self._query(url, timeout)

    def resolve_tv(self, imdb_id: str, season: int, episode: int, timeout: int = 20) -> List[TorrentioStream]:
        """Resolve streams for a TV episode by IMDb ID."""
        url = self._api_url("series", f"{imdb_id}:{season}:{episode}")
        cine_cli_logger.debug(f"[torrentio] Querying: {url[:120]}...")
        return self._query(url, timeout)

    def _query(self, url: str, timeout: int) -> List[TorrentioStream]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "cine-cli/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read())
            streams = [TorrentioStream(s) for s in data.get("streams", [])]
            cine_cli_logger.debug(f"[torrentio] Found {len(streams)} streams")
            return streams
        except Exception as e:
            cine_cli_logger.error(f"[torrentio] Query failed: {e}")
            return []

    def pick_best_stream(self, streams: List[TorrentioStream], prefer_quality: str = "1080p") -> Optional[TorrentioStream]:
        """Pick the best stream from the list.

        Priority:
        1. Direct URL (debrid) at preferred quality
        2. Direct URL (debrid) at any quality
        3. Torrent at preferred quality
        4. Torrent at any quality
        """
        if not streams:
            return None

        # Group by type
        direct = [s for s in streams if s.has_direct_url]
        torrents = [s for s in streams if s.has_torrent]

        # Try preferred quality first
        for pool in [direct, torrents]:
            for s in pool:
                if s.quality == prefer_quality:
                    return s

        # Fall back to any
        for pool in [direct, torrents]:
            if pool:
                return pool[0]

        return None
