# OWNER OPERATIONS

Product: Flowza v1.0  
Version: Flowza v1.0.3

## Daily Checklist

1. Validate system health.
- /system
- /health
- /database

2. Review commercial status.
- /revenue
- /paymentstats
- /subscribers
- /expiredusers

3. Review operational risk.
- /errors
- /maintenance

4. Ensure backup coverage.
- /backup (manual on demand)
- Confirm scheduled daily and weekly backups are being created in assets/backups

## Alert Handling

Payment incidents:
- Confirm wallet and API key configuration.
- Validate submitted tx hash against expected plan amount.
- Check failed requests and ask admin to resubmit only valid hashes.

Subscription expiry spikes:
- Run /expiredusers and /payments together for context.
- Confirm daily subscription sweep is active.
- Notify impacted admins to renew via /plans and /renew.

Runtime failures:
- Use /errors for latest error UIDs.
- Correlate error time with logs for root-cause analysis.
- Prioritize bot availability, scheduler health, and payment verification integrity.

## Backup and Maintenance

Manual backup:
- /backup creates a zip archive and records metadata.

Scheduled backup:
- Daily backup job around 01:00.
- Weekly backup job on Sunday around 02:00.

Maintenance:
- /maintenance runs retention and cleanup logic for enterprise operational tables.

## Governance Notes

- Owner access is superuser and should remain restricted to trusted operators.
- Keep .env credentials private and rotate keys when required.
- Apply release updates with compile and runtime validation before production deployment.
