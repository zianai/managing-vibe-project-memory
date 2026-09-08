# Parallel Harness Work

## Boundary

Activate only when separate harnesses really mutate concurrently and their outputs must be resumed or merged independently. Do not create a default workstream registry, lock service, graph, or role topology. `active_task` is recovery focus, not a concurrency lock; internal subagents remain outside this protocol.

## Git-Native Coordination

Prefer one branch/worktree per independently mutating harness, a recorded common base, exact source heads, and integration verification on the combined result. Semantic ownership or overlap annotations are hints, not locks or proof of resolution.

Complex harness topology belongs in a referenced native file. If a checker-readable extension is useful, keep `x_*` fields flat or place opaque topology under one top-level ignored extension block.

Pre-existing/source-unknown modified and untracked work remains protected. Never silently reset, clean, stash, overwrite, stage, or commit it.

Branch/worktree separation does not eliminate hostile concurrent rename between
check and use, hardlink aliases, or locally rewritten Git history. Resolve real
paths and recheck subjects at the mutation/merge boundary; treat Git and the
local filesystem as trusted operational inputs, not tamper-proof provenance.

## Handoff And Merge

At a real cross-harness handoff, create a task-local handoff only when Git/task/tests do not expose needed transient semantics. Front matter names a project-local `task_ref` and exact subject; the body records base/head or patch, dirty state, complete/incomplete work, checks, hazards, and next action. The receiver verifies it. Taking over the same boundary needs no new approval.

Before integration, confirm heads, protect unrelated local work, review conflicts semantically, run combined verification, and update `integration_status`. Overlap is resolved only when status is `resolved` or `merged` and the record references concrete resolution/merge evidence. Never silently choose the newest agent output.

## Verification Responsibility

Builder and verifier describe events, not fixed agent IDs. Modes are `self_check`, `fresh_context`, `independent_actor`, and `human`. Low reversible work may use self-check; medium work benefits from fresh context; high-impact work requires independent actor.

If a reviewer modifies the subject, its prior verdict is stale. Reverify the new commit, patch, or artifact and record the actual mode.
