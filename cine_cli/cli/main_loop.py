from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Literal, Tuple, Optional

    from .scraper import SelectedScraperT

    from ..media import Media
    from ..config import Config
    from ..scraper import Scraper
    from ..media.metadata import Metadata
    from ..utils.platform import SUPPORTED_PLATFORMS
    from ..utils.episode_selector import EpisodeSelector

from devgoldyutils import Colours, LoggerAdapter

from .search import search
from .episode import handle_episode
from .scraper import use_next_scraper, scrape

from ..media import MetadataType
from ..logger import cine_cli_logger
from ..errors import InternalPluginError

__all__ = ()

atns_logger = LoggerAdapter(cine_cli_logger, prefix = Colours.PURPLE.apply("ATNS")) # Auto try next scraper

def query_and_grab_content(
    query: str,
    auto_select: Optional[int],
    episode: Optional[str],
    continue_watching: bool,
    scraper: Scraper,
    selected_scraper: SelectedScraperT,
    platform: SUPPORTED_PLATFORMS,
    config: Config,
) -> Literal[False] | Tuple[Media, Metadata, EpisodeSelector]:
    reason_for_auto_try = f"🫥 Query not found with '{Colours.PURPLE.apply(selected_scraper[0])}'!"

    try:
        choice = search(
            query = query,
            auto_select = auto_select,
            scraper = scraper,
            platform = platform,
            fzf_enabled = config.fzf_enabled,
            preview = config.preview,
            limit = config.limit
        )

    except InternalPluginError as e:

        if config.debug:
            cine_cli_logger.critical(e.message)

        if not config.auto_try_next_scraper:
            raise e

        choice = None
        reason_for_auto_try = f"❌ Error occurred while searching with '{Colours.PURPLE.apply(selected_scraper[0])}'!"

    if choice is None:

        if config.auto_try_next_scraper:
            return try_again_with_next_scraper(
                reason_for_auto_try = reason_for_auto_try,
                query = query,
                auto_select = auto_select,
                episode = episode,
                continue_watching = continue_watching,
                scraper = scraper,
                selected_scraper = selected_scraper,
                platform = platform,
                config = config
            )

        cine_cli_logger.error("There was no results or you didn't select anything.")
        return False

    reason_for_auto_try = f"🫥 Episode not selected with '{Colours.PURPLE.apply(selected_scraper[0])}'!"

    chosen_episode = handle_episode(
        episode_string = episode, 
        scraper = scraper, 
        choice = choice, 
        fzf_enabled = config.fzf_enabled,
        continue_watching = continue_watching
    )

    if chosen_episode is None:
        cine_cli_logger.error("You didn't select an episode!")
        return False

    try:
        media = scrape(choice, chosen_episode, scraper)

    except InternalPluginError as e:

        if config.debug:
            cine_cli_logger.critical(e.message)

        if not config.auto_try_next_scraper:
            raise e

        media = None
        reason_for_auto_try = f"❌ Error occurred while scraping with '{Colours.PURPLE.apply(selected_scraper[0])}'!"

    if media is None:

        if config.auto_try_next_scraper:
            return try_again_with_next_scraper(
                reason_for_auto_try = reason_for_auto_try,
                query = query,
                auto_select = auto_select,
                episode = episode,
                continue_watching = continue_watching,
                scraper = scraper,
                selected_scraper = selected_scraper,
                platform = platform,
                config = config
            )

        episode_details_string = f" ep {chosen_episode.episode} season {chosen_episode.season} of" if choice.type == MetadataType.MULTI else ""

        cine_cli_logger.error(
            f"The scraper '{scraper.__class__.__name__}' couldn't find{episode_details_string} '{choice.title}'! " \
                "Don't report this to cine-cli, report this to the plugin itself."
        )
        return False

    return media, choice, chosen_episode

def try_again_with_next_scraper(
    reason_for_auto_try: str,
    query: str,
    auto_select: Optional[int],
    episode: Optional[str],
    continue_watching: bool,
    scraper: Scraper,
    selected_scraper: SelectedScraperT,
    platform: SUPPORTED_PLATFORMS,
    config: Config
) -> Tuple[Media, Metadata, EpisodeSelector] | Literal[False]:
    atns_logger.info(
       f"{reason_for_auto_try} Trying the next scraper..."
    )

    next_scraper_or_none = use_next_scraper(
        current_scraper = scraper,
        current_scraper_namespace = selected_scraper[0],
        plugins = config.plugins
    )

    if next_scraper_or_none is None:
        return False

    next_chosen_scraper, next_selected_scraper = next_scraper_or_none

    return query_and_grab_content(
        query = query,
        auto_select = auto_select,
        episode = episode,
        continue_watching = continue_watching,
        scraper = next_chosen_scraper,
        selected_scraper = next_selected_scraper,
        platform = platform,
        config = config
    )