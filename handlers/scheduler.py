"""Scheduler and auto-posting handlers for Flowza v1.0."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from telegram import InputMediaPhoto, InputMediaVideo, Update
from telegram.error import RetryAfter
from telegram.ext import ContextTypes

from config import OWNER_ID, TIMEZONE
from database.approval import mark_published_for_draft
from database.channels import get_channel, get_channels, get_default_channel
from database.drafts import get_draft, get_latest
from database.enterprise import (
    create_notification,
    detect_schedule_conflict,
    enqueue_retry,
    get_due_retries,
    get_retry_statistics,
    get_workspace_timezone,
    log_audit,
    mark_retry_state,
    record_publish,
)
from database.scheduler import (
    add_schedule,
    delete_schedule as delete_schedule_db,
    get_all_schedules,
    get_pending,
    get_schedule,
    pause_schedule as pause_schedule_db,
    resume_schedule as resume_schedule_db,
    update_schedule,
)
from database.settings import get_admin_for_user
from database.workspace import get_current_workspace
from handlers.commercial import run_daily_commercial_jobs, run_scheduled_backup
from keyboards.scheduler import build_schedule_actions_keyboard, build_scheduler_keyboard
from states import (
    WAITING_SCHEDULE_CONFIRM,
    WAITING_SCHEDULE_DATE,
    WAITING_SCHEDULE_INTERVAL,
    WAITING_SCHEDULE_TIME,
    WAITING_SCHEDULE_TYPE,
)
from utils.logger import get_logger
from utils.permissions import can_manage_schedule

logger = get_logger(__name__)

scheduler = AsyncIOScheduler(timezone=TIMEZONE)
bot_app: Any | None = None


async def _send_or_edit(update: Update, text: str, keyboard=None, answer_text: str | None = None) -> None:
    """Reply to a normal message or edit a callback message."""
    query = update.callback_query
    if query is not None:
        await query.answer(answer_text or "")
        await query.edit_message_text(text, reply_markup=keyboard)
        return

    if update.effective_message is not None:
        await update.effective_message.reply_text(text, reply_markup=keyboard)


def _parse_date(value: str) -> datetime | None:
    """Parse an accepted date format."""
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def _parse_time(value: str) -> datetime | None:
    """Parse an accepted time format."""
    try:
        return datetime.strptime(value.strip(), "%H:%M")
    except ValueError:
        return None


def initialize_scheduler(application: Any | None = None) -> None:
    """Initialize the scheduler and attach the bot application."""
    global bot_app
    if application is not None:
        bot_app = application
    if not scheduler.running:
        try:
            scheduler.start()
            scheduler.add_job(process_retry_queue, trigger=IntervalTrigger(seconds=30), id="retry_queue_worker", replace_existing=True)
            scheduler.add_job(restore_pending_schedules, trigger=DateTrigger(run_date=datetime.now() + timedelta(seconds=2)), id="schedule_restore_worker", replace_existing=True)
            scheduler.add_job(run_daily_jobs, trigger=CronTrigger(hour=0, minute=15), id="daily_commercial_worker", replace_existing=True)
            scheduler.add_job(run_daily_backup_job, trigger=CronTrigger(hour=1, minute=0), id="daily_backup_worker", replace_existing=True)
            scheduler.add_job(run_weekly_backup_job, trigger=CronTrigger(day_of_week="sun", hour=2, minute=0), id="weekly_backup_worker", replace_existing=True)
        except RuntimeError:
            # run_polling creates the event loop later; retry lazily on first schedule action
            logger.info("Scheduler start deferred until an active event loop is available")


def shutdown_scheduler() -> None:
    """Stop the scheduler cleanly."""
    if scheduler.running:
        scheduler.shutdown(wait=False)


async def scheduler_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the scheduler dashboard."""
    if not await can_manage_schedule(update):
        await _send_or_edit(update, "🚫 You do not have access to scheduling.", answer_text="Access denied")
        return

    text = "⏰ Scheduler\n\nManage one-time and recurring auto-posts."
    await _send_or_edit(update, text, keyboard=build_scheduler_keyboard())


async def schedule_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start the scheduling workflow."""
    if not await can_manage_schedule(update):
        await _send_or_edit(update, "🚫 You do not have permission to schedule posts.", answer_text="Access denied")
        return

    draft = await get_latest()
    if not draft:
        await _send_or_edit(update, "❌ Create a draft before scheduling it.", keyboard=build_scheduler_keyboard())
        return

    context.user_data["schedule_draft_id"] = draft["id"]
    context.user_data["post_state"] = WAITING_SCHEDULE_DATE
    await _send_or_edit(update, "📅 Send the schedule date (DD-MM-YYYY or YYYY-MM-DD).", keyboard=build_scheduler_keyboard())


async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Receive the chosen date for a schedule."""
    message = update.effective_message
    if message is None:
        return

    parsed = _parse_date(message.text or "")
    if parsed is None:
        await message.reply_text("❌ Invalid date. Use DD-MM-YYYY or YYYY-MM-DD.")
        return

    if parsed.date() < datetime.now().date():
        await message.reply_text("❌ Date cannot be in the past.")
        return

    context.user_data["schedule_date"] = parsed.strftime("%Y-%m-%d")
    context.user_data["post_state"] = WAITING_SCHEDULE_TIME
    await message.reply_text("🕒 Send the schedule time in HH:MM format.", reply_markup=build_scheduler_keyboard())


async def receive_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Receive the chosen time for a schedule."""
    message = update.effective_message
    if message is None:
        return

    parsed = _parse_time(message.text or "")
    if parsed is None:
        await message.reply_text("❌ Invalid time. Use HH:MM (24-hour).")
        return

    selected_date = context.user_data.get("schedule_date")
    selected_time = parsed.strftime("%H:%M")
    if selected_date:
        combined = datetime.strptime(f"{selected_date} {selected_time}", "%Y-%m-%d %H:%M")
        if combined < datetime.now():
            await message.reply_text("❌ Schedule time cannot be in the past.")
            return
    context.user_data["schedule_time"] = selected_time
    context.user_data["post_state"] = WAITING_SCHEDULE_TYPE
    await message.reply_text(
        "📆 Choose the schedule type:\n\n1. One Time\n2. Daily\n3. Weekly\n4. Monthly\n5. Yearly\n6. Every X Minutes\n7. Every X Hours",
        reply_markup=build_scheduler_keyboard(),
    )


async def receive_schedule_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Capture the selected schedule type and interval if needed."""
    message = update.effective_message
    if message is None:
        return

    text = (message.text or "").strip().lower()
    types = {
        "1": "one_time",
        "one time": "one_time",
        "2": "daily",
        "daily": "daily",
        "3": "weekly",
        "weekly": "weekly",
        "4": "monthly",
        "monthly": "monthly",
        "5": "yearly",
        "yearly": "yearly",
        "6": "interval_minutes",
        "every x minutes": "interval_minutes",
        "7": "interval_hours",
        "every x hours": "interval_hours",
    }
    schedule_type = types.get(text)
    if schedule_type is None:
        await message.reply_text("❌ Unsupported schedule type.")
        return

    context.user_data["schedule_type"] = schedule_type
    if schedule_type in {"interval_minutes", "interval_hours"}:
        context.user_data["post_state"] = WAITING_SCHEDULE_INTERVAL
        await message.reply_text("🔁 Send the interval value (for example 5 or 3).", reply_markup=build_scheduler_keyboard())
        return

    context.user_data["post_state"] = WAITING_SCHEDULE_CONFIRM
    await confirm_schedule(update, context)


async def receive_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Capture an interval value for recurring scheduling."""
    message = update.effective_message
    if message is None:
        return

    try:
        value = int((message.text or "").strip())
    except ValueError:
        await message.reply_text("❌ Interval must be a number.")
        return

    if value <= 0:
        await message.reply_text("❌ Interval must be greater than zero.")
        return

    context.user_data["schedule_interval"] = value
    context.user_data["post_state"] = WAITING_SCHEDULE_CONFIRM
    await confirm_schedule(update, context)


async def confirm_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Confirm the scheduled post details and save it."""
    message = update.effective_message
    if message is None:
        return

    draft_id = context.user_data.get("schedule_draft_id")
    channel_id = context.user_data.get("schedule_channel_id")
    if not draft_id:
        await message.reply_text("❌ Missing draft. Start the scheduler again.")
        return

    schedule_type = context.user_data.get("schedule_type")
    schedule_date = context.user_data.get("schedule_date")
    schedule_time = context.user_data.get("schedule_time")
    if not schedule_type or not schedule_date or not schedule_time:
        await message.reply_text("❌ Missing schedule details.")
        return

    draft = await get_draft(int(draft_id))
    if not draft:
        await message.reply_text("❌ Missing draft. Start the scheduler again.")
        return

    channels = await get_channels()
    if not channels:
        await message.reply_text("❌ No channel exists for scheduling.")
        return

    if channel_id is None:
        default_channel = await get_default_channel()
        if default_channel is not None:
            channel_id = int(default_channel["channel_id"])
        else:
            channel_id = int(channels[0]["channel_id"])
        context.user_data["schedule_channel_id"] = channel_id

    cron_expression = None
    if schedule_type == "daily":
        minute, hour = schedule_time.split(":")
        cron_expression = f"{minute} {hour} * * *"
    elif schedule_type == "weekly":
        minute, hour = schedule_time.split(":")
        cron_expression = f"{minute} {hour} * * 1"
    elif schedule_type == "monthly":
        minute, hour = schedule_time.split(":")
        cron_expression = f"{minute} {hour} 1 * *"
    elif schedule_type == "yearly":
        minute, hour = schedule_time.split(":")
        cron_expression = f"{minute} {hour} 1 1 *"
    elif schedule_type == "interval_minutes":
        cron_expression = f"every:{context.user_data.get('schedule_interval', 5)}m"
    elif schedule_type == "interval_hours":
        cron_expression = f"every:{context.user_data.get('schedule_interval', 1)}h"

    next_run = f"{schedule_date} {schedule_time}"
    conflict_ids = await detect_schedule_conflict(int(channel_id), schedule_date, schedule_time)
    if conflict_ids:
        await message.reply_text(
            f"⚠ Schedule conflict detected with schedule IDs: {', '.join(str(i) for i in conflict_ids)}. Saving anyway with lower priority."
        )

    user = update.effective_user
    admin_id = await get_admin_for_user(user.id) if user else None
    workspace_id = None
    timezone_name = TIMEZONE
    if user and admin_id is not None:
        ws = await get_current_workspace(user.id, int(admin_id))
        if ws is not None:
            workspace_id = int(ws["workspace_id"])
            timezone_name = await get_workspace_timezone(workspace_id, TIMEZONE)

    schedule = await add_schedule(
        draft_id=int(draft_id),
        channel_id=int(channel_id),
        schedule_type=schedule_type,
        schedule_date=schedule_date,
        schedule_time=schedule_time,
        cron_expression=cron_expression,
        timezone=timezone_name,
        status="pending",
        next_run=next_run,
    )
    if not schedule:
        await message.reply_text("❌ Failed to save the schedule.")
        return

    _schedule_job(schedule)
    await log_audit(
        actor_id=int(user.id) if user else None,
        actor_role="scheduler_user",
        action="schedule_created",
        module="scheduler",
        target_type="schedule",
        target_id=str(schedule.get("id")),
        metadata_json=json.dumps({"workspace_id": workspace_id, "conflicts": conflict_ids}),
    )
    logger.info("Schedule created for draft %s", draft_id)
    context.user_data.pop("schedule_draft_id", None)
    context.user_data.pop("schedule_date", None)
    context.user_data.pop("schedule_time", None)
    context.user_data.pop("schedule_type", None)
    context.user_data.pop("schedule_interval", None)
    context.user_data.pop("schedule_channel_id", None)
    context.user_data.pop("post_state", None)
    await message.reply_text("✅ Schedule created successfully.", reply_markup=build_scheduler_keyboard())


async def list_schedules(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all saved schedules."""
    if not await can_manage_schedule(update):
        await _send_or_edit(update, "🚫 You do not have permission to view schedules.", answer_text="Access denied")
        return

    schedules = await get_all_schedules()
    if not schedules:
        await _send_or_edit(update, "No scheduled posts found.", keyboard=build_scheduler_keyboard())
        return

    lines = ["📆 Scheduled Posts"]
    for schedule in schedules:
        draft = await get_draft(int(schedule["draft_id"])) if schedule.get("draft_id") else None
        channel = await get_channel(int(schedule["channel_id"])) if schedule.get("channel_id") else None
        lines.append(
            f"\n#{schedule['id']} | {draft.get('draft_type') if draft else 'unknown'} | {channel.get('title') if channel else 'unknown'} | {schedule.get('schedule_type')} | {schedule.get('next_run')} | {schedule.get('status')}"
        )
    await _send_or_edit(update, "\n".join(lines), keyboard=build_schedule_actions_keyboard(int(schedules[0]["id"])))


async def pause_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pause a schedule."""
    if not await can_manage_schedule(update):
        await _send_or_edit(update, "🚫 You do not have permission to manage schedules.", answer_text="Access denied")
        return

    schedule_id = _extract_id(update)
    if schedule_id is None:
        return
    await pause_schedule_db(schedule_id)
    logger.info("Schedule paused %s", schedule_id)
    await _send_or_edit(update, "⏸ Schedule paused.", keyboard=build_scheduler_keyboard())


async def resume_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Resume a paused schedule."""
    if not await can_manage_schedule(update):
        await _send_or_edit(update, "🚫 You do not have permission to manage schedules.", answer_text="Access denied")
        return

    schedule_id = _extract_id(update)
    if schedule_id is None:
        return
    await resume_schedule_db(schedule_id)
    logger.info("Schedule resumed %s", schedule_id)
    await _send_or_edit(update, "▶ Schedule resumed.", keyboard=build_scheduler_keyboard())


async def delete_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a schedule."""
    if not await can_manage_schedule(update):
        await _send_or_edit(update, "🚫 You do not have permission to manage schedules.", answer_text="Access denied")
        return

    schedule_id = _extract_id(update)
    if schedule_id is None:
        return
    deleted = await delete_schedule_db(schedule_id)
    if deleted:
        await log_audit(
            actor_id=int(update.effective_user.id) if update.effective_user else None,
            actor_role="scheduler_user",
            action="schedule_deleted",
            module="scheduler",
            target_type="schedule",
            target_id=str(schedule_id),
        )
        logger.info("Schedule deleted %s", schedule_id)
        await _send_or_edit(update, "🗑 Schedule deleted.", keyboard=build_scheduler_keyboard())
        return
    await _send_or_edit(update, "❌ Failed to delete schedule.", keyboard=build_scheduler_keyboard())


async def edit_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Edit a schedule by restarting the flow."""
    if not await can_manage_schedule(update):
        await _send_or_edit(update, "🚫 You do not have permission to manage schedules.", answer_text="Access denied")
        return

    schedule_id = _extract_id(update)
    if schedule_id is None:
        return
    await _send_or_edit(update, "✏ Scheduling flow restarted. Create a new draft and reschedule.", keyboard=build_scheduler_keyboard())


def _extract_id(update: Update) -> int | None:
    """Extract a schedule id from callback data."""
    query = update.callback_query
    if query is None or query.data is None:
        return None
    data = query.data.split(":")
    if len(data) < 3:
        return None
    try:
        return int(data[-1])
    except ValueError:
        return None


def _schedule_job(schedule: dict[str, Any]) -> None:
    """Register a schedule with APScheduler."""
    initialize_scheduler(bot_app)

    schedule_id = int(schedule["id"])
    job_id = f"schedule_{schedule_id}"
    if scheduler.get_job(job_id):
        return

    schedule_type = schedule.get("schedule_type")
    if schedule_type in {"one_time"}:
        run_time = datetime.strptime(f"{schedule['schedule_date']} {schedule['schedule_time']}", "%Y-%m-%d %H:%M")
        scheduler.add_job(execute_schedule, trigger=DateTrigger(run_date=run_time), id=job_id, args=[schedule_id], replace_existing=True)
    elif schedule_type in {"daily", "weekly", "monthly", "yearly"}:
        cron_expression = schedule.get("cron_expression") or "0 0 * * *"
        scheduler.add_job(execute_schedule, trigger=CronTrigger.from_crontab(cron_expression), id=job_id, args=[schedule_id], replace_existing=True)
    elif schedule_type == "interval_minutes":
        interval_value = int((schedule.get("cron_expression") or "5m").replace("every:", "").replace("m", ""))
        scheduler.add_job(execute_schedule, trigger=IntervalTrigger(minutes=interval_value), id=job_id, args=[schedule_id], replace_existing=True)
    elif schedule_type == "interval_hours":
        interval_value = int((schedule.get("cron_expression") or "1h").replace("every:", "").replace("h", ""))
        scheduler.add_job(execute_schedule, trigger=IntervalTrigger(hours=interval_value), id=job_id, args=[schedule_id], replace_existing=True)


async def restore_pending_schedules() -> None:
    """Restore pending schedules after process restart (auto recovery)."""
    rows = await get_pending()
    restored = 0
    for row in rows:
        _schedule_job(row)
        restored += 1
    if restored:
        logger.info("Restored %s pending schedules", restored)


async def process_retry_queue() -> None:
    """Retry queue worker with priority ordering and attempt caps."""
    rows = await get_due_retries(limit=20)
    for row in rows:
        retry_id = int(row["id"])
        attempt = int(row.get("attempt_count") or 0) + 1
        max_attempts = int(row.get("max_attempts") or 5)
        if attempt > max_attempts:
            await mark_retry_state(retry_id, "failed", attempt_count=attempt, last_error="Max retry attempts reached")
            continue

        await mark_retry_state(retry_id, "processing", attempt_count=attempt)
        schedule_id = row.get("schedule_id")
        if not schedule_id:
            await mark_retry_state(retry_id, "failed", attempt_count=attempt, last_error="Missing schedule_id")
            continue

        schedule = await get_schedule(int(schedule_id))
        if not schedule:
            await mark_retry_state(retry_id, "failed", attempt_count=attempt, last_error="Schedule not found")
            continue

        try:
            await execute_schedule(int(schedule_id), from_retry=True)
            await mark_retry_state(retry_id, "completed", attempt_count=attempt)
        except Exception as exc:
            backoff = min(3600, 60 * attempt)
            await mark_retry_state(retry_id, "queued", attempt_count=attempt, last_error=str(exc), delay_seconds=backoff)


async def run_daily_jobs() -> None:
    """Run daily subscription/notification sweeps."""
    if bot_app is None:
        return
    await run_daily_commercial_jobs(bot_app)


async def run_daily_backup_job() -> None:
    """Run daily automated backup."""
    await run_scheduled_backup("daily")


async def run_weekly_backup_job() -> None:
    """Run weekly automated backup."""
    await run_scheduled_backup("weekly")


async def execute_schedule(schedule_id: int, from_retry: bool = False) -> None:
    """Execute a scheduled post and update its status."""
    schedule = await get_schedule(schedule_id)
    if not schedule:
        return

    draft = await get_draft(int(schedule["draft_id"])) if schedule.get("draft_id") else None
    if not draft:
        await update_schedule(schedule_id, status="failed")
        logger.warning("Schedule %s failed: missing draft", schedule_id)
        await record_publish(
            draft_id=None,
            channel_id=int(schedule.get("channel_id") or 0),
            workspace_id=None,
            collection_id=None,
            editor_id=None,
            published_via="scheduler",
            status="failed",
            error_message="Missing draft",
        )
        return

    channel = await get_channel(int(schedule["channel_id"])) if schedule.get("channel_id") else None
    if not channel:
        await update_schedule(schedule_id, status="failed")
        logger.warning("Schedule %s failed: missing channel", schedule_id)
        await record_publish(
            draft_id=int(schedule.get("draft_id") or 0),
            channel_id=int(schedule.get("channel_id") or 0),
            workspace_id=None,
            collection_id=None,
            editor_id=None,
            published_via="scheduler",
            status="failed",
            error_message="Missing channel",
        )
        return

    application = bot_app
    if application is None:
        logger.warning("No bot application available for schedule %s", schedule_id)
        return

    try:
        await _publish_draft(application, int(schedule["channel_id"]), draft)
        queue_rows = await mark_published_for_draft(int(schedule["draft_id"]), int(schedule["channel_id"]))
        for row in queue_rows:
            editor_id = row.get("editor_id")
            if editor_id:
                try:
                    await application.bot.send_message(
                        chat_id=int(editor_id),
                        text=f"✅ Draft published by scheduler. Queue #{row.get('id')}",
                    )
                except Exception:
                    logger.warning("Could not notify editor %s for scheduled queue %s", editor_id, row.get("id"))
        await update_schedule(schedule_id, status="completed", last_run=datetime.now().isoformat(), next_run=None)
        await record_publish(
            draft_id=int(schedule.get("draft_id") or 0),
            channel_id=int(schedule["channel_id"]),
            workspace_id=None,
            collection_id=None,
            editor_id=None,
            published_via="scheduler_retry" if from_retry else "scheduler",
            status="published",
        )
        await log_audit(
            actor_id=None,
            actor_role="system",
            action="schedule_executed",
            module="scheduler",
            target_type="schedule",
            target_id=str(schedule_id),
            metadata_json=json.dumps({"from_retry": from_retry}),
        )
        logger.info("Schedule executed %s", schedule_id)
    except RetryAfter as exc:
        wait_seconds = int(getattr(exc, "retry_after", 30) or 30)
        await enqueue_retry(
            schedule_id=schedule_id,
            draft_id=int(schedule.get("draft_id") or 0),
            channel_id=int(schedule.get("channel_id") or 0),
            workspace_id=None,
            retry_reason="flood_wait",
            priority=10,
            attempt_count=0,
            max_attempts=6,
            delay_seconds=wait_seconds,
            last_error=f"FloodWait {wait_seconds}s",
        )
        await update_schedule(schedule_id, status="pending", last_run=datetime.now().isoformat())
        if OWNER_ID:
            await create_notification(
                OWNER_ID,
                "owner",
                "scheduler",
                "FloodWait retry queued",
                f"Schedule {schedule_id} delayed for {wait_seconds}s due to Telegram FloodWait.",
            )
        logger.warning("Schedule %s delayed by FloodWait %ss", schedule_id, wait_seconds)
    except Exception as exc:
        logger.exception("Schedule failed %s: %s", schedule_id, exc)
        await update_schedule(schedule_id, status="failed", last_run=datetime.now().isoformat())
        await enqueue_retry(
            schedule_id=schedule_id,
            draft_id=int(schedule.get("draft_id") or 0),
            channel_id=int(schedule.get("channel_id") or 0),
            workspace_id=None,
            retry_reason="publish_failure",
            priority=5,
            attempt_count=0,
            max_attempts=5,
            delay_seconds=120,
            last_error=str(exc),
        )
        await record_publish(
            draft_id=int(schedule.get("draft_id") or 0),
            channel_id=int(schedule.get("channel_id") or 0),
            workspace_id=None,
            collection_id=None,
            editor_id=None,
            published_via="scheduler",
            status="failed",
            error_message=str(exc),
        )


async def retry_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show retry queue statistics for scheduler operations."""
    del context
    if not await can_manage_schedule(update):
        await update.effective_message.reply_text("🚫 Access denied.")
        return

    stats = await get_retry_statistics()
    await update.effective_message.reply_text(
        "📈 Retry Queue Stats\n"
        f"Queued: {stats.get('queued', 0)}\n"
        f"Processing: {stats.get('processing', 0)}\n"
        f"Completed: {stats.get('completed', 0)}\n"
        f"Failed: {stats.get('failed', 0)}"
    )


async def _publish_draft(application: Any, channel_id: int, draft: dict[str, Any]) -> None:
    """Publish a stored draft to a channel using the same send helpers as the composer."""
    if draft.get("draft_type") == "text":
        await application.bot.send_message(chat_id=channel_id, text=draft.get("text") or "", parse_mode=draft.get("parse_mode") or "HTML")
    elif draft.get("draft_type") == "photo":
        await application.bot.send_photo(chat_id=channel_id, photo=draft.get("file_id"), caption=draft.get("caption"), parse_mode=draft.get("parse_mode") or "HTML")
    elif draft.get("draft_type") == "gif":
        await application.bot.send_animation(chat_id=channel_id, animation=draft.get("file_id"), caption=draft.get("caption"), parse_mode=draft.get("parse_mode") or "HTML")
    elif draft.get("draft_type") == "video":
        await application.bot.send_video(chat_id=channel_id, video=draft.get("file_id"), caption=draft.get("caption"), parse_mode=draft.get("parse_mode") or "HTML")
    elif draft.get("draft_type") == "document":
        await application.bot.send_document(chat_id=channel_id, document=draft.get("file_id"), caption=draft.get("caption"), parse_mode=draft.get("parse_mode") or "HTML")
    elif draft.get("draft_type") == "album":
        album_items = json.loads(draft.get("album") or "[]")
        if album_items:
            media = []
            for item in album_items:
                if item.get("type") == "video":
                    media.append(InputMediaVideo(media=item.get("media", "")))
                else:
                    media.append(InputMediaPhoto(media=item.get("media", "")))
            await application.bot.send_media_group(chat_id=channel_id, media=media)
    else:
        raise ValueError("Unsupported draft type")
