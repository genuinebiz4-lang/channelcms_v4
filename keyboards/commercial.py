"""Inline keyboard builders for subscription and payment actions."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_subscription_keyboard() -> InlineKeyboardMarkup:
    """Build subscription actions with required wallet and navigation controls."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📋 Copy Wallet", callback_data="commercial:copy_wallet")],
            [InlineKeyboardButton("💰 Verify Payment", callback_data="commercial:verify_payment")],
            [InlineKeyboardButton("📜 Payment History", callback_data="commercial:payment_history")],
            [InlineKeyboardButton("⬅ Back", callback_data="commercial:back")],
            [InlineKeyboardButton("🏠 Dashboard", callback_data="dashboard:home")],
        ]
    )
