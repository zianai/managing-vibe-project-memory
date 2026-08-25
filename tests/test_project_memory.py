from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
INIT_SCRIPT = SKILL_ROOT / "scripts" / "init_project_memory.py"
CHECK_SCRIPT = SKILL_ROOT / "scripts" / "check_project_memory.py"

# macOS exposes /var as a system symlink. Use its canonical target so tests that
# create their own symlinks exercise the selected paths rather than that global alias.
tempfile.tempdir = str(Path(tempfile.gettempdir()).resolve())


def run_script(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def write_state(
    project: Path,
    schema_version: int,
    *,
    protocol_version: str | None = None,
    legacy_archive_ids: tuple[str, ...] = (),
    adopted_at: str = "2026-08-10T00:00:00+08:00",
    adoption_commit: str | None = None,
    version_adopted_at: str | None = None,
) -> None:
    # Protocol 3.0 initialization is intentionally only three files. Legacy
    # fixtures construct their own historical scaffold so compatibility tests
    # do not make the live initializer carry obsolete default packages.
    active_root = project / "work" / "active"
    if active_root.is_dir():
        for child in active_root.iterdir():
            task_file = child / "task.yaml"
            if child.is_dir() and (
                child.name == "T-001-initial"
                or (
                    task_file.is_file()
                    and 'protocol_version: "3.0"' in task_file.read_text(encoding="utf-8")
                )
            ):
                shutil.rmtree(child)
    for relative in (
        "project/decisions",
        "milestones",
        "work/active",
        "work/archive",
        "templates/task",
    ):
        (project / relative).mkdir(parents=True, exist_ok=True)
    legacy_files = {
        "CLAUDE.md": "# Claude\nRead AGENTS.md.\n",
        "CODEX.md": "# Codex\nRead AGENTS.md.\n",
        "project/charter.md": "# Charter\nLegacy compatibility fixture.\n",
        "project/architecture.md": "# Architecture\nLegacy compatibility fixture.\n",
        "project/glossary.md": "# Glossary\nLegacy compatibility fixture.\n",
    }
    for relative, content in legacy_files.items():
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(content, encoding="utf-8")
    template_headings = {
        "handoff.md": (
            "Execution Basis", "Universal Alignment Baseline", "Approved Design Baseline",
            "Delivered", "Changed Files", "Verification", "Acceptance Criteria",
            "Human Readout", "Design Differences", "Risks And Open Questions", "Git", "Next Action",
        ),
        "review.md": (
            "Review Basis", "Engineering Findings", "Human Readout Findings",
            "Design Conformance Findings", "Acceptance Decision", "Residual Risk",
        ),
    }
    for name, headings in template_headings.items():
        (project / "templates" / "task" / name).write_text(
            "# Template\n\n" + "\n\n".join(f"## {heading}\nTODO" for heading in headings) + "\n",
            encoding="utf-8",
        )
    protocol_field = ""
    if protocol_version:
        legacy = ", ".join(legacy_archive_ids)
        commit_value = f'"{adoption_commit}"' if adoption_commit else "null"
        version_field = (
            f'governance_protocol_version_adopted_at: "{version_adopted_at or adopted_at}"\n'
            if protocol_version == "2.2"
            else ""
        )
        protocol_field = f'''governance_protocol_version: "{protocol_version}"
governance_protocol_adopted_at: "{adopted_at}"
{version_field}governance_protocol_adoption_commit: {commit_value}
legacy_archive_ids: [{legacy}]
'''
    (project / "project" / "state.yaml").write_text(
        f'''schema_version: {schema_version}
{protocol_field}project_id: "TEST"
project_name: "Test Project"
status: active
active_milestone: null
active_task: null
updated: "2026-08-09"
source_of_truth: project/state.yaml
''',
        encoding="utf-8",
    )


def make_task(
    project: Path,
    *,
    task_id: str = "T-M01-001-demo",
    location: str = "active",
    status: str = "proposed",
    schema_version: int = 2,
    task_types: tuple[str, ...] = ("engineering",),
    alignment_mode: str = "text",
    design_ref: str | None = None,
    priority: str = "P1",
    protocol_version: str | None = None,
    risk_level: str | None = None,
    alignment_ref: str | None = None,
    builder_id: str = "builder-agent",
    verifier_id: str = "independent-verifier",
) -> Path:
    task_dir = project / "work" / location / task_id
    (task_dir / "evidence").mkdir(parents=True)
    v2_fields = ""
    if schema_version == 2:
        types = ", ".join(task_types)
        design_value = design_ref if design_ref is not None else "null"
        v2_fields = f'''schema_version: 2
task_types: [{types}]
alignment_mode: {alignment_mode}
design_governance_ref: {design_value}
'''
    protocol_fields = ""
    if protocol_version is not None:
        alignment_value = alignment_ref if alignment_ref is not None else "null"
        protocol_fields = f'''protocol_version: "{protocol_version}"
risk_level: {risk_level or "low"}
alignment_governance_ref: {alignment_value}
builder_id: {builder_id}
verifier_id: {verifier_id}
'''
    (task_dir / "task.yaml").write_text(
        f'''{v2_fields}{protocol_fields}id: {task_id}
title: Test task
status: {status}
milestone: M01
owner: builder
verifier: independent-verifier
priority: {priority}
created: 2026-08-09
updated: 2026-08-09
goal: Exercise project memory validation
allowed_files: [src/example.py]
forbidden_files: []
acceptance_criteria: [Governance rule is enforced]
dependencies: []
commits: []
verification_status: pending
not_committed_reason: Test fixture is intentionally uncommitted
''',
        encoding="utf-8",
    )
    substantive = {
        "brief.md": "# Brief\nValidate the requested governance behavior with a reproducible fixture.\n",
        "decisions.md": """# Decisions
The project owner selected the recorded alignment scope.

## Experience approval
The project owner approved the exact experience artifact for this task.

## Visual approval
The project owner approved the exact visual artifact for this task.

## Accepted differences
The project owner accepted the listed implementation differences.

## P0 human waiver
The project owner explicitly authorized the narrow emergency implementation.

## Human start alignment confirmation
The project owner confirmed the exact start alignment for this task.

## Human decision checkpoint confirmation
The project owner confirmed the exact decision checkpoint for this task.

## Human readout acceptance
The project owner accepted the exact completion readout for this task.
""",
        "handoff.md": """# Implementation Handoff

## Execution Basis
The builder loaded the exact task boundary, authority chain, risk record, and current alignment artifacts before making changes.

## Universal Alignment Baseline
The recorded start artifact and any material-decision checkpoint remain hash-bound to this task's declared execution scope.

## Approved Design Baseline
This fixture has no human-visible interface, so visual design approval is not applicable to its engineering-only behavior.

## Delivered
The implementation now enforces the requested governance invariant and reports an actionable failure when the invariant is violated.

## Changed Files
Only the task-scoped validation fixture and its corresponding checker behavior changed for this bounded test outcome.

## Verification
The checker command was executed against both valid and invalid fixtures, and the observed exit codes matched the acceptance boundary.

## Acceptance Criteria
The governance rule passes for a valid fixture and fails closed for the deliberately invalid condition covered by this test.

## Human Readout
The versioned Human Readout explains the before-and-after behavior, preserved boundaries, evidence confidence, and next lifecycle action.

## Design Differences
No visual baseline applies, and no material difference from the confirmed nonvisual start alignment was observed during comparison.

## Risks And Open Questions
The fixture proves the specified mechanical invariant but does not authenticate a declared human identity or external evidence source.

## Git
The fixture is intentionally uncommitted, and task.yaml records that bounded reason instead of claiming a repository commit.

## Next Action
An independent verifier should reproduce the checker result and compare this handoff with the exact Human Readout before completion.
""",
        "review.md": """# Independent Review

## Review Basis
The independent verifier inspected the exact fixture, alignment hashes, checker output, and task-local evidence referenced by the handoff.

## Engineering Findings
No blocking engineering finding remains within the tested invariant, and both the passing and fail-closed paths were reproduced.

## Human Readout Findings
The Human Readout accurately separates the delivered outcome, preserved boundaries, evidence confidence, and unresolved trust limits.

## Design Conformance Findings
No human-visible interface is in scope, so visual conformance is not applicable and no owner aesthetic judgment is claimed.

## Acceptance Decision
Engineering verification passed for the bounded fixture; this review does not impersonate owner acceptance or target-user validation.

## Residual Risk
The local records remain trusted project input rather than authenticated identity or tamper-proof external provenance.
""",
    }
    for name, content in substantive.items():
        (task_dir / name).write_text(content, encoding="utf-8")
    return task_dir


def png_data_uri(width: int = 160, height: int = 240) -> str:
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            rows.extend(((x * 7 + y * 3) % 256, (x * 5 + y * 11) % 256, (x * 13 + y * 2) % 256))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(rows), level=6))
        + chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def write_html(task_dir: Path, relative: str, kind: str, *, body: str | None = None) -> tuple[str, str]:
    path = task_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    required = {
        "experience-alignment": (
            "L0 boundary",
            "L1 journey",
            "Key alternatives",
            "L2 page map",
            "L3 complete screens",
            "State coverage",
            "Approval requested",
        ),
        "visual-alignment": (
            "Selected visual language",
            "Actual device frames",
            "Dynamic Type",
            "Complete key states",
            "Mapping to approved experience",
            "Approval requested",
            "Experience context",
            "User journey",
            "Affected page relationship",
            "Affected states",
        ),
        "design-conformance": (
            "Baseline identity",
            "Capture environment",
            "Page-state comparison",
            "Required state matrix",
            "Difference register",
            "Independent disposition",
        ),
    }
    sections = "".join(
        f"<section><h2>{heading}</h2><p>This section provides concrete, task-specific, independently reviewable detail for {heading.lower()} and its exact decision boundary.</p></section>"
        for heading in required[kind]
    )
    captures = ""
    if kind == "design-conformance":
        raster = png_data_uri()
        captures = f'''<figure data-conformance-capture="approved" data-page-state="primary-normal"><svg role="img" aria-label="Approved design capture" width="320" height="480" viewBox="0 0 320 480"><rect x="0" y="0" width="320" height="480" fill="#ffffff"></rect><circle cx="160" cy="120" r="56" fill="#3355aa"></circle><path d="M40 260 L280 260 L280 420 L40 420 Z" fill="#dde4ff"></path></svg></figure>
<figure data-conformance-capture="implementation" data-page-state="primary-normal"><img alt="Implementation capture" src="{raster}"></figure>'''
    content = body or f'''<!doctype html>
<html lang="en" data-project-memory-artifact="{kind}" data-task-id="{task_dir.name}" data-artifact-version="v1">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Alignment artifact</title></head>
<body><main><h1>Alignment artifact</h1><p>This self-contained artifact records a complete representative state, its information hierarchy, expected behavior, and owner decision boundary for reproducible human review.</p>{sections}{captures}</main></body>
</html>
'''
    path.write_text(content, encoding="utf-8")
    return relative, hashlib.sha256(content.encode("utf-8")).hexdigest()


def yaml_value(value: object) -> str:
    if value is None:
        return "null"
    return str(value)


def write_decision_binding(
    task_dir: Path,
    heading: str,
    *,
    decision_kind: str,
    artifact_path: str,
    artifact_version: str,
    artifact_sha256: str,
    gate: str,
    scope: str,
    decision_outcome: str | None = None,
) -> str:
    expected_outcomes = {
        "start-direction": "recorded",
        "start-confirmation": "confirmed",
        "h2-confirmation": "confirmed",
        "completion-acceptance": "accepted",
        "experience-approval": "approved",
        "visual-approval": "approved",
        "difference-acceptance": "accepted",
        "emergency-waiver": "approved",
        "risk-downgrade": "approved",
    }
    outcome = decision_outcome or expected_outcomes[decision_kind]
    decisions = task_dir / "decisions.md"
    content = decisions.read_text(encoding="utf-8")
    section = f'''## {heading}
The project owner made this version-bound decision for the stated scope.

Decision outcome: {outcome}

<!-- project-memory-decision-binding
task-id: {task_dir.name}
decision-kind: {decision_kind}
artifact-path: {artifact_path}
artifact-version: {artifact_version}
artifact-sha256: {artifact_sha256}
gate: {gate}
decision-outcome: {outcome}
scope: {scope}
-->
'''
    pattern = re.compile(
        rf"^## {re.escape(heading)}\s*$.*?(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    if pattern.search(content):
        content = pattern.sub(section.rstrip() + "\n\n", content)
    else:
        content = content.rstrip() + "\n\n" + section
    decisions.write_text(content, encoding="utf-8")
    anchor = re.sub(r"[^a-z0-9\s-]", "", heading.lower())
    anchor = re.sub(r"[\s-]+", "-", anchor).strip("-")
    return f"decisions.md#{anchor}"


def write_design(
    task_dir: Path,
    *,
    gate_profile: str = "two_gate",
    experience_status: str | None = None,
    visual_status: str = "approved",
    conformance_status: str = "not_started",
    emergency_waiver_ref: str | None = None,
    difference_approval: bool = True,
) -> Path:
    if experience_status is None:
        experience_status = "not_required" if gate_profile == "one_gate" else "approved"

    values: dict[str, object] = {
        "schema_version": 2,
        "task_id": task_dir.name,
        "gate_profile": gate_profile,
        "target_maturity": "owner_approved",
        "current_maturity": "design_candidate",
        "experience_status": experience_status,
        "experience_ref": None,
        "experience_sha256": None,
        "experience_approved_by": None,
        "experience_approved_at": None,
        "experience_approval_ref": None,
        "visual_status": visual_status,
        "visual_ref": None,
        "visual_sha256": None,
        "visual_approved_by": None,
        "visual_approved_at": None,
        "visual_approval_ref": None,
        "conformance_status": conformance_status,
        "conformance_ref": None,
        "conformance_sha256": None,
        "difference_approved_by": None,
        "difference_approved_at": None,
        "difference_approval_ref": None,
        "emergency_waiver_ref": emergency_waiver_ref,
    }
    for prefix, status, kind in (
        ("experience", experience_status, "experience-alignment"),
        ("visual", visual_status, "visual-alignment"),
    ):
        if status in {"draft", "awaiting_human", "changes_requested", "approved"}:
            ref, digest = write_html(task_dir, f"design/{prefix}-v1.html", kind)
            values[f"{prefix}_ref"] = ref
            values[f"{prefix}_sha256"] = digest
        if status == "approved":
            values[f"{prefix}_approved_by"] = "Project Owner"
            values[f"{prefix}_approved_at"] = "2026-08-09T12:00:00+08:00"
            values[f"{prefix}_approval_ref"] = write_decision_binding(
                task_dir,
                f"{prefix.title()} approval",
                decision_kind=f"{prefix}-approval",
                artifact_path=str(values[f"{prefix}_ref"]),
                artifact_version="v1",
                artifact_sha256=str(values[f"{prefix}_sha256"]),
                gate=f"{prefix}-alignment",
                scope=f"Approve the exact {prefix} gate artifact and only its documented task boundary.",
            )

    if conformance_status in {
        "pending_review",
        "matched",
        "changes_requested",
        "accepted_with_differences",
    }:
        ref, digest = write_html(
            task_dir,
            "evidence/2026-08-09-design-conformance.html",
            "design-conformance",
        )
        values["conformance_ref"] = ref
        values["conformance_sha256"] = digest
    if conformance_status == "accepted_with_differences" and difference_approval:
        values["difference_approved_by"] = "Project Owner"
        values["difference_approved_at"] = "2026-08-09T13:00:00+08:00"
        values["difference_approval_ref"] = write_decision_binding(
            task_dir,
            "Accepted differences",
            decision_kind="difference-acceptance",
            artifact_path=str(values["conformance_ref"]),
            artifact_version="v1",
            artifact_sha256=str(values["conformance_sha256"]),
            gate="design-conformance",
            scope="Accept only the explicitly listed implementation differences in this conformance report.",
        )

    design_path = task_dir / "design" / "design.yaml"
    design_path.parent.mkdir(parents=True, exist_ok=True)
    design_path.write_text(
        "".join(f"{key}: {yaml_value(value)}\n" for key, value in values.items()),
        encoding="utf-8",
    )
    return design_path


def replace_yaml_value(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text(
        "\n".join(f"{key}: {value}" if line.startswith(f"{key}:") else line for line in lines)
        + "\n",
        encoding="utf-8",
    )


def git(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(project), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def establish_legacy_adoption_anchor(
    project: Path,
    *,
    commit_record: bool = True,
) -> str:
    if not (project / ".git").exists():
        if git(project, "init", "-q").returncode != 0:
            raise AssertionError("could not initialize Git fixture")
        git(project, "config", "user.name", "Project Memory Test")
        git(project, "config", "user.email", "memory-test@example.invalid")
    git(project, "add", "-A")
    committed = git(project, "commit", "-q", "-m", "protocol adoption anchor")
    if committed.returncode != 0:
        raise AssertionError(committed.stderr)
    anchor = git(project, "rev-parse", "HEAD").stdout.strip()
    replace_yaml_value(
        project / "project" / "state.yaml",
        "governance_protocol_adoption_commit",
        f'"{anchor}"',
    )
    if commit_record:
        git(project, "add", "project/state.yaml")
        recorded = git(project, "commit", "-q", "-m", "record adoption anchor")
        if recorded.returncode != 0:
            raise AssertionError(recorded.stderr)
    return anchor


def write_markdown_artifact(
    task_dir: Path,
    relative: str,
    kind: str,
    heading: str,
    *,
    mermaid: bool = False,
) -> tuple[str, str]:
    path = task_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    diagram = """
```mermaid
flowchart LR
    A[Human intent] --> B[Bounded execution]
    B --> C[Reproducible evidence]
```
""" if mermaid else ""
    required_sections = {
        "human-start-alignment": (
            "Outcome And H0 Boundary",
            "Scope And Non-goals",
            "Acceptance And Evidence",
            "Risk Assessment",
            "H1 Execution Boundary",
            "Assumptions And Unknowns",
        ),
        "human-decision-checkpoint": (
            "Trigger",
            "Options And Tradeoffs",
            "Recommendation",
            "Human Decision",
            "AI Autonomous Boundary",
        ),
        "human-readout": (
            "Outcome",
            "Before And After",
            "Boundaries Preserved",
            "Acceptance Map",
            "Evidence And Confidence",
            "Residual Risk And Unknowns",
            "Next Decision",
        ),
    }
    sections = "\n".join(
        f"## {section}\n\nThe recorded human-readable statement for {section.lower()} is specific, bounded, and independently reviewable.\n"
        for section in required_sections[kind]
    )
    content = f'''<!-- project-memory-artifact: {kind} -->
<!-- task-id: {task_dir.name} -->
<!-- artifact-version: v1 -->

# {heading}

This versioned artifact records the human-readable goal, boundary, expected outcome, exclusions, risk posture, and evidence needed to keep autonomous execution aligned with the project owner's intent.
{diagram}
{sections}
'''
    path.write_text(content, encoding="utf-8")
    return relative, hashlib.sha256(content.encode("utf-8")).hexdigest()


def write_alignment(
    task_dir: Path,
    *,
    risk_level: str = "low",
    alignment_mode: str = "text",
    start_status: str = "direct_instruction",
    decision_status: str = "not_required",
    readout_status: str = "not_started",
    material_deviation: bool = False,
    waiver_used: bool = False,
    unresolved_risk: bool = False,
    h2_required: bool | None = None,
    risk_factors: tuple[str, ...] | None = None,
    risk_downgrade: bool = False,
    effect_reversibility: str | None = None,
    effect_data: str | None = None,
    effect_environment: str | None = None,
    effect_external: str | None = None,
    effect_security_safety: str | None = None,
    effect_user_impact: str | None = None,
) -> Path:
    start_ref, start_sha = write_markdown_artifact(
        task_dir,
        "alignment/start-v1.md",
        "human-start-alignment",
        "Human Start Alignment",
        mermaid=alignment_mode == "diagram",
    )
    if risk_factors is None:
        risk_factors = {
            "low": ("local-reversible",),
            "medium": ("cross-component",),
            "high": ("security-or-safety",),
        }[risk_level]
    effect_defaults = {
        "low": ("reversible", "none", "local-only", "none", "none", "none"),
        "medium": (
            "partially_reversible",
            "internal",
            "shared-nonproduction",
            "draft-only",
            "none",
            "indirect",
        ),
        "high": (
            "irreversible",
            "personal-or-sensitive",
            "production",
            "message-or-publish",
            "involved",
            "direct",
        ),
    }[risk_level]
    effective_h2_required = (
        decision_status != "not_required" or material_deviation or waiver_used
        if h2_required is None
        else h2_required
    )
    values: dict[str, object] = {
        "schema_version": 1,
        "protocol_version": '"2.1"',
        "task_id": task_dir.name,
        "risk_level": risk_level,
        "risk_factors": f"[{', '.join(risk_factors)}]",
        "risk_downgrade_ref": None,
        "start_status": start_status,
        "start_ref": start_ref,
        "start_sha256": start_sha,
        "start_authority_by": "Project Owner" if start_status in {"direct_instruction", "confirmed"} else None,
        "start_authority_at": "2026-08-09T14:00:00+08:00" if start_status in {"direct_instruction", "confirmed"} else None,
        "start_authority_ref": "decisions.md#human-start-alignment-confirmation" if start_status in {"direct_instruction", "confirmed"} else None,
        "decision_status": decision_status,
        "decision_ref": None,
        "decision_sha256": None,
        "decision_confirmed_by": None,
        "decision_confirmed_at": None,
        "decision_confirmation_ref": None,
        "readout_status": readout_status,
        "readout_ref": None,
        "readout_sha256": None,
        "completion_accepted_by": None,
        "completion_accepted_at": None,
        "completion_acceptance_ref": None,
        "material_deviation": str(material_deviation).lower(),
        "waiver_used": str(waiver_used).lower(),
        "unresolved_risk": str(unresolved_risk).lower(),
        "h2_required": str(effective_h2_required).lower(),
        "effect_reversibility": effect_reversibility or effect_defaults[0],
        "effect_data": effect_data or effect_defaults[1],
        "effect_environment": effect_environment or effect_defaults[2],
        "effect_external": effect_external or effect_defaults[3],
        "effect_security_safety": effect_security_safety or effect_defaults[4],
        "effect_user_impact": effect_user_impact or effect_defaults[5],
    }
    if decision_status != "not_required":
        ref, digest = write_markdown_artifact(
            task_dir,
            "alignment/decision-v1.md",
            "human-decision-checkpoint",
            "Human Decision Checkpoint",
        )
        values["decision_ref"] = ref
        values["decision_sha256"] = digest
    if decision_status == "confirmed":
        values["decision_confirmed_by"] = "Project Owner"
        values["decision_confirmed_at"] = "2026-08-09T15:00:00+08:00"
        values["decision_confirmation_ref"] = write_decision_binding(
            task_dir,
            "Human decision checkpoint confirmation",
            decision_kind="h2-confirmation",
            artifact_path=str(values["decision_ref"]),
            artifact_version="v1",
            artifact_sha256=str(values["decision_sha256"]),
            gate="human-decision-checkpoint",
            scope="Confirm this exact H2 decision checkpoint and its bounded consequence only.",
        )
    if readout_status != "not_started":
        ref, digest = write_markdown_artifact(
            task_dir,
            "alignment/readout-v1.md",
            "human-readout",
            "Human Readout",
        )
        values["readout_ref"] = ref
        values["readout_sha256"] = digest
    if readout_status == "accepted":
        values["completion_accepted_by"] = "Project Owner"
        values["completion_accepted_at"] = "2026-08-09T16:00:00+08:00"
        values["completion_acceptance_ref"] = write_decision_binding(
            task_dir,
            "Human readout acceptance",
            decision_kind="completion-acceptance",
            artifact_path=str(values["readout_ref"]),
            artifact_version="v1",
            artifact_sha256=str(values["readout_sha256"]),
            gate="human-readout",
            scope="Accept the exact completion readout and its explicitly disclosed residual risk.",
        )
    if start_status in {"direct_instruction", "confirmed"}:
        values["start_authority_ref"] = write_decision_binding(
            task_dir,
            "Human start alignment confirmation",
            decision_kind="start-direction"
            if start_status == "direct_instruction"
            else "start-confirmation",
            artifact_path=start_ref,
            artifact_version="v1",
            artifact_sha256=start_sha,
            gate="human-start-alignment",
            scope=(
                "Record the concrete current human instruction and the normalized H0 and H1 execution boundary without claiming exact-version confirmation."
                if start_status == "direct_instruction"
                else "Confirm the exact H0 and H1 task boundary recorded in this start artifact."
            ),
        )
    if risk_downgrade:
        values["risk_downgrade_ref"] = write_decision_binding(
            task_dir,
            "Human risk downgrade",
            decision_kind="risk-downgrade",
            artifact_path=start_ref,
            artifact_version="v1",
            artifact_sha256=start_sha,
            gate="risk-classification",
            scope="Explicitly accept the lower declared risk despite the factor-derived risk floor.",
        )
    if waiver_used and decision_status == "confirmed":
        write_decision_binding(
            task_dir,
            "P0 human waiver",
            decision_kind="emergency-waiver",
            artifact_path=str(values["decision_ref"]),
            artifact_version="v1",
            artifact_sha256=str(values["decision_sha256"]),
            gate="emergency-waiver",
            scope="Authorize only the narrow P0 emergency bypass and require final H3 acceptance.",
        )

    alignment_path = task_dir / "alignment" / "alignment.yaml"
    alignment_path.parent.mkdir(parents=True, exist_ok=True)
    alignment_path.write_text(
        "".join(f"{key}: {yaml_value(value)}\n" for key, value in values.items()),
        encoding="utf-8",
    )
    return alignment_path


def canonical_package_digest(package: dict[str, object]) -> str:
    canonical_fields = (
        "schema_version",
        "protocol_version",
        "task_id",
        "checkpoint",
        "package_version",
        "question",
        "covers",
        "binding_surfaces",
        "excluded",
        "limitations",
        "extensions",
    )
    payload = {field: package.get(field) for field in canonical_fields}
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_surface_file(task_dir: Path, relative: str, content: str | bytes) -> Path:
    path = task_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_bytes(content)
    return path


def file_review_surface(
    task_dir: Path,
    relative: str,
    *,
    surface_id: str,
    role: str,
    kind: str,
    content: str | bytes,
    page_state: str | None = None,
) -> dict[str, object]:
    path = write_surface_file(task_dir, relative, content)
    surface: dict[str, object] = {
        "id": surface_id,
        "role": role,
        "kind": kind,
        "locator": relative,
        "identity": {
            "method": "file_sha256",
            "value": hashlib.sha256(path.read_bytes()).hexdigest(),
            "immutable": True,
        },
    }
    if page_state is not None:
        surface["page_state"] = page_state
    return surface


def external_review_surface(
    *,
    surface_id: str,
    role: str,
    kind: str,
    locator: str,
    revision: str,
    method: str = "provider_revision",
    immutable: bool = True,
    page_state: str | None = None,
) -> dict[str, object]:
    surface: dict[str, object] = {
        "id": surface_id,
        "role": role,
        "kind": kind,
        "locator": locator,
        "identity": {
            "method": method,
            "value": revision,
            "immutable": immutable,
        },
    }
    if page_state is not None:
        surface["page_state"] = page_state
    return surface


def write_review_package(
    task_dir: Path,
    relative: str,
    checkpoint: str,
    covers: tuple[str, ...],
    binding_surfaces: list[dict[str, object]],
    *,
    supporting_surfaces: list[dict[str, object]] | None = None,
    question: str | None = None,
    excluded: list[str] | None = None,
    limitations: list[str] | None = None,
    extensions: dict[str, object] | None = None,
) -> tuple[str, str, dict[str, object]]:
    package: dict[str, object] = {
        "schema_version": 1,
        "protocol_version": "2.2",
        "task_id": task_dir.name,
        "checkpoint": checkpoint,
        "package_version": "v1",
        "question": question
        or f"Does this exact {checkpoint} review package communicate the bounded decision clearly enough for the declared lifecycle gate?",
        "covers": list(covers),
        "binding_surfaces": binding_surfaces,
        "supporting_surfaces": supporting_surfaces or [],
        "excluded": excluded or [],
        "limitations": limitations or [],
        "extensions": extensions or {},
    }
    path = task_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(package, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return relative, canonical_package_digest(package), package


def default_local_surface(
    task_dir: Path,
    checkpoint: str,
    *,
    role: str = "primary-review",
    page_state: str | None = None,
) -> dict[str, object]:
    return file_review_surface(
        task_dir,
        f"evidence/{checkpoint}-surface.md",
        surface_id=f"{checkpoint}-local",
        role=role,
        kind="markdown-source",
        content=(
            f"# {checkpoint.title()} evidence\n\n"
            "This task-local immutable surface records concrete review evidence, boundaries, state, and limitations for independent reproduction.\n"
        ),
        page_state=page_state,
    )


def write_alignment_v22(
    task_dir: Path,
    *,
    risk_level: str = "low",
    start_status: str = "direct_instruction",
    start_surfaces: list[dict[str, object]] | None = None,
    start_supporting: list[dict[str, object]] | None = None,
    start_covers: tuple[str, ...] = ("H0", "H1"),
    decision_status: str = "not_required",
    decision_surfaces: list[dict[str, object]] | None = None,
    readout_status: str = "not_started",
    readout_surfaces: list[dict[str, object]] | None = None,
    readout_covers: tuple[str, ...] = ("HumanReadout", "H3"),
    freeze_draft_readout: bool = False,
) -> Path:
    if start_surfaces is None:
        start_surfaces = [default_local_surface(task_dir, "start")]
    start_ref, start_digest, _ = write_review_package(
        task_dir,
        "alignment/start-review-v1.json",
        "start",
        start_covers,
        start_surfaces,
        supporting_surfaces=start_supporting,
    )
    factors = {
        "low": "[local-reversible]",
        "medium": "[cross-component]",
        "high": "[security-or-safety]",
    }[risk_level]
    effects = {
        "low": ("reversible", "none", "local-only", "none", "none", "none"),
        "medium": (
            "partially_reversible",
            "internal",
            "shared-nonproduction",
            "draft-only",
            "none",
            "indirect",
        ),
        "high": (
            "irreversible",
            "personal-or-sensitive",
            "production",
            "message-or-publish",
            "involved",
            "direct",
        ),
    }[risk_level]
    values: dict[str, object] = {
        "schema_version": 2,
        "protocol_version": '"2.2"',
        "review_model": "adaptive",
        "task_id": task_dir.name,
        "risk_level": risk_level,
        "risk_factors": factors,
        "risk_downgrade_ref": None,
        "start_status": start_status,
        "start_ref": start_ref,
        "start_sha256": None if start_status == "draft" else start_digest,
        "start_authority_by": None,
        "start_authority_at": None,
        "start_authority_ref": None,
        "decision_status": decision_status,
        "decision_ref": None,
        "decision_sha256": None,
        "decision_confirmed_by": None,
        "decision_confirmed_at": None,
        "decision_confirmation_ref": None,
        "readout_status": readout_status,
        "readout_ref": None,
        "readout_sha256": None,
        "completion_accepted_by": None,
        "completion_accepted_at": None,
        "completion_acceptance_ref": None,
        "material_deviation": "false",
        "waiver_used": "false",
        "unresolved_risk": "false",
        "h2_required": str(decision_status != "not_required").lower(),
        "effect_reversibility": effects[0],
        "effect_data": effects[1],
        "effect_environment": effects[2],
        "effect_external": effects[3],
        "effect_security_safety": effects[4],
        "effect_user_impact": effects[5],
    }
    if start_status in {"direct_instruction", "confirmed"}:
        values["start_authority_by"] = "Project Owner"
        values["start_authority_at"] = "2026-08-11T10:00:00+08:00"
        values["start_authority_ref"] = write_decision_binding(
            task_dir,
            "Human start alignment confirmation",
            decision_kind="start-direction"
            if start_status == "direct_instruction"
            else "start-confirmation",
            artifact_path=start_ref,
            artifact_version="v1",
            artifact_sha256=start_digest,
            gate="human-start-alignment",
            scope="Bind the exact adaptive start package and its declared H0 and H1 execution boundary.",
        )
    if decision_status != "not_required":
        decision_surfaces = decision_surfaces or [default_local_surface(task_dir, "decision")]
        decision_ref, decision_digest, _ = write_review_package(
            task_dir,
            "alignment/decision-review-v1.json",
            "decision",
            ("H2",),
            decision_surfaces,
        )
        values["decision_ref"] = decision_ref
        values["decision_sha256"] = None if decision_status == "draft" else decision_digest
        if decision_status == "confirmed":
            values["decision_confirmed_by"] = "Project Owner"
            values["decision_confirmed_at"] = "2026-08-11T11:00:00+08:00"
            values["decision_confirmation_ref"] = write_decision_binding(
                task_dir,
                "Human decision checkpoint confirmation",
                decision_kind="h2-confirmation",
                artifact_path=decision_ref,
                artifact_version="v1",
                artifact_sha256=decision_digest,
                gate="human-decision-checkpoint",
                scope="Bind the exact adaptive H2 package and the selected bounded decision.",
            )
    if readout_status != "not_started":
        readout_surfaces = readout_surfaces or [default_local_surface(task_dir, "readout")]
        readout_ref, readout_digest, _ = write_review_package(
            task_dir,
            "alignment/readout-review-v1.json",
            "readout",
            readout_covers,
            readout_surfaces,
        )
        values["readout_ref"] = readout_ref
        values["readout_sha256"] = (
            readout_digest
            if readout_status != "draft" or freeze_draft_readout
            else None
        )
        if readout_status == "accepted":
            values["completion_accepted_by"] = "Project Owner"
            values["completion_accepted_at"] = "2026-08-11T12:00:00+08:00"
            values["completion_acceptance_ref"] = write_decision_binding(
                task_dir,
                "Human readout acceptance",
                decision_kind="completion-acceptance",
                artifact_path=readout_ref,
                artifact_version="v1",
                artifact_sha256=readout_digest,
                gate="human-readout",
                scope="Accept the exact adaptive Human Readout package and disclosed limitations.",
            )
    alignment_path = task_dir / "alignment" / "alignment.yaml"
    alignment_path.parent.mkdir(parents=True, exist_ok=True)
    alignment_path.write_text(
        "".join(f"{key}: {yaml_value(value)}\n" for key, value in values.items()),
        encoding="utf-8",
    )
    return alignment_path


def write_design_v22(
    task_dir: Path,
    *,
    gate_profile: str = "one_gate",
    experience_status: str | None = None,
    visual_status: str = "awaiting_human",
    visual_surfaces: list[dict[str, object]] | None = None,
    visual_supporting: list[dict[str, object]] | None = None,
    conformance_status: str = "not_started",
    conformance_surfaces: list[dict[str, object]] | None = None,
) -> Path:
    if experience_status is None:
        experience_status = "not_required" if gate_profile == "one_gate" else "approved"
    values: dict[str, object] = {
        "schema_version": 3,
        "protocol_version": '"2.2"',
        "review_model": "adaptive",
        "task_id": task_dir.name,
        "gate_profile": gate_profile,
        "target_maturity": "owner_approved",
        "current_maturity": "design_candidate",
        "experience_status": experience_status,
        "experience_ref": None,
        "experience_sha256": None,
        "experience_approved_by": None,
        "experience_approved_at": None,
        "experience_approval_ref": None,
        "visual_status": visual_status,
        "visual_ref": None,
        "visual_sha256": None,
        "visual_approved_by": None,
        "visual_approved_at": None,
        "visual_approval_ref": None,
        "conformance_status": conformance_status,
        "conformance_ref": None,
        "conformance_sha256": None,
        "difference_approved_by": None,
        "difference_approved_at": None,
        "difference_approval_ref": None,
        "emergency_waiver_ref": None,
    }
    for prefix, status in (("experience", experience_status), ("visual", visual_status)):
        if status not in {"draft", "awaiting_human", "changes_requested", "approved"}:
            continue
        surfaces = (
            visual_surfaces
            if prefix == "visual" and visual_surfaces is not None
            else [default_local_surface(task_dir, prefix)]
        )
        covers = (
            ("L1", "L2", "L3", "L4")
            if prefix == "visual"
            and (
                gate_profile == "one_gate"
                or (gate_profile == "design_only" and experience_status == "not_required")
            )
            else ("L1", "L2", "L3")
            if prefix == "experience"
            else ("L4",)
        )
        ref, digest, _ = write_review_package(
            task_dir,
            f"design/{prefix}-review-v1.json",
            prefix,
            covers,
            surfaces,
            supporting_surfaces=visual_supporting if prefix == "visual" else None,
        )
        values[f"{prefix}_ref"] = ref
        values[f"{prefix}_sha256"] = None if status == "draft" else digest
        if status == "approved":
            values[f"{prefix}_approved_by"] = "Project Owner"
            values[f"{prefix}_approved_at"] = "2026-08-11T13:00:00+08:00"
            values[f"{prefix}_approval_ref"] = write_decision_binding(
                task_dir,
                f"{prefix.title()} approval",
                decision_kind=f"{prefix}-approval",
                artifact_path=ref,
                artifact_version="v1",
                artifact_sha256=digest,
                gate=f"{prefix}-alignment",
                scope=f"Approve the exact adaptive {prefix} package and its bounded review question.",
            )
    if conformance_status in {
        "pending_review",
        "matched",
        "changes_requested",
        "accepted_with_differences",
    }:
        conformance_surfaces = conformance_surfaces or [
            default_local_surface(
                task_dir,
                "approved-baseline",
                role="approved-baseline",
                page_state="primary-normal",
            ),
            default_local_surface(
                task_dir,
                "implementation-capture",
                role="implementation-capture",
                page_state="primary-normal",
            ),
        ]
        ref, digest, _ = write_review_package(
            task_dir,
            "evidence/conformance-review-v1.json",
            "conformance",
            ("L5",),
            conformance_surfaces,
        )
        values["conformance_ref"] = ref
        values["conformance_sha256"] = digest
        if conformance_status == "accepted_with_differences":
            values["difference_approved_by"] = "Project Owner"
            values["difference_approved_at"] = "2026-08-11T14:00:00+08:00"
            values["difference_approval_ref"] = write_decision_binding(
                task_dir,
                "Accepted differences",
                decision_kind="difference-acceptance",
                artifact_path=ref,
                artifact_version="v1",
                artifact_sha256=digest,
                gate="design-conformance",
                scope="Accept only the exact differences bound into this adaptive conformance package.",
            )
    design_path = task_dir / "design" / "design.yaml"
    design_path.parent.mkdir(parents=True, exist_ok=True)
    design_path.write_text(
        "".join(f"{key}: {yaml_value(value)}\n" for key, value in values.items()),
        encoding="utf-8",
    )
    return design_path


def make_task_done(task_dir: Path) -> None:
    replace_yaml_value(task_dir / "task.yaml", "verification_status", "passed")
    (task_dir / "evidence" / "verification.txt").write_text(
        "Independent verification reproduced every acceptance criterion and recorded the observed result.",
        encoding="utf-8",
    )


class ProjectMemoryScriptsTest(unittest.TestCase):
    def test_initialized_project_passes_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "sample-project"
            project.mkdir()

            initialized = run_script(
                INIT_SCRIPT,
                str(project),
                "--project-name",
                "Sample Project",
                "--project-id",
                "SAMPLE",
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertIn("Project memory check passed", checked.stdout)

    def test_reinitialization_does_not_overwrite_existing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "existing-project"
            project.mkdir()

            first = run_script(INIT_SCRIPT, str(project), "--project-name", "Existing")
            self.assertEqual(first.returncode, 0, first.stderr)
            agents_file = project / "AGENTS.md"
            agents_file.write_text("# Human-owned rules\n", encoding="utf-8")

            second = run_script(INIT_SCRIPT, str(project), "--project-name", "Existing")
            self.assertEqual(second.returncode, 2, second.stdout + second.stderr)
            self.assertEqual(agents_file.read_text(encoding="utf-8"), "# Human-owned rules\n")
            self.assertIn("manual merge is required", second.stderr)

    def test_initializer_escapes_yaml_scalars_and_rejects_file_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            project = base / "quoted-project"
            initialized = run_script(
                INIT_SCRIPT,
                str(project),
                "--project-name",
                'Goal "Quoted" \\ Project',
                "--project-id",
                'GOAL"ID\\V2',
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            state = (project / "project" / "state.yaml").read_text(encoding="utf-8")
            self.assertIn('project_name: "Goal \\"Quoted\\" \\\\ Project"', state)
            self.assertIn('project_id: "GOAL\\"ID\\\\V2"', state)

            file_root = base / "not-a-directory"
            file_root.write_text("preserve these bytes", encoding="utf-8")
            rejected = run_script(INIT_SCRIPT, str(file_root))
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("selected project root is not a directory", rejected.stderr)
            self.assertNotIn("Traceback", rejected.stderr)
            self.assertEqual(file_root.read_text(encoding="utf-8"), "preserve these bytes")

    def test_checker_rejects_duplicate_yaml_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "duplicate-yaml"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            state_path = project / "project" / "state.yaml"
            state_path.write_text(
                state_path.read_text(encoding="utf-8") + "active_task: null\n",
                encoding="utf-8",
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("duplicate key 'active_task'", checked.stdout)

    def test_invalid_active_task_reports_actionable_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "invalid-project"
            project.mkdir()
            initialized = run_script(INIT_SCRIPT, str(project), "--project-name", "Invalid")
            self.assertEqual(initialized.returncode, 0, initialized.stderr)

            task_dir = project / "work" / "active" / "bad-task-name"
            (task_dir / "evidence").mkdir(parents=True)
            (task_dir / "task.yaml").write_text(
                """id: T-M01-001-demo
title: Demo
status: finished
milestone: M01
owner: codex
verifier: claude
priority: P1
created: 2026-06-15
updated: 2026-06-15
goal: Demonstrate validation
allowed_files: [src/app.py]
forbidden_files: [src/app.py]
acceptance_criteria: [Checker catches errors]
dependencies: []
commits: []
verification_status: pending
not_committed_reason: null
""",
                encoding="utf-8",
            )
            for name in ("brief.md", "decisions.md", "handoff.md", "review.md"):
                (task_dir / name).write_text(f"# {name}\n", encoding="utf-8")

            checked = run_script(CHECK_SCRIPT, str(project), "--full")
            self.assertEqual(checked.returncode, 1)
            self.assertIn("invalid task directory name", checked.stdout)
            self.assertIn("invalid status 'finished'", checked.stdout)
            self.assertIn("allowed_files and forbidden_files overlap", checked.stdout)

    def test_done_task_requires_review_verification_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "done-project"
            project.mkdir()
            initialized = run_script(INIT_SCRIPT, str(project), "--project-name", "Done")
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            write_state(project, 1)

            task_dir = project / "work" / "archive" / "T-M01-001-demo"
            (task_dir / "evidence").mkdir(parents=True)
            (task_dir / "task.yaml").write_text(
                """id: T-M01-001-demo
title: Demo
status: done
milestone: M01
owner: codex
verifier: claude
priority: P1
created: 2026-06-15
updated: 2026-06-15
goal: Demonstrate completion checks
allowed_files: [src/app.py]
forbidden_files: []
acceptance_criteria: [Feature works]
dependencies: []
commits: []
verification_status: pending
not_committed_reason: null
""",
                encoding="utf-8",
            )
            (task_dir / "brief.md").write_text("# Brief\nImplement the feature.\n", encoding="utf-8")
            (task_dir / "decisions.md").write_text("# Decisions\nNone.\n", encoding="utf-8")
            (task_dir / "handoff.md").write_text("# Handoff\n", encoding="utf-8")
            (task_dir / "review.md").write_text("# Review\n", encoding="utf-8")

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("requires a substantive handoff.md", checked.stdout)
            self.assertIn("requires a substantive review.md", checked.stdout)
            self.assertIn("verification_status must be 'passed'", checked.stdout)
            self.assertIn("requires at least one evidence file", checked.stdout)
            self.assertIn("requires commits or not_committed_reason", checked.stdout)

    def test_protocol_21_done_requires_structured_handoff_review_and_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "v21-thin-completion"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.1")
            task_dir = make_task(
                project,
                location="archive",
                status="done",
                protocol_version="2.1",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            make_task_done(task_dir)
            write_alignment(task_dir, readout_status="ready")
            (task_dir / "handoff.md").write_text("# Handoff\nabcdefghij\n", encoding="utf-8")
            (task_dir / "review.md").write_text("# Review\nabcdefghij\n", encoding="utf-8")
            (task_dir / "evidence" / "verification.txt").write_bytes(b"")

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("handoff missing required heading", checked.stdout)
            self.assertIn("independent review missing required heading", checked.stdout)
            self.assertIn("substantive nonempty evidence file", checked.stdout)

    def test_protocol_21_unfilled_handoff_and_review_templates_are_not_substantive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "v21-template-completion"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.1")
            task_dir = make_task(
                project,
                status="verifying",
                protocol_version="2.1",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment(task_dir, readout_status="ready")
            for name in ("handoff.md", "review.md"):
                (task_dir / name).write_bytes(
                    (project / "templates" / "task" / name).read_bytes()
                )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("handoff section(s) lack substantive content", checked.stdout)
            self.assertIn("independent review section(s) lack substantive content", checked.stdout)

    def test_schema_v1_project_and_active_task_remain_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "v1-project"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 1)
            make_task(project, schema_version=1)

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_schema_v2_project_allows_archived_v1_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "mixed-history"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2)
            make_task(
                project,
                location="archive",
                status="cancelled",
                schema_version=1,
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_schema_v2_active_task_requires_v2_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "v2-active-v1-task"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2)
            make_task(project, schema_version=1)

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("schema v2 active task requires schema_version: 2", checked.stdout)

    def test_v2_ui_task_rejects_text_alignment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "text-ui"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2)
            task_dir = make_task(
                project,
                task_types=("product", "ux", "ui"),
                alignment_mode="text",
                design_ref="design/design.yaml",
            )
            write_design(
                task_dir,
                experience_status="awaiting_human",
                visual_status="not_started",
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("ui/ux task requires alignment_mode visual or mixed", checked.stdout)

    def test_v2_task_rejects_unknown_task_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "bad-type"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2)
            make_task(project, task_types=("engineering", "magic"))

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("task_types contains invalid value", checked.stdout)

    def test_visual_or_mixed_alignment_requires_design_governance(self) -> None:
        for alignment_mode in ("visual", "mixed"):
            with self.subTest(alignment_mode=alignment_mode), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"missing-design-{alignment_mode}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2)
                make_task(
                    project,
                    task_types=("product", "engineering"),
                    alignment_mode=alignment_mode,
                )

                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 1)
                self.assertIn("missing design_governance_ref", checked.stdout)

    def test_major_ui_cannot_implement_with_either_gate_missing(self) -> None:
        for missing_gate in ("experience", "visual"):
            with self.subTest(missing_gate=missing_gate), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"major-ui-{missing_gate}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2)
                task_dir = make_task(
                    project,
                    status="implementing",
                    task_types=("product", "ux", "ui", "engineering"),
                    alignment_mode="mixed",
                    design_ref="design/design.yaml",
                )
                write_design(
                    task_dir,
                    experience_status="not_started" if missing_gate == "experience" else "approved",
                    visual_status="not_started" if missing_gate == "visual" else "approved",
                )

                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 1)
                self.assertIn(f"requires approved {missing_gate} gate", checked.stdout)

    def test_two_gate_visual_work_cannot_start_before_experience_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "out-of-order-design"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2)
            task_dir = make_task(
                project,
                task_types=("product", "ux", "ui"),
                alignment_mode="mixed",
                design_ref="design/design.yaml",
            )
            write_design(
                task_dir,
                experience_status="awaiting_human",
                visual_status="draft",
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn(
                "visual gate cannot start before the experience gate is approved",
                checked.stdout,
            )

    def test_minor_ui_one_gate_and_backend_zero_gate_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "adaptive-gates"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2)
            ui_task = make_task(
                project,
                task_id="T-M01-001-minor-ui",
                status="implementing",
                task_types=("ui", "engineering"),
                alignment_mode="visual",
                design_ref="design/design.yaml",
            )
            write_design(ui_task, gate_profile="one_gate")
            make_task(
                project,
                task_id="T-M01-002-backend",
                status="implementing",
                task_types=("engineering",),
                alignment_mode="text",
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_design_only_done_does_not_require_implementation_conformance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "design-only"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2)
            task_dir = make_task(
                project,
                location="archive",
                status="done",
                task_types=("product", "ux", "ui"),
                alignment_mode="visual",
                design_ref="design/design.yaml",
            )
            replace_yaml_value(task_dir / "task.yaml", "verification_status", "passed")
            (task_dir / "evidence" / "design-review.txt").write_text(
                "Independent review reproduced the approved design baseline.",
                encoding="utf-8",
            )
            write_design(task_dir, gate_profile="design_only", conformance_status="not_required")

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_html_artifact_failures_are_actionable(self) -> None:
        cases = ("missing", "escape", "placeholder", "template_copy", "marker", "hash")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"artifact-{case}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2)
                task_dir = make_task(
                    project,
                    task_types=("ux", "ui"),
                    alignment_mode="visual",
                    design_ref="design/design.yaml",
                )
                design_path = write_design(
                    task_dir,
                    experience_status="awaiting_human",
                    visual_status="not_started",
                )
                artifact = task_dir / "design" / "experience-v1.html"

                if case == "missing":
                    artifact.unlink()
                    expected = "experience_ref does not exist"
                elif case == "escape":
                    replace_yaml_value(design_path, "experience_ref", "../outside.html")
                    expected = "experience_ref escapes task directory"
                elif case == "placeholder":
                    content = artifact.read_text(encoding="utf-8").replace(
                        "</main>", "<p>TODO replace me</p></main>"
                    )
                    artifact.write_text(content, encoding="utf-8")
                    replace_yaml_value(
                        design_path,
                        "experience_sha256",
                        hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    )
                    expected = "contains unresolved template placeholder"
                elif case == "template_copy":
                    content = artifact.read_text(encoding="utf-8").replace(
                        "</main>", "<p>Replace with the exact screen content.</p></main>"
                    )
                    artifact.write_text(content, encoding="utf-8")
                    replace_yaml_value(
                        design_path,
                        "experience_sha256",
                        hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    )
                    expected = "contains unresolved template placeholder"
                elif case == "marker":
                    content = artifact.read_text(encoding="utf-8").replace(
                        'data-project-memory-artifact="experience-alignment"', ""
                    )
                    artifact.write_text(content, encoding="utf-8")
                    replace_yaml_value(
                        design_path,
                        "experience_sha256",
                        hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    )
                    expected = "missing artifact marker"
                else:
                    replace_yaml_value(design_path, "experience_sha256", "f" * 64)
                    expected = "SHA-256 mismatch"

                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 1)
                self.assertIn(expected, checked.stdout)

    def test_approved_artifact_requires_human_version_bound_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "machine-approval"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2)
            task_dir = make_task(
                project,
                status="implementing",
                task_types=("ui",),
                alignment_mode="visual",
                design_ref="design/design.yaml",
            )
            design_path = write_design(task_dir, gate_profile="one_gate")
            replace_yaml_value(design_path, "visual_approved_by", "codex-agent")
            replace_yaml_value(design_path, "visual_approved_at", "null")
            replace_yaml_value(design_path, "visual_approval_ref", "null")

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("requires a human approver", checked.stdout)
            self.assertIn("requires an approval time", checked.stdout)
            self.assertIn("requires a decision reference", checked.stdout)

    def test_approval_reference_must_resolve_to_task_decision_heading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "invalid-approval-reference"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2)
            task_dir = make_task(
                project,
                status="implementing",
                task_types=("ui",),
                alignment_mode="visual",
                design_ref="design/design.yaml",
            )
            design_path = write_design(task_dir, gate_profile="one_gate")
            replace_yaml_value(
                design_path,
                "visual_approval_ref",
                "decisions.md#missing-visual-decision",
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn(
                "heading '#missing-visual-decision' does not exist in decisions.md",
                checked.stdout,
            )

    def test_changing_approved_html_invalidates_bound_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "changed-approved-artifact"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2)
            task_dir = make_task(
                project,
                status="implementing",
                task_types=("ui",),
                alignment_mode="visual",
                design_ref="design/design.yaml",
            )
            write_design(task_dir, gate_profile="one_gate")
            visual = task_dir / "design" / "visual-v1.html"
            visual.write_text(
                visual.read_text(encoding="utf-8").replace(
                    "complete representative state",
                    "silently changed representative state",
                ),
                encoding="utf-8",
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("SHA-256 mismatch; approval is invalid", checked.stdout)

    def test_reviewing_ui_requires_conformance_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "review-without-conformance"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2)
            task_dir = make_task(
                project,
                status="reviewing",
                task_types=("ux", "ui", "engineering"),
                alignment_mode="mixed",
                design_ref="design/design.yaml",
            )
            write_design(task_dir, conformance_status="not_started")

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("status reviewing requires design conformance", checked.stdout)

    def test_verifying_requires_matched_or_human_accepted_differences(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "verification-conformance"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2)
            task_dir = make_task(
                project,
                status="verifying",
                task_types=("ui", "engineering"),
                alignment_mode="visual",
                design_ref="design/design.yaml",
            )
            write_design(task_dir, gate_profile="one_gate", conformance_status="changes_requested")
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn(
                "requires conformance_status matched or accepted_with_differences",
                checked.stdout,
            )

            write_design(
                task_dir,
                gate_profile="one_gate",
                conformance_status="accepted_with_differences",
                difference_approval=False,
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("accepted_with_differences requires a human approver", checked.stdout)

            write_design(
                task_dir,
                gate_profile="one_gate",
                conformance_status="accepted_with_differences",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

            write_design(task_dir, gate_profile="one_gate", conformance_status="matched")
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_p0_waiver_allows_implementation_but_not_final_conformance_bypass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "p0-waiver"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2)
            task_dir = make_task(
                project,
                status="implementing",
                task_types=("ux", "ui", "engineering"),
                alignment_mode="mixed",
                design_ref="design/design.yaml",
                priority="P0",
            )
            write_design(
                task_dir,
                experience_status="not_started",
                visual_status="not_started",
                emergency_waiver_ref="decisions.md#p0-human-waiver",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

            replace_yaml_value(task_dir / "task.yaml", "status", "verifying")
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("requires approved experience gate", checked.stdout)
            self.assertIn("requires approved visual gate", checked.stdout)
            self.assertIn(
                "requires conformance_status matched or accepted_with_differences",
                checked.stdout,
            )

    def test_protocol_21_low_risk_direct_instruction_needs_no_extra_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "low-direct-instruction"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.1")
            task_dir = make_task(
                project,
                status="implementing",
                protocol_version="2.1",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment(task_dir, risk_level="low", start_status="direct_instruction")

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_protocol_21_medium_and_high_execution_require_confirmed_start(self) -> None:
        for risk_level in ("medium", "high"):
            with self.subTest(risk_level=risk_level), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"{risk_level}-unconfirmed-start"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2, protocol_version="2.1")
                task_dir = make_task(
                    project,
                    status="implementing",
                    protocol_version="2.1",
                    risk_level=risk_level,
                    alignment_ref="alignment/alignment.yaml",
                )
                write_alignment(
                    task_dir,
                    risk_level=risk_level,
                    start_status="awaiting_human",
                )

                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 1)
                self.assertIn("requires confirmed start alignment", checked.stdout)

    def test_protocol_21_pending_decision_blocks_execution(self) -> None:
        for decision_status in ("draft", "awaiting_human", "changes_requested"):
            with self.subTest(decision_status=decision_status), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"pending-decision-{decision_status}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2, protocol_version="2.1")
                task_dir = make_task(
                    project,
                    status="implementing",
                    protocol_version="2.1",
                    risk_level="medium",
                    alignment_ref="alignment/alignment.yaml",
                )
                write_alignment(
                    task_dir,
                    risk_level="medium",
                    start_status="confirmed",
                    decision_status=decision_status,
                )

                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 1)
                self.assertIn(
                    f"cannot proceed with decision_status {decision_status}",
                    checked.stdout,
                )

    def test_protocol_21_every_done_task_requires_a_readout(self) -> None:
        for risk_level in ("low", "medium", "high"):
            with self.subTest(risk_level=risk_level), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"done-without-readout-{risk_level}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2, protocol_version="2.1")
                task_dir = make_task(
                    project,
                    location="archive",
                    status="done",
                    protocol_version="2.1",
                    risk_level=risk_level,
                    alignment_ref="alignment/alignment.yaml",
                )
                make_task_done(task_dir)
                write_alignment(
                    task_dir,
                    risk_level=risk_level,
                    start_status="confirmed" if risk_level != "low" else "direct_instruction",
                    readout_status="not_started",
                )

                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 1)
                self.assertIn("status done requires readout_status ready or accepted", checked.stdout)

    def test_protocol_21_high_or_unresolved_done_requires_human_acceptance(self) -> None:
        for risk_level, unresolved_risk in (("high", False), ("low", True)):
            with self.subTest(risk_level=risk_level, unresolved_risk=unresolved_risk), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"acceptance-{risk_level}-{unresolved_risk}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2, protocol_version="2.1")
                task_dir = make_task(
                    project,
                    location="archive",
                    status="done",
                    protocol_version="2.1",
                    risk_level=risk_level,
                    alignment_ref="alignment/alignment.yaml",
                )
                make_task_done(task_dir)
                write_alignment(
                    task_dir,
                    risk_level=risk_level,
                    start_status="confirmed" if risk_level == "high" else "direct_instruction",
                    readout_status="ready",
                    unresolved_risk=unresolved_risk,
                )
                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 1)
                self.assertIn("requires human-accepted readout", checked.stdout)

                write_alignment(
                    task_dir,
                    risk_level=risk_level,
                    start_status="confirmed" if risk_level == "high" else "direct_instruction",
                    readout_status="accepted",
                    unresolved_risk=unresolved_risk,
                )
                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_protocol_21_material_deviation_or_waiver_requires_confirmed_decision(self) -> None:
        for exceptional_field in ("material_deviation", "waiver_used"):
            with self.subTest(exceptional_field=exceptional_field), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"exception-{exceptional_field}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2, protocol_version="2.1")
                task_dir = make_task(
                    project,
                    location="archive",
                    status="done",
                    protocol_version="2.1",
                    risk_level="low",
                    alignment_ref="alignment/alignment.yaml",
                )
                make_task_done(task_dir)
                kwargs = {exceptional_field: True}
                write_alignment(
                    task_dir,
                    risk_level="low",
                    readout_status="accepted",
                    **kwargs,
                )
                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 1)
                self.assertIn("requires decision_status confirmed", checked.stdout)

                write_alignment(
                    task_dir,
                    risk_level="low",
                    decision_status="confirmed",
                    readout_status="accepted",
                    **kwargs,
                )
                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_protocol_21_exception_cannot_cross_any_execution_state_without_h2(self) -> None:
        for exceptional_field in ("material_deviation", "waiver_used"):
            with self.subTest(exceptional_field=exceptional_field), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"execution-exception-{exceptional_field}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2, protocol_version="2.1")
                task_dir = make_task(
                    project,
                    status="implementing",
                    protocol_version="2.1",
                    risk_level="low",
                    alignment_ref="alignment/alignment.yaml",
                )
                kwargs = {exceptional_field: True}
                write_alignment(task_dir, **kwargs)

                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 1)
                self.assertIn(
                    "H2-triggered status implementing requires decision_status confirmed",
                    checked.stdout,
                )

                write_alignment(
                    task_dir,
                    decision_status="confirmed",
                    h2_required=False,
                    **kwargs,
                )
                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 1)
                self.assertIn(
                    "material_deviation or waiver_used requires h2_required true",
                    checked.stdout,
                )

                write_alignment(task_dir, decision_status="confirmed", **kwargs)
                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_protocol_21_known_irreversible_h2_requires_confirmed_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "known-irreversible-h2"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.1")
            task_dir = make_task(
                project,
                status="implementing",
                protocol_version="2.1",
                risk_level="high",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment(
                task_dir,
                risk_level="high",
                start_status="confirmed",
                decision_status="awaiting_human",
                h2_required=True,
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("H2-triggered status implementing", checked.stdout)

            write_alignment(
                task_dir,
                risk_level="high",
                start_status="confirmed",
                decision_status="confirmed",
                h2_required=True,
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_protocol_21_alignment_artifact_failures_are_actionable(self) -> None:
        for case in ("escape", "marker", "placeholder", "hash"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"alignment-artifact-{case}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2, protocol_version="2.1")
                task_dir = make_task(
                    project,
                    protocol_version="2.1",
                    risk_level="low",
                    alignment_ref="alignment/alignment.yaml",
                )
                alignment_path = write_alignment(task_dir)
                artifact = task_dir / "alignment" / "start-v1.md"

                if case == "escape":
                    replace_yaml_value(alignment_path, "start_ref", "../outside-v1.md")
                    expected = "start_ref escapes task directory"
                elif case == "marker":
                    content = artifact.read_text(encoding="utf-8").replace(
                        "<!-- project-memory-artifact: human-start-alignment -->",
                        "",
                    )
                    artifact.write_text(content, encoding="utf-8")
                    replace_yaml_value(
                        alignment_path,
                        "start_sha256",
                        hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    )
                    expected = "missing artifact marker"
                elif case == "placeholder":
                    content = artifact.read_text(encoding="utf-8") + "\nTODO replace this\n"
                    artifact.write_text(content, encoding="utf-8")
                    replace_yaml_value(
                        alignment_path,
                        "start_sha256",
                        hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    )
                    expected = "contains unresolved template placeholder"
                else:
                    replace_yaml_value(alignment_path, "start_sha256", "a" * 64)
                    expected = "SHA-256 mismatch"

                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 1)
                self.assertIn(expected, checked.stdout)

    def test_protocol_21_alignment_artifact_requires_human_readout_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "readout-missing-human-section"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.1")
            task_dir = make_task(
                project,
                status="reviewing",
                protocol_version="2.1",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            alignment_path = write_alignment(task_dir, readout_status="ready")
            readout = task_dir / "alignment" / "readout-v1.md"
            content = readout.read_text(encoding="utf-8").replace(
                "## Evidence And Confidence",
                "## Technical Logs",
            )
            readout.write_text(content, encoding="utf-8")
            replace_yaml_value(
                alignment_path,
                "readout_sha256",
                hashlib.sha256(content.encode("utf-8")).hexdigest(),
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn(
                "missing required visible heading(s): Evidence And Confidence",
                checked.stdout,
            )

    def test_protocol_21_html_readout_requires_visible_human_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "html-readout-sections"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.1")
            task_dir = make_task(
                project,
                status="reviewing",
                protocol_version="2.1",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            alignment_path = write_alignment(task_dir, readout_status="ready")
            headings = (
                "Human Readout",
                "Outcome",
                "Before And After",
                "Boundaries Preserved",
                "Acceptance Map",
                "Evidence And Confidence",
                "Residual Risk And Unknowns",
                "Next Decision",
            )
            html_path = task_dir / "alignment" / "readout-v2.html"
            sections = "".join(
                f"<section><h2>{heading}</h2><p>The {index} owner-facing result explains {heading.lower()} with distinct task facts, bounded consequences, and reproducible evidence.</p></section>"
                for index, heading in enumerate(headings[1:], 1)
            )
            content = f'''<!doctype html>
<html lang="en" data-project-memory-artifact="human-readout" data-task-id="{task_dir.name}" data-artifact-version="v2">
<head><meta charset="utf-8"><title>Human Readout</title></head>
<body><main><h1>{headings[0]}</h1><p>This complete readout summarizes the exact human outcome and its independently reviewed evidence.</p>{sections}</main></body>
</html>
'''
            html_path.write_text(content, encoding="utf-8")
            replace_yaml_value(alignment_path, "readout_ref", "alignment/readout-v2.html")
            replace_yaml_value(
                alignment_path,
                "readout_sha256",
                hashlib.sha256(content.encode("utf-8")).hexdigest(),
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

            changed = content.replace("<h2>Acceptance Map</h2>", "<p>Acceptance Map</p>")
            html_path.write_text(changed, encoding="utf-8")
            replace_yaml_value(
                alignment_path,
                "readout_sha256",
                hashlib.sha256(changed.encode("utf-8")).hexdigest(),
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("missing required visible heading(s): Acceptance Map", checked.stdout)

    def test_protocol_21_changed_confirmed_artifact_invalidates_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "changed-confirmed-start"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.1")
            task_dir = make_task(
                project,
                status="implementing",
                protocol_version="2.1",
                risk_level="medium",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment(task_dir, risk_level="medium", start_status="confirmed")
            artifact = task_dir / "alignment" / "start-v1.md"
            artifact.write_text(
                artifact.read_text(encoding="utf-8") + "\nThe approved boundary was silently changed.\n",
                encoding="utf-8",
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("SHA-256 mismatch; confirmation is invalid", checked.stdout)

    def test_protocol_21_diagram_start_requires_fenced_mermaid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "diagram-start"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.1")
            task_dir = make_task(
                project,
                alignment_mode="diagram",
                protocol_version="2.1",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment(task_dir, risk_level="low", alignment_mode="text")

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("requires a fenced Mermaid diagram", checked.stdout)

            write_alignment(task_dir, risk_level="low", alignment_mode="diagram")
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_protocol_21_opt_in_preserves_visual_design_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "protocol-visual-composition"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.1")
            task_dir = make_task(
                project,
                status="implementing",
                task_types=("ui", "engineering"),
                alignment_mode="visual",
                design_ref="design/design.yaml",
                protocol_version="2.1",
                risk_level="medium",
                alignment_ref="alignment/alignment.yaml",
            )
            write_design(task_dir, gate_profile="one_gate")
            write_alignment(task_dir, risk_level="medium", start_status="confirmed")

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

            replace_yaml_value(task_dir / "design" / "design.yaml", "visual_status", "draft")
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("requires approved visual gate", checked.stdout)

    def test_protocol_21_archived_legacy_tasks_remain_compatible_but_opted_in_history_is_strict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "protocol-history"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(
                project,
                2,
                protocol_version="2.1",
                legacy_archive_ids=("T-M01-001-legacy",),
            )
            make_task(
                project,
                task_id="T-M01-001-legacy",
                location="archive",
                status="cancelled",
                schema_version=1,
            )
            establish_legacy_adoption_anchor(project)
            strict_task = make_task(
                project,
                task_id="T-M01-002-strict",
                location="archive",
                status="cancelled",
                protocol_version="2.1",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("must reference an existing alignment.yaml", checked.stdout)

            write_alignment(strict_task)
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_decision_binding_rejects_reused_heading_after_universal_artifact_rehash(self) -> None:
        cases = (
            ("start", "implementing", "medium", "confirmed", "not_required", "not_started"),
            ("decision", "implementing", "medium", "confirmed", "confirmed", "not_started"),
            ("readout", "reviewing", "low", "direct_instruction", "not_required", "accepted"),
        )
        for prefix, status, risk, start, decision, readout in cases:
            with self.subTest(prefix=prefix), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"stale-{prefix}-binding"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2, protocol_version="2.1")
                task_dir = make_task(
                    project,
                    status=status,
                    protocol_version="2.1",
                    risk_level=risk,
                    alignment_ref="alignment/alignment.yaml",
                )
                alignment_path = write_alignment(
                    task_dir,
                    risk_level=risk,
                    start_status=start,
                    decision_status=decision,
                    readout_status=readout,
                )
                artifact = task_dir / "alignment" / f"{prefix}-v1.md"
                changed = artifact.read_text(encoding="utf-8") + "\nThe artifact was rehashed without a new human decision.\n"
                artifact.write_text(changed, encoding="utf-8")
                replace_yaml_value(
                    alignment_path,
                    f"{prefix}_sha256",
                    hashlib.sha256(changed.encode("utf-8")).hexdigest(),
                )

                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 1)
                self.assertIn("decision binding artifact-sha256 does not match", checked.stdout)

    def test_decision_binding_rejects_reused_visual_heading_after_rehash(self) -> None:
        for prefix in ("experience", "visual"):
            with self.subTest(prefix=prefix), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"stale-{prefix}-visual-binding"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2, protocol_version="2.1")
                task_dir = make_task(
                    project,
                    status="implementing",
                    task_types=("ux", "ui"),
                    alignment_mode="visual",
                    design_ref="design/design.yaml",
                    protocol_version="2.1",
                    risk_level="low",
                    alignment_ref="alignment/alignment.yaml",
                )
                write_alignment(task_dir)
                design_path = write_design(task_dir)
                artifact = task_dir / "design" / f"{prefix}-v1.html"
                changed = artifact.read_text(encoding="utf-8").replace(
                    "exact decision boundary",
                    "silently revised decision boundary",
                )
                artifact.write_text(changed, encoding="utf-8")
                replace_yaml_value(
                    design_path,
                    f"{prefix}_sha256",
                    hashlib.sha256(changed.encode("utf-8")).hexdigest(),
                )

                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 1)
                self.assertIn("decision binding artifact-sha256 does not match", checked.stdout)

    def test_decision_binding_scope_must_be_substantive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "short-binding-scope"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.1")
            task_dir = make_task(
                project,
                status="implementing",
                protocol_version="2.1",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment(task_dir)
            decisions = task_dir / "decisions.md"
            decisions.write_text(
                re.sub(r"^scope: .+$", "scope: x", decisions.read_text(encoding="utf-8"), count=1, flags=re.MULTILINE),
                encoding="utf-8",
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("scope must be substantive and placeholder-free", checked.stdout)

    def test_protocol_21_emergency_waiver_requires_h2_coupling_while_implementing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "uncoupled-waiver"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.1")
            task_dir = make_task(
                project,
                status="implementing",
                task_types=("ux", "ui", "engineering"),
                alignment_mode="mixed",
                design_ref="design/design.yaml",
                priority="P0",
                protocol_version="2.1",
                risk_level="high",
                alignment_ref="alignment/alignment.yaml",
            )
            write_design(
                task_dir,
                experience_status="not_started",
                visual_status="not_started",
                emergency_waiver_ref="decisions.md#p0-human-waiver",
            )
            write_alignment(task_dir, risk_level="high", start_status="confirmed")

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("requires alignment waiver_used true", checked.stdout)
            self.assertIn("requires alignment h2_required true", checked.stdout)
            self.assertIn("requires a confirmed H2 decision", checked.stdout)

            write_alignment(
                task_dir,
                risk_level="high",
                start_status="confirmed",
                decision_status="confirmed",
                waiver_used=True,
                h2_required=True,
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_protocol_21_emergency_waiver_done_requires_h3_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "waiver-without-h3"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.1")
            task_dir = make_task(
                project,
                location="archive",
                status="done",
                task_types=("ux", "ui", "engineering"),
                alignment_mode="mixed",
                design_ref="design/design.yaml",
                priority="P0",
                protocol_version="2.1",
                risk_level="high",
                alignment_ref="alignment/alignment.yaml",
            )
            make_task_done(task_dir)
            write_design(
                task_dir,
                conformance_status="matched",
                emergency_waiver_ref="decisions.md#p0-human-waiver",
            )
            write_alignment(
                task_dir,
                risk_level="high",
                start_status="confirmed",
                decision_status="confirmed",
                readout_status="ready",
                waiver_used=True,
                h2_required=True,
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("emergency waiver done task requires an accepted Human Readout", checked.stdout)

            write_alignment(
                task_dir,
                risk_level="high",
                start_status="confirmed",
                decision_status="confirmed",
                readout_status="accepted",
                waiver_used=True,
                h2_required=True,
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_initializer_rejects_symlink_components_without_external_writes(self) -> None:
        for component in ("project", "work"):
            with self.subTest(component=component), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                project = base / "unsafe-project"
                external = base / "external"
                project.mkdir()
                external.mkdir()
                sentinel = external / "sentinel.txt"
                sentinel.write_text("owner data", encoding="utf-8")
                (project / component).symlink_to(external, target_is_directory=True)

                initialized = run_script(INIT_SCRIPT, str(project), "--project-name", "Unsafe")
                self.assertEqual(initialized.returncode, 2)
                self.assertIn("unsafe initialization target", initialized.stderr)
                self.assertEqual(sentinel.read_text(encoding="utf-8"), "owner data")
                self.assertFalse((external / "state.yaml").exists())
                self.assertFalse((project / "AGENTS.md").exists())

    def test_initializer_rejects_selected_root_with_symlink_ancestor_before_any_write(self) -> None:
        for mode in ((), ("--dry-run",), ("--force",)):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                external = base / "external"
                external.mkdir()
                sentinel = external / "sentinel.txt"
                sentinel.write_text("owner data", encoding="utf-8")
                alias = base / "alias"
                alias.symlink_to(external, target_is_directory=True)
                selected_root = alias / "new-project"

                initialized = run_script(
                    INIT_SCRIPT,
                    str(selected_root),
                    "--project-name",
                    "Unsafe Ancestor",
                    *mode,
                )

                self.assertEqual(initialized.returncode, 2)
                self.assertIn("unsafe selected project root", initialized.stderr)
                self.assertIn(str(alias), initialized.stderr)
                self.assertEqual(sentinel.read_text(encoding="utf-8"), "owner data")
                self.assertFalse((external / "new-project").exists())
                self.assertEqual(
                    {path.relative_to(external).as_posix() for path in external.rglob("*")},
                    {"sentinel.txt"},
                )

    def test_checker_rejects_task_local_ancestor_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "artifact-ancestor-symlink"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.1")
            task_dir = make_task(
                project,
                protocol_version="2.1",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            storage = task_dir / "artifact-storage"
            storage.mkdir()
            (task_dir / "alignment").symlink_to(storage, target_is_directory=True)
            write_alignment(task_dir)

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("project-memory paths must not be symlinks", checked.stdout)

    def test_generic_visual_and_conformance_html_are_rejected(self) -> None:
        for kind in ("experience", "visual", "conformance"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"generic-{kind}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2, protocol_version="2.1")
                task_status = "reviewing" if kind == "conformance" else "proposed"
                task_dir = make_task(
                    project,
                    status=task_status,
                    task_types=("ux", "ui"),
                    alignment_mode="visual",
                    design_ref="design/design.yaml",
                    protocol_version="2.1",
                    risk_level="low",
                    alignment_ref="alignment/alignment.yaml",
                )
                write_alignment(
                    task_dir,
                    readout_status="ready" if task_status == "reviewing" else "not_started",
                )
                if kind == "experience":
                    design_path = write_design(task_dir, experience_status="awaiting_human", visual_status="not_started")
                    ref = "design/experience-v1.html"
                    sha_field = "experience_sha256"
                    marker = "experience-alignment"
                elif kind == "visual":
                    design_path = write_design(task_dir, gate_profile="one_gate", visual_status="draft")
                    ref = "design/visual-v1.html"
                    sha_field = "visual_sha256"
                    marker = "visual-alignment"
                else:
                    design_path = write_design(task_dir, conformance_status="pending_review")
                    ref = "evidence/2026-08-09-design-conformance.html"
                    sha_field = "conformance_sha256"
                    marker = "design-conformance"
                generic = f'''<!doctype html><html data-project-memory-artifact="{marker}" data-task-id="{task_dir.name}" data-artifact-version="v1"><body><h1>Generic artifact</h1><p>This generic paragraph is long enough to pass the old length-only validation while proving no required human contract.</p></body></html>'''
                (task_dir / ref).write_text(generic, encoding="utf-8")
                replace_yaml_value(design_path, sha_field, hashlib.sha256(generic.encode("utf-8")).hexdigest())

                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 1)
                self.assertIn("missing required visible heading", checked.stdout)

    def test_required_universal_and_visual_sections_need_substantive_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "empty-required-sections"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.1")
            task_dir = make_task(
                project,
                protocol_version="2.1",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            alignment_path = write_alignment(task_dir, start_status="draft")
            start = task_dir / "alignment" / "start-v1.md"
            changed = start.read_text(encoding="utf-8").replace(
                "The recorded human-readable statement for risk assessment is specific, bounded, and independently reviewable.",
                "x",
            )
            start.write_text(changed, encoding="utf-8")
            replace_yaml_value(alignment_path, "start_sha256", hashlib.sha256(changed.encode("utf-8")).hexdigest())

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("required section(s) lack substantive body: Risk Assessment", checked.stdout)

    def test_one_gate_visual_requires_experience_context_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "one-gate-without-context"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.1")
            task_dir = make_task(
                project,
                task_types=("ui",),
                alignment_mode="visual",
                design_ref="design/design.yaml",
                protocol_version="2.1",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment(task_dir)
            design_path = write_design(task_dir, gate_profile="one_gate", visual_status="draft")
            visual = task_dir / "design" / "visual-v1.html"
            changed = visual.read_text(encoding="utf-8").replace(
                "<h2>Experience context</h2>",
                "<h2>Implementation notes</h2>",
            )
            visual.write_text(changed, encoding="utf-8")
            replace_yaml_value(design_path, "visual_sha256", hashlib.sha256(changed.encode("utf-8")).hexdigest())

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("Experience context", checked.stdout)

    def test_matched_conformance_requires_real_capture_pair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "conformance-without-captures"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.1")
            task_dir = make_task(
                project,
                status="verifying",
                task_types=("ui", "engineering"),
                alignment_mode="visual",
                design_ref="design/design.yaml",
                protocol_version="2.1",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment(task_dir, readout_status="ready")
            design_path = write_design(task_dir, gate_profile="one_gate", conformance_status="matched")
            conformance = task_dir / "evidence" / "2026-08-09-design-conformance.html"
            changed = re.sub(r"<figure data-conformance-capture=.*?</figure>", "", conformance.read_text(encoding="utf-8"), flags=re.DOTALL)
            conformance.write_text(changed, encoding="utf-8")
            replace_yaml_value(design_path, "conformance_sha256", hashlib.sha256(changed.encode("utf-8")).hexdigest())

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("requires a self-contained approved/implementation capture pair", checked.stdout)

    def test_protocol_21_requires_schema_two_and_independent_execution_roles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "protocol-schema-and-roles"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 1, protocol_version="2.1")
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("protocol 2.1 requires schema_version: 2", checked.stdout)

            write_state(project, 2, protocol_version="2.1")
            task_dir = make_task(
                project,
                status="implementing",
                protocol_version="2.1",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
                builder_id="same-agent",
                verifier_id="same-agent",
            )
            write_alignment(task_dir)
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("builder_id and verifier_id must differ", checked.stdout)

            replace_yaml_value(task_dir / "task.yaml", "status", "proposed")
            replace_yaml_value(task_dir / "task.yaml", "builder_id", "unassigned")
            replace_yaml_value(task_dir / "task.yaml", "verifier_id", "unassigned")
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_risk_factor_floor_requires_confirmed_human_downgrade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "risk-floor"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.1")
            task_dir = make_task(
                project,
                status="implementing",
                protocol_version="2.1",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment(
                task_dir,
                risk_level="low",
                start_status="direct_instruction",
                risk_factors=("custom-high:regulated-export",),
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("below factor floor high requires start_status confirmed", checked.stdout)
            self.assertIn("requires risk_downgrade_ref", checked.stdout)

            write_alignment(
                task_dir,
                risk_level="low",
                start_status="confirmed",
                risk_factors=("custom-high:regulated-export",),
                risk_downgrade=True,
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

            write_alignment(
                task_dir,
                risk_level="low",
                start_status="confirmed",
                risk_factors=("vague-risk",),
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("risk_factors contains unsupported value", checked.stdout)

    def test_legacy_archive_manifest_cannot_hide_post_adoption_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "late-legacy-downgrade"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(
                project,
                2,
                protocol_version="2.1",
                adopted_at="2026-08-09T10:00:00+08:00",
                legacy_archive_ids=("T-M01-001-late",),
            )
            make_task(
                project,
                task_id="T-M01-001-late",
                location="archive",
                status="cancelled",
                schema_version=1,
            )
            establish_legacy_adoption_anchor(project)
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("updated after governance_protocol_adopted_at", checked.stdout)

    def test_legacy_archive_manifest_rejects_created_after_adoption_with_backdated_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "backdated-legacy-downgrade"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(
                project,
                2,
                protocol_version="2.1",
                adopted_at="2026-08-09T10:00:00+08:00",
                legacy_archive_ids=("T-M01-001-backdated",),
            )
            task_dir = make_task(
                project,
                task_id="T-M01-001-backdated",
                location="archive",
                status="cancelled",
                schema_version=1,
            )
            replace_yaml_value(task_dir / "task.yaml", "created", '"2026-08-10"')
            replace_yaml_value(
                task_dir / "task.yaml",
                "updated",
                '"2026-08-09T09:00:00+08:00"',
            )
            establish_legacy_adoption_anchor(project)

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("created after governance_protocol_adopted_at", checked.stdout)
            self.assertNotIn("updated after governance_protocol_adopted_at", checked.stdout)

    def test_invalid_calendar_dates_cannot_authorize_protocol_or_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "invalid-calendar-date"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(
                project,
                2,
                protocol_version="2.1",
                adopted_at="2026-99-99T12:00:00+08:00",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("must be an ISO date or date-time", checked.stdout)

            write_state(project, 2)
            task_dir = make_task(
                project,
                status="implementing",
                task_types=("ui",),
                alignment_mode="visual",
                design_ref="design/design.yaml",
            )
            design_path = write_design(task_dir, gate_profile="one_gate")
            replace_yaml_value(design_path, "visual_approved_at", "2026-99-99")
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("requires an approval time", checked.stdout)

    def test_legacy_v2_visual_artifact_passes_normally_but_fails_protocol_21_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "legacy-v2-visual"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2)
            task_dir = make_task(
                project,
                status="implementing",
                task_types=("ui", "engineering"),
                alignment_mode="visual",
                design_ref="design/design.yaml",
            )
            design_path = write_design(task_dir, gate_profile="one_gate")
            visual = task_dir / "design" / "visual-v1.html"
            generic = f'''<!doctype html>
<html lang="en" data-project-memory-artifact="visual-alignment" data-task-id="{task_dir.name}" data-artifact-version="v1">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Legacy visual artifact</title></head>
<body><main><h1>Legacy visual decision</h1><p>This previously valid schema v2 artifact records the owner-reviewed interface direction, representative layout, expected behavior, implementation boundary, and enough durable context for the original length-based visual governance contract.</p><h2>Legacy notes</h2><p>The approved direction remains intentionally generic because this fixture represents a project that has not adopted governance protocol 2.1.</p></main></body>
</html>
'''
            visual.write_text(generic, encoding="utf-8")
            replace_yaml_value(
                design_path,
                "visual_sha256",
                hashlib.sha256(generic.encode("utf-8")).hexdigest(),
            )
            decisions = task_dir / "decisions.md"
            decisions.write_text(
                re.sub(
                    r"\n?<!-- project-memory-decision-binding.*?-->\n?",
                    "\n",
                    decisions.read_text(encoding="utf-8"),
                    flags=re.DOTALL,
                ),
                encoding="utf-8",
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

            preflight = run_script(
                CHECK_SCRIPT,
                str(project),
                "--target-protocol",
                "2.1",
            )
            self.assertEqual(preflight.returncode, 1)
            self.assertIn("missing required visible heading", preflight.stdout)
            self.assertIn(
                "heading must contain exactly one project-memory-decision-binding block",
                preflight.stdout,
            )

    def test_target_protocol_21_preflight_is_read_only_and_composes_with_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "protocol-preflight"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 1)
            state_path = project / "project" / "state.yaml"
            make_task(project, schema_version=1)
            before = state_path.read_bytes()

            checked = run_script(
                CHECK_SCRIPT,
                str(project),
                "--target-schema",
                "2",
                "--target-protocol",
                "2.1",
            )
            self.assertEqual(checked.returncode, 1)
            self.assertIn("target schema 2 / protocol 2.1 preflight failed", checked.stdout)
            self.assertIn("requires protocol_version", checked.stdout)
            self.assertIn("missing required field 'risk_level'", checked.stdout)
            self.assertIn("missing required field 'alignment_governance_ref'", checked.stdout)
            self.assertNotIn("missing alignment_governance_ref", checked.stdout)
            self.assertNotIn("invalid risk_level ''", checked.stdout)
            self.assertEqual(state_path.read_bytes(), before)

            archived_project = Path(tmp) / "protocol-archive-preflight"
            archived_project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(archived_project)).returncode, 0)
            write_state(archived_project, 1)
            make_task(
                archived_project,
                location="archive",
                status="cancelled",
                schema_version=1,
            )
            checked = run_script(
                CHECK_SCRIPT,
                str(archived_project),
                "--target-protocol",
                "2.1",
            )
            self.assertEqual(checked.returncode, 1)
            self.assertIn("requires schema_version: 2", checked.stdout)
            self.assertIn("requires legacy_archive_ids", checked.stdout)
            self.assertEqual(checked.stdout.count("requires legacy_archive_ids"), 1)
            self.assertNotIn(
                "work/archive/T-M01-001-demo/task.yaml: governance protocol 2.1 archived task requires protocol_version",
                checked.stdout,
            )
            self.assertNotIn(
                "work/archive/T-M01-001-demo/task.yaml: missing required field 'risk_level'",
                checked.stdout,
            )

    def test_target_schema_two_preflight_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "migration-preflight"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 1)
            state_path = project / "project" / "state.yaml"
            make_task(project, schema_version=1)
            before = state_path.read_bytes()

            checked = run_script(CHECK_SCRIPT, str(project), "--target-schema", "2")
            self.assertEqual(checked.returncode, 1)
            self.assertIn("target schema 2 preflight failed", checked.stdout)
            self.assertIn("schema v2 active task requires schema_version: 2", checked.stdout)
            self.assertEqual(state_path.read_bytes(), before)

            archived_project = Path(tmp) / "archive-only-preflight"
            archived_project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(archived_project)).returncode, 0)
            write_state(archived_project, 1)
            make_task(
                archived_project,
                location="archive",
                status="cancelled",
                schema_version=1,
            )
            checked = run_script(CHECK_SCRIPT, str(archived_project), "--target-schema", "2")
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertIn("preflight passed (read-only)", checked.stdout)

    def test_decision_outcome_distinguishes_recorded_direction_from_confirmation(self) -> None:
        cases = (
            ("low", "direct_instruction", "start-direction", "recorded"),
            ("medium", "confirmed", "start-confirmation", "confirmed"),
        )
        for risk, status, expected_kind, expected_outcome in cases:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"decision-outcome-{status}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2, protocol_version="2.1")
                task_dir = make_task(
                    project,
                    status="implementing",
                    protocol_version="2.1",
                    risk_level=risk,
                    alignment_ref="alignment/alignment.yaml",
                )
                write_alignment(task_dir, risk_level=risk, start_status=status)
                decisions = task_dir / "decisions.md"
                recorded = decisions.read_text(encoding="utf-8")
                self.assertIn(f"decision-kind: {expected_kind}", recorded)
                self.assertIn(f"Decision outcome: {expected_outcome}", recorded)
                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

                wrong_outcome = "confirmed" if expected_outcome == "recorded" else "recorded"
                decisions.write_text(
                    recorded.replace(
                        f"Decision outcome: {expected_outcome}",
                        f"Decision outcome: {wrong_outcome}",
                        1,
                    ),
                    encoding="utf-8",
                )
                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 1)
                self.assertIn(
                    f"requires exactly one canonical 'Decision outcome: {expected_outcome}'",
                    checked.stdout,
                )

    def test_decision_outcome_must_be_visible_once_outside_fences_and_comments(self) -> None:
        replacements = {
            "fenced": "```text\nDecision outcome: recorded\n```",
            "commented": "<!-- Decision outcome: recorded -->",
            "duplicated": "Decision outcome: recorded\n\nDecision outcome: recorded",
            "hidden": "<div hidden>\nDecision outcome: recorded\n</div>",
            "aria-hidden": '<div aria-hidden="true">\nDecision outcome: recorded\n</div>',
            "style-hidden": '<div style="display: none">\nDecision outcome: recorded\n</div>',
        }
        for case, replacement in replacements.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"decision-visible-{case}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2, protocol_version="2.1")
                task_dir = make_task(
                    project,
                    status="implementing",
                    protocol_version="2.1",
                    risk_level="low",
                    alignment_ref="alignment/alignment.yaml",
                )
                write_alignment(task_dir)
                decisions = task_dir / "decisions.md"
                decisions.write_text(
                    decisions.read_text(encoding="utf-8").replace(
                        "Decision outcome: recorded", replacement, 1
                    ),
                    encoding="utf-8",
                )
                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 1)
                self.assertIn("requires exactly one canonical", checked.stdout)

    def test_decision_heading_requires_visible_natural_language_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "decision-natural-language"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.1")
            task_dir = make_task(
                project,
                status="implementing",
                protocol_version="2.1",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment(task_dir)
            decisions = task_dir / "decisions.md"
            content = decisions.read_text(encoding="utf-8")
            content = content.replace(
                "The project owner made this version-bound decision for the stated scope.\n\n",
                "",
                1,
            )
            decisions.write_text(content, encoding="utf-8")
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("requires a substantive visible natural-language decision", checked.stdout)

    def test_decision_scope_may_withhold_a_different_visual_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "withheld-other-gate"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.1")
            task_dir = make_task(
                project,
                status="implementing",
                task_types=("ux", "ui", "engineering"),
                alignment_mode="mixed",
                design_ref="design/design.yaml",
                protocol_version="2.1",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment(task_dir)
            write_design(task_dir)
            decisions = task_dir / "decisions.md"
            decisions.write_text(
                decisions.read_text(encoding="utf-8").replace(
                    "Decision outcome: approved\n\n<!-- project-memory-decision-binding",
                    "Decision outcome: approved\n\nVisual design is not approved by this experience-only decision.\n\n<!-- project-memory-decision-binding",
                    1,
                ),
                encoding="utf-8",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_alignment_content_rejects_repetition_and_duplicate_sections_but_accepts_chinese(self) -> None:
        headings = (
            "Outcome And H0 Boundary",
            "Scope And Non-goals",
            "Acceptance And Evidence",
            "Risk Assessment",
            "H1 Execution Boundary",
            "Assumptions And Unknowns",
        )
        chinese_bodies = (
            "本任务只验证本地治理规则，目标是让所有者清楚知道开始条件和最终证据。",
            "范围仅限技能脚本与模板，不修改产品仓库、用户数据、网络服务或发布流程。",
            "验收通过完整单元测试、失败夹具和只读项目检查共同证明，不以口头结论替代。",
            "风险来自跨组件治理变化但仍可恢复，因此采用中风险边界并保留独立复核。",
            "代理可自主选择实现细节与测试组织，不能代替所有者批准范围或残余风险。",
            "假设本地文件是可信输入；人类身份与截图来源仍需外部证明才能获得更强保证。",
        )
        for case in ("repeated", "duplicate", "chinese"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"content-quality-{case}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2, protocol_version="2.1")
                task_dir = make_task(
                    project,
                    protocol_version="2.1",
                    risk_level="low",
                    alignment_ref="alignment/alignment.yaml",
                )
                alignment = write_alignment(task_dir, start_status="draft")
                artifact = task_dir / "alignment" / "start-v1.md"
                if case == "repeated":
                    bodies = ("xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",) + chinese_bodies[1:]
                elif case == "duplicate":
                    shared = "This identical body repeats the same generic boundary, evidence, ownership, and risk statement without section-specific facts."
                    bodies = (shared,) * len(headings)
                else:
                    bodies = chinese_bodies
                sections = "\n\n".join(
                    f"## {heading}\n\n{body}" for heading, body in zip(headings, bodies)
                )
                content = f'''<!-- project-memory-artifact: human-start-alignment -->
<!-- task-id: {task_dir.name} -->
<!-- artifact-version: v1 -->

# Human Start Alignment

这份版本化产物记录目标、边界、证据和代理可以自主决定的范围。

{sections}
'''
                artifact.write_text(content, encoding="utf-8")
                replace_yaml_value(
                    alignment,
                    "start_sha256",
                    hashlib.sha256(content.encode("utf-8")).hexdigest(),
                )
                checked = run_script(CHECK_SCRIPT, str(project))
                if case == "chinese":
                    self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
                else:
                    self.assertEqual(checked.returncode, 1)
                    expected = (
                        "lack substantive body"
                        if case == "repeated"
                        else "reuse identical normalized body content"
                    )
                    self.assertIn(expected, checked.stdout)

    def test_repeated_binding_scope_is_not_substantive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "repeated-binding-scope"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.1")
            task_dir = make_task(
                project,
                status="implementing",
                protocol_version="2.1",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment(task_dir)
            decisions = task_dir / "decisions.md"
            decisions.write_text(
                re.sub(
                    r"^scope: .+$",
                    "scope: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                    decisions.read_text(encoding="utf-8"),
                    count=1,
                    flags=re.MULTILINE,
                ),
                encoding="utf-8",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("scope must be substantive", checked.stdout)

    def test_conformance_capture_payload_contract(self) -> None:
        invalid_cases = (
            "implementation-svg",
            "empty-approved-svg",
            "tiny-png",
            "bad-crc",
            "bad-zlib",
            "jpeg",
            "different-state",
            "body-hidden",
            "body-aria-hidden",
            "body-style-hidden",
            "capture-hidden",
        )
        for case in ("valid", *invalid_cases):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"capture-contract-{case}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2, protocol_version="2.1")
                task_dir = make_task(
                    project,
                    status="verifying",
                    task_types=("ui", "engineering"),
                    alignment_mode="visual",
                    design_ref="design/design.yaml",
                    protocol_version="2.1",
                    risk_level="low",
                    alignment_ref="alignment/alignment.yaml",
                )
                write_alignment(task_dir, readout_status="ready")
                design = write_design(task_dir, gate_profile="one_gate", conformance_status="matched")
                conformance = task_dir / "evidence" / "2026-08-09-design-conformance.html"
                content = conformance.read_text(encoding="utf-8")
                valid_uri = re.search(r"data:image/png;base64,[A-Za-z0-9+/=]+", content)
                self.assertIsNotNone(valid_uri)
                uri = valid_uri.group(0)
                if case == "implementation-svg":
                    content = re.sub(
                        r'<img alt="Implementation capture"[^>]*>',
                        '<svg width="320" height="480" viewBox="0 0 320 480"><rect width="320" height="480"></rect><circle cx="80" cy="80" r="40"></circle></svg>',
                        content,
                        count=1,
                    )
                elif case == "empty-approved-svg":
                    content = re.sub(r"<svg role=\"img\".*?</svg>", "<svg></svg>", content, count=1, flags=re.DOTALL)
                elif case == "tiny-png":
                    content = content.replace(uri, png_data_uri(1, 1), 1)
                elif case in {"bad-crc", "bad-zlib"}:
                    payload = bytearray(base64.b64decode(uri.split(",", 1)[1]))
                    offset = 8
                    while offset + 12 <= len(payload):
                        length = struct.unpack(">I", payload[offset : offset + 4])[0]
                        kind = bytes(payload[offset + 4 : offset + 8])
                        if kind == b"IDAT":
                            data_start = offset + 8
                            if case == "bad-crc":
                                payload[data_start] ^= 0x01
                            else:
                                replacement = b"x" * length
                                payload[data_start : data_start + length] = replacement
                                crc = zlib.crc32(kind + replacement) & 0xFFFFFFFF
                                payload[data_start + length : data_start + length + 4] = struct.pack(">I", crc)
                            break
                        offset += 12 + length
                    bad_uri = "data:image/png;base64," + base64.b64encode(payload).decode("ascii")
                    content = content.replace(uri, bad_uri, 1)
                elif case == "jpeg":
                    fake_jpeg = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8" + b"x" * 800 + b"\xff\xd9").decode("ascii")
                    content = content.replace(uri, fake_jpeg, 1)
                elif case == "different-state":
                    content = content.replace(
                        'data-conformance-capture="implementation" data-page-state="primary-normal"',
                        'data-conformance-capture="implementation" data-page-state="primary-error"',
                        1,
                    )
                elif case == "body-hidden":
                    content = content.replace("<body>", "<body hidden>", 1)
                elif case == "body-aria-hidden":
                    content = content.replace("<body>", '<body aria-hidden="true">', 1)
                elif case == "body-style-hidden":
                    content = content.replace("<body>", '<body style="visibility: hidden">', 1)
                elif case == "capture-hidden":
                    content = content.replace(
                        '<figure data-conformance-capture="implementation"',
                        '<figure hidden data-conformance-capture="implementation"',
                        1,
                    )
                conformance.write_text(content, encoding="utf-8")
                replace_yaml_value(
                    design,
                    "conformance_sha256",
                    hashlib.sha256(content.encode("utf-8")).hexdigest(),
                )
                checked = run_script(CHECK_SCRIPT, str(project))
                if case == "valid":
                    self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
                else:
                    self.assertEqual(checked.returncode, 1)
                    self.assertIn("capture", checked.stdout.lower())

    def test_legacy_anchor_two_commit_workflow_passes_before_and_after_record_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "legacy-two-commit"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            legacy_id = "T-M01-001-legacy"
            write_state(
                project,
                2,
                protocol_version="2.1",
                legacy_archive_ids=(legacy_id,),
            )
            make_task(
                project,
                task_id=legacy_id,
                location="archive",
                status="cancelled",
                schema_version=1,
            )
            anchor = establish_legacy_adoption_anchor(project, commit_record=False)
            self.assertEqual(git(project, "rev-parse", "HEAD").stdout.strip(), anchor)
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

            self.assertEqual(git(project, "add", "project/state.yaml").returncode, 0)
            committed = git(project, "commit", "-q", "-m", "record adoption anchor")
            self.assertEqual(committed.returncode, 0, committed.stderr)
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_legacy_anchor_rejects_backfilled_or_changed_task_content(self) -> None:
        for case in ("missing-at-anchor", "changed-after-anchor", "symlink-blob"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"legacy-anchor-{case}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                legacy_id = "T-M01-001-legacy"
                write_state(
                    project,
                    2,
                    protocol_version="2.1",
                    legacy_archive_ids=(legacy_id,),
                )
                task_dir: Path | None = None
                original = ""
                if case != "missing-at-anchor":
                    task_dir = make_task(
                        project,
                        task_id=legacy_id,
                        location="archive",
                        status="cancelled",
                        schema_version=1,
                    )
                    original = (task_dir / "task.yaml").read_text(encoding="utf-8")
                if case == "symlink-blob":
                    external = Path(tmp) / "external-task.yaml"
                    external.write_text(original, encoding="utf-8")
                    (task_dir / "task.yaml").unlink()
                    (task_dir / "task.yaml").symlink_to(external)
                establish_legacy_adoption_anchor(project, commit_record=False)
                if case == "missing-at-anchor":
                    task_dir = make_task(
                        project,
                        task_id=legacy_id,
                        location="archive",
                        status="cancelled",
                        schema_version=1,
                    )
                elif case == "changed-after-anchor":
                    replace_yaml_value(task_dir / "task.yaml", "title", "Changed after adoption")
                else:
                    (task_dir / "task.yaml").unlink()
                    (task_dir / "task.yaml").write_text(original, encoding="utf-8")
                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 1)
                expected = (
                    "as a regular Git blob"
                    if case in {"missing-at-anchor", "symlink-blob"}
                    else "differs from its adoption-commit version"
                )
                self.assertIn(expected, checked.stdout)

    def test_legacy_anchor_ignores_index_flags_and_hashes_actual_worktree(self) -> None:
        for flag in ("assume-unchanged", "skip-worktree"):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"legacy-index-{flag}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                legacy_id = "T-M01-001-legacy"
                write_state(
                    project,
                    2,
                    protocol_version="2.1",
                    legacy_archive_ids=(legacy_id,),
                )
                task_dir = make_task(
                    project,
                    task_id=legacy_id,
                    location="archive",
                    status="cancelled",
                    schema_version=1,
                )
                establish_legacy_adoption_anchor(project)
                relative_task = f"work/archive/{legacy_id}/task.yaml"
                flagged = git(project, "update-index", f"--{flag}", relative_task)
                self.assertEqual(flagged.returncode, 0, flagged.stderr)
                replace_yaml_value(task_dir / "task.yaml", "title", "Changed behind index flag")

                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 1)
                self.assertIn("worktree blob differs", checked.stdout)

    def test_nonempty_legacy_manifest_requires_git_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "legacy-without-git"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            legacy_id = "T-M01-001-legacy"
            write_state(
                project,
                2,
                protocol_version="2.1",
                legacy_archive_ids=(legacy_id,),
                adoption_commit="a" * 40,
            )
            make_task(
                project,
                task_id=legacy_id,
                location="archive",
                status="cancelled",
                schema_version=1,
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("inside a Git repository", checked.stdout)

    def test_structured_effects_derive_non_downgradeable_risk_floor(self) -> None:
        cases = (
            ("effect_reversibility", "partially_reversible", "medium"),
            ("effect_reversibility", "irreversible", "high"),
            ("effect_data", "internal", "medium"),
            ("effect_data", "personal-or-sensitive", "high"),
            ("effect_environment", "shared-nonproduction", "medium"),
            ("effect_environment", "production", "high"),
            ("effect_external", "draft-only", "medium"),
            ("effect_external", "message-or-publish", "high"),
            ("effect_external", "payment-or-legal", "high"),
            ("effect_security_safety", "involved", "high"),
            ("effect_user_impact", "indirect", "medium"),
            ("effect_user_impact", "direct", "high"),
        )
        low_effects = {
            "effect_reversibility": "reversible",
            "effect_data": "none",
            "effect_environment": "local-only",
            "effect_external": "none",
            "effect_security_safety": "none",
            "effect_user_impact": "none",
        }
        factors = {"medium": ("cross-component",), "high": ("security-or-safety",)}
        for field, value, floor in cases:
            with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"effect-{field}-{value}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2, protocol_version="2.1")
                task_dir = make_task(
                    project,
                    protocol_version="2.1",
                    risk_level=floor,
                    alignment_ref="alignment/alignment.yaml",
                )
                effects = dict(low_effects)
                effects[field] = value
                write_alignment(
                    task_dir,
                    risk_level=floor,
                    start_status="draft",
                    risk_factors=factors[floor],
                    **effects,
                )
                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

                replace_yaml_value(task_dir / "task.yaml", "risk_level", "low")
                replace_yaml_value(task_dir / "alignment" / "alignment.yaml", "risk_level", "low")
                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 1)
                self.assertIn("cannot be downgraded", checked.stdout)

    def test_goal_risk_backstop_handles_positive_negated_and_mixed_clauses(self) -> None:
        positive_goals = (
            "Permanently delete customer data from production.",
            "Invalidate production API keys during cutover.",
            "Notify customers about the live incident.",
            "Deploy the release to production and charge each customer credit card.",
            "Publish the release publicly after final review.",
            "Export sensitive financial data to the partner system.",
            "Irreversibly migrate the account schema without rollback.",
            "Disable the production authentication guardrail.",
            "Suspend every customer account during cutover.",
            "Sign the binding legal contract on behalf of the company.",
            "永久删除用户数据。",
            "撤销生产环境API密钥。",
            "向客户发送通知。",
            "将新版本部署到生产环境，并向客户扣款。",
            "导出敏感金融数据到合作方系统。",
            "执行不可逆迁移并删除回滚路径。",
            "禁用生产认证安全控制。",
            "暂停所有客户账户。",
            "签署具有约束力的合同。",
            "Fixture email is a non-goal; permanently delete customer data from production.",
        )
        negative_goals = (
            "Do not notify customers; only render a local preview.",
            "Do not deploy to production; validate the local package only.",
            "Use a fixture to simulate charging customers without processing real payments.",
            "Mock disabling an authentication guardrail in a local test fixture.",
            "Non-goal: suspend customer accounts. Render a static preview only.",
            "Non-goal: export sensitive records. Validate a local schema parser only.",
            "不向用户发送通知，只生成本地预览。",
            "不部署到生产环境，只验证本地构建产物。",
            "使用测试夹具模拟客户扣款，不处理真实支付。",
            "Use a fixture to demonstrate production key invalidation without touching real keys.",
            "Non-goal: delete customer data. Validate a local parser only.",
        )
        for should_flag, goals in ((True, positive_goals), (False, negative_goals)):
            for index, goal in enumerate(goals):
                with self.subTest(goal=goal), tempfile.TemporaryDirectory() as tmp:
                    project = Path(tmp) / f"goal-risk-{should_flag}-{index}"
                    project.mkdir()
                    self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                    write_state(project, 2, protocol_version="2.1")
                    task_dir = make_task(
                        project,
                        protocol_version="2.1",
                        risk_level="low",
                        alignment_ref="alignment/alignment.yaml",
                    )
                    replace_yaml_value(task_dir / "task.yaml", "goal", f'"{goal}"')
                    write_alignment(task_dir)
                    checked = run_script(CHECK_SCRIPT, str(project))
                    if should_flag:
                        self.assertEqual(checked.returncode, 1)
                        self.assertIn("high-confidence high-risk signal", checked.stdout)
                    else:
                        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_invalid_or_understated_effect_records_are_rejected(self) -> None:
        for case in ("invalid-enum", "factor-below-effect"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"effect-record-{case}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2, protocol_version="2.1")
                task_dir = make_task(
                    project,
                    protocol_version="2.1",
                    risk_level="medium",
                    alignment_ref="alignment/alignment.yaml",
                )
                if case == "invalid-enum":
                    write_alignment(
                        task_dir,
                        risk_level="medium",
                        start_status="draft",
                        effect_data="unknown-data-class",
                    )
                    expected = "invalid effect_data"
                else:
                    write_alignment(
                        task_dir,
                        risk_level="medium",
                        start_status="draft",
                        risk_factors=("local-reversible",),
                        effect_environment="shared-nonproduction",
                    )
                    expected = "risk_factors floor low is below structured effect floor medium"
                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 1)
                self.assertIn(expected, checked.stdout)

    def test_checker_rejects_authority_and_task_symlinks_without_traceback(self) -> None:
        for case in ("state", "task-directory", "opt-in-evidence", "done-evidence"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                project = base / f"symlink-{case}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                if case == "state":
                    external = base / "external-state.yaml"
                    state = project / "project" / "state.yaml"
                    state.replace(external)
                    state.symlink_to(external)
                elif case == "task-directory":
                    write_state(project, 2, protocol_version="2.1")
                    task_dir = make_task(
                        project,
                        protocol_version="2.1",
                        risk_level="low",
                        alignment_ref="alignment/alignment.yaml",
                    )
                    write_alignment(task_dir)
                    external = base / "external-task"
                    task_dir.replace(external)
                    task_dir.symlink_to(external, target_is_directory=True)
                else:
                    write_state(
                        project,
                        2,
                        protocol_version=None if case == "opt-in-evidence" else "2.1",
                    )
                    task_dir = make_task(
                        project,
                        location="archive" if case == "done-evidence" else "active",
                        status="done" if case == "done-evidence" else "proposed",
                        protocol_version="2.1",
                        risk_level="low",
                        alignment_ref="alignment/alignment.yaml",
                    )
                    write_alignment(
                        task_dir,
                        readout_status="ready" if case == "done-evidence" else "not_started",
                    )
                    if case == "done-evidence":
                        make_task_done(task_dir)
                    evidence = task_dir / "evidence"
                    external = base / f"external-evidence-{case}"
                    evidence.replace(external)
                    evidence.symlink_to(external, target_is_directory=True)
                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 1)
                self.assertNotIn("Traceback", checked.stdout + checked.stderr)
                self.assertIn("symlink", checked.stdout.lower())

    def test_protocol_21_rejects_milestone_authority_symlink_and_invalid_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            project = base / "milestone-authority-symlink"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.1")
            replace_yaml_value(project / "project" / "state.yaml", "active_milestone", "M01")
            milestone_dir = project / "milestones" / "M01-linked"
            milestone_dir.mkdir()
            (milestone_dir / "brief.md").write_text(
                "# Milestone Brief\nThis milestone boundary is concrete and independently reviewable.\n",
                encoding="utf-8",
            )
            external = base / "external-milestone.yaml"
            external.write_text(
                "id: M01\ntitle: External authority\nstatus: active\n",
                encoding="utf-8",
            )
            (milestone_dir / "milestone.yaml").symlink_to(external)

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("authority descendants must not be symlinks", checked.stdout)
            self.assertIn("active milestone authority file must be a regular file", checked.stdout)
            self.assertNotIn("Traceback", checked.stderr + checked.stdout)

            (milestone_dir / "milestone.yaml").unlink()
            (milestone_dir / "milestone.yaml").write_text(
                "id: M02\ntitle: Wrong milestone identity\nstatus: active\n",
                encoding="utf-8",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("id must match project/state.yaml active_milestone", checked.stdout)

    def test_protocol_22_figma_provider_revision_and_supporting_context_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "v22-figma"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.2")
            task_dir = make_task(
                project,
                task_types=("ux", "ui"),
                alignment_mode="visual",
                design_ref="design/design.yaml",
                protocol_version="2.2",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment_v22(task_dir)
            figma = external_review_surface(
                surface_id="figma-primary",
                role="review-target",
                kind="figma-frame",
                locator="https://www.figma.com/design/example?node-id=12-34",
                revision="figma-file-v88:12-34",
            )
            write_design_v22(
                task_dir,
                visual_surfaces=[figma],
                visual_supporting=[
                    {
                        "id": "research-notes",
                        "role": "context-only/non-binding",
                        "kind": "research-notes",
                        "locator": "https://example.invalid/context",
                    }
                ],
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_protocol_22_local_image_pdf_and_arbitrary_kind_pass_without_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "v22-local-media"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.2")
            task_dir = make_task(
                project,
                task_types=("ui",),
                alignment_mode="visual",
                design_ref="design/design.yaml",
                protocol_version="2.2",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment_v22(task_dir)
            image = file_review_surface(
                task_dir,
                "design/screen.webp",
                surface_id="screen-image",
                role="visual-proposal",
                kind="lossless-screen-capture",
                content=b"RIFF" + b"visual-review-pixels" * 40,
            )
            pdf = file_review_surface(
                task_dir,
                "design/interaction.pdf",
                surface_id="interaction-pdf",
                role="interaction-notes",
                kind="spatial-prototype-v7",
                content=b"%PDF-1.7\n" + b"bounded interaction review evidence\n" * 30,
            )
            write_design_v22(task_dir, visual_surfaces=[image, pdf])

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertFalse(any(task_dir.rglob("*.html")))

    def test_protocol_22_composite_and_custom_identity_pass_with_extra_unordered_covers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "v22-composite"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.2")
            task_dir = make_task(
                project,
                protocol_version="2.2",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            local = file_review_surface(
                task_dir,
                "alignment/start-map.mmd",
                surface_id="local-map",
                role="offline-fallback",
                kind="mermaid-diagram",
                content="flowchart LR\n  Human --> Boundary\n  Boundary --> Evidence\n",
            )
            custom = external_review_surface(
                surface_id="external-prototype",
                role="interactive-review",
                kind="immersive-prototype",
                locator="prototype://workspace/scene/4",
                revision="scene-revision-4471",
                method="custom/vr-scene",
            )
            write_alignment_v22(
                task_dir,
                start_status="awaiting_human",
                start_surfaces=[custom, local],
                start_covers=("L4", "H1", "L2", "H0", "L1", "L3"),
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_protocol_22_draft_mutable_package_needs_no_digest_but_formal_gate_rejects_it(self) -> None:
        for status, should_pass in (("draft", True), ("awaiting_human", False)):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"v22-mutable-{status}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2, protocol_version="2.2")
                task_dir = make_task(
                    project,
                    protocol_version="2.2",
                    risk_level="low",
                    alignment_ref="alignment/alignment.yaml",
                )
                mutable = external_review_surface(
                    surface_id="working-draft",
                    role="draft-source",
                    kind="working-canvas",
                    locator="canvas://mutable/current",
                    revision="current",
                    method="mutable",
                    immutable=False,
                )
                alignment_path = write_alignment_v22(
                    task_dir,
                    start_status=status,
                    start_surfaces=[mutable],
                )
                if status == "awaiting_human":
                    self.assertNotIn(
                        "start_sha256: null",
                        alignment_path.read_text(encoding="utf-8"),
                    )
                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 0 if should_pass else 1, checked.stdout)
                if not should_pass:
                    self.assertIn("requires immutable binding-surface identities", checked.stdout)

    def test_protocol_22_stale_local_identity_and_stale_package_digest_fail(self) -> None:
        for stale_kind in ("local", "package"):
            with self.subTest(stale_kind=stale_kind), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"v22-stale-{stale_kind}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2, protocol_version="2.2")
                task_dir = make_task(
                    project,
                    protocol_version="2.2",
                    risk_level="low",
                    alignment_ref="alignment/alignment.yaml",
                )
                write_alignment_v22(task_dir, start_status="awaiting_human")
                if stale_kind == "local":
                    (task_dir / "evidence" / "start-surface.md").write_text(
                        "The bound local bytes changed after the package was frozen.",
                        encoding="utf-8",
                    )
                    expected = "does not match the local file bytes"
                else:
                    package_path = task_dir / "alignment" / "start-review-v1.json"
                    package = json.loads(package_path.read_text(encoding="utf-8"))
                    package["question"] = "Does this materially changed question still match the previously frozen package digest?"
                    package_path.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
                    expected = "canonical package digest mismatch"
                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 1)
                self.assertIn(expected, checked.stdout)

    def test_protocol_22_digest_covered_approval_change_fails_but_supporting_change_passes(self) -> None:
        for change_kind, should_pass in (
            ("binding-question", False),
            ("extensions", False),
            ("supporting", True),
        ):
            with self.subTest(change_kind=change_kind), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"v22-approval-{change_kind}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2, protocol_version="2.2")
                task_dir = make_task(
                    project,
                    task_types=("ui",),
                    alignment_mode="visual",
                    design_ref="design/design.yaml",
                    protocol_version="2.2",
                    risk_level="low",
                    alignment_ref="alignment/alignment.yaml",
                )
                write_alignment_v22(task_dir)
                write_design_v22(
                    task_dir,
                    visual_status="approved",
                    visual_supporting=[
                        {
                            "id": "optional-context",
                            "role": "context-only/non-binding",
                            "kind": "review-note",
                            "locator": "https://example.invalid/context/v1",
                        }
                    ],
                )
                package_path = task_dir / "design" / "visual-review-v1.json"
                package = json.loads(package_path.read_text(encoding="utf-8"))
                before_digest = canonical_package_digest(package)
                if change_kind == "binding-question":
                    package["question"] = "Does this changed approval question remain authorized without a new exact-version human decision?"
                elif change_kind == "extensions":
                    package["extensions"] = {"adapter": {"revision": "extension-v2"}}
                else:
                    package["supporting_surfaces"][0]["locator"] = (
                        "https://example.invalid/context/v2"
                    )
                after_digest = canonical_package_digest(package)
                package_path.write_text(
                    json.dumps(package, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                self.assertEqual(before_digest == after_digest, should_pass)
                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 0 if should_pass else 1, checked.stdout)
                if not should_pass:
                    self.assertIn("canonical package digest mismatch", checked.stdout)
                    self.assertIn("recorded SHA-256 is stale", checked.stdout)

    def test_protocol_22_high_risk_external_binding_requires_local_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "v22-high-external"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.2")
            task_dir = make_task(
                project,
                task_types=("ui",),
                alignment_mode="visual",
                design_ref="design/design.yaml",
                protocol_version="2.2",
                risk_level="high",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment_v22(task_dir, risk_level="high", start_status="awaiting_human")
            external = external_review_surface(
                surface_id="external-only",
                role="review-target",
                kind="figma-frame",
                locator="https://www.figma.com/design/high-risk",
                revision="revision-991",
            )
            write_design_v22(task_dir, visual_surfaces=[external])

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("requires a local file_sha256 binding fallback", checked.stdout)

    def test_protocol_22_supporting_surfaces_are_explicitly_non_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "v22-support-role"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.2")
            task_dir = make_task(
                project,
                protocol_version="2.2",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment_v22(
                task_dir,
                start_supporting=[
                    {
                        "id": "ambiguous-support",
                        "role": "primary-decision-evidence",
                        "kind": "mutable-note",
                        "locator": "https://example.invalid/latest",
                    }
                ],
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("role must be exactly context-only/non-binding", checked.stdout)

    def test_protocol_22_high_risk_local_git_commit_needs_no_fallback_but_external_git_does(self) -> None:
        for locator, should_pass in (
            ("repository-object:reviewed-tree", True),
            ("https://git.example.invalid/repository/commit", False),
        ):
            with self.subTest(locator=locator), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / "v22-high-git"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2, protocol_version="2.2")
                task_dir = make_task(
                    project,
                    task_types=("ui",),
                    alignment_mode="visual",
                    design_ref="design/design.yaml",
                    protocol_version="2.2",
                    risk_level="high",
                    alignment_ref="alignment/alignment.yaml",
                )
                write_alignment_v22(
                    task_dir,
                    risk_level="high",
                    start_status="awaiting_human",
                )
                commit_surface = external_review_surface(
                    surface_id="reviewed-commit",
                    role="immutable-review-scope",
                    kind="git-tree",
                    locator=locator,
                    revision="a" * 40,
                    method="git_commit",
                )
                write_design_v22(task_dir, visual_surfaces=[commit_surface])

                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 0 if should_pass else 1, checked.stdout)
                if not should_pass:
                    self.assertIn(
                        "requires a local file_sha256 binding fallback",
                        checked.stdout,
                    )

    def test_protocol_22_formal_package_rejects_digest_covered_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "v22-formal-placeholder"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.2")
            task_dir = make_task(
                project,
                protocol_version="2.2",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            placeholder_surface = external_review_surface(
                surface_id="claimed-stable",
                role="primary-review",
                kind="provider-frame",
                locator="canvas://replace-with-review-surface",
                revision="replace-with-stable-revision",
            )
            write_alignment_v22(
                task_dir,
                start_status="awaiting_human",
                start_surfaces=[placeholder_surface],
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn(
                "formal review package contains an unresolved placeholder",
                checked.stdout,
            )

    def test_protocol_22_provider_revision_rejects_mutable_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "v22-provider-latest"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.2")
            task_dir = make_task(
                project,
                protocol_version="2.2",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            claimed_revision = external_review_surface(
                surface_id="mutable-provider-view",
                role="primary-review",
                kind="provider-frame",
                locator="https://provider.invalid/file/42",
                revision="latest",
            )
            write_alignment_v22(
                task_dir,
                start_status="awaiting_human",
                start_surfaces=[claimed_revision],
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn(
                "provider_revision must name a stable provider revision",
                checked.stdout,
            )

    def test_protocol_22_rejects_duplicate_or_nonstandard_json_members(self) -> None:
        for malformed_kind in ("duplicate", "nan"):
            with self.subTest(malformed_kind=malformed_kind), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"v22-malformed-{malformed_kind}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2, protocol_version="2.2")
                task_dir = make_task(
                    project,
                    protocol_version="2.2",
                    risk_level="low",
                    alignment_ref="alignment/alignment.yaml",
                )
                write_alignment_v22(task_dir)
                package_path = task_dir / "alignment" / "start-review-v1.json"
                raw = package_path.read_text(encoding="utf-8")
                if malformed_kind == "duplicate":
                    raw = '{"schema_version": 1,' + raw[1:]
                else:
                    raw = raw.replace('"schema_version": 1', '"schema_version": NaN', 1)
                package_path.write_text(raw, encoding="utf-8")

                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 1)
                self.assertIn("review package must contain one valid JSON object", checked.stdout)

    def test_protocol_22_package_filename_version_and_lowercase_hashes_are_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "v22-package-identity"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.2")
            task_dir = make_task(
                project,
                protocol_version="2.2",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment_v22(task_dir)
            package_path = task_dir / "alignment" / "start-review-v1.json"
            package = json.loads(package_path.read_text(encoding="utf-8"))
            package["package_version"] = "v2"
            package["binding_surfaces"][0]["identity"]["value"] = package[
                "binding_surfaces"
            ][0]["identity"]["value"].upper()
            package_path.write_text(
                json.dumps(package, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            alignment_path = task_dir / "alignment" / "alignment.yaml"
            replace_yaml_value(
                alignment_path,
                "start_sha256",
                canonical_package_digest(package).upper(),
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("package_version must match the -vN.json filename", checked.stdout)
            self.assertIn("requires a valid canonical package SHA-256", checked.stdout)
            self.assertIn("identity.value requires a valid SHA-256", checked.stdout)

    def test_protocol_22_active_task_pointer_and_milestone_index_are_coherent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "v22-active-pointer"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.2")
            task_dir = make_task(
                project,
                status="implementing",
                protocol_version="2.2",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment_v22(task_dir)

            missing_pointer = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(missing_pointer.returncode, 1)
            self.assertIn(
                "active_task must point to the approved-through-verifying task",
                missing_pointer.stdout,
            )

            state_path = project / "project" / "state.yaml"
            replace_yaml_value(state_path, "active_task", task_dir.name)
            replace_yaml_value(state_path, "active_milestone", "M01")
            milestone_dir = project / "milestones" / "M01-active"
            milestone_dir.mkdir()
            (milestone_dir / "brief.md").write_text(
                "# Active milestone\n\nCoordinate the adaptive review task.\n",
                encoding="utf-8",
            )
            (milestone_dir / "milestone.yaml").write_text(
                """id: M01
title: Active milestone
status: active
owner: human
created: 2026-08-09
updated: 2026-08-09
goal: Coordinate the adaptive review task
dependencies: []
tasks: []
acceptance_criteria: [The task is indexed]
""",
                encoding="utf-8",
            )
            missing_index = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(missing_index.returncode, 1)
            self.assertIn("must be indexed by the active milestone", missing_index.stdout)

            replace_yaml_value(task_dir / "task.yaml", "milestone", "M02")
            mismatch = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(mismatch.returncode, 1)
            self.assertIn("milestone must match project/state.yaml active_milestone", mismatch.stdout)

    def test_protocol_22_design_only_supports_one_combined_gate_for_approved_experience(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "v22-design-only-one-gate"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.2")
            task_dir = make_task(
                project,
                status="reviewing",
                task_types=("ux", "ui"),
                alignment_mode="visual",
                design_ref="design/design.yaml",
                protocol_version="2.2",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment_v22(task_dir, readout_status="ready")
            write_design_v22(
                task_dir,
                gate_profile="design_only",
                experience_status="not_required",
                visual_status="approved",
                conformance_status="not_required",
            )
            replace_yaml_value(
                project / "project" / "state.yaml",
                "active_milestone",
                "M01",
            )
            replace_yaml_value(
                project / "project" / "state.yaml",
                "active_task",
                task_dir.name,
            )
            milestone_dir = project / "milestones" / "M01-demo"
            milestone_dir.mkdir()
            (milestone_dir / "brief.md").write_text(
                "# Milestone brief\n\nValidate the adaptive design-only gate.\n",
                encoding="utf-8",
            )
            (milestone_dir / "milestone.yaml").write_text(
                f'''id: M01
title: Adaptive design gate
status: active
owner: human
created: 2026-08-09
updated: 2026-08-09
goal: Validate a bounded adaptive review flow
dependencies: []
tasks: [{task_dir.name}]
acceptance_criteria: [The combined gate remains mechanically valid]
''',
                encoding="utf-8",
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_protocol_22_readout_package_requires_h3_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "v22-readout-h3"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.2")
            task_dir = make_task(
                project,
                protocol_version="2.2",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment_v22(
                task_dir,
                readout_status="ready",
                readout_covers=("HumanReadout",),
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("covers must include HumanReadout, H3", checked.stdout)

    def test_protocol_22_conformance_requires_role_pair_with_shared_page_state(self) -> None:
        for shared_state, should_pass in ((False, False), (True, True)):
            with self.subTest(shared_state=shared_state), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"v22-conformance-{shared_state}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(project, 2, protocol_version="2.2")
                task_dir = make_task(
                    project,
                    task_types=("ui",),
                    alignment_mode="visual",
                    design_ref="design/design.yaml",
                    protocol_version="2.2",
                    risk_level="low",
                    alignment_ref="alignment/alignment.yaml",
                )
                write_alignment_v22(task_dir)
                baseline = file_review_surface(
                    task_dir,
                    "design/baseline.pdf",
                    surface_id="approved",
                    role="approved-baseline",
                    kind="approved-review-pdf",
                    content=b"%PDF baseline" * 80,
                    page_state="dashboard-normal",
                )
                implementation = file_review_surface(
                    task_dir,
                    "evidence/implementation.mp4",
                    surface_id="implementation",
                    role="implementation-capture",
                    kind="screen-recording",
                    content=b"video capture" * 80,
                    page_state="dashboard-normal" if shared_state else "dashboard-error",
                )
                write_design_v22(
                    task_dir,
                    visual_status="approved",
                    conformance_status="matched",
                    conformance_surfaces=[baseline, implementation],
                )
                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 0 if should_pass else 1, checked.stdout)
                if not should_pass:
                    self.assertIn("sharing page_state", checked.stdout)

    def test_protocol_22_conformance_requires_every_page_state_on_both_sides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "v22-conformance-complete-pairs"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.2")
            task_dir = make_task(
                project,
                task_types=("ui",),
                alignment_mode="visual",
                design_ref="design/design.yaml",
                protocol_version="2.2",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment_v22(task_dir)
            surfaces = [
                file_review_surface(
                    task_dir,
                    "design/baseline-normal.png",
                    surface_id="baseline-normal",
                    role="approved-baseline",
                    kind="screen-capture",
                    content=b"approved normal state" * 40,
                    page_state="dashboard-normal",
                ),
                file_review_surface(
                    task_dir,
                    "design/baseline-error.png",
                    surface_id="baseline-error",
                    role="approved-baseline",
                    kind="screen-capture",
                    content=b"approved error state" * 40,
                    page_state="dashboard-error",
                ),
                file_review_surface(
                    task_dir,
                    "evidence/implementation-normal.png",
                    surface_id="implementation-normal",
                    role="implementation-capture",
                    kind="screen-capture",
                    content=b"implementation normal state" * 40,
                    page_state="dashboard-normal",
                ),
            ]
            write_design_v22(
                task_dir,
                visual_status="approved",
                conformance_status="matched",
                conformance_surfaces=surfaces,
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("identical sets", checked.stdout)

    def test_protocol_22_universal_packages_accept_pdf_composite_html_and_video(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "v22-universal-media"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.2")
            task_dir = make_task(
                project,
                protocol_version="2.2",
                risk_level="medium",
                alignment_ref="alignment/alignment.yaml",
            )
            pdf = file_review_surface(
                task_dir,
                "alignment/journey.pdf",
                surface_id="journey-pdf",
                role="offline-review",
                kind="journey-pdf",
                content=b"%PDF-1.7\n" + b"H0 H1 bounded journey evidence\n" * 30,
            )
            external = external_review_surface(
                surface_id="versioned-board",
                role="interactive-review",
                kind="diagram-board",
                locator="https://provider.invalid/board/22",
                revision="board-revision-9",
            )
            html = file_review_surface(
                task_dir,
                "evidence/readout.html",
                surface_id="readout-html",
                role="human-readout",
                kind="readout-page",
                content=(
                    "<!doctype html><html><head><meta charset='utf-8'><title>Readout</title></head>"
                    "<body><main><h1>Outcome review</h1><p>The delivered result, preserved boundary, "
                    "acceptance evidence, confidence, residual risk, and next decision are presented here "
                    "as substantive visible content without requiring any protocol-specific headings or remote assets."
                    "</p></main></body></html>"
                ),
            )
            video = file_review_surface(
                task_dir,
                "evidence/walkthrough.mp4",
                surface_id="walkthrough-video",
                role="demonstration",
                kind="screen-recording",
                content=b"offline video walkthrough" * 40,
            )
            write_alignment_v22(
                task_dir,
                risk_level="medium",
                start_status="awaiting_human",
                start_surfaces=[external, pdf],
                readout_status="ready",
                readout_surfaces=[html, video],
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_protocol_22_reviewing_freezes_even_draft_readout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "v22-reviewing-draft"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.2")
            task_dir = make_task(
                project,
                status="reviewing",
                protocol_version="2.2",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            mutable = external_review_surface(
                surface_id="mutable-readout",
                role="working-readout",
                kind="working-canvas",
                locator="canvas://readout/current",
                revision="current",
                method="mutable",
                immutable=False,
            )
            write_alignment_v22(
                task_dir,
                readout_status="draft",
                readout_surfaces=[mutable],
                freeze_draft_readout=True,
            )

            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("requires immutable binding-surface identities", checked.stdout)

    def test_protocol_22_target_preflight_is_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "v22-preflight"
            project.mkdir()
            self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
            write_state(project, 2, protocol_version="2.1")
            task_dir = make_task(
                project,
                protocol_version="2.1",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment(task_dir)
            archive_dir = make_task(
                project,
                task_id="T-M01-002-historical",
                location="archive",
                status="done",
                protocol_version="2.1",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            make_task_done(archive_dir)
            write_alignment(archive_dir, readout_status="ready")
            watched = [
                project / "project" / "state.yaml",
                task_dir / "task.yaml",
                archive_dir / "task.yaml",
            ]
            before = {path: path.read_bytes() for path in watched}

            checked = run_script(
                CHECK_SCRIPT,
                str(project),
                "--target-protocol",
                "2.2",
            )
            self.assertEqual(checked.returncode, 1)
            self.assertIn("target protocol 2.2 preflight failed", checked.stdout)
            self.assertIn("requires governance_protocol_version_adopted_at", checked.stdout)
            self.assertIn('requires protocol_version: "2.2"', checked.stdout)
            self.assertNotIn("T-M01-002-historical", checked.stdout)
            self.assertEqual({path: path.read_bytes() for path in watched}, before)

    def test_protocol_22_grandfathers_terminal_protocol_21_archive_by_version_date(self) -> None:
        cases = (
            ("2026-08-08", "2026-08-09", True),
            ("2026-08-08", "2026-08-13", False),
            ("2026-08-10", "2026-08-09", False),
        )
        for created, updated, should_pass in cases:
            with self.subTest(created=created, updated=updated), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp) / f"v22-archive-{created}-{updated}"
                project.mkdir()
                self.assertEqual(run_script(INIT_SCRIPT, str(project)).returncode, 0)
                write_state(
                    project,
                    2,
                    protocol_version="2.2",
                    adopted_at="2026-08-01T00:00:00+08:00",
                    version_adopted_at="2026-08-12T00:00:00+08:00",
                )
                task_dir = make_task(
                    project,
                    location="archive",
                    status="done",
                    protocol_version="2.1",
                    risk_level="low",
                    alignment_ref="alignment/alignment.yaml",
                )
                replace_yaml_value(task_dir / "task.yaml", "created", created)
                replace_yaml_value(task_dir / "task.yaml", "updated", updated)
                make_task_done(task_dir)
                write_alignment(task_dir, readout_status="ready")

                checked = run_script(CHECK_SCRIPT, str(project))
                self.assertEqual(checked.returncode, 0 if should_pass else 1, checked.stdout)
                if not should_pass:
                    self.assertIn("must migrate to protocol 2.2", checked.stdout)


if __name__ == "__main__":
    unittest.main()
