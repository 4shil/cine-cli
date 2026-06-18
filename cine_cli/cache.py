from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Dict, Any, Optional, TypeVar, TypedDict

    from io import TextIOWrapper

    from .utils.platform import SUPPORTED_PLATFORMS

    T = TypeVar("T", Any)

    class BasicCacheData(TypedDict):
        value: Any
        expiring_date: Optional[float]

import json
from datetime import datetime
from devgoldyutils import LoggerAdapter, Colours

from .logger import cine_cli_logger
from .utils import get_cache_directory

__all__ = (
    "Cache",
)

logger = LoggerAdapter(
    cine_cli_logger, prefix = Colours.BLUE.apply("Cache")
)

class Cache():
    """An API for caching text based data on cine-cli cross platform respectively."""
    def __init__(self, platform: SUPPORTED_PLATFORMS, section: Optional[str] = None) -> None:
        self.section = section

        cache_dir = get_cache_directory(platform)

        self._basic_cache_file_path = cache_dir.joinpath("osaka_cache") # ◔_◔ https://static.wikia.nocookie.net/parody/images/f/fd/Osaka.png/revision/latest

        super().__init__()

    def get_cache(self, id: str) -> Optional[Any]:
        logger.debug(
            f"Getting '{id}' cache" + ("..." if self.section is None else f" from '{self.section}' section...")
        )

        data: Dict[str, BasicCacheData | Dict[str, BasicCacheData]] = {}

        with self.__get_cache_file("r") as file:
            data = json.load(file)

        if self.section is not None:
            data = data.get(self.section, {})

        basic_cache = data.get(id)

        if basic_cache is None:
            return None

        value = basic_cache["value"]
        expiring_data = basic_cache["expiring_date"]

        if expiring_data is not None and datetime.now().timestamp() > expiring_data:
            self.clear_cache(id)
            return None

        return value

    def set_cache(
        self, 
        id: str, 
        value: T, 
        seconds_until_expired: Optional[int] = None
    ) -> T:
        logger.debug(
            f"Setting '{id}' cache" + ("..." if self.section is None else f" in '{self.section}' section...")
        )

        json_data = {}

        with self.__get_cache_file("r") as file:
            json_data: Dict[str, BasicCacheData | Dict[str, BasicCacheData]] = json.load(file)

        with self.__get_cache_file("w") as file:
            timestamp = None

            if seconds_until_expired is not None:
                timestamp = datetime.now().timestamp() + float(seconds_until_expired)

            if self.section is not None:
                section_data = json_data.get(self.section, {})

                json_data[self.section] = {
                    **section_data, 
                    **{
                        id: {
                            "value": value,
                            "expiring_date": timestamp
                        }
                    }
                }

            else:
                json_data[id] = {
                    "value": value, "expiring_date": timestamp
                }

            json.dump(json_data, file)

        return value

    def clear_cache(self, id: str) -> None:
        logger.debug(
            f"Clearing '{id}' cache" + ("..." if self.section is None else f" from '{self.section}' section...")
        )

        json_data = {}

        with self.__get_cache_file("r") as file:
            json_data: Dict[str, BasicCacheData | Dict[str, BasicCacheData]] = json.load(file)

        if self.section is not None:
            json_data[self.section].pop(id)
        else:
            json_data.pop(id)

        with self.__get_cache_file("w") as file:
            json.dump(json_data, file)

        return None

    def clear_all_cache(self) -> None:
        logger.debug("Clearing all cache in file or section...")

        json_data = {}

        with self.__get_cache_file("r") as file:
            json_data: Dict[str, BasicCacheData | Dict[str, BasicCacheData]] = json.load(file)

        if self.section is not None:

            if self.section in json_data:
                json_data.pop(self.section)
        else:
            json_data = {}

        with self.__get_cache_file("w") as file:
            json.dump(json_data, file)

        return None

    def delete_cache_file(self) -> None:
        logger.info(f"Deleting basic cache file ({self._basic_cache_file_path.name})...")
        self._basic_cache_file_path.unlink(True)

    def __get_cache_file(self, mode: str) -> TextIOWrapper:

        if not self._basic_cache_file_path.exists():
            logger.debug("Cache file doesn't exist, creating one...")

            with self._basic_cache_file_path.open("w") as file:
                file.write("{}")

        return self._basic_cache_file_path.open(mode, encoding = "utf+8")