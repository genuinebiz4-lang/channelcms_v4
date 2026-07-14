"""Admin and editor provisioning handlers for Flowza v1.0."""

from __future__ import annotations

from typing import Any

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config import OWNER_ID
from database.approval import get_admin_stats, get_editor_stats
from database.provisioning import (
    DEFAULT_EDITOR_PERMISSIONS,
    TRIAL_DAYS,
    audit_action,
    create_admin_profile,
    create_editor_profile,
    delete_admin,
    delete_editor,
    get_admin_dashboard_stats,
    get_admin_profile,
    get_editor_profile,
    list_admin_profiles,
    list_destinations_for_admin,
    list_editor_activity,
    list_editor_profiles,
    set_admin_status,
    set_editor_permission,
    set_editor_status,
    transfer_destination_owner,
)
from database.settings import get_admin_for_user
from database.workspace import assign_editor_workspace, create_workspace, list_workspaces
from keyboards.provisioning import build_add_admin_confirmation_keyboard, build_add_editor_confirmation_keyboard
from states import WAITING_ADMIN_FORWARD, WAITING_EDITOR_DESTINATIONS, WAITING_EDITOR_FORWARD, WAITING_EDITOR_WORKSPACE
from utils.logger import get_logger
from utils.permissions import ROLE_ADMIN, ROLE_EDITOR, get_request_role, is_owner

logger = get_logger(__name__)


def _forwarded_user(message: Any) -> Any | None:
    """Extract a forwarded Telegram user from multiple PTB forward formats."""
    if message is None:
        return None

    user = getattr(message, "forward_from", None)
    if user is not None:
        return user

    origin = getattr(message, "forward_origin", None)
    if origin is not None:
        sender_user = getattr(origin, "sender_user", None)
        if sender_user is not None:
            return sender_user
    return None


def _display_name(user: Any) -> str:
    if user is None:
        return "Unknown"
    name = str(getattr(user, "full_name", "") or "").strip()
    if name:
        return name
    first = str(getattr(user, "first_name", "") or "").strip()
    last = str(getattr(user, "last_name", "") or "").strip()
    return (first + " " + last).strip() or "Unknown"


def _username(user: Any) -> str | None:
    value = str(getattr(user, "username", "") or "").strip()
    return value or None


def _parse_id_argument(text: str) -> int | None:
    parts = text.strip().split()
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


async def _notify_user(context: ContextTypes.DEFAULT_TYPE, user_id: int, text: str) -> None:
    """Send best-effort notification message."""
    try:
        await context.bot.send_message(chat_id=user_id, text=text)
    except Exception:
        logger.warning("Could not notify user %s", user_id)


async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Begin owner-driven admin onboarding flow."""
    if not is_owner(update):
        await update.effective_message.reply_text("🚫 Only Platform Owner can create admins.")
        return

    context.user_data["provision_state"] = WAITING_ADMIN_FORWARD
    await update.effective_message.reply_text(
        "👤 Admin Onboarding\n\nForward a message from the Telegram user you want to create as Admin."
    )


async def receive_admin_forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Capture forwarded account for admin onboarding confirmation."""
    if not is_owner(update):
        await update.effective_message.reply_text("🚫 Only Platform Owner can create admins.")
        return

    message = update.effective_message
    forwarded = _forwarded_user(message)
    if forwarded is None:
        await message.reply_text("❌ Please forward a message from a real Telegram user account.")
        return

    target_id = int(forwarded.id)
    if OWNER_ID and target_id == OWNER_ID:
        await message.reply_text("❌ Owner account cannot be converted to Admin.")
        return

    context.user_data["pending_admin"] = {
        "id": target_id,
        "username": _username(forwarded),
        "full_name": _display_name(forwarded),
    }

    preview = (
        "Confirm Admin Creation\n\n"
        f"Telegram ID: {target_id}\n"
        f"Username: @{_username(forwarded) or 'n/a'}\n"
        f"Full Name: {_display_name(forwarded)}\n"
        f"Trial: {TRIAL_DAYS} days"
    )
    await message.reply_text(preview, reply_markup=build_add_admin_confirmation_keyboard(target_id))


async def add_admin_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, admin_id: int) -> None:
    """Finalize admin creation after owner confirmation."""
    query = update.callback_query
    if query is None:
        return

    if not is_owner(update):
        await query.answer("Access denied", show_alert=True)
        return

    pending = context.user_data.get("pending_admin") or {}
    if int(pending.get("id", 0)) != admin_id:
        await query.answer("Pending admin session expired", show_alert=True)
        return

    actor_id = int(update.effective_user.id)
    ok, message, profile = await create_admin_profile(
        admin_id=admin_id,
        username=pending.get("username"),
        full_name=pending.get("full_name") or f"User {admin_id}",
        actor_id=actor_id,
    )
    if not ok:
        await query.edit_message_text(f"❌ {message}")
        context.user_data.pop("pending_admin", None)
        context.user_data.pop("provision_state", None)
        return

    await audit_action(actor_id, "admin_created", admin_id)
    logger.info("Admin created: %s", admin_id)

    await _notify_user(
        context,
        admin_id,
        "🎉 You have been onboarded as an Admin in Flowza v1.0. Use /start to open your dashboard.",
    )

    await query.edit_message_text(
        "✅ Admin profile created successfully.\n\n"
        f"Admin ID: {admin_id}\n"
        f"Status: {profile.get('status')}\n"
        f"Trial Ends: {profile.get('trial_end')}"
    )
    context.user_data.pop("pending_admin", None)
    context.user_data.pop("provision_state", None)


async def add_admin_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel current admin onboarding session."""
    query = update.callback_query
    if query is None:
        return
    context.user_data.pop("pending_admin", None)
    context.user_data.pop("provision_state", None)
    await query.edit_message_text("Admin onboarding cancelled.")


async def list_admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all admin profiles for owner review."""
    del context
    if not is_owner(update):
        await update.effective_message.reply_text("🚫 Only Platform Owner can view admin list.")
        return

    admins = await list_admin_profiles()
    if not admins:
        await update.effective_message.reply_text("No admins found.")
        return

    lines = ["👥 Admin Accounts"]
    for admin in admins:
        lines.append(
            f"\nID: {admin['admin_id']} | {admin['full_name']} | @{admin.get('username') or 'n/a'} | {admin['status']}"
        )
    await update.effective_message.reply_text("\n".join(lines))


async def admin_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View one admin profile and usage details."""
    del context
    if not is_owner(update):
        await update.effective_message.reply_text("🚫 Only Platform Owner can view admin details.")
        return

    admin_id = _parse_id_argument(update.effective_message.text or "")
    if admin_id is None:
        await update.effective_message.reply_text("Usage: /admininfo <admin_id>")
        return

    profile = await get_admin_profile(admin_id)
    stats = await get_admin_dashboard_stats(admin_id)
    if profile is None:
        await update.effective_message.reply_text("Admin not found.")
        return

    await update.effective_message.reply_text(
        "📊 Admin Details\n\n"
        f"ID: {admin_id}\n"
        f"Name: {profile.get('full_name')}\n"
        f"Username: @{profile.get('username') or 'n/a'}\n"
        f"Status: {profile.get('status')}\n"
        f"Trial Days Left: {profile.get('trial_days_left', 0)}\n"
        f"Subscription Expiry: {profile.get('subscription_expiry') or 'not set'}\n"
        f"Editors: {stats.get('editors', 0)}\n"
        f"Destinations: {stats.get('destinations', 0)}\n"
        f"Workspaces: {stats.get('workspaces', 0)}\n"
        f"Scheduled Posts: {stats.get('scheduled_posts', 0)}\n"
        f"Published Today: {stats.get('published_today', 0)}"
    )


async def suspend_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Suspend an admin account."""
    if not is_owner(update):
        await update.effective_message.reply_text("🚫 Only Platform Owner can suspend admins.")
        return

    admin_id = _parse_id_argument(update.effective_message.text or "")
    if admin_id is None:
        await update.effective_message.reply_text("Usage: /suspendadmin <admin_id>")
        return

    ok = await set_admin_status(admin_id, active=False, actor_id=int(update.effective_user.id))
    if not ok:
        await update.effective_message.reply_text("Admin not found.")
        return

    logger.info("Admin suspended: %s", admin_id)
    await update.effective_message.reply_text("⛔ Admin suspended.")
    await _notify_user(context, admin_id, "Your Admin account has been suspended by the Platform Owner.")


async def activate_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Activate an admin account."""
    if not is_owner(update):
        await update.effective_message.reply_text("🚫 Only Platform Owner can activate admins.")
        return

    admin_id = _parse_id_argument(update.effective_message.text or "")
    if admin_id is None:
        await update.effective_message.reply_text("Usage: /activateadmin <admin_id>")
        return

    ok = await set_admin_status(admin_id, active=True, actor_id=int(update.effective_user.id))
    if not ok:
        await update.effective_message.reply_text("Admin not found.")
        return

    logger.info("Admin activated: %s", admin_id)
    await update.effective_message.reply_text("✅ Admin activated.")
    await _notify_user(context, admin_id, "Your Admin account has been activated by the Platform Owner.")


async def delete_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete an admin account and linked editor records."""
    del context
    if not is_owner(update):
        await update.effective_message.reply_text("🚫 Only Platform Owner can delete admins.")
        return

    admin_id = _parse_id_argument(update.effective_message.text or "")
    if admin_id is None:
        await update.effective_message.reply_text("Usage: /deleteadmin <admin_id>")
        return

    ok = await delete_admin(admin_id, int(update.effective_user.id))
    if not ok:
        await update.effective_message.reply_text("Admin not found.")
        return

    logger.info("Admin deleted: %s", admin_id)
    await update.effective_message.reply_text("🗑 Admin deleted.")


async def transfer_destination_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Transfer destination ownership to another admin."""
    if not is_owner(update):
        await update.effective_message.reply_text("🚫 Only Platform Owner can transfer destination ownership.")
        return

    parts = (update.effective_message.text or "").split()
    if len(parts) < 3:
        await update.effective_message.reply_text("Usage: /transferdestination <channel_id> <admin_id>")
        return

    try:
        channel_id = int(parts[1])
        admin_id = int(parts[2])
    except ValueError:
        await update.effective_message.reply_text("Channel ID and Admin ID must be numeric.")
        return

    ok = await transfer_destination_owner(channel_id, admin_id, int(update.effective_user.id))
    if not ok:
        await update.effective_message.reply_text("Transfer failed. Ensure the admin exists.")
        return

    logger.info("Destination ownership transferred: channel=%s admin=%s", channel_id, admin_id)
    await update.effective_message.reply_text("✅ Destination ownership transferred.")
    await _notify_user(context, admin_id, f"A destination was assigned to your admin scope: {channel_id}")


async def add_editor_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Begin admin editor onboarding flow."""
    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await update.effective_message.reply_text("🚫 Only Admin can create editors.")
        return

    context.user_data["provision_state"] = WAITING_EDITOR_FORWARD
    await update.effective_message.reply_text(
        "👤 Editor Onboarding\n\nForward a message from the Telegram user you want to add as Editor."
    )


async def receive_editor_forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Capture forwarded account for editor onboarding."""
    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await update.effective_message.reply_text("🚫 Only Admin can create editors.")
        return

    message = update.effective_message
    forwarded = _forwarded_user(message)
    if forwarded is None:
        await message.reply_text("❌ Please forward a message from a real Telegram user account.")
        return

    user = update.effective_user
    if user is None:
        return

    admin_scope = await get_admin_for_user(user.id)
    if admin_scope is None:
        await message.reply_text("❌ Admin scope missing.")
        return

    context.user_data["pending_editor"] = {
        "id": int(forwarded.id),
        "username": _username(forwarded),
        "full_name": _display_name(forwarded),
        "admin_id": int(admin_scope),
    }
    context.user_data["provision_state"] = WAITING_EDITOR_WORKSPACE
    await message.reply_text("Send workspace name for this editor (example: Marketing).")


async def receive_editor_workspace(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Capture workspace during editor onboarding."""
    pending = context.user_data.get("pending_editor") or {}
    if not pending:
        await update.effective_message.reply_text("Editor onboarding session expired. Use /addeditor again.")
        context.user_data.pop("provision_state", None)
        return

    workspace = (update.effective_message.text or "").strip()
    if not workspace:
        await update.effective_message.reply_text("❌ Workspace cannot be empty.")
        return

    pending["workspace"] = workspace
    context.user_data["pending_editor"] = pending
    context.user_data["provision_state"] = WAITING_EDITOR_DESTINATIONS
    await update.effective_message.reply_text(
        "Send assigned destination channel IDs separated by comma, or type 'all' or 'none'."
    )


async def receive_editor_destinations(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Capture destination assignment and ask for final confirmation."""
    pending = context.user_data.get("pending_editor") or {}
    if not pending:
        await update.effective_message.reply_text("Editor onboarding session expired. Use /addeditor again.")
        context.user_data.pop("provision_state", None)
        return

    raw = (update.effective_message.text or "").strip().lower()
    admin_id = int(pending.get("admin_id", 0))
    assigned: list[int] = []

    if raw == "all":
        assigned = await list_destinations_for_admin(admin_id)
    elif raw == "none" or not raw:
        assigned = []
    else:
        parsed: list[int] = []
        for part in raw.split(","):
            value = part.strip()
            if not value:
                continue
            try:
                parsed.append(int(value))
            except ValueError:
                await update.effective_message.reply_text("❌ Destination IDs must be numeric.")
                return
        assigned = parsed

    pending["destinations"] = assigned
    pending["permissions"] = dict(DEFAULT_EDITOR_PERMISSIONS)
    context.user_data["pending_editor"] = pending

    await update.effective_message.reply_text(
        "Confirm Editor Creation\n\n"
        f"Editor ID: {pending['id']}\n"
        f"Name: {pending['full_name']}\n"
        f"Workspace: {pending.get('workspace')}\n"
        f"Assigned Destinations: {', '.join(str(v) for v in assigned) if assigned else 'none'}\n"
        f"Default Permissions: {', '.join([k for k, v in pending['permissions'].items() if v])}",
        reply_markup=build_add_editor_confirmation_keyboard(int(pending["id"])),
    )


async def add_editor_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, editor_id: int) -> None:
    """Finalize editor onboarding after admin confirmation."""
    query = update.callback_query
    if query is None:
        return

    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await query.answer("Access denied", show_alert=True)
        return

    pending = context.user_data.get("pending_editor") or {}
    if int(pending.get("id", 0)) != editor_id:
        await query.answer("Pending editor session expired", show_alert=True)
        return

    actor_id = int(update.effective_user.id)
    ok, message, _profile = await create_editor_profile(
        editor_id=editor_id,
        username=pending.get("username"),
        full_name=pending.get("full_name") or f"User {editor_id}",
        admin_id=int(pending.get("admin_id")),
        workspace=str(pending.get("workspace") or "General"),
        destinations=list(pending.get("destinations") or []),
        permissions=dict(pending.get("permissions") or DEFAULT_EDITOR_PERMISSIONS),
        actor_id=actor_id,
    )

    if not ok:
        await query.edit_message_text(f"❌ {message}")
        context.user_data.pop("pending_editor", None)
        context.user_data.pop("provision_state", None)
        return

    logger.info("Editor created: %s under admin %s", editor_id, pending.get("admin_id"))

    admin_id = int(pending.get("admin_id"))
    workspace_name = str(pending.get("workspace") or "General").strip() or "General"
    all_workspaces = await list_workspaces(admin_id)
    target_workspace = next((ws for ws in all_workspaces if ws.get("workspace_name", "").lower() == workspace_name.lower()), None)
    if target_workspace is None:
        created, _msg, ws = await create_workspace(admin_id, workspace_name, "Auto-created from editor onboarding")
        if created and ws is not None:
            target_workspace = ws
    if target_workspace is not None:
        await assign_editor_workspace(editor_id, admin_id, int(target_workspace["workspace_id"]))

    await _notify_user(
        context,
        editor_id,
        "You have been onboarded as an Editor in Flowza v1.0. Use /start and /editordashboard.",
    )

    if OWNER_ID:
        await _notify_user(
            context,
            int(OWNER_ID),
            f"Editor created: {editor_id} under admin {pending.get('admin_id')}",
        )

    await query.edit_message_text("✅ Editor created successfully.")
    context.user_data.pop("pending_editor", None)
    context.user_data.pop("provision_state", None)


async def add_editor_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel current editor onboarding session."""
    query = update.callback_query
    if query is None:
        return
    context.user_data.pop("pending_editor", None)
    context.user_data.pop("provision_state", None)
    await query.edit_message_text("Editor onboarding cancelled.")


async def list_editors_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List admin-scoped editor profiles."""
    del context
    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await update.effective_message.reply_text("🚫 Only Admin can view editor list.")
        return

    admin_id = await get_admin_for_user(update.effective_user.id)
    if admin_id is None:
        await update.effective_message.reply_text("Admin scope missing.")
        return

    editors = await list_editor_profiles(admin_id)
    if not editors:
        await update.effective_message.reply_text("No editors found.")
        return

    lines = ["🧑‍💻 Editors"]
    for editor in editors:
        lines.append(
            f"\nID: {editor['editor_id']} | {editor['full_name']} | @{editor.get('username') or 'n/a'} | {editor['status']} | Workspace: {editor['workspace']}"
        )
    await update.effective_message.reply_text("\n".join(lines))


async def suspend_editor_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Suspend an editor under admin scope."""
    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await update.effective_message.reply_text("🚫 Only Admin can suspend editors.")
        return

    editor_id = _parse_id_argument(update.effective_message.text or "")
    if editor_id is None:
        await update.effective_message.reply_text("Usage: /suspendeditor <editor_id>")
        return

    admin_id = await get_admin_for_user(update.effective_user.id)
    if admin_id is None:
        await update.effective_message.reply_text("Admin scope missing.")
        return

    ok = await set_editor_status(editor_id, admin_id, active=False, actor_id=int(update.effective_user.id))
    if not ok:
        await update.effective_message.reply_text("Editor not found in your scope.")
        return

    logger.info("Editor suspended: %s by admin %s", editor_id, admin_id)
    await update.effective_message.reply_text("⛔ Editor suspended.")
    await _notify_user(context, editor_id, "Your Editor account has been suspended by your Admin.")


async def activate_editor_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Activate an editor under admin scope."""
    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await update.effective_message.reply_text("🚫 Only Admin can activate editors.")
        return

    editor_id = _parse_id_argument(update.effective_message.text or "")
    if editor_id is None:
        await update.effective_message.reply_text("Usage: /activateeditor <editor_id>")
        return

    admin_id = await get_admin_for_user(update.effective_user.id)
    if admin_id is None:
        await update.effective_message.reply_text("Admin scope missing.")
        return

    ok = await set_editor_status(editor_id, admin_id, active=True, actor_id=int(update.effective_user.id))
    if not ok:
        await update.effective_message.reply_text("Editor not found in your scope.")
        return

    logger.info("Editor activated: %s by admin %s", editor_id, admin_id)
    await update.effective_message.reply_text("✅ Editor activated.")
    await _notify_user(context, editor_id, "Your Editor account has been activated by your Admin.")


async def delete_editor_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete an editor under admin scope."""
    del context
    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await update.effective_message.reply_text("🚫 Only Admin can delete editors.")
        return

    editor_id = _parse_id_argument(update.effective_message.text or "")
    if editor_id is None:
        await update.effective_message.reply_text("Usage: /deleteeditor <editor_id>")
        return

    admin_id = await get_admin_for_user(update.effective_user.id)
    if admin_id is None:
        await update.effective_message.reply_text("Admin scope missing.")
        return

    ok = await delete_editor(editor_id, admin_id, int(update.effective_user.id))
    if not ok:
        await update.effective_message.reply_text("Editor not found in your scope.")
        return

    logger.info("Editor deleted: %s by admin %s", editor_id, admin_id)
    await update.effective_message.reply_text("🗑 Editor deleted.")


async def set_editor_permission_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Update one editor permission via command."""
    del context
    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await update.effective_message.reply_text("🚫 Only Admin can change editor permissions.")
        return

    parts = (update.effective_message.text or "").split()
    if len(parts) < 4:
        await update.effective_message.reply_text(
            "Usage: /seteditorperm <editor_id> <permission_key> <on|off>"
        )
        return

    try:
        editor_id = int(parts[1])
    except ValueError:
        await update.effective_message.reply_text("Editor ID must be numeric.")
        return

    permission = parts[2].strip().lower()
    toggle = parts[3].strip().lower()
    enabled = toggle in {"on", "true", "1", "yes"}

    admin_id = await get_admin_for_user(update.effective_user.id)
    if admin_id is None:
        await update.effective_message.reply_text("Admin scope missing.")
        return

    ok, message = await set_editor_permission(
        editor_id,
        admin_id,
        permission,
        enabled,
        int(update.effective_user.id),
    )
    if not ok:
        await update.effective_message.reply_text(f"❌ {message}")
        return

    logger.info("Editor permission changed: editor=%s permission=%s enabled=%s", editor_id, permission, enabled)
    await update.effective_message.reply_text(f"✅ {message}")


async def editor_activity_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show recent activity entries for editors under admin scope."""
    del context
    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await update.effective_message.reply_text("🚫 Only Admin can view editor activity.")
        return

    admin_id = await get_admin_for_user(update.effective_user.id)
    if admin_id is None:
        await update.effective_message.reply_text("Admin scope missing.")
        return

    editor_id = _parse_id_argument(update.effective_message.text or "")
    entries = await list_editor_activity(admin_id, editor_id=editor_id, limit=20)
    if not entries:
        await update.effective_message.reply_text("No editor activity found.")
        return

    lines = ["🧾 Editor Activity"]
    for entry in entries:
        lines.append(
            f"\n{entry['created_at']} | {entry['action']} | target={entry.get('target_user_id')}"
        )
    await update.effective_message.reply_text("\n".join(lines))


async def admin_dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show admin dashboard metrics."""
    del context
    role = await get_request_role(update)
    admin_id: int | None = None

    if role == ROLE_ADMIN:
        admin_id = await get_admin_for_user(update.effective_user.id)
    elif is_owner(update):
        admin_id = _parse_id_argument(update.effective_message.text or "")

    if admin_id is None:
        await update.effective_message.reply_text("Usage for owner: /admindashboard <admin_id>")
        return

    stats = await get_admin_dashboard_stats(admin_id)
    approval_stats = await get_admin_stats(admin_id)
    if not stats:
        await update.effective_message.reply_text("Admin dashboard data not found.")
        return

    await update.effective_message.reply_text(
        "📈 Admin Dashboard\n\n"
        f"Subscription Expiry: {stats.get('subscription_expiry') or 'not set'}\n"
        f"Trial Days Left: {stats.get('trial_days_left', 0)}\n"
        f"Editors: {stats.get('editors', 0)}\n"
        f"Destinations: {stats.get('destinations', 0)}\n"
        f"Workspaces: {stats.get('workspaces', 0)}\n"
        f"Scheduled Posts: {stats.get('scheduled_posts', 0)}\n"
        f"Published Today: {stats.get('published_today', 0)}\n"
        f"Status: {stats.get('status', 'unknown')}\n\n"
        f"Approval Pending: {approval_stats.get('pending', 0)}\n"
        f"Approval Approved: {approval_stats.get('approved', 0)}\n"
        f"Approval Rejected: {approval_stats.get('rejected', 0)}"
    )


async def editor_dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show editor dashboard summary."""
    del context
    role = await get_request_role(update)
    if role != ROLE_EDITOR:
        await update.effective_message.reply_text("🚫 Only Editor can access this dashboard.")
        return

    profile = await get_editor_profile(update.effective_user.id)
    queue_stats = await get_editor_stats(int(update.effective_user.id))
    if profile is None:
        await update.effective_message.reply_text("Editor profile not found.")
        return

    await update.effective_message.reply_text(
        "🧩 Editor Dashboard\n\n"
        f"Workspace: {profile.get('workspace')}\n"
        f"My Assigned Destinations: {', '.join(str(v) for v in profile.get('assigned_destinations', [])) or 'none'}\n"
        f"Pending Approval: {queue_stats.get('pending', 0)}\n"
        f"Rejected Drafts: {queue_stats.get('rejected', 0)}\n"
        f"Approved Drafts: {queue_stats.get('approved', 0)}\n"
        f"My Drafts: use Post Composer\n"
        f"My Schedules: use Scheduler"
    )


def register_provisioning_handlers(application: Application) -> None:
    """Register provisioning and dashboard commands."""
    application.add_handler(CommandHandler("addadmin", add_admin_command))
    application.add_handler(CommandHandler("admins", list_admins_command))
    application.add_handler(CommandHandler("admininfo", admin_info_command))
    application.add_handler(CommandHandler("suspendadmin", suspend_admin_command))
    application.add_handler(CommandHandler("activateadmin", activate_admin_command))
    application.add_handler(CommandHandler("deleteadmin", delete_admin_command))
    application.add_handler(CommandHandler("transferdestination", transfer_destination_command))

    application.add_handler(CommandHandler("addeditor", add_editor_command))
    application.add_handler(CommandHandler("editors", list_editors_command))
    application.add_handler(CommandHandler("suspendeditor", suspend_editor_command))
    application.add_handler(CommandHandler("activateeditor", activate_editor_command))
    application.add_handler(CommandHandler("deleteeditor", delete_editor_command))
    application.add_handler(CommandHandler("seteditorperm", set_editor_permission_command))
    application.add_handler(CommandHandler("editoractivity", editor_activity_command))

    application.add_handler(CommandHandler("admindashboard", admin_dashboard_command))
    application.add_handler(CommandHandler("editordashboard", editor_dashboard_command))
