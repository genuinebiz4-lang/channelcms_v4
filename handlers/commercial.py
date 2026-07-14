"""Commercial subscription, payments, owner operations, backup, and error reporting handlers for Flowza v1.0.3."""

from __future__ import annotations

import os
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from telegram import Update
from telegram import error as telegram_error
from telegram.error import BadRequest, Conflict, Forbidden, NetworkError, RetryAfter, TimedOut
from telegram.ext import Application, CommandHandler, ContextTypes

from config import BASE_DIR, OWNER_ID, TIMEZONE, TRON_API_KEY, USDT_TRC20_WALLET
from database.commercial import (
    create_payment_request,
    daily_subscription_expiry_job,
    get_payment_history,
    get_plan,
    get_subscription_view,
    list_backups,
    list_errors,
    list_subscription_plans,
    mark_payment_failed,
    mark_payment_verified,
    owner_payment_stats,
    record_backup,
    report_error,
    submit_payment_hash,
    verify_tron_payment,
)
from database.enterprise import create_notification, log_audit, run_maintenance
from database.provisioning import get_admin_profile, list_admin_profiles
from database.settings import get_admin_for_user
from utils.logger import get_logger
from utils.permissions import ROLE_ADMIN, get_request_role, is_owner
from utils.rate_limit import enforce_rate_limit
from utils.telegram_safety import is_not_modified_error, retry_transient, safe_edit_message

logger = get_logger(__name__)
UnauthorizedType = getattr(telegram_error, "Unauthorized", Forbidden)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_subscription(subscription: dict[str, Any] | None, payments: list[dict[str, Any]]) -> str:
    if not subscription:
        return "No subscription data available."

    plan = subscription.get("plan_code")
    status = subscription.get("status")
    start = subscription.get("start_date")
    expiry = subscription.get("expiry_date")
    days = subscription.get("days_remaining")

    lines = [
        "💳 Subscription Status",
        f"Plan: {plan}",
        f"Start Date: {start}",
        f"Expiry Date: {expiry}",
        f"Days Remaining: {days}",
        f"Status: {status}",
        "",
        "Recent Payments:",
    ]
    if not payments:
        lines.append("- No payment history yet")
    else:
        for row in payments[:5]:
            lines.append(f"- {row.get('amount_usdt')} USDT | {row.get('plan_code')} | {row.get('created_at')[:19]}")

    return "\n".join(lines)


async def plans_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    role = await get_request_role(update)
    if role != ROLE_ADMIN and not is_owner(update):
        await update.effective_message.reply_text("🚫 Only Admin can view subscription plans.")
        return

    if not enforce_rate_limit(update, "plans", 4, 10):
        await update.effective_message.reply_text("Too many requests. Please wait a few seconds.")
        return

    plans = await list_subscription_plans()
    lines = ["📦 Flowza Subscription Plans", ""]
    for plan in plans:
        if int(plan.get("is_trial") or 0) == 1:
            lines.append(f"- {plan['code']}: {plan['name']}")
        else:
            lines.append(f"- {plan['code']}: {plan['name']} | {plan['price_usdt']} USDT | {plan['duration_days']} days")
    lines.append("")
    lines.append("Payment network: USDT TRC20 only")
    await update.effective_message.reply_text("\n".join(lines))


async def subscription_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    role = await get_request_role(update)
    if role != ROLE_ADMIN and not is_owner(update):
        await update.effective_message.reply_text("🚫 Only Admin can view subscription status.")
        return

    user = update.effective_user
    if user is None:
        return

    admin_id = await get_admin_for_user(user.id)
    if admin_id is None and is_owner(update):
        admin_id = user.id
    if admin_id is None:
        await update.effective_message.reply_text("Admin scope not found.")
        return

    admin_profile = await get_admin_profile(int(admin_id))
    trial_end = admin_profile.get("trial_end") if admin_profile else None
    sub = await get_subscription_view(int(admin_id), trial_end)
    payments = await get_payment_history(int(admin_id), limit=10)
    await update.effective_message.reply_text(_format_subscription(sub, payments))


async def renew_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await update.effective_message.reply_text("🚫 Only Admin can renew subscription.")
        return

    user = update.effective_user
    if user is None:
        return
    admin_id = await get_admin_for_user(user.id)
    if admin_id is None:
        await update.effective_message.reply_text("Admin scope not found.")
        return

    parts = (update.effective_message.text or "").split()
    if len(parts) < 2:
        await update.effective_message.reply_text("Usage: /renew <plan_code>")
        return

    plan_code = parts[1].strip().lower()
    ok, message, request = await create_payment_request(int(admin_id), plan_code, USDT_TRC20_WALLET)
    if not ok:
        await update.effective_message.reply_text(f"❌ {message}")
        return

    plan = await get_plan(plan_code)
    await log_audit(
        actor_id=int(user.id),
        actor_role="admin",
        action="payment_request_created",
        module="commercial",
        target_type="payment_request",
        target_id=str(request.get("id")),
    )
    await update.effective_message.reply_text(
        "💸 Renewal Request Created\n\n"
        f"Plan: {plan.get('name')}\n"
        f"Amount: {plan.get('price_usdt')} USDT\n"
        f"Network: TRC20\n"
        f"Receiver Wallet: {USDT_TRC20_WALLET}\n\n"
        "After payment, submit transaction hash:\n"
        "/submitpayment <tx_hash>"
    )


async def submit_payment_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    role = await get_request_role(update)
    if role != ROLE_ADMIN:
        await update.effective_message.reply_text("🚫 Only Admin can submit payment hash.")
        return

    user = update.effective_user
    if user is None:
        return

    parts = (update.effective_message.text or "").split()
    if len(parts) < 2:
        await update.effective_message.reply_text("Usage: /submitpayment <tx_hash>")
        return

    tx_hash = parts[1].strip()
    admin_id = await get_admin_for_user(user.id)
    if admin_id is None:
        await update.effective_message.reply_text("Admin scope not found.")
        return

    ok, message, request = await submit_payment_hash(int(admin_id), tx_hash)
    if not ok:
        await update.effective_message.reply_text(f"❌ {message}")
        return

    verified, verify_message, details = await verify_tron_payment(
        tx_hash=tx_hash,
        expected_amount=float(request.get("expected_amount_usdt") or 0),
        receiver_wallet=str(request.get("receiver_wallet") or ""),
        tron_api_key=TRON_API_KEY,
    )

    if not verified:
        await mark_payment_failed(int(request.get("id")), verify_message)
        await log_audit(
            actor_id=int(user.id),
            actor_role="admin",
            action="payment_verification_failed",
            module="commercial",
            target_type="payment_request",
            target_id=str(request.get("id")),
            metadata_json=str({"reason": verify_message}),
        )
        await update.effective_message.reply_text(f"❌ Payment verification failed: {verify_message}")
        return

    marked = await mark_payment_verified(
        request_id=int(request.get("id")),
        admin_id=int(admin_id),
        plan_code=str(request.get("plan_code")),
        amount_usdt=float(request.get("expected_amount_usdt") or 0),
        tx_hash=tx_hash,
        receiver_wallet=str(request.get("receiver_wallet") or ""),
        payer_wallet=str(details.get("from") or ""),
        metadata=details,
    )
    if not marked:
        await update.effective_message.reply_text("❌ Payment verification save failed.")
        return

    await create_notification(int(admin_id), "admin", "subscription", "Subscription activated", "Your Flowza subscription is now active.")
    if OWNER_ID:
        await create_notification(int(OWNER_ID), "owner", "payments", "Payment verified", f"Admin {admin_id} payment verified for {request.get('plan_code')}.")

    await log_audit(
        actor_id=int(user.id),
        actor_role="admin",
        action="payment_verified",
        module="commercial",
        target_type="payment_request",
        target_id=str(request.get("id")),
    )
    await update.effective_message.reply_text("✅ Payment verified and subscription activated.")


async def revenue_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if not is_owner(update):
        await update.effective_message.reply_text("🚫 Owner only command.")
        return

    stats = await owner_payment_stats()
    await update.effective_message.reply_text(
        "💰 Revenue\n"
        f"Total Payments: {stats['total_payments']}\n"
        f"USDT Received: {stats['total_usdt']:.2f}"
    )


async def payments_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if not is_owner(update):
        await update.effective_message.reply_text("🚫 Owner only command.")
        return

    stats = await owner_payment_stats()
    rows = stats.get("recent_payments") or []
    if not rows:
        await update.effective_message.reply_text("No payments recorded yet.")
        return
    lines = ["🧾 Payments"]
    for row in rows[:10]:
        lines.append(f"- admin={row.get('admin_id')} {row.get('amount_usdt')} USDT {row.get('plan_code')} {row.get('created_at')[:19]}")
    await update.effective_message.reply_text("\n".join(lines))


async def subscribers_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if not is_owner(update):
        await update.effective_message.reply_text("🚫 Owner only command.")
        return

    admins = await list_admin_profiles()
    stats = await owner_payment_stats()
    await update.effective_message.reply_text(
        "👥 Subscribers\n"
        f"Active Subscribers: {stats.get('active_subscribers', 0)}\n"
        f"Total Admin Accounts: {len(admins)}"
    )


async def expired_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if not is_owner(update):
        await update.effective_message.reply_text("🚫 Owner only command.")
        return

    stats = await owner_payment_stats()
    await update.effective_message.reply_text(
        "⛔ Expired Users\n"
        f"Expired Subscribers: {stats.get('expired_subscribers', 0)}\n"
        f"Upcoming Expiry (7d): {stats.get('upcoming_expiry', 0)}"
    )


async def payment_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if not is_owner(update):
        await update.effective_message.reply_text("🚫 Owner only command.")
        return

    stats = await owner_payment_stats()
    await update.effective_message.reply_text(
        "📊 Payment Stats\n"
        f"Total Payments: {stats.get('total_payments', 0)}\n"
        f"USDT Received: {stats.get('total_usdt', 0):.2f}\n"
        f"Active: {stats.get('active_subscribers', 0)}\n"
        f"Expired: {stats.get('expired_subscribers', 0)}\n"
        f"Upcoming Expiry: {stats.get('upcoming_expiry', 0)}"
    )


def _read_mem_info() -> tuple[int, int]:
    total_kb = 0
    avail_kb = 0
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total_kb = int(line.split()[1])
                if line.startswith("MemAvailable:"):
                    avail_kb = int(line.split()[1])
    except Exception:
        pass
    return total_kb, avail_kb


def _database_size_bytes() -> int:
    db_file = Path(BASE_DIR / os.getenv("DATABASE", "database/data/channelcms.db"))
    if not db_file.exists():
        return 0
    return int(db_file.stat().st_size)


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if not is_owner(update):
        await update.effective_message.reply_text("🚫 Owner only command.")
        return

    total_kb, avail_kb = _read_mem_info()
    disk = shutil.disk_usage(str(BASE_DIR))
    await update.effective_message.reply_text(
        "🩺 Health\n"
        f"CPU: available (load avg not sampled)\n"
        f"RAM Total: {total_kb // 1024} MB\n"
        f"RAM Available: {avail_kb // 1024} MB\n"
        f"Disk Free: {disk.free // (1024 * 1024)} MB\n"
        f"Timezone: {TIMEZONE}"
    )


async def system_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if not is_owner(update):
        await update.effective_message.reply_text("🚫 Owner only command.")
        return

    await update.effective_message.reply_text(
        "🧠 System\n"
        f"Bot Status: Running\n"
        f"Scheduler Status: Integrated\n"
        f"Telegram API: Reachable via bot polling\n"
        f"TRON API Key: {'Configured' if TRON_API_KEY else 'Missing'}\n"
        f"USDT Wallet: {'Configured' if USDT_TRC20_WALLET else 'Missing'}"
    )


async def database_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if not is_owner(update):
        await update.effective_message.reply_text("🚫 Owner only command.")
        return

    size = _database_size_bytes()
    await update.effective_message.reply_text(
        "🗄 Database\n"
        f"SQLite Size: {size // (1024 * 1024)} MB\n"
        f"Path: database/data/channelcms.db"
    )


def _zip_backup(target_dir: Path, backup_type: str) -> Path:
    timestamp = _utc_now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"flowza_{backup_type}_{timestamp}.zip"
    backup_path = target_dir / backup_name

    include_paths = [
        BASE_DIR / "database" / "data" / "channelcms.db",
        BASE_DIR / "config.py",
        BASE_DIR / ".env",
        BASE_DIR / "README.md",
        BASE_DIR / "docs",
    ]

    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in include_paths:
            if not path.exists():
                continue
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(BASE_DIR)))
            else:
                for child in path.rglob("*"):
                    if child.is_file():
                        zf.write(child, arcname=str(child.relative_to(BASE_DIR)))

    return backup_path


async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if not is_owner(update):
        await update.effective_message.reply_text("🚫 Owner only command.")
        return

    backup_dir = BASE_DIR / "assets" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    backup_path = _zip_backup(backup_dir, "manual")
    size = int(backup_path.stat().st_size)
    await record_backup("manual", str(backup_path), size, "completed")

    await update.effective_message.reply_text(
        "✅ Backup created\n"
        f"File: {backup_path.name}\n"
        f"Size: {size // 1024} KB"
    )


async def run_scheduled_backup(backup_type: str) -> dict[str, Any]:
    """Run a scheduled backup job and record metadata."""
    backup_dir = BASE_DIR / "assets" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = _zip_backup(backup_dir, backup_type)
    size = int(backup_path.stat().st_size)
    await record_backup(backup_type, str(backup_path), size, "completed")
    return {"file": str(backup_path), "size": size, "type": backup_type}


async def system_maintenance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if not is_owner(update):
        await update.effective_message.reply_text("🚫 Owner only command.")
        return

    result = await run_maintenance()
    await update.effective_message.reply_text(
        "🧹 Maintenance\n"
        f"Deleted retry rows: {result.get('deleted_retry', 0)}\n"
        f"Deleted notifications: {result.get('deleted_notifications', 0)}"
    )


async def errors_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    if not is_owner(update):
        await update.effective_message.reply_text("🚫 Owner only command.")
        return

    rows = await list_errors(limit=20, unresolved_only=False)
    if not rows:
        await update.effective_message.reply_text("No error reports found.")
        return

    lines = ["🧯 Error Reports"]
    for row in rows[:10]:
        lines.append(f"- {row.get('error_uid')} | {row.get('source')} | {row.get('created_at')[:19]}")
        lines.append(f"  {str(row.get('message') or '')[:120]}")
    await update.effective_message.reply_text("\n".join(lines))


async def owner_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    query = update.callback_query
    if query is None:
        return
    await safe_edit_message(
        query,
        "👑 Owner Menu\n\n"
        "System: /system /health /database /maintenance\n"
        "Payments: /revenue /payments /paymentstats\n"
        "Users: /subscribers /expiredusers\n"
        "Backup: /backup\n"
        "Errors: /errors"
    )


async def admin_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    query = update.callback_query
    if query is None:
        return
    await safe_edit_message(
        query,
        "🧑‍💼 Admin Menu\n\n"
        "Workspace: /workspaces /switchworkspace\n"
        "Destinations: /channels /addchannel\n"
        "Posts: /postdashboard /publishworkspace\n"
        "Scheduler: /scheduler /retrystats\n"
        "Analytics: /adminanalytics /workspaceanalytics\n"
        "Subscription: /plans /subscription /renew"
    )


async def editor_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    del context
    query = update.callback_query
    if query is None:
        return
    await safe_edit_message(
        query,
        "✍ Editor Menu\n\n"
        "Drafts: /postdashboard\n"
        "Assigned Destinations: /collections\n"
        "Approval Queue: /approvalqueue"
    )


async def run_daily_commercial_jobs(application: Application) -> None:
    """Execute daily expiry checks and send renewal notifications."""
    stats = await daily_subscription_expiry_job()
    logger.info("Commercial daily subscription sweep: %s", stats)

    admins = await list_admin_profiles()
    now = _utc_now()
    for admin in admins:
        admin_id = int(admin["admin_id"])
        subscription = await get_subscription_view(admin_id, admin.get("trial_end"))
        if not subscription:
            continue
        status = subscription.get("status")
        days_remaining = int(subscription.get("days_remaining") or 0)

        if status == "expired":
            await create_notification(
                admin_id,
                "admin",
                "subscription",
                "Subscription expired",
                "Your Flowza subscription expired. Publishing and scheduling are disabled until renewal.",
            )
            try:
                await application.bot.send_message(
                    chat_id=admin_id,
                    text=(
                        "⚠ Your Flowza subscription expired.\n\n"
                        "Choose a renewal plan with /plans and create payment request with /renew <plan_code>."
                    ),
                )
            except Exception:
                logger.warning("Failed to push expiry notice to admin %s", admin_id)

        elif status in {"active", "trial"} and days_remaining <= 3:
            await create_notification(
                admin_id,
                "admin",
                "subscription",
                "Subscription expiring soon",
                f"Your subscription expires in {days_remaining} day(s). Renew using /plans and /renew.",
            )
            try:
                await application.bot.send_message(
                    chat_id=admin_id,
                    text=f"⏳ Your Flowza subscription expires in {days_remaining} day(s). Renew soon with /plans.",
                )
            except Exception:
                logger.warning("Failed to push renewal reminder to admin %s", admin_id)

        if OWNER_ID and status == "expired":
            try:
                await application.bot.send_message(chat_id=int(OWNER_ID), text=f"Admin {admin_id} subscription expired.")
            except Exception:
                logger.warning("Failed to notify owner about expired admin %s", admin_id)

    await log_audit(actor_id=None, actor_role="system", action="daily_subscription_sweep", module="commercial")


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Capture unhandled exceptions and report to owner securely."""
    exc = context.error
    source = "telegram_update"
    message = str(exc) if exc else "Unknown exception"
    error_uid = f"ERR-{uuid.uuid4().hex[:12].upper()}"

    if exc is None:
        logger.debug("global_error_handler invoked without exception")
        return

    if isinstance(exc, BadRequest):
        if is_not_modified_error(exc):
            logger.debug("Ignored harmless Telegram BadRequest (%s): %s", error_uid, message)
            return
        logger.info("Telegram BadRequest (%s): %s", error_uid, message)
        return

    if isinstance(exc, Forbidden):
        logger.info("Telegram Forbidden (%s): %s", error_uid, message)
        return

    if isinstance(exc, UnauthorizedType):
        logger.info("Telegram Unauthorized (%s): %s", error_uid, message)
        return

    if isinstance(exc, RetryAfter):
        wait_seconds = int(getattr(exc, "retry_after", 1) or 1)
        logger.info("Telegram RetryAfter (%s): wait=%ss", error_uid, wait_seconds)
        return

    if isinstance(exc, TimedOut):
        logger.info("Telegram TimedOut (%s): %s", error_uid, message)
        return

    if isinstance(exc, NetworkError):
        logger.info("Telegram NetworkError (%s): %s", error_uid, message)
        return

    if isinstance(exc, Conflict):
        logger.warning("Telegram Conflict (%s): %s", error_uid, message)
        return

    report = await report_error(source=source, message=message, exc=exc, context={"update": str(update)[:400], "error_uid": error_uid})
    persisted_uid = report.get("error_uid") or error_uid

    logger.exception("Unhandled exception captured %s", persisted_uid)
    if OWNER_ID:
        try:
            await retry_transient(
                lambda: context.bot.send_message(
                    chat_id=int(OWNER_ID),
                    text=f"🚨 Flowza error captured: {persisted_uid}\nSource: {source}\nMessage: {message[:200]}",
                ),
                attempts=3,
                delay_seconds=0.6,
            )
        except Exception:
            logger.warning("Failed to notify owner for error %s", persisted_uid)


def register_commercial_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("plans", plans_command))
    application.add_handler(CommandHandler("subscription", subscription_command))
    application.add_handler(CommandHandler("renew", renew_command))
    application.add_handler(CommandHandler("submitpayment", submit_payment_command))

    application.add_handler(CommandHandler("revenue", revenue_command))
    application.add_handler(CommandHandler("payments", payments_command))
    application.add_handler(CommandHandler("subscribers", subscribers_command))
    application.add_handler(CommandHandler("expiredusers", expired_users_command))
    application.add_handler(CommandHandler("paymentstats", payment_stats_command))

    application.add_handler(CommandHandler("health", health_command))
    application.add_handler(CommandHandler("system", system_command))
    application.add_handler(CommandHandler("database", database_command))
    application.add_handler(CommandHandler("backup", backup_command))
    application.add_handler(CommandHandler("maintenance", system_maintenance_command))
    application.add_handler(CommandHandler("errors", errors_command))
