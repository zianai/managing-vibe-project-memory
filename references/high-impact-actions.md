# High-Impact External Actions

## Trigger

Activate this overlay for production deployment, publication, real-user or sensitive data, payment, messaging, account changes, security or safety controls, legal commitments, destructive/irreversible operations, or a similarly consequential external effect. Code that merely prepares an action is not execution.

The task owns its risk rating. Declarations activate the overlay mechanically: a high-impact `risk_reasons` entry, a high-impact `effect_*` value (`effect_reversibility: irreversible`, `effect_data: personal-or-sensitive`, `effect_environment: production`, `effect_external: message-or-publish` or `payment-or-legal`, `effect_security_safety: involved`, `effect_user_impact: direct`; other values are ignored), `external_effects` other than `none`, or any `action_refs`. The checker also scans `goal` and `scope` prose for consequential wording, but a match is only a `WARNING`: it never raises the floor or fails the check. If the effect is real, set `risk: high` or add the matching `risk_reasons` entry.

## Action Identity And Record

Create a task-local action record when an action is authorized or attempted. `action_id` is unique per logical external effect; attempts/reconciliation remain attached to that identity rather than manufacturing a second logical effect. Its identity binds target, environment, bounded payload, and exact subject (commit, worktree, artifact hash, or immutable provider revision).

Record: authority source and limits; one-shot/idempotency data; preconditions; expiration/timeout; status; observed result; provider receipt when safe; reconciliation; and compensation/recovery path. Never store secrets.

Status is exactly one of `planned`, `authorized`, `executing`, `succeeded`,
`failed`, `unknown`, or `compensated`. Any claimed high-impact completion
requires action record(s), or the task must explicitly state
`external_effects: none`.

`authorization_basis` is lightweight evidence of bounded authority; it does not require a versioned start package. Every action record carries the keys `authorization_basis`, `authority_ref`, `idempotency_key`, `expires_at`, `timeout_seconds`, `observation`, and `compensation`, even while `planned`. While `planned`, `authorization_basis`, `authority_ref`, `idempotency_key`, `observation`, and `compensation` may be `null`; in the execution statuses (`authorized`, `executing`, `succeeded`, `failed`, `unknown`, `compensated`) their values are required. `expires_at` and `timeout_seconds` need valid values in every status.

## Authority

Authority must cover exact consequence, target, environment, subject, and meaningful payload bounds. Plan approval does not imply execution approval unless the human clearly included execution. Agent-relayed summaries are not human authority. Re-align if scope or consequence grows.

## Ambiguous Outcomes

Treat timeout and callback/event ordering as order-independent observations. If outcome is ambiguous:

1. Mark it `unknown` with `retry_allowed: false`.
2. Query the destination using action identity or receipt.
3. Reconcile actual external state before retrying.
4. Retry only after non-execution is established or idempotency makes duplication impossible.

Record the conclusion in `reconciliation_result` and project-local
`reconciliation_ref`. Arrival order of timeout, callback, webhook, and poll
observations does not determine the result; reconciled external state does.

Never blind-retry payment, messaging, publication, destructive change, or another non-idempotent effect.

High-impact completion requires a current independent review record to inspect exact subject, authority, observed external state, and recovery path; its `action_refs` cover the exact action record(s). Verification does not accept residual risk for the human.
