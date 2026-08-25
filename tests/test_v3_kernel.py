from __future__ import annotations

import hashlib
import base64
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent
if str(TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTS_ROOT))

from test_project_memory import (
    CHECK_SCRIPT,
    INIT_SCRIPT,
    make_task,
    png_data_uri,
    run_script,
    write_alignment,
    write_alignment_v22,
)


def git(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(project), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def init_git(project: Path) -> str:
    assert git(project, "init", "-q").returncode == 0
    assert git(project, "config", "user.email", "fixture@example.invalid").returncode == 0
    assert git(project, "config", "user.name", "Fixture").returncode == 0
    assert git(project, "add", ".").returncode == 0
    assert git(project, "commit", "-qm", "fixture").returncode == 0
    result = git(project, "rev-parse", "HEAD")
    assert result.returncode == 0
    return result.stdout.strip()


def append_yaml(path: Path, **values: object) -> None:
    lines: list[str] = []
    for key, value in values.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        elif value is None:
            rendered = "null"
        elif isinstance(value, (list, tuple)):
            rendered = "[" + ", ".join(str(item) for item in value) + "]"
        else:
            rendered = str(value)
        lines.append(f"{key}: {rendered}\n")
    path.write_text(path.read_text(encoding="utf-8") + "".join(lines), encoding="utf-8")


def write_claim(
    path: Path,
    *,
    task_ref: str,
    subject: str,
    subject_ref: str | None = None,
    subject_paths: list[str] | None = None,
    mode: str | None = None,
    actor_modified_subject: bool | None = None,
    verdict: str | None = None,
    action_refs: list[str] | None = None,
    baseline_subject: str | None = None,
    implementation_render_subject: str | None = None,
) -> None:
    lines = ["---", f"task_ref: {task_ref}", f"subject: {subject}"]
    if subject_ref is not None:
        lines.append(f"subject_ref: {subject_ref}")
    if subject_paths is not None:
        lines.append(f"subject_paths: [{', '.join(subject_paths)}]")
    if mode is not None:
        lines.append(f"mode: {mode}")
    if actor_modified_subject is not None:
        lines.append(f"actor_modified_subject: {'true' if actor_modified_subject else 'false'}")
    if verdict is not None:
        lines.append(f"verdict: {verdict}")
    if action_refs is not None:
        lines.append(f"action_refs: [{', '.join(action_refs)}]")
    if baseline_subject is not None:
        lines.append(f"baseline_subject: {baseline_subject}")
    if implementation_render_subject is not None:
        lines.append(f"implementation_render_subject: {implementation_render_subject}")
    lines.extend(["---", "# Durable claim", "This record binds the claim to the exact scoped implementation subject.", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def substantive_html(label: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>Visual artifact</title></head>"
        f"<body><main data-visual-surface><h1>{label}</h1><p>This visible offline surface provides a concrete full-screen "
        "render with real hierarchy, content density, state, and comparison context for human review.</p>"
        "<section><h2>Primary state</h2><button type='button'>Continue</button></section></main></body></html>"
    )


def write_png(path: Path, width: int = 32, height: int = 32) -> None:
    encoded = png_data_uri(width, height).split(",", 1)[1]
    path.write_bytes(base64.b64decode(encoded))


def write_v3_project(
    project: Path,
    *,
    task_id: str = "T-001-initial",
    status: str = "proposed",
    risk: str = "low",
    active_task: str | None = None,
    extras: dict[str, object] | None = None,
) -> Path:
    task_dir = project / "work" / "active" / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    (project / "project").mkdir(parents=True, exist_ok=True)
    (project / "AGENTS.md").write_text(
        "# Project memory\nRead state, then its recovery-focus task and referenced context.\n",
        encoding="utf-8",
    )
    focus = task_id if active_task is None else active_task
    focus_value = focus if focus else "null"
    (project / "project" / "state.yaml").write_text(
        f'''schema_version: 3
protocol_version: "3.0"
project_id: TEST
project_name: Test
status: active
active_task: {focus_value}
updated: 2026-08-19
''',
        encoding="utf-8",
    )
    task = task_dir / "task.yaml"
    task.write_text(
        f'''schema_version: 3
protocol_version: "3.0"
id: {task_id}
status: {status}
goal: Deliver one bounded result
scope: [src]
non_goals: [external side effects]
acceptance: [checker passes]
risk: {risk}
risk_reasons: [{"security-or-safety" if risk == "high" else "local-reversible"}]
protected_paths: []
context_refs: []
decision_refs: []
evidence_refs: []
updated: 2026-08-19
''',
        encoding="utf-8",
    )
    if extras:
        append_yaml(task, **extras)
    return task_dir


class MinimalContinuityKernelTest(unittest.TestCase):
    def test_minimal_project_passes_focus_full_and_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "minimal"
            project.mkdir()
            write_v3_project(project)
            for args in ((), ("--focus",), ("--full",), ("--migration",)):
                checked = run_script(CHECK_SCRIPT, str(project), *args)
                self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_active_task_is_recovery_focus_not_mutex_or_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "multi"
            project.mkdir()
            write_v3_project(project, status="waiting-on-local-tool")
            write_v3_project(
                project,
                task_id="T-002-parallel",
                status="building-in-another-harness",
                active_task="T-001-initial",
            )
            checked = run_script(CHECK_SCRIPT, str(project), "--full")
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_focus_mode_avoids_internal_subagent_full_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "focus"
            project.mkdir()
            write_v3_project(project)
            broken = project / "work" / "active" / "T-002-broken"
            broken.mkdir(parents=True)
            (broken / "task.yaml").write_text("schema_version: 3\n", encoding="utf-8")
            self.assertEqual(run_script(CHECK_SCRIPT, str(project)).returncode, 0)
            self.assertEqual(run_script(CHECK_SCRIPT, str(project), "--full").returncode, 1)

    def test_generic_next_cannot_cross_an_unresolved_choice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "choice"
            project.mkdir()
            write_v3_project(
                project,
                status="working",
                extras={
                    "authorization_basis": "generic-next",
                    "unresolved_choices": ["navigation model"],
                    "implementation_started": True,
                },
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("cannot establish human authorization", checked.stdout)
            self.assertIn("unresolved product choices", checked.stdout)

    def test_declared_dirty_and_untracked_protected_paths_are_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "protected"
            project.mkdir()
            task = write_v3_project(project)
            (project / "owner.txt").write_text("original\n", encoding="utf-8")
            init_git(project)
            (project / "owner.txt").write_text("owner dirty bytes\n", encoding="utf-8")
            (project / "owner-untracked.txt").write_text("untracked owner bytes\n", encoding="utf-8")
            task_file = task / "task.yaml"
            task_file.write_text(
                task_file.read_text(encoding="utf-8").replace(
                    "protected_paths: []",
                    "protected_paths: [owner.txt, owner-untracked.txt]",
                ),
                encoding="utf-8",
            )
            before = {
                name: (project / name).read_bytes()
                for name in ("owner.txt", "owner-untracked.txt")
            }
            for flag in ("--focus", "--full"):
                checked = run_script(CHECK_SCRIPT, str(project), flag)
                self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertEqual(
                before,
                {name: (project / name).read_bytes() for name in before},
            )

    def test_subject_freshness_is_scoped_not_whole_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "subject"
            project.mkdir()
            task_dir = write_v3_project(project)
            (project / "src").mkdir()
            (project / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
            review = task_dir / "review.md"
            review.write_text(
                "# Review\nThe independent actor reproduced the bounded behavior and inspected the implementation subject.\n",
                encoding="utf-8",
            )
            head = init_git(project)
            write_claim(
                review,
                task_ref=f"work/active/{task_dir.name}/task.yaml",
                subject=f"git:{head}",
                subject_paths=["src/app.py"],
                mode="fresh_context",
                actor_modified_subject=False,
                verdict="passed",
            )
            append_yaml(
                task_dir / "task.yaml",
                review_ref=f"work/active/{task_dir.name}/review.md",
                review_current=True,
            )
            (project / "owner-note.txt").write_text("unrelated dirty owner note\n", encoding="utf-8")
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            (project / "src" / "app.py").write_text("VALUE = 2\n", encoding="utf-8")
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("stale for its declared subject_paths", checked.stdout)

    def test_git_subject_rejects_a_phantom_scope_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "phantom-subject"
            project.mkdir()
            task_dir = write_v3_project(project)
            review = task_dir / "review.md"
            review.write_text(
                "# Review\nThis claim deliberately names a path absent from both the commit and current worktree.\n",
                encoding="utf-8",
            )
            head = init_git(project)
            write_claim(
                review,
                task_ref=f"work/active/{task_dir.name}/task.yaml",
                subject=f"git:{head}",
                subject_paths=["src/never-existed.py"],
                mode="fresh_context",
                actor_modified_subject=False,
                verdict="passed",
            )
            append_yaml(
                task_dir / "task.yaml",
                review_ref=f"work/active/{task_dir.name}/review.md",
                review_current=True,
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("never identifies a regular file", checked.stdout)

    def test_harness_handoff_is_optional_and_does_not_reapprove_product_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "handoff"
            project.mkdir()
            task_dir = write_v3_project(project, status="resumed-by-grok")
            handoff = task_dir / "handoff.md"
            handoff.write_text(
                "# Handoff\nClaude reports the unfinished local invariant, observed command result, and next safe point; Codex or Grok must verify it.\n",
                encoding="utf-8",
            )
            append_yaml(
                task_dir / "task.yaml",
                handoff_ref=f"work/active/{task_dir.name}/handoff.md",
                handoff_current=False,
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertNotIn("approval", checked.stdout.lower())

    def test_hermes_claude_codex_claude_pipeline_uses_claims_not_static_roles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "cross-harness-pipeline"
            project.mkdir()
            task_dir = write_v3_project(
                project,
                status="verified-by-claude",
                extras={"completion_claim": True},
            )
            implementation = project / "result.bin"
            implementation.write_bytes(b"codex implementation reviewed from a separate claude event")
            digest = hashlib.sha256(implementation.read_bytes()).hexdigest()
            decision = task_dir / "decisions.md"
            decision.write_text(
                "# Product decision\nHermes proposed the boundary and Claude found no unresolved product conflict before implementation.\n",
                encoding="utf-8",
            )
            handoff = task_dir / "handoff.md"
            handoff.write_text(
                "# Builder claim\nCodex reports the delivered subject and observed local checks for the next verifier to reproduce.\n",
                encoding="utf-8",
            )
            review = task_dir / "review.md"
            review.write_text(
                "# Verification event\nClaude independently inspected the exact subject without changing it and reproduced the acceptance result.\n",
                encoding="utf-8",
            )
            write_claim(
                handoff,
                task_ref=f"work/active/{task_dir.name}/task.yaml",
                subject=f"sha256:{digest}",
                subject_ref="result.bin",
            )
            write_claim(
                review,
                task_ref=f"work/active/{task_dir.name}/task.yaml",
                subject=f"sha256:{digest}",
                subject_ref="result.bin",
                mode="independent_actor",
                actor_modified_subject=False,
                verdict="passed",
            )
            task = task_dir / "task.yaml"
            task.write_text(
                task.read_text(encoding="utf-8").replace(
                    "decision_refs: []",
                    f"decision_refs: [work/active/{task_dir.name}/decisions.md]",
                ),
                encoding="utf-8",
            )
            append_yaml(
                task,
                handoff_ref=f"work/active/{task_dir.name}/handoff.md",
                handoff_current=True,
                review_ref=f"work/active/{task_dir.name}/review.md",
                review_current=True,
            )
            for flag in ("--focus", "--full"):
                checked = run_script(CHECK_SCRIPT, str(project), flag)
                self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            content = task.read_text(encoding="utf-8")
            self.assertNotIn("builder_id", content)
            self.assertNotIn("verifier_id", content)

    def test_high_risk_completion_requires_independent_actor_and_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "high"
            project.mkdir()
            task_dir = write_v3_project(project, status="done", risk="high")
            source = project / "result.bin"
            source.write_bytes(b"bounded implementation subject")
            decision = task_dir / "decisions.md"
            decision.write_text(
                "# Completion acceptance\nThe human owner accepts this exact high-risk completion outcome and its recorded residual boundary.\n",
                encoding="utf-8",
            )
            review = task_dir / "review.md"
            review.write_text(
                "# High-risk verification\nThe independent event inspected the exact subject without modifying it and recorded a formal verdict.\n",
                encoding="utf-8",
            )
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            write_claim(
                review,
                task_ref=f"work/active/{task_dir.name}/task.yaml",
                subject=f"sha256:{digest}",
                subject_ref="result.bin",
                mode="self_check",
                actor_modified_subject=False,
                verdict="passed",
            )
            append_yaml(
                task_dir / "task.yaml",
                review_ref=f"work/active/{task_dir.name}/review.md",
                completion_acceptance_ref=f"work/active/{task_dir.name}/decisions.md",
                external_effects="none",
            )
            checked = run_script(CHECK_SCRIPT, str(project), "--full")
            self.assertEqual(checked.returncode, 1)
            self.assertIn("review mode: independent_actor", checked.stdout)
            review.write_text(
                review.read_text(encoding="utf-8").replace("mode: self_check", "mode: independent_actor"),
                encoding="utf-8",
            )
            checked = run_script(CHECK_SCRIPT, str(project), "--full")
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_reviewer_who_modifies_subject_cannot_claim_independent_actor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "reviewer-modified"
            project.mkdir()
            task_dir = write_v3_project(project, status="done", risk="high")
            subject = project / "result.bin"
            subject.write_bytes(b"reviewer changed these implementation bytes")
            acceptance = task_dir / "decisions.md"
            acceptance.write_text(
                "# Human completion\nThe owner accepts the exact high-risk outcome after the independent event is valid.\n",
                encoding="utf-8",
            )
            review = task_dir / "review.md"
            review.write_text(
                "# Invalid independence claim\nThe same actor changed the subject and therefore cannot supply an independent verdict.\n",
                encoding="utf-8",
            )
            digest = hashlib.sha256(subject.read_bytes()).hexdigest()
            write_claim(
                review,
                task_ref=f"work/active/{task_dir.name}/task.yaml",
                subject=f"sha256:{digest}",
                subject_ref="result.bin",
                mode="independent_actor",
                actor_modified_subject=True,
                verdict="passed",
            )
            append_yaml(
                task_dir / "task.yaml",
                review_ref=f"work/active/{task_dir.name}/review.md",
                completion_acceptance_ref=f"work/active/{task_dir.name}/decisions.md",
                external_effects="none",
            )
            checked = run_script(CHECK_SCRIPT, str(project), "--full")
            self.assertEqual(checked.returncode, 1)
            self.assertIn("modified the subject is not independent", checked.stdout)

    def test_native_v3_rejects_task_duplicates_of_review_owned_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "review-subject-mismatch"
            project.mkdir()
            task_dir = write_v3_project(project, status="done", risk="high")
            reviewed = project / "reviewed.bin"
            declared = project / "declared.bin"
            reviewed.write_bytes(b"reviewed implementation")
            declared.write_bytes(b"different implementation")
            reviewed_digest = hashlib.sha256(reviewed.read_bytes()).hexdigest()
            declared_digest = hashlib.sha256(declared.read_bytes()).hexdigest()
            review = task_dir / "review.md"
            write_claim(
                review,
                task_ref=f"work/active/{task_dir.name}/task.yaml",
                subject=f"sha256:{reviewed_digest}",
                subject_ref="reviewed.bin",
                mode="independent_actor",
                actor_modified_subject=False,
                verdict="passed",
            )
            acceptance = task_dir / "acceptance.md"
            acceptance.write_text(
                "The human owner accepts this exact high-impact completion boundary.\n",
                encoding="utf-8",
            )
            append_yaml(
                task_dir / "task.yaml",
                verification_subject=f"sha256:{declared_digest}",
                verification_subject_ref="declared.bin",
                review_ref=f"work/active/{task_dir.name}/review.md",
                completion_acceptance_ref=f"work/active/{task_dir.name}/acceptance.md",
                external_effects="none",
            )
            checked = run_script(CHECK_SCRIPT, str(project), "--full")
            self.assertEqual(checked.returncode, 1)
            self.assertIn("duplicates review-owned formal metadata", checked.stdout)

    def test_reserved_completion_acceptance_must_be_a_nonempty_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "empty-completion-decision"
            project.mkdir()
            task_dir = write_v3_project(
                project,
                status="completed-locally",
                extras={"completion_claim": True, "human_completion_reserved": True},
            )
            decision = task_dir / "decisions.md"
            decision.write_text("   \n", encoding="utf-8")
            append_yaml(
                task_dir / "task.yaml",
                completion_acceptance_ref=f"work/active/{task_dir.name}/decisions.md",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("claim artifact must not be empty", checked.stdout)
            decision.write_text(
                "The human owner accepts this exact reserved completion outcome.\n",
                encoding="utf-8",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_visual_conformance_claim_requires_render_baseline_and_human_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "visual"
            project.mkdir()
            write_v3_project(project, extras={"conformance_status": "matched"})
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("stable approved-baseline and implementation-render subjects", checked.stdout)

    def test_visual_conformance_binds_stable_baseline_render_and_nonempty_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "visual-exactness"
            project.mkdir()
            task_dir = write_v3_project(project)
            baseline = task_dir / "baseline.html"
            render = task_dir / "render.png"
            review = task_dir / "review.md"
            decision = task_dir / "decisions.md"
            baseline.write_text(substantive_html("Approved baseline"), encoding="utf-8")
            write_png(render)
            decision.write_bytes(b"")
            baseline_digest = hashlib.sha256(baseline.read_bytes()).hexdigest()
            render_digest = hashlib.sha256(render.read_bytes()).hexdigest()
            write_claim(
                review,
                task_ref=f"work/active/{task_dir.name}/task.yaml",
                subject=f"sha256:{render_digest}",
                subject_ref=f"work/active/{task_dir.name}/render.png",
                mode="fresh_context",
                actor_modified_subject=False,
                verdict="passed",
                baseline_subject=f"sha256:{baseline_digest}",
                implementation_render_subject=f"sha256:{render_digest}",
            )
            append_yaml(
                task_dir / "task.yaml",
                conformance_status="matched",
                approved_baseline_ref=f"work/active/{task_dir.name}/baseline.html",
                approved_baseline_subject=f"sha256:{baseline_digest}",
                implementation_render_ref=f"work/active/{task_dir.name}/render.png",
                implementation_render_subject=f"sha256:{render_digest}",
                baseline_decision_ref=f"work/active/{task_dir.name}/decisions.md",
                review_ref=f"work/active/{task_dir.name}/review.md",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("claim artifact must not be empty", checked.stdout)
            decision.write_text(
                "The human owner approved this exact stable baseline for conformance comparison.\n",
                encoding="utf-8",
            )
            review.write_text(
                review.read_text(encoding="utf-8").replace(
                    f"baseline_subject: sha256:{baseline_digest}",
                    "baseline_subject: sha256:" + "0" * 64,
                ),
                encoding="utf-8",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("conformance review must bind the exact approved_baseline_subject", checked.stdout)
            review.write_text(
                review.read_text(encoding="utf-8").replace(
                    "baseline_subject: sha256:" + "0" * 64,
                    f"baseline_subject: sha256:{baseline_digest}",
                ),
                encoding="utf-8",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            task = task_dir / "task.yaml"
            task.write_text(
                task.read_text(encoding="utf-8").replace(
                    "conformance_status: matched",
                    "conformance_status: differences_accepted",
                ),
                encoding="utf-8",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("accepted visual differences require", checked.stdout)
            differences = task_dir / "difference-decision.md"
            differences.write_text(
                "The human owner accepts the exact recorded visual differences for this stable comparison.\n",
                encoding="utf-8",
            )
            append_yaml(
                task,
                difference_decision_ref=f"work/active/{task_dir.name}/difference-decision.md",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            write_png(render, 33, 32)
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("implementation_render_subject: artifact subject is stale", checked.stdout)

    def test_ambiguous_high_impact_action_stops_and_cannot_blind_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "action"
            project.mkdir()
            task_dir = write_v3_project(project, status="blocked", risk="high")
            authority = task_dir / "authority.md"
            authority.write_text(
                "The human owner authorized one bounded production action for this exact target and payload.\n",
                encoding="utf-8",
            )
            action = task_dir / "action-record.md"
            action.write_text(
                '''---
action_id: deploy-1
target: production-service
environment: production
payload_scope: release-42
subject: provider:release-42-revision-1
authority_ref: work/active/T-001-initial/authority.md
authorization_basis: direct-human-instruction
one_shot: true
idempotency_key: deploy-release-42
expires_at: 2099-01-01T00:00:00Z
timeout_seconds: 30
status: unknown
observation: timeout before acknowledgement
compensation: reconcile provider state before any retry
retry_allowed: true
---
# Action observation
The provider timed out, so the outcome remains unknown and no retry may occur before reconciliation.
''',
                encoding="utf-8",
            )
            append_yaml(
                task_dir / "task.yaml",
                action_refs=[f"work/active/{task_dir.name}/action-record.md"],
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("retry_allowed: false", checked.stdout)
            action.write_text(action.read_text(encoding="utf-8").replace("retry_allowed: true", "retry_allowed: false"), encoding="utf-8")
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_high_impact_expiry_payload_binding_and_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "action-invariants"
            project.mkdir()
            task_dir = write_v3_project(project, status="custom-action-state", risk="high")
            (task_dir / "authority.md").write_text(
                "The human owner authorized one bounded production action for this exact target and payload.\n",
                encoding="utf-8",
            )

            def record(name: str, payload: str, state: str, expiry: str, retry: bool = False) -> str:
                path = task_dir / name
                path.write_text(
                    f'''action_id: {name.removesuffix(".yaml")}
target: production-service
environment: production
payload_scope: {payload}
subject: provider:{payload}-revision-1
authority_ref: work/active/T-001-initial/authority.md
authorization_basis: direct-human-instruction
one_shot: true
idempotency_key: shared-key
expires_at: {expiry}
timeout_seconds: 30
status: {state}
observation: bounded provider observation
compensation: reconcile before another attempt
retry_allowed: {"true" if retry else "false"}
''',
                    encoding="utf-8",
                )
                return f"work/active/{task_dir.name}/{name}"

            expired = record("expired.yaml", "release-1", "authorized", "2020-01-01T00:00:00Z")
            append_yaml(task_dir / "task.yaml", action_refs=[expired])
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("expired authority", checked.stdout)

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "action-payload"
            project.mkdir()
            task_dir = write_v3_project(project, status="custom-action-state", risk="high")
            (task_dir / "authority.md").write_text(
                "The human owner authorized one bounded production action for this exact target and payload.\n",
                encoding="utf-8",
            )
            refs: list[str] = []
            for name, payload, state in (
                ("unknown.yaml", "release-1", "unknown"),
                ("retry.yaml", "release-2", "executing"),
            ):
                path = task_dir / name
                path.write_text(
                    f'''action_id: {name.removesuffix(".yaml")}
target: production-service
environment: production
payload_scope: {payload}
subject: provider:{payload}-revision-1
authority_ref: work/active/T-001-initial/authority.md
authorization_basis: direct-human-instruction
one_shot: true
idempotency_key: shared-key
expires_at: 2099-01-01T00:00:00Z
timeout_seconds: 30
status: {state}
observation: bounded provider observation
compensation: reconcile before another attempt
retry_allowed: false
''',
                    encoding="utf-8",
                )
                refs.append(f"work/active/{task_dir.name}/{name}")
            append_yaml(task_dir / "task.yaml", action_refs=refs)
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("reused with a different target, environment, payload scope, or subject", checked.stdout)
            self.assertIn("requires reconciliation before retry", checked.stdout)

    def test_parallel_overlap_is_a_hint_but_resolved_integration_requires_proof(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "parallel"
            project.mkdir()
            task_dir = write_v3_project(project, extras={"parallel_overlap_paths": ["src/app.py"]})
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            append_yaml(task_dir / "task.yaml", integration_status="resolved")
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("resolved integration requires merge_resolution_ref", checked.stdout)

    def test_unknown_extensions_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "extensions"
            project.mkdir()
            write_v3_project(
                project,
                status="custom-native-harness-stage",
                extras={"x_future_harness_graph": "native", "x_model_strategy": "frontier"},
            )
            checked = run_script(CHECK_SCRIPT, str(project), "--full")
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_nested_x_extension_uses_referenced_native_graph_without_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "nested-extension"
            project.mkdir()
            task_dir = write_v3_project(project)
            native = task_dir / "native-graph.json"
            native.write_text('{"nodes":[{"id":"build"}],"edges":[]}\n', encoding="utf-8")
            task = task_dir / "task.yaml"
            task.write_text(
                task.read_text(encoding="utf-8").replace(
                    "context_refs: []",
                    f"context_refs: [work/active/{task_dir.name}/native-graph.json]",
                )
                + "x_harness_graph:\n  nodes:\n    - build\n  topology: native\n",
                encoding="utf-8",
            )
            checked = run_script(CHECK_SCRIPT, str(project), "--full")
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_focus_does_not_enumerate_unselected_symlink_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "direct-focus"
            project.mkdir()
            write_v3_project(project)
            external = Path(tmp) / "external-task"
            external.mkdir()
            (external / "task.yaml").write_text("schema_version: 3\n", encoding="utf-8")
            (project / "work" / "active" / "T-002-unselected").symlink_to(
                external, target_is_directory=True
            )
            focused = run_script(CHECK_SCRIPT, str(project), "--focus")
            self.assertEqual(focused.returncode, 0, focused.stdout + focused.stderr)
            full = run_script(CHECK_SCRIPT, str(project), "--full")
            self.assertEqual(full.returncode, 1)
            self.assertIn("must not be a symlink", full.stdout)

    def test_v3_rejects_project_work_and_task_descendant_symlinks_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case in ("project", "work", "descendant"):
                project = root / case
                project.mkdir()
                task_dir = write_v3_project(project)
                external = root / f"{case}-external"
                external.mkdir()
                if case == "project":
                    moved = external / "project"
                    (project / "project").rename(moved)
                    (project / "project").symlink_to(moved, target_is_directory=True)
                elif case == "work":
                    moved = external / "work"
                    (project / "work").rename(moved)
                    (project / "work").symlink_to(moved, target_is_directory=True)
                else:
                    (external / "evidence.txt").write_text("external\n", encoding="utf-8")
                    (task_dir / "evidence-link.txt").symlink_to(external / "evidence.txt")
                checked = run_script(CHECK_SCRIPT, str(project), "--full")
                self.assertEqual(checked.returncode, 1, case)
                self.assertIn("symlink", checked.stdout.lower())
                self.assertNotIn("traceback", (checked.stdout + checked.stderr).lower())

    def test_current_handoff_and_review_require_bound_nonempty_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "current-claims"
            project.mkdir()
            task_dir = write_v3_project(
                project,
                extras={"handoff_current": True, "review_current": True},
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("handoff_current requires handoff_ref", checked.stdout)
            self.assertIn("requires review_ref", checked.stdout)

            subject = project / "result.bin"
            subject.write_bytes(b"exact implementation")
            digest = hashlib.sha256(subject.read_bytes()).hexdigest()
            handoff = task_dir / "handoff.md"
            review = task_dir / "review.md"
            write_claim(
                handoff,
                task_ref="work/active/T-999-wrong/task.yaml",
                subject=f"sha256:{digest}",
                subject_ref="result.bin",
            )
            write_claim(
                review,
                task_ref="work/active/T-999-wrong/task.yaml",
                subject=f"sha256:{digest}",
                subject_ref="result.bin",
                mode="fresh_context",
                actor_modified_subject=False,
                verdict="passed",
            )
            append_yaml(
                task_dir / "task.yaml",
                handoff_ref=f"work/active/{task_dir.name}/handoff.md",
                review_ref=f"work/active/{task_dir.name}/review.md",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("identify this exact task.yaml", checked.stdout)

    def test_external_and_directory_refs_are_not_portable_file_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "bad-refs"
            project.mkdir()
            task_dir = write_v3_project(project)
            (project / "evidence-dir").mkdir()
            task = task_dir / "task.yaml"
            task.write_text(
                task.read_text(encoding="utf-8").replace(
                    "context_refs: []",
                    "context_refs: [https://example.invalid/claim, evidence-dir]",
                ),
                encoding="utf-8",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("external URIs are not portable", checked.stdout)
            self.assertIn("must be a regular file", checked.stdout)

    def test_high_impact_completion_requires_action_records_or_explicit_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "high-impact-omission"
            project.mkdir()
            task_dir = write_v3_project(
                project,
                status="delivered-locally",
                risk="high",
                extras={
                    "completion_claim": True,
                    "effect_external": "message-or-publish",
                },
            )
            subject = project / "result.bin"
            subject.write_bytes(b"verified local result")
            digest = hashlib.sha256(subject.read_bytes()).hexdigest()
            review = task_dir / "review.md"
            write_claim(
                review,
                task_ref=f"work/active/{task_dir.name}/task.yaml",
                subject=f"sha256:{digest}",
                subject_ref="result.bin",
                mode="independent_actor",
                actor_modified_subject=False,
                verdict="passed",
            )
            acceptance = task_dir / "acceptance.md"
            acceptance.write_text(
                "The human owner accepts this exact completed high-impact boundary with no external effect performed.\n",
                encoding="utf-8",
            )
            append_yaml(
                task_dir / "task.yaml",
                review_ref=f"work/active/{task_dir.name}/review.md",
                completion_acceptance_ref=f"work/active/{task_dir.name}/acceptance.md",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("action_refs or explicit external_effects: none", checked.stdout)
            append_yaml(task_dir / "task.yaml", external_effects="none")
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_action_ambiguity_is_order_independent_and_reconciliation_is_substantive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "action-order"
            project.mkdir()
            task_dir = write_v3_project(project, status="external-action-active", risk="high")
            authority = task_dir / "authority.md"
            authority.write_text(
                "The human owner authorized one bounded production action for this exact target and payload.\n",
                encoding="utf-8",
            )

            def action(name: str, state: str, reconciliation: str | None = None) -> str:
                path = task_dir / name
                extra = f"reconciliation_ref: {reconciliation}\n" if reconciliation else ""
                path.write_text(
                    f'''action_id: {name.removesuffix(".yaml")}
target: production-service
environment: production
payload_scope: release-42
subject: provider:release-42-revision-1
authority_ref: work/active/T-001-initial/authority.md
authorization_basis: direct-human-instruction
one_shot: true
idempotency_key: deploy-release-42
expires_at: 2099-01-01T00:00:00Z
timeout_seconds: 30
status: {state}
observation: bounded provider observation
compensation: reconcile before another attempt
retry_allowed: false
{extra}''',
                    encoding="utf-8",
                )
                return f"work/active/{task_dir.name}/{name}"

            ambiguous = action("unknown.yaml", "unknown")
            live = action("live.yaml", "executing")
            append_yaml(task_dir / "task.yaml", action_refs=[live, ambiguous])
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("requires reconciliation before retry", checked.stdout)
            task = task_dir / "task.yaml"
            task.write_text(
                task.read_text(encoding="utf-8").replace(
                    f"action_refs: [{live}, {ambiguous}]",
                    f"action_refs: [{ambiguous}, {live}]",
                ),
                encoding="utf-8",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("requires reconciliation before retry", checked.stdout)
            reconciliation = task_dir / "reconciliation.md"
            reconciliation.write_text("Provider state was queried and the prior attempt was confirmed absent before retry.\n", encoding="utf-8")
            live_path = task_dir / "live.yaml"
            live_path.write_text(
                live_path.read_text(encoding="utf-8")
                + f"reconciliation_ref: work/active/{task_dir.name}/reconciliation.md\n"
                + "reconciliation_result: no-effect-confirmed\n",
                encoding="utf-8",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_compensated_action_still_requires_direct_normalized_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "compensated-authority"
            project.mkdir()
            task_dir = write_v3_project(project, status="compensated", risk="high")
            authority = task_dir / "authority.md"
            authority.write_text(
                "The human owner authorized this exact bounded compensation action.\n",
                encoding="utf-8",
            )
            reconciliation = task_dir / "compensation-evidence.md"
            reconciliation.write_text(
                "The provider receipt confirms the compensating operation completed and the prior effect was reversed.\n",
                encoding="utf-8",
            )
            action = task_dir / "action.yaml"
            action.write_text(
                '''action_id: compensation-1
target: production-service
environment: production
payload_scope: rollback-release-42
subject: provider:rollback-release-42-revision-1
authority_ref: work/active/T-001-initial/authority.md
authorization_basis: agent-relay
one_shot: true
idempotency_key: rollback-release-42
expires_at: 2099-01-01T00:00:00Z
timeout_seconds: 30
status: compensated
observation: compensation observed
compensation: completed
reconciliation_result: compensated-confirmed
reconciliation_ref: work/active/T-001-initial/compensation-evidence.md
retry_allowed: false
''',
                encoding="utf-8",
            )
            append_yaml(
                task_dir / "task.yaml",
                action_refs=[f"work/active/{task_dir.name}/action.yaml"],
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("cannot authorize an external effect", checked.stdout)
            action.write_text(
                action.read_text(encoding="utf-8").replace(
                    "authorization_basis: agent-relay",
                    "authorization_basis: direct-human-instruction",
                ),
                encoding="utf-8",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_resolved_parallel_integration_requires_stable_subject_and_substantive_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "merge-proof"
            project.mkdir()
            task_dir = write_v3_project(project)
            merged = project / "merged.bin"
            merged.write_bytes(b"integrated implementation")
            (project / "src").mkdir()
            (project / "src" / "app.py").write_text("print('integrated')\n", encoding="utf-8")
            resolution = task_dir / "merge-resolution.md"
            resolution.write_text("  \n", encoding="utf-8")
            head = init_git(project)
            append_yaml(
                task_dir / "task.yaml",
                integration_status="merged",
                parallel_overlap_paths=["src/app.py"],
                merge_resolution_ref=f"work/active/{task_dir.name}/merge-resolution.md",
                merge_resolution_subject=f"git:{head}",
                merge_resolution_subject_paths=["merged.bin"],
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("claim artifact must not be empty", checked.stdout)
            resolution.write_text(
                "The two harness branches were integrated and conflicts were resolved against the exact merged subject.\n",
                encoding="utf-8",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("must cover every parallel_overlap_path", checked.stdout)
            task = task_dir / "task.yaml"
            task.write_text(
                task.read_text(encoding="utf-8").replace(
                    "merge_resolution_subject_paths: [merged.bin]",
                    "merge_resolution_subject_paths: [merged.bin, src/app.py]",
                ),
                encoding="utf-8",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_visual_conformance_rejects_arbitrary_and_plural_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "visual-shape"
            project.mkdir()
            task_dir = write_v3_project(project)
            baseline = task_dir / "baseline.txt"
            render = task_dir / "render.txt"
            baseline.write_text("not actual visual media\n", encoding="utf-8")
            render.write_text("not actual visual media\n", encoding="utf-8")
            decision = task_dir / "decision.md"
            decision.write_text("The human owner approved the exact visual baseline for this bounded comparison.\n", encoding="utf-8")
            append_yaml(
                task_dir / "task.yaml",
                conformance_status="matched",
                approved_baseline_ref=f"work/active/{task_dir.name}/baseline.txt",
                approved_baseline_refs=[f"work/active/{task_dir.name}/baseline.txt"],
                approved_baseline_subject=f"sha256:{hashlib.sha256(baseline.read_bytes()).hexdigest()}",
                implementation_render_ref=f"work/active/{task_dir.name}/render.txt",
                implementation_render_subject=f"sha256:{hashlib.sha256(render.read_bytes()).hexdigest()}",
                baseline_decision_ref=f"work/active/{task_dir.name}/decision.md",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("approved_baseline_refs is ambiguous", checked.stdout)
            self.assertIn("supported image, SVG, PDF, video", checked.stdout)

    def test_high_impact_review_covers_exact_actions_and_local_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "review-action-scope"
            project.mkdir()
            task_dir = write_v3_project(project, status="done", risk="high")
            payload = project / "payload.bin"
            payload.write_bytes(b"exact production payload")
            authority = task_dir / "authority.md"
            authority.write_text(
                "The human owner authorized this one exact production effect and payload.\n",
                encoding="utf-8",
            )
            action = task_dir / "action.yaml"
            action.write_text(
                f'''action_id: deploy-42
target: production-service
environment: production
payload_scope: release-42
subject: provider:release-42-revision-9
subject_paths: [payload.bin]
authority_ref: work/active/{task_dir.name}/authority.md
authorization_basis: direct-human-instruction
one_shot: true
idempotency_key: deploy-release-42
expires_at: 2099-01-01T00:00:00Z
timeout_seconds: 30
status: succeeded
observation: provider receipt confirms the exact effect
compensation: bounded rollback remains available if independently authorized
retry_allowed: false
''',
                encoding="utf-8",
            )
            head = init_git(project)
            action_ref = f"work/active/{task_dir.name}/action.yaml"
            review = task_dir / "review.md"
            write_claim(
                review,
                task_ref=f"work/active/{task_dir.name}/task.yaml",
                subject=f"git:{head}",
                subject_paths=["payload.bin"],
                mode="independent_actor",
                actor_modified_subject=False,
                verdict="passed",
                action_refs=[],
            )
            acceptance = task_dir / "acceptance.md"
            acceptance.write_text(
                "The human owner accepts this exact high-impact completion and recorded external result.\n",
                encoding="utf-8",
            )
            append_yaml(
                task_dir / "task.yaml",
                action_refs=[action_ref],
                review_ref=f"work/active/{task_dir.name}/review.md",
                completion_acceptance_ref=f"work/active/{task_dir.name}/acceptance.md",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("action_refs must exactly cover", checked.stdout)
            review.write_text(
                review.read_text(encoding="utf-8").replace("action_refs: []", f"action_refs: [{action_ref}]"),
                encoding="utf-8",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("omit action scope", checked.stdout)
            review.write_text(
                review.read_text(encoding="utf-8").replace(
                    "subject_paths: [payload.bin]",
                    f"subject_paths: [payload.bin, {action_ref}]",
                ),
                encoding="utf-8",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_action_ids_are_unique_and_obsolete_statuses_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "action-identity"
            project.mkdir()
            task_dir = write_v3_project(project, risk="high")

            def planned(name: str, status: str) -> str:
                path = task_dir / name
                path.write_text(
                    f'''action_id: duplicate-action
target: production-service
environment: production
payload_scope: release-42
subject: provider:release-42-revision-9
authorization_basis: direct-human-instruction
authority_ref:
one_shot: true
idempotency_key: {name}
expires_at: 2099-01-01T00:00:00Z
timeout_seconds: 30
status: {status}
observation: not attempted
compensation: stop before effect
retry_allowed: false
''',
                    encoding="utf-8",
                )
                return f"work/active/{task_dir.name}/{name}"

            first = planned("first.yaml", "planned")
            second = planned("second.yaml", "planned")
            append_yaml(task_dir / "task.yaml", action_refs=[first, second])
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("action_id 'duplicate-action' is duplicated", checked.stdout)
            (task_dir / "second.yaml").write_text(
                (task_dir / "second.yaml").read_text(encoding="utf-8")
                .replace("action_id: duplicate-action", "action_id: second-action")
                .replace("status: planned", "status: ambiguous"),
                encoding="utf-8",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("invalid action status 'ambiguous'", checked.stdout)

    def test_goal_or_scope_high_impact_language_sets_risk_floor_but_negation_does_not(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "prose-risk"
            project.mkdir()
            task_dir = write_v3_project(project)
            task = task_dir / "task.yaml"
            task.write_text(
                task.read_text(encoding="utf-8").replace(
                    "goal: Deliver one bounded result",
                    "goal: Deploy this release to production",
                ),
                encoding="utf-8",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("activated high-impact floor", checked.stdout)
            task.write_text(
                task.read_text(encoding="utf-8").replace(
                    "goal: Deploy this release to production",
                    "goal: Do not deploy this mock release to production",
                ),
                encoding="utf-8",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_provider_visual_subjects_are_adaptive_but_revision_and_node_bound(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "provider-visual"
            project.mkdir()
            task_dir = write_v3_project(project)
            baseline_subject = "provider:figma:file-abc123:node-home:revision-9"
            render_subject = "provider:simulator:file-capture42:screen-home:revision-9"
            decision = task_dir / "decision.md"
            review = task_dir / "review.md"
            decision.write_text("The human owner approved this exact provider-bound visual baseline for comparison.\n", encoding="utf-8")
            write_claim(
                review,
                task_ref=f"work/active/{task_dir.name}/task.yaml",
                subject=render_subject,
                mode="fresh_context",
                actor_modified_subject=False,
                verdict="passed",
                baseline_subject=baseline_subject,
                implementation_render_subject=render_subject,
            )
            append_yaml(
                task_dir / "task.yaml",
                conformance_status="matched",
                approved_baseline_subject=baseline_subject,
                implementation_render_subject=render_subject,
                baseline_decision_ref=f"work/active/{task_dir.name}/decision.md",
                review_ref=f"work/active/{task_dir.name}/review.md",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            task = task_dir / "task.yaml"
            task.write_text(
                task.read_text(encoding="utf-8").replace(
                    baseline_subject,
                    "provider:figma:file-latest:node-home:revision-latest",
                ),
                encoding="utf-8",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("provider visual subject requires", checked.stdout)

    def test_sha_visual_subjects_require_corresponding_local_media_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "sha-visual-without-refs"
            project.mkdir()
            task_dir = write_v3_project(project)
            baseline_subject = "sha256:" + "1" * 64
            render_subject = "sha256:" + "2" * 64
            decision = task_dir / "decision.md"
            review = task_dir / "review.md"
            decision.write_text(
                "The human owner approved the exact local visual baseline represented by this subject.\n",
                encoding="utf-8",
            )
            write_claim(
                review,
                task_ref=f"work/active/{task_dir.name}/task.yaml",
                subject="provider:review:file-event42:screen-home:revision-9",
                mode="fresh_context",
                actor_modified_subject=False,
                verdict="passed",
                baseline_subject=baseline_subject,
                implementation_render_subject=render_subject,
            )
            append_yaml(
                task_dir / "task.yaml",
                conformance_status="matched",
                approved_baseline_subject=baseline_subject,
                implementation_render_subject=render_subject,
                baseline_decision_ref=f"work/active/{task_dir.name}/decision.md",
                review_ref=f"work/active/{task_dir.name}/review.md",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("sha256/local approved baseline subject requires approved_baseline_ref", checked.stdout)
            self.assertIn("sha256/local implementation render subject requires implementation_render_ref", checked.stdout)

    def test_html_needs_visual_structure_and_cannot_be_runtime_render(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "html-visual-shape"
            project.mkdir()
            task_dir = write_v3_project(project)
            baseline = task_dir / "baseline.html"
            render = task_dir / "render.html"
            decision = task_dir / "decision.md"
            review = task_dir / "review.md"
            baseline.write_text(substantive_html("Baseline").replace(" data-visual-surface", ""), encoding="utf-8")
            render.write_text(substantive_html("Runtime-looking HTML"), encoding="utf-8")
            decision.write_text("The owner approved this exact baseline candidate only after visual inspection.\n", encoding="utf-8")
            baseline_subject = f"sha256:{hashlib.sha256(baseline.read_bytes()).hexdigest()}"
            render_subject = f"sha256:{hashlib.sha256(render.read_bytes()).hexdigest()}"
            write_claim(
                review,
                task_ref=f"work/active/{task_dir.name}/task.yaml",
                subject=render_subject,
                subject_ref=f"work/active/{task_dir.name}/render.html",
                mode="fresh_context",
                actor_modified_subject=False,
                verdict="passed",
                baseline_subject=baseline_subject,
                implementation_render_subject=render_subject,
            )
            append_yaml(
                task_dir / "task.yaml",
                conformance_status="matched",
                approved_baseline_ref=f"work/active/{task_dir.name}/baseline.html",
                approved_baseline_subject=baseline_subject,
                implementation_render_ref=f"work/active/{task_dir.name}/render.html",
                implementation_render_subject=render_subject,
                baseline_decision_ref=f"work/active/{task_dir.name}/decision.md",
                review_ref=f"work/active/{task_dir.name}/review.md",
            )
            checked = run_script(CHECK_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 1)
            self.assertIn("HTML baseline needs", checked.stdout)
            self.assertIn("not a real implementation render", checked.stdout)

    def test_v3_project_can_keep_legacy_tasks_without_rewriting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "mixed"
            project.mkdir()
            write_v3_project(project)
            v1 = make_task(
                project,
                task_id="T-M01-101-v1",
                location="archive",
                status="cancelled",
                schema_version=1,
            )
            v21 = make_task(
                project,
                task_id="T-M01-102-v21",
                location="archive",
                status="cancelled",
                protocol_version="2.1",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment(v21)
            v22 = make_task(
                project,
                task_id="T-M01-103-v22",
                location="archive",
                status="cancelled",
                protocol_version="2.2",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment_v22(v22)
            active_v22 = make_task(
                project,
                task_id="T-M01-104-active-v22",
                status="proposed",
                protocol_version="2.2",
                risk_level="low",
                alignment_ref="alignment/alignment.yaml",
            )
            write_alignment_v22(active_v22)
            watched = [v1 / "task.yaml", v21 / "task.yaml", v22 / "task.yaml", active_v22 / "task.yaml"]
            before = {path: path.read_bytes() for path in watched}
            checked = run_script(CHECK_SCRIPT, str(project), "--full")
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertEqual(before, {path: path.read_bytes() for path in watched})

    def test_initializer_default_is_three_files_dry_run_reentrant_and_optional(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dry = root / "dry"
            checked = run_script(INIT_SCRIPT, str(dry), "--dry-run")
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertFalse(dry.exists())

            project = root / "live"
            initialized = run_script(INIT_SCRIPT, str(project))
            self.assertEqual(initialized.returncode, 0, initialized.stdout + initialized.stderr)
            files = sorted(path.relative_to(project).as_posix() for path in project.rglob("*") if path.is_file())
            self.assertEqual(
                files,
                ["AGENTS.md", "project/state.yaml", "work/active/T-001-initial/task.yaml"],
            )
            before = {path: path.read_bytes() for path in project.rglob("*") if path.is_file()}
            again = run_script(INIT_SCRIPT, str(project))
            self.assertEqual(again.returncode, 0)
            self.assertEqual(before, {path: path.read_bytes() for path in before})
            refused = run_script(INIT_SCRIPT, str(project), "--force")
            self.assertEqual(refused.returncode, 2)
            self.assertIn("never overwrites", refused.stderr)
            self.assertEqual(before, {path: path.read_bytes() for path in before})

            optional = root / "optional"
            result = run_script(
                INIT_SCRIPT,
                str(optional),
                "--adapter", "claude",
                "--adapter", "codex",
                "--with-milestones",
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((optional / "CLAUDE.md").is_file())
            self.assertTrue((optional / "CODEX.md").is_file())
            self.assertTrue((optional / "milestones" / "M01" / "milestone.yaml").is_file())

    def test_initializer_preflights_incompatible_authority_before_any_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "incompatible-state"
            (project / "project").mkdir(parents=True)
            state = project / "project" / "state.yaml"
            state.write_text("schema_version: 2\ngovernance_protocol_version: 2.2\n", encoding="utf-8")
            before = state.read_bytes()
            checked = run_script(INIT_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 2)
            self.assertIn("incompatible with protocol 3.0", checked.stderr)
            self.assertEqual(before, state.read_bytes())
            self.assertFalse((project / "AGENTS.md").exists())
            self.assertFalse((project / "work").exists())

            task_project = root / "placeholder-task"
            task_dir = task_project / "work" / "active" / "T-001-initial"
            task_dir.mkdir(parents=True)
            task = task_dir / "task.yaml"
            task.write_text(
                '''schema_version: 3
protocol_version: "3.0"
id: T-001-initial
status: implementing
goal: Replace with bounded goal
scope: [src]
non_goals: [external effects]
acceptance: [observable result]
risk: low
risk_reasons: [local-reversible]
protected_paths: []
context_refs: []
decision_refs: []
evidence_refs: []
updated: 2026-08-19
''',
                encoding="utf-8",
            )
            before = task.read_bytes()
            checked = run_script(INIT_SCRIPT, str(task_project))
            self.assertEqual(checked.returncode, 2)
            self.assertIn("placeholder task may only remain proposed", checked.stderr)
            self.assertEqual(before, task.read_bytes())
            self.assertFalse((task_project / "AGENTS.md").exists())

            focus_project = root / "conflicting-focus"
            (focus_project / "project").mkdir(parents=True)
            focus_state = focus_project / "project" / "state.yaml"
            focus_state.write_text(
                '''schema_version: 3
protocol_version: "3.0"
project_id: TEST
project_name: Test
status: active
active_task: T-999-other
updated: 2026-08-19
''',
                encoding="utf-8",
            )
            before = focus_state.read_bytes()
            checked = run_script(INIT_SCRIPT, str(focus_project))
            self.assertEqual(checked.returncode, 2)
            self.assertIn("conflicts with initialization task", checked.stderr)
            self.assertEqual(before, focus_state.read_bytes())
            self.assertFalse((focus_project / "AGENTS.md").exists())

    def test_initializer_requires_exact_agents_contract_and_respects_planned_output_protection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conflict = root / "agents-conflict"
            conflict.mkdir()
            agents = conflict / "AGENTS.md"
            agents.write_text("# Owner contract\nKeep this repository-specific policy.\n", encoding="utf-8")
            before = agents.read_bytes()
            checked = run_script(INIT_SCRIPT, str(conflict))
            self.assertEqual(checked.returncode, 2)
            self.assertIn("manual merge is required", checked.stderr)
            self.assertEqual(agents.read_bytes(), before)
            self.assertFalse((conflict / "project").exists())
            self.assertFalse((conflict / "work").exists())

            protected = root / "protected-output"
            initialized = run_script(INIT_SCRIPT, str(protected))
            self.assertEqual(initialized.returncode, 0, initialized.stdout + initialized.stderr)
            task = protected / "work" / "active" / "T-001-initial" / "task.yaml"
            task.write_text(
                task.read_text(encoding="utf-8").replace(
                    "protected_paths: []", "protected_paths: [CODEX.md]"
                ),
                encoding="utf-8",
            )
            before_files = {
                path: path.read_bytes()
                for path in protected.rglob("*")
                if path.is_file()
            }
            checked = run_script(INIT_SCRIPT, str(protected), "--adapter", "codex")
            self.assertEqual(checked.returncode, 2)
            self.assertIn("planned initialization output is protected", checked.stderr)
            self.assertFalse((protected / "CODEX.md").exists())
            self.assertEqual(before_files, {path: path.read_bytes() for path in before_files})

    def test_initializer_rejects_non_directory_ancestors_and_path_traversal_before_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blocked = root / "blocked"
            blocked.mkdir()
            (blocked / "project").write_text("owner file\n", encoding="utf-8")
            checked = run_script(INIT_SCRIPT, str(blocked))
            self.assertEqual(checked.returncode, 2)
            self.assertIn("ancestor is not a directory", checked.stderr)
            self.assertFalse((blocked / "AGENTS.md").exists())
            self.assertNotIn("traceback", (checked.stdout + checked.stderr).lower())

            traversing = root / "container" / ".." / "escaped"
            checked = run_script(INIT_SCRIPT, str(traversing))
            self.assertEqual(checked.returncode, 2)
            self.assertIn("must not contain '..'", checked.stderr)
            self.assertFalse((root / "escaped").exists())

    def test_initializer_preflight_ignores_nested_x_payload_but_rejects_nested_core(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "native-extension"
            project.mkdir()
            task_dir = write_v3_project(project)
            task = task_dir / "task.yaml"
            task.write_text(
                task.read_text(encoding="utf-8")
                + "x_native_graph:\n  node: <native-provider-node>\n",
                encoding="utf-8",
            )
            (project / "AGENTS.md").write_bytes(
                (INIT_SCRIPT.parent.parent / "assets" / "project-template" / "AGENTS.md").read_bytes()
            )
            checked = run_script(INIT_SCRIPT, str(project))
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

            malformed = root / "nested-core"
            task_dir = malformed / "work" / "active" / "T-001-initial"
            task_dir.mkdir(parents=True)
            (task_dir / "task.yaml").write_text(
                '''schema_version: 3
protocol_version: "3.0"
id: T-001-initial
status: proposed
goal:
  value: nested-core-is-not-portable
scope: [src]
non_goals: [none]
acceptance: [observable]
risk: low
risk_reasons: [local-reversible]
protected_paths: []
context_refs: []
decision_refs: []
evidence_refs: []
updated: 2026-08-19
''',
                encoding="utf-8",
            )
            checked = run_script(INIT_SCRIPT, str(malformed))
            self.assertEqual(checked.returncode, 2)
            self.assertIn("unsupported nested core YAML", checked.stderr)
            self.assertFalse((malformed / "AGENTS.md").exists())

    def test_migration_mode_is_read_only_and_modes_are_exclusive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "migration"
            project.mkdir()
            write_v3_project(project)
            before = {path: path.read_bytes() for path in project.rglob("*") if path.is_file()}
            checked = run_script(CHECK_SCRIPT, str(project), "--migration")
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertEqual(before, {path: path.read_bytes() for path in before})
            rejected = run_script(CHECK_SCRIPT, str(project), "--migration", "--full")
            self.assertEqual(rejected.returncode, 2)

    def test_real_parallel_worktree_remains_native_git_coordination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "primary"
            project.mkdir()
            write_v3_project(project)
            init_git(project)
            branch = root / "parallel-worktree"
            added = git(project, "worktree", "add", "-qb", "parallel-fixture", str(branch))
            self.assertEqual(added.returncode, 0, added.stderr)
            for checkout in (project, branch):
                checked = run_script(CHECK_SCRIPT, str(checkout))
                self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)


if __name__ == "__main__":
    unittest.main()
