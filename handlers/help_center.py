"""Help Center, support page, and manual generation handlers."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config import BASE_DIR, VERSION
from keyboards.help_center import build_help_center_keyboard, build_support_keyboard
from utils.telegram_safety import safe_edit_message

SUPPORT_USERNAME = "@Lazy999000"
SUPPORT_LINK = "https://t.me/Lazy999000"

HELP_CONTENT = {
    "getting_started": "Use Setup Wizard to create workspace, add destination, draft first post, and publish.",
    "workspace": "Workspaces isolate destinations, media, templates, and collections by admin scope.",
    "destinations": "Add channels by forwarding channel messages. Set default destination and manage ownership.",
    "posts": "Create drafts from text or media, preview, then publish now or schedule.",
    "scheduler": "Scheduler queues existing drafts only. Choose date/time/destination and confirm.",
    "media": "Media Library stores Telegram file IDs for reuse with dedupe and search.",
    "collections": "Collections group destinations for batch publishing workflows.",
    "templates": "Templates support placeholders and reusable content bodies.",
    "team": "Owner manages admins/editors. Admins control assignments and permissions.",
    "analytics": "Analytics dashboards show owner, admin, workspace, collection, destination, and editor scopes.",
    "settings": "Settings controls approval workflow and role-based publishing behavior.",
    "subscription": "Flowza runs in free mode. No subscription is required.",
    "payments": "Payment workflows are disabled in free mode.",
    "faq": "Use Help Center sections for setup and operations. Contact support for unresolved issues.",
    "troubleshooting": "Common checks: bot admin rights, destination existence, selected workspace, and editor/admin permissions.",
}


async def help_center_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render Help Center landing screen."""
    del context
    query = update.callback_query
    if query is None:
        return
    await safe_edit_message(
        query,
        "❓ Help Center\n\nSelect a section below.",
        reply_markup=build_help_center_keyboard(),
    )


async def help_topic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, topic_key: str) -> None:
    """Render one help section."""
    del context
    query = update.callback_query
    if query is None:
        return

    text = HELP_CONTENT.get(topic_key, "Section not found.")
    await safe_edit_message(
        query,
        f"❓ Help Center\n\n{text}",
        reply_markup=build_help_center_keyboard(),
    )


async def support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Render support contact information."""
    del context
    query = update.callback_query
    if query is None:
        return

    await safe_edit_message(
        query,
        "📞 Contact Support\n\n"
        "Owner: Lazy\n"
        f"Telegram: {SUPPORT_USERNAME}\n"
        f"Open Chat: {SUPPORT_LINK}\n\n"
        "Support Type:\n"
        "- Technical\n"
        "- Admin Requests\n"
        "- Feature Requests\n"
        "- Bug Reports",
        reply_markup=build_support_keyboard(),
    )


def _manual_output_path() -> Path:
    out_dir = BASE_DIR / "assets" / "documents"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "Flowza_User_Manual_v1.0.4.pdf"


def _collect_doc_sections() -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = [
        ("Introduction", "Flowza is a Telegram publishing workspace for teams."),
        ("Getting Started", "Create workspace, add destination, compose post, publish or schedule."),
        ("Workspace", "Use workspace manager for isolated operations."),
        ("Destinations", "Manage channels/groups and ownership."),
        ("Posts", "Composer supports text and media drafts with preview."),
        ("Publishing", "Publish only to valid scoped destinations."),
        ("Scheduling", "Schedule existing drafts with timezone-aware runs."),
        ("Templates", "Use placeholder variables for reusable content."),
        ("Collections", "Group destinations for batch operations."),
        ("Media Library", "Store Telegram file IDs for reuse."),
        ("Approval Flow", "Editors submit, admins approve/reject."),
        ("Analytics", "Track publishing and usage metrics."),
        ("Settings", "Use settings to control approval workflow behavior for editors and admins."),
        ("FAQ", "Use Help Center and support contact paths."),
        ("Support", f"Contact {SUPPORT_USERNAME} at {SUPPORT_LINK}."),
        ("Troubleshooting", "Check bot permissions, workspace scope, destination validity, and role mapping."),
        ("Flowza Version", VERSION),
    ]

    docs_dir = BASE_DIR / "docs"
    for name in ["ADMIN_GUIDE.md", "EDITOR_GUIDE.md", "OWNER_GUIDE.md", "DATABASE.md", "ARCHITECTURE.md"]:
        file_path = docs_dir / name
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8").strip()
            excerpt = " ".join(content.split())[:500]
            sections.append((name.replace("_", " ").replace(".md", ""), excerpt))
    return sections


def _build_manual_pdf() -> Path:
    out = _manual_output_path()
    pdf = canvas.Canvas(str(out), pagesize=A4)
    width, height = A4

    y = height - 2 * cm
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(2 * cm, y, "Flowza User Manual")
    y -= 0.8 * cm
    pdf.setFont("Helvetica", 10)
    pdf.drawString(2 * cm, y, f"Version: {VERSION}")
    y -= 1.0 * cm

    for title, body in _collect_doc_sections():
        if y < 4 * cm:
            pdf.showPage()
            y = height - 2 * cm
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(2 * cm, y, title)
        y -= 0.5 * cm
        pdf.setFont("Helvetica", 10)
        words = body.split()
        line = ""
        for w in words:
            trial = f"{line} {w}".strip()
            if pdf.stringWidth(trial, "Helvetica", 10) <= width - 4 * cm:
                line = trial
            else:
                pdf.drawString(2 * cm, y, line)
                y -= 0.45 * cm
                line = w
                if y < 3 * cm:
                    pdf.showPage()
                    y = height - 2 * cm
                    pdf.setFont("Helvetica", 10)
        if line:
            pdf.drawString(2 * cm, y, line)
            y -= 0.6 * cm
        y -= 0.2 * cm

    pdf.save()
    return out


async def manual_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate and send user manual PDF."""
    file_path = _build_manual_pdf()
    query = update.callback_query
    if query is None:
        return

    chat_id = query.message.chat_id if query.message else None
    if chat_id is not None:
        try:
            with file_path.open("rb") as f:
                await context.bot.send_document(chat_id=chat_id, document=f, filename=file_path.name)
        except Exception:
            await safe_edit_message(
                query,
                f"📄 User Manual generated at: {file_path}",
                reply_markup=build_help_center_keyboard(),
            )
            return

    await safe_edit_message(
        query,
        "📄 User Manual generated and ready.",
        reply_markup=build_help_center_keyboard(),
    )


async def help_center_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Expose help center via command fallback."""
    del context
    await update.effective_message.reply_text(
        "❓ Help Center\n\nSelect a section below.",
        reply_markup=build_help_center_keyboard(),
    )


async def download_manual_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate and send manual PDF via command fallback."""
    file_path = _build_manual_pdf()
    try:
        with file_path.open("rb") as f:
            await context.bot.send_document(chat_id=update.effective_user.id, document=f, filename=file_path.name)
    except Exception:
        await update.effective_message.reply_text(f"📄 User Manual generated at: {file_path}")


def register_help_center_handlers(application: Application) -> None:
    """Register help center command fallback."""
    application.add_handler(CommandHandler("helpcenter", help_center_command))
    application.add_handler(CommandHandler("downloadmanual", download_manual_command))
