"""Settings handlers for role and approval workflow controls."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from database.settings import get_admin_for_user, is_approval_required, set_approval_required
from keyboards.settings import build_settings_keyboard
from utils.permissions import ROLE_ADMIN, get_request_role
from utils.telegram_safety import safe_answer, safe_edit_message


async def _send_or_edit(update: Update, text: str, keyboard=None, answer_text: str | None = None) -> None:
	"""Reply to a normal message or edit a callback message."""
	query = update.callback_query
	if query is not None:
		await safe_answer(query, answer_text)
		await safe_edit_message(query, text, reply_markup=keyboard)
		return

	if update.effective_message is not None:
		await update.effective_message.reply_text(text, reply_markup=keyboard)


async def settings_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Display current role and approval workflow status."""
	del context
	role = await get_request_role(update)
	user = update.effective_user
	if user is None or role is None:
		await _send_or_edit(update, "🚫 Access denied.", answer_text="Access denied")
		return

	admin_scope = await get_admin_for_user(user.id)
	approval_required = await is_approval_required(admin_scope) if admin_scope is not None else False
	can_toggle = role == ROLE_ADMIN and admin_scope is not None

	text = (
		"⚙️ Settings\n\n"
		f"Role: {role.title()}\n"
		f"Approval Workflow: {'ON' if approval_required else 'OFF'}\n\n"
		"Admins can enable approval so Editors create drafts but cannot publish directly."
	)
	await _send_or_edit(update, text, keyboard=build_settings_keyboard(approval_required, can_toggle))


async def toggle_approval_workflow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	"""Toggle approval workflow state for the signed-in admin."""
	del context
	role = await get_request_role(update)
	user = update.effective_user
	if user is None or role != ROLE_ADMIN:
		await _send_or_edit(update, "🚫 Only Admin can change approval workflow.", answer_text="Access denied")
		return

	admin_scope = await get_admin_for_user(user.id)
	if admin_scope is None:
		await _send_or_edit(update, "❌ Admin scope not found.", answer_text="Error")
		return

	current = await is_approval_required(admin_scope)
	await set_approval_required(admin_scope, not current)
	await settings_dashboard(update, context)
