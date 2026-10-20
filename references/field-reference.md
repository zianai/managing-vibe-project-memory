# Field Reference

Every field and value that `scripts/check_project_memory.py` reads or enforces
for protocol 3.0. Rows describe what the code does; anything not listed is not
checked mechanically. Unknown fields are allowed, nested data is allowed only
inside a top-level `x_*` extension, and every record uses the flat YAML subset
described in [continuity-kernel.md](continuity-kernel.md#flat-yaml-subset).
For mechanical rules this file and the checker are normative; the prose
references describe intent and claim no mechanical rule beyond these. The one
remaining exception is listed in [Known Disagreements](#known-disagreements).

## Common Rules

| Rule | Applies to | Values | Checker enforces |
| --- | --- | --- | --- |
| File reference | every `*_ref` field and every item of a `*_refs` list in task, handoff, review and action records (not `x_*`) | project-relative path, optional `#fragment` | not empty, not absolute, no `..`, no `scheme://` URI, stays inside the project, no symlink at or below the project root, exists, is a regular file |
| Path list | `protected_paths`, `parallel_overlap_paths`, `subject_paths` | project-relative paths | same containment and symlink rules; the path may be missing and may be a folder (`subject_paths` must name a regular file for `git:`/`worktree:`, and each item must be a string: quote a name that YAML reads as a number, boolean or null, such as `["001"]`) |
| Task id | `id`, `active_task`, task folder names | `T-<NNN>-<slug>` or `T-<AREA>-<NNN>-<slug>` (`AREA` is 2–12 uppercase letters/digits) | folder name and `id` must match the pattern; `id` must equal the folder name |
| Placeholders | `task.yaml` core fields, claim files, action-record required fields | none of `{{…}}`, `TODO`, `TBD`, `REPLACE ME`, `REPLACE THIS/THE/WITH`, `LOREM IPSUM`, template comments | a placeholder in a core `task.yaml` field is an error unless `status: proposed` with no `implementation_started` or completion claim; YAML comments and `x_*` extensions are not scanned. The initializer applies the same rule |
| Claim file | `handoff_ref`, `review_ref`, `completion_acceptance_ref`, `authority_ref`, `reconciliation_ref` and other claim refs | any readable file | not empty; text formats contain no placeholder |
| Decision file | `baseline_decision_ref`, `difference_decision_ref`, `merge_resolution_ref` | any readable file | claim-file rules plus at least 12 letters/digits of content |
| Output | every check | `ERROR`, `WARNING` | any `ERROR` exits `1`; `WARNING` lines alone exit `0` |

## `project/state.yaml`

| Field | Required / when | Allowed values | Checker enforces |
| --- | --- | --- | --- |
| `schema_version` | required | `3` (unquoted integer) | anything else is unsupported; `"3"` gets a hint to write `schema_version: 3` |
| `protocol_version` | required | `"3.0"` | anything else is unsupported |
| `project_id` | required | any | presence only |
| `project_name` | required | any | presence only |
| `status` | required | any | presence only |
| `active_task` | required | task id, or `null` | must match the task-id pattern; both default/`--focus` and `--full` require `work/active/<id>/` |
| `updated` | required | any | presence only |
| `focus_task` | forbidden | — | error: use `active_task` |
| `protected_paths` | forbidden | — | error: belongs in `task.yaml` |

## `task.yaml`

### Core

| Field | Required / when | Allowed values | Checker enforces |
| --- | --- | --- | --- |
| `schema_version` | required | `3` | anything else is unsupported; `"3"` gets an unquoted hint |
| `protocol_version` | required | `"3.0"` | exact match |
| `id` | required | task id | equals the folder name |
| `status` | required | any nonempty; `done`/`completed` claim completion; `proposed` may keep placeholders | not empty |
| `goal` | required | string or list | at least one nonempty value; risk wording produces a `WARNING` when `risk` is not `high` |
| `scope` | required | list or string | at least one nonempty value; scanned like `goal` |
| `non_goals` | required | list | presence only |
| `acceptance` | required | list or string | at least one nonempty value; whether it is satisfied is not checked |
| `risk` | required | `low`, `medium`, `high` | valid level; not below any `risk_reasons` floor; `high` whenever the task is high-impact |
| `risk_reasons` | required | see [Risk Reasons](#risk-reasons) | at least one nonempty reason; an unlisted value produces a `WARNING` |
| `protected_paths` | required | list of paths | path-list rules |
| `context_refs` | required | list of file refs | file-reference rules |
| `decision_refs` | required | list of file refs | file-reference rules |
| `evidence_refs` | required | list of file refs | file-reference rules |
| `updated` | required | any | presence only |

### Risk Reasons

| `risk_reasons` value | Risk floor | High-impact | Checker enforces |
| --- | --- | --- | --- |
| `local-reversible` | `low` | no | — |
| `cross-component` | `medium` | no | `risk` at least `medium` |
| `product-choice` | `medium` | no | `risk` at least `medium` |
| `reversible-migration` | `medium` | no | `risk` at least `medium` |
| `irreversible-or-destructive` | `high` | yes | `risk: high` |
| `real-user-or-sensitive-data` | `high` | yes | `risk: high` |
| `security-or-safety` | `high` | yes | `risk: high` |
| `difficult-migration` | `high` | yes | `risk: high` |
| `publication-or-deployment` | `high` | yes | `risk: high` |
| `payment-or-message` | `high` | yes | `risk: high` |
| `legal-impact` | `high` | yes | `risk: high` |
| `custom-<low\|medium\|high>:<slug>` | the named level | only `custom-high:<slug>` | `risk` at least the named level, e.g. `custom-medium:vendor-api` |
| any other value | none | no | accepted without a floor, with a `WARNING` that names the value, a close listed reason if there is one, and the `custom-` form |

### Effects And External Actions

| Field | Required / when | Allowed values | Checker enforces |
| --- | --- | --- | --- |
| `effect_reversibility` | optional | `irreversible` is high-impact; other values ignored | high-impact requires `risk: high` |
| `effect_data` | optional | `personal-or-sensitive` is high-impact | same |
| `effect_environment` | optional | `production` is high-impact | same |
| `effect_external` | optional | `message-or-publish`, `payment-or-legal` are high-impact | same |
| `effect_security_safety` | optional | `involved` is high-impact | same |
| `effect_user_impact` | optional | `direct` is high-impact | same |
| `external_effects` | high-impact completion without `action_refs` | `none`, or any description | any value other than `none` is high-impact; high-impact completion needs `action_refs` or `external_effects: none` |
| `action_refs` | optional | list of action-record file refs | any entry is high-impact and needs `risk: high`; each record is validated; `action_id` unique across records; see [Action Record](#action-record-front-matter) |
| `authorization_basis` | optional | slug; denied: `next`, `generic-next`, `continue`, `ok`, `okay`, `yes`, `silence`, `in-artifact-control`, `agent-relay`, `summarized-approval` (one list, shared with action records) | must be a lowercase slug and not a denied value |

### Claims And Completion

| Field | Required / when | Allowed values | Checker enforces |
| --- | --- | --- | --- |
| `completion_claim` | optional | `true` | `true`, or `status` `done`/`completed`, activates completion rules |
| `implementation_started` | optional | `true` | forbids placeholders and `unresolved_choices`; with `visual_alignment: reserved`, needs `visual_alignment_status` |
| `unresolved_choices` | optional | list | a nonempty list with `implementation_started: true` or a completion claim is an error |
| `completion_acceptance_ref` | completion when `risk: high`, `material_deviation: true`, `residual_risk` set, or `human_completion_reserved: true` | claim file | must be set; claim-file rules |
| `material_deviation` | optional | `true` | requires `completion_acceptance_ref` at completion |
| `residual_risk` | optional | any non-empty value | requires `completion_acceptance_ref` at completion |
| `human_completion_reserved` | optional | `true` | requires `completion_acceptance_ref` at completion |
| `result_status` | forbidden | — | error: use `completion_claim: true` |

High-impact completion additionally requires `review_ref` with a passing
`independent_actor` review (see [Review](#review-front-matter)), and every
`action_refs` group finished: `succeeded` or `compensated`, or `failed` with
`no-effect-confirmed`/`compensated-confirmed`, and no unreconciled `unknown`.
An action record without an `idempotency_key` belongs to no group and can only
be `planned`, so any completion claim with one is an error; remove an action
that will not run from `action_refs`.

### Handoff And Review

| Field | Required / when | Allowed values | Checker enforces |
| --- | --- | --- | --- |
| `handoff_ref` | required when `handoff_current: true` | claim file | claim-file rules |
| `handoff_current` | optional | `true`, `false` | `true` validates the handoff front matter (`task_ref`, subject freshness) |
| `handoff_subject_ref` | optional; has no effect | file ref | file-reference rules, then a `WARNING` that it has no effect: the handoff's own `subject_ref` binds the subject |
| `review_ref` | required when `review_current: true`, at high-impact completion, or with a conformance claim | claim file | claim-file rules; when required, the review front matter and body are validated |
| `review_current` | optional | `true` | activates review validation |
| `verification_mode`, `verification_status`, `verification_subject`, `verification_subject_ref`, `verification_subject_paths`, `verification_actor`, `verification_actor_modified_subject`, `review_subject`, `review_subject_ref`, `review_subject_paths`, `review_mode`, `review_verdict` | forbidden | — | error: these belong only in review front matter |

### Visual Alignment

| Field | Required / when | Allowed values | Checker enforces |
| --- | --- | --- | --- |
| `conformance_status` | optional (default `not_required`) | `not_required`, `pending`, `matched`, `changes_requested`, `differences_accepted` | value in the set; `matched` and `differences_accepted` are conformance claims |
| `approved_baseline_subject` | conformance claim | `provider:`/`artifact:` with revision and frame/node/page/screen identity, or `sha256:` | nonempty; provider form checked for identity; local form must be `sha256:` and match `approved_baseline_ref` |
| `approved_baseline_ref` | conformance claim with a `sha256:` baseline | visual artifact file | supported shape: PNG/JPEG/GIF/WebP (≥16 px), SVG, PDF, MP4/MOV/M4V, visual HTML (SVG, canvas, inline image, or `data-visual-surface`), Mermaid Markdown, JSON visual manifest |
| `implementation_render_subject` | conformance claim | same as baseline subject | same as baseline subject |
| `implementation_render_ref` | conformance claim with a `sha256:` render | visual artifact file | same shapes, except HTML is rejected as a render |
| `baseline_decision_ref` | conformance claim | decision file | must be set; decision-file rules |
| `difference_decision_ref` | `conformance_status: differences_accepted` | decision file | must be set; decision-file rules |
| `visual_alignment` | optional | `reserved` | with `implementation_started: true` or `conformance_status` other than `not_required`, requires `visual_alignment_status` |
| `visual_alignment_status` | when `visual_alignment: reserved` applies | `accepted`, `delegated` | value in the set |
| `approved_baseline_refs`, `implementation_render_refs` | forbidden | — | error: use the singular ref |

### Parallel Integration

| Field | Required / when | Allowed values | Checker enforces |
| --- | --- | --- | --- |
| `parallel_overlap_paths` | optional | list of paths | path-list rules; covered by `merge_resolution_subject_paths` once resolved |
| `integration_status` | optional | `resolved` and `merged` activate checks; other values free | — |
| `merge_resolution_ref` | `integration_status` `resolved`/`merged` | decision file | must be set; decision-file rules |
| `merge_resolution_subject` | `integration_status` `resolved`/`merged` | `git:`, `worktree:` or `patch:` subject | subject kind and freshness |
| `merge_resolution_subject_paths` | `integration_status` `resolved`/`merged` | list of paths | nonempty; must include every `parallel_overlap_paths` entry |
| `merge_resolution_subject_ref` | forbidden once resolved | — | error: cannot replace a combined source scope |

## Handoff Front Matter

Validated when the task sets `handoff_current: true`. The record is Markdown
with front matter, or `.yaml`/`.yml`.

| Field | Required / when | Allowed values | Checker enforces |
| --- | --- | --- | --- |
| `task_ref` | required | `work/active/<id>/task.yaml` or `work/archive/<id>/task.yaml` | exact string of this task's `task.yaml` path |
| `subject` | required | see [Subjects](#subjects) | subject rules; freshness for active tasks |
| `subject_ref` | `sha256:` subject | file ref | digest must match the file |
| `subject_paths` | `git:`/`worktree:` subject | list of paths | required for `git:` and `worktree:`; scope of the freshness check |
| other `*_ref`/`*_refs` | optional | file refs | file-reference rules |

## Review Front Matter

Validated when the task sets `review_current: true`, claims high-impact
completion, or claims visual conformance. The body outside the front matter
must contain at least 12 letters/digits of findings.

| Field | Required / when | Allowed values | Checker enforces |
| --- | --- | --- | --- |
| `task_ref` | required | this task's `task.yaml` path | exact match |
| `subject` | required | see [Subjects](#subjects) | subject rules; freshness for active tasks; `git:`, `worktree:` or `patch:` at high-impact completion with `action_refs` |
| `subject_ref` | `sha256:` subject | file ref | digest must match the file |
| `subject_paths` | `git:`/`worktree:` subject | list of paths | at high-impact completion must include every task `action_refs` entry and each action's `subject_ref`/`subject_paths` |
| `mode` | required | `self_check`, `fresh_context`, `independent_actor`, `human` | value in the set; `independent_actor` at high-impact completion |
| `actor_modified_subject` | high-impact completion | `true`, `false` | must be `false` at high-impact completion |
| `verdict` | high-impact completion or conformance claim | `passed`, `changes_requested`, `failed` | must be `passed`; any other value counts as not passed and is otherwise not checked |
| `action_refs` | high-impact completion | list of action-record refs | same set as the task's `action_refs` |
| `baseline_subject` | conformance claim | subject | equals the task's `approved_baseline_subject` |
| `implementation_render_subject` | conformance claim | subject | equals the task's `implementation_render_subject` |
| other `*_ref`/`*_refs` | optional | file refs | file-reference rules |

## Action Record Front Matter

Each `action_refs` entry: Markdown with front matter, or `.yaml`/`.yml`. Required
fields must not contain placeholders. "Execution statuses" are `authorized`,
`executing`, `succeeded`, `failed`, `unknown` and `compensated`.

| Field | Required / when | Allowed values | Checker enforces |
| --- | --- | --- | --- |
| `action_id` | required | nonempty | unique across the task's `action_refs` |
| `target` | required | nonempty | part of the idempotency identity |
| `environment` | required | nonempty | part of the idempotency identity |
| `payload_scope` | required | nonempty | part of the idempotency identity |
| `subject` | required | see [Subjects](#subjects) | nonempty; subject rules |
| `subject_ref` | `sha256:` subject | file ref | digest must match the file |
| `subject_paths` | `git:`/`worktree:` subject | list of paths | required for `git:` and `worktree:`; scope of the freshness check |
| `authorization_basis` | key always; value checked in execution statuses | `direct-human-instruction`, `durable-decision`, `platform-authority`, `external-attestation`, `delegated-authority`; denied: the `task.yaml` list (see [Effects And External Actions](#effects-and-external-actions)) | in execution statuses must be an allowed slug |
| `authority_ref` | key always; value in execution statuses | claim file | set and a valid claim file in execution statuses |
| `one_shot` | required | `true` | must be `true` |
| `idempotency_key` | key always; value in execution statuses | nonempty | records sharing a key share target, environment, payload scope and subject; at most one `succeeded`/`compensated` per key; a record without one blocks a completion claim |
| `expires_at` | required | ISO date or date-time | parseable; must be in the future while `authorized` or `executing` |
| `timeout_seconds` | required | positive integer | integer above `0` |
| `status` | required | `planned`, `authorized`, `executing`, `succeeded`, `failed`, `unknown`, `compensated` | value in the set |
| `observation` | required | substantive text | in execution statuses not empty, `none`, `unknown` or `not observed` |
| `compensation` | required | substantive text | same as `observation` |
| `retry_allowed` | `status: unknown` | `true`, `false` | must be `false` while `unknown` |
| `reconciliation_result` | optional | `effect-confirmed`, `no-effect-confirmed`, `compensated-confirmed`; other text is unresolved | a resolved value requires `reconciliation_ref`; `compensated` requires `compensated-confirmed` |
| `reconciliation_ref` | resolved `reconciliation_result`, or `status: compensated` | claim file | claim-file rules; resolves an `unknown` in its idempotency group |
| `reconciliation_outcome` | forbidden | — | error: use `reconciliation_result` |
| other `*_ref`/`*_refs` | optional | file refs | file-reference rules |

## Subjects

A subject binds a claim to exact content. Print one with
`python3 <skill-dir>/scripts/project_memory.py subject <project-root> <kind> <path>...`
and paste the output into the front matter. The command refuses (exit `2`) git-ignored files for
`git`/`worktree`, and any path containing `#`, which a reference reads as a
`#fragment`; it quotes names that YAML would otherwise read as a number, boolean
or null, so its output always reads back unchanged.

| Kind | Use when | Produce with | Active task: checker enforces | Archived task: checker enforces |
| --- | --- | --- | --- | --- |
| `git:<full-sha>` (40 or 64 hex) | the work is committed | `subject <root> git <path>...` (prints `subject` and `subject_paths`) | full 40/64-hex SHA (a branch, tag, `HEAD` or abbreviated SHA is an error, because it moves with new commits); commit exists; `subject_paths` required; each path is a regular file in the worktree or commit; paths unchanged since the commit and clean in `git status` | full SHA of an existing commit; `subject_paths` required |
| `worktree:<sha256>` | the work is not committed yet | `subject <root> worktree <path>...` (prints `subject` and `subject_paths`) | recomputed digest of `HEAD`, `git status`, the diff against `HEAD`, and untracked files under `subject_paths` (required) must match; the digest includes `HEAD`, so any new commit makes it stale; use `git:` for committed work; an untracked git-ignored file under `subject_paths` is an error, because its bytes are not in the digest (bind it with `sha256:`) | 64 hex characters |
| `patch:<sha256>` | still accepted alias of `worktree:`; don't use it in new records | `subject <root> worktree <path>...`, then use `worktree:` | same as `worktree:` | same as `worktree:` |
| `sha256:<hex>` | one artifact file (export, payload, render) | `subject <root> sha256 <path>` (prints `subject` and `subject_ref`) | SHA-256 of `subject_ref` matches | SHA-256 of `subject_ref` matches |
| `provider:<identity>` / `artifact:<identity>` | an external revision (design tool, registry) | written by hand from the provider's immutable revision | identity at least 8 characters without `current`, `draft`, `head`, `latest`, `main`, `master`, `mutable` or `working`; `subject_paths` must be current regular files; visual subjects also need a revision and a frame/node/page/screen identity | same |

## Known Disagreements

This file describes what the checker currently does. In one place a protocol
text still says something different:

1. Visual fields in the project template's `AGENTS.md`: it says a visual task always names `approved_baseline_subject`, `implementation_render_subject`, `baseline_decision_ref` and `conformance_status`; the checker requires them only for a conformance claim (`matched`, `differences_accepted`), as [visual-alignment.md](visual-alignment.md) says. The template stays unchanged within protocol 3.0 because `init_project_memory.py` accepts an existing `AGENTS.md` only if it matches the template byte for byte, so any edit would make `init` refuse every project initialized before it. Follow this file and visual-alignment.md.
