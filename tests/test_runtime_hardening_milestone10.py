"""Milestone 10 runtime hardening tests."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx

from database.approval import create_approval_request, initialize as initialize_approval, set_status
from database.commercial import initialize as initialize_commercial, verify_tron_payment
from database.db import get_connection
from database.drafts import initialize as initialize_drafts, save_text
from database.scheduler import add_schedule, find_duplicate_schedule, initialize as initialize_scheduler
from handlers import scheduler as scheduler_handler
from handlers.post import publish_to_channel
from utils.telegram_safety import safe_edit_message


class _DummyMessage:
    def __init__(self, text: str = "", reply_markup=None) -> None:
        self.text = text
        self.reply_markup = reply_markup


class _DummyQuery:
    def __init__(self, text: str = "") -> None:
        self.message = _DummyMessage(text=text)
        self.answer = AsyncMock()
        self.edit_message_text = AsyncMock()


class _DummyUpdate:
    def __init__(self, user_id: int = 1, query: _DummyQuery | None = None) -> None:
        self.callback_query = query
        self.effective_user = type("U", (), {"id": user_id})()
        self.effective_message = None


class _DummyContext:
    def __init__(self) -> None:
        self.application = type("A", (), {"bot_data": {}})()
        self.bot = type("B", (), {"send_message": AsyncMock()})()


class RuntimeHardeningMilestone10Tests(unittest.TestCase):
    def test_safe_edit_ignores_unchanged_callback_message(self) -> None:
        async def scenario() -> None:
            query = _DummyQuery(text="unchanged")
            edited = await safe_edit_message(query, "unchanged")
            self.assertFalse(edited)
            query.edit_message_text.assert_not_called()

        asyncio.run(scenario())

    def test_double_publish_click_is_deduplicated(self) -> None:
        async def scenario() -> None:
            query = _DummyQuery(text="publish")
            update = _DummyUpdate(user_id=42, query=query)
            context = _DummyContext()
            draft = {"id": 99, "draft_type": "text", "text": "hello", "parse_mode": "HTML"}

            with patch("handlers.post.can_publish_content", AsyncMock(return_value=True)), patch(
                "handlers.post.get_latest", AsyncMock(return_value=draft)
            ), patch("handlers.post.record_publish", AsyncMock()), patch("handlers.post.log_audit", AsyncMock()), patch(
                "handlers.post.mark_published_for_draft", AsyncMock(return_value=[])
            ), patch("handlers.post._send_or_edit", AsyncMock()):
                await publish_to_channel(update, context, 12345)
                await publish_to_channel(update, context, 12345)

            # second call is deduped before Telegram send
            self.assertEqual(context.bot.send_message.await_count, 1)

        asyncio.run(scenario())

    def test_double_schedule_is_detected(self) -> None:
        async def scenario() -> None:
            await initialize_scheduler()
            await add_schedule(
                draft_id=11,
                channel_id=22,
                schedule_type="one_time",
                schedule_date="2099-01-01",
                schedule_time="10:00",
                cron_expression=None,
                timezone="UTC",
                status="pending",
                next_run="2099-01-01 10:00",
            )
            duplicate = await find_duplicate_schedule(
                draft_id=11,
                channel_id=22,
                schedule_type="one_time",
                schedule_date="2099-01-01",
                schedule_time="10:00",
            )
            self.assertIsNotNone(duplicate)

        asyncio.run(scenario())

    def test_payment_timeout_is_handled(self) -> None:
        class _TimeoutClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url, headers=None):
                raise httpx.TimeoutException("timeout")

        async def scenario() -> None:
            ok, message, _payload = await verify_tron_payment(
                tx_hash="0x123",
                expected_amount=10.0,
                receiver_wallet="TTEST",
                tron_api_key="key",
            )
            self.assertFalse(ok)
            self.assertIn("timeout", message.lower())

        with patch("database.commercial.httpx.AsyncClient", return_value=_TimeoutClient()):
            asyncio.run(scenario())

    def test_approval_status_can_expire_without_crash(self) -> None:
        async def scenario() -> None:
            await initialize_drafts()
            await initialize_approval()
            draft = await save_text("approval expiry test")
            ok, _msg, row = await create_approval_request(
                draft_id=int(draft["id"]),
                editor_id=3001,
                admin_id=3002,
                workspace="Test",
                destination_id=777,
            )
            self.assertTrue(ok)
            changed = await set_status(int(row["id"]), status="expired")
            self.assertTrue(changed)

        asyncio.run(scenario())

    def test_restart_recovery_does_not_add_duplicate_jobs(self) -> None:
        schedule = {
            "id": 5,
            "schedule_type": "one_time",
            "schedule_date": "2099-02-01",
            "schedule_time": "12:00",
            "cron_expression": None,
        }
        fake_scheduler = Mock()
        fake_scheduler.get_job.return_value = object()
        fake_scheduler.add_job = Mock()

        with patch.object(scheduler_handler, "scheduler", fake_scheduler), patch.object(
            scheduler_handler, "initialize_scheduler", Mock()
        ):
            scheduler_handler._schedule_job(schedule)

        fake_scheduler.add_job.assert_not_called()

    def test_subscription_expiry_state_persists(self) -> None:
        async def scenario() -> None:
            await initialize_commercial()
            with get_connection() as connection:
                connection.execute(
                    """
                    INSERT INTO admin_subscriptions(admin_id, plan_code, status, start_date, expiry_date, days_remaining, source, created_at, updated_at)
                    VALUES (?, 'trial_45', 'trial', '2020-01-01T00:00:00+00:00', '2020-01-02T00:00:00+00:00', 0, 'test', '2020-01-01T00:00:00+00:00', '2020-01-01T00:00:00+00:00')
                    """,
                    (909090,),
                )
                connection.commit()

            from database.commercial import get_subscription_view

            view = await get_subscription_view(909090)
            self.assertIsNotNone(view)
            self.assertEqual(view.get("status"), "expired")

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
