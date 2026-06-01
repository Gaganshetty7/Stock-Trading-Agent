import logging
from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

_theme = Theme({
    "info": "white",
    "warning": "yellow",
    "error": "bold red",
    "debug": "cyan",
})

_console = Console(theme=_theme)


def get_logger(name: str = "ranker") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = RichHandler(console=_console, show_time=True, show_path=False, markup=True)
        handler.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
    return logger


logger = get_logger()
