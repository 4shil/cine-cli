"""Multi-provider stream resolver.

All providers use IMDb IDs.
Default: vidsrc.to (most reliable).
"""
from __future__ import annotations
from typing import Optional, Dict


# Provider configurations — all use IMDb IDs
PROVIDERS = {
    "vidsrc": {
        "name": "VidSrc.to",
        "url_movie": "https://vidsrc.to/embed/movie/{imdb_id}",
        "url_tv": "https://vidsrc.to/embed/tv/{imdb_id}/{season}/{episode}",
        "priority": 1,
    },
    "vidking": {
        "name": "VidKing",
        "url_movie": "https://www.vidking.net/embed/movie/{imdb_id}",
        "url_tv": "https://www.vidking.net/embed/tv/{imdb_id}/{season}/{episode}",
        "priority": 2,
    },
    "vidlink": {
        "name": "VidLink",
        "url_movie": "https://vidlink.pro/movie/{imdb_id}",
        "url_tv": "https://vidlink.pro/tv/{imdb_id}/{season}/{episode}",
        "priority": 3,
    },
    "vidsync": {
        "name": "VidSync",
        "url_movie": "https://vidsync.live/embed/movie/{imdb_id}",
        "url_tv": "https://vidsync.live/embed/tv/{imdb_id}/{season}/{episode}",
        "priority": 4,
    },
    "cinesrc": {
        "name": "CineSrc",
        "url_movie": "https://cinesrc.st/embed/movie/{imdb_id}",
        "url_tv": "https://cinesrc.st/embed/tv/{imdb_id}/{season}/{episode}",
        "priority": 5,
    },
    "lordflix": {
        "name": "LordFlix",
        "url_movie": "https://lordflix.org/movie/{imdb_id}",
        "url_tv": "https://lordflix.org/tv/{imdb_id}/{season}/{episode}",
        "priority": 6,
    },
}


def get_provider_url(provider: str, imdb_id: str, media_type: str = "movie",
                      season: str = "1", episode: str = "1") -> Optional[str]:
    """Get embed URL for a provider."""
    p = PROVIDERS.get(provider)
    if not p:
        return None
    if media_type == "tv":
        return p["url_tv"].format(imdb_id=imdb_id, season=season, episode=episode)
    return p["url_movie"].format(imdb_id=imdb_id)


def get_all_urls(imdb_id: str, media_type: str = "movie",
                 season: str = "1", episode: str = "1") -> Dict[str, str]:
    """Get embed URLs for all providers."""
    results = {}
    for pid, p in sorted(PROVIDERS.items(), key=lambda x: x[1]["priority"]):
        url = get_provider_url(pid, imdb_id, media_type, season, episode)
        if url:
            results[pid] = url
    return results
