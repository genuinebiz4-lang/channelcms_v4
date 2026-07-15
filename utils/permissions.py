"""Permission helpers for Flowza v1.0."""

from __future__ import annotations

from telegram import Update

from config import OWNER_ID
from database.settings import get_admin_for_user, get_user_role, is_approval_required

ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_EDITOR = "editor"


def is_owner(update: Update) -> bool:
    """Check whether the update sender is the configured owner."""
    user = update.effective_user
    return bool(user and OWNER_ID and user.id == OWNER_ID)


async def get_request_role(update: Update) -> str | None:
    """Resolve the request role using owner fallback then persisted roles."""
    user = update.effective_user
    if user is None:
        return None
    if is_owner(update):
        return ROLE_OWNER
    return await get_user_role(user.id)


async def can_manage_destinations(update: Update) -> bool:
    """Return whether the user can add/remove destinations."""
    role = await get_request_role(update)
    return role in {ROLE_OWNER, ROLE_ADMIN}


async def can_compose_content(update: Update) -> bool:
    """Return whether the user can create and edit drafts."""
    role = await get_request_role(update)
    return role in {ROLE_OWNER, ROLE_ADMIN, ROLE_EDITOR}


async def can_publish_content(update: Update) -> bool:
    """Return whether the user can publish immediately."""
    role = await get_request_role(update)
    if role in {ROLE_OWNER, ROLE_ADMIN}:
        return True
    if role != ROLE_EDITOR:
        return False

    user = update.effective_user
    if user is None:
        return False
    admin_id = await get_admin_for_user(user.id)
    if admin_id is None:
        return False
    return not await is_approval_required(admin_id)


async def can_manage_schedule(update: Update) -> bool:
    """Return whether the user can create and maintain schedules."""
    role = await get_request_role(update)
    return role in {ROLE_OWNER, ROLE_ADMIN, ROLE_EDITOR}


async def can_manage_settings(update: Update) -> bool:
    """Return whether the user can access workspace settings."""
    role = await get_request_role(update)
    return role in {ROLE_OWNER, ROLE_ADMIN}
