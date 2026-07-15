"""Conversation state constants for Flowza v1.0."""

from __future__ import annotations

WAITING_CHANNEL_FORWARD = "waiting_channel_forward"
WAITING_DEFAULT_CHANNEL = "waiting_default_channel"
WAITING_REMOVE_CHANNEL = "waiting_remove_channel"

WAITING_POST_TEXT = "waiting_post_text"
WAITING_POST_PHOTO = "waiting_post_photo"
WAITING_POST_PHOTO_CAPTION = "waiting_post_photo_caption"
WAITING_POST_GIF = "waiting_post_gif"
WAITING_POST_GIF_CAPTION = "waiting_post_gif_caption"
WAITING_POST_VIDEO = "waiting_post_video"
WAITING_POST_VIDEO_CAPTION = "waiting_post_video_caption"
WAITING_POST_DOCUMENT = "waiting_post_document"
WAITING_POST_DOCUMENT_CAPTION = "waiting_post_document_caption"
WAITING_POST_ALBUM = "waiting_post_album"
WAITING_POST_PREVIEW = "waiting_post_preview"

WAITING_SCHEDULE_DATE = "waiting_schedule_date"
WAITING_SCHEDULE_TIME = "waiting_schedule_time"
WAITING_SCHEDULE_TYPE = "waiting_schedule_type"
WAITING_SCHEDULE_INTERVAL = "waiting_schedule_interval"
WAITING_SCHEDULE_CONFIRM = "waiting_schedule_confirm"

WAITING_ADMIN_FORWARD = "waiting_admin_forward"
WAITING_EDITOR_FORWARD = "waiting_editor_forward"
WAITING_EDITOR_WORKSPACE = "waiting_editor_workspace"
WAITING_EDITOR_DESTINATIONS = "waiting_editor_destinations"
WAITING_APPROVAL_REJECT_REASON = "waiting_approval_reject_reason"
WAITING_MEDIA_UPLOAD = "waiting_media_upload"
WAITING_WORKSPACE_NAME = "waiting_workspace_name"

WAITING_TEXT = WAITING_POST_TEXT
WAITING_PHOTO = WAITING_POST_PHOTO
WAITING_GIF = WAITING_POST_GIF
WAITING_VIDEO = WAITING_POST_VIDEO
WAITING_DOCUMENT = WAITING_POST_DOCUMENT
WAITING_ALBUM = WAITING_POST_ALBUM
WAITING_PREVIEW = WAITING_POST_PREVIEW
