"""Commercial subscription, payments, backups, and error reporting persistence for Flowza v1.0.3."""

from __future__ import annotations

import asyncio
import json
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from database.db import get_connection

PLAN_DEFINITIONS = {
    "trial_45": {"name": "45 Days Free Trial", "days": 45, "price_usdt": 0.0, "is_trial": 1},
    "plan_28": {"name": "28 Days", "days": 28, "price_usdt": 10.0, "is_trial": 0},
    "plan_84": {"name": "84 Days", "days": 84, "price_usdt": 25.0, "is_trial": 0},
    "plan_365": {"name": "365 Days", "days": 365, "price_usdt": 90.0, "is_trial": 0},
}


def _row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    return dict(row)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _initialize_sync() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS subscription_plans (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                duration_days INTEGER NOT NULL,
                price_usdt REAL NOT NULL,
                is_trial INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admin_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                plan_code TEXT NOT NULL,
                status TEXT NOT NULL,
                start_date TEXT NOT NULL,
                expiry_date TEXT NOT NULL,
                days_remaining INTEGER NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS payment_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                plan_code TEXT NOT NULL,
                expected_amount_usdt REAL NOT NULL,
                receiver_wallet TEXT NOT NULL,
                tx_hash TEXT,
                verification_status TEXT NOT NULL DEFAULT 'pending',
                verification_details TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS payment_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                plan_code TEXT NOT NULL,
                amount_usdt REAL NOT NULL,
                tx_hash TEXT NOT NULL,
                receiver_wallet TEXT NOT NULL,
                payer_wallet TEXT,
                network TEXT NOT NULL DEFAULT 'TRC20',
                token_symbol TEXT NOT NULL DEFAULT 'USDT',
                verified_at TEXT NOT NULL,
                status TEXT NOT NULL,
                metadata_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS system_backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backup_type TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size_bytes INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS error_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_uid TEXT NOT NULL UNIQUE,
                source TEXT,
                message TEXT,
                stack_trace TEXT,
                context_json TEXT,
                created_at TEXT NOT NULL,
                resolved INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_admin_subscriptions_admin ON admin_subscriptions(admin_id, status, expiry_date);
            CREATE INDEX IF NOT EXISTS idx_payment_requests_admin ON payment_requests(admin_id, verification_status);
            CREATE INDEX IF NOT EXISTS idx_payment_history_admin ON payment_history(admin_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_error_reports_created ON error_reports(created_at, resolved);
            """
        )

        now = _now_iso()
        for code, data in PLAN_DEFINITIONS.items():
            connection.execute(
                """
                INSERT INTO subscription_plans(code, name, duration_days, price_usdt, is_trial, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name = excluded.name,
                    duration_days = excluded.duration_days,
                    price_usdt = excluded.price_usdt,
                    is_trial = excluded.is_trial,
                    updated_at = excluded.updated_at
                """,
                (code, data["name"], int(data["days"]), float(data["price_usdt"]), int(data["is_trial"]), now, now),
            )

        connection.commit()


async def initialize() -> None:
    await asyncio.to_thread(_initialize_sync)


async def list_subscription_plans() -> list[dict[str, Any]]:
    def _list() -> list[dict[str, Any]]:
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM subscription_plans WHERE status = 'active' ORDER BY duration_days"
            ).fetchall()
            return [_row_to_dict(row) for row in rows]

    return await asyncio.to_thread(_list)


async def get_plan(plan_code: str) -> dict[str, Any] | None:
    def _get() -> dict[str, Any] | None:
        with get_connection() as connection:
            row = connection.execute("SELECT * FROM subscription_plans WHERE code = ?", (plan_code,)).fetchone()
            return None if row is None else _row_to_dict(row)

    return await asyncio.to_thread(_get)


async def get_latest_subscription(admin_id: int) -> dict[str, Any] | None:
    def _get() -> dict[str, Any] | None:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM admin_subscriptions WHERE admin_id = ? ORDER BY id DESC LIMIT 1",
                (admin_id,),
            ).fetchone()
            return None if row is None else _row_to_dict(row)

    return await asyncio.to_thread(_get)


async def ensure_trial_subscription(admin_id: int, trial_end_iso: str | None) -> dict[str, Any] | None:
    def _ensure() -> dict[str, Any] | None:
        with get_connection() as connection:
            current = connection.execute(
                "SELECT * FROM admin_subscriptions WHERE admin_id = ? ORDER BY id DESC LIMIT 1",
                (admin_id,),
            ).fetchone()
            if current is not None:
                return _row_to_dict(current)

            start = _now()
            expiry = datetime.fromisoformat(trial_end_iso) if trial_end_iso else (start + timedelta(days=45))
            days = max(0, (expiry - start).days)
            connection.execute(
                """
                INSERT INTO admin_subscriptions(admin_id, plan_code, status, start_date, expiry_date, days_remaining, source, created_at, updated_at)
                VALUES (?, 'trial_45', ?, ?, ?, ?, 'system_trial', ?, ?)
                """,
                (
                    admin_id,
                    "trial" if days > 0 else "expired",
                    start.isoformat(),
                    expiry.isoformat(),
                    days,
                    _now_iso(),
                    _now_iso(),
                ),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM admin_subscriptions WHERE admin_id = ? ORDER BY id DESC LIMIT 1",
                (admin_id,),
            ).fetchone()
            return None if row is None else _row_to_dict(row)

    return await asyncio.to_thread(_ensure)


async def create_payment_request(admin_id: int, plan_code: str, receiver_wallet: str) -> tuple[bool, str, dict[str, Any] | None]:
    plan = await get_plan(plan_code)
    if plan is None:
        return False, "Invalid plan.", None
    if float(plan["price_usdt"]) <= 0:
        return False, "Trial plan does not require payment.", None

    wallet = (receiver_wallet or "").strip()
    if not wallet:
        return False, "USDT TRC20 wallet is not configured.", None

    def _create() -> dict[str, Any] | None:
        now = _now_iso()
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO payment_requests(admin_id, plan_code, expected_amount_usdt, receiver_wallet, verification_status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?)
                """,
                (admin_id, plan_code, float(plan["price_usdt"]), wallet, now, now),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM payment_requests WHERE id = ?", (cursor.lastrowid,)).fetchone()
            return None if row is None else _row_to_dict(row)

    req = await asyncio.to_thread(_create)
    if req is None:
        return False, "Unable to create payment request.", None
    return True, "Payment request created.", req


async def submit_payment_hash(admin_id: int, tx_hash: str) -> tuple[bool, str, dict[str, Any] | None]:
    tx = (tx_hash or "").strip()
    if not tx:
        return False, "Transaction hash is required.", None

    def _submit() -> dict[str, Any] | None:
        now = _now_iso()
        with get_connection() as connection:
            pending = connection.execute(
                """
                SELECT * FROM payment_requests
                WHERE admin_id = ? AND verification_status = 'pending'
                ORDER BY id DESC LIMIT 1
                """,
                (admin_id,),
            ).fetchone()
            if pending is None:
                return None
            connection.execute(
                "UPDATE payment_requests SET tx_hash = ?, updated_at = ? WHERE id = ?",
                (tx, now, pending["id"]),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM payment_requests WHERE id = ?", (pending["id"],)).fetchone()
            return None if row is None else _row_to_dict(row)

    request = await asyncio.to_thread(_submit)
    if request is None:
        return False, "No pending payment request found. Choose a plan first.", None
    return True, "Transaction hash submitted.", request


def _parse_tron_transfer(event: dict[str, Any]) -> dict[str, Any] | None:
    value = event.get("result") or {}
    token = str(value.get("token_abbr") or value.get("tokenName") or "").upper()
    if token != "USDT":
        return None
    amount_raw = value.get("amount_str") or value.get("amount") or value.get("quant")
    try:
        amount = float(amount_raw) / 1_000_000 if float(amount_raw) > 1000 else float(amount_raw)
    except Exception:
        return None
    return {
        "token": token,
        "amount": amount,
        "to": str(value.get("to") or value.get("to_address") or ""),
        "from": str(value.get("from") or value.get("from_address") or ""),
        "network": "TRC20",
    }


async def verify_tron_payment(tx_hash: str, expected_amount: float, receiver_wallet: str, tron_api_key: str) -> tuple[bool, str, dict[str, Any]]:
    tx = (tx_hash or "").strip()
    if not tx:
        return False, "Transaction hash is missing.", {}
    if not tron_api_key:
        return False, "TRON API key not configured.", {}
    if not receiver_wallet:
        return False, "Receiver wallet is not configured.", {}

    headers = {"TRON-PRO-API-KEY": tron_api_key}
    url = f"https://api.trongrid.io/v1/transactions/{tx}/events"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code >= 400:
                return False, f"TRON API returned {response.status_code}", {}
            if not response.content:
                return False, "TRON API returned empty response.", {}
            try:
                payload = response.json()
            except ValueError:
                return False, "TRON API returned invalid JSON response.", {}
    except httpx.TimeoutException:
        return False, "TRON API request timeout.", {}
    except httpx.NetworkError as exc:
        return False, f"TRON API network failure: {exc}", {}
    except httpx.HTTPError as exc:
        return False, f"TRON API HTTP error: {exc}", {}
    except Exception as exc:
        return False, f"TRON API request failed: {exc}", {}

    if not isinstance(payload, dict):
        return False, "TRON API returned unexpected response format.", {}

    data = payload.get("data") or []
    if not isinstance(data, list):
        return False, "TRON API response missing event list.", payload
    transfer = None
    for event in data:
        candidate = _parse_tron_transfer(event)
        if candidate is None:
            continue
        transfer = candidate
        break

    if transfer is None:
        return False, "USDT TRC20 transfer event not found in transaction.", payload

    receiver = transfer.get("to", "")
    if receiver_wallet and receiver_wallet.lower() not in receiver.lower():
        return False, "Receiver wallet does not match configured wallet.", transfer

    amount = float(transfer.get("amount") or 0)
    if round(amount, 6) < round(float(expected_amount), 6):
        return False, "Transferred USDT amount is lower than required plan amount.", transfer

    return True, "Payment verified successfully.", transfer


async def mark_payment_verified(
    request_id: int,
    admin_id: int,
    plan_code: str,
    amount_usdt: float,
    tx_hash: str,
    receiver_wallet: str,
    payer_wallet: str | None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    def _mark() -> bool:
        now = _now()
        with get_connection() as connection:
            plan = connection.execute("SELECT * FROM subscription_plans WHERE code = ?", (plan_code,)).fetchone()
            if plan is None:
                return False
            duration_days = int(plan["duration_days"])

            current = connection.execute(
                "SELECT * FROM admin_subscriptions WHERE admin_id = ? ORDER BY id DESC LIMIT 1",
                (admin_id,),
            ).fetchone()
            base_start = now
            if current is not None:
                try:
                    existing_expiry = datetime.fromisoformat(current["expiry_date"])
                    if existing_expiry > now:
                        base_start = existing_expiry
                except Exception:
                    pass

            new_expiry = base_start + timedelta(days=duration_days)
            status = "active"
            connection.execute(
                """
                INSERT INTO admin_subscriptions(admin_id, plan_code, status, start_date, expiry_date, days_remaining, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'payment', ?, ?)
                """,
                (
                    admin_id,
                    plan_code,
                    status,
                    now.isoformat(),
                    new_expiry.isoformat(),
                    max(0, (new_expiry - now).days),
                    _now_iso(),
                    _now_iso(),
                ),
            )

            connection.execute(
                """
                INSERT INTO payment_history(admin_id, plan_code, amount_usdt, tx_hash, receiver_wallet, payer_wallet, verified_at, status, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'verified', ?, ?)
                """,
                (
                    admin_id,
                    plan_code,
                    float(amount_usdt),
                    tx_hash,
                    receiver_wallet,
                    payer_wallet,
                    _now_iso(),
                    json.dumps(metadata or {}),
                    _now_iso(),
                ),
            )

            connection.execute(
                """
                UPDATE payment_requests
                SET verification_status = 'verified', verification_details = ?, updated_at = ?
                WHERE id = ?
                """,
                (json.dumps(metadata or {}), _now_iso(), request_id),
            )

            connection.execute(
                "UPDATE admin_profiles SET status = 'active', subscription_expiry = ?, last_updated = ? WHERE admin_id = ?",
                (new_expiry.isoformat(), _now_iso(), admin_id),
            )

            connection.execute(
                "UPDATE user_roles SET is_active = 1, updated_at = CURRENT_TIMESTAMP WHERE (user_id = ? OR admin_id = ?) AND role IN ('admin', 'editor')",
                (admin_id, admin_id),
            )
            connection.commit()
            return True

    return await asyncio.to_thread(_mark)


async def mark_payment_failed(request_id: int, details: str) -> None:
    def _mark() -> None:
        with get_connection() as connection:
            connection.execute(
                "UPDATE payment_requests SET verification_status = 'failed', verification_details = ?, updated_at = ? WHERE id = ?",
                (details, _now_iso(), request_id),
            )
            connection.commit()

    await asyncio.to_thread(_mark)


async def get_subscription_view(admin_id: int, trial_end_iso: str | None = None) -> dict[str, Any] | None:
    await ensure_trial_subscription(admin_id, trial_end_iso)
    latest = await get_latest_subscription(admin_id)
    if latest is None:
        return None

    expiry = datetime.fromisoformat(latest["expiry_date"])
    now = _now()
    remaining = max(0, (expiry - now).days)
    status = str(latest.get("status") or "expired")
    if status != "suspended":
        status = "active" if expiry > now else ("trial" if latest.get("plan_code") == "trial_45" and remaining > 0 else "expired")

    latest["days_remaining"] = remaining
    latest["status"] = status
    return latest


async def is_subscription_active(admin_id: int, trial_end_iso: str | None = None) -> bool:
    view = await get_subscription_view(admin_id, trial_end_iso)
    if view is None:
        return False
    return view.get("status") in {"active", "trial"}


async def get_payment_history(admin_id: int, limit: int = 20) -> list[dict[str, Any]]:
    safe_limit = max(1, min(200, int(limit)))

    def _list() -> list[dict[str, Any]]:
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM payment_history WHERE admin_id = ? ORDER BY id DESC LIMIT ?",
                (admin_id, safe_limit),
            ).fetchall()
            return [_row_to_dict(row) for row in rows]

    return await asyncio.to_thread(_list)


async def daily_subscription_expiry_job() -> dict[str, int]:
    def _run() -> dict[str, int]:
        now = _now()
        expired = 0
        active = 0
        with get_connection() as connection:
            admins = connection.execute("SELECT admin_id, trial_end FROM admin_profiles").fetchall()
            for admin in admins:
                admin_id = int(admin["admin_id"])
                latest = connection.execute(
                    "SELECT * FROM admin_subscriptions WHERE admin_id = ? ORDER BY id DESC LIMIT 1",
                    (admin_id,),
                ).fetchone()
                if latest is None:
                    trial_end_iso = admin["trial_end"]
                    trial_end = datetime.fromisoformat(trial_end_iso) if trial_end_iso else now
                    status = "trial" if trial_end > now else "expired"
                    expiry = trial_end
                    connection.execute(
                        """
                        INSERT INTO admin_subscriptions(admin_id, plan_code, status, start_date, expiry_date, days_remaining, source, created_at, updated_at)
                        VALUES (?, 'trial_45', ?, ?, ?, ?, 'expiry_job', ?, ?)
                        """,
                        (
                            admin_id,
                            status,
                            now.isoformat(),
                            expiry.isoformat(),
                            max(0, (expiry - now).days),
                            _now_iso(),
                            _now_iso(),
                        ),
                    )
                    latest = connection.execute(
                        "SELECT * FROM admin_subscriptions WHERE admin_id = ? ORDER BY id DESC LIMIT 1",
                        (admin_id,),
                    ).fetchone()

                expiry = datetime.fromisoformat(latest["expiry_date"])
                if latest["status"] == "suspended":
                    continue

                if expiry <= now:
                    expired += 1
                    connection.execute(
                        "UPDATE admin_profiles SET status = 'expired', subscription_expiry = ?, last_updated = ? WHERE admin_id = ?",
                        (expiry.isoformat(), _now_iso(), admin_id),
                    )
                    connection.execute(
                        "UPDATE user_roles SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE (user_id = ? OR admin_id = ?) AND role IN ('admin', 'editor')",
                        (admin_id, admin_id),
                    )
                    connection.execute(
                        "UPDATE admin_subscriptions SET status = 'expired', days_remaining = 0, updated_at = ? WHERE id = ?",
                        (_now_iso(), latest["id"]),
                    )
                else:
                    active += 1
                    remaining = max(0, (expiry - now).days)
                    next_status = "trial" if latest["plan_code"] == "trial_45" else "active"
                    connection.execute(
                        "UPDATE admin_subscriptions SET status = ?, days_remaining = ?, updated_at = ? WHERE id = ?",
                        (next_status, remaining, _now_iso(), latest["id"]),
                    )
                    connection.execute(
                        "UPDATE admin_profiles SET status = 'active', subscription_expiry = ?, last_updated = ? WHERE admin_id = ?",
                        (expiry.isoformat(), _now_iso(), admin_id),
                    )
            connection.commit()
        return {"expired": expired, "active": active}

    return await asyncio.to_thread(_run)


async def owner_payment_stats() -> dict[str, Any]:
    def _stats() -> dict[str, Any]:
        now = _now()
        with get_connection() as connection:
            total_payments = int(connection.execute("SELECT COUNT(*) c FROM payment_history WHERE status = 'verified'").fetchone()["c"])
            total_usdt = float(connection.execute("SELECT COALESCE(SUM(amount_usdt), 0) s FROM payment_history WHERE status = 'verified'").fetchone()["s"])
            active_subscribers = int(
                connection.execute(
                    """
                    SELECT COUNT(*) c FROM (
                        SELECT admin_id, MAX(id) latest_id
                        FROM admin_subscriptions
                        GROUP BY admin_id
                    ) x
                    JOIN admin_subscriptions s ON s.id = x.latest_id
                    WHERE s.status IN ('active', 'trial') AND datetime(s.expiry_date) > datetime('now')
                    """
                ).fetchone()["c"]
            )
            expired_subscribers = int(
                connection.execute(
                    """
                    SELECT COUNT(*) c FROM (
                        SELECT admin_id, MAX(id) latest_id
                        FROM admin_subscriptions
                        GROUP BY admin_id
                    ) x
                    JOIN admin_subscriptions s ON s.id = x.latest_id
                    WHERE s.status = 'expired' OR datetime(s.expiry_date) <= datetime('now')
                    """
                ).fetchone()["c"]
            )
            upcoming_expiry = int(
                connection.execute(
                    """
                    SELECT COUNT(*) c FROM (
                        SELECT admin_id, MAX(id) latest_id
                        FROM admin_subscriptions
                        GROUP BY admin_id
                    ) x
                    JOIN admin_subscriptions s ON s.id = x.latest_id
                    WHERE datetime(s.expiry_date) > datetime('now')
                      AND datetime(s.expiry_date) <= datetime('now', '+7 day')
                    """
                ).fetchone()["c"]
            )

            recent_payments = connection.execute(
                "SELECT * FROM payment_history ORDER BY id DESC LIMIT 20"
            ).fetchall()
            recent_subscriptions = connection.execute(
                "SELECT * FROM admin_subscriptions ORDER BY id DESC LIMIT 50"
            ).fetchall()

            return {
                "generated_at": now.isoformat(),
                "total_payments": total_payments,
                "total_usdt": total_usdt,
                "active_subscribers": active_subscribers,
                "expired_subscribers": expired_subscribers,
                "upcoming_expiry": upcoming_expiry,
                "recent_payments": [_row_to_dict(r) for r in recent_payments],
                "recent_subscriptions": [_row_to_dict(r) for r in recent_subscriptions],
            }

    return await asyncio.to_thread(_stats)


async def record_backup(backup_type: str, file_path: str, file_size_bytes: int, status: str = "completed") -> None:
    def _record() -> None:
        with get_connection() as connection:
            connection.execute(
                "INSERT INTO system_backups(backup_type, file_path, file_size_bytes, status, created_at) VALUES (?, ?, ?, ?, ?)",
                (backup_type, file_path, int(file_size_bytes), status, _now_iso()),
            )
            connection.commit()

    await asyncio.to_thread(_record)


async def list_backups(limit: int = 20) -> list[dict[str, Any]]:
    safe_limit = max(1, min(200, int(limit)))

    def _list() -> list[dict[str, Any]]:
        with get_connection() as connection:
            rows = connection.execute("SELECT * FROM system_backups ORDER BY id DESC LIMIT ?", (safe_limit,)).fetchall()
            return [_row_to_dict(row) for row in rows]

    return await asyncio.to_thread(_list)


async def report_error(source: str, message: str, exc: BaseException | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    now = _now()
    error_uid = f"ERR-{now.strftime('%Y%m%d%H%M%S')}-{int(now.timestamp() * 1000) % 1000000:06d}"
    stack_trace = ""
    if exc is not None:
        stack_trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    def _insert() -> dict[str, Any]:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO error_reports(error_uid, source, message, stack_trace, context_json, created_at, resolved)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    error_uid,
                    source,
                    message,
                    stack_trace,
                    json.dumps(context or {}),
                    _now_iso(),
                ),
            )
            connection.commit()
            row = connection.execute("SELECT * FROM error_reports WHERE error_uid = ?", (error_uid,)).fetchone()
            return _row_to_dict(row)

    return await asyncio.to_thread(_insert)


async def list_errors(limit: int = 30, unresolved_only: bool = False) -> list[dict[str, Any]]:
    safe_limit = max(1, min(200, int(limit)))

    def _list() -> list[dict[str, Any]]:
        with get_connection() as connection:
            if unresolved_only:
                rows = connection.execute(
                    "SELECT * FROM error_reports WHERE resolved = 0 ORDER BY id DESC LIMIT ?",
                    (safe_limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM error_reports ORDER BY id DESC LIMIT ?",
                    (safe_limit,),
                ).fetchall()
            return [_row_to_dict(row) for row in rows]

    return await asyncio.to_thread(_list)
