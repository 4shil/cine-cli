from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Optional, Any, List, Tuple
    from ..config import Config

import os
from subprocess import check_call, CalledProcessError

from .. import utils
from ..logger import cine_cli_logger

def set_cli_config(config: Config, **kwargs: Any | Tuple[Any, List[str]]) -> Config:

    for key, value in kwargs.items():

        if isinstance(value, tuple):
            dict_keys = value[1]
            actual_value = value[0]
        else:
            dict_keys = None
            actual_value = value

        if actual_value is not None:

            if isinstance(value, tuple):
                config_data = config.data

                for index, dict_key in enumerate(dict_keys):
                    dict_key = dict_key.format(K = key)

                    if index + 1 == len(dict_keys):
                        config_data[dict_key] = actual_value
                        break

                    config_data = config_data.get(dict_key, {})

            else:
                config.data[key] = actual_value

    return config

def open_config_file(config: Config, file_path: Optional[Path] = None):
    """Opens the config file in the respectable editor for that platform."""
    editor = config.editor
    platform = utils.what_platform()

    if editor is None: 
        env_editor = os.environ.get("EDITOR")        

        if env_editor is not None:
            editor = env_editor
        else:
            if platform == "Windows":
                editor = "notepad"
            elif platform == "Darwin":
                editor = "nano" # NOTE: https://support.apple.com/guide/terminal/use-command-line-text-editors-apdb02f1133-25af-4c65-8976-159609f99817/mac
            elif platform == "iOS":
                editor = "vi"
            elif platform == "Linux" or platform == "Android":
                editor = "nano"

    cine_cli_logger.debug("Opening config file...")

    appdata_path = utils.get_appdata_directory(platform)

    try:
        check_call([editor, config.config_path if file_path is None else appdata_path.joinpath(file_path)])
    except (FileNotFoundError, CalledProcessError) as e:
        cine_cli_logger.error(
            f"Failed to open config file with the editor '{editor}'! Error: {e}" \
                f"\nYou can manually edit it over here: '{config.config_path}'."
        )