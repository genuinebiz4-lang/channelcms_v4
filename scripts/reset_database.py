"""Development database reset utility for Flowza v1.0.3."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config import DATABASE_PATH, OWNER_ID
from database.approval import initialize as initialize_approval
from database.channels import initialize as initialize_channels
from database.commercial import initialize as initialize_commercial
from database.db import get_connection, init_db
from database.drafts import initialize as initialize_drafts
from database.enterprise import initialize as initialize_enterprise
from database.provisioning import initialize as initialize_provisioning
from database.scheduler import initialize as initialize_scheduler
from database.settings import assign_role, initialize as initialize_settings
from database.workspace import initialize as initialize_workspace


async def _initialize_all() -> None:
    init_db()
    await initialize_channels()
    await initialize_drafts()
    await initialize_scheduler()
    await initialize_settings()
    await initialize_provisioning()
    await initialize_approval()
    await initialize_workspace()
    await initialize_enterprise()
    await initialize_commercial()


async def _ensure_owner_role() -> None:
    if OWNER_ID:
        await assign_role(int(OWNER_ID), "owner", created_by=int(OWNER_ID), is_active=True)


def _table_summary() -> dict[str, int]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        tables = [str(row["name"]) for row in rows]
        summary: dict[str, int] = {}
        for table in tables:
            count = connection.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
            summary[table] = int(count)
        return summary


async def main() -> int:
    db_path = Path(DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        db_path.unlink()

    await _initialize_all()
    await _ensure_owner_role()

    summary = _table_summary()
    print("DB_RESET_OK")
    print(f"DATABASE_PATH={db_path}")
    print(f"TABLE_COUNT={len(summary)}")
    print("ROW_COUNTS=" + json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
