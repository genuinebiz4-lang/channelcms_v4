"""Shared helper utilities for Flowza v1.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def ensure_directory(path: str | Path) -> Path:
    """Create a directory if it does not already exist."""
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def normalize_text(value: Any, default: str = "") -> str:
    """Return a safe string value from common input types."""
    if value is None:
        return default
    return str(value).strip()
