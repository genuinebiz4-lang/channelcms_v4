"""Approval queue handlers for Flowza v1.0."""

from __future__ import annotations

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config import OWNER_ID
from database.approval import (
    create_approval_request,
    get_admin_stats,
    get_editor_stats,
    get_owner_stats,
    get_queue_item,
    list_for_editor,
    list_pending_for_admin,
    set_status,
)
from database.drafts import get_draft, get_latest
from database.provisioning import audit_action, get_editor_profile
from database.settings import get_admin_for_user, is_approval_required
from handlers.post import publish_to_channel
from keyboards.approval import build_admin_approval_actions
from states import WAITING_APPROVAL_REJECT_REASON
from utils.logger import get_logger
from utils.permissions import ROLE_ADMIN, ROLE_EDITOR, get_request_role, is_owner
from utils.telegram_safety import safe_edit_message

logger = get_logger(__name__)


def _queue_id_from_callback(data: str) -> int | None:
    try:
        return int(data.split(":")[-1])
    except Exception:
        return None


async def submit_approval_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Submit latest draft for admin approval by an editor."""
    role = await get_request_role(update)
    if role != ROLE_EDITOR:
        await update.effective_message.reply_text("🚫 Only Editors can submit drafts for approval.")
        return

    editor = update.effective_user
    if editor is None:
        return

    admin_id = await get_admin_for_user(editor.id)
    if admin_id is None:
        await update.effective_message.reply_text("❌ Admin scope not found for this editor.")
        return

    approval_on = await is_approval_required(admin_id)
    if not approval_on:
        await update.effective_message.reply_text("Approval workflow is OFF. You can publish directly.")
        return

    draft = await get_latest()
    if not draft:
        await update.effective_message.reply_text("❌ No draft available.")
        return

    profile = await get_editor_profile(editor.id)
    if profile is None:
        await update.effective_message.reply_text("❌ Editor profile not found.")
        return

    destination_id = None
    assigned = profile.get("assigned_destinations") or []
    if assigned:
        destination_id = int(assigned[0])

    ok, message, queue_item = await create_approval_request(
        draft_id=int(draft["id"]),
        editor_id=int(editor.id),
        admin_id=int(admin_id),
        workspace=str(profile.get("workspace") or "General"),
        destination_id=destination_id,
    )
    if not ok:
        await update.effective_message.reply_text(f"❌ {message}")
        return

    await audit_action(int(editor.id), "approval_submitted", int(editor.id), {"queue_id": queue_item["id"], "draft_id": draft["id"]})
    logger.info("Approval submitted: queue=%s draft=%s editor=%s", queue_item["id"], draft["id"], editor.id)

    await update.effective_message.reply_text("✅ Draft submitted for approval.")

    try:
        await context.bot.send_message(
            chat_id=admin_id,
            text=(
                "🆕 New Draft Waiting for Approval\n\n"
                f"Queue ID: {queue_item['id']}\n"
                f"Draft ID: {queue_item['draft_id']}\n"
                f"Editor ID: {queue_item['editor_id']}\n"
                f"Workspace: {queue_item['workspace']}\n"
                f"Destination: {queue_item.get('destination_id') or 'not set'}"
            ),
            reply_markup=build_admin_approval_actions(int(queue_item["id"])),
        )
    except Exception:
        logger.warning("Could not notify admin %s for queue %s", admin_id, queue_item["id"])


async def pending_queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show admin pending approval queue."""
    del context
    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await update.effective_message.reply_text("🚫 Only Admin can view pending queue.")
        return

    admin_id = await get_admin_for_user(update.effective_user.id)
    if admin_id is None:
        await update.effective_message.reply_text("Admin scope missing.")
        return

    items = await list_pending_for_admin(admin_id, limit=20)
    if not items:
        await update.effective_message.reply_text("No pending drafts in queue.")
        return

    lines = ["🗂 Pending Approval Queue"]
    for item in items:
        lines.append(
            f"\nQueue #{item['id']} | Draft {item['draft_id']} | Editor {item['editor_id']} | Workspace {item['workspace']}"
        )
    await update.effective_message.reply_text("\n".join(lines))


async def approval_preview_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, queue_id: int) -> None:
    """Preview queued draft details for admin."""
    query = update.callback_query
    if query is None:
        return

    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await query.answer("Access denied", show_alert=True)
        return

    item = await get_queue_item(queue_id)
    if item is None:
        await query.answer("Queue item not found", show_alert=True)
        return

    admin_id = await get_admin_for_user(update.effective_user.id)
    if admin_id is None or int(item["admin_id"]) != int(admin_id):
        await query.answer("You cannot access this queue item", show_alert=True)
        return

    draft = await get_draft(int(item["draft_id"]))
    if draft is None:
        await safe_edit_message(query, "❌ Draft not found (possibly deleted).")
        return

    text = (
        "🧾 Approval Preview\n\n"
        f"Queue ID: {item['id']}\n"
        f"Draft ID: {item['draft_id']}\n"
        f"Type: {draft.get('draft_type')}\n"
        f"Workspace: {item.get('workspace')}\n"
        f"Destination: {item.get('destination_id') or 'not set'}\n"
        f"Status: {item.get('status')}"
    )
    if draft.get("text"):
        text += f"\n\nText:\n{draft['text']}"
    if draft.get("caption"):
        text += f"\n\nCaption:\n{draft['caption']}"

    await safe_edit_message(query, text, reply_markup=build_admin_approval_actions(queue_id))


async def approval_approve_now_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, queue_id: int) -> None:
    """Approve and publish queued draft immediately."""
    query = update.callback_query
    if query is None:
        return

    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await query.answer("Access denied", show_alert=True)
        return

    item = await get_queue_item(queue_id)
    if item is None:
        await query.answer("Queue item not found", show_alert=True)
        return

    admin_id = await get_admin_for_user(update.effective_user.id)
    if admin_id is None or int(item["admin_id"]) != int(admin_id):
        await query.answer("You cannot approve this queue item", show_alert=True)
        return

    if item.get("status") != "pending":
        await query.answer("This queue item is no longer pending", show_alert=True)
        return

    draft = await get_draft(int(item["draft_id"]))
    if draft is None:
        await set_status(queue_id, status="cancelled")
        await safe_edit_message(query, "❌ Draft was deleted. Approval cancelled.")
        return

    destination = item.get("destination_id")
    if not destination:
        await safe_edit_message(query, "❌ Destination is not assigned for this queue item.")
        return

    await set_status(queue_id, status="approved", approved_by=int(update.effective_user.id))
    await audit_action(int(update.effective_user.id), "approval_approved", item["editor_id"], {"queue_id": queue_id})

    await publish_to_channel(update, context, int(destination))

    await set_status(queue_id, status="published", approved_by=int(update.effective_user.id))
    await audit_action(int(update.effective_user.id), "approval_published", item["editor_id"], {"queue_id": queue_id})
    logger.info("Approval published immediately: queue=%s", queue_id)

    try:
        await context.bot.send_message(chat_id=int(item["editor_id"]), text=f"✅ Draft approved and published. Queue #{queue_id}")
    except Exception:
        logger.warning("Could not notify editor %s for published queue %s", item["editor_id"], queue_id)


async def approval_approve_schedule_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, queue_id: int) -> None:
    """Approve queued draft and leave it ready for scheduling."""
    query = update.callback_query
    if query is None:
        return

    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await query.answer("Access denied", show_alert=True)
        return

    item = await get_queue_item(queue_id)
    if item is None:
        await query.answer("Queue item not found", show_alert=True)
        return

    admin_id = await get_admin_for_user(update.effective_user.id)
    if admin_id is None or int(item["admin_id"]) != int(admin_id):
        await query.answer("You cannot approve this queue item", show_alert=True)
        return

    if item.get("status") != "pending":
        await query.answer("This queue item is no longer pending", show_alert=True)
        return

    draft = await get_draft(int(item["draft_id"]))
    if draft is None:
        await set_status(queue_id, status="cancelled")
        await safe_edit_message(query, "❌ Draft was deleted. Approval cancelled.")
        return

    await set_status(queue_id, status="approved", approved_by=int(update.effective_user.id))
    await audit_action(int(update.effective_user.id), "approval_approved_for_schedule", item["editor_id"], {"queue_id": queue_id})
    logger.info("Approval approved for scheduling: queue=%s", queue_id)

    await safe_edit_message(
        query,
        f"✅ Queue #{queue_id} approved for scheduling. Use Scheduler module to set run time.",
        reply_markup=build_admin_approval_actions(queue_id),
    )

    try:
        await context.bot.send_message(chat_id=int(item["editor_id"]), text=f"✅ Draft approved. Admin selected scheduling. Queue #{queue_id}")
    except Exception:
        logger.warning("Could not notify editor %s for approved queue %s", item["editor_id"], queue_id)


async def approval_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, queue_id: int) -> None:
    """Start rejection reason capture."""
    query = update.callback_query
    if query is None:
        return

    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await query.answer("Access denied", show_alert=True)
        return

    item = await get_queue_item(queue_id)
    if item is None or item.get("status") != "pending":
        await query.answer("Queue item is unavailable", show_alert=True)
        return

    admin_id = await get_admin_for_user(update.effective_user.id)
    if admin_id is None or int(item["admin_id"]) != int(admin_id):
        await query.answer("You cannot reject this queue item", show_alert=True)
        return

    context.user_data["approval_reject_queue_id"] = queue_id
    context.user_data["approval_state"] = WAITING_APPROVAL_REJECT_REASON
    await safe_edit_message(query, f"Send rejection reason for Queue #{queue_id}.")


async def approval_reject_reason_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Finalize rejection after receiving reason text from admin."""
    queue_id = context.user_data.get("approval_reject_queue_id")
    if queue_id is None:
        return

    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await update.effective_message.reply_text("🚫 Only Admin can reject approvals.")
        return

    item = await get_queue_item(int(queue_id))
    if item is None or item.get("status") != "pending":
        await update.effective_message.reply_text("Queue item is no longer pending.")
        context.user_data.pop("approval_reject_queue_id", None)
        context.user_data.pop("approval_state", None)
        return

    admin_id = await get_admin_for_user(update.effective_user.id)
    if admin_id is None or int(item["admin_id"]) != int(admin_id):
        await update.effective_message.reply_text("You cannot reject this queue item.")
        context.user_data.pop("approval_reject_queue_id", None)
        context.user_data.pop("approval_state", None)
        return

    reason = (update.effective_message.text or "").strip()
    if not reason:
        await update.effective_message.reply_text("❌ Rejection reason cannot be empty.")
        return

    await set_status(
        int(queue_id),
        status="rejected",
        rejected_by=int(update.effective_user.id),
        rejected_reason=reason,
    )
    await audit_action(int(update.effective_user.id), "approval_rejected", item["editor_id"], {"queue_id": queue_id, "reason": reason})
    logger.info("Approval rejected: queue=%s", queue_id)

    await update.effective_message.reply_text(f"❌ Queue #{queue_id} rejected.")
    try:
        await context.bot.send_message(
            chat_id=int(item["editor_id"]),
            text=f"❌ Draft rejected. Queue #{queue_id}\nReason: {reason}",
        )
    except Exception:
        logger.warning("Could not notify editor %s for rejected queue %s", item["editor_id"], queue_id)

    context.user_data.pop("approval_reject_queue_id", None)
    context.user_data.pop("approval_state", None)


async def approval_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, queue_id: int) -> None:
    """Notify editor to edit draft after admin review."""
    query = update.callback_query
    if query is None:
        return

    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await query.answer("Access denied", show_alert=True)
        return

    item = await get_queue_item(queue_id)
    if item is None:
        await query.answer("Queue item not found", show_alert=True)
        return

    admin_id = await get_admin_for_user(update.effective_user.id)
    if admin_id is None or int(item["admin_id"]) != int(admin_id):
        await query.answer("You cannot edit this queue item", show_alert=True)
        return

    await safe_edit_message(query, f"✏ Editor notified to revise draft for Queue #{queue_id}.")
    try:
        await context.bot.send_message(
            chat_id=int(item["editor_id"]),
            text=f"✏ Admin requested draft edits. Queue #{queue_id}. Update the draft and resubmit approval.",
        )
    except Exception:
        logger.warning("Could not notify editor %s for edit request queue %s", item["editor_id"], queue_id)


async def approval_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show approval queue statistics by role scope."""
    del context
    role = await get_request_role(update)

    if is_owner(update):
        stats = await get_owner_stats()
        await update.effective_message.reply_text(
            "📊 Owner Approval Statistics\n\n"
            f"Pending: {stats['pending']}\n"
            f"Approved: {stats['approved']}\n"
            f"Rejected: {stats['rejected']}\n"
            f"Published: {stats['published']}\n"
            f"Expired: {stats['expired']}\n"
            f"Cancelled: {stats['cancelled']}"
        )
        return

    if role == ROLE_ADMIN:
        admin_id = await get_admin_for_user(update.effective_user.id)
        if admin_id is None:
            await update.effective_message.reply_text("Admin scope missing.")
            return
        stats = await get_admin_stats(admin_id)
        await update.effective_message.reply_text(
            "📊 Admin Approval Statistics\n\n"
            f"Pending: {stats['pending']}\n"
            f"Approved: {stats['approved']}\n"
            f"Rejected: {stats['rejected']}\n"
            f"Published: {stats['published']}\n"
            f"Expired: {stats['expired']}\n"
            f"Cancelled: {stats['cancelled']}"
        )
        return

    if role == ROLE_EDITOR:
        editor_id = int(update.effective_user.id)
        stats = await get_editor_stats(editor_id)
        await update.effective_message.reply_text(
            "📊 Editor Approval Statistics\n\n"
            f"Pending Drafts: {stats['pending']}\n"
            f"Approved Drafts: {stats['approved']}\n"
            f"Rejected Drafts: {stats['rejected']}\n"
            f"Published Drafts: {stats['published']}"
        )
        return

    await update.effective_message.reply_text("🚫 Access denied.")


async def editor_queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show editor queue records with status view support."""
    del context
    role = await get_request_role(update)
    if role != ROLE_EDITOR:
        await update.effective_message.reply_text("🚫 Only Editor can use this command.")
        return

    parts = (update.effective_message.text or "").split()
    status = parts[1].strip().lower() if len(parts) > 1 else None
    rows = await list_for_editor(int(update.effective_user.id), status=status, limit=50)
    if not rows:
        await update.effective_message.reply_text("No queue records found.")
        return

    lines = ["🧩 My Approval Queue"]
    for row in rows:
        lines.append(
            f"\nQueue #{row['id']} | Draft {row['draft_id']} | Status {row['status']} | Workspace {row['workspace']}"
        )
    await update.effective_message.reply_text("\n".join(lines))


def register_approval_handlers(application: Application) -> None:
    """Register command handlers for approval workflow."""
    application.add_handler(CommandHandler("submitapproval", submit_approval_command))
    application.add_handler(CommandHandler("pendingqueue", pending_queue_command))
    application.add_handler(CommandHandler("approvalstats", approval_stats_command))
    application.add_handler(CommandHandler("myqueue", editor_queue_command))
