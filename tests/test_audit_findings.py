"""Regression tests for the 2026-10-20 audit of v3.0.2.

Each class covers one audit finding (P1-01 ... P3-01) or a group of them. Every
test except those named ``test_guard_*`` fails on v3.0.2 and describes the
target behavior; ``test_guard_*`` tests pin behavior that already worked.

Run from the repository root:

    python3 -m unittest tests.test_audit_findings -v
"""

from __future__ import annotations

import contextlib
import errno
import hashlib
import importlib
import io
import os
import re
import shlex
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

TESTS_ROOT = Path(__file__).resolve().parent
if str(TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTS_ROOT))

from test_reference_and_archive import ArchiveCase, project_memory, tree_snapshot  # noqa: E402
from test_review_findings import (  # noqa: E402
    ACTIVE_TASK,
    ARCHIVED_TASK,
    HAS_GIT,
    INIT_SCRIPT,
    SKILL_ROOT,
    TASK_ID,
    ProjectCase,
    output,
    render_task,
    review_record,
    run_script,
)

OTHER_ID = "T-002-next"
OTHER_TASK = f"work/active/{OTHER_ID}"


def load_memory_tools():
    scripts = str(SKILL_ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    sys.dont_write_bytecode = True
    return importlib.import_module("memory_tools")


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_review(task: str, artifact: str, digest: str) -> str:
    return (
        "---\n"
        f'task_ref: "{task}/task.yaml"\n'
        f'subject: "sha256:{digest}"\n'
        f'subject_ref: "{artifact}"\n'
        'mode: "fresh_context"\n'
        "actor_modified_subject: false\n"
        'verdict: "passed"\n'
        "---\n"
        "- Evidence inspected: the exact artifact bytes named by the subject.\n"
        "- Findings: none; the artifact matches the agreed content.\n"
    )


class AuditArchiveCase(ArchiveCase):
    def add_other_task(self, **overrides: str) -> Path:
        other = self.project / OTHER_TASK
        other.mkdir(parents=True)
        (other / "task.yaml").write_text(render_task(id=OTHER_ID, **overrides), encoding="utf-8")
        return other

    def set_focus(self, task_id: str) -> None:
        state = self.project / "project" / "state.yaml"
        state.write_text(
            re.sub(r"^active_task:.*$", f"active_task: {task_id}", state.read_text(encoding="utf-8"), flags=re.M),
            encoding="utf-8",
        )

    def assertRefusedUnchanged(self, fragment: str) -> subprocess.CompletedProcess[str]:
        before = tree_snapshot(self.project)
        result = self.archive(TASK_ID)
        self.assertEqual(result.returncode, 2, output(result))
        self.assertIn(fragment, output(result))
        self.assertIn("nothing changed", output(result))
        self.assertEqual(tree_snapshot(self.project), before)
        return result


# ---------------------------------------------------------------------------
# P1-01: archive honors protected_paths and never edits source-unknown files
# ---------------------------------------------------------------------------


class ArchiveProtectionTest(AuditArchiveCase):
    def test_refuses_to_rewrite_a_protected_record(self) -> None:
        self.write_task(render_task(status="done", protected_paths="[project/state.yaml]"))
        self.assertRefusedUnchanged("protected_paths: project/state.yaml")

    def test_refuses_to_move_a_folder_another_task_protects(self) -> None:
        self.finished_task_with_records()
        self.add_other_task(protected_paths=f"[{ACTIVE_TASK}/decisions.md]")
        self.assertRefusedUnchanged("archive would move")

    def test_refuses_when_a_protection_covers_the_whole_work_tree(self) -> None:
        self.finished_task_with_records()
        self.add_other_task(protected_paths="[work/]")
        self.assertRefusedUnchanged("protected_paths: work/")

    def test_protected_prose_that_mentions_the_task_keeps_its_bytes(self) -> None:
        note = self.project / "project" / "private.md"
        note.write_text(f"Human-owned note about {ACTIVE_TASK}/task.yaml\n", encoding="utf-8")
        self.write_task(render_task(status="done", protected_paths="[project/private.md]"))
        original = note.read_bytes()
        result = self.archive(TASK_ID)
        self.assertEqual(result.returncode, 0, output(result))
        self.assertEqual(note.read_bytes(), original)
        self.assertIn("WARNING project/private.md mentions", result.stdout)
        self.assertNotIn("REWRITE project/private.md", result.stdout)
        self.assertPasses(self.check("--full"))


@unittest.skipUnless(HAS_GIT, "git is required")
class ArchiveGitOwnershipTest(AuditArchiveCase):
    def setUp(self) -> None:
        super().setUp()
        self.git_init()

    def test_ignored_untracked_file_is_never_rewritten(self) -> None:
        note = self.project / "project" / "private.md"
        note.write_text(f"Untracked note about {ACTIVE_TASK}/task.yaml\n", encoding="utf-8")
        (self.project / ".gitignore").write_text("project/private.md\n", encoding="utf-8")
        self.write_task(render_task(status="done"))
        self.commit("base")
        original = note.read_bytes()
        result = self.archive(TASK_ID)
        self.assertEqual(result.returncode, 0, output(result))
        self.assertEqual(note.read_bytes(), original)

    def test_refuses_to_rewrite_an_ignored_record(self) -> None:
        self.finished_task_with_records()
        (self.project / ".gitignore").write_text(f"{ACTIVE_TASK}/handoff.md\n", encoding="utf-8")
        self.commit("base")
        self.assertTrue(self.git("status", "--porcelain") == "", "the ignored record hides from git status")
        self.assertRefusedUnchanged("not tracked by git")

    def test_printed_staging_command_stages_only_the_archive(self) -> None:
        self.finished_task_with_records()
        other = self.project / "project" / "other-person.txt"
        other.write_text("version 1\n", encoding="utf-8")
        self.commit("base")
        other.write_text("someone else's uncommitted edit\n", encoding="utf-8")
        result = self.archive(TASK_ID)
        self.assertEqual(result.returncode, 0, output(result))
        command = next(line.strip() for line in result.stdout.splitlines() if line.strip().startswith("git -C"))
        subprocess.run(shlex.split(command), check=True, capture_output=True)
        staged = set(self.git("diff", "--cached", "--no-renames", "--name-only").splitlines())
        self.assertNotIn("project/other-person.txt", staged)
        self.assertIn("project/state.yaml", staged)
        self.assertIn(f"{ARCHIVED_TASK}/task.yaml", staged)
        self.assertIn(f"{ACTIVE_TASK}/task.yaml", staged)  # the deletion
        self.git("commit", "-qm", "archive")
        self.assertEqual(self.git("status", "--porcelain"), "M project/other-person.txt")
        self.assertPasses(self.check("--full"))

    def test_readme_no_longer_stages_whole_folders(self) -> None:
        readme = (SKILL_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("add work project", readme)


# ---------------------------------------------------------------------------
# P1-02: archive keeps bound artifacts byte-identical and refuses to break claims
# ---------------------------------------------------------------------------


@unittest.skipUnless(HAS_GIT, "git is required")
class ArchiveClaimTest(AuditArchiveCase):
    def setUp(self) -> None:
        super().setUp()
        self.git_init()

    def test_archived_tasks_sha256_artifact_keeps_its_bytes(self) -> None:
        artifact = self.task_dir / "deliverable.md"
        artifact.write_text(f"Approved artifact that links to {ACTIVE_TASK}/task.yaml\n", encoding="utf-8")
        original = artifact.read_bytes()
        (self.task_dir / "review.md").write_text(
            sha256_review(ACTIVE_TASK, f"{ACTIVE_TASK}/deliverable.md", sha256_of(artifact)), encoding="utf-8"
        )
        self.write_task(render_task(status="done", review_ref=f"{ACTIVE_TASK}/review.md", review_current="true"))
        self.commit("reviewed artifact")
        self.assertPasses(self.check("--full"))
        result = self.archive(TASK_ID)
        self.assertEqual(result.returncode, 0, output(result))
        self.assertEqual((self.project / ARCHIVED_TASK / "deliverable.md").read_bytes(), original)
        self.assertIn(f"{ARCHIVED_TASK}/deliverable.md", (self.project / ARCHIVED_TASK / "review.md").read_text())
        self.assertPasses(self.check("--full"))

    def test_other_active_tasks_artifact_keeps_its_bytes(self) -> None:
        self.write_task(render_task(status="done"))
        other = self.add_other_task(review_ref=f"{OTHER_TASK}/review.md", review_current="true")
        artifact = other / "approved.md"
        artifact.write_text(f"Approved artifact that links to {ACTIVE_TASK}/task.yaml\n", encoding="utf-8")
        original = artifact.read_bytes()
        (other / "review.md").write_text(
            sha256_review(OTHER_TASK, f"{OTHER_TASK}/approved.md", sha256_of(artifact)), encoding="utf-8"
        )
        self.commit("reviewed artifact")
        self.assertPasses(self.check("--full"))
        result = self.archive(TASK_ID)
        self.assertEqual(result.returncode, 0, output(result))
        self.assertEqual(artifact.read_bytes(), original)
        self.assertPasses(self.check("--full"))

    def test_refuses_when_another_tasks_git_claim_binds_moved_files(self) -> None:
        self.finished_task_with_records()
        sha = self.commit("decisions")
        other = self.add_other_task(review_ref=f"{OTHER_TASK}/review.md", review_current="true")
        (other / "review.md").write_text(
            review_record(sha=sha, subject_paths=[f"{ACTIVE_TASK}/decisions.md"], mode="fresh_context", action_refs=[])
            .replace(f"{ACTIVE_TASK}/task.yaml", f"{OTHER_TASK}/task.yaml"),
            encoding="utf-8",
        )
        self.commit("review of T1's decisions")
        self.assertPasses(self.check("--full"))
        self.assertRefusedUnchanged("archiving would invalidate")

    def test_refuses_when_a_sha256_bound_record_would_be_rewritten(self) -> None:
        self.finished_task_with_records()
        other = self.add_other_task(
            context_refs=f"[{ACTIVE_TASK}/decisions.md]",
            review_ref=f"{OTHER_TASK}/review.md",
            review_current="true",
        )
        (other / "review.md").write_text(
            sha256_review(OTHER_TASK, f"{OTHER_TASK}/task.yaml", sha256_of(other / "task.yaml")), encoding="utf-8"
        )
        self.commit("review binds T2's task.yaml bytes")
        self.assertPasses(self.check("--full"))
        self.assertRefusedUnchanged("would rewrite")

    def test_guard_high_impact_task_archives_with_its_action_records(self) -> None:
        payload = self.project / "deploy.txt"
        payload.write_text("replicas: 3\n", encoding="utf-8")
        (self.task_dir / "authority.md").write_text(
            "Direct human instruction: deploy this exact payload to prod-1 once.\n", encoding="utf-8"
        )
        (self.task_dir / "acceptance.md").write_text(
            "The human accepted completion after reviewing the observed rollout.\n", encoding="utf-8"
        )
        action_ref = f"{ACTIVE_TASK}/action.md"
        (self.project / action_ref).write_text(
            "---\n"
            'action_id: "A-001"\ntarget: "prod-1"\nenvironment: "production"\npayload_scope: "deploy.txt"\n'
            f'subject: "sha256:{sha256_of(payload)}"\nsubject_ref: "deploy.txt"\n'
            f'authorization_basis: "direct-human-instruction"\nauthority_ref: "{ACTIVE_TASK}/authority.md"\n'
            'one_shot: true\nidempotency_key: "deploy-001"\nexpires_at: "2099-01-01T00:00:00Z"\n'
            'timeout_seconds: 600\nstatus: succeeded\nobservation: "3/3 replicas healthy"\n'
            'compensation: "roll back to the previous image"\nretry_allowed: false\n'
            "---\nReceipt r-1.\n",
            encoding="utf-8",
        )
        self.write_task(
            render_task(
                status="done",
                risk="high",
                risk_reasons="[publication-or-deployment]",
                action_refs=f"[{action_ref}]",
                completion_acceptance_ref=f"{ACTIVE_TASK}/acceptance.md",
                review_ref=f"{ACTIVE_TASK}/review.md",
                review_current="true",
            )
        )
        sha = self.commit("deploy")
        (self.task_dir / "review.md").write_text(
            review_record(sha=sha, subject_paths=["deploy.txt", action_ref], mode="independent_actor", action_refs=[action_ref]),
            encoding="utf-8",
        )
        self.commit("independent review")
        self.assertPasses(self.check("--full"))
        result = self.archive(TASK_ID)
        self.assertEqual(result.returncode, 0, output(result))
        self.assertIn(f"REWRITE {ARCHIVED_TASK}/action.md", result.stdout)
        self.assertPasses(self.check("--full"))


# ---------------------------------------------------------------------------
# P2-01 B, P2-02, P2-03: state syntax, archived references, versions
# ---------------------------------------------------------------------------


class ArchivePlanningTest(AuditArchiveCase):
    def test_clears_a_focus_written_with_a_space_before_the_colon(self) -> None:
        state = self.project / "project" / "state.yaml"
        state.write_text(state.read_text(encoding="utf-8").replace("active_task:", "active_task :"), encoding="utf-8")
        self.write_task(render_task(status="done"))
        result = self.archive(TASK_ID)
        self.assertEqual(result.returncode, 0, output(result))
        self.assertIn("active_task: null", state.read_text(encoding="utf-8"))
        self.assertPasses(self.check())
        self.assertPasses(self.check("--full"))

    def test_refuses_to_break_a_reference_from_archived_history(self) -> None:
        other = self.add_other_task()
        (other / "notes.md").write_text("Durable note the first task depends on.\n", encoding="utf-8")
        self.write_task(render_task(status="done", context_refs=f"[{OTHER_TASK}/notes.md]"))
        self.set_focus(OTHER_ID)
        first = self.archive(TASK_ID)
        self.assertEqual(first.returncode, 0, output(first))
        self.assertPasses(self.check("--full"))
        before = tree_snapshot(self.project)
        second = self.archive(OTHER_ID)
        self.assertEqual(second.returncode, 2, output(second))
        self.assertIn(f"{ARCHIVED_TASK}/task.yaml:context_refs[0]", output(second))
        self.assertEqual(tree_snapshot(self.project), before)
        self.assertPasses(self.check("--full"))

    def test_refuses_another_active_task_with_an_unsupported_version(self) -> None:
        self.write_task(render_task(status="done"))
        self.add_other_task(schema_version="2", protocol_version='"2.0"', context_refs=f"[{ACTIVE_TASK}/task.yaml]")
        self.assertRefusedUnchanged("archive edits no other version")

    def test_refuses_a_source_task_with_an_unsupported_version(self) -> None:
        self.write_task(render_task(status="done", schema_version="2", protocol_version='"2.0"'))
        self.assertRefusedUnchanged("archive edits no other version")

    def test_refuses_an_unsupported_state(self) -> None:
        state = self.project / "project" / "state.yaml"
        state.write_text(
            state.read_text(encoding="utf-8").replace('protocol_version: "3.0"', 'protocol_version: "2.0"'),
            encoding="utf-8",
        )
        self.assertRefusedUnchanged("project/state.yaml is not schema_version: 3")


# ---------------------------------------------------------------------------
# PR #13 review (review-pr-13.md), scenarios A-C: archive must not leave a passing
# check --full failing, and its planning must read paths as the checker does
# ---------------------------------------------------------------------------


class ArchiveReviewScenarioTest(AuditArchiveCase):
    def test_a_refuses_to_create_the_archive_folder_under_a_protection(self) -> None:
        self.write_task(render_task(status="done"))
        self.add_other_task(protected_paths="[work/archive/]")
        self.assertPasses(self.check("--full"))
        self.assertRefusedUnchanged(f"archive would create {ARCHIVED_TASK}")

    def test_b_refuses_to_rewrite_a_file_an_archived_sha256_claim_binds(self) -> None:
        self.write_task(render_task(status="done"))
        other = self.add_other_task(review_ref=f"{OTHER_TASK}/review.md", review_current="true")
        state = self.project / "project" / "state.yaml"
        (other / "review.md").write_text(
            sha256_review(OTHER_TASK, "project/state.yaml", sha256_of(state)), encoding="utf-8"
        )
        first = self.archive(OTHER_ID)
        self.assertEqual(first.returncode, 0, output(first))
        self.assertPasses(self.check("--full"))
        self.assertRefusedUnchanged(f"work/archive/{OTHER_ID}/task.yaml:review_ref")
        self.assertPasses(self.check("--full"))

    def test_c_reads_a_dot_slash_archived_reference_as_the_checker_does(self) -> None:
        other = self.add_other_task()
        (other / "notes.md").write_text("Durable context and decisions.\n", encoding="utf-8")
        self.write_task(render_task(status="done", context_refs=f"[./{OTHER_TASK}/notes.md]"))
        self.set_focus(OTHER_ID)
        first = self.archive(TASK_ID)
        self.assertEqual(first.returncode, 0, output(first))
        self.assertPasses(self.check("--full"))
        before = tree_snapshot(self.project)
        second = self.archive(OTHER_ID)
        self.assertEqual(second.returncode, 2, output(second))
        self.assertIn(f"context_refs[0] -> ./{OTHER_TASK}/notes.md", output(second))
        self.assertEqual(tree_snapshot(self.project), before)

    def test_check_backstop_rolls_back_what_planning_misses(self) -> None:
        tools = load_memory_tools()
        other = self.add_other_task()
        (other / "notes.md").write_text("Durable context and decisions.\n", encoding="utf-8")
        self.write_task(render_task(status="done", context_refs=f"[{OTHER_TASK}/notes.md]"))
        self.set_focus(OTHER_ID)
        self.assertEqual(self.archive(TASK_ID).returncode, 0)
        before = tree_snapshot(self.project)
        stderr = io.StringIO()
        # Blind the planning check, as if it had a gap; the full-check backstop must still refuse.
        with patch.object(tools, "archived_references", return_value=[]), contextlib.redirect_stdout(
            io.StringIO()
        ), contextlib.redirect_stderr(stderr):
            code = tools.archive_main([str(self.project), OTHER_ID])
        self.assertEqual(code, 2, stderr.getvalue())
        self.assertIn("would add errors to `check --full`, so it was rolled back", stderr.getvalue())
        self.assertIn("referenced path does not exist", stderr.getvalue())
        self.assertEqual(tree_snapshot(self.project), before)
        self.assertFalse((self.project / f"work/archive/{OTHER_ID}").exists())

    def test_archive_of_an_already_failing_project_reports_it_added_no_errors(self) -> None:
        self.write_task(render_task(status="done"))
        self.add_other_task(context_refs="[missing.md]")
        self.assertFailsWith(self.check("--full"), "referenced path does not exist")
        result = self.archive(TASK_ID)
        self.assertEqual(result.returncode, 0, output(result))
        self.assertIn("still fails with the 1 error(s) it had before; archive added none", result.stdout)

    def test_guard_errors_that_only_move_with_the_task_are_not_new(self) -> None:
        # The archived task's own pre-existing error is reported under its new path afterwards.
        self.write_task(render_task(status="done", context_refs="[missing.md]"))
        self.assertFailsWith(self.check("--full"), f"{ACTIVE_TASK}/task.yaml:context_refs[0]")
        result = self.archive(TASK_ID)
        self.assertEqual(result.returncode, 0, output(result))
        self.assertFailsWith(self.check("--full"), f"{ARCHIVED_TASK}/task.yaml:context_refs[0]")

    def archived_task_with_a_malformed_review(self) -> Path:
        """Scenario D: an archived task references T-002's notes and has a review with a duplicate key."""
        other = self.add_other_task()
        (other / "notes.md").write_text("Durable context and decisions.\n", encoding="utf-8")
        artifact = self.project / "artifact.txt"
        artifact.write_text("Reviewed content.\n", encoding="utf-8")
        (self.task_dir / "review.md").write_text(
            sha256_review(ACTIVE_TASK, "artifact.txt", sha256_of(artifact)), encoding="utf-8"
        )
        self.write_task(
            render_task(
                status="done",
                context_refs=f"[{OTHER_TASK}/notes.md]",
                review_current="true",
                review_ref=f"{ACTIVE_TASK}/review.md",
            )
        )
        self.set_focus(OTHER_ID)
        self.assertEqual(self.archive(TASK_ID).returncode, 0)
        review = self.project / ARCHIVED_TASK / "review.md"
        review.write_text(
            review.read_text(encoding="utf-8").replace('mode: "fresh_context"', 'mode: "fresh_context"\nmode: "fresh_context"'),
            encoding="utf-8",
        )
        self.assertFailsWith(self.check("--full"), "duplicate key 'mode'")
        return review

    def test_d_a_malformed_archived_record_does_not_hide_its_tasks_references(self) -> None:
        self.archived_task_with_a_malformed_review()
        before = tree_snapshot(self.project)
        result = self.archive(OTHER_ID)
        self.assertEqual(result.returncode, 2, output(result))
        self.assertIn(f"{ARCHIVED_TASK}/task.yaml:context_refs[0] -> {OTHER_TASK}/notes.md", output(result))
        self.assertEqual(tree_snapshot(self.project), before)

    def test_d_backstop_also_guards_an_already_failing_project(self) -> None:
        tools = load_memory_tools()
        self.archived_task_with_a_malformed_review()
        before = tree_snapshot(self.project)
        stderr = io.StringIO()
        with patch.object(tools, "archived_references", return_value=[]), contextlib.redirect_stdout(
            io.StringIO()
        ), contextlib.redirect_stderr(stderr):
            code = tools.archive_main([str(self.project), OTHER_ID])
        self.assertEqual(code, 2, stderr.getvalue())
        self.assertIn("would add errors to `check --full`", stderr.getvalue())
        self.assertIn("context_refs[0]: referenced path does not exist", stderr.getvalue())
        self.assertNotIn("duplicate key", stderr.getvalue(), "pre-existing errors are not reported as new")
        self.assertEqual(tree_snapshot(self.project), before)

    def test_references_of_an_archived_task_with_another_version_are_still_protected(self) -> None:
        other = self.add_other_task()
        (other / "notes.md").write_text("Durable context and decisions.\n", encoding="utf-8")
        self.write_task(render_task(status="done", context_refs=f"[{OTHER_TASK}/notes.md]"))
        self.set_focus(OTHER_ID)
        self.assertEqual(self.archive(TASK_ID).returncode, 0)
        archived = self.project / ARCHIVED_TASK / "task.yaml"
        archived.write_text(archived.read_text(encoding="utf-8").replace("schema_version: 3", "schema_version: 2"), encoding="utf-8")
        before = tree_snapshot(self.project)
        result = self.archive(OTHER_ID)
        self.assertEqual(result.returncode, 2, output(result))
        self.assertIn(f"{ARCHIVED_TASK}/task.yaml:context_refs[0]", output(result))
        self.assertEqual(tree_snapshot(self.project), before)

    def test_successful_archive_reports_that_check_still_passes(self) -> None:
        self.finished_task_with_records()
        result = self.archive(TASK_ID)
        self.assertEqual(result.returncode, 0, output(result))
        self.assertIn("check --full still passes", result.stdout)


# ---------------------------------------------------------------------------
# P2-04: rollback is verified and reported truthfully
# ---------------------------------------------------------------------------


class ArchiveRollbackTest(AuditArchiveCase):
    def setUp(self) -> None:
        super().setUp()
        self.tools = load_memory_tools()
        self.finished_task_with_records()

    def run_archive(self, failing_overwrite) -> tuple[int, str]:
        stderr = io.StringIO()
        with patch.object(self.tools, "overwrite", side_effect=failing_overwrite), contextlib.redirect_stdout(
            io.StringIO()
        ), contextlib.redirect_stderr(stderr):
            code = self.tools.archive_main([str(self.project), TASK_ID])
        return code, stderr.getvalue()

    def test_reports_an_incomplete_rollback_and_keeps_the_original_bytes(self) -> None:
        state = self.project / "project" / "state.yaml"
        original = state.read_bytes()

        def persistent_disk_full(path: Path, payload: bytes) -> None:
            with path.open("wb") as handle:
                handle.write(payload[:5])
            raise OSError(errno.ENOSPC, "injected persistent disk full")

        code, stderr = self.run_archive(persistent_disk_full)
        self.assertEqual(code, 3, stderr)
        self.assertNotIn("was rolled back", stderr)
        self.assertIn("could not roll back completely", stderr)
        # state.yaml is the first rewrite, so it is the file the injected fault corrupts.
        self.assertIn("RESIDUE project/state.yaml does not have its original bytes", stderr)
        self.assertTrue(self.task_dir.is_dir(), "the task folder is moved back")
        backup = Path(re.search(r"BACKUP original bytes of the unrestored files are in (\S+)", stderr).group(1))
        self.addCleanup(shutil.rmtree, backup, True)
        self.assertEqual((backup / "project" / "state.yaml").read_bytes(), original)

    def test_guard_a_single_failure_rolls_back_every_byte(self) -> None:
        before = tree_snapshot(self.project)
        real = self.tools.overwrite
        calls = []

        def fail_once(path: Path, payload: bytes) -> None:
            calls.append(path)
            if len(calls) == 2:
                raise OSError(errno.EIO, "injected one-time failure")
            real(path, payload)

        code, stderr = self.run_archive(fail_once)
        self.assertEqual(code, 2, stderr)
        self.assertIn("was rolled back", stderr)
        self.assertEqual(tree_snapshot(self.project), before)

    def test_guard_writes_leave_no_temporary_files(self) -> None:
        result = self.archive(TASK_ID)
        self.assertEqual(result.returncode, 0, output(result))
        self.assertEqual(list(self.project.rglob(".*.tmp")), [])


# ---------------------------------------------------------------------------
# P1-03, P1-04, P2-05: subjects bind exactly what they name
# ---------------------------------------------------------------------------


@unittest.skipUnless(HAS_GIT, "git is required")
class SubjectBindingTest(ProjectCase):
    def setUp(self) -> None:
        super().setUp()
        (self.project / "app.py").write_text("print(1)\n", encoding="utf-8")
        self.git_init()
        self.base = self.commit("base")

    def subject(self, *args: str) -> subprocess.CompletedProcess[str]:
        return project_memory("subject", self.project, *args)

    def write_review(self, subject: str, paths: str) -> None:
        (self.task_dir / "review.md").write_text(
            "---\n"
            f'task_ref: "{ACTIVE_TASK}/task.yaml"\n'
            f'subject: "{subject}"\n'
            f"subject_paths: {paths}\n"
            'mode: "fresh_context"\n'
            'verdict: "passed"\n'
            "---\n"
            "- Evidence inspected: the named subject and its acceptance output.\n",
            encoding="utf-8",
        )
        self.write_task(render_task(review_ref=f"{ACTIVE_TASK}/review.md", review_current="true"))

    def test_subject_refuses_a_git_ignored_file(self) -> None:
        (self.project / ".gitignore").write_text("cache.txt\n", encoding="utf-8")
        (self.project / "cache.txt").write_text("reviewed v1\n", encoding="utf-8")
        for kind in ("worktree", "git"):
            with self.subTest(kind=kind):
                result = self.subject(kind, "cache.txt")
                self.assertEqual(result.returncode, 2, output(result))
                self.assertIn("sha256", result.stderr)

    def test_checker_rejects_a_worktree_subject_over_a_git_ignored_file(self) -> None:
        digest = load_memory_tools().v3_worktree_digest  # the checker's own digest
        (self.project / ".gitignore").write_text("cache.txt\n", encoding="utf-8")
        (self.project / "cache.txt").write_text("reviewed v1\n", encoding="utf-8")
        self.write_review(f"worktree:{digest(self.project, ['cache.txt'])}", "[cache.txt]")
        self.assertFailsWith(self.check(), "git-ignored")

    def test_checker_rejects_a_branch_name_as_git_subject(self) -> None:
        branch = self.git("rev-parse", "--abbrev-ref", "HEAD")
        for subject in (f"git:{branch}", f"git:{self.base[:12]}", "git:HEAD"):
            with self.subTest(subject=subject):
                self.write_review(subject, "[app.py]")
                self.assertFailsWith(self.check(), "full 40- or 64-character commit SHA")

    def test_guard_full_sha_git_subject_still_passes(self) -> None:
        self.write_review(f"git:{self.base}", "[app.py]")
        self.assertPasses(self.check())

    def test_names_that_parse_as_numbers_or_booleans_round_trip(self) -> None:
        for name in ("001", "true", "null"):
            (self.project / name).write_text(f"content of {name}\n", encoding="utf-8")
        base = self.commit("odd names")
        for name in ("001", "true", "null"):
            with self.subTest(name=name):
                result = self.subject("git", name)
                self.assertEqual(result.returncode, 0, output(result))
                self.assertIn(f'subject_paths: ["{name}"]', result.stdout)
                self.write_review(f"git:{base}", f'["{name}"]')
                self.assertPasses(self.check())

    def test_checker_rejects_unquoted_numeric_subject_paths(self) -> None:
        (self.project / "001").write_text("content\n", encoding="utf-8")
        base = self.commit("numeric name")
        self.write_review(f"git:{base}", "[001]")
        self.assertFailsWith(self.check(), "is not a path string")

    def test_subject_refuses_a_hash_in_the_path(self) -> None:
        (self.project / "note#1.md").write_text("content\n", encoding="utf-8")
        result = self.subject("sha256", "note#1.md")
        self.assertEqual(result.returncode, 2, output(result))
        self.assertIn("#fragment", result.stderr)


# ---------------------------------------------------------------------------
# P1-05, P2-01 A, P2-06, P3-01: checker completeness
# ---------------------------------------------------------------------------


class CheckerCompletenessTest(ProjectCase):
    def test_full_check_requires_the_recovery_focus_to_exist(self) -> None:
        state = self.project / "project" / "state.yaml"
        state.write_text(
            re.sub(r"^active_task:.*$", "active_task: T-999-missing", state.read_text(encoding="utf-8"), flags=re.M),
            encoding="utf-8",
        )
        for mode in ((), ("--full",)):
            with self.subTest(mode=mode):
                self.assertFailsWith(self.check(*mode), "does not exist in work/active")

    def test_guard_null_focus_still_passes_full(self) -> None:
        state = self.project / "project" / "state.yaml"
        state.write_text(
            re.sub(r"^active_task:.*$", "active_task: null", state.read_text(encoding="utf-8"), flags=re.M),
            encoding="utf-8",
        )
        self.write_task(render_task())
        self.assertPasses(self.check("--full"))

    def test_placeholder_inside_an_x_extension_or_comment_is_ignored(self) -> None:
        self.write_task(render_task() + "# TODO: tidy this record later\nx_native_graph:\n  node: TODO\n")
        self.assertPasses(self.check("--full"))
        self.assertEqual(run_script(INIT_SCRIPT, self.project).returncode, 0)

    def test_guard_placeholder_in_a_core_field_still_fails(self) -> None:
        self.write_task(render_task(goal='"TODO decide the goal"'))
        self.assertFailsWith(self.check(), "unresolved template placeholders")

    def test_missing_git_is_a_resource_error(self) -> None:
        (self.project / "source.txt").write_text("known bytes\n", encoding="utf-8")
        self.write_task(render_task(review_ref=f"{ACTIVE_TASK}/review.md", review_current="true"))
        (self.task_dir / "review.md").write_text(
            review_record(sha="a" * 40, subject_paths=["source.txt"], mode="fresh_context", action_refs=[]),
            encoding="utf-8",
        )
        empty = self.tmp / "empty-bin"
        empty.mkdir()
        result = subprocess.run(
            [sys.executable, "-B", str(SKILL_ROOT / "scripts" / "check_project_memory.py"), str(self.project)],
            capture_output=True,
            text=True,
            env={**os.environ, "PATH": str(empty)},
            check=False,
        )
        self.assertEqual(result.returncode, 2, output(result))
        self.assertIn("need git", result.stdout)
        self.assertNotIn("Traceback", output(result))

    def test_initializer_skips_protection_for_outputs_that_already_exist(self) -> None:
        self.write_task(render_task(status="proposed", protected_paths="[AGENTS.md]"))
        result = run_script(INIT_SCRIPT, self.project)
        self.assertEqual(result.returncode, 0, output(result))
        self.assertIn("SKIP AGENTS.md", result.stdout)


@unittest.skipUnless(HAS_GIT, "git is required")
class CompletionCoversEveryActionTest(ProjectCase):
    def action(self, index: int, status: str, key: str | None) -> str:
        executed = status != "planned"
        return (
            f'action_id: "A-00{index}"\ntarget: "target-{index}"\nenvironment: "production"\n'
            f'payload_scope: "bounded-{index}"\nsubject: "sha256:{sha256_of(self.project / "payload.bin")}"\n'
            'subject_ref: "payload.bin"\n'
            f"authorization_basis: {'direct-human-instruction' if executed else 'null'}\n"
            f"authority_ref: {ACTIVE_TASK + '/authority.md' if executed else 'null'}\n"
            f"one_shot: true\nidempotency_key: {key or 'null'}\n"
            'expires_at: "2099-01-01T00:00:00Z"\ntimeout_seconds: 30\n'
            f"status: {status}\n"
            f'observation: "{"receipt confirms the effect" if executed else "not attempted"}"\n'
            'compensation: "bounded restoration procedure"\n'
        )

    def test_planned_action_without_a_key_blocks_completion(self) -> None:
        (self.project / "payload.bin").write_bytes(b"exact bounded payload")
        (self.task_dir / "authority.md").write_text("The human approved this exact bounded effect.\n", encoding="utf-8")
        (self.task_dir / "accept.md").write_text("The human accepts this bounded result.\n", encoding="utf-8")
        refs = [f"{ACTIVE_TASK}/action1.yaml", f"{ACTIVE_TASK}/action2.yaml"]
        (self.project / refs[0]).write_text(self.action(1, "succeeded", "effect-one"), encoding="utf-8")
        (self.project / refs[1]).write_text(self.action(2, "planned", None), encoding="utf-8")
        self.write_task(
            render_task(
                status="done",
                risk="high",
                risk_reasons="[security-or-safety]",
                action_refs=f"[{', '.join(refs)}]",
                completion_acceptance_ref=f"{ACTIVE_TASK}/accept.md",
                review_ref=f"{ACTIVE_TASK}/review.md",
                review_current="true",
            )
        )
        self.git_init()
        head = self.commit("actions")
        (self.task_dir / "review.md").write_text(
            review_record(sha=head, subject_paths=[*refs, "payload.bin"], mode="independent_actor", action_refs=refs),
            encoding="utf-8",
        )
        result = self.check()
        self.assertFailsWith(result, "completion cannot claim unfinished or ambiguous external actions")
        self.assertIn("action2.yaml (planned, no idempotency_key)", result.stdout)
        # Removing the unfinished action leaves one finished effect, which may complete.
        self.write_task(
            (self.task_dir / "task.yaml").read_text(encoding="utf-8").replace(f", {refs[1]}", "")
        )
        (self.project / refs[1]).unlink()
        head = self.commit("drop the unexecuted action")
        (self.task_dir / "review.md").write_text(
            review_record(sha=head, subject_paths=[refs[0], "payload.bin"], mode="independent_actor", action_refs=refs[:1]),
            encoding="utf-8",
        )
        self.assertPasses(self.check())


if __name__ == "__main__":
    unittest.main()
