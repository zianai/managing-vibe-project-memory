"""Regression tests for the Known Disagreements in references/field-reference.md.

Each class covers one numbered item that changed the checker (1, 6, 8, 9b). Every
test except those named ``test_guard_*`` fails on 17a7ef2 and describes the
target behavior; ``test_guard_*`` tests pin behavior that already worked.

Run from the repository root:

    python3 -m unittest tests.test_known_disagreements -v
"""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

TESTS_ROOT = Path(__file__).resolve().parent
if str(TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTS_ROOT))

from test_review_findings import ACTIVE_TASK, ProjectCase, render_task  # noqa: E402


def sha256_review(artifact: Path, artifact_ref: str, mode: str | None) -> str:
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    mode_line = "" if mode is None else f'mode: "{mode}"\n'
    return (
        "---\n"
        f'task_ref: "{ACTIVE_TASK}/task.yaml"\n'
        f'subject: "sha256:{digest}"\n'
        f'subject_ref: "{artifact_ref}"\n'
        f"{mode_line}"
        "actor_modified_subject: false\n"
        'verdict: "passed"\n'
        "---\n"
        "- Evidence inspected: the exact artifact bytes named by the subject.\n"
        "- Findings: none; the artifact matches the agreed content.\n"
    )


# ---------------------------------------------------------------------------
# 1: a validated review names one of the four review modes
# ---------------------------------------------------------------------------


class ReviewModeTest(ProjectCase):
    def write_review(self, mode: str | None, **task: str) -> None:
        artifact = self.project / "export.txt"
        artifact.write_text("exact reviewed bytes\n", encoding="utf-8")
        (self.task_dir / "review.md").write_text(sha256_review(artifact, "export.txt", mode), encoding="utf-8")
        self.write_task(render_task(review_ref=f"{ACTIVE_TASK}/review.md", **task))

    def test_validated_review_rejects_a_mode_outside_the_vocabulary(self) -> None:
        for mode in ("peer", "Independent_actor", "independent-actor"):
            with self.subTest(mode=mode):
                self.write_review(mode, review_current="true")
                self.assertFailsWith(self.check(), f"invalid review mode '{mode}'")

    def test_validated_review_requires_a_mode(self) -> None:
        self.write_review(None, review_current="true")
        self.assertFailsWith(self.check(), "invalid review mode ''")

    def test_guard_each_listed_mode_passes(self) -> None:
        for mode in ("self_check", "fresh_context", "independent_actor", "human"):
            with self.subTest(mode=mode):
                self.write_review(mode, review_current="true")
                self.assertPasses(self.check())

    def test_guard_a_review_that_is_not_validated_keeps_any_mode(self) -> None:
        self.write_review("peer")
        self.assertPasses(self.check())


# ---------------------------------------------------------------------------
# 6: task-level authorization_basis uses the action-record deny list
# ---------------------------------------------------------------------------


class AuthorizationDenyListTest(ProjectCase):
    def test_task_level_basis_denies_ok_and_yes(self) -> None:
        for basis in ("ok", "yes"):
            with self.subTest(basis=basis):
                self.write_task(render_task(authorization_basis=basis))
                self.assertFailsWith(self.check(), f"'{basis}' cannot establish human authorization")

    def test_guard_task_level_basis_still_denies_okay_and_accepts_a_category(self) -> None:
        self.write_task(render_task(authorization_basis="okay"))
        self.assertFailsWith(self.check(), "'okay' cannot establish human authorization")
        self.write_task(render_task(authorization_basis="direct-human-instruction"))
        self.assertPasses(self.check())


# ---------------------------------------------------------------------------
# 8: handoff_subject_ref has no effect; merge_resolution_subject_ref is an error
# ---------------------------------------------------------------------------


class SubjectRefFieldsTest(ProjectCase):
    def test_handoff_subject_ref_warns_that_it_has_no_effect(self) -> None:
        (self.project / "notes.md").write_text("Context for the next session.\n", encoding="utf-8")
        self.write_task(render_task(handoff_subject_ref="notes.md"))
        result = self.check()
        self.assertPasses(result)
        self.assertIn("WARNING", result.stdout)
        self.assertIn("handoff_subject_ref has no effect", result.stdout)

    def test_guard_handoff_subject_ref_is_still_path_checked(self) -> None:
        self.write_task(render_task(handoff_subject_ref="../outside.md"))
        self.assertEqual(self.check().returncode, 1)

    def test_guard_merge_resolution_subject_ref_is_an_error_once_resolved(self) -> None:
        (self.project / "merge.md").write_text("Combined result of both harness branches.\n", encoding="utf-8")
        self.write_task(
            render_task(integration_status="resolved", merge_resolution_subject_ref="merge.md")
        )
        self.assertFailsWith(self.check(), "merge_resolution_subject_ref cannot substitute a combined source scope")


# ---------------------------------------------------------------------------
# 9b: an unknown risk_reasons value warns that it sets no floor
# ---------------------------------------------------------------------------


class UnknownRiskReasonTest(ProjectCase):
    def test_misspelled_reason_warns_and_names_the_listed_reason(self) -> None:
        self.write_task(render_task(risk_reasons="[publication-or-deploy]"))
        result = self.check()
        self.assertPasses(result)
        self.assertIn("WARNING", result.stdout)
        self.assertIn("'publication-or-deploy' is not a listed reason and sets no risk floor", result.stdout)
        self.assertIn("did you mean 'publication-or-deployment'?", result.stdout)
        self.assertIn("custom-<low|medium|high>:<slug>", result.stdout)

    def test_unrelated_extension_reason_warns_with_the_custom_form(self) -> None:
        self.write_task(render_task(risk_reasons="[vendor-quirk]"))
        result = self.check()
        self.assertPasses(result)
        self.assertIn("'vendor-quirk' is not a listed reason", result.stdout)
        self.assertIn("custom-<low|medium|high>:<slug>", result.stdout)

    def test_guard_listed_and_custom_reasons_do_not_warn(self) -> None:
        self.write_task(render_task(risk="medium", risk_reasons="[local-reversible, custom-medium:vendor-api]"))
        result = self.check()
        self.assertPasses(result)
        self.assertNotIn("WARNING", result.stdout)


if __name__ == "__main__":
    unittest.main()
