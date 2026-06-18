from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional, Callable

    from ..media import Metadata
    from ..scraper import Scraper
    from ..utils.platform import SUPPORTED_PLATFORMS

import re
from devgoldyutils import Colours

from .ui import prompt
from .auto_select import auto_select_choice

from ..cache import Cache
from ..logger import cine_cli_logger
from ..errors import InternalPluginError

def cache_image_for_preview(cache: Cache) -> Callable[[Metadata], Metadata]:
    ansi_remover = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])') # Remove colours

    def before_display_callable(metadata: Metadata) -> Metadata:
        cache.set_cache(ansi_remover.sub("", metadata.display_name), metadata.image_url)

        return metadata

    return before_display_callable

def search(
    query: str,
    auto_select: Optional[int],
    scraper: Scraper,
    platform: SUPPORTED_PLATFORMS,
    fzf_enabled: bool,
    preview: bool,
    limit: Optional[int]
) -> Optional[Metadata]:
    choice = None

    cache = Cache(platform, section = "image_urls")

    cine_cli_logger.info(f"Searching for '{Colours.ORANGE.apply(query)}'...")

    try:
        search_results = scraper.search(query, limit)

        if auto_select is not None:
            choice = auto_select_choice((choice for choice in search_results), auto_select)
        else:
            choice = prompt(
                "Choose Result", 
                choices = (choice for choice in search_results), 
                display = lambda x: x.display_name, 
                fzf_enabled = fzf_enabled,
                before_display = cache_image_for_preview(cache),
                preview = "cine-cli-dev preview image -- {}" if preview else None
            )

    except Exception as e:
        raise InternalPluginError(e)

    cache.clear_all_cache()

    return choice