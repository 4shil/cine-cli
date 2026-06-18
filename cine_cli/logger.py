import logging
from devgoldyutils import add_custom_handler, Colours

__all__ = ("cine_cli_logger",)

cine_cli_logger = add_custom_handler(
    logger = logging.getLogger(Colours.WHITE.apply("cine_cli")), 
    level = logging.INFO
)