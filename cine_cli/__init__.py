from .cli import *
from .media import *
from .cache import *
from .config import *
from .scraper import *
from .download import *

__version__ = "4.4.20"

# --------------------------------------------------------------------------- #
# Built-in TMDB + vidsrc scraper (no external plugin required)
# --------------------------------------------------------------------------- #
from .plugins import PluginHookData
from .scrapers.tmdb import TmdbScraper as _TmdbScraper
from .scrapers.torrentio import TorrentioScraper as _TorrentioScraper

plugin: PluginHookData = {
    "version": 1,
    "package_name": "cine-cli",
    "scrapers": {
        "DEFAULT": _TmdbScraper,
        "tmdb": _TmdbScraper,
        "torrentio": _TorrentioScraper,
    },
}
