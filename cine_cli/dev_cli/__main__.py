from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import List

import json
import typer
from pathlib import Path
from devgoldyutils import Colours

from .preview import preview_app

__all__ = ()

app = typer.Typer(
    pretty_exceptions_enable = False, 
    help = "Developer only commands to be executed from scripts and assist with testing and development of cine-cli plugins and more."
)

test_app = typer.Typer(name = "test", help = "Run tests on cine-cli plugins and other varies cine-cli functionalities.")

test_misc_app = typer.Typer(name = "misc", help = "")
test_app.add_typer(test_misc_app)

app.add_typer(test_app)
app.add_typer(preview_app)

@test_misc_app.command(help = "Test how a tip that get's displayed under the cine-cli welcome message is displayed.")
def tip(tip_index: int):
    cine_cli_path = Path(__file__).parent.parent
    random_tips_path = cine_cli_path.joinpath("cli", "random_tips.json")

    random_tips_json: List[str] = json.load(random_tips_path.open("r"))

    print(f"\n- {Colours.ORANGE}TIP: {Colours.RESET}{random_tips_json[tip_index]}\n")