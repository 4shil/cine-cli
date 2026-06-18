from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Tuple, List, Dict, Optional

    from pathlib import Path
    from ..cache import Cache

import httpx
from packaging import version
from datetime import timedelta
from devgoldyutils import LoggerAdapter, Colours

import cine_cli
from ..plugins import load_plugin
from ..logger import cine_cli_logger
from .platform import what_distro

__all__ = (
    "update_available", 
    "plugin_update_available",
    "update_command",
)

logger = LoggerAdapter(cine_cli_logger, prefix = Colours.GREEN.apply("version"))

def update_available(cache: Cache) -> bool:
    logger.debug("Checking if cine-cli needs updating...")

    update_fail_msg = "Failed to check for cine-cli update!"

    pypi_version: Optional[str] = cache.get_cache("pypi_version")

    if pypi_version is None:

        try:
            response = httpx.get("https://pypi.org/pypi/cine-cli/json")
        except httpx.HTTPError as e:
            logger.warning(update_fail_msg + f" Error: {e}")
            return False

        if response.status_code >= 400:
            logger.warning(update_fail_msg + f" Response: {response}")
            return False

        pypi_version: str = cache.set_cache(
            id = "pypi_version", 
            value = response.json()["info"]["version"], 
            seconds_until_expired = timedelta(hours = 1).total_seconds()
        )

    if version.parse(pypi_version) > version.parse(cine_cli.__version__):
        return True

    return False

def plugin_update_available(cache: Cache, plugins: Dict[str, str]) -> Tuple[bool, List[str]]:
    plugins_with_updates: List[str] = []

    logger.debug("Checking if plugins need updating...")

    for _, module_name in plugins.items():
        plugin = load_plugin(module_name)

        if plugin is None:
            continue

        plugin_version = plugin.version
        pypi_package_name = plugin.hook_data.get("package_name", None)

        if plugin_version is None:
            logger.debug(
                f"The plugin '{module_name}' doesn't expose '__version__' in" \
                    "it's root module ('__init__.py') so it the update checker will skip it."
            )
            continue

        if pypi_package_name is None:
            logger.debug(
                f"Skipped update check for '{module_name}' as the plugin " \
                    "doesn't contain 'package_name' in it's hook data."
            )
            continue

        pypi_version: Optional[str] = cache.get_cache(f"{pypi_package_name}_pypi_version")

        if pypi_version is None:

            try:
                response = httpx.get(f"https://pypi.org/pypi/{pypi_package_name}/json")
            except httpx.HTTPError as e:
                logger.warning(f"Failed to check for update of the plugin '{module_name}'! Error: {e}")
                continue

            if response.status_code >= 400:
                logger.warning(f"Failed to check for update of the plugin '{module_name}'! Response: {response}")
                continue

            pypi_version: str = cache.set_cache(
                id = f"{pypi_package_name}_pypi_version", 
                value = response.json()["info"]["version"], 
                seconds_until_expired = timedelta(hours = 1).total_seconds()
            )

        if version.parse(pypi_version) > version.parse(plugin_version):
            plugins_with_updates.append(pypi_package_name)

    if not plugins_with_updates == []:
        return True, plugins_with_updates

    return False, []

def update_command(cine_cli_path: Path, package: str | list = "cine-cli") -> str:
    path = str(cine_cli_path)

    if "pipx" in path:
        return "pipx upgrade cine-cli --include-injected"
    elif "/usr/bin" in path:
        if what_distro() == "arch":
            return "yay"
        else:
            if isinstance(package, list):
                return f"Use your package manager. Packages to update: {' '.join(package)}"
            else:
                return f"Use your package manager. Package to update: {package}"

    if isinstance(package, list):
        return f"pip install {' '.join(package)} -U"
    else:
        return f"pip install {package} -U"