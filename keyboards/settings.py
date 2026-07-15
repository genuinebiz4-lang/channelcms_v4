"""Inline keyboard builders for settings flows."""

from __future__ import annotations

from functools import lru_cache

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


@lru_cache(maxsize=4)
def build_settings_keyboard(approval_required: bool, can_toggle: bool) -> InlineKeyboardMarkup:
	"""Build the settings action keyboard."""
	status_label = "ON" if approval_required else "OFF"
	buttons: list[list[InlineKeyboardButton]] = [
		[InlineKeyboardButton(f"Approval Workflow: {status_label}", callback_data="settings:dashboard")]
	]
	if can_toggle:
		buttons.append([InlineKeyboardButton("Toggle Approval Workflow", callback_data="settings:toggle_approval")])
	buttons.append([InlineKeyboardButton("⬅ Back", callback_data="dashboard:home")])
	buttons.append([InlineKeyboardButton("🏠 Dashboard", callback_data="dashboard:home")])
	return InlineKeyboardMarkup(buttons)
