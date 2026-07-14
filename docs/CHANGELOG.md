# CHANGELOG

## Flowza v1.0.3 - 2026-07-15

### Added

- Commercial persistence layer for subscription plans, admin subscriptions, payment requests, payment history, backup metadata, and error reports
- Telegram commercial command surface for plans, subscription status, renewal, payment submission, owner revenue dashboards, system health, backups, and error review
- USDT TRC20 payment verification pipeline using transaction hash checks against TronGrid events API
- Daily commercial scheduler sweep for subscription expiry state sync and proactive renewal reminders
- Automated daily and weekly backup jobs integrated into scheduler lifecycle
- Global error handler with persistent error UID capture and owner alert notifications
- Milestone 9 integration test scaffold for subscription lifecycle, payments, backups, and error persistence

### Changed

- Permission checks for publishing and scheduling now require active subscription state for admin/editor scopes
- Startup initialization now includes commercial schema and commercial command handlers
- Dashboard and callback routing now expose role-specific owner/admin/editor operational menus
- Documentation and release metadata bumped to v1.0.3

### Planned

- Destination type expansion (groups/supergroups/topics)
- Restore workflows for backup archives and recycle bin support

## Flowza v1.0.2 - 2026-07-15

### Added

- Enterprise scheduler extensions: retry queue, retry worker, FloodWait/RetryAfter handling, restart recovery of pending jobs, conflict detection, retry stats
- Publish history tracking for manual and scheduled publishing outcomes
- Workspace timezone persistence for scheduler execution context
- Analytics command layer for owner/admin/workspace/collection/destination/editor scopes
- Notification Center command layer with read-state controls
- Central audit log and audit command surface
- Enterprise global search command across audit, notifications, history, and retry queue
- Milestone 8 integration test scaffold for workspace/collection/media/template/analytics/search flows

### Changed

- SQLite connection manager now applies WAL mode and performance pragmas
- Bot startup now initializes enterprise database schema and registers analytics/notification handlers
- Scheduler now auto-restores pending jobs on startup and processes retry queue in background
- Documentation and release metadata bumped to v1.0.2

### Planned

- Subscription/payment automation and owner billing dashboards
- Destination type expansion and richer enterprise dashboards

## Flowza v1.0.1 - 2026-07-14

### Added

- Workspace subsystem persistence module with workspaces, user workspace context, editor workspace assignments, collections, collection destinations, media library, templates, and template variables
- Workspace command handlers for workspace, collection, media, template, global search, and scoped publish flows
- Workspace keyboard module for switching and delete confirmations
- Callback and message router integrations for workspace actions and media upload state

### Changed

- Bot startup now initializes workspace database module and registers workspace handlers
- Provisioning flow now auto-creates/assigns editor workspace when onboarding confirms
- Dashboard includes workspace module quick access entry
- Documentation and release metadata updated to v1.0.1

### Planned

- Analytics module completion and destination type expansion
- Subscription/payment automation and owner dashboards

## Flowza v1.0.0 - 2026-07-14

### Added

- RBAC persistence layer with user_roles and admin_settings tables
- Role-aware permissions for destination, composer, scheduler, and settings flows
- Approval workflow toggle in settings
- Project-level version constants for Flowza branding
- Professional README and docs/ documentation suite

### Changed

- Rebranded project identity from ChannelCMS V4 to Flowza v1.0 in source documentation, startup text, and dashboards
- Startup logs now include the central VERSION constant
- Logging namespace and file naming updated to Flowza identity

### Planned

- Workspace isolation and editor assignment UI
- Analytics and templates module completion
- Subscription/payment automation and owner dashboards
