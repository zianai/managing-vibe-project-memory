#!/usr/bin/env python3
"""Protocol 3.0 maintenance commands behind `project_memory.py`.

`subject` prints claim subjects using the checker's own digest code, so a
subject it prints is exactly what the checker recomputes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from check_project_memory import (
    first_symlink_component,
    run_git,
    sha256,
    v3_git_head,
    v3_git_status,
    v3_worktree_digest,
)


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
