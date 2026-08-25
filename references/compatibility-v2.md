# Compatibility With v1, v2.1, And v2.2

Dispatch by each project/task’s declared schema and protocol. Protocol 3.0 does not retroactively change older fields, hashes, review packages, approvals, or archived states.

- v1 records remain valid under their original contract.
- protocol 2.1 retains schema-v2 tasks, alignment schema 1, design schema 2, raw-file SHA-256 approval bindings, HTML artifact rules, and declared completion gates.
- protocol 2.2 retains alignment schema 2, design schema 3, Adaptive Review Package schema 1, canonical package-digest semantics, and declared completion gates.

Do not manufacture a v3 decision by wrapping or relabeling old evidence. Do not rewrite terminal archives for uniformity.

An unfinished legacy task may finish under its declared contract or migrate explicitly after a source-to-destination map and authority-conflict review. A harness change alone requires neither migration nor reapproval.

Run read-only migration preflight before writes:

```bash
python3 <skill-dir>/scripts/check_project_memory.py <project-root> --migration
```

For approved migration: preserve old records/history; create v3 facts only from current authority; carry optional overlays only while their trigger remains; keep old approvals bound to old subjects; and run focus plus full validation. Never alter protected/source-unknown work.

Legacy validation may remain stricter because it enforces the producing contract. Native v3 tasks must not inherit v2 package, readout, or fixed visual-gate requirements. A v2 task inside a v3-era archive is still checked under its historical protocol.

Unknown extension fields should be preserved. Report unsupported or contradictory mixed schemas without guessing or rewriting.
