"""Validation for user-entered text stored as a single line."""

from typing import Annotated
from unicodedata import category

from pydantic import AfterValidator


def single_line(value: str) -> str:
    if any(category(char) == 'Cc' for char in value):
        raise ValueError('Control characters are not allowed.')
    return value


SingleLine = Annotated[str, AfterValidator(single_line)]
