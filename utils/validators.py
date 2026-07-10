"""Validation helpers for ChannelCMS V4."""

from __future__ import annotations

from typing import Any


def is_non_empty(value: Any) -> bool:
    """Return True when the provided value contains meaningful content."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return bool(value)
