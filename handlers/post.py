"""Post composer and publishing handlers for Flowza v1.0."""

from __future__ import annotations

import json

from telegram import InputMediaPhoto, InputMediaVideo, Update
from telegram.ext import ContextTypes

from database.channels import get_channels, get_default_channel
from database.approval import cancel_for_draft, mark_published_for_draft
from database.enterprise import create_notification, log_audit, record_publish
from database.drafts import (
    delete,
    get_latest,
    save_album,
    save_animation,
    save_document,
    save_photo,
    save_text,
    save_video,
    update_draft,
)
from keyboards.post import build_post_keyboard, build_preview_keyboard, build_publish_keyboard
from states import (
    WAITING_POST_ALBUM,
    WAITING_POST_DOCUMENT,
    WAITING_POST_DOCUMENT_CAPTION,
    WAITING_POST_GIF,
    WAITING_POST_GIF_CAPTION,
    WAITING_POST_PHOTO,
    WAITING_POST_PHOTO_CAPTION,
    WAITING_POST_PREVIEW,
    WAITING_POST_TEXT,
    WAITING_POST_VIDEO,
    WAITING_POST_VIDEO_CAPTION,
)
from utils.logger import get_logger
from utils.permissions import can_compose_content, can_publish_content
from utils.telegram_safety import duplicate_guard, safe_answer, safe_edit_message

logger = get_logger(__name__)


async def _send_or_edit(update: Update, text: str, keyboard=None, answer_text: str | None = None) -> None:
    """Reply to a normal message or edit a callback message."""
    query = update.callback_query
    if query is not None:
        await safe_answer(query, answer_text)
        await safe_edit_message(query, text, reply_markup=keyboard)
        return

    if update.effective_message is not None:
        await update.effective_message.reply_text(text, reply_markup=keyboard)


async def _finalize_draft(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    draft_type: str,
    text: str | None = None,
    file_id: str | None = None,
    caption: str | None = None,
    album: list[dict[str, str]] | None = None,
    success_message: str,
    logger_message: str,
) -> None:
    """Persist a draft, store the draft id, and move to preview."""
    draft_id = context.user_data.get("draft_id")
    if draft_id is not None:
        await update_draft(int(draft_id), draft_type=draft_type, text=text, file_id=file_id, caption=caption, album=json.dumps(album) if album is not None else None)
    else:
        if draft_type == "text":
            draft = await save_text(text or "")
        elif draft_type == "photo":
            draft = await save_photo(file_id or "", caption or None)
        elif draft_type == "gif":
            draft = await save_animation(file_id or "", caption or None)
        elif draft_type == "video":
            draft = await save_video(file_id or "", caption or None)
        elif draft_type == "document":
            draft = await save_document(file_id or "", caption or None)
        elif draft_type == "album":
            draft = await save_album([item["media"] for item in album or []], caption or None)
        else:
            draft = None
        draft_id = draft["id"] if draft else None

    context.user_data["post_state"] = WAITING_POST_PREVIEW
    context.user_data["draft_id"] = draft_id
    await update.effective_message.reply_text(success_message, reply_markup=build_preview_keyboard())
    logger.info(logger_message)


async def post_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the post composer dashboard."""
    if not await can_compose_content(update):
        await _send_or_edit(update, "🚫 You do not have access to the post composer.", answer_text="Access denied")
        return

    text = "📝 Post Composer\n\nChoose a content type to start composing."
    await _send_or_edit(update, text, keyboard=build_post_keyboard())


async def text_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a text post draft."""
    if not await can_compose_content(update):
        await _send_or_edit(update, "🚫 You do not have permission to create drafts.", answer_text="Access denied")
        return

    context.user_data["post_state"] = WAITING_POST_TEXT
    await _send_or_edit(update, "📝 Send the text you want to publish.", keyboard=build_post_keyboard())


async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Store or update a text draft and move to preview."""
    message = update.effective_message
    if message is None:
        return

    text = message.text or ""
    if not text.strip():
        await message.reply_text("❌ Please send non-empty text.")
        return

    await _finalize_draft(
        update,
        context,
        draft_type="text",
        text=text,
        success_message=f"📝 Draft ready.\n\n{text}\n\nTap preview to review it.",
        logger_message="Draft created or updated for text post",
    )


async def photo_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a photo post draft."""
    if not await can_compose_content(update):
        await _send_or_edit(update, "🚫 You do not have permission to create drafts.", answer_text="Access denied")
        return

    context.user_data["post_state"] = WAITING_POST_PHOTO
    await _send_or_edit(update, "🖼 Send a photo to create a post draft.", keyboard=build_post_keyboard())


async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Store a photo file id and ask for an optional caption."""
    message = update.effective_message
    if message is None:
        return

    post_state = context.user_data.get("post_state")
    if post_state == WAITING_POST_PHOTO and message.photo:
        photo = message.photo[-1]
        context.user_data["pending_file_id"] = photo.file_id
        context.user_data["post_state"] = WAITING_POST_PHOTO_CAPTION
        await message.reply_text("🖼 Photo stored. Send an optional caption, or tap preview to continue.", reply_markup=build_post_keyboard())
        return

    if post_state == WAITING_POST_PHOTO_CAPTION:
        caption = message.text or message.caption or ""
        file_id = context.user_data.get("pending_file_id")
        if not file_id:
            await message.reply_text("❌ No photo was stored yet.")
            return
        await _finalize_draft(
            update,
            context,
            draft_type="photo",
            file_id=str(file_id),
            caption=caption.strip() or None,
            success_message="🖼 Photo draft created. Preview it before publishing.",
            logger_message="Draft created or updated for photo post",
        )
        context.user_data.pop("pending_file_id", None)
        return

    await message.reply_text("❌ Please send a valid photo.")


async def gif_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a GIF post draft."""
    if not await can_compose_content(update):
        await _send_or_edit(update, "🚫 You do not have permission to create drafts.", answer_text="Access denied")
        return

    context.user_data["post_state"] = WAITING_POST_GIF
    await _send_or_edit(update, "🎞 Send a GIF or animation to create a post draft.", keyboard=build_post_keyboard())


async def receive_animation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Store an animation file id and ask for an optional caption."""
    message = update.effective_message
    if message is None:
        return

    post_state = context.user_data.get("post_state")
    if post_state == WAITING_POST_GIF and message.animation:
        animation = message.animation
        context.user_data["pending_file_id"] = animation.file_id
        context.user_data["post_state"] = WAITING_POST_GIF_CAPTION
        await message.reply_text("🎞 GIF stored. Send an optional caption, or tap preview to continue.", reply_markup=build_post_keyboard())
        return

    if post_state == WAITING_POST_GIF_CAPTION:
        caption = message.text or message.caption or ""
        file_id = context.user_data.get("pending_file_id")
        if not file_id:
            await message.reply_text("❌ No GIF was stored yet.")
            return
        await _finalize_draft(
            update,
            context,
            draft_type="gif",
            file_id=str(file_id),
            caption=caption.strip() or None,
            success_message="🎞 GIF draft created. Preview it before publishing.",
            logger_message="Draft created or updated for animation post",
        )
        context.user_data.pop("pending_file_id", None)
        return

    await message.reply_text("❌ Please send a valid GIF/animation.")


async def video_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a video post draft."""
    if not await can_compose_content(update):
        await _send_or_edit(update, "🚫 You do not have permission to create drafts.", answer_text="Access denied")
        return

    context.user_data["post_state"] = WAITING_POST_VIDEO
    await _send_or_edit(update, "🎥 Send a video to create a post draft.", keyboard=build_post_keyboard())


async def receive_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Store a video file id and ask for an optional caption."""
    message = update.effective_message
    if message is None:
        return

    post_state = context.user_data.get("post_state")
    if post_state == WAITING_POST_VIDEO and message.video:
        video = message.video
        context.user_data["pending_file_id"] = video.file_id
        context.user_data["post_state"] = WAITING_POST_VIDEO_CAPTION
        await message.reply_text("🎥 Video stored. Send an optional caption, or tap preview to continue.", reply_markup=build_post_keyboard())
        return

    if post_state == WAITING_POST_VIDEO_CAPTION:
        caption = message.text or message.caption or ""
        file_id = context.user_data.get("pending_file_id")
        if not file_id:
            await message.reply_text("❌ No video was stored yet.")
            return
        await _finalize_draft(
            update,
            context,
            draft_type="video",
            file_id=str(file_id),
            caption=caption.strip() or None,
            success_message="🎥 Video draft created. Preview it before publishing.",
            logger_message="Draft created or updated for video post",
        )
        context.user_data.pop("pending_file_id", None)
        return

    await message.reply_text("❌ Please send a valid video.")


async def document_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a document post draft."""
    if not await can_compose_content(update):
        await _send_or_edit(update, "🚫 You do not have permission to create drafts.", answer_text="Access denied")
        return

    context.user_data["post_state"] = WAITING_POST_DOCUMENT
    await _send_or_edit(update, "📄 Send a document to create a post draft.", keyboard=build_post_keyboard())


async def receive_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Store a document file id and ask for an optional caption."""
    message = update.effective_message
    if message is None:
        return

    post_state = context.user_data.get("post_state")
    if post_state == WAITING_POST_DOCUMENT and message.document:
        document = message.document
        context.user_data["pending_file_id"] = document.file_id
        context.user_data["post_state"] = WAITING_POST_DOCUMENT_CAPTION
        await message.reply_text("📄 Document stored. Send an optional caption, or tap preview to continue.", reply_markup=build_post_keyboard())
        return

    if post_state == WAITING_POST_DOCUMENT_CAPTION:
        caption = message.text or message.caption or ""
        file_id = context.user_data.get("pending_file_id")
        if not file_id:
            await message.reply_text("❌ No document was stored yet.")
            return
        await _finalize_draft(
            update,
            context,
            draft_type="document",
            file_id=str(file_id),
            caption=caption.strip() or None,
            success_message="📄 Document draft created. Preview it before publishing.",
            logger_message="Draft created or updated for document post",
        )
        context.user_data.pop("pending_file_id", None)
        return

    await message.reply_text("❌ Please send a valid document.")


async def album_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start an album post draft."""
    if not await can_compose_content(update):
        await _send_or_edit(update, "🚫 You do not have permission to create drafts.", answer_text="Access denied")
        return

    context.user_data["post_state"] = WAITING_POST_ALBUM
    context.user_data["pending_album_items"] = []
    context.user_data.pop("pending_album_caption", None)
    await _send_or_edit(update, "🖼 Send a media group (album) with at least two items.", keyboard=build_post_keyboard())


async def receive_album(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Collect a media-group album and finalize it once the group is complete."""
    message = update.effective_message
    if message is None:
        return

    media_group_id = getattr(message, "media_group_id", None)
    pending_items = context.user_data.setdefault("pending_album_items", [])
    if media_group_id:
        if getattr(message, "photo", None):
            pending_items.append({"type": "photo", "media": message.photo[-1].file_id})
        elif getattr(message, "video", None):
            pending_items.append({"type": "video", "media": message.video.file_id})
        elif getattr(message, "animation", None):
            pending_items.append({"type": "animation", "media": message.animation.file_id})
        else:
            await message.reply_text("❌ Unsupported album contents.")
            return

        if message.caption:
            context.user_data["pending_album_caption"] = message.caption.strip() or None

        await message.reply_text(
            f"🖼 Added media item #{len(pending_items)} to the album. Send the next item or a final text/caption to complete it.",
            reply_markup=build_post_keyboard(),
        )
        return

    if not pending_items:
        await message.reply_text("❌ Please send a media group (album) with at least two items.")
        return

    caption = context.user_data.get("pending_album_caption") or (message.caption or "")
    await _finalize_draft(
        update,
        context,
        draft_type="album",
        album=pending_items,
        caption=caption.strip() or None,
        success_message="🖼 Album draft created. Preview it before publishing.",
        logger_message="Draft created or updated for album post",
    )
    context.user_data.pop("pending_album_items", None)
    context.user_data.pop("pending_album_caption", None)


async def preview_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show a preview of the latest draft."""
    draft = await get_latest()
    if not draft:
        await _send_or_edit(update, "No draft found.", keyboard=build_post_keyboard())
        return

    summary = f"🧾 Draft Preview\n\nType: {draft.get('draft_type') or 'unknown'}"
    if draft.get("text"):
        summary += f"\n\nText:\n{draft['text']}"
    if draft.get("caption"):
        summary += f"\n\nCaption:\n{draft['caption']}"
    if draft.get("album"):
        summary += "\n\nAlbum media collected."
    await _send_or_edit(update, summary, keyboard=build_preview_keyboard())


async def edit_draft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Restart the composer flow for the current draft type."""
    draft = await get_latest()
    if not draft:
        await _send_or_edit(update, "No draft found to edit.", keyboard=build_post_keyboard())
        return

    draft_type = draft.get("draft_type")
    if draft_type == "text":
        await text_post(update, context)
    elif draft_type == "photo":
        await photo_post(update, context)
    elif draft_type == "gif":
        await gif_post(update, context)
    elif draft_type == "video":
        await video_post(update, context)
    elif draft_type == "document":
        await document_post(update, context)
    elif draft_type == "album":
        await album_post(update, context)
    else:
        await post_dashboard(update, context)


async def publish_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start the publish flow by selecting a target channel."""
    if not await can_publish_content(update):
        await _send_or_edit(
            update,
            "🚫 You cannot publish right now. Approval may be required by your Admin.",
            answer_text="Access denied",
        )
        return

    draft = await get_latest()
    if not draft:
        await _send_or_edit(update, "❌ No draft available to publish.", keyboard=build_post_keyboard())
        return

    if not draft.get("draft_type"):
        await _send_or_edit(update, "❌ Draft is empty or invalid.", keyboard=build_post_keyboard())
        return

    channels = await get_channels()
    if not channels:
        await _send_or_edit(update, "❌ No channels available for publishing.", keyboard=build_post_keyboard())
        return

    default_channel = await get_default_channel()
    if default_channel is not None:
        await publish_to_channel(update, context, int(default_channel["channel_id"]))
        return

    if len(channels) == 1:
        await publish_to_channel(update, context, int(channels[0]["channel_id"]))
        return

    await _send_or_edit(update, "🚀 Select a channel to publish to.", keyboard=build_publish_keyboard([int(channel["channel_id"]) for channel in channels]))


async def publish_to_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, channel_id: int) -> None:
    """Publish the current draft to the selected channel using Telegram file ids."""
    if not await can_publish_content(update):
        await _send_or_edit(
            update,
            "🚫 You cannot publish right now. Approval may be required by your Admin.",
            answer_text="Access denied",
        )
        return

    draft = await get_latest()
    if not draft:
        await _send_or_edit(update, "❌ No draft available to publish.", keyboard=build_post_keyboard())
        return

    actor_id = int(update.effective_user.id) if update.effective_user else 0
    draft_id = int(draft.get("id") or 0)
    dedupe_key = f"publish:{actor_id}:{draft_id}:{int(channel_id)}"
    if duplicate_guard(context.application.bot_data, dedupe_key, ttl_seconds=8):
        await _send_or_edit(update, "ℹ Publish already in progress or just completed.", keyboard=build_post_keyboard())
        return

    try:
        if draft.get("draft_type") == "text":
            await context.bot.send_message(
                chat_id=channel_id,
                text=draft.get("text") or "",
                parse_mode=draft.get("parse_mode") or "HTML",
            )
        elif draft.get("draft_type") == "photo":
            await context.bot.send_photo(
                chat_id=channel_id,
                photo=draft.get("file_id"),
                caption=draft.get("caption"),
                parse_mode=draft.get("parse_mode") or "HTML",
            )
        elif draft.get("draft_type") == "gif":
            await context.bot.send_animation(
                chat_id=channel_id,
                animation=draft.get("file_id"),
                caption=draft.get("caption"),
                parse_mode=draft.get("parse_mode") or "HTML",
            )
        elif draft.get("draft_type") == "video":
            await context.bot.send_video(
                chat_id=channel_id,
                video=draft.get("file_id"),
                caption=draft.get("caption"),
                parse_mode=draft.get("parse_mode") or "HTML",
            )
        elif draft.get("draft_type") == "document":
            await context.bot.send_document(
                chat_id=channel_id,
                document=draft.get("file_id"),
                caption=draft.get("caption"),
                parse_mode=draft.get("parse_mode") or "HTML",
            )
        elif draft.get("draft_type") == "album":
            album_items = json.loads(draft.get("album") or "[]")
            if not album_items:
                raise ValueError("Album draft is empty")
            media = []
            caption = draft.get("caption") or None
            for index, item in enumerate(album_items):
                media_type = item.get("type", "photo")
                if media_type == "video":
                    media.append(
                        InputMediaVideo(
                            media=item.get("media", ""),
                            caption=caption if index == 0 else None,
                            parse_mode=draft.get("parse_mode") or "HTML",
                        )
                    )
                else:
                    media.append(
                        InputMediaPhoto(
                            media=item.get("media", ""),
                            caption=caption if index == 0 else None,
                            parse_mode=draft.get("parse_mode") or "HTML",
                        )
                    )
            await context.bot.send_media_group(chat_id=channel_id, media=media)
        else:
            raise ValueError("Unsupported draft type")

        logger.info("Published successfully to channel %s", channel_id)
        await record_publish(
            draft_id=int(draft.get("id") or 0),
            channel_id=int(channel_id),
            workspace_id=None,
            collection_id=None,
            editor_id=actor_id or None,
            published_via="manual",
            status="published",
        )
        await log_audit(
            actor_id=actor_id or None,
            actor_role="publisher",
            action="publish_success",
            module="post",
            target_type="channel",
            target_id=str(channel_id),
        )
        if draft.get("id"):
            queue_rows = await mark_published_for_draft(int(draft["id"]), channel_id)
            for row in queue_rows:
                editor_id = row.get("editor_id")
                if editor_id:
                    try:
                        await context.bot.send_message(
                            chat_id=int(editor_id),
                            text=f"✅ Draft published successfully. Queue #{row.get('id')}",
                        )
                    except Exception:
                        logger.warning("Could not notify editor %s about published queue %s", editor_id, row.get("id"))
        await _send_or_edit(update, "🚀 Post published successfully.", keyboard=build_post_keyboard())
    except Exception as exc:
        logger.exception("Publish failed for channel %s: %s", channel_id, exc)
        await record_publish(
            draft_id=int(draft.get("id") or 0),
            channel_id=int(channel_id),
            workspace_id=None,
            collection_id=None,
            editor_id=actor_id or None,
            published_via="manual",
            status="failed",
            error_message=str(exc),
        )
        if update.effective_user is not None:
            await create_notification(
                int(update.effective_user.id),
                "publisher",
                "publish",
                "Publish failed",
                f"Publishing to channel {channel_id} failed: {exc}",
            )
        await _send_or_edit(update, "❌ Publish failed. Please try again.", keyboard=build_post_keyboard())


async def delete_draft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete the latest draft and reset the composer state."""
    draft = await get_latest()
    if draft:
        await cancel_for_draft(int(draft["id"]))
        await delete(draft["id"])
    context.user_data.pop("draft_id", None)
    context.user_data.pop("post_state", None)
    context.user_data.pop("pending_file_id", None)
    await _send_or_edit(update, "🗑 Draft deleted.", keyboard=build_post_keyboard())
    logger.info("Draft deleted")
