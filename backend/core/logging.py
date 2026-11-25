"""Structured application events compatible with the hosting log handler."""

import json
import logging


def log_event(logger: logging.Logger, level: int, event: str, **fields: str) -> None:
    logger.log(
        level, '%s', json.dumps({'event': event, **fields}, separators=(',', ':'))
    )
