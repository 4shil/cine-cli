from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Type, Optional, Tuple, List, Dict

    from .plugins import PluginsDataT

    from ..plugins import Plugin
    from ..media import Metadata, Media
    from ..http_client import HTTPClient
    from ..config import Config, ScrapersConfigT
    from ..utils.platform import SUPPORTED_PLATFORMS
    from ..utils.episode_selector import EpisodeSelector
    from ..scraper import Scraper, ScraperOptionsT

    SelectedScraperT = Tuple[str, Type[Scraper], ScraperOptionsT]

from thefuzz import fuzz
from devgoldyutils import Colours

from .ui import prompt
from .plugins import get_plugins_data

from ..utils import what_platform
from ..logger import cine_cli_logger
from ..errors import InternalPluginError

def scrape(choice: Metadata, episode: EpisodeSelector, scraper: Scraper) -> Optional[Media]:
    cine_cli_logger.info(f"Scraping '{Colours.CLAY.apply(choice.title)}'...")

    try:
        media = scraper.scrape(choice, episode)
    except Exception as e:
        raise InternalPluginError(e)

    return media

def use_scraper(
    selected_scraper: SelectedScraperT,
    config: Config,
    http_client: HTTPClient
) -> Scraper:
    scraper_name, scraper_class, scraper_options = selected_scraper

    cine_cli_logger.info(f"Using '{Colours.BLUE.apply(scraper_name)}' scraper...")

    try:
        chosen_scraper = scraper_class(config, http_client, scraper_options)
    except Exception as e:
        raise InternalPluginError(e)

    return chosen_scraper

def use_next_scraper(
    current_scraper: Scraper,
    current_scraper_namespace: str,
    plugins: Dict[str, str]
) -> Optional[Tuple[Scraper, SelectedScraperT]]:
    current_scraper_namespaces = current_scraper_namespace.split(".")

    current_plugin_namespace = current_scraper_namespaces[0]
    current_scraper_namespace = ".".join(current_scraper_namespaces[1:])

    current_plugin: Plugin # It should get bound. Like it's impossible for it to not. 💀

    for plugin_namespace, _, plugin in get_plugins_data(plugins):

        if plugin_namespace == current_plugin_namespace:
            current_plugin = plugin
            break

    # Replace the current scraper namespace with actual scraper 
    # namespace if the namespace we got was the default scraper namespace.
    if current_scraper_namespace.endswith("DEFAULT"):

        for plugin_scraper_namespace, plugin_scraper in current_plugin.scrapers:

            if plugin_scraper == current_plugin.hook_data["scrapers"][current_scraper_namespace]:
                current_scraper_namespace = plugin_scraper_namespace
                break

    next_plugin_scraper_class = None
    next_plugin_scraper_namespace = None

    # We get the next scraper by finding the current chosen scraper and returning 
    # the one after that. If none exist then that is the last scraper so we just continue.
    current_chosen_scraper_found = False

    plugin_scrapers_amount = len(current_plugin.scrapers)

    for index, (plugin_scraper_namespace, plugin_scraper_class) in enumerate(current_plugin.scrapers):

        if plugin_scraper_namespace == current_scraper_namespace:

            # If we are on the last scraper the next scraper should 
            # be None to indicate that there's no more scrapers after.
            if index + 1 >= plugin_scrapers_amount:
                next_plugin_scraper_class = None
                break

            current_chosen_scraper_found = True
            continue # iterate to the next scraper

        if current_chosen_scraper_found:
            next_plugin_scraper_class = plugin_scraper_class
            next_plugin_scraper_namespace = f"{plugin_namespace}.{plugin_scraper_namespace}"
            break

    if next_plugin_scraper_class is None:
        return None

    next_selected_Scraper = (next_plugin_scraper_namespace, next_plugin_scraper_class, current_scraper.options)

    next_plugin_scraper = use_scraper(
        selected_scraper = next_selected_Scraper,
        config = current_scraper.config,
        http_client = current_scraper.http_client
    )

    return next_plugin_scraper, next_selected_Scraper

def select_scraper(
    plugins: Dict[str, str],
    scrapers: ScrapersConfigT,
    platform: SUPPORTED_PLATFORMS,
    fzf_enabled: bool,
    default_scraper: Optional[str] = None
) -> Optional[SelectedScraperT]:
    plugins_data = get_plugins_data(plugins)

    if default_scraper is not None:
        scraper_name, scraper_or_available_scrapers, scraper_options = get_scraper(default_scraper, plugins_data, scrapers)

        if scraper_name is None:
            cine_cli_logger.error(
                f"Could not find a scraper by the id '{default_scraper}'! Are you sure the plugin is installed and in your config? " \
                    "Read the wiki for more on that: 'https://github.com/cine-cli/cine-cli/wiki#plugins'."
            )

            scrapers_beautifully_formatted = Colours.ORANGE.apply(f"{f'{Colours.RESET} | {Colours.ORANGE}'.join(scraper_or_available_scrapers)}")

            print(f"\nAvailable Scrapers -> {scrapers_beautifully_formatted}")

            did_you_mean_these = [(x, fuzz.ratio(default_scraper, x)) for x in scraper_or_available_scrapers]
            did_you_mean_these.sort(key = lambda x: x[1], reverse = True)

            if len(did_you_mean_these) > 0:
                print(Colours.PURPLE.apply(f"\n* Did you mean: {Colours.GREEN}{did_you_mean_these[0][0]}\n"))

            return None

        return scraper_name, scraper_or_available_scrapers, scraper_options

    chosen_plugin = prompt(
        "Select a plugin", 
        choices = plugins_data, 
        display = lambda x: f"{Colours.ORANGE.apply(x[0])} [{Colours.PINK_GREY.apply(x[1])}]", 
        fzf_enabled = fzf_enabled
    )

    if chosen_plugin is not None:
        plugin_namespace, _, plugin = chosen_plugin

        plugin_default_scraper = plugin.default_scraper(platform)

        chosen_scraper = prompt(
            "Select a scraper", 
            choices = [scraper for scraper in plugin.scrapers], 
            display = (
                lambda x: Colours.BLUE.apply(x[0].lower()) + Colours.CLAY.apply(" [DEFAULT]") if x[1] == plugin_default_scraper else Colours.BLUE.apply(x[0].lower())
            ), 
            fzf_enabled = fzf_enabled
        )

        if chosen_scraper is None:
            return None

        scraper_name, scraper = chosen_scraper

        return f"{plugin_namespace}.{scraper_name}".lower(), scraper, {}

    return None

def steal_scraper_args(query: List[str]) -> ScraperOptionsT:
    args_to_kidnap: List[str] = []
    arg_values_to_kidnap: List[str] = []

    scraper_options_args: List[Tuple[str, str | bool]] = []

    for index, arg in enumerate(query):

        if arg.startswith("--"):
            arg_value = True

            try:
                arg_value_maybe = query[index + 1]

                if not arg_value_maybe.startswith("--"):
                    arg_value = arg_value_maybe

                    arg_values_to_kidnap.append(arg_value)

            except IndexError as e:
                cine_cli_logger.debug(
                    f"No scraper option argument value was found after '{arg}' so we'll assume this argument is a flag. \nError: {e}"
                )

            args_to_kidnap.append(arg)
            scraper_options_args.append((arg.replace("--", "").replace("-", "_"), arg_value))

    # KIDNAP THEM ARGS!!!!!
    for arg_or_arg_value in args_to_kidnap + arg_values_to_kidnap:
        query.remove(arg_or_arg_value)

    cine_cli_logger.debug(f"Scraper args picked up on --> {scraper_options_args}")

    return dict(scraper_options_args)

def get_scraper(scraper_id: str, plugins_data: PluginsDataT, user_defined_scrapers: ScrapersConfigT) -> Tuple[str, Type[Scraper] | Tuple[None, List[str]], ScraperOptionsT]:
    scraper_options = {}
    available_scrapers = []

    # scraper namespace override.
    for scraper_namespace, scraper_data in user_defined_scrapers.items():

        if scraper_id.lower() == scraper_namespace.lower():
            cine_cli_logger.debug(f"Using the scraper overridden namespace '{scraper_namespace}'...")
            scraper_id = scraper_data["namespace"]
            scraper_options = scraper_data["options"]

    platform = what_platform().upper()

    for plugin_namespace, _, plugin in plugins_data:
        plugin_scrapers = plugin.hook_data["scrapers"]

        if scraper_id.lower() == plugin_namespace.lower() and f"{platform}.DEFAULT" in plugin_scrapers:
            return f"{plugin_namespace}.{platform}.DEFAULT", plugin_scrapers[f"{platform}.DEFAULT"], scraper_options

        elif scraper_id.lower() == plugin_namespace.lower() and "DEFAULT" in plugin_scrapers:
            return f"{plugin_namespace}.DEFAULT", plugin_scrapers["DEFAULT"], scraper_options

        for scraper_name, scraper in plugin_scrapers.items():
            id = f"{plugin_namespace}.{scraper_name}".lower()

            available_scrapers.append(id)

            if scraper_id.lower() == id:
                return id, scraper, scraper_options

    return None, available_scrapers, scraper_options