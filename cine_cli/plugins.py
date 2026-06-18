"""
Module containing cine-cli plugin related stuff.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from types import ModuleType
    from typing import Optional, Dict, List, Tuple, Literal, Type

    from .utils.platform import SUPPORTED_PLATFORMS

import importlib
from dataclasses import dataclass
from devgoldyutils import LoggerAdapter

from .scraper import Scraper
from .logger import cine_cli_logger

__all__ = (
    "load_plugin", 
    "PluginHookData", 
    "Plugin"
)

logger = LoggerAdapter(cine_cli_logger, prefix = "Plugins")

class PluginHookData(TypedDict):
    version: Literal[1]
    """The version of the plugin hook to use. Version 1 is latest currently."""
    package_name: str
    """The name of the pypi package. This is required for the plugin update notifier to work."""
    scrapers: Dict[str, Type[Scraper]] | PluginHookScrapersT

PluginHookScrapersT = TypedDict(
    "PluginHookScrapersT",
    {
        "DEFAULT": Scraper,
        "LINUX.DEFAULT": Scraper,
        "ANDROID.DEFAULT": Scraper,
        "IOS.DEFAULT": Scraper,
        "WINDOWS.DEFAULT": Scraper,
        "DARWIN.DEFAULT": Scraper
    }
)

@dataclass
class Plugin:
    module: ModuleType
    hook_data: PluginHookData

    @property
    def scrapers(self) -> List[Tuple[str, Type[Scraper]]]:
        non_default_scrapers = []

        for scraper_namespace, scraper_class in self.hook_data["scrapers"].items():

            if scraper_namespace.endswith("DEFAULT"):
                continue

            non_default_scrapers.append((scraper_namespace, scraper_class))

        return non_default_scrapers

    @property
    def version(self) -> Optional[str]:
        return getattr(self.module, "__version__", None)

    def default_scraper(self, platform: SUPPORTED_PLATFORMS) -> Optional[Scraper]:

        for scraper_namespace, scraper_class in self.hook_data["scrapers"].items():

            if scraper_namespace == f"{platform}.DEFAULT" or scraper_namespace == "DEFAULT":
                return scraper_class

        return None

def load_plugin(module_name: str) -> Optional[Plugin]:
    try:
        plugin_module = importlib.import_module(module_name.replace("-", "_"))
    except ModuleNotFoundError as e:
        logger.error(f"Failed to import a plugin from the module '{module_name}'! Error --> {e}")
        return None

    plugin_data: PluginHookData = getattr(plugin_module, "plugin", None)

    if plugin_data is None:
        logger.warning(f"Failed to load the plugin '{module_name}'! It doesn't contain a plugin hook!")
        return None

    return Plugin(
        module = plugin_module, 
        hook_data = plugin_data
    )