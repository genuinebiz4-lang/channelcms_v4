# DATABASE

Product: Flowza v1.0  
Version: Flowza v1.0.2

## Engine

- SQLite

## Current Tables

1. bot_settings
- Purpose: generic key/value settings store.

2. channels
- Purpose: destination records and default destination flag.

3. drafts
- Purpose: draft payload storage for text/media/album composer flows.

4. scheduled_posts
- Purpose: scheduled publication queue metadata and execution state.

5. user_roles
- Purpose: RBAC assignment records for owner/admin/editor users.

6. admin_settings
- Purpose: admin-level approval workflow toggle state.

7. provisioning_admins
- Purpose: admin provisioning lifecycle and subscription metadata.

8. provisioning_editors
- Purpose: editor onboarding, assignment scope, and activity state.

9. provisioning_audit_log
- Purpose: role-sensitive operational audit history.

10. approval_queue
- Purpose: pending approval workflow with submit/approve/reject/edit transitions.

11. approval_actions
- Purpose: immutable decision history for moderation events.

12. workspaces
- Purpose: admin-scoped workspace definitions.

13. user_workspace_context
- Purpose: current workspace selection per user/admin scope.

14. workspace_editor_assignments
- Purpose: editor-to-workspace access control assignments.

15. collections
- Purpose: workspace-local destination collection definitions.

16. collection_destinations
- Purpose: many-to-many destination membership per collection.

17. media_library
- Purpose: deduplicated media references and searchable metadata per workspace.

18. templates
- Purpose: reusable workspace template records.

19. template_variables
- Purpose: template variable metadata and default value mappings.

20. retry_queue
- Purpose: scheduler retry/backoff queue with priority and attempt tracking.

21. publish_history
- Purpose: immutable publish result timeline for analytics and incident review.

22. scheduler_conflicts
- Purpose: schedule collision tracking for channel/date/time conflicts.

23. workspace_timezones
- Purpose: workspace-level timezone preferences for scheduling behavior.

24. notifications
- Purpose: notification center records for owner/admin/editor users.

25. central_audit_log
- Purpose: centralized cross-module audit trail.

## Planned Tables

- payment/subscription records
- recycle bin metadata
