"""Callback query routing for Flowza v1.0."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from handlers.channel import (
    add_channel_menu,
    channel_dashboard,
    default_channel_menu,
    list_channels,
    remove_channel_confirm,
    remove_channel_menu,
    set_default_channel,
)
from handlers.post import (
    album_post,
    delete_draft,
    document_post,
    edit_draft,
    gif_post,
    photo_post,
    post_dashboard,
    preview_post,
    publish_post,
    publish_to_channel,
    text_post,
    video_post,
)
from handlers.approval import (
    approval_approve_now_callback,
    approval_approve_schedule_callback,
    approval_edit_callback,
    approval_preview_callback,
    approval_reject_callback,
)
from handlers.workspace import (
    collection_delete_no_callback,
    collection_delete_yes_callback,
    workspace_dashboard_callback,
    workspace_delete_no_callback,
    workspace_delete_yes_callback,
    workspace_switch_callback,
)
from handlers.commercial import admin_menu_callback, editor_menu_callback, owner_menu_callback
from handlers.provisioning import (
    add_admin_cancel_callback,
    add_admin_confirm_callback,
    add_editor_cancel_callback,
    add_editor_confirm_callback,
)
from handlers.scheduler import (
    delete_schedule,
    edit_schedule,
    list_schedules,
    pause_schedule,
    resume_schedule,
    schedule_post,
    scheduler_dashboard,
)
from handlers.settings import settings_dashboard, toggle_approval_workflow
from utils.logger import get_logger

logger = get_logger(__name__)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard callback queries."""
    query = update.callback_query
    if query is None:
        return

    data = query.data or ""
    if data == "dashboard:channels":
        await query.answer()
        await channel_dashboard(update, context)
        return

    if data == "dashboard:workspaces":
        await query.answer()
        await workspace_dashboard_callback(update, context)
        return

    if data == "dashboard:posts":
        await query.answer()
        await post_dashboard(update, context)
        return

    if data == "dashboard:scheduler":
        await query.answer()
        await scheduler_dashboard(update, context)
        return

    if data == "dashboard:settings":
        await query.answer()
        await settings_dashboard(update, context)
        return

    if data in {"dashboard:owner_system", "dashboard:owner_payments", "dashboard:owner_users", "dashboard:owner_health", "dashboard:owner_backup"}:
        await query.answer()
        await owner_menu_callback(update, context)
        return

    if data in {"dashboard:admin_analytics", "dashboard:admin_subscription"}:
        await query.answer()
        await admin_menu_callback(update, context)
        return

    if data == "dashboard:editor_approval":
        await query.answer()
        await editor_menu_callback(update, context)
        return

    if data == "settings:dashboard":
        await query.answer()
        await settings_dashboard(update, context)
        return

    if data == "settings:toggle_approval":
        await query.answer()
        await toggle_approval_workflow(update, context)
        return

    if data.startswith("provision:addadmin:confirm:"):
        admin_id = int(data.split(":")[-1])
        await query.answer()
        await add_admin_confirm_callback(update, context, admin_id)
        return

    if data == "provision:addadmin:cancel":
        await query.answer()
        await add_admin_cancel_callback(update, context)
        return

    if data.startswith("provision:addeditor:confirm:"):
        editor_id = int(data.split(":")[-1])
        await query.answer()
        await add_editor_confirm_callback(update, context, editor_id)
        return

    if data == "provision:addeditor:cancel":
        await query.answer()
        await add_editor_cancel_callback(update, context)
        return

    if data.startswith("approval:preview:"):
        queue_id = int(data.split(":")[-1])
        await query.answer()
        await approval_preview_callback(update, context, queue_id)
        return

    if data.startswith("approval:approve_now:"):
        queue_id = int(data.split(":")[-1])
        await query.answer()
        await approval_approve_now_callback(update, context, queue_id)
        return

    if data.startswith("approval:approve_schedule:"):
        queue_id = int(data.split(":")[-1])
        await query.answer()
        await approval_approve_schedule_callback(update, context, queue_id)
        return

    if data.startswith("approval:reject:"):
        queue_id = int(data.split(":")[-1])
        await query.answer()
        await approval_reject_callback(update, context, queue_id)
        return

    if data.startswith("approval:edit:"):
        queue_id = int(data.split(":")[-1])
        await query.answer()
        await approval_edit_callback(update, context, queue_id)
        return

    if data.startswith("workspace:switch:"):
        workspace_id = int(data.split(":")[-1])
        await query.answer()
        await workspace_switch_callback(update, context, workspace_id)
        return

    if data.startswith("workspace:delete_yes:"):
        workspace_id = int(data.split(":")[-1])
        await query.answer()
        await workspace_delete_yes_callback(update, context, workspace_id)
        return

    if data == "workspace:delete_no":
        await query.answer()
        await workspace_delete_no_callback(update, context)
        return

    if data.startswith("collection:delete_yes:"):
        collection_id = int(data.split(":")[-1])
        await query.answer()
        await collection_delete_yes_callback(update, context, collection_id)
        return

    if data == "collection:delete_no":
        await query.answer()
        await collection_delete_no_callback(update, context)
        return

    if data == "post:dashboard":
        await query.answer()
        await post_dashboard(update, context)
        return

    if data == "post:text":
        await query.answer()
        await text_post(update, context)
        return

    if data == "post:photo":
        await query.answer()
        await photo_post(update, context)
        return

    if data == "post:gif":
        await query.answer()
        await gif_post(update, context)
        return

    if data == "post:video":
        await query.answer()
        await video_post(update, context)
        return

    if data == "post:document":
        await query.answer()
        await document_post(update, context)
        return

    if data == "post:album":
        await query.answer()
        await album_post(update, context)
        return

    if data == "post:preview":
        await query.answer()
        await preview_post(update, context)
        return

    if data == "post:publish":
        await query.answer()
        await publish_post(update, context)
        return

    if data == "post:delete":
        await query.answer()
        await delete_draft(update, context)
        return

    if data == "post:edit":
        await query.answer()
        await edit_draft(update, context)
        return

    if data.startswith("post:channel:"):
        channel_id = int(data.split(":", 2)[-1])
        await query.answer()
        await publish_to_channel(update, context, channel_id)
        return

    if data == "channel:dashboard":
        await query.answer()
        await channel_dashboard(update, context)
        return

    if data == "channel:add":
        await query.answer()
        await add_channel_menu(update, context)
        return

    if data == "channel:list":
        await query.answer()
        await list_channels(update, context)
        return

    if data == "channel:default_menu":
        await query.answer()
        await default_channel_menu(update, context)
        return

    if data == "channel:remove_menu":
        await query.answer()
        await remove_channel_menu(update, context)
        return

    if data == "channel:refresh":
        await query.answer()
        await channel_dashboard(update, context)
        return

    if data.startswith("channel:set_default:"):
        channel_id = int(data.split(":", 2)[-1])
        await query.answer()
        await set_default_channel(update, context, channel_id)
        return

    if data.startswith("channel:remove_confirm:"):
        channel_id = int(data.split(":", 2)[-1])
        await query.answer()
        await remove_channel_confirm(update, context, channel_id)
        return

    if data.startswith("channel:remove_yes:"):
        channel_id = int(data.split(":", 2)[-1])
        await query.answer()
        await remove_channel_confirm(update, context, channel_id, confirmed=True)
        return

    if data == "scheduler:schedule":
        await query.answer()
        await schedule_post(update, context)
        return

    if data == "scheduler:list":
        await query.answer()
        await list_schedules(update, context)
        return

    if data.startswith("scheduler:pause:"):
        await query.answer()
        await pause_schedule(update, context)
        return

    if data.startswith("scheduler:resume:"):
        await query.answer()
        await resume_schedule(update, context)
        return

    if data.startswith("scheduler:edit:"):
        await query.answer()
        await edit_schedule(update, context)
        return

    if data.startswith("scheduler:delete:"):
        await query.answer()
        await delete_schedule(update, context)
        return

    await query.answer("Unsupported action.")
