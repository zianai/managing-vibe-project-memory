"""Regression tests for review findings 3 and 4 (target release v3.0.2).

Finding 4: every field and value the checker enforces is documented in
``references/field-reference.md``, and ``project_memory.py subject`` prints
claim subjects that agents could not compute before.

Finding 3: ``project_memory.py archive`` moves a task to ``work/archive/`` and
rewrites the paths that point into it, so archiving is one safe command.

Tests named ``test_guard_*`` already pass on v3.0.1 and must keep passing. All
other tests fail on v3.0.1 and describe the target behavior.

Run from the repository root:

    python3 -m unittest tests.test_reference_and_archive -v
"""

from __future__ import annotations

import hashlib
import importlib
import re
import subprocess
import sys
import unittest
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent
if str(TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTS_ROOT))

from test_review_findings import (  # noqa: E402
    ACTIVE_TASK,
    ARCHIVED_TASK,
    CHECK_SCRIPT,
    HAS_GIT,
    SKILL_ROOT,
    TASK_ID,
    ProjectCase,
    output,
    render_task,
    review_record,
    run_script,
)

PROJECT_MEMORY_SCRIPT = SKILL_ROOT / "scripts" / "project_memory.py"
FIELD_REFERENCE = SKILL_ROOT / "references" / "field-reference.md"
KERNEL_REFERENCE = SKILL_ROOT / "references" / "continuity-kernel.md"
SKILL_FILE = SKILL_ROOT / "SKILL.md"

RECORD_GETTER_RE = re.compile(
    r"\b(?:task|state|record|review_record|handoff_record)\.get\(\s*\"([a-z][a-z0-9_]*)\""
)
BACKTICK_SPAN_RE = re.compile(r"`([^`\n]+)`")
SUBJECT_LINE_RE = re.compile(r'^subject: "((?:git|worktree|sha256):[0-9a-f]+)"$', re.MULTILINE)


def project_memory(*args: object) -> subprocess.CompletedProcess[str]:
    return run_script(PROJECT_MEMORY_SCRIPT, *args)


def load_checker():
    scripts = str(SKILL_ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    sys.dont_write_bytecode = True
    return importlib.import_module("check_project_memory")


def documented_spans() -> list[str]:
    return BACKTICK_SPAN_RE.findall(FIELD_REFERENCE.read_text(encoding="utf-8"))


def is_documented(token: str, spans: list[str]) -> bool:
    pattern = re.compile(rf"(?<![A-Za-z0-9_-]){re.escape(token)}(?![A-Za-z0-9_-])")
    return any(pattern.search(span) for span in spans)


def assert_refused(case: unittest.TestCase, result: subprocess.CompletedProcess[str], reason: str) -> None:
    """Exit 2 for a deliberate refusal that names its reason (not an argparse error)."""
    case.assertEqual(result.returncode, 2, output(result))
    case.assertNotIn("invalid choice", output(result))
    case.assertIn(reason.lower(), output(result).lower())


def tree_snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


# ---------------------------------------------------------------------------
# Finding 4a: one reference for every enforced field and value
# ---------------------------------------------------------------------------


class FieldReferenceTest(unittest.TestCase):
    def test_reference_exists_and_is_routed_from_the_skill(self) -> None:
        self.assertTrue(FIELD_REFERENCE.is_file(), "references/field-reference.md is missing")
        self.assertIn("references/field-reference.md", SKILL_FILE.read_text(encoding="utf-8"))
        self.assertIn("field-reference.md", KERNEL_REFERENCE.read_text(encoding="utf-8"))

    def test_guide_command_prints_the_reference(self) -> None:
        result = project_memory("guide", "field-reference")
        self.assertEqual(result.returncode, 0, output(result))
        self.assertEqual(result.stdout, FIELD_REFERENCE.read_text(encoding="utf-8"))

    def test_every_field_the_checker_reads_is_documented(self) -> None:
        source = (SKILL_ROOT / "scripts" / "check_project_memory.py").read_text(encoding="utf-8")
        checker = load_checker()
        fields = set(RECORD_GETTER_RE.findall(source))
        fields |= set(checker.V3_REQUIRED_STATE_KEYS) | set(checker.V3_REQUIRED_TASK_KEYS)
        optional_refs = re.search(r"optional_ref_fields = \((.*?)\)", source, re.S)
        if optional_refs:
            fields |= set(re.findall(r'"([a-z_]+)"', optional_refs.group(1)))
        self.assertGreaterEqual(len(fields), 60, "field scan found too little; update the scan")
        spans = documented_spans() if FIELD_REFERENCE.is_file() else []
        missing = sorted(field for field in fields if not is_documented(field, spans))
        self.assertEqual(missing, [], "fields read by the checker but absent from field-reference.md")

    def test_every_value_the_checker_enforces_is_documented(self) -> None:
        checker = load_checker()
        values: set[str] = set()
        values |= set(checker.RISK_FACTOR_FLOORS)
        values |= set(checker.V3_ACTION_AUTHORITY_ALLOWED)
        values |= set(checker.V3_ACTION_STATUSES)
        values |= set(checker.V3_CONFORMANCE_STATUSES)
        for field, field_values in checker.V3_HIGH_IMPACT_EFFECTS.items():
            values.add(field)
            values |= set(field_values)
        values |= {
            # reconciliation_result
            "effect-confirmed", "no-effect-confirmed", "compensated-confirmed",
            # review mode and verdict
            "self_check", "fresh_context", "independent_actor", "human", "passed",
            # integration_status, visual_alignment, visual_alignment_status
            "resolved", "merged", "reserved", "accepted", "delegated",
            # subject kinds, including the patch: alias
            "git:", "worktree:", "patch:", "sha256:", "provider:", "artifact:",
        }
        spans = documented_spans() if FIELD_REFERENCE.is_file() else []
        missing = sorted(value for value in values if not is_documented(value, spans))
        self.assertEqual(missing, [], "values enforced by the checker but absent from field-reference.md")
        self.assertTrue(
            any(re.search(r"custom-(?:high|<)", span) for span in spans),
            "document the custom-<level>:<slug> risk_reasons syntax",
        )


# ---------------------------------------------------------------------------
# Finding 4b: a command that prints claim subjects
# ---------------------------------------------------------------------------


@unittest.skipUnless(HAS_GIT, "git is required")
class SubjectCommandTest(ProjectCase):
    def setUp(self) -> None:
        super().setUp()
        (self.project / "src").mkdir()
        (self.project / "src" / "app.py").write_text('print("v1")\n', encoding="utf-8")
        (self.project / "deploy").mkdir()
        (self.project / "deploy" / "payload.txt").write_text("replicas: 3\n", encoding="utf-8")
        self.git_init()
        self.base = self.commit("base")

    def subject(self, *args: str) -> subprocess.CompletedProcess[str]:
        return project_memory("subject", self.project, *args)

    def test_worktree_subject_round_trips_through_the_checker(self) -> None:
        (self.project / "src" / "app.py").write_text('print("v2, uncommitted")\n', encoding="utf-8")
        before = tree_snapshot(self.project)
        status_before = self.git("status", "--porcelain")
        result = self.subject("worktree", "src/app.py")
        self.assertEqual(result.returncode, 0, output(result))
        self.assertEqual(tree_snapshot(self.project), before, "subject must not write files")
        self.assertEqual(self.git("status", "--porcelain"), status_before)
        match = SUBJECT_LINE_RE.search(result.stdout)
        self.assertIsNotNone(match, result.stdout)
        subject = match.group(1)
        self.assertRegex(subject, r"^worktree:[0-9a-f]{64}$")
        self.assertIn("subject_paths: [src/app.py]", result.stdout)

        review = review_record(sha="0" * 40, subject_paths=["src/app.py"], mode="fresh_context", action_refs=[])
        review = review.replace(f'subject: "git:{"0" * 40}"', f'subject: "{subject}"')
        (self.task_dir / "review.md").write_text(review, encoding="utf-8")
        self.write_task(render_task(review_ref=f"{ACTIVE_TASK}/review.md", review_current="true"))
        self.assertPasses(self.check())

        (self.project / "src" / "app.py").write_text('print("v3")\n', encoding="utf-8")
        stale = self.check()
        self.assertFailsWith(stale, "stale")
        self.assertIn("project_memory.py subject", stale.stdout)

    def test_git_subject_names_head_for_clean_paths(self) -> None:
        result = self.subject("git", "src/app.py")
        self.assertEqual(result.returncode, 0, output(result))
        match = SUBJECT_LINE_RE.search(result.stdout)
        self.assertIsNotNone(match, result.stdout)
        self.assertEqual(match.group(1), f"git:{self.base}")
        self.assertIn("subject_paths: [src/app.py]", result.stdout)

    def test_git_subject_refuses_uncommitted_paths_and_suggests_worktree(self) -> None:
        (self.project / "src" / "app.py").write_text('print("dirty")\n', encoding="utf-8")
        result = self.subject("git", "src/app.py")
        self.assertEqual(result.returncode, 1, output(result))
        self.assertIn("worktree", output(result))

    def test_sha256_subject_prints_its_subject_ref(self) -> None:
        result = self.subject("sha256", "deploy/payload.txt")
        self.assertEqual(result.returncode, 0, output(result))
        expected = hashlib.sha256((self.project / "deploy" / "payload.txt").read_bytes()).hexdigest()
        match = SUBJECT_LINE_RE.search(result.stdout)
        self.assertIsNotNone(match, result.stdout)
        self.assertEqual(match.group(1), f"sha256:{expected}")
        self.assertIn('subject_ref: "deploy/payload.txt"', result.stdout)

    def test_subject_rejects_paths_outside_the_project(self) -> None:
        result = self.subject("worktree", "../outside.txt")
        assert_refused(self, result, "outside")


# ---------------------------------------------------------------------------
# Finding 3: archiving is one safe command
# ---------------------------------------------------------------------------


class ArchiveCase(ProjectCase):
    def archive(self, *args: str) -> subprocess.CompletedProcess[str]:
        return project_memory("archive", self.project, *args)

    def finished_task_with_records(self) -> None:
        """A done task whose own records point at work/active/<id>/... paths."""
        (self.task_dir / "decisions.md").write_text(
            "## D-001 Export format\n\n- Decision: CSV first, XLSX later.\n- Source: direct human instruction.\n",
            encoding="utf-8",
        )
        (self.task_dir / "handoff.md").write_text(
            "---\n"
            f'task_ref: "{ACTIVE_TASK}/task.yaml"\n'
            f'subject: "sha256:{"0" * 64}"\n'
            'subject_ref: ""\n'
            "subject_paths: []\n"
            "---\n"
            "- Completed: CSV export. Incomplete: none.\n",
            encoding="utf-8",
        )
        self.write_task(
            render_task(
                status="done",
                decision_refs=f"[{ACTIVE_TASK}/decisions.md]",
                handoff_ref=f"{ACTIVE_TASK}/handoff.md",
                handoff_current="false",
            )
        )

    def files_mentioning(self, text: str) -> list[str]:
        return sorted(
            name for name, data in tree_snapshot(self.project).items()
            if text.encode("utf-8") in data
        )

    def state_line(self, key: str) -> str:
        for line in (self.project / "project" / "state.yaml").read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{key}:"):
                return line
        return ""


class ArchiveWithoutGitTest(ArchiveCase):
    def test_archive_moves_the_task_and_rewrites_its_paths(self) -> None:
        self.finished_task_with_records()
        self.assertPasses(self.check("--full"))
        result = self.archive(TASK_ID)
        self.assertEqual(result.returncode, 0, output(result))
        self.assertFalse((self.project / ACTIVE_TASK).exists())
        self.assertTrue((self.project / ARCHIVED_TASK / "task.yaml").is_file())
        self.assertEqual(self.files_mentioning(f"{ACTIVE_TASK}/"), [])
        self.assertIn(f"{ARCHIVED_TASK}/decisions.md", (self.project / ARCHIVED_TASK / "task.yaml").read_text(encoding="utf-8"))
        self.assertRegex(self.state_line("active_task"), r"^active_task:\s*(?:null|~)?\s*$")
        self.assertPasses(self.check())
        self.assertPasses(self.check("--full"))

    def test_dry_run_lists_the_plan_and_changes_nothing(self) -> None:
        self.finished_task_with_records()
        before = tree_snapshot(self.project)
        result = self.archive(TASK_ID, "--dry-run")
        self.assertEqual(result.returncode, 0, output(result))
        self.assertIn("MOVE", result.stdout)
        self.assertIn("task.yaml", result.stdout)
        self.assertIn("handoff.md", result.stdout)
        self.assertEqual(tree_snapshot(self.project), before)

    def test_refuses_an_unknown_task(self) -> None:
        result = self.archive("T-999-missing")
        assert_refused(self, result, "T-999-missing")

    def test_refuses_when_the_archive_folder_already_exists(self) -> None:
        self.finished_task_with_records()
        (self.project / ARCHIVED_TASK).mkdir(parents=True)
        before = tree_snapshot(self.project)
        result = self.archive(TASK_ID)
        assert_refused(self, result, "exists")
        self.assertEqual(tree_snapshot(self.project), before)
        self.assertTrue((self.project / ACTIVE_TASK).is_dir())

    def test_refuses_a_symlink_inside_the_task(self) -> None:
        self.finished_task_with_records()
        outside = self.tmp / "outside.md"
        outside.write_text("outside\n", encoding="utf-8")
        (self.task_dir / "linked.md").symlink_to(outside)
        result = self.archive(TASK_ID)
        assert_refused(self, result, "symlink")
        self.assertTrue((self.project / ACTIVE_TASK).is_dir())

    def test_rewrites_refs_from_other_active_tasks_but_not_lookalike_ids(self) -> None:
        self.finished_task_with_records()
        other = self.project / "work" / "active" / "T-002-next"
        other.mkdir()
        (other / "task.yaml").write_text(
            render_task(id="T-002-next", decision_refs=f"[{ACTIVE_TASK}/decisions.md]"),
            encoding="utf-8",
        )
        lookalike_id = f"{TASK_ID}-v2"
        lookalike = self.project / "work" / "active" / lookalike_id
        lookalike.mkdir()
        (lookalike / "notes.md").write_text("Notes for the v2 follow-up.\n", encoding="utf-8")
        lookalike_ref = f"work/active/{lookalike_id}/notes.md"
        (lookalike / "task.yaml").write_text(
            render_task(id=lookalike_id, context_refs=f"[{lookalike_ref}]"),
            encoding="utf-8",
        )
        state = self.project / "project" / "state.yaml"
        state.write_text(
            re.sub(r"^active_task:.*$", "active_task: T-002-next", state.read_text(encoding="utf-8"), flags=re.M),
            encoding="utf-8",
        )
        self.assertPasses(self.check("--full"))

        result = self.archive(TASK_ID)
        self.assertEqual(result.returncode, 0, output(result))
        self.assertIn(f"{ARCHIVED_TASK}/decisions.md", (other / "task.yaml").read_text(encoding="utf-8"))
        self.assertIn(lookalike_ref, (lookalike / "task.yaml").read_text(encoding="utf-8"))
        self.assertEqual(self.state_line("active_task"), "active_task: T-002-next")
        self.assertPasses(self.check("--full"))

    def test_kernel_reference_documents_the_archive_command(self) -> None:
        text = KERNEL_REFERENCE.read_text(encoding="utf-8")
        self.assertIn("project_memory.py archive", text)

    def test_guard_manual_archive_without_rewrites_still_fails(self) -> None:
        self.finished_task_with_records()
        archived = self.project / ARCHIVED_TASK
        archived.parent.mkdir(parents=True, exist_ok=True)
        self.task_dir.rename(archived)
        self.assertFailsWith(self.check("--full"), "does not exist")


@unittest.skipUnless(HAS_GIT, "git is required")
class ArchiveWithGitTest(ArchiveCase):
    def setUp(self) -> None:
        super().setUp()
        (self.project / "src").mkdir()
        (self.project / "src" / "app.py").write_text('print("v1")\n', encoding="utf-8")
        self.git_init()

    def reviewed_task(self) -> None:
        sha = self.commit("implement")
        self.finished_task_with_records()
        (self.task_dir / "review.md").write_text(
            review_record(sha=sha, subject_paths=["src/app.py"], mode="fresh_context", action_refs=[]),
            encoding="utf-8",
        )
        self.write_task(
            render_task(
                status="done",
                decision_refs=f"[{ACTIVE_TASK}/decisions.md]",
                handoff_ref=f"{ACTIVE_TASK}/handoff.md",
                handoff_current="false",
                review_ref=f"{ACTIVE_TASK}/review.md",
                review_current="true",
            )
        )
        self.commit("review and records")

    def test_archive_never_stages_or_commits(self) -> None:
        self.reviewed_task()
        head = self.git("rev-parse", "HEAD")
        result = self.archive(TASK_ID)
        self.assertEqual(result.returncode, 0, output(result))
        self.assertEqual(self.git("rev-parse", "HEAD"), head)
        staged = subprocess.run(
            ["git", "-C", str(self.project), "diff", "--cached", "--quiet"],
            check=False,
        )
        self.assertEqual(staged.returncode, 0, "archive must not stage anything")
        self.assertEqual(self.files_mentioning(f"{ACTIVE_TASK}/"), [])
        self.assertPasses(self.check("--full"))
        self.commit("archive")
        (self.project / "src" / "app.py").write_text('print("v2")\n', encoding="utf-8")
        self.commit("later work")
        self.assertPasses(self.check("--full"))

    def test_refuses_uncommitted_changes_in_the_task(self) -> None:
        self.reviewed_task()
        task_file = self.task_dir / "task.yaml"
        task_file.write_text(task_file.read_text(encoding="utf-8") + "x_note: unsaved\n", encoding="utf-8")
        before = tree_snapshot(self.project)
        result = self.archive(TASK_ID)
        assert_refused(self, result, "commit")
        self.assertEqual(tree_snapshot(self.project), before)


if __name__ == "__main__":
    unittest.main()
