"""Notification center and audit visibility handlers for Flowza v1.0.2."""

from __future__ import annotations

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from database.enterprise import (
    list_audit_logs,
    list_notifications,
    list_retry_queue,
    mark_notifications_read,
    run_maintenance,
)
from utils.permissions import ROLE_ADMIN, ROLE_EDITOR, get_request_role, is_owner


async def notifications_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    role = await get_request_role(update)
    if role not in {ROLE_ADMIN, ROLE_EDITOR} and not is_owner(update):
        await update.effective_message.reply_text("🚫 Access denied.")
        return

    rows = await list_notifications(update.effective_user.id, unread_only=False, limit=20)
    if not rows:
        await update.effective_message.reply_text("🔔 Notification Center is empty.")
        return

    lines = ["🔔 Notification Center"]
    for row in rows[:10]:
        marker = "✅" if int(row.get("is_read") or 0) else "🆕"
        lines.append(f"\n{marker} [{row.get('category')}] {row.get('title')}")
        lines.append(f"{row.get('message')}")
    await update.effective_message.reply_text("\n".join(lines))


async def mark_notifications_read_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    role = await get_request_role(update)
    if role not in {ROLE_ADMIN, ROLE_EDITOR} and not is_owner(update):
        await update.effective_message.reply_text("🚫 Access denied.")
        return

    count = await mark_notifications_read(update.effective_user.id)
    await update.effective_message.reply_text(f"✅ Marked {count} notification(s) as read.")


async def maintenance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if not is_owner(update):
        await update.effective_message.reply_text("🚫 Only owner can run maintenance.")
        return

    result = await run_maintenance()
    await update.effective_message.reply_text(
        "🧹 Maintenance Complete\n"
        f"Deleted retry rows: {result.get('deleted_retry', 0)}\n"
        f"Deleted notifications: {result.get('deleted_notifications', 0)}"
    )


async def audit_log_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    role = await get_request_role(update)
    if role not in {ROLE_ADMIN} and not is_owner(update):
        await update.effective_message.reply_text("🚫 Access denied.")
        return

    parts = (update.effective_message.text or "").split(maxsplit=1)
    module = parts[1].strip().lower() if len(parts) > 1 else None
    rows = await list_audit_logs(module=module, limit=20)
    if not rows:
        await update.effective_message.reply_text("No audit records found.")
        return

    lines = ["📚 Central Audit Log"]
    for row in rows[:10]:
        lines.append(f"\n#{row['id']} [{row.get('module')}] {row.get('action')} -> {row.get('target_type') or '-'}:{row.get('target_id') or '-'}")
    await update.effective_message.reply_text("\n".join(lines))


async def retry_queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    role = await get_request_role(update)
    if role not in {ROLE_ADMIN} and not is_owner(update):
        await update.effective_message.reply_text("🚫 Access denied.")
        return

    rows = await list_retry_queue(limit=30)
    if not rows:
        await update.effective_message.reply_text("Retry queue is empty.")
        return

    lines = ["🧵 Retry Queue"]
    for row in rows[:10]:
        lines.append(
            f"\n#{row['id']} sched={row.get('schedule_id') or '-'} priority={row.get('priority')} status={row.get('status')} attempts={row.get('attempt_count')}/{row.get('max_attempts')}"
        )
    await update.effective_message.reply_text("\n".join(lines))


def register_notification_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("notifications", notifications_command))
    application.add_handler(CommandHandler("readnotifications", mark_notifications_read_command))
    application.add_handler(CommandHandler("maintenance", maintenance_command))
    application.add_handler(CommandHandler("auditlog", audit_log_command))
    application.add_handler(CommandHandler("retryqueue", retry_queue_command))
