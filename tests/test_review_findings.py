"""Regression tests for the 2026-10-19 review of protocol 3.0.

Each class covers one review finding. Tests named ``test_guard_*`` describe
behavior that already works and must keep working. All other tests describe the
target behavior and fail on the unfixed v3.0 code.

Run from the repository root:

    python3 -m unittest tests.test_review_findings -v
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
INIT_SCRIPT = SKILL_ROOT / "scripts" / "init_project_memory.py"
CHECK_SCRIPT = SKILL_ROOT / "scripts" / "check_project_memory.py"
HAS_GIT = shutil.which("git") is not None

TASK_ID = "T-001-initial"
ACTIVE_TASK = f"work/active/{TASK_ID}"
ARCHIVED_TASK = f"work/archive/{TASK_ID}"

BASE_TASK_FIELDS = (
    ("schema_version", "3"),
    ("protocol_version", '"3.0"'),
    ("id", TASK_ID),
    ("status", "executing"),
    ("goal", '"Add CSV export to the reports page"'),
    ("scope", "[src/]"),
    ("non_goals", "[Report data model changes]"),
    ("acceptance", "[Export test passes]"),
    ("risk", "low"),
    ("risk_reasons", "[local-reversible]"),
    ("protected_paths", "[]"),
    ("context_refs", "[]"),
    ("decision_refs", "[]"),
    ("evidence_refs", "[]"),
    ("updated", '"2026-10-19"'),
)


def run_script(script: Path, *args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(script), *(str(arg) for arg in args)],
        capture_output=True,
        text=True,
        check=False,
    )


def render_task(**overrides: str | None) -> str:
    """Render task.yaml. A value of None drops the key; a value starting with a
    newline is written as a block (``key:`` followed by the value's lines)."""
    fields = dict(BASE_TASK_FIELDS)
    for key, value in overrides.items():
        if value is None:
            fields.pop(key, None)
        else:
            fields[key] = value
    lines = []
    for key, value in fields.items():
        lines.append(f"{key}:{value}\n" if value.startswith("\n") else f"{key}: {value}\n")
    return "".join(lines)


def output(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


class ProjectCase(unittest.TestCase):
    """A freshly initialized project in a symlink-free temporary directory."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.project = self.tmp / "project"
        self.project.mkdir()
        result = run_script(INIT_SCRIPT, self.project, "--project-name", "Fixture")
        self.assertEqual(result.returncode, 0, output(result))
        self.task_dir = self.project / ACTIVE_TASK

    def write_task(self, text: str) -> None:
        (self.task_dir / "task.yaml").write_text(text, encoding="utf-8")

    def check(self, *args: str) -> subprocess.CompletedProcess[str]:
        return run_script(CHECK_SCRIPT, self.project, *args)

    def assertPasses(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, output(result))

    def assertFailsWith(self, result: subprocess.CompletedProcess[str], fragment: str) -> None:
        self.assertEqual(result.returncode, 1, output(result))
        self.assertIn(fragment, result.stdout)

    # Git helpers -----------------------------------------------------------

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.project), *args],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def git_init(self) -> None:
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Fixture")
        self.git("config", "commit.gpgsign", "false")

    def commit(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD")

    def archive_task(self) -> None:
        """Archive the task the way an agent would today: move the folder,
        rewrite every embedded work/active path, and clear the recovery focus."""
        archived = self.project / ARCHIVED_TASK
        archived.parent.mkdir(parents=True, exist_ok=True)
        self.task_dir.rename(archived)
        for path in archived.rglob("*"):
            if path.is_file():
                text = path.read_text(encoding="utf-8")
                path.write_text(text.replace(ACTIVE_TASK, ARCHIVED_TASK), encoding="utf-8")
        state = self.project / "project" / "state.yaml"
        lines = [
            "active_task: null" if line.startswith("active_task:") else line
            for line in state.read_text(encoding="utf-8").splitlines()
        ]
        state.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self.task_dir = archived


def review_record(*, sha: str, subject_paths: list[str], mode: str, action_refs: list[str]) -> str:
    return (
        "---\n"
        f'task_ref: "{ACTIVE_TASK}/task.yaml"\n'
        f'subject: "git:{sha}"\n'
        'subject_ref: ""\n'
        f"subject_paths: [{', '.join(subject_paths)}]\n"
        f'mode: "{mode}"\n'
        "actor_modified_subject: false\n"
        'verdict: "passed"\n'
        f"action_refs: [{', '.join(action_refs)}]\n"
        'baseline_subject: ""\n'
        'implementation_render_subject: ""\n'
        "---\n"
        "- Evidence inspected: the named commit, its source, and its test output.\n"
        "- Findings: none after inspection; behavior matches acceptance.\n"
        "- Limitations: no load testing.\n"
    )


# ---------------------------------------------------------------------------
# Finding 1: keyword scanning of goal/scope must not override the declared risk
# ---------------------------------------------------------------------------


class KeywordRiskIsAdvisoryTest(ProjectCase):
    ORDINARY_GOALS = (
        "Add an email alert to users when their export finishes",
        "Fix the cancel button for user subscriptions on the settings page",
        "Show a banner to notify users about scheduled maintenance",
        "Release v2 of the public docs site theme",
        "Process customer payments page - fix layout on mobile",
    )

    def test_keyword_goal_with_low_risk_passes_with_a_warning(self) -> None:
        for goal in self.ORDINARY_GOALS:
            with self.subTest(goal=goal):
                self.write_task(render_task(goal=f'"{goal}"'))
                result = self.check()
                self.assertPasses(result)
                self.assertIn("WARNING", result.stdout)

    def test_keyword_goal_completed_at_low_risk_needs_no_high_impact_records(self) -> None:
        self.write_task(
            render_task(
                goal='"Fix the cancel button for user subscriptions on the settings page"',
                status="done",
            )
        )
        self.assertPasses(self.check())

    def test_completion_acceptance_error_names_the_field_to_set(self) -> None:
        self.write_task(
            render_task(
                status="done",
                risk="high",
                risk_reasons="[publication-or-deployment]",
                external_effects="none",
            )
        )
        result = self.check()
        self.assertEqual(result.returncode, 1, output(result))
        self.assertIn("completion_acceptance_ref", result.stdout)

    def test_guard_declared_risk_reason_floor_is_still_enforced(self) -> None:
        self.write_task(render_task(risk_reasons="[publication-or-deployment]"))
        self.assertFailsWith(self.check(), "risk is below")

    def test_guard_declared_high_impact_effect_is_still_enforced(self) -> None:
        self.write_task(render_task(effect_environment="production"))
        self.assertFailsWith(self.check(), "risk is below")


# ---------------------------------------------------------------------------
# Finding 2: freshness applies to current claims, not to archived history
# ---------------------------------------------------------------------------


@unittest.skipUnless(HAS_GIT, "git is required")
class ArchivedClaimsTest(ProjectCase):
    def setUp(self) -> None:
        super().setUp()
        (self.project / "src").mkdir()
        (self.project / "src" / "app.py").write_text('print("v1")\n', encoding="utf-8")
        self.git_init()

    def reviewed_low_risk_task(self) -> None:
        sha = self.commit("implement banner")
        (self.task_dir / "review.md").write_text(
            review_record(sha=sha, subject_paths=["src/app.py"], mode="fresh_context", action_refs=[]),
            encoding="utf-8",
        )
        self.write_task(
            render_task(
                status="done",
                goal='"Print a version banner"',
                scope="[src/app.py]",
                review_ref=f"{ACTIVE_TASK}/review.md",
                review_current="true",
            )
        )
        self.commit("review")

    def test_archived_review_survives_later_edits_to_its_files(self) -> None:
        self.reviewed_low_risk_task()
        self.archive_task()
        self.commit("archive")
        self.assertPasses(self.check("--full"))
        (self.project / "src" / "app.py").write_text('print("v2")\n', encoding="utf-8")
        self.commit("a later task edits app.py")
        self.assertPasses(self.check("--full"))

    def test_archived_high_impact_task_survives_archiving(self) -> None:
        (self.project / "deploy").mkdir()
        payload = self.project / "deploy" / "payload.txt"
        payload.write_text("image: app@sha256:abc; replicas: 3\n", encoding="utf-8")
        payload_sha = hashlib.sha256(payload.read_bytes()).hexdigest()
        (self.task_dir / "authority.md").write_text(
            "Direct human instruction on 2026-10-19: deploy this payload to prod-1, once.\n",
            encoding="utf-8",
        )
        (self.task_dir / "acceptance.md").write_text(
            "Human accepted completion on 2026-10-19 after reviewing the observed rollout.\n",
            encoding="utf-8",
        )
        action_ref = f"{ACTIVE_TASK}/action-deploy.md"
        (self.project / action_ref).write_text(
            "---\n"
            'action_id: "A-001"\n'
            'target: "prod-1 cluster"\n'
            'environment: "production"\n'
            'payload_scope: "deploy/payload.txt image and replica count"\n'
            f'subject: "sha256:{payload_sha}"\n'
            'subject_ref: "deploy/payload.txt"\n'
            'authorization_basis: "direct-human-instruction"\n'
            f'authority_ref: "{ACTIVE_TASK}/authority.md"\n'
            "one_shot: true\n"
            'idempotency_key: "deploy-2026-10-19-001"\n'
            'expires_at: "2099-01-01T00:00:00Z"\n'
            "timeout_seconds: 600\n"
            "status: succeeded\n"
            'observation: "rollout complete, 3/3 replicas healthy"\n'
            'reconciliation_result: "effect-confirmed"\n'
            f'reconciliation_ref: "{ACTIVE_TASK}/authority.md"\n'
            'compensation: "roll back to the previous image"\n'
            "retry_allowed: false\n"
            "---\n"
            "Receipt: rollout id r-123.\n",
            encoding="utf-8",
        )
        self.write_task(
            render_task(
                status="done",
                goal='"Deploy the banner change"',
                scope="[src/app.py, deploy/]",
                risk="high",
                risk_reasons="[publication-or-deployment]",
                action_refs=f"[{action_ref}]",
                completion_acceptance_ref=f"{ACTIVE_TASK}/acceptance.md",
                review_ref=f"{ACTIVE_TASK}/review.md",
                review_current="true",
            )
        )
        sha = self.commit("deploy and record the action")
        (self.task_dir / "review.md").write_text(
            review_record(
                sha=sha,
                subject_paths=["src/app.py", "deploy/payload.txt", action_ref],
                mode="independent_actor",
                action_refs=[action_ref],
            ),
            encoding="utf-8",
        )
        self.commit("independent review")
        self.assertPasses(self.check("--full"))
        self.archive_task()
        self.commit("archive")
        self.assertPasses(self.check("--full"))

    def test_guard_active_review_still_goes_stale_when_its_files_change(self) -> None:
        self.reviewed_low_risk_task()
        self.assertPasses(self.check())
        (self.project / "src" / "app.py").write_text('print("v2")\n', encoding="utf-8")
        self.commit("edit after review")
        self.assertFailsWith(self.check(), "review_ref:subject")

    def test_guard_archived_review_must_name_an_existing_commit(self) -> None:
        self.reviewed_low_risk_task()
        review = self.task_dir / "review.md"
        text = review.read_text(encoding="utf-8")
        start = text.index("git:") + 4
        review.write_text(text[:start] + "0" * 40 + text[start + 40 :], encoding="utf-8")
        self.archive_task()
        self.commit("archive with a bad subject")
        self.assertFailsWith(self.check("--full"), "review_ref:subject")


# ---------------------------------------------------------------------------
# Finding 5: the YAML subset must not misread common YAML
# ---------------------------------------------------------------------------


class YamlSubsetTest(ProjectCase):
    def test_inline_comment_after_a_scalar_is_ignored(self) -> None:
        self.write_task(render_task(risk="low  # local only"))
        self.assertPasses(self.check())

    def test_inline_comment_after_a_flow_list_is_ignored(self) -> None:
        # Today the whole line becomes one string, so the ref cannot resolve.
        notes = self.project / "notes"
        notes.mkdir()
        (notes / "export.md").write_text("Context for the export format choice.\n", encoding="utf-8")
        self.write_task(render_task(context_refs="[notes/export.md]  # why CSV first"))
        self.assertPasses(self.check())

    def test_block_list_items_at_column_zero_are_accepted(self) -> None:
        self.write_task(render_task(scope="\n- src/reports/\n- src/export/"))
        self.assertPasses(self.check())

    def test_quoted_flow_list_item_keeps_its_comma(self) -> None:
        notes = self.project / "notes"
        notes.mkdir()
        (notes / "a, b.md").write_text("Context for the export format choice.\n", encoding="utf-8")
        self.write_task(render_task(context_refs='["notes/a, b.md"]'))
        self.assertPasses(self.check())

    def test_quoted_schema_version_is_accepted_or_explained(self) -> None:
        self.write_task(render_task(schema_version='"3"'))
        result = self.check()
        self.assertTrue(
            result.returncode == 0 or "unquoted" in result.stdout,
            output(result),
        )

    def test_initializer_rerun_reads_the_same_yaml_as_the_checker(self) -> None:
        self.write_task(
            render_task(
                risk="low  # local only",
                scope="\n- src/reports/\n- src/export/",
            )
        )
        self.assertPasses(self.check())
        rerun = run_script(INIT_SCRIPT, self.project, "--project-name", "Fixture")
        self.assertEqual(rerun.returncode, 0, output(rerun))

    def test_guard_two_space_block_list_still_works(self) -> None:
        self.write_task(render_task(scope="\n  - src/reports/\n  - src/export/"))
        self.assertPasses(self.check())

    def test_guard_nested_mapping_is_still_rejected(self) -> None:
        self.write_task(render_task(scope="\n  reports: src/reports/"))
        result = self.check()
        self.assertEqual(result.returncode, 1, output(result))


# ---------------------------------------------------------------------------
# Finding 7: symlinks above the project root are the user's environment
# ---------------------------------------------------------------------------


class SymlinkAncestorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.real = self.tmp / "real"
        self.real.mkdir()
        self.link = self.tmp / "link"
        self.link.symlink_to(self.real, target_is_directory=True)

    def init_and_check(self, project: Path) -> None:
        init = run_script(INIT_SCRIPT, project, "--project-name", "Fixture")
        self.assertEqual(init.returncode, 0, output(init))
        for mode in ("--focus", "--full"):
            checked = run_script(CHECK_SCRIPT, project, mode)
            self.assertEqual(checked.returncode, 0, output(checked))

    def test_project_below_a_symlinked_ancestor(self) -> None:
        (self.real / "project").mkdir()
        self.init_and_check(self.link / "project")

    def test_project_root_that_is_itself_a_symlink(self) -> None:
        (self.real / "project").mkdir()
        alias = self.tmp / "project-alias"
        alias.symlink_to(self.real / "project", target_is_directory=True)
        self.init_and_check(alias)

    def test_guard_symlinked_task_folder_inside_the_project_is_rejected(self) -> None:
        project = self.real / "project"
        project.mkdir()
        init = run_script(INIT_SCRIPT, project, "--project-name", "Fixture")
        self.assertEqual(init.returncode, 0, output(init))
        outside = self.tmp / "outside"
        outside.mkdir()
        task = project / ACTIVE_TASK
        task.rename(outside / TASK_ID)
        task.symlink_to(outside / TASK_ID, target_is_directory=True)
        checked = run_script(CHECK_SCRIPT, project)
        self.assertEqual(checked.returncode, 1, output(checked))
        self.assertIn("symlink", checked.stdout)

    def test_guard_initializer_refuses_a_symlinked_authority_folder(self) -> None:
        project = self.real / "project"
        project.mkdir()
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        (project / "project").symlink_to(elsewhere, target_is_directory=True)
        init = run_script(INIT_SCRIPT, project, "--project-name", "Fixture")
        self.assertEqual(init.returncode, 2, output(init))
        self.assertFalse((elsewhere / "state.yaml").exists())


if __name__ == "__main__":
    unittest.main()
