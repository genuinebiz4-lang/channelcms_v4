# OWNER GUIDE

Product: Flowza v1.0  
Version: Flowza v1.0.1

## Purpose

The Owner is the single platform authority responsible for platform governance, not day-to-day customer content operations.

## Current Owner Capabilities (Implemented)

- Global superuser access through OWNER_ID fallback
- Access to destination management
- Access to post composer and publish actions
- Access to scheduler controls
- Access to settings dashboard

## Current Owner Workflows

1. Set OWNER_ID in environment configuration.
2. Start Flowza and verify startup logs.
3. Use dashboard modules to monitor and operate critical workflows.

## Planned Owner Capabilities

- Subscription and revenue monitoring
- VPS and health dashboard (CPU, RAM, disk, DB, API health)
- Global announcements
- Backup monitoring and restore controls
- Platform maintenance mode
- Notification center inbox

## Security Notes

- Keep BOT_TOKEN private.
- Restrict server access and rotate secrets regularly.
- Store backups securely and validate restore procedures.
