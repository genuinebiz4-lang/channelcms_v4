"""Milestone 8 integration tests for key persistence workflows."""

from __future__ import annotations

import asyncio
import unittest

from database.enterprise import (
    analytics_snapshot,
    create_notification,
    get_retry_statistics,
    global_search_all,
    initialize as initialize_enterprise,
    list_notifications,
)
from database.workspace import (
    create_collection,
    create_template,
    create_workspace,
    initialize as initialize_workspace,
    save_media,
)


class Milestone8IntegrationTests(unittest.TestCase):
    def test_workspace_collection_media_template_analytics_search(self) -> None:
        async def scenario() -> None:
            await initialize_workspace()
            await initialize_enterprise()

            ok, _msg, workspace = await create_workspace(999001, "Test WS", "integration")
            self.assertTrue(ok)
            self.assertIsNotNone(workspace)
            workspace_id = int(workspace["workspace_id"])

            ok, _msg, collection = await create_collection(999001, workspace_id, "Launch Collection", "test")
            self.assertTrue(ok)
            self.assertIsNotNone(collection)

            ok, _msg, media = await save_media(
                workspace_id=workspace_id,
                file_id="integration_file_id",
                file_type="photo",
                caption="integration caption",
                tags="integration,test",
                created_by=999001,
            )
            self.assertTrue(ok)
            self.assertIsNotNone(media)

            ok, _msg, template = await create_template(
                workspace_id=workspace_id,
                admin_id=999001,
                template_name="Launch Template",
                body_text="Hello {workspace}",
                media_file_id=None,
                buttons=None,
                created_by=999001,
                variables={"workspace": ""},
            )
            self.assertTrue(ok)
            self.assertIsNotNone(template)

            await create_notification(999001, "admin", "integration", "Integration Test", "Notification row")
            notifications = await list_notifications(999001)
            self.assertGreaterEqual(len(notifications), 1)

            owner_snapshot = await analytics_snapshot("owner")
            self.assertIn("workspaces", owner_snapshot)

            retry_stats = await get_retry_statistics()
            self.assertIn("queued", retry_stats)

            search = await global_search_all("integration")
            self.assertIn("notifications", search)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()