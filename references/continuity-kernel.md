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

Every field and value the checker enforces, for this task schema and every
other record, is listed in [field-reference.md](field-reference.md).

References are project-root-relative, remain inside the project, and must not
traverse symlinks. An external mutable link may appear only as context inside a
local referenced note; it is not authority. `scope` is a semantic boundary, not
a mandatory exact file allowlist. `protected_paths` is exact hard protection:
do not modify, stage, commit, delete, move, overwrite, or stash those paths.

Status is descriptive recovery metadata. Protocol 3.0 does not impose one fixed lifecycle or forbid project extensions. Only a declared claim activates the matching consistency rule: for example, passed verification requires an exact reviewed subject and verdict; design approval requires human evidence; an executed external action requires an action record.

`status: done` or `completed`, or `completion_claim: true` with any other status, claims completion; `result_status` is rejected as ambiguous. Satisfying `acceptance` before that claim is the claimant's responsibility: the checker cannot verify it, and enforces only the completion consequences, namely a passing review where one is required, `completion_acceptance_ref` where human acceptance is required, finished action records, and no `unresolved_choices`. `implementation_started: true` declares that implementation has begun; from then on, as after a completion claim, the task may hold no template placeholders and no `unresolved_choices`.

Unknown extension fields are allowed and ignored safely unless they contradict a core field or activate a declared overlay.

### Flat YAML Subset

State, task, handoff, review, and action records share one flat YAML subset (`scripts/flat_yaml.py`):

- Top-level `key: value` scalars and flow lists such as `[src/, "notes/a, b.md"]`; commas split items only outside quotes.
- Block lists directly under an empty `key:` line, with `- item` at column 0 or indented.
- `#` comments outside quotes, at line start or after whitespace (`risk: low  # local only`). A `#` with no space before it is part of the value, so `notes.md#section` keeps its fragment.
- Nested data only inside a top-level `x_*` extension, which the checker skips.

Nested mappings, block scalars (`|`, `>`), and duplicate keys are rejected with a message. `schema_version` is the unquoted integer `3`; `schema_version: "3"` is rejected with a hint to write `schema_version: 3`.

## Event-Triggered Artifacts

### Decisions

Create a decision only when future work depends on a choice that code/Git cannot explain reliably. Record the question, decision, subject/version when staleness matters, scope/conditions, and what was not decided.

Natural human language is valid when the visible choice is singular and unambiguous. Do not require a magic phrase or duplicate hashes. Provider-backed artifacts need a stable revision; keep a local export only when provider-less recovery is material.

### Handoff

The outgoing agent creates or refreshes `handoff.md` without waiting for a human request when responsibility actually moves and task/Git/decisions/tests omit transient semantics needed next. This is an event response, not something an agent asks a human to request and not a human gate. Its YAML front matter owns a project-local task ref, exact subject, optional project-local subject ref, and bounded subject paths. The body records what is complete/incomplete, local state, observed checks, hazards, and next useful action without duplicating the subject metadata.

Skip handoff when the minimal kernel and repository already answer those questions. The task stores only `handoff_ref` and `handoff_current`; the artifact front matter owns its subject, so a task-level `handoff_subject_ref` has no effect and produces a warning. Handoff is a fallible claim, not authority, approval, verification, or a replacement for inspecting Git. A changed subject sets `handoff_current: false` until refreshed.

### Review And Evidence

Create `review.md` only for a formal verdict. Its YAML front matter solely owns the project-local task ref, exact subject/ref/paths, reviewer mode (`self_check`, `fresh_context`, `independent_actor`, or `human`), whether the actor modified the subject, covered `action_refs`, and verdict (`passed`, `changes_requested`, or `failed`). The task owns only `review_ref` and `review_current`; review metadata copied into `task.yaml`, such as `review_mode`, `review_verdict`, or `verification_status`, is an error. The body owns evidence, findings, and limitations.

Whenever the review is checked (`review_current: true`, high-impact completion, or a visual conformance claim), `mode` must be one of the four modes. Where a passing review is required, only `verdict: passed` counts as passed; `changes_requested`, `failed`, or any other value does not. Builder and verifier are responsibilities/events, not mandatory static IDs or proof of independence.

A low-risk self-check may remain a transient test observation and need not create `review.md`. High-impact completion requires a current `independent_actor` review record whose `action_refs` cover every exact action record. If the reviewer modifies the subject, that record cannot establish independent verification of the changed subject.

Create durable evidence only when later reproduction, audit, visual comparison, or high-impact verification needs it. Test output that can be cheaply rerun need not always be copied into the repository.

## Validation Modes

- Default/focus mode validates state, recovery-focus task, refs, protected-path consistency, subject freshness, activated overlays, and contradictions between status and results.
- `--full` validates all managed active/archived records and completion/audit consistency, and, like focus mode, that a non-null `active_task` exists in `work/active/`.
- Freshness applies to current claims. For tasks under `work/archive/`, subjects are history and are not compared with today's worktree: a `git:` subject must name a commit that exists (the worktree need not match it or be clean); a `worktree:`/`patch:` digest cannot be recomputed after the fact, so only its 64-hex shape is checked; a `sha256:` subject is still verified against its artifact. This covers review, handoff, merge-resolution, and action-record subjects. Active tasks keep the full freshness rules.
- `ERROR` lines fail the check (exit `1`). `WARNING` lines follow the errors and are advisory; a check with only warnings exits `0`. Prose signals in `goal`/`scope` produce warnings only; declared `risk_reasons`, `effect_*`, `external_effects`, and `action_refs` set the risk floor. A `risk_reasons` value outside the listed reasons sets no floor and produces a warning; write an extension reason as `custom-<low|medium|high>:<slug>`.

Both modes require schema 3 / protocol 3.0 for every selected record. Other
declared versions are rejected without modifying them.

Mechanical validation must not judge aesthetics, prose quality, agent topology, or implementation wisdom. It must not require fixed Markdown headings, minimum prose length, a singleton active task, static builder/verifier inequality, universal readout packages, or a fixed number/format of visual gates.

### Archiving

Archive a task when it no longer belongs in the working set: it is done, cancelled, or superseded. Archiving is a move, not a completion check; it does not require `status: done`. Use the command rather than moving the folder by hand, because a plain move leaves every `work/active/<id>` reference dangling:

```bash
python3 <skill-dir>/scripts/project_memory.py archive <project-root> <task-id> --dry-run
python3 <skill-dir>/scripts/project_memory.py archive <project-root> <task-id>
```

- It moves `work/active/<id>/` to `work/archive/<id>/` with one rename, creating `work/archive/` if needed.
- It rewrites `work/active/<id>` to `work/archive/<id>` only in protocol records: `project/state.yaml`, every active task's `task.yaml`, and the front matter of the handoff, review, and action records those tasks reference (a `.yaml` record is rewritten whole). A longer id such as `<id>-v2` is never matched.
- Every other file keeps its bytes: artifacts, notes, decision bodies, Markdown bodies below the front matter, and other archived tasks, which are history and are never edited. A `sha256:` subject bound to such a file therefore stays valid. A `WARNING` names each file that still mentions the old path.
- If `project/state.yaml` has `active_task: <id>` (also written `active_task : <id>`), it becomes `active_task: null` with today's `updated`; any other focus is kept.
- It prints `MOVE`, `REWRITE`, `STATE`, and `WARNING` lines; `--dry-run` prints the same plan and changes nothing.
- It refuses (exit `2`, nothing changed) when:
  - the task id is invalid or missing, or `work/archive/<id>` exists;
  - a path it would move or rewrite contains a symlink;
  - `project/state.yaml` or an active `task.yaml` is missing, unreadable, or not schema 3 / protocol 3.0;
  - the move or a rewrite touches a path that any active task, the archived one included, lists in `protected_paths`;
  - the change would invalidate a claim the checker still validates: a `sha256:` subject whose file would be rewritten, or another active task's `git:`/`worktree:` subject whose paths would be moved or rewritten;
  - an archived record references a file inside the task being moved (archived history is never edited, so the reference would break);
  - in a Git repository, the task folder has uncommitted or untracked changes, or a file it would rewrite is untracked, ignored, or modified. Commit those first.
- Each rewrite replaces the file atomically. If a step fails, it restores every byte, verifies the result, and moves the folder back; if the rollback cannot be completed it exits `3`, lists each residue, and saves the original bytes to a backup folder.
- It never stages or commits. After a successful run it prints a `git add -A -- …` command that names only the moved folder and the other rewritten files.

Afterwards run `check --full`, stage with the printed command (not whole folders, which can sweep in someone else's uncommitted work), and commit. The archived task's claims are then checked as history (see above).

## Record Templates

Copy a template into the task directory only when its event occurs. These are
runtime starting points; the initializer deliberately does not copy them.

| Event | Template | Task reference |
| --- | --- | --- |
| A durable choice must survive handoff | [Decision](../assets/project-template/optional/decisions.md) | `decision_refs` |
| Responsibility crosses a boundary with otherwise lost context | [Handoff](../assets/project-template/optional/handoff.md) | `handoff_ref`, `handoff_current` |
| A formal verdict must be retained | [Review](../assets/project-template/optional/review.md) | `review_ref`, `review_current` |
| A high-impact action is authorized or attempted | [Action record](../assets/project-template/optional/action-record.md) | `action_refs` |

Replace template placeholders, including `{{TASK_ID}}`, and use project-root-relative
references. Bind claims to actual subject paths or artifact refs. Templates are
incomplete until filled with the observed facts; copying one does not establish
approval or a successful check.

## Always-Hard Rules

- Resolve the selected project root once to its real path (a symlinked root or ancestor is the user's environment and is allowed), then resolve the focus task and every authority path below it without symlink redirection.
- Treat pre-existing/source-unknown modified or untracked work as owned; never silently reset, clean, stash, overwrite, stage, or commit it.
- Preserve `protected_paths` exactly.
- Never transform agent-relayed prose into human authorization.
- Re-align if scope, acceptance, or high-impact consequences change.
- Reconcile uncertain high-impact action results before retry.
- Keep completion, testing, independent verification, design approval, and target-user validation distinct.
- Invalidate a claim when its named commit, patch, artifact revision, or render changes.
- Treat concurrent rename between validation and use, hardlink aliases, and mutable or locally rewritten Git history as trust boundaries. Re-resolve and re-inspect at the action boundary; local validation is not tamper-proof provenance.
