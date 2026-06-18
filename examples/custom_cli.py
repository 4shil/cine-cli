# This is a simple example on how to use cine-cli as a library.
# This script requires the cine-cli-youtube plugin to be installed!
#
# pip install cine-cli-youtube -U

import time

from cine_cli import prompt
from cine_cli.config import Config
from cine_cli.players import PLAYER_TABLE
from cine_cli.http_client import HTTPClient
from cine_cli.utils import EpisodeSelector, what_platform

from cine_cli_youtube.yt_dlp import YTDlpScraper

WELCOME_MESSAGE = "Hello and welcome to my custom cine-cli script!\n\n" \
    "What would you like to watch from YouTube?\n"

if __name__ == "__main__":
    print(WELCOME_MESSAGE)

    time.sleep(1)

    query = input("Enter your query -> ")

    config = Config()
    http_client = HTTPClient()
    platform = what_platform()

    scraper = YTDlpScraper(
        config = config,
        http_client = http_client
    )

    print("I'm searching... ⚆ _ ⚆")
    search_results = scraper.search(query)

    choice = prompt(
        text = "Which youtube video would you like to watch?",
        choices = search_results,
        display = lambda x: x.title,
        fzf_enabled = config.fzf_enabled
    )

    if choice is None:
        print("No video was selected. :(")

    print("Scrapping that... ◉_◉")
    media = scraper.scrape(choice, EpisodeSelector())

    player_class = PLAYER_TABLE[config.player]

    player = player_class(platform = platform)

    popen = player.play(media)

    print("I'm playing :)")

    popen.wait()