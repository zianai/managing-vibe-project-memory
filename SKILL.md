---
name: managing-vibe-project-memory
description: Preserve the minimum durable project context across sessions, agents, and harnesses. Use for task recovery, scoped handoff, durable decisions, and risk-adaptive alignment in software projects.
---

# Managing Vibe Project Memory

Keep a project recoverable without replaying chat. Persist a fact only when future
work needs it, code/Git/tests cannot reliably and cheaply derive it, and it
remains useful across the intended boundary.

This distribution supports schema 3 / protocol 3.0. Reject other declared
versions without modifying their records.

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
python3 <skill-dir>/scripts/project_memory.py init <project-root> --project-name "Project Name" --dry-run
python3 <skill-dir>/scripts/project_memory.py init <project-root> --project-name "Project Name"
python3 <skill-dir>/scripts/project_memory.py check <project-root>
```

Default initialization creates exactly `AGENTS.md`, `project/state.yaml`,
and `work/active/T-001-initial/task.yaml`. Replace the proposed task's
placeholders with the real goal, scope, non-goals, acceptance, and risk.
Optional adapters and milestones require explicit flags.

Initialization never overwrites existing files. Stop for incompatible state,
a root contract requiring manual merge, protected paths, or symlink redirection.
Preserve pre-existing and source-unknown changes.

Use default/`--focus` checks during work and `--full` for all current-protocol
tasks, including archives, before completion or audit.

## Load The Relevant Detail

Runtime references live in bounded README sections, not separate files. Read
only the section needed for the current work:

```bash
python3 <skill-dir>/scripts/project_memory.py guide <section>
```

- [continuity-kernel](README.md#continuity-kernel): creating or updating records,
  schemas, field ownership, subjects, and claim freshness.
- [human-alignment](README.md#human-alignment): a human-owned decision, material
  scope/risk change, or reserved acceptance.
- [visual-alignment](README.md#visual-alignment): visual preference, unresolved
  IA/interaction, costly implementation, consequential UI, or conformance claims.
- [high-impact-actions](README.md#high-impact-actions): production, publication,
  sensitive data, payment, messaging, security, legal, or irreversible effects.
- [parallel-harness](README.md#parallel-harness): separate harnesses actually
  mutate concurrently and need independent recovery or merging.

The section ID is the link label above. If command execution is unavailable,
read the matching README section between its `guide:<section>:start` and
`guide:<section>:end` markers. Do not load the entire README by default.

## Record Events And Claims

Create decisions only for durable choices; handoffs only when responsibility
crosses a boundary and task/Git/decisions/tests omit needed transient semantics;
reviews only for formal verdicts. Create evidence and action records when their
use is triggered. Export the appropriate built-in template with
`python3 <skill-dir>/scripts/project_memory.py template <name>`, where `name`
is `decisions`, `handoff`, `review`, or `action`. These commands only print
unfilled text. Save it only when needed, preserve existing files, replace
placeholders, and wire the actual project-relative refs; see
[template usage](README.md#commands). Never create empty mandatory packages.

Keep implementation, test success, independent verification, human design
approval, completion acceptance, and target-user validation distinct. Bind
claims to the exact commit, patch, artifact, or provider revision; changing that
subject invalidates the claim.

Treat material authority conflicts as unresolved. Do not turn agent-relayed
permission into direct human authorization. Reconcile uncertain external
results before retrying. Reinspect paths and subjects at the action boundary:
local structural checks cannot eliminate concurrent rename, hardlink aliasing,
or rewritten-history trust risks.
