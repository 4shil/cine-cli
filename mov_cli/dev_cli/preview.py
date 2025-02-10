from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional

    from pathlib import Path

import os
import httpx
import typer
import shutil

from subprocess import call

from ..cache import Cache
from ..utils import what_platform, get_temp_directory, slugify

__all__ = ()

preview_app = typer.Typer(
    name = "preview", 
    help = "Dev command used by stuff like fzf to display images from mov-cli in the terminal."
)

@preview_app.command(help = "Preview image from mov-cli cache to terminal.")
def image(id: str):
    platform = what_platform()

    if not platform == "Linux" and not platform == "FreeBSD" and not platform == "Android":
        print("Image preview only works on Linux, Android an FreeBSD atm.")
        return False

    cache = Cache(
        platform = platform, 
        section = "image_urls"
    )

    image_url = cache.get_cache(id)

    if image_url is None:
        print("No Image :(")
        return False

    fzf_preview_lines = os.environ["FZF_PREVIEW_LINES"] # height
    fzf_preview_columns = os.environ["FZF_PREVIEW_COLUMNS"] # width

    os.system("clear")

    if "KITTY_WINDOW_ID" in os.environ:
        call([
            "kitty", 
            "icat", 
            "--clear", 
            "--transfer-mode=memory", 
            "--unicode-placeholder", 
            "--stdin=no", 
            f"--place={fzf_preview_columns}x{fzf_preview_lines}@0x0", 
            "--scale-up", 
            image_url
        ])

    elif shutil.which("chafa") is not None:
        file = image_url_to_file(image_url, id, platform)

        if file is None:
            print("Image not found! (◡︵◡)")
            raise typer.Exit(1)

        call([
            "chafa", 
            file.resolve(), 
            f"--size={fzf_preview_columns}x{fzf_preview_lines}", 
            "--clear"
        ])

    else:
        print("'chafa' was not found! :( Please install it: https://github.com/hpjansson/chafa")
        return False


def image_url_to_file(image_url: str, id: str, platform: str) -> Optional[Path]:
    temp = get_temp_directory(platform)
    file = temp.joinpath(slugify(id))

    if file.exists():
        return file

    request = httpx.get(image_url)

    if request.is_error:
        return None

    with file.open("wb") as f:
        f.write(request.content)

    return file