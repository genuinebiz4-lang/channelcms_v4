"""Milestone 9 integration tests for commercial lifecycle workflows."""

from __future__ import annotations

import asyncio
import time
import unittest
from pathlib import Path

from config import BASE_DIR
from database.commercial import (
    create_payment_request,
    daily_subscription_expiry_job,
    get_latest_subscription,
    get_payment_history,
    get_subscription_view,
    initialize as initialize_commercial,
    list_errors,
    mark_payment_verified,
    owner_payment_stats,
    record_backup,
    report_error,
)
from database.provisioning import create_admin_profile, initialize as initialize_provisioning
from database.settings import initialize as initialize_settings


class Milestone9IntegrationTests(unittest.TestCase):
    def test_subscription_payment_backup_error_flows(self) -> None:
        async def scenario() -> None:
            await initialize_settings()
            await initialize_provisioning()
            await initialize_commercial()

            admin_id = 991000 + int(time.time() % 10000)
            owner_id = 990001

            ok, _msg, _profile = await create_admin_profile(
                admin_id=admin_id,
                username="m9_admin",
                full_name="Milestone Nine Admin",
                actor_id=owner_id,
            )
            self.assertTrue(ok)

            sub_before = await get_subscription_view(admin_id)
            self.assertIsNotNone(sub_before)
            self.assertIn(sub_before.get("status"), {"trial", "active", "expired"})

            created, _msg, request = await create_payment_request(admin_id, "plan_28", "TTESTWALLET123")
            self.assertTrue(created)
            self.assertIsNotNone(request)

            marked = await mark_payment_verified(
                request_id=int(request["id"]),
                admin_id=admin_id,
                plan_code="plan_28",
                amount_usdt=10.0,
                tx_hash="TEST_TX_HASH_0001",
                receiver_wallet="TTESTWALLET123",
                payer_wallet="TPAYERTEST123",
                metadata={"source": "integration_test"},
            )
            self.assertTrue(marked)

            latest = await get_latest_subscription(admin_id)
            self.assertIsNotNone(latest)
            self.assertEqual(latest.get("plan_code"), "plan_28")

            history = await get_payment_history(admin_id, limit=5)
            self.assertGreaterEqual(len(history), 1)

            backup_file = BASE_DIR / "assets" / "backups" / "m9_test_backup.zip"
            backup_file.parent.mkdir(parents=True, exist_ok=True)
            backup_file.write_text("test backup", encoding="utf-8")
            await record_backup("manual", str(backup_file), int(backup_file.stat().st_size), "completed")

            report = await report_error("integration_test", "Milestone9 simulated error", None, {"case": "m9"})
            self.assertTrue(str(report.get("error_uid", "")).startswith("ERR-"))

            errors = await list_errors(limit=10, unresolved_only=False)
            self.assertGreaterEqual(len(errors), 1)

            sweep = await daily_subscription_expiry_job()
            self.assertIn("active", sweep)
            self.assertIn("expired", sweep)

            stats = await owner_payment_stats()
            self.assertGreaterEqual(int(stats.get("total_payments", 0)), 1)

            if backup_file.exists():
                backup_file.unlink()

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
