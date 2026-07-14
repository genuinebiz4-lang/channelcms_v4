# CHANGELOG

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
