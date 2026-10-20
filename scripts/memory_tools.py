#!/usr/bin/env python3
"""Protocol 3.0 maintenance commands behind `project_memory.py`.

`subject` prints claim subjects using the checker's own digest code, so a
subject it prints is exactly what the checker recomputes. `archive` moves a task
to work/archive/ and rewrites the protocol records that point into it, with
rollback.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shlex
import stat
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

from check_project_memory import (
    CONTINUITY_KERNEL_PROTOCOL,
    GIT_COMMIT_RE,
    V3_TASK_NAME_RE,
    GitUnavailable,
    as_list,
    first_symlink_component,
    run_git,
    sha256,
    v3_git_head,
    v3_git_ignored,
    v3_git_status,
    v3_project_relative_path,
    v3_review_required,
    v3_worktree_digest,
)
from flat_yaml import parse_flat_yaml_text, parse_scalar


EXIT_OK = 0
EXIT_UNCOMMITTED = 1
EXIT_REFUSED = 2
EXIT_ROLLBACK_INCOMPLETE = 3

PLAIN_YAML_PATH_RE = re.compile(r"^[A-Za-z0-9._/@+-]+$")


class Refusal(Exception):
    """A deliberate refusal: exit 2 with the reason, nothing changed."""


class UncommittedPaths(Exception):
    """git was asked for paths that no commit names yet: exit 1."""


def yaml_path(path: str) -> str:
    """Render a path as a flow-list item, quoting it unless it reads back as the same string.

    `001`, `true` and `null` are plain-safe characters but parse as a number,
    boolean and null, so they are quoted.
    """
    if PLAIN_YAML_PATH_RE.fullmatch(path) and parse_scalar(path) == path:
        return path
    return json.dumps(path, ensure_ascii=False)


def resolve_project_root(raw: str) -> Path:
    root = Path(raw)
    if not root.is_dir():
        raise Refusal(f"project root does not exist: {raw}")
    return root.absolute().resolve()


def contained_path(project_root: Path, raw: str) -> tuple[str, Path]:
    """Return (project-relative posix path, absolute path) or refuse."""
    candidate = Path(raw)
    if candidate.is_absolute():
        raise Refusal(f"absolute path is not allowed; use a project-relative path: {raw}")
    if ".." in candidate.parts:
        raise Refusal(f"path points outside the project ('..' is not allowed): {raw}")
    if candidate == Path("."):
        raise Refusal("the project root itself is not a subject path")
    target = project_root / candidate
    try:
        target.resolve(strict=False).relative_to(project_root)
    except ValueError:
        raise Refusal(f"path resolves outside the project: {raw}") from None
    symlink = first_symlink_component(project_root, target)
    if symlink is not None:
        raise Refusal(f"path traverses a symlink: {symlink.relative_to(project_root)}")
    return candidate.as_posix(), target


def require_git_repository(project_root: Path) -> str:
    inside = run_git(project_root, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != b"true":
        raise Refusal(f"no git repository at {project_root}; use a sha256 subject for a single file")
    head = v3_git_head(project_root)
    if head is None:
        raise Refusal("the git repository has no commit yet; commit first or use a sha256 subject")
    return head


def blob_in_head(project_root: Path, path: str) -> bool:
    # "./" makes the path relative to the project root even inside a larger repository.
    result = run_git(project_root, "cat-file", "-t", f"HEAD:./{path}")
    return result.returncode == 0 and result.stdout.strip() == b"blob"


def subject_lines(project_root: Path, kind: str, raw_paths: list[str]) -> list[str]:
    paths = [contained_path(project_root, raw) for raw in raw_paths]
    for path, _ in paths:
        if "#" in path:
            # The checker reads `#` in a reference as the start of a fragment.
            raise Refusal(f"path contains '#', which the checker reads as a #fragment: {path}; rename the file to bind it")
    if kind == "sha256":
        if len(paths) != 1:
            raise Refusal("a sha256 subject takes exactly one file path")
        path, target = paths[0]
        if not target.exists():
            raise Refusal(f"file does not exist: {path}")
        if not target.is_file():
            raise Refusal(f"not a regular file: {path}")
        value = f"sha256:{sha256(target)}"
        lines = [f'subject: "{value}"', f"subject_ref: {json.dumps(path, ensure_ascii=False)}"]
        return checked_round_trip(lines, {"subject": value, "subject_ref": path})

    head = require_git_repository(project_root)
    for path, target in paths:
        if target.exists() and not target.is_file():
            raise Refusal(f"not a regular file: {path}")
        if not target.exists() and not blob_in_head(project_root, path):
            raise Refusal(f"not a file in the worktree or HEAD: {path}")
    names = [path for path, _ in paths]
    ignored = v3_git_ignored(project_root, names)
    if ignored is None:
        raise Refusal("cannot read git's ignore rules")
    if ignored:
        raise Refusal(
            f"git ignores {', '.join(ignored)}, so no git or worktree subject covers its bytes; "
            f"use a sha256 subject for a single file: project_memory.py subject {project_root} sha256 <path>"
        )
    if kind == "git":
        dirty = [path for path in names if not blob_in_head(project_root, path)]
        status = v3_git_status(project_root, *names)
        if status is None:
            raise Refusal("cannot read git status")
        if status or dirty:
            raise UncommittedPaths(
                "paths have uncommitted or untracked changes, so no commit names them yet; "
                "commit first, or use a worktree subject: "
                f"project_memory.py subject {project_root} worktree {' '.join(names)}"
            )
        value = f"git:{head}"
    else:
        digest = v3_worktree_digest(project_root, names)
        if digest is None:
            raise Refusal("cannot compute the worktree digest from git")
        value = f"worktree:{digest}"
    lines = [f'subject: "{value}"', f"subject_paths: [{', '.join(yaml_path(path) for path in names)}]"]
    return checked_round_trip(lines, {"subject": value, "subject_paths": names})


def checked_round_trip(lines: list[str], expected: dict[str, Any]) -> list[str]:
    """Refuse output that the checker's parser would not read back exactly."""
    try:
        parsed = parse_flat_yaml_text("\n".join(lines))
    except ValueError as exc:
        raise Refusal(f"cannot write these paths as flat YAML: {exc}") from None
    if parsed != expected:
        raise Refusal("cannot write these paths so that the checker reads them back unchanged")
    return lines


def subject_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="project_memory.py subject",
        description=(
            "Print the subject lines to paste into handoff, review, or action-record "
            "front matter. Read-only: writes no files and changes no git state."
        ),
    )
    parser.add_argument("project_root")
    parser.add_argument(
        "kind",
        choices=("git", "worktree", "sha256"),
        help="git: committed paths; worktree: uncommitted paths; sha256: one artifact file",
    )
    parser.add_argument("paths", nargs="+", metavar="path", help="project-relative path")
    args = parser.parse_args(argv)
    try:
        project_root = resolve_project_root(args.project_root)
        lines = subject_lines(project_root, args.kind, args.paths)
    except UncommittedPaths as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return EXIT_UNCOMMITTED
    except Refusal as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except GitUnavailable as exc:
        print(f"ERROR git and worktree subjects need git: {exc}; use a sha256 subject for a single file", file=sys.stderr)
        return EXIT_REFUSED
    except OSError as exc:
        print(f"ERROR cannot read subject paths: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    print("\n".join(lines))
    return EXIT_OK


# ---------------------------------------------------------------------------
# archive
# ---------------------------------------------------------------------------
#
# archive edits only protocol records: project/state.yaml, each active task's
# task.yaml, and the front matter of the handoff, review and action records a
# task references. Other files (artifacts, notes, decisions) keep their bytes,
# so digests bound to them stay valid; a WARNING names any that still mention
# the old path. Everything that could break a protection or a claim is refused
# while planning, before any write.

TEXT_SUFFIXES = {".yaml", ".yml", ".md"}
YAML_SUFFIXES = {".yaml", ".yml"}


@dataclass
class Rewrite:
    path: Path  # where the file lives before the move
    final: Path  # where the file lives after the move
    original: bytes
    updated: bytes


@dataclass
class ArchivePlan:
    project_root: Path
    source: Path
    destination: Path
    in_git: bool = False
    rewrites: list[Rewrite] = field(default_factory=list)
    clears_focus: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class TaskView:
    """One active task as the checker reads it."""

    directory: Path
    task_file: Path
    task: dict[str, Any]
    records: list[Path]  # handoff, review and action records the task references
    claims: list[tuple[str, dict[str, Any]]]  # (label, front matter) of the claims the checker validates


class RollbackIncomplete(Exception):
    """A failed archive whose rollback could not restore everything."""

    def __init__(self, cause: BaseException, problems: list[str], backup: Path | None, backup_error: str | None):
        super().__init__(str(cause))
        self.cause = cause
        self.problems = problems
        self.backup = backup
        self.backup_error = backup_error


def active_path_pattern(task_id: str) -> re.Pattern[bytes]:
    """work/active/<id> not followed by an id character, so T-001-x never matches T-001-x-v2."""
    return re.compile(re.escape(f"work/active/{task_id}".encode()) + rb"(?![A-Za-z0-9._-])")


def files_below(project_root: Path, folder: Path) -> list[Path]:
    """Every file below folder; refuse if any entry is a symlink."""

    def unreadable(error: OSError) -> None:
        raise Refusal(f"cannot inspect {error.filename}: {error.strerror}")

    found: list[Path] = []
    for directory, dirnames, filenames in os.walk(folder, onerror=unreadable):
        for name in sorted(dirnames + filenames):
            path = Path(directory) / name
            if path.is_symlink():
                raise Refusal(f"symlink in the archive scope: {path.relative_to(project_root)}")
        found.extend(Path(directory) / name for name in sorted(filenames))
    return found


def git_dirty(project_root: Path, paths: list[str]) -> bool:
    status = v3_git_status(project_root, *paths)
    if status is None:
        raise Refusal("cannot read git status")
    return bool(status)


def git_tracked(project_root: Path, paths: list[str]) -> set[str]:
    result = run_git(project_root, "ls-files", "-z", "--", *paths)
    if result.returncode != 0:
        raise Refusal("cannot read the git index")
    return {name.decode("utf-8", errors="surrogateescape") for name in result.stdout.split(b"\0") if name}


def inside_git_worktree(project_root: Path) -> bool:
    try:
        inside = run_git(project_root, "rev-parse", "--is-inside-work-tree")
    except GitUnavailable as exc:
        if any((directory / ".git").exists() for directory in (project_root, *project_root.parents)):
            raise Refusal(f"{exc}; archive needs git to check this repository for uncommitted changes") from None
        return False
    return inside.returncode == 0 and inside.stdout.strip() == b"true"


def front_matter_end(data: bytes) -> int | None:
    """Byte offset just past a Markdown record's closing '---' line, or None."""
    lines = data.splitlines(keepends=True)
    if not lines or lines[0].strip() != b"---":
        return None
    offset = len(lines[0])
    for line in lines[1:]:
        offset += len(line)
        if line.strip() == b"---":
            return offset
    return None


def record_fields(path: Path, data: bytes) -> dict[str, Any]:
    """The flat YAML fields of a record: a whole .yaml file or a Markdown front matter."""
    text = data.decode("utf-8")
    if path.suffix.lower() in YAML_SUFFIXES:
        return parse_flat_yaml_text(text)
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = next((index for index, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None:
        raise ValueError("unclosed YAML front matter")
    return parse_flat_yaml_text("\n".join(lines[1:end]))


def rewrite_record(path: Path, data: bytes, pattern: re.Pattern[bytes], new_prefix: bytes) -> bytes:
    """Rewrite the path only in record fields: a whole .yaml record, or a Markdown front matter."""
    if path.suffix.lower() in YAML_SUFFIXES:
        return pattern.sub(new_prefix, data)
    if path.suffix.lower() == ".md":
        end = front_matter_end(data)
        if end is not None:
            return pattern.sub(new_prefix, data[:end]) + data[end:]
    return data


def load_protocol_record(project_root: Path, path: Path) -> dict[str, Any]:
    label = path.relative_to(project_root).as_posix()
    if path.is_symlink() or not path.is_file():
        raise Refusal(f"{label} is missing; archive needs every active protocol record")
    try:
        record = record_fields(path, path.read_bytes())
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise Refusal(f"cannot read {label}: {exc}") from None
    if record.get("schema_version") != 3 or str(record.get("protocol_version") or "") != CONTINUITY_KERNEL_PROTOCOL:
        raise Refusal(f'{label} is not schema_version: 3 / protocol_version: "3.0"; archive edits no other version')
    return record


def resolve_ref(project_root: Path, value: Any) -> Path | None:
    """The file a reference names, by the checker's rules, or None (the checker reports why)."""
    if value is None or not str(value).strip():
        return None
    return v3_project_relative_path(project_root, value, "ref", [])


def read_task(project_root: Path, directory: Path) -> TaskView:
    task_file = directory / "task.yaml"
    task = load_protocol_record(project_root, task_file)
    label = task_file.relative_to(project_root).as_posix()
    if str(task.get("id") or "").strip() != directory.name:
        raise Refusal(f"{label}: id does not match its folder name")
    view = TaskView(directory, task_file, task, [], [])
    references = [("handoff_ref", task.get("handoff_ref")), ("review_ref", task.get("review_ref"))]
    references += [(f"action_refs[{index}]", value) for index, value in enumerate(as_list(task.get("action_refs")))]
    for name, value in references:
        path = resolve_ref(project_root, value)
        if path is None:
            continue
        view.records.append(path)
        if name == "handoff_ref":
            validated = task.get("handoff_current") is True
        elif name == "review_ref":
            validated = v3_review_required(task)
        else:
            validated = True  # every action record is validated
        if validated:
            try:
                view.claims.append((f"{label}:{name}", record_fields(path, path.read_bytes())))
            except (OSError, UnicodeDecodeError, ValueError) as exc:
                raise Refusal(f"cannot read {path.relative_to(project_root)}: {exc}") from None
    return view


def claim_bindings(project_root: Path, view: TaskView) -> list[tuple[str, str, Path]]:
    """(claim label, kind, file) for every file a validated claim binds.

    kind "bytes": a sha256 subject, still verified for archived tasks.
    kind "content": a git/worktree subject path, whose path and bytes must both
    stay put while the claim is current.
    """
    bindings: list[tuple[str, str, Path]] = []

    def add(label: str, subject: Any, subject_ref: Any, subject_paths: Any) -> None:
        value = str(subject or "").strip().lower()
        if value.startswith("sha256:"):
            path = resolve_ref(project_root, subject_ref)
            if path is not None:
                bindings.append((label, "bytes", path))
        elif value.startswith(("git:", "worktree:", "patch:")) or GIT_COMMIT_RE.fullmatch(value):
            for item in as_list(subject_paths):
                if isinstance(item, str) and item.strip():
                    bindings.append((label, "content", project_root / item.strip()))

    for label, front in view.claims:
        add(label, front.get("subject"), front.get("subject_ref"), front.get("subject_paths"))
    task = view.task
    label = view.task_file.relative_to(project_root).as_posix()
    if str(task.get("conformance_status") or "") in {"matched", "differences_accepted"}:
        add(f"{label}:approved_baseline_subject", task.get("approved_baseline_subject"), task.get("approved_baseline_ref"), None)
        add(
            f"{label}:implementation_render_subject",
            task.get("implementation_render_subject"),
            task.get("implementation_render_ref"),
            None,
        )
    if str(task.get("integration_status") or "").strip().lower() in {"resolved", "merged"}:
        add(
            f"{label}:merge_resolution_subject",
            task.get("merge_resolution_subject"),
            None,
            task.get("merge_resolution_subject_paths"),
        )
    return bindings


def archived_references(project_root: Path, archive_root: Path, old_prefix: str) -> list[str]:
    """References from archived records that the checker resolves and that point at old_prefix."""
    found: list[str] = []
    if not archive_root.is_dir():
        return found

    def scan(label: str, record: dict[str, Any]) -> None:
        for key, value in record.items():
            if key.startswith("x_"):
                continue
            if key.endswith("_ref"):
                items = [(key, value)]
            elif key.endswith("_refs"):
                items = [(f"{key}[{index}]", item) for index, item in enumerate(as_list(value))]
            else:
                continue
            for name, item in items:
                target = str(item or "").strip().split("#", 1)[0]
                if target == old_prefix or target.startswith(old_prefix + "/"):
                    found.append(f"{label}:{name} -> {item}")

    for directory in sorted(archive_root.iterdir()):
        task_file = directory / "task.yaml"
        if directory.is_symlink() or not directory.is_dir() or task_file.is_symlink() or not task_file.is_file():
            continue
        try:
            task = record_fields(task_file, task_file.read_bytes())
        except (OSError, UnicodeDecodeError, ValueError):
            continue  # the checker reports a malformed archived task on its own
        label = task_file.relative_to(project_root).as_posix()
        scan(label, task)
        claims = []
        if task.get("handoff_current") is True:
            claims.append(task.get("handoff_ref"))
        if v3_review_required(task):
            claims.append(task.get("review_ref"))
        claims.extend(as_list(task.get("action_refs")))
        for value in claims:
            path = resolve_ref(project_root, value)
            if path is None:
                continue
            try:
                scan(path.relative_to(project_root).as_posix(), record_fields(path, path.read_bytes()))
            except (OSError, UnicodeDecodeError, ValueError):
                continue
    return found


def protection_covers(protected: str, path: PurePosixPath) -> bool:
    candidate = PurePosixPath(protected)
    return candidate == path or candidate in path.parents


def plan_archive(project_root: Path, task_id: str) -> ArchivePlan:
    if not V3_TASK_NAME_RE.fullmatch(task_id):
        raise Refusal(f"invalid task id: {task_id}")
    active_root = project_root / "work" / "active"
    archive_root = project_root / "work" / "archive"
    source = active_root / task_id
    destination = archive_root / task_id
    for path in (source, destination):
        symlink = first_symlink_component(project_root, path)
        if symlink is not None:
            raise Refusal(f"symlink in the archive path: {symlink.relative_to(project_root)}")
    if not source.is_dir():
        raise Refusal(f"task {task_id} not found: work/active/{task_id} is not a folder")
    if destination.exists():
        raise Refusal(f"work/archive/{task_id} already exists")
    if archive_root.exists() and not archive_root.is_dir():
        raise Refusal("work/archive exists but is not a folder")

    def relative(path: Path) -> str:
        return path.relative_to(project_root).as_posix()

    def final_path(path: Path) -> Path:
        return destination / path.relative_to(source) if path.is_relative_to(source) else path

    plan = ArchivePlan(project_root=project_root, source=source, destination=destination)
    plan.in_git = inside_git_worktree(project_root)

    # Versions and authority first: archive edits only schema 3 / protocol 3.0 records.
    project_dir = project_root / "project"
    if project_dir.is_symlink():
        raise Refusal("symlink in the archive scope: project")
    state_path = project_dir / "state.yaml"
    state = load_protocol_record(project_root, state_path)
    moved_files = files_below(project_root, source)
    scanned: list[Path] = list(moved_files)
    views: list[TaskView] = []
    for child in sorted(active_root.iterdir()):
        if child.is_symlink():
            raise Refusal(f"symlink in the archive scope: {relative(child)}")
        if not child.is_dir():
            scanned.append(child)
            continue
        if child != source:
            scanned.extend(files_below(project_root, child))
        views.append(read_task(project_root, child))
    if project_dir.is_dir():
        scanned.extend(files_below(project_root, project_dir))

    # The rewrite set: protocol records that mention the old path.
    pattern = active_path_pattern(task_id)
    old_prefix = f"work/active/{task_id}"
    new_prefix = f"work/archive/{task_id}".encode()
    candidates = [state_path] + [path for view in views for path in (view.task_file, *view.records)]
    plan.clears_focus = str(state.get("active_task") or "").strip() == task_id
    rewrites: dict[Path, Rewrite] = {}
    for path in dict.fromkeys(candidates):
        if path.is_relative_to(archive_root):
            continue  # archived history is never edited
        label = relative(path)
        try:
            original = path.read_bytes()
        except OSError as exc:
            raise Refusal(f"cannot read {label}: {exc}") from None
        updated = rewrite_record(path, original, pattern, new_prefix)
        if path == state_path and plan.clears_focus:
            updated, count = re.subn(rb"(?m)^active_task[ \t]*:[^\r\n]*", b"active_task: null", updated)
            if count != 1:
                raise Refusal(f"cannot find exactly one active_task line to clear in {label}")
            today = date.today().isoformat().encode()
            updated = re.sub(rb"(?m)^updated[ \t]*:[^\r\n]*", b'updated: "' + today + b'"', updated)
        if updated == original:
            continue
        try:
            before, after = record_fields(path, original), record_fields(path, updated)
        except (UnicodeDecodeError, ValueError) as exc:
            raise Refusal(f"cannot safely rewrite {label}: {exc}") from None
        focus_kept = path == state_path and plan.clears_focus and after.get("active_task") is not None
        if before.keys() != after.keys() or focus_kept:
            raise Refusal(f"cannot safely rewrite {label}: the rewritten record does not read back as intended")
        symlink = first_symlink_component(project_root, path)
        if symlink is not None:
            raise Refusal(f"symlink in the archive scope: {relative(symlink)}")
        rewrites[path] = Rewrite(path, final_path(path), original, updated)
    plan.rewrites = list(rewrites.values())

    # The protected_paths of every active task, the archived one included, cover the move and the rewrites.
    moved_folder = PurePosixPath(relative(source))
    for view in views:
        for raw in as_list(view.task.get("protected_paths")):
            protected = str(raw or "").strip()
            if not protected:
                continue
            touched = [("move", moved_folder)] if (
                protection_covers(protected, moved_folder) or PurePosixPath(protected).is_relative_to(moved_folder)
            ) else []
            touched += [
                ("rewrite", PurePosixPath(relative(path))) for path in rewrites
                if protection_covers(protected, PurePosixPath(relative(path)))
            ]
            if touched:
                action, path = touched[0]
                raise Refusal(
                    f"archive would {action} {path}, which {relative(view.task_file)} protects "
                    f"(protected_paths: {protected}); remove that protection first if this is intended"
                )

    # Claims that would stop matching what they bind. The archived task's claims become
    # history, where only sha256 subjects are still compared with the file.
    for view in views:
        historical = view.directory == source
        for label, kind, path in claim_bindings(project_root, view):
            if path in rewrites and (kind == "bytes" or not historical):
                raise Refusal(
                    f"archiving would invalidate {label}: its subject binds {relative(path)}, "
                    "which archive would rewrite; refresh or retire that claim first"
                )
            if kind == "content" and not historical and path.is_relative_to(source):
                raise Refusal(
                    f"archiving would invalidate {label}: its subject binds {relative(path)}, "
                    "which archive would move; refresh or retire that claim first"
                )

    broken = archived_references(project_root, archive_root, old_prefix)
    if broken:
        raise Refusal(
            "archived records reference files archive would move, and archived history is never edited: "
            + "; ".join(broken)
            + ". Point those references at files that stay in place first"
        )

    if plan.in_git:
        if git_dirty(project_root, [relative(source)]):
            raise Refusal(f"work/active/{task_id}/ has uncommitted or untracked changes; commit them first")
        rewrite_names = [relative(path) for path in rewrites]
        if rewrite_names:
            tracked = git_tracked(project_root, rewrite_names)
            untracked = [name for name in rewrite_names if name not in tracked]
            if untracked:
                raise Refusal(
                    "files archive would rewrite are not tracked by git (untracked or ignored), "
                    "so git could not restore them: " + ", ".join(untracked)
                )
            others = [relative(path) for path in rewrites if not path.is_relative_to(source)]
            if others and git_dirty(project_root, others):
                raise Refusal(
                    "files that archive would rewrite have uncommitted changes; commit them first: "
                    + ", ".join(others)
                )

    for path in scanned:
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        rewrite = rewrites.get(path)
        try:
            data = rewrite.updated if rewrite else path.read_bytes()
        except OSError:
            continue
        if pattern.search(data):
            plan.warnings.append(
                f"{relative(final_path(path))} mentions {old_prefix} outside the record fields archive rewrites; "
                "left unchanged"
            )
    if archive_root.is_dir():
        for directory, _, filenames in os.walk(archive_root):
            for name in sorted(filenames):
                path = Path(directory) / name
                if path.suffix.lower() in TEXT_SUFFIXES and not path.is_symlink():
                    try:
                        mentions = pattern.search(path.read_bytes()) is not None
                    except OSError:
                        continue
                    if mentions:
                        plan.warnings.append(
                            f"{relative(path)} mentions {old_prefix}; archived history is left unchanged"
                        )
    return plan


def overwrite(path: Path, payload: bytes) -> None:
    """Replace a file's bytes atomically: write a sibling temporary file, then rename it over the file."""
    mode = stat.S_IMODE(os.lstat(path).st_mode)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def save_originals(project_root: Path, rewrites: list[Rewrite]) -> tuple[Path | None, str | None]:
    """Copy original bytes outside the project so an unrestored file can be recovered by hand."""
    try:
        backup = Path(tempfile.mkdtemp(prefix="project-memory-archive-"))
        for rewrite in rewrites:
            target = backup / rewrite.path.relative_to(project_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(rewrite.original)
    except OSError as exc:
        return None, str(exc)
    return backup, None


def apply_archive(plan: ArchivePlan) -> None:
    """Move, then rewrite; on failure restore and verify every byte, then move back."""
    archive_root = plan.destination.parent
    created_archive_root = False
    moved = False
    written: list[Rewrite] = []
    try:
        if not archive_root.exists():
            os.mkdir(archive_root, 0o755)
            created_archive_root = True
        os.rename(plan.source, plan.destination)
        moved = True
        for rewrite in plan.rewrites:
            written.append(rewrite)
            overwrite(rewrite.final, rewrite.updated)
    except BaseException as exc:
        unrestored: list[Rewrite] = []
        for rewrite in reversed(written):
            with contextlib.suppress(OSError):
                overwrite(rewrite.final, rewrite.original)
            try:
                restored = rewrite.final.read_bytes() == rewrite.original
            except OSError:
                restored = False
            if not restored:
                unrestored.append(rewrite)
        problems: list[str] = []
        moved_back = not moved
        if moved:
            try:
                os.rename(plan.destination, plan.source)
                moved_back = True
            except OSError as error:
                problems.append(
                    f"{plan.destination.relative_to(plan.project_root)} could not be moved back to "
                    f"{plan.source.relative_to(plan.project_root)}: {error}"
                )
        if created_archive_root and moved_back:
            with contextlib.suppress(OSError):
                os.rmdir(archive_root)
        for rewrite in unrestored:
            location = rewrite.path if moved_back else rewrite.final
            problems.append(f"{location.relative_to(plan.project_root)} does not have its original bytes")
        if problems:
            backup, backup_error = save_originals(plan.project_root, unrestored) if unrestored else (None, None)
            raise RollbackIncomplete(exc, problems, backup, backup_error) from exc
        raise


def archive_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="project_memory.py archive",
        description=(
            "Move work/active/<task-id> to work/archive/<task-id> and rewrite the protocol "
            "records that point into it. Never stages or commits."
        ),
    )
    parser.add_argument("project_root")
    parser.add_argument("task_id")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without changing files.")
    args = parser.parse_args(argv)
    try:
        project_root = resolve_project_root(args.project_root)
        plan = plan_archive(project_root, args.task_id)
    except Refusal as exc:
        print(f"ERROR {exc}; nothing changed", file=sys.stderr)
        return EXIT_REFUSED
    except (OSError, GitUnavailable) as exc:
        print(f"ERROR cannot plan the archive: {exc}; nothing changed", file=sys.stderr)
        return EXIT_REFUSED

    def relative(path: Path) -> str:
        return path.relative_to(project_root).as_posix()

    print(f"MOVE {relative(plan.source)} -> {relative(plan.destination)}")
    for rewrite in plan.rewrites:
        print(f"REWRITE {relative(rewrite.final)}")
    if plan.clears_focus:
        print("STATE active_task -> null")
    for warning in plan.warnings:
        print(f"WARNING {warning}")
    if args.dry_run:
        print("Dry run: nothing changed")
        return EXIT_OK
    try:
        apply_archive(plan)
    except RollbackIncomplete as exc:
        print(f"ERROR archive failed ({exc.cause}) and could not roll back completely:", file=sys.stderr)
        for problem in exc.problems:
            print(f"RESIDUE {problem}", file=sys.stderr)
        if exc.backup is not None:
            print(f"BACKUP original bytes of the unrestored files are in {exc.backup}", file=sys.stderr)
        elif exc.backup_error is not None:
            print(f"BACKUP could not save the original bytes: {exc.backup_error}", file=sys.stderr)
        if plan.in_git:
            print(
                "Files archive rewrites are tracked and committed, so `git restore` can also recover them.",
                file=sys.stderr,
            )
        return EXIT_ROLLBACK_INCOMPLETE
    except OSError as exc:
        print(f"ERROR archive failed and was rolled back: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    print(f"Archived {args.task_id}. Next: run `project_memory.py check {project_root} --full`.")
    if plan.in_git:
        staged = [relative(plan.source), relative(plan.destination)]
        staged += [relative(rewrite.final) for rewrite in plan.rewrites if not rewrite.final.is_relative_to(plan.destination)]
        print("archive never stages or commits. Stage exactly its changes, then commit:")
        print(f"  git -C {shlex.quote(str(project_root))} add -A -- {' '.join(shlex.quote(path) for path in staged)}")
    return EXIT_OK
