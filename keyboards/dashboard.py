"""Dashboard keyboard builders for Flowza v1.0."""

from __future__ import annotations

from functools import lru_cache

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


@lru_cache(maxsize=1)
def build_dashboard_keyboard() -> InlineKeyboardMarkup:
    """Create the startup dashboard keyboard."""
    buttons = [
        [InlineKeyboardButton("🏢 Workspace", callback_data="dashboard:workspaces")],
        [InlineKeyboardButton("📢 Destinations", callback_data="dashboard:channels")],
        [InlineKeyboardButton("📝 Posts", callback_data="dashboard:posts")],
        [InlineKeyboardButton("📅 Scheduler", callback_data="dashboard:scheduler")],
        [InlineKeyboardButton("🖼 Media Library", callback_data="dashboard:media")],
        [InlineKeyboardButton("📂 Collections", callback_data="dashboard:collections")],
        [InlineKeyboardButton("📝 Templates", callback_data="dashboard:templates")],
        [InlineKeyboardButton("👥 Team", callback_data="dashboard:team")],
        [InlineKeyboardButton("📊 Analytics", callback_data="dashboard:admin_analytics")],
        [InlineKeyboardButton("⚙ Settings", callback_data="dashboard:settings")],
        [InlineKeyboardButton("❓ Help Center", callback_data="dashboard:help")],
        [InlineKeyboardButton("📞 Contact Support", callback_data="help:support")],
    ]
    return InlineKeyboardMarkup(buttons)


@lru_cache(maxsize=1)
def build_owner_dashboard_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("🏢 Workspace", callback_data="dashboard:workspaces")],
        [InlineKeyboardButton("📢 Destinations", callback_data="dashboard:channels")],
        [InlineKeyboardButton("📝 Posts", callback_data="dashboard:posts")],
        [InlineKeyboardButton("📅 Scheduler", callback_data="dashboard:scheduler")],
        [InlineKeyboardButton("🖥 System", callback_data="dashboard:owner_system")],
        [InlineKeyboardButton("👥 Users", callback_data="dashboard:owner_users")],
        [InlineKeyboardButton("🩺 Health", callback_data="dashboard:owner_health")],
        [InlineKeyboardButton("🗃 Backup", callback_data="dashboard:owner_backup")],
        [InlineKeyboardButton("❓ Help Center", callback_data="dashboard:help")],
        [InlineKeyboardButton("📞 Contact Support", callback_data="help:support")],
    ]
    return InlineKeyboardMarkup(buttons)


@lru_cache(maxsize=1)
def build_admin_dashboard_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("🏢 Workspace", callback_data="dashboard:workspaces")],
        [InlineKeyboardButton("📢 Destinations", callback_data="dashboard:channels")],
        [InlineKeyboardButton("📝 Posts", callback_data="dashboard:posts")],
        [InlineKeyboardButton("📅 Scheduler", callback_data="dashboard:scheduler")],
        [InlineKeyboardButton("🖼 Media Library", callback_data="dashboard:media")],
        [InlineKeyboardButton("📂 Collections", callback_data="dashboard:collections")],
        [InlineKeyboardButton("📝 Templates", callback_data="dashboard:templates")],
        [InlineKeyboardButton("👥 Team", callback_data="dashboard:team")],
        [InlineKeyboardButton("📈 Analytics", callback_data="dashboard:admin_analytics")],
        [InlineKeyboardButton("⚙ Settings", callback_data="dashboard:settings")],
        [InlineKeyboardButton("❓ Help Center", callback_data="dashboard:help")],
        [InlineKeyboardButton("📞 Contact Support", callback_data="help:support")],
    ]
    return InlineKeyboardMarkup(buttons)


@lru_cache(maxsize=1)
def build_editor_dashboard_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("📝 Drafts", callback_data="dashboard:posts")],
        [InlineKeyboardButton("📢 Assigned Destinations", callback_data="dashboard:workspaces")],
        [InlineKeyboardButton("📅 Scheduler", callback_data="dashboard:scheduler")],
        [InlineKeyboardButton("✅ Approval Queue", callback_data="dashboard:editor_approval")],
        [InlineKeyboardButton("❓ Help Center", callback_data="dashboard:help")],
        [InlineKeyboardButton("📞 Contact Support", callback_data="help:support")],
    ]
    return InlineKeyboardMarkup(buttons)


@lru_cache(maxsize=1)
def build_first_run_keyboard() -> InlineKeyboardMarkup:
    """Create first-run setup wizard keyboard for new users."""
    buttons = [
        [InlineKeyboardButton("1) Create Workspace", callback_data="setup:create_workspace")],
        [InlineKeyboardButton("2) Add Destination", callback_data="setup:add_destination")],
        [InlineKeyboardButton("3) Create First Post", callback_data="setup:create_post")],
        [InlineKeyboardButton("4) Publish", callback_data="setup:publish")],
        [InlineKeyboardButton("✅ Completed", callback_data="setup:complete")],
        [InlineKeyboardButton("🏠 Dashboard", callback_data="dashboard:home")],
    ]
    return InlineKeyboardMarkup(buttons)
