import logging

import pytest

from mar_dss.logging_config import APP_LOGGER, setup_logging


@pytest.fixture(autouse=True)
def restore_logging():
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    app_level = logging.getLogger(APP_LOGGER).level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)
    logging.getLogger(APP_LOGGER).setLevel(app_level)


def test_dev_mode_logs_app_debug(monkeypatch):
    monkeypatch.delenv("MAR_LOG_LEVEL", raising=False)
    setup_logging(dev=True)
    assert logging.getLogger("mar_dss.base").getEffectiveLevel() == logging.DEBUG
    assert logging.getLogger("urllib3").getEffectiveLevel() == logging.WARNING


def test_prod_mode_logs_app_info(monkeypatch):
    monkeypatch.delenv("MAR_LOG_LEVEL", raising=False)
    setup_logging(dev=False)
    assert logging.getLogger("mar_dss.base").getEffectiveLevel() == logging.INFO


def test_log_level_can_be_overridden(monkeypatch):
    monkeypatch.setenv("MAR_LOG_LEVEL", "warning")
    setup_logging(dev=True)
    assert logging.getLogger("mar_dss.base").getEffectiveLevel() == logging.WARNING
