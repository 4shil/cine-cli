"""Multi-provider stream resolver using EncDecEndpoints API.

For browser playback: construct website URLs directly.
For MPV/API playback: use EncDec encryption/decryption.
"""
from __future__ import annotations
from typing import Optional, Dict
import json
import urllib.request
import urllib.parse

from ..logger import cine_cli_logger


# Provider configurations
# For browser playback, we construct the website URL directly.
# For API playback, we use EncDec encryption.
PROVIDERS = {
    "vidlink": {
        "name": "VidLink",
        "browser_url_movie": "https://vidlink.pro/movie/{tmdb_id}",
        "browser_url_tv": "https://vidlink.pro/tv/{tmdb_id}/{season}/{episode}",
        "priority": 1,
    },
    "videasy": {
        "name": "Videasy",
        "browser_url_movie": "https://www.vidking.net/embed/movie/{tmdb_id}",
        "browser_url_tv": "https://www.vidking.net/embed/tv/{tmdb_id}/{season}/{episode}",
        "api_base": "https://api.videasy.to",
        "dec_endpoint": "https://enc-dec.app/api/dec-videasy",
        "priority": 2,
    },
    "vidsync": {
        "name": "VidSync",
        "browser_url_movie": "https://vidsync.xyz/embed/{tmdb_id}",
        "browser_url_tv": "https://vidsync.xyz/embed/{tmdb_id}/{season}/{episode}",
        "priority": 3,
    },
    "cinesrc": {
        "name": "CineSrc",
        "browser_url_movie": "https://cinesrc.st/embed/{tmdb_id}",
        "browser_url_tv": "https://cinesrc.st/embed/{tmdb_id}/{season}/{episode}",
        "priority": 4,
    },
    "hexa": {
        "name": "Hexa",
        "browser_url_movie": "https://hexa.su/movie/{tmdb_id}",
        "browser_url_tv": "https://hexa.su/tv/{tmdb_id}/{season}/{episode}",
        "priority": 5,
    },
    "yflix": {
        "name": "yFlix",
        "browser_url_movie": "https://yflix.to/movie/{tmdb_id}",
        "browser_url_tv": "https://yflix.to/tv/{tmdb_id}/{season}/{episode}",
        "priority": 6,
    },
    "lordflix": {
        "name": "LordFlix",
        "browser_url_movie": "https://lordflix.org/movie/{tmdb_id}",
        "browser_url_tv": "https://lordflix.org/tv/{tmdb_id}/{season}/{episode}",
        "priority": 7,
    },
}


class MultiProviderResolver:
    """Resolves streams from multiple providers."""

    def __init__(self):
        self.ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"

    def get_browser_url(self, provider: str, tmdb_id: str,
                         media_type: str = "movie",
                         season: str = "1", episode: str = "1") -> Optional[str]:
        """Get browser-playable URL for a provider."""
        p = PROVIDERS.get(provider)
        if not p:
            return None

        if media_type == "tv":
            tmpl = p.get("browser_url_tv", "")
        else:
            tmpl = p.get("browser_url_movie", "")

        if not tmpl:
            return None

        return tmpl.format(tmdb_id=tmdb_id, season=season, episode=episode)

    def get_all_browser_urls(self, tmdb_id: str, media_type: str = "movie",
                              season: str = "1", episode: str = "1") -> Dict[str, str]:
        """Get browser URLs for all providers."""
        results = {}
        for pid, p in sorted(PROVIDERS.items(), key=lambda x: x[1]["priority"]):
            url = self.get_browser_url(pid, tmdb_id, media_type, season, episode)
            if url:
                results[pid] = url
        return results

    def resolve_videasy_direct(self, tmdb_id: str, title: str = "",
                                media_type: str = "movie",
                                season: str = "1", episode: str = "1") -> Optional[str]:
        """Resolve Videasy direct .m3u8 URL (for MPV playback)."""
        params = {"title": title, "mediaType": media_type, "tmdbId": tmdb_id}
        if media_type == "tv":
            params["seasonId"] = season
            params["episodeId"] = episode

        cipher_url = f"https://api.videasy.to/mb-flix/sources-with-title?{urllib.parse.urlencode(params)}"
        try:
            req = urllib.request.Request(cipher_url, headers={
                "User-Agent": self.ua,
                "Referer": "https://www.vidking.net/",
                "Origin": "https://www.vidking.net/",
            })
            with urllib.request.urlopen(req, timeout=15) as r:
                cipher = r.read().decode().strip()
        except Exception as e:
            cine_cli_logger.debug(f"[videasy] cipher error: {e}")
            return None

        try:
            body = json.dumps({"result": cipher}).encode()
            req = urllib.request.Request(
                "https://enc-dec.app/api/dec-videasy",
                data=body,
                headers={"User-Agent": self.ua, "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                dec_result = json.loads(r.read().decode())
        except Exception as e:
            cine_cli_logger.debug(f"[videasy] decrypt error: {e}")
            return None

        if dec_result and dec_result.get("ok"):
            sources = dec_result.get("result", {}).get("sources", [])
            if sources:
                return sources[0].get("url")
        return None
