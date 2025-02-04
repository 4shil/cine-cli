from __future__ import annotations
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    ...

import typer
import shutil
import logging
from pathlib import Path

from .play import play
from .ui import welcome_msg
from .plugins import show_all_plugins
from .main_loop import query_and_grab_content
from .scraper import select_scraper, use_scraper, steal_scraper_args
from .configuration import open_config_file, set_cli_config

from ..config import Config
from ..download import Download
from ..logger import mov_cli_logger
from ..http_client import HTTPClient
from ..utils import hide_ip, get_temp_directory, what_platform, get_cache_directory

__all__ = ("mov_cli",)

uwu_app = typer.Typer(pretty_exceptions_enable = False) # NOTE: goldy has an uwu complex.

def mov_cli(
    query: Optional[List[str]] = typer.Argument(None, help = "A film, tv show or anime you would like to Query."), 
    debug: Optional[bool] = typer.Option(None, help = "Enable extra logging details. Useful for bug reporting."), 
    player: Optional[str] = typer.Option(None, "--player", "-p", help = "Player you would like to stream with. E.g. mpv, vlc"), 
    scraper: Optional[str] = typer.Option(None, "--scraper", "-s", help = "Scraper you would like to scrape with. E.g. test, youtube, jellyplex"), 
    fzf: Optional[bool] = typer.Option(None, help = "Toggle fzf on/off for all user selection prompts."), 
    preview: Optional[bool] = typer.Option(None, help = "Toggle fzf's preview (image preview, etc) on/off for fzf prompts."), 
    episode: Optional[str] = typer.Option(None, "--episode", "-ep", help = "Episode and season you wanna scrape. E.g. {episode}:{season} like -> 26:3"), 
    auto_select: Optional[int] = typer.Option(None, "--choice", "-c", help = "Auto select the search results. E.g. Setting it to 1 with query 'nyan cat' will pick " \
        "the first nyan cat video to show up in search results."
    ), 
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help = "Specify the maximum number of results"), 

    version: bool = typer.Option(False, "--version", help = "Display what version mov-cli is currently on."), 
    edit: bool = typer.Option(False, "--edit", "-e", help = "Opens the mov-cli config with your respective editor."), 
    download: bool = typer.Option(False, "--download", "-d", help = "Downloads the media instead of playing."), 
    continue_watching: bool = typer.Option(False, "--continue", "-co", help = "Continue where you left off in a series."), 
    list_plugins: bool = typer.Option(False, "--list-plugins", "-lp", help = "Prints all configured plugins and their scrapers."), 
    clear_cache: bool = typer.Option(False, "--no-cache", "--clear-cache", help = "Clears ALL cache stored by mov-cli, including the temp directory cache."),
    auto_try_next_scraper: bool = typer.Option(False, "--auto-try-next-scraper", "--atns", help = "Enables auto try next scraper."),
):
    config = Config()
    platform = what_platform()

    config = set_cli_config(
        config,
        debug = debug,
        player = player,
        scraper = (scraper, ["scrapers", "default"]),
        fzf = (fzf, ["ui", "fzf"]),
        preview = (preview, ["ui", "preview"]),
        limit = (limit, ["ui", "limit"]),
        auto_try_next_scraper = auto_try_next_scraper
    )

    if config.debug:
        mov_cli_logger.setLevel(logging.DEBUG)

    if clear_cache:
        mov_cli_logger.info("Clearing cache...")
        shutil.rmtree(get_temp_directory(platform))
        shutil.rmtree(get_cache_directory(platform))

        # return right away after clearing cache if only --clear-cache or --no-cache is passed.
        if query is None: 
            return None

    mov_cli_logger.debug(f"Config -> {config.data}")

    if edit:
        file_path = None if query is None else Path(query[0])
        open_config_file(config, file_path)
        return None

    plugins = config.plugins

    if list_plugins:
        show_all_plugins(plugins, platform)
        return None

    welcome_message = welcome_msg(
        plugins = plugins, 
        platform = platform, 
        check_for_updates = True if query is None and config.skip_update_checker is False else False, 
        display_tip = True if query is None else False, 
        display_version = version
    )

    print(welcome_message)

    if query is not None:
        scrape_options = steal_scraper_args(query) 
        # This allows passing arguments to scrapers like this: 
        # https://github.com/mov-cli/mov-cli-youtube/commit/b538d82745a743cd74a02530d6a3d476cd60b808#diff-4e5b064838aa74a5375265f4dfbd94024b655ee24a191290aacd3673abed921a

        query: str = " ".join(query)

        http_client = HTTPClient(
            headers = config.http_headers, 
            timeout = config.http_timeout, 
            hide_ip = config.hide_ip
        )

        selected_scraper = select_scraper(
            plugins = plugins, 
            scrapers = config.scrapers, 
            platform = platform, 
            fzf_enabled = config.fzf_enabled, 
            default_scraper = config.default_scraper
        )

        if selected_scraper is None:
            mov_cli_logger.error(
                "You must choose a scraper to scrape with! " \
                    "You can set a default scraper with the default key in config.toml."
            )
            return False

        selected_scraper[2].update(scrape_options)

        chosen_scraper = use_scraper(selected_scraper, config, http_client)

        content_or_bool = query_and_grab_content(
            query = query,
            auto_select = auto_select,
            episode = episode,
            continue_watching = continue_watching,
            scraper = chosen_scraper,
            selected_scraper = selected_scraper,
            platform = platform,
            config = config
        )

        if content_or_bool is False:
            raise typer.Exit(1)

        media, metadata, chosen_episode = content_or_bool

        if download:
            dl = Download(config)

            mov_cli_logger.debug(f"Downloading from this url -> '{hide_ip(media.url, config.hide_ip)}'")

            popen = dl.download(media)
            
            if popen:
                popen.wait()

        else:
            play(media, metadata, chosen_scraper, chosen_episode, config)

def app():
    uwu_app.command()(mov_cli)
    uwu_app()