from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Tuple, List, Dict

    from ..plugins import Plugin
    from ..utils.platform import SUPPORTED_PLATFORMS

    PluginsDataT = List[Tuple[str, str, Plugin]]

from devgoldyutils import Colours

from ..plugins import load_plugin

def get_plugins_data(plugins: Dict[str, str]) -> PluginsDataT:
    plugins_data: PluginsDataT = []

    for plugin_namespace, plugin_module_name in plugins.items():
        plugin = load_plugin(plugin_module_name)

        if plugin is None:
            continue

        plugins_data.append(
            (plugin_namespace, plugin_module_name, plugin)
        )

    return plugins_data

def show_all_plugins(plugins: Dict[str, str], platform: SUPPORTED_PLATFORMS) -> None:

    for plugin_namespace, plugin_module_name, plugin in get_plugins_data(plugins):

        if plugin is not None:
            plugin_version = getattr(plugin.module, "__version__", "N/A")

            print(f"- {Colours.PURPLE.apply(plugin_module_name)} ({plugin_namespace}) [{Colours.BLUE.apply(plugin_version)}]")

            plugin_default_scraper = plugin.default_scraper(platform)

            for scraper_name, scraper_class in plugin.scrapers:
                print(f"  - {Colours.PINK_GREY.apply(scraper_name) + (' ❤' if scraper_class == plugin_default_scraper and len(plugin.scrapers) > 1 else '')}")