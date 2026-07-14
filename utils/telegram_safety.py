"""Telegram runtime safety helpers for callback-heavy flows."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from telegram import InlineKeyboardMarkup
from telegram.error import BadRequest

from utils.logger import get_logger

logger = get_logger(__name__)


def _markup_payload(markup: InlineKeyboardMarkup | None) -> Any:
    if markup is None:
        return None
    try:
        return markup.to_dict()
    except Exception:
        return str(markup)


def _message_current_text(query: Any) -> str | None:
    message = getattr(query, "message", None)
    if message is None:
        return None
    text = getattr(message, "text", None)
    if text is not None:
        return text
    return getattr(message, "caption", None)


def _message_current_markup(query: Any) -> Any:
    message = getattr(query, "message", None)
    if message is None:
        return None
    return _markup_payload(getattr(message, "reply_markup", None))


def is_not_modified_error(exc: BaseException) -> bool:
    """Return True when Telegram rejects an unchanged edit request."""
    return "message is not modified" in str(exc).lower()


async def safe_answer(query: Any, text: str | None = None, *, show_alert: bool = False) -> bool:
    """Answer callback query safely and suppress harmless callback-age failures."""
    if query is None:
        return False
    try:
        await query.answer(text=text or "", show_alert=show_alert)
        return True
    except BadRequest as exc:
        message = str(exc).lower()
        if "query is too old" in message or "query id is invalid" in message:
            logger.debug("Ignoring stale callback answer failure: %s", exc)
            return False
        logger.debug("Ignoring callback answer bad request: %s", exc)
        return False
    except Exception as exc:
        logger.debug("Ignoring callback answer failure: %s", exc)
        return False


async def safe_edit_message(
    query: Any,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> bool:
    """Safely edit callback message text and ignore unchanged-content failures."""
    if query is None:
        return False

    incoming_markup = _markup_payload(reply_markup)
    if _message_current_text(query) == text and _message_current_markup(query) == incoming_markup:
        logger.debug("Skipping callback edit: content and keyboard unchanged")
        return False

    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
        return True
    except BadRequest as exc:
        if is_not_modified_error(exc):
            logger.debug("Ignoring non-modifying edit attempt: %s", exc)
            return False
        logger.debug("Ignoring callback edit bad request: %s", exc)
        return False


def duplicate_guard(bot_data: dict[str, Any], key: str, ttl_seconds: int) -> bool:
    """Return True if action is considered duplicate within ttl_seconds."""
    now = time.time()
    state = bot_data.setdefault("runtime_guards", {})
    last = float(state.get(key, 0.0))
    if (now - last) < max(1, int(ttl_seconds)):
        return True
    state[key] = now
    return False


async def retry_transient(
    action: Callable[[], Any],
    *,
    attempts: int = 3,
    delay_seconds: float = 0.4,
) -> Any:
    """Retry a transient async operation with short linear backoff."""
    import asyncio

    last_error: BaseException | None = None
    total = max(1, int(attempts))
    for idx in range(total):
        try:
            return await action()
        except Exception as exc:
            last_error = exc
            if idx == total - 1:
                break
            await asyncio.sleep(delay_seconds * float(idx + 1))
    if last_error is not None:
        raise last_error
    return None
