"""Callback query routing for Flowza v1.0."""

from __future__ import annotations

import re

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
    audio_post,
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
    voice_post,
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
    workspace_open_collections_callback,
    workspace_open_create_callback,
    workspace_open_list_callback,
    workspace_open_media_callback,
    workspace_open_switch_callback,
    workspace_open_templates_callback,
    workspace_switch_callback,
)
from handlers.help_center import (
    help_center_callback,
    help_topic_callback,
    manual_callback,
    support_callback,
)
from handlers.commercial import (
    admin_menu_callback,
    editor_menu_callback,
    owner_menu_callback,
    subscription_command,
    subscription_back_callback,
    subscription_copy_wallet_callback,
    subscription_payment_history_callback,
    subscription_verify_payment_callback,
)
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
    select_schedule_destination_callback,
    scheduler_dashboard,
)
from handlers.settings import settings_dashboard, toggle_approval_workflow
from handlers.start import send_dashboard
from utils.logger import get_logger
from utils.telegram_safety import safe_answer

logger = get_logger(__name__)
CALLBACK_DATA_RE = re.compile(r"^[a-z_]+(?::[-a-z0-9_]+)*$")


def _parse_callback_int(data: str, *, prefix: str) -> int | None:
    if not data.startswith(prefix):
        return None
    value = data.removeprefix(prefix)
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard callback queries."""
    query = update.callback_query
    if query is None:
        return

    data = query.data or ""
    if not CALLBACK_DATA_RE.match(data):
        await safe_answer(query, "Invalid callback data", show_alert=True)
        logger.info("Rejected malformed callback payload: %s", data)
        return

    try:
        await _dispatch_callback(update, context, data)
    except Exception as exc:
        logger.exception("Callback routing failure for data=%s: %s", data, exc)
        await safe_answer(query, "Action failed. Please retry.", show_alert=True)


async def _dispatch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    query = update.callback_query
    if query is None:
        return

    if data == "dashboard:channels":
        await safe_answer(query)
        await channel_dashboard(update, context)
        return

    if data == "dashboard:home":
        await send_dashboard(update, context)
        return

    if data == "dashboard:workspaces":
        await safe_answer(query)
        await workspace_dashboard_callback(update, context)
        return

    if data == "workspace:open_create":
        await safe_answer(query)
        await workspace_open_create_callback(update, context)
        return

    if data == "workspace:open_list":
        await safe_answer(query)
        await workspace_open_list_callback(update, context)
        return

    if data == "workspace:open_switch":
        await safe_answer(query)
        await workspace_open_switch_callback(update, context)
        return

    if data == "workspace:open_collections":
        await safe_answer(query)
        await workspace_open_collections_callback(update, context)
        return

    if data == "workspace:open_media":
        await safe_answer(query)
        await workspace_open_media_callback(update, context)
        return

    if data == "workspace:open_templates":
        await safe_answer(query)
        await workspace_open_templates_callback(update, context)
        return

    if data in {"dashboard:media", "dashboard:collections", "dashboard:templates"}:
        await safe_answer(query)
        await workspace_dashboard_callback(update, context)
        return

    if data == "dashboard:team":
        await safe_answer(query)
        await admin_menu_callback(update, context)
        return

    if data == "dashboard:posts":
        await safe_answer(query)
        await post_dashboard(update, context)
        return

    if data == "dashboard:scheduler":
        await safe_answer(query)
        await scheduler_dashboard(update, context)
        return

    if data == "dashboard:settings":
        await safe_answer(query)
        await settings_dashboard(update, context)
        return

    if data in {"dashboard:owner_system", "dashboard:owner_payments", "dashboard:owner_users", "dashboard:owner_health", "dashboard:owner_backup"}:
        await safe_answer(query)
        await owner_menu_callback(update, context)
        return

    if data == "dashboard:admin_analytics":
        await safe_answer(query)
        await admin_menu_callback(update, context)
        return

    if data == "dashboard:admin_subscription":
        await safe_answer(query)
        await subscription_command(update, context)
        return

    if data == "dashboard:editor_approval":
        await safe_answer(query)
        await editor_menu_callback(update, context)
        return

    if data == "dashboard:help":
        await safe_answer(query)
        await help_center_callback(update, context)
        return

    if data == "help:support":
        await safe_answer(query)
        await support_callback(update, context)
        return

    if data == "help:manual":
        await safe_answer(query)
        await manual_callback(update, context)
        return

    if data.startswith("help:"):
        await safe_answer(query)
        topic = data.removeprefix("help:")
        await help_topic_callback(update, context, topic)
        return

    if data == "setup:create_workspace":
        await safe_answer(query)
        await workspace_dashboard_callback(update, context)
        return

    if data == "setup:add_destination":
        await safe_answer(query)
        await channel_dashboard(update, context)
        return

    if data == "setup:create_post":
        await safe_answer(query)
        await post_dashboard(update, context)
        return

    if data == "setup:publish":
        await safe_answer(query)
        await publish_post(update, context)
        return

    if data == "setup:complete":
        await safe_answer(query)
        await send_dashboard(update, context)
        return

    if data == "commercial:copy_wallet":
        await safe_answer(query)
        await subscription_copy_wallet_callback(update, context)
        return

    if data == "commercial:verify_payment":
        await safe_answer(query)
        await subscription_verify_payment_callback(update, context)
        return

    if data == "commercial:payment_history":
        await safe_answer(query)
        await subscription_payment_history_callback(update, context)
        return

    if data == "commercial:back":
        await safe_answer(query)
        await subscription_back_callback(update, context)
        return

    if data == "settings:dashboard":
        await safe_answer(query)
        await settings_dashboard(update, context)
        return

    if data == "settings:toggle_approval":
        await safe_answer(query)
        await toggle_approval_workflow(update, context)
        return

    admin_id = _parse_callback_int(data, prefix="provision:addadmin:confirm:")
    if admin_id is not None:
        await safe_answer(query)
        await add_admin_confirm_callback(update, context, admin_id)
        return

    if data == "provision:addadmin:cancel":
        await safe_answer(query)
        await add_admin_cancel_callback(update, context)
        return

    editor_id = _parse_callback_int(data, prefix="provision:addeditor:confirm:")
    if editor_id is not None:
        await safe_answer(query)
        await add_editor_confirm_callback(update, context, editor_id)
        return

    if data == "provision:addeditor:cancel":
        await safe_answer(query)
        await add_editor_cancel_callback(update, context)
        return

    queue_id = _parse_callback_int(data, prefix="approval:preview:")
    if queue_id is not None:
        await safe_answer(query)
        await approval_preview_callback(update, context, queue_id)
        return

    queue_id = _parse_callback_int(data, prefix="approval:approve_now:")
    if queue_id is not None:
        await safe_answer(query)
        await approval_approve_now_callback(update, context, queue_id)
        return

    queue_id = _parse_callback_int(data, prefix="approval:approve_schedule:")
    if queue_id is not None:
        await safe_answer(query)
        await approval_approve_schedule_callback(update, context, queue_id)
        return

    queue_id = _parse_callback_int(data, prefix="approval:reject:")
    if queue_id is not None:
        await safe_answer(query)
        await approval_reject_callback(update, context, queue_id)
        return

    queue_id = _parse_callback_int(data, prefix="approval:edit:")
    if queue_id is not None:
        await safe_answer(query)
        await approval_edit_callback(update, context, queue_id)
        return

    workspace_id = _parse_callback_int(data, prefix="workspace:switch:")
    if workspace_id is not None:
        await safe_answer(query)
        await workspace_switch_callback(update, context, workspace_id)
        return

    workspace_id = _parse_callback_int(data, prefix="workspace:delete_yes:")
    if workspace_id is not None:
        await safe_answer(query)
        await workspace_delete_yes_callback(update, context, workspace_id)
        return

    if data == "workspace:delete_no":
        await safe_answer(query)
        await workspace_delete_no_callback(update, context)
        return

    collection_id = _parse_callback_int(data, prefix="collection:delete_yes:")
    if collection_id is not None:
        await safe_answer(query)
        await collection_delete_yes_callback(update, context, collection_id)
        return

    if data == "collection:delete_no":
        await safe_answer(query)
        await collection_delete_no_callback(update, context)
        return

    if data == "post:dashboard":
        await safe_answer(query)
        await post_dashboard(update, context)
        return

    if data == "post:text":
        await safe_answer(query)
        await text_post(update, context)
        return

    if data == "post:photo":
        await safe_answer(query)
        await photo_post(update, context)
        return

    if data == "post:gif":
        await safe_answer(query)
        await gif_post(update, context)
        return

    if data == "post:video":
        await safe_answer(query)
        await video_post(update, context)
        return

    if data == "post:document":
        await safe_answer(query)
        await document_post(update, context)
        return

    if data == "post:audio":
        await safe_answer(query)
        await audio_post(update, context)
        return

    if data == "post:voice":
        await safe_answer(query)
        await voice_post(update, context)
        return

    if data == "post:album":
        await safe_answer(query)
        await album_post(update, context)
        return

    if data == "post:preview":
        await safe_answer(query)
        await preview_post(update, context)
        return

    if data == "post:publish":
        await safe_answer(query)
        await publish_post(update, context)
        return

    if data == "post:delete":
        await safe_answer(query)
        await delete_draft(update, context)
        return

    if data == "post:edit":
        await safe_answer(query)
        await edit_draft(update, context)
        return

    channel_id = _parse_callback_int(data, prefix="post:channel:")
    if channel_id is not None:
        await safe_answer(query)
        await publish_to_channel(update, context, channel_id)
        return

    if data == "channel:dashboard":
        await safe_answer(query)
        await channel_dashboard(update, context)
        return

    if data == "channel:add":
        await safe_answer(query)
        await add_channel_menu(update, context)
        return

    if data == "channel:list":
        await safe_answer(query)
        await list_channels(update, context)
        return

    if data == "channel:default_menu":
        await safe_answer(query)
        await default_channel_menu(update, context)
        return

    if data == "channel:remove_menu":
        await safe_answer(query)
        await remove_channel_menu(update, context)
        return

    if data == "channel:refresh":
        await safe_answer(query)
        await channel_dashboard(update, context)
        return

    channel_id = _parse_callback_int(data, prefix="channel:set_default:")
    if channel_id is not None:
        await safe_answer(query)
        await set_default_channel(update, context, channel_id)
        return

    channel_id = _parse_callback_int(data, prefix="channel:remove_confirm:")
    if channel_id is not None:
        await safe_answer(query)
        await remove_channel_confirm(update, context, channel_id)
        return

    channel_id = _parse_callback_int(data, prefix="channel:remove_yes:")
    if channel_id is not None:
        await safe_answer(query)
        await remove_channel_confirm(update, context, channel_id, confirmed=True)
        return

    if data == "scheduler:schedule":
        await safe_answer(query)
        await schedule_post(update, context)
        return

    if data == "scheduler:list":
        await safe_answer(query)
        await list_schedules(update, context)
        return

    if data.startswith("scheduler:pause:"):
        await safe_answer(query)
        await pause_schedule(update, context)
        return

    if data.startswith("scheduler:resume:"):
        await safe_answer(query)
        await resume_schedule(update, context)
        return

    if data.startswith("scheduler:edit:"):
        await safe_answer(query)
        await edit_schedule(update, context)
        return

    if data.startswith("scheduler:delete:"):
        await safe_answer(query)
        await delete_schedule(update, context)
        return

    channel_id = _parse_callback_int(data, prefix="scheduler:dest:")
    if channel_id is not None:
        await safe_answer(query)
        await select_schedule_destination_callback(update, context, channel_id)
        return

    await safe_answer(query, "Unsupported action.")
