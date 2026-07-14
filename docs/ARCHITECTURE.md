# ARCHITECTURE

Product: Flowza v1.0  
Version: Flowza v1.0.3

## Overview

Flowza uses a modular Python architecture with clear separation between routing, handlers, keyboard builders, and database access.

## Layers

- Entry layer:
  - bot.py initializes app, DB modules, routers, and polling
- Routing layer:
  - routers/callback_router.py dispatches callback_data actions
  - routers/message_router.py dispatches state-based messages
- Handler layer:
  - handlers/* implement destination, post, scheduler, settings, provisioning, approval, workspace, analytics, notification, and commercial behavior
- UI layer:
  - keyboards/* build inline keyboard markup
- Data layer:
  - database/* manages SQLite schema and persistence, including enterprise retry/history/notification/audit models and commercial subscription/payment/backup/error models
- Utility layer:
  - utils/* provides logging, permissions, and helper functions

## Design Notes

- Existing architecture is extended, not replaced.
- SQLite remains the v1.0 database engine.
- RBAC is implemented through role resolution and permission helpers.
- Approval workflow state is modeled per admin scope.
- Workspace scope is enforced through current workspace context and editor workspace assignments.
- Media and templates are persisted at workspace scope with search and rendering helpers.
- Enterprise scheduler reliability is implemented with retry queue processing and restart restoration.
- Central audit and notification services provide cross-module observability.
- Commercial controls enforce subscription-aware operational access for admin/editor publishing and scheduling.
- Error handling captures unhandled failures into persistent reports and owner alerts.

## Planned Architecture Extensions

- Payment verification queue hardening and multi-network billing adapters
- Backup restore orchestration pipeline

