---
action_id: "A-001"
target: "replace-with-exact-target"
environment: "replace-with-exact-environment"
payload_scope: "replace-with-bounded-payload"
subject: "replace-with-stable-payload-or-operation-subject"
authorization_basis: "replace-on-actual-execution-with-bounded-direct-human-instruction-or-valid-authority"
authority_ref: ""
one_shot: true
idempotency_key: ""
expires_at: "1970-01-01T00:00:00Z"
timeout_seconds: 30
status: planned
observation: "not attempted"
reconciliation_result: "not required before first attempt"
reconciliation_ref: ""
compensation: "none defined; stop and escalate"
retry_allowed: false
---

# High-impact action record

Replace the fail-closed placeholders before authorization. `action_id` is unique
per logical external effect. Use only `planned`, `authorized`, `executing`,
`succeeded`, `failed`, `unknown`, or `compensated`. Append provider receipts or
reconciliation evidence below; `unknown` keeps `retry_allowed: false` until the
project-local `reconciliation_ref` resolves actual external state.
