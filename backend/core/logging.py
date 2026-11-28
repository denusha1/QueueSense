"""Structured application events compatible with the hosting log handler."""

import json
import logging


def configure_application_logging() -> None:
    logger = logging.getLogger('queuesense')
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def log_event(
    logger: logging.Logger, level: int, event: str, **fields: str | int | float
) -> None:
    logger.log(
        level, '%s', json.dumps({'event': event, **fields}, separators=(',', ':'))
    )
