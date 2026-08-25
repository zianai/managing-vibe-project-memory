# High-Impact External Actions

## Trigger

Activate this overlay for production deployment, publication, real-user or sensitive data, payment, messaging, account changes, security or safety controls, legal commitments, destructive/irreversible operations, or a similarly consequential external effect. Code that merely prepares an action is not execution.

## Action Identity And Record

Create a task-local action record when an action is authorized or attempted. `action_id` is unique per logical external effect; attempts/reconciliation remain attached to that identity rather than manufacturing a second logical effect. Its identity binds target, environment, bounded payload, and exact subject (commit, worktree, artifact hash, or immutable provider revision).

Record: authority source and limits; one-shot/idempotency data; preconditions; expiration/timeout; status; observed result; provider receipt when safe; reconciliation; and compensation/recovery path. Never store secrets.

Status is exactly one of `planned`, `authorized`, `executing`, `succeeded`,
`failed`, `unknown`, or `compensated`. Any claimed high-impact completion
requires action record(s), or the task must explicitly state
`external_effects: none`.

`authorization_basis` is lightweight evidence of bounded authority. It becomes required only when actual execution or completion is claimed; it does not require a versioned start package.

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
