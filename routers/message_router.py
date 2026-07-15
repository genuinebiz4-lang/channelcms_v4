"""Message routing for Flowza v1.0."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from handlers.channel import receive_channel
from handlers.post import (
    receive_album,
    receive_animation,
    receive_audio_voice_sticker,
    receive_document,
    receive_photo,
    receive_text,
    receive_video,
)
from handlers.approval import approval_reject_reason_message
from handlers.provisioning import (
    receive_admin_forward,
    receive_editor_destinations,
    receive_editor_forward,
    receive_editor_workspace,
)
from handlers.workspace import receive_media_upload, receive_workspace_name
from handlers.scheduler import (
    confirm_schedule,
    receive_date,
    receive_interval,
    receive_schedule_type,
    receive_time,
)
from states import (
    WAITING_ALBUM,
    WAITING_CHANNEL_FORWARD,
    WAITING_DOCUMENT,
    WAITING_EDITOR_DESTINATIONS,
    WAITING_EDITOR_FORWARD,
    WAITING_EDITOR_WORKSPACE,
    WAITING_GIF,
    WAITING_PHOTO,
    WAITING_POST_ALBUM,
    WAITING_POST_AUDIO,
    WAITING_POST_DOCUMENT,
    WAITING_POST_DOCUMENT_CAPTION,
    WAITING_POST_GIF,
    WAITING_POST_GIF_CAPTION,
    WAITING_POST_PHOTO,
    WAITING_POST_PHOTO_CAPTION,
    WAITING_POST_TEXT,
    WAITING_POST_VIDEO,
    WAITING_POST_VIDEO_CAPTION,
    WAITING_POST_VOICE,
    WAITING_SCHEDULE_CONFIRM,
    WAITING_SCHEDULE_DATE,
    WAITING_SCHEDULE_INTERVAL,
    WAITING_SCHEDULE_TIME,
    WAITING_SCHEDULE_TYPE,
    WAITING_ADMIN_FORWARD,
    WAITING_APPROVAL_REJECT_REASON,
    WAITING_MEDIA_UPLOAD,
    WAITING_WORKSPACE_NAME,
    WAITING_TEXT,
    WAITING_VIDEO,
)
from utils.logger import get_logger

logger = get_logger(__name__)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle general incoming messages and channel-forward flows."""
    if update.effective_message is None:
        return

    if context.user_data.get("channel_state") == WAITING_CHANNEL_FORWARD:
        await receive_channel(update, context)
        return

    provision_state = context.user_data.get("provision_state")
    if provision_state == WAITING_ADMIN_FORWARD:
        await receive_admin_forward(update, context)
        return
    if provision_state == WAITING_EDITOR_FORWARD:
        await receive_editor_forward(update, context)
        return
    if provision_state == WAITING_EDITOR_WORKSPACE:
        await receive_editor_workspace(update, context)
        return
    if provision_state == WAITING_EDITOR_DESTINATIONS:
        await receive_editor_destinations(update, context)
        return

    if context.user_data.get("approval_state") == WAITING_APPROVAL_REJECT_REASON:
        await approval_reject_reason_message(update, context)
        return

    if context.user_data.get("workspace_state") == WAITING_MEDIA_UPLOAD:
        await receive_media_upload(update, context)
        return
    if context.user_data.get("workspace_state") == WAITING_WORKSPACE_NAME:
        await receive_workspace_name(update, context)
        return

    post_state = context.user_data.get("post_state")
    if post_state in {
        WAITING_POST_TEXT,
        WAITING_TEXT,
        WAITING_POST_PHOTO,
        WAITING_POST_PHOTO_CAPTION,
        WAITING_PHOTO,
        WAITING_POST_GIF,
        WAITING_POST_GIF_CAPTION,
        WAITING_GIF,
        WAITING_POST_VIDEO,
        WAITING_POST_VIDEO_CAPTION,
        WAITING_VIDEO,
        WAITING_POST_DOCUMENT,
        WAITING_POST_DOCUMENT_CAPTION,
        WAITING_DOCUMENT,
        WAITING_POST_ALBUM,
        WAITING_ALBUM,
        WAITING_POST_AUDIO,
        WAITING_POST_VOICE,
    }:
        handled = await receive_audio_voice_sticker(update, context)
        if handled:
            return

    if post_state in {WAITING_POST_TEXT, WAITING_TEXT}:
        await receive_text(update, context)
        return
    if post_state in {WAITING_POST_PHOTO, WAITING_POST_PHOTO_CAPTION, WAITING_PHOTO}:
        await receive_photo(update, context)
        return
    if post_state in {WAITING_POST_GIF, WAITING_POST_GIF_CAPTION, WAITING_GIF}:
        await receive_animation(update, context)
        return
    if post_state in {WAITING_POST_VIDEO, WAITING_POST_VIDEO_CAPTION, WAITING_VIDEO}:
        await receive_video(update, context)
        return
    if post_state in {WAITING_POST_DOCUMENT, WAITING_POST_DOCUMENT_CAPTION, WAITING_DOCUMENT}:
        await receive_document(update, context)
        return
    if post_state in {WAITING_POST_ALBUM, WAITING_ALBUM}:
        await receive_album(update, context)
        return
    if post_state in {WAITING_POST_AUDIO, WAITING_POST_VOICE}:
        await update.effective_message.reply_text("❌ Please send the requested media type.")
        return

    if post_state == WAITING_SCHEDULE_DATE:
        await receive_date(update, context)
        return
    if post_state == WAITING_SCHEDULE_TIME:
        await receive_time(update, context)
        return
    if post_state == WAITING_SCHEDULE_TYPE:
        await receive_schedule_type(update, context)
        return
    if post_state == WAITING_SCHEDULE_INTERVAL:
        await receive_interval(update, context)
        return
    if post_state == WAITING_SCHEDULE_CONFIRM:
        await confirm_schedule(update, context)
        return

    text = update.effective_message.text or ""
    if text.startswith("/"):
        return

    await update.effective_message.reply_text(
        "💬 Thanks for your message. Flowza v1.0 is ready for future features."
    )
    logger.info("Handled plain text message from %s", update.effective_user.id)
