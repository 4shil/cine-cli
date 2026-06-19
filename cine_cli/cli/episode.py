"""Episode selector — with fzf for interactive, auto-select for non-interactive."""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional
    from ..media import Metadata
    from ..scraper import Scraper

import sys

from devgoldyutils import Colours
from .ui import prompt
from ..media import MetadataType
from ..utils import EpisodeSelector
from ..cache import Cache
from ..utils import what_platform
from ..logger import cine_cli_logger


def handle_episode(episode_string: Optional[str], scraper: Scraper, choice: Metadata,
                   fzf_enabled: bool, continue_watching: bool) -> Optional[EpisodeSelector]:
    """Handle episode selection — fzf for interactive, auto-select for non-interactive."""
    if choice.type == MetadataType.SINGLE:
        return EpisodeSelector()

    if continue_watching:
        cache = Cache(what_platform())
        cached_episode = cache.get_cache(str(choice.id))
        if cached_episode is not None:
            return EpisodeSelector(**cached_episode)

    metadata_episodes = scraper.scrape_episodes(choice)

    # If only one possible episode (movie), auto-select
    if metadata_episodes.get(None) == 1:
        return EpisodeSelector()

    # If episode string provided via CLI arg (e.g., "5:1" = ep 5, season 1)
    if episode_string is not None:
        return __parse_episode_string(episode_string)

    # Check if we have a real terminal for fzf
    if not sys.stdin.isatty():
        # Non-interactive: auto-select season 1, episode 1
        cine_cli_logger.debug("Non-interactive terminal, auto-selecting S01E01")
        return EpisodeSelector(1, 1)

    # Interactive: use fzf/inquirer
    cine_cli_logger.info(f"Scraping episodes for '{Colours.CLAY.apply(choice.title)}'...")

    seasons = [s for s in metadata_episodes.keys() if s is not None]
    if not seasons:
        return EpisodeSelector()

    season = prompt(
        "Select Season",
        choices=seasons,
        display=lambda x: f"Season {x}",
        fzf_enabled=fzf_enabled,
    )

    if season is None:
        return None

    episode = prompt(
        "Select Episode",
        choices=[episode for episode in range(1, metadata_episodes[season] + 1)],
        display=lambda x: f"Episode {x}",
        fzf_enabled=fzf_enabled,
    )

    if episode is None:
        return None

    return EpisodeSelector(episode, season)


def __parse_episode_string(episode_string: str) -> Optional[EpisodeSelector]:
    """Parse episode string like '5:1' (episode 5, season 1) or '5' (episode 5, season 1)."""
    try:
        parts = episode_string.split(":")
        if len(parts) == 1 or parts[1] == "":
            return EpisodeSelector(int(parts[0]), 1)
        elif len(parts) == 2:
            return EpisodeSelector(int(parts[0]), int(parts[1]))
    except ValueError as e:
        cine_cli_logger.error(
            f"Incorrect episode format! Use '5:1' (episode:season) or '5' (episode)\\nError: {e}"
        )
    return None
