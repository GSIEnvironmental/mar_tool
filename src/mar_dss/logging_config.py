"""Logging setup for the app.

Dev mode (``mar_dss --dev``) shows the app's DEBUG messages with a short
timestamp. Prod mode (plain ``mar_dss``) shows INFO and above with the full
date and time, which is what ends up in ``docker logs`` on the server.

Set MAR_LOG_LEVEL (DEBUG, INFO, WARNING, ...) to override the app's level in
either mode. Other libraries stay at WARNING so they don't flood the log.
"""

import logging
import os
import sys

APP_LOGGER = "mar_dss"

_DEV_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_DEV_DATEFMT = "%H:%M:%S"
_PROD_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_PROD_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(dev: bool = False) -> None:
    """Send log messages to stdout, with dev or prod settings."""
    default_level = "DEBUG" if dev else "INFO"
    level = os.environ.get("MAR_LOG_LEVEL", default_level).upper()

    logging.basicConfig(
        level=logging.WARNING,
        format=_DEV_FORMAT if dev else _PROD_FORMAT,
        datefmt=_DEV_DATEFMT if dev else _PROD_DATEFMT,
        stream=sys.stdout,
        force=True,
    )
    logging.getLogger(APP_LOGGER).setLevel(level)
    # Waitress logs its startup and "task queue depth" warnings at INFO.
    logging.getLogger("waitress").setLevel(logging.INFO)
