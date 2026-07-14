# TELEGRAM COMMANDS

Product: Flowza v1.0  
Version: Flowza v1.0.3

## Commercial Commands (Admin)

- /plans
  - Show active subscription plans and pricing.
- /subscription
  - Show current subscription state, expiry, and recent payment history.
- /renew <plan_code>
  - Create a payment request for a paid plan.
- /submitpayment <tx_hash>
  - Submit payment transaction hash and trigger TRC20 verification.

## Commercial Commands (Owner)

- /revenue
  - Show total verified payments and total USDT received.
- /payments
  - List recent verified payment rows.
- /subscribers
  - Show active subscriber count and total admin accounts.
- /expiredusers
  - Show expired and near-expiry subscriber counts.
- /paymentstats
  - Show aggregate payment and subscriber metrics.

## Owner Operations Commands

- /health
  - Show RAM, disk, and timezone health summary.
- /system
  - Show service and integration readiness summary.
- /database
  - Show SQLite file size and path.
- /backup
  - Create a manual backup archive and record metadata.
- /maintenance
  - Run retention cleanup and maintenance actions.
- /errors
  - List recent captured runtime errors.

## Existing Core Commands (Reference)

- /start
- /dashboard
- /channels
- /postdashboard
- /scheduler
- /settings
- /workspaces
- /approvalqueue

## Notes

- Commercial verification currently supports USDT on TRC20 only.
- Publishing and scheduling for Admin and Editor roles require an active subscription state.
- Owner role remains superuser and is not subscription-gated.
