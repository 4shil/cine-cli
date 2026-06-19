"""Videasy resolver — decrypts Videasy.net streams and returns direct .m3u8 URLs.

Based on: https://github.com/walterwhite-69/Videasy.net-Decryptor

Flow:
1. Call Videasy API to get cipher for a TMDB ID
2. Decrypt using the WASM module via Node.js subprocess
3. Parse response to get .m3u8 stream URLs
4. Return direct stream URL for MPV/VLC

This replaces the old vidsrc.to embed approach — no more Turnstile blocking.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..media import Media

import json
import subprocess
import os
import re
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..logger import cine_cli_logger

__all__ = ("VideasyResolver",)

API_BASE = "https://api.videasy.to"
ORIGIN = "https://www.vidking.net"
REFERER = "https://www.vidking.net/"

PROVIDERS = [
    {"name": "Oxygen", "endpoint": "mb-flix", "active": True},
    {"name": "Hydrogen", "endpoint": "cdn", "active": True},
    {"name": "Lithium", "endpoint": "downloader2", "active": True},
    {"name": "Helium", "endpoint": "1movies", "active": False},
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/134.0.0.0 Safari/537.36"
    ),
    "Referer": REFERER,
    "Origin": ORIGIN,
}

DECRYPTOR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "videasy_decryptor")

def _get_decryptor_dir() -> str:
    """Find the decryptor directory, checking multiple locations."""
    # First: bundled in package (pipx install)
    bundled = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "videasy_decryptor")
    if os.path.exists(os.path.join(bundled, "decrypt.js")):
        return bundled
    # Second: repo root (development, not installed via pipx)
    repo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "videasy_decryptor")
    if os.path.exists(os.path.join(repo, "decrypt.js")):
        return repo
    return bundled


class VideasyResolver:
    """Resolves Videasy.net streams by decrypting their API response."""

    def __init__(self, decryptor_dir: Optional[str] = None):
        self.decryptor_dir = decryptor_dir or _get_decryptor_dir()
        self._node_available: Optional[bool] = None

    def _check_node(self) -> bool:
        if self._node_available is not None:
            return self._node_available
        try:
            result = subprocess.run(
                ["node", "--version"], capture_output=True, text=True, timeout=5
            )
            self._node_available = result.returncode == 0
            if self._node_available:
                cine_cli_logger.debug(f"[videasy] Node.js {result.stdout.strip()}")
            else:
                cine_cli_logger.warning("[videasy] Node.js not available")
        except FileNotFoundError:
            self._node_available = False
            cine_cli_logger.warning("[videasy] Node.js not installed")
        return self._node_available

    def _fetch_cipher(self, provider_endpoint: str, params: dict) -> Optional[str]:
        """Fetch cipher from Videasy API with retries."""
        url = f"{API_BASE}/{provider_endpoint}/sources-with-title?{urlencode(params)}"
        req = Request(url, headers=HEADERS)
        for attempt in range(3):
            try:
                with urlopen(req, timeout=20) as r:
                    return r.read().decode("utf-8", errors="replace").strip()
            except Exception as e:
                cine_cli_logger.debug(f"[videasy] API error (attempt {attempt+1}): {e}")
                if attempt < 2:
                    time.sleep(1)
        return None

    def _decrypt(self, cipher_hex: str, tmdb_id: str) -> Optional[dict]:
        if not self._check_node():
            return None

        decrypt_js = os.path.join(self.decryptor_dir, "decrypt.js")
        wasm_file = os.path.join(self.decryptor_dir, "module1.wasm")

        if not os.path.exists(decrypt_js) or not os.path.exists(wasm_file):
            cine_cli_logger.warning(f"[videasy] Decryptor files not found in {self.decryptor_dir}")
            return None

        try:
            result = subprocess.run(
                ["node", decrypt_js, cipher_hex, tmdb_id],
                capture_output=True, text=True, timeout=30, cwd=self.decryptor_dir,
            )
            if result.returncode != 0:
                cine_cli_logger.debug(f"[videasy] Decrypt error: {result.stderr.strip()}")
                return None
            out = json.loads(result.stdout)
            if not out.get("success"):
                cine_cli_logger.debug(f"[videasy] Decrypt failed: {out.get('error')}")
                return None
            return out.get("data")
        except subprocess.TimeoutExpired:
            cine_cli_logger.error("[videasy] Decrypt timed out")
            return None
        except (json.JSONDecodeError, Exception) as e:
            cine_cli_logger.debug(f"[videasy] Parse error: {e}")
            return None

    def resolve(self, tmdb_id: str, title: str, media_type: str = "movie",
                year: str = "", season: str = "1", episode: str = "1") -> Optional[dict]:
        """Resolve Videasy streams. Returns dict with sources list or None."""
        params = {
            "title": title, "mediaType": media_type, "year": year, "tmdbId": tmdb_id,
        }
        if media_type == "tv":
            params["seasonId"] = season
            params["episodeId"] = episode

        for provider in PROVIDERS:
            if not provider["active"]:
                continue

            cipher = self._fetch_cipher(provider["endpoint"], params)
            if not cipher:
                continue

            data = self._decrypt(cipher, tmdb_id)
            if not data:
                continue

            sources = self._parse_sources(data)
            if sources:
                return {
                    "provider": provider["name"],
                    "sources": sources,
                    "subtitles": self._parse_subtitles(data),
                }

        return None

    def _parse_sources(self, data) -> list:
        """Extract quality-labelled stream URLs from decrypted data."""
        sources = []

        def _extract(obj, depth=0):
            if depth > 5 or not isinstance(obj, (dict, list)):
                return
            if isinstance(obj, dict):
                url = obj.get("url", "")
                if url and (".m3u8" in url or ".mp4" in url):
                    quality = obj.get("quality") or obj.get("label") or "unknown"
                    sources.append({"quality": quality, "url": url})
                for v in obj.values():
                    _extract(v, depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    _extract(item, depth + 1)

        _extract(data)

        seen = set()
        return [s for s in sources if not (s["url"] in seen or seen.add(s["url"]))]

    def _parse_subtitles(self, data) -> list:
        """Extract subtitle URLs from decrypted data."""
        subs = []

        def _extract(obj, depth=0):
            if depth > 5 or not isinstance(obj, (dict, list)):
                return
            if isinstance(obj, dict):
                if "subtitles" in obj and isinstance(obj["subtitles"], list):
                    for sub in obj["subtitles"]:
                        if isinstance(sub, dict) and sub.get("file"):
                            subs.append(sub["file"])
                        elif isinstance(sub, str) and sub.startswith("http"):
                            subs.append(sub)
                for v in obj.values():
                    _extract(v, depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    _extract(item, depth + 1)

        _extract(data)
        return [s for s in subs if s.startswith("http")]

    def get_best_stream(self, tmdb_id: str, title: str, media_type: str = "movie",
                       year: str = "", season: str = "1", episode: str = "1",
                       prefer_quality: str = "1080p") -> Optional[str]:
        """Get the best stream URL for a TMDB ID."""
        result = self.resolve(tmdb_id, title, media_type, year, season, episode)
        if not result or not result.get("sources"):
            return None

        sources = result["sources"]

        for s in sources:
            if prefer_quality.lower() in s.get("quality", "").lower():
                return s["url"]

        if sources:
            return sources[0]["url"]
        return None
