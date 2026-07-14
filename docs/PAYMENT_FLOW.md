# PAYMENT FLOW

Product: Flowza v1.0  
Version: Flowza v1.0.3

## Scope

This document describes the production payment flow for commercial plans in Flowza.

Network:
- USDT TRC20

Required environment variables:
- USDT_TRC20_WALLET
- TRON_API_KEY

## End-to-End Flow

1. Admin checks plans.
- Command: /plans
- Source: subscription_plans table

2. Admin creates renewal request.
- Command: /renew <plan_code>
- Validation:
  - Plan exists
  - Plan is paid (trial cannot be purchased)
  - Receiver wallet configured
- Persistence:
  - payment_requests row with verification_status=pending

3. Admin submits transaction hash.
- Command: /submitpayment <tx_hash>
- Persistence:
  - Latest pending payment request for admin is updated with tx_hash

4. Verification against TronGrid events API.
- Endpoint pattern: /v1/transactions/{tx_hash}/events
- Validation rules:
  - Event contains USDT transfer
  - Receiver wallet matches configured wallet
  - Amount is greater than or equal to expected plan amount

5. Verification outcome.
- Success:
  - payment_requests marked verified
  - payment_history entry created
  - admin_subscriptions new active row inserted
  - admin_profiles status moved to active with updated expiry
  - user_roles for admin/editor scope re-enabled
  - owner/admin notifications emitted
- Failure:
  - payment_requests marked failed
  - verification details retained for audit

## Subscription Lifecycle

- Trial is auto-provisioned if no subscription exists.
- Daily sweep job recalculates status and disables expired admin/editor role activity.
- Expired subscriptions block publishing and scheduling for admin/editor users.

## Operational Safety

- Use one payment request per renewal attempt.
- Only submit trusted transaction hashes.
- Keep TRON_API_KEY and wallet configuration in secure environment management.
- Monitor /errors and /paymentstats regularly.
