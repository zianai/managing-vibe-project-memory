#!/usr/bin/env python3
"""Protocol 3.0 maintenance commands behind `project_memory.py`.

`subject` prints claim subjects using the checker's own digest code, so a
subject it prints is exactly what the checker recomputes. `archive` moves a task
to work/archive/ and rewrites the paths that point into it, with rollback.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from check_project_memory import (
    V3_TASK_NAME_RE,
    first_symlink_component,
    run_git,
    sha256,
    v3_git_head,
    v3_git_status,
    v3_worktree_digest,
)
from flat_yaml import load_flat_yaml


EXIT_OK = 0
EXIT_UNCOMMITTED = 1
EXIT_REFUSED = 2

PLAIN_YAML_PATH_RE = re.compile(r"^[A-Za-z0-9._/@+-]+$")


class Refusal(Exception):
    """A deliberate refusal: exit 2 with the reason, nothing changed."""


class UncommittedPaths(Exception):
    """git was asked for paths that no commit names yet: exit 1."""


def yaml_path(path: str) -> str:
    """Render a path as a flow-list item, quoting it only when needed."""
    return path if PLAIN_YAML_PATH_RE.fullmatch(path) else json.dumps(path, ensure_ascii=False)


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
    if kind == "sha256":
        if len(paths) != 1:
            raise Refusal("a sha256 subject takes exactly one file path")
        path, target = paths[0]
        if not target.exists():
            raise Refusal(f"file does not exist: {path}")
        if not target.is_file():
            raise Refusal(f"not a regular file: {path}")
        return [f'subject: "sha256:{sha256(target)}"', f"subject_ref: {json.dumps(path, ensure_ascii=False)}"]

    head = require_git_repository(project_root)
    for path, target in paths:
        if target.exists() and not target.is_file():
            raise Refusal(f"not a regular file: {path}")
        if not target.exists() and not blob_in_head(project_root, path):
            raise Refusal(f"not a file in the worktree or HEAD: {path}")
    names = [path for path, _ in paths]
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
    return [f'subject: "{value}"', f"subject_paths: [{', '.join(yaml_path(path) for path in names)}]"]


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
    except OSError as exc:
        print(f"ERROR cannot read subject paths: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    print("\n".join(lines))
    return EXIT_OK


# ---------------------------------------------------------------------------
# archive
# ---------------------------------------------------------------------------

REWRITE_SUFFIXES = {".yaml", ".yml", ".md"}


@dataclass
class Rewrite:
    final: Path  # where the file lives after the move
    original: bytes
    updated: bytes


@dataclass
class ArchivePlan:
    source: Path
    destination: Path
    rewrites: list[Rewrite] = field(default_factory=list)
    clears_focus: bool = False
    warnings: list[str] = field(default_factory=list)


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

    plan = ArchivePlan(source=source, destination=destination)
    moved_files = files_below(project_root, source)
    other_files: list[Path] = []
    for child in sorted(active_root.iterdir()):
        if child == source:
            continue
        if child.is_symlink():
            raise Refusal(f"symlink in the archive scope: {child.relative_to(project_root)}")
        other_files.extend(files_below(project_root, child) if child.is_dir() else [child])
    project_dir = project_root / "project"
    if project_dir.is_symlink():
        raise Refusal("symlink in the archive scope: project")
    if project_dir.is_dir():
        other_files.extend(files_below(project_root, project_dir))

    pattern = active_path_pattern(task_id)
    new_prefix = f"work/archive/{task_id}".encode()
    pending: dict[Path, tuple[Path, bytes, bytes]] = {}
    for path in moved_files + other_files:
        if path.suffix.lower() not in REWRITE_SUFFIXES:
            continue
        original = path.read_bytes()
        updated = pattern.sub(new_prefix, original)
        if updated != original:
            final = destination / path.relative_to(source) if path.is_relative_to(source) else path
            pending[path] = (final, original, updated)

    state_path = project_dir / "state.yaml"
    if state_path.is_file():
        try:
            state = load_flat_yaml(state_path)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise Refusal(f"cannot read project/state.yaml: {exc}") from None
        if str(state.get("active_task") or "").strip() == task_id:
            plan.clears_focus = True
            final, original, updated = pending.get(
                state_path, (state_path, state_path.read_bytes(), state_path.read_bytes())
            )
            updated = re.sub(rb"(?m)^active_task:[^\r\n]*", b"active_task: null", updated)
            today = date.today().isoformat().encode()
            updated = re.sub(rb"(?m)^updated:[^\r\n]*", b'updated: "' + today + b'"', updated)
            pending[state_path] = (final, original, updated)

    inside = run_git(project_root, "rev-parse", "--is-inside-work-tree")
    if inside.returncode == 0 and inside.stdout.strip() == b"true":
        if git_dirty(project_root, [f"work/active/{task_id}"]):
            raise Refusal(
                f"work/active/{task_id}/ has uncommitted or untracked changes; commit them first"
            )
        others = [
            path.relative_to(project_root).as_posix()
            for path in pending
            if not path.is_relative_to(source)
        ]
        if others and git_dirty(project_root, others):
            raise Refusal(
                "files that archive would rewrite have uncommitted changes; commit them first: "
                + ", ".join(others)
            )

    plan.rewrites = [Rewrite(final, original, updated) for final, original, updated in pending.values()]
    if archive_root.is_dir():
        for directory, _, filenames in os.walk(archive_root):
            for name in sorted(filenames):
                path = Path(directory) / name
                if path.suffix.lower() in REWRITE_SUFFIXES and not path.is_symlink():
                    try:
                        mentions = pattern.search(path.read_bytes()) is not None
                    except OSError:
                        continue
                    if mentions:
                        plan.warnings.append(
                            f"{path.relative_to(project_root)} mentions work/active/{task_id}; "
                            "archived history is left unchanged"
                        )
    return plan


def overwrite(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "wb", closefd=True) as handle:
        handle.write(payload)


def apply_archive(plan: ArchivePlan) -> None:
    """Move, then rewrite; on any failure restore every byte and move back."""
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
    except BaseException:
        for rewrite in reversed(written):
            try:
                overwrite(rewrite.final, rewrite.original)
            except OSError:
                pass
        if moved:
            try:
                os.rename(plan.destination, plan.source)
            except OSError:
                pass
        if created_archive_root:
            try:
                os.rmdir(archive_root)
            except OSError:
                pass
        raise


def archive_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="project_memory.py archive",
        description=(
            "Move work/active/<task-id> to work/archive/<task-id> and rewrite the paths "
            "that point into it. Never stages or commits."
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
    except OSError as exc:
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
    except OSError as exc:
        print(f"ERROR archive failed and was rolled back: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    print(
        f"Archived {args.task_id}. Next: run `project_memory.py check {project_root} --full`, "
        "then commit the move (archive never stages or commits)."
    )
    return EXIT_OK
