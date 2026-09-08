---
name: managing-vibe-project-memory
description: Maintain minimal repository-backed context for software-project recovery, decisions, handoffs, and reviews across sessions or agents, with risk-adaptive human, visual, and external-action alignment.
---

# Managing Vibe Project Memory

Keep a project recoverable without replaying chat. Persist a fact only when future
work needs it, code/Git/tests cannot reliably and cheaply derive it, and it
remains useful across the intended boundary.

This distribution supports schema 3 / protocol 3.0. Reject other declared
versions without modifying their records.

## Host-Neutral Use

Use this skill with any host that can read its Markdown and project files.
Resolve links below relative to this skill directory, not the target project.
Read references and templates directly; Python is needed only to run the
initialization and validation helpers, not to obtain instructions or templates.
If execution is unavailable, work with the readable records within available
capabilities and report mechanical checks as not run. Never claim equivalent
validation from reading alone.

## Recover Current Work

Read the project's root `AGENTS.md`, `project/state.yaml`, and the task named by
`active_task`. Follow only its `context_refs` and `decision_refs`; read
`handoff_ref` only when `handoff_current: true`. Inspect relevant Git state,
code, and tests before editing. `active_task` is a recovery focus; multiple
tasks can coexist.

Internal subagents need only their delegated goal, boundary, acceptance,
relevant paths, and hazards. Their coordinator integrates durable memory.
Do not impose agent counts, roles, topology, models, tools, prompts, code
architecture, branch names, or commit counts.

## Initialize And Validate

Preview before initialization:

```bash
python3 <skill-dir>/scripts/init_project_memory.py <project-root> --project-name "Project Name" --dry-run
python3 <skill-dir>/scripts/init_project_memory.py <project-root> --project-name "Project Name"
python3 <skill-dir>/scripts/check_project_memory.py <project-root>
```

Default initialization creates exactly `AGENTS.md`, `project/state.yaml`,
and `work/active/T-001-initial/task.yaml`. Replace the proposed task's
placeholders with the real goal, scope, non-goals, acceptance, and risk.
Optional adapters and milestones require explicit flags.

Initialization never overwrites existing files. Stop for incompatible state,
a root contract requiring manual merge, protected paths, or symlink redirection.
Preserve pre-existing and source-unknown changes.

The optional `scripts/project_memory.py init|check` dispatcher invokes these
same implementations. Its `guide` and `template` commands only print existing
resource files; they are not prerequisites for reading them.

Use default/`--focus` checks during work and `--full` for all current-protocol
tasks, including archives, before completion or audit.

## Load The Relevant Detail

- Read [continuity-kernel.md](references/continuity-kernel.md) when creating or
  updating records: schemas, field ownership, subjects, and claim freshness.
- Read [human-alignment.md](references/human-alignment.md) when a human-owned
  decision, material scope/risk change, or reserved acceptance matters.
- Read [visual-alignment.md](references/visual-alignment.md) when visual
  preference, unresolved IA/interaction, costly implementation, consequential
  UI, or design-conformance claims activate visual alignment.
- Read [high-impact-actions.md](references/high-impact-actions.md) for
  production, publication, sensitive data, payment, messaging, security, legal,
  or irreversible effects.
- Read [parallel-harness.md](references/parallel-harness.md) only when separate
  harnesses actually mutate concurrently and need independent recovery/merging.

## Record Events And Claims

Create decisions only for durable choices; handoffs only when responsibility
crosses a boundary and task/Git/decisions/tests omit needed transient semantics;
reviews only for formal verdicts. At a real handoff with otherwise lost context,
create or refresh the record without waiting for the human to request it.
Skip it when task/Git/decisions/tests already suffice. Create evidence and action records when their
use is triggered. Use the linked [record templates](references/continuity-kernel.md#record-templates)
as starting points, never as empty mandatory packages.

Keep implementation, test success, independent verification, human design
approval, completion acceptance, and target-user validation distinct. Bind
claims to the exact commit, patch, artifact, or provider revision; changing that
subject invalidates the claim.

Treat material authority conflicts as unresolved. Do not turn agent-relayed
permission into direct human authorization. Reconcile uncertain external
results before retrying. Reinspect paths and subjects at the action boundary:
local structural checks cannot eliminate concurrent rename, hardlink aliasing,
or rewritten-history trust risks.
