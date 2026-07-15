# Flowza v1.0

Professional Telegram Content Management System

Automate.  
Schedule.  
Grow.

Version: Flowza v1.0.3

Release Stage: Release Candidate (RC)

## About

Flowza is a Telegram Content Management System designed to centralize destination management, post composition, drafting, and scheduling in one operational workflow.

Target users:

- Creators
- Freelancers
- Businesses
- Agencies
- Enterprise Teams

## Features

### Completed

- ✔ Destination Manager (channel destinations currently implemented)
- ✔ Post Composer (text, photo, GIF/animation, video, document, album)
- ✔ Post Composer Extensions (audio, voice, sticker rejection safety)
- ✔ Draft System (save, preview, edit, delete latest draft)
- ✔ Scheduler (one-time and recurring schedules)
- ✔ RBAC Foundation (Owner/Admin/Editor role model)
- ✔ Provisioning Module (owner/admin/editor onboarding and assignment)
- ✔ Approval Workflow Toggle (admin-level setting with publish restriction for editors)
- ✔ Approval Queue (submit/approve/reject/edit review flow)
- ✔ Workspace Management (create/list/switch/edit/delete)
- ✔ Destination Collections (group destinations for batch publish)
- ✔ Media Library (workspace-scoped upload/search/delete with dedupe)
- ✔ Template Engine (create/edit/delete/apply variable-based templates)
- ✔ Global Search (workspace, collection, media, templates, destinations, drafts, editors)
- ✔ Enterprise Scheduler (retry queue, FloodWait handling, auto-recovery, retry stats, conflict checks)
- ✔ Analytics Engine (owner/admin/workspace/collection/destination/editor scopes)
- ✔ Notification Center (owner/admin/editor notifications with read state)
- ✔ Central Audit Log (cross-module action history)
- ✔ Performance Layer (SQLite WAL mode, maintenance cleanup, vacuum command)
- ✔ Commercial Engine (subscription lifecycle, plan management, payment requests)
- ✔ USDT TRC20 Verification (transaction hash verification via TronGrid)
- ✔ Owner Revenue and Subscription Operations (health, revenue, payments, expiry dashboards)
- ✔ Automated Backup Jobs (daily/weekly zip backups plus manual backup command)
- ✔ Global Error Reporting (error UID capture and owner alerting)
- ✔ Settings Dashboard (role and approval status)
- ✔ Button-First Dashboard Navigation (Back + Dashboard controls across modules)
- ✔ First-Run Setup Wizard (Create Workspace → Add Destination → Create Post → Publish)
- ✔ Help Center (guided sections, FAQ, troubleshooting, support)
- ✔ PDF User Manual generation and download
- ✔ Support Contact panel with Telegram deep-link
- ✔ Structured Logging
- ✔ SQLite Database Layer
- ✔ Telegram Dashboard Navigation

### Planned

- ○ Destination type expansion (groups/supergroups/topics)
- ○ Recycle bin and restore window

## Project Architecture

```text
.
├── assets/
│   ├── backups/
│   ├── documents/
│   ├── gifs/
│   ├── images/
│   └── videos/
├── database/
│   ├── __init__.py
│   ├── analytics.py
│   ├── approval.py
│   ├── commercial.py
│   ├── enterprise.py
│   ├── channels.py
│   ├── db.py
│   ├── drafts.py
│   ├── provisioning.py
│   ├── scheduler.py
│   ├── settings.py
│   ├── workspace.py
│   └── data/
├── docs/
│   ├── ADMIN_GUIDE.md
│   ├── ARCHITECTURE.md
│   ├── CHANGELOG.md
│   ├── DATABASE.md
│   ├── EDITOR_GUIDE.md
│   ├── INSTALLATION.md
│   ├── OWNER_GUIDE.md
│   └── ROADMAP.md
├── handlers/
│   ├── __init__.py
│   ├── analytics.py
│   ├── approval.py
│   ├── channel.py
│   ├── commercial.py
│   ├── post.py
│   ├── provisioning.py
│   ├── notifications.py
│   ├── scheduler.py
│   ├── settings.py
│   ├── start.py
│   ├── template.py
│   └── workspace.py
├── keyboards/
│   ├── __init__.py
│   ├── approval.py
│   ├── channel.py
│   ├── dashboard.py
│   ├── post.py
│   ├── provisioning.py
│   ├── scheduler.py
│   ├── settings.py
│   └── workspace.py
├── logs/
├── routers/
│   ├── __init__.py
│   ├── callback_router.py
│   └── message_router.py
├── utils/
│   ├── __init__.py
│   ├── helpers.py
│   ├── logger.py
│   ├── permissions.py
│   ├── rate_limit.py
│   └── validators.py
├── tests/
│   └── test_integration_milestone8.py
│   └── test_integration_milestone9.py
├── bot.py
├── config.py
├── requirements.txt
└── states.py
```

Folder responsibilities:

- assets/: Uploaded and generated media storage roots
- database/: SQLite schema initialization and data access modules
- handlers/: Business logic for dashboard actions and content workflows
- keyboards/: Inline keyboard builders for each domain module
- routers/: Callback and message dispatchers
- utils/: Cross-cutting helpers (logging, permissions, validators)
- docs/: Product and operations documentation

## User Hierarchy

Owner

↓

Admin

↓

Editor

Role permissions in current implementation:

- Owner: Full platform-level access and fallback superuser authority
- Admin: Destination management, composer, publishing, scheduler, settings, approval toggle
- Editor: Composer and scheduler access; direct publishing blocked when approval is enabled for assigned admin

## Subscription System

Commercial plan model:

- 45 Days Free Trial
- 28 Days = 10 USDT
- 84 Days = 25 USDT
- 365 Days = 90 USDT

Payment method:

- USDT TRC20
- Automatic verification (Implemented)

## Current Development Status

- [x] Phase 1: Core bot skeleton and routing
- [x] Phase 2: Destination, draft, and publishing workflows
- [x] Phase 3: Scheduler and callback actions
- [x] Phase 4: RBAC foundation and approval controls
- [x] Phase 5: Subscription/payment automation
- [x] Phase 6: Owner dashboards, analytics, notifications, backups

## Installation

1. Python Version

- Python 3.12

2. Create Virtual Environment

- python3 -m venv .venv
- source .venv/bin/activate

3. Install Requirements

- pip install -r requirements.txt

4. Configure Environment

- Copy and update .env values:
	- BOT_TOKEN
	- OWNER_ID
	- DATABASE
	- LOG_LEVEL
	- TIMEZONE
	- USDT_TRC20_WALLET
	- TRON_API_KEY

5. Run Bot

- .venv/bin/python bot.py

## Folder Structure

See the Project Architecture tree above.

## Database

Current SQLite tables:

- bot_settings: key/value system settings store
- channels: destination records and default destination flag
- drafts: composed content payloads and media references
- scheduled_posts: schedule queue metadata and status
- user_roles: RBAC assignments for owner/admin/editor
- admin_settings: per-admin approval workflow setting
- admin_profiles: admin onboarding/subscription lifecycle metadata
- editor_profiles: editor assignment and capability metadata
- destination_owners: admin ownership mapping for destinations
- provisioning_audit: provisioning and moderation action log
- approval_queue: pending approval workflow records
- approval_actions: approval decision history
- workspaces: admin-scoped workspace definitions
- user_workspace_context: selected workspace per user/admin scope
- workspace_editor_assignments: editor-to-workspace access mapping
- collections: workspace-level destination grouping
- collection_destinations: collection membership mapping
- media_library: workspace media asset index with dedupe keys
- templates: workspace template records
- template_variables: variable metadata per template
- retry_queue: enterprise scheduler retry/backoff queue
- publish_history: publish success/failure timeline for analytics
- scheduler_conflicts: schedule collision detection records
- workspace_timezones: workspace-level timezone preferences
- notifications: owner/admin/editor notification center records
- central_audit_log: global action audit timeline
- subscription_plans: active commercial plans and pricing
- admin_subscriptions: subscription lifecycle and expiry snapshots per admin
- payment_requests: pending payment verification requests
- payment_history: immutable verified payment ledger
- system_backups: backup metadata and status tracking
- error_reports: captured runtime errors with source/context

## Future Roadmap

Flowza v1.1:

- Destination type expansion, recycle bin restore window, enterprise dashboard UI refinements

Flowza v2.0:

- Multi-network billing, advanced owner command center, backup restore orchestration, enterprise reporting

## License

Private Software  
Copyright © Nihaswi Tech  
Flowza v1.0  
All Rights Reserved
