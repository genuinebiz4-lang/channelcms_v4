"""Dashboard keyboard builders for Flowza v1.0."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_dashboard_keyboard() -> InlineKeyboardMarkup:
    """Create the startup dashboard keyboard."""
    buttons = [
        [InlineKeyboardButton("🧭 Workspaces", callback_data="dashboard:workspaces")],
        [InlineKeyboardButton("📢 Destinations", callback_data="dashboard:channels")],
        [InlineKeyboardButton("📝 Posts", callback_data="dashboard:posts")],
        [InlineKeyboardButton("⏰ Scheduler", callback_data="dashboard:scheduler")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="dashboard:settings")],
    ]
    return InlineKeyboardMarkup(buttons)


def build_owner_dashboard_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("🖥 System", callback_data="dashboard:owner_system")],
        [InlineKeyboardButton("💰 Payments", callback_data="dashboard:owner_payments")],
        [InlineKeyboardButton("👥 Users", callback_data="dashboard:owner_users")],
        [InlineKeyboardButton("🩺 Health", callback_data="dashboard:owner_health")],
        [InlineKeyboardButton("🗃 Backup", callback_data="dashboard:owner_backup")],
    ]
    return InlineKeyboardMarkup(buttons)


def build_admin_dashboard_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("🧭 Workspace", callback_data="dashboard:workspaces")],
        [InlineKeyboardButton("📢 Destinations", callback_data="dashboard:channels")],
        [InlineKeyboardButton("📝 Posts", callback_data="dashboard:posts")],
        [InlineKeyboardButton("⏰ Scheduler", callback_data="dashboard:scheduler")],
        [InlineKeyboardButton("📈 Analytics", callback_data="dashboard:admin_analytics")],
        [InlineKeyboardButton("💳 Subscription", callback_data="dashboard:admin_subscription")],
    ]
    return InlineKeyboardMarkup(buttons)


def build_editor_dashboard_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("📝 Drafts", callback_data="dashboard:posts")],
        [InlineKeyboardButton("📢 Assigned Destinations", callback_data="dashboard:workspaces")],
        [InlineKeyboardButton("✅ Approval Queue", callback_data="dashboard:editor_approval")],
    ]
    return InlineKeyboardMarkup(buttons)
