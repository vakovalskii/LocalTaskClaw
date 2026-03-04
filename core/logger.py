"""Logging setup."""

import logging
import sys


def _make_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(name)s] %(levelname)s %(message)s", "%H:%M:%S")
        )
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


agent_logger = _make_logger("agent")
tool_logger = _make_logger("tools")
bot_logger = _make_logger("bot")
core_logger = _make_logger("core")
