import logging

from app.utils.logging_config import setup_logging


def test_setup_logging_keeps_root_level_info():
    root_logger = logging.getLogger()
    original_level = root_logger.level
    try:
        setup_logging(level=logging.INFO)
        assert logging.getLogger().level == logging.INFO
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("telegram").level == logging.WARNING
    finally:
        root_logger.setLevel(original_level)
