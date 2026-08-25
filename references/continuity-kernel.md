# Continuity Kernel v3.0

## Boundary

The kernel makes work recoverable across sessions, agents, and harnesses. It does not orchestrate their internal execution. A capable incoming participant should locate the current focus, understand its boundary, inspect the real repository state, and continue without replaying chat or loading all history.

Persist information only when all three are true:

1. Future work needs it.
2. Git, code, tests, or current tooling cannot cheaply and reliably derive it.
3. It remains valid across the intended handoff boundary.

## Minimal Layout

```text
project-root/
  AGENTS.md
  project/state.yaml
  work/active/T-001-initial/task.yaml
```

Optional, event-triggered task files include `decisions.md`, `handoff.md`, `review.md`, `evidence/`, `design/`, and one or more Markdown action records. Milestones and harness adapters are optional. Empty future-facing packages must not be initialized by default.

## Authority And Writable Homes

Apply this precedence when facts conflict:

1. Current direct human instruction and platform rules
2. `project/state.yaml` for project recovery focus
3. Focus task `task.yaml` for current goal and boundary
4. Referenced durable decisions
5. Relevant implemented code, tests, and Git history
6. Handoff and review claims
7. Archived records and chat summaries

A higher source does not silently erase a lower one. Stop before an affected edit, expose the conflict, and record the resolution in the owning file.

| Fact | One writable home |
|---|---|
| Default recovery focus | `project/state.yaml` |
| Goal, scope, non-goals, acceptance, risk, status | task `task.yaml` |
| Durable downstream choice | task or project decision record |
| File bytes and chronology | Git |
| Outgoing progress claim | task `handoff.md` |
| Formal verification verdict | task `review.md` |
| Durable reproducible proof | task `evidence/` |
| High-impact external action state | task action record referenced by `action_refs` |

Prefer references over copied prose. Do not duplicate Git hashes merely to identify local committed content unless a review verdict must name its exact subject.

## Project State Schema v3

```yaml
schema_version: 3
protocol_version: "3.0"
project_id: SAMPLE
project_name: "Sample"
status: active
active_task: T-001-initial
updated: "2026-08-19"
```

`active_task` is the default recovery focus. It may point to proposed, blocked, or executing work and is never a repository-wide lock. Multiple directories may coexist in `work/active/`. A project may add fields without making them universal protocol requirements.

## Task Schema v3

```yaml
schema_version: 3
protocol_version: "3.0"
id: T-001-initial
status: proposed
goal: Deliver one observable outcome
scope: [src/]
non_goals: [Production deployment]
acceptance: [Relevant tests pass]
risk: low
risk_reasons: [local-reversible]
protected_paths: []
context_refs: []
decision_refs: []
evidence_refs: []
updated: "2026-08-19"
```

References are project-root-relative, remain inside the project, and must not
traverse symlinks. An external mutable link may appear only as context inside a
local referenced note; it is not authority. `scope` is a semantic boundary, not
a mandatory exact file allowlist. `protected_paths` is exact hard protection:
do not modify, stage, commit, delete, move, overwrite, or stash those paths.

Status is descriptive recovery metadata. Protocol 3.0 does not impose one fixed lifecycle or forbid project extensions. Only a declared claim activates the matching consistency rule: for example, `done` requires satisfied acceptance and no unresolved required overlay; passed verification requires an exact reviewed subject and verdict; design approval requires human evidence; an executed external action requires an action record.

Unknown extension fields are allowed and ignored safely unless they contradict a core field or activate a declared overlay.

## Recovery Algorithm

An incoming harness or coordinating agent:

1. Reads `AGENTS.md`.
2. Reads state and resolves `active_task`.
3. Reads that task and only its `context_refs` and `decision_refs`.
4. Reads `handoff_ref` only when the task says `handoff_current: true`.
5. Inspects current Git status before touching files.
6. Reads relevant code/tests and selectively follows activated evidence.
7. States material conflicts or assumptions; otherwise proceeds within the task boundary.

This is orientation, not an exhaustive repository scan. Archived work is loaded only when a current reference or decision depends on it.

Internal subagents receive a delegated capsule in the parent prompt: local goal, boundary, acceptance, relevant files, and hazards. They do not need to reload full project governance. The parent remains responsible for reconciling outputs with task memory.

## Event-Triggered Artifacts

### Decisions

Create a decision only when future work depends on a choice that code/Git cannot explain reliably. Record the question, decision, subject/version when staleness matters, scope/conditions, and what was not decided.

Natural human language is valid when the visible choice is singular and unambiguous. Do not require a magic phrase or duplicate hashes. Provider-backed artifacts need a stable revision; keep a local export only when provider-less recovery is material.

### Handoff

The outgoing agent creates or refreshes `handoff.md` without waiting for a human request when responsibility actually moves and task/Git/decisions/tests omit transient semantics needed next. This is an event response, not something an agent asks a human to request and not a human gate. Its YAML front matter owns a project-local task ref, exact subject, optional project-local subject ref, and bounded subject paths. The body records what is complete/incomplete, local state, observed checks, hazards, and next useful action without duplicating the subject metadata.

Skip handoff when the minimal kernel and repository already answer those questions. The task stores only `handoff_ref` and `handoff_current`; the artifact front matter owns its subject. Handoff is a fallible claim, not authority, approval, verification, or a replacement for inspecting Git. A changed subject sets `handoff_current: false` until refreshed.

### Review And Evidence

Create `review.md` only for a formal verdict. Its YAML front matter solely owns the project-local task ref, exact subject/ref/paths, reviewer mode (`self_check`, `fresh_context`, `independent_actor`, or `human`), whether the actor modified the subject, covered `action_refs`, and verdict. The task owns only `review_ref` and `review_current`. The body owns evidence, findings, and limitations. Builder and verifier are responsibilities/events, not mandatory static IDs or proof of independence.

A low-risk self-check may remain a transient test observation and need not create `review.md`. High-impact completion requires a current `independent_actor` review record whose `action_refs` cover every exact action record. If the reviewer modifies the subject, that record cannot establish independent verification of the changed subject.

Create durable evidence only when later reproduction, audit, visual comparison, or high-impact verification needs it. Test output that can be cheaply rerun need not always be copied into the repository.

## Validation Modes

- Default/focus mode validates state, recovery-focus task, refs, protected-path consistency, subject freshness, activated overlays, and contradictions between status and results.
- `--full` validates all managed active/archived records and completion/audit consistency.
- `--migration` is read-only and dispatches legacy schema/protocol validation without rewriting it.

Mechanical validation must not judge aesthetics, prose quality, agent topology, or implementation wisdom. It must not require fixed Markdown headings, minimum prose length, a singleton active task, static builder/verifier inequality, universal readout packages, or a fixed number/format of visual gates.

## Always-Hard Rules

- Resolve project and focus task without symlink redirection.
- Treat pre-existing/source-unknown modified or untracked work as owned; never silently reset, clean, stash, overwrite, stage, or commit it.
- Preserve `protected_paths` exactly.
- Never transform agent-relayed prose into human authorization.
- Re-align if scope, acceptance, or high-impact consequences change.
- Reconcile uncertain high-impact action results before retry.
- Keep completion, testing, independent verification, design approval, and target-user validation distinct.
- Invalidate a claim when its named commit, patch, artifact revision, or render changes.
- Treat concurrent rename between validation and use, hardlink aliases, and mutable or locally rewritten Git history as trust boundaries. Re-resolve and re-inspect at the action boundary; local validation is not tamper-proof provenance.
