#!/usr/bin/env python3
"""Initialize the protocol 3.0 Minimal Continuity Kernel without overwrites."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = SKILL_ROOT / "assets" / "project-template"
DEFAULT_TASK_ID = "T-001-initial"
TASK_ID_RE = re.compile(
    r"^T-(?:[A-Z][A-Z0-9]{1,11}-\d{3}|\d{3})-[a-z0-9]+(?:-[a-z0-9]+)*$"
)
PLACEHOLDER_RE = re.compile(
    r"\{\{[^}]+\}\}|\b(?:TODO|TBD|FIXME)\b|\bREPLACE[_ -]?(?:ME|THIS|THE|WITH)\b",
    re.IGNORECASE,
)


def read_portable_scalars(path: Path) -> dict[str, object]:
    data: dict[str, object] = {}
    current_list: str | None = None
    ignored_extension = False
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line[:1].isspace():
            if ignored_extension:
                continue
            if raw_line.startswith("  - ") and current_list:
                item = raw_line[4:].strip().strip('"').strip("'")
                value = data.get(current_list)
                if isinstance(value, list):
                    value.append(item)
                continue
            raise ValueError(
                f"unsupported nested core YAML at line {line_number}; use a top-level x_* extension"
            )
        current_list = None
        ignored_extension = False
        if ":" not in raw_line:
            raise ValueError(f"expected key: value at line {line_number}")
        key, value = raw_line.split(":", 1)
        key = key.strip()
        if key in data:
            raise ValueError(f"duplicate key '{key}' at line {line_number}")
        raw_value = value.strip()
        if not raw_value and key.startswith("x_"):
            data[key] = "<nested-extension>"
            ignored_extension = True
            continue
        if not raw_value:
            data[key] = []
            current_list = key
            continue
        scalar = raw_value.strip('"').strip("'")
        if raw_value.startswith("[") and raw_value.endswith("]"):
            inner = raw_value[1:-1].strip()
            parsed = [] if not inner else [
                item.strip().strip('"').strip("'") for item in inner.split(",")
            ]
        elif scalar == "null":
            parsed: object = None
        elif scalar in {"true", "false"}:
            parsed = scalar == "true"
        elif scalar.isdigit():
            parsed = int(scalar)
        else:
            parsed = scalar
        data[key] = parsed
    return data


def protected_path_covers_output(protected: str, output: Path) -> bool:
    candidate = Path(protected)
    if candidate.is_absolute() or ".." in candidate.parts or candidate == Path("."):
        return False
    return candidate == output or candidate in output.parents


def incompatible_existing_authority(
    project_root: Path,
    task_id: str,
    planned_outputs: tuple[Path, ...],
) -> str | None:
    state_path = project_root / "project" / "state.yaml"
    task_path = project_root / "work" / "active" / task_id / "task.yaml"
    for kind, path in (("state", state_path), ("task", task_path)):
        if not path.exists():
            continue
        try:
            record = read_portable_scalars(path)
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            return f"existing {kind} authority is unreadable or malformed: {path.relative_to(project_root)}: {exc}"
        if record.get("schema_version") != 3 or str(record.get("protocol_version") or "") != "3.0":
            return f"existing {kind} authority is incompatible with protocol 3.0: {path.relative_to(project_root)}"
        required = (
            ("project_id", "project_name", "status", "active_task", "updated")
            if kind == "state"
            else (
                "id", "status", "goal", "scope", "non_goals", "acceptance",
                "risk", "risk_reasons", "protected_paths", "context_refs",
                "decision_refs", "evidence_refs", "updated",
            )
        )
        if kind == "task":
            if "result_status" in record:
                return "existing task uses ambiguous result_status; use completion_claim for protocol 3.0"
            if str(record.get("id") or "") != task_id:
                return f"existing task id does not match initialization target: {path.relative_to(project_root)}"
            status = str(record.get("status") or "").strip()
            if not status:
                return f"existing task status is empty: {path.relative_to(project_root)}"
            for field in ("goal", "scope", "acceptance"):
                value = record.get(field)
                values = value if isinstance(value, list) else [value]
                if not any(str(item or "").strip() for item in values):
                    return f"existing task field '{field}' is empty: {path.relative_to(project_root)}"
            if str(record.get("risk") or "") not in {"low", "medium", "high"}:
                return f"existing task risk is invalid: {path.relative_to(project_root)}"
            reasons = record.get("risk_reasons")
            reason_values = reasons if isinstance(reasons, list) else [reasons]
            if not any(str(item or "").strip() for item in reason_values):
                return f"existing task risk_reasons is empty: {path.relative_to(project_root)}"
            core_text = "\n".join(
                str(record.get(key) or "")
                for key in required
                if not key.startswith("x_")
            )
            if PLACEHOLDER_RE.search(core_text) and (
                status != "proposed"
                or record.get("implementation_started") is True
                or record.get("completion_claim") is True
            ):
                return f"placeholder task may only remain proposed: {path.relative_to(project_root)}"
            protected = record.get("protected_paths")
            protected_values = protected if isinstance(protected, list) else [protected]
            for raw_protected in protected_values:
                value = str(raw_protected or "").strip()
                if value and any(
                    protected_path_covers_output(value, output)
                    for output in planned_outputs
                ):
                    return (
                        f"planned initialization output is protected by '{value}'; "
                        "manual merge is required"
                    )
        missing = [key for key in required if key not in record]
        if missing:
            return f"existing {kind} authority is incomplete ({', '.join(missing)}): {path.relative_to(project_root)}"
        if kind == "state":
            if "focus_task" in record:
                return "existing state uses unsupported focus_task alias; protocol 3.0 uses active_task"
            if "protected_paths" in record:
                return "existing state stores protected_paths outside task.yaml"
            active_task = str(record.get("active_task") or "").strip()
            if active_task != task_id:
                return (
                    f"existing state active_task '{active_task or 'null'}' conflicts with initialization task '{task_id}'"
                )
    archived = project_root / "work" / "archive" / task_id
    if archived.exists() or archived.is_symlink():
        return f"task id already exists in work/archive: {task_id}"
    return None


def default_project_id(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()
    return value or "PROJECT"


def render_template(content: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        content = content.replace("{{" + key + "}}", value)
    return content


def first_symlink_component(path: Path) -> Path | None:
    absolute = path.absolute()
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor = cursor / part
        if cursor.is_symlink():
            return cursor
    return None


def first_non_directory_ancestor(path: Path) -> Path | None:
    absolute = path.absolute()
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor = cursor / part
        if cursor.exists() and not cursor.is_dir():
            return cursor
    return None


def unsafe_target_reason(project_root: Path, relative: Path) -> str | None:
    symlink = first_symlink_component(project_root / relative)
    if symlink is not None:
        return f"target path contains symlink component: {symlink}"
    canonical_root = project_root.resolve(strict=False)
    resolved_target = (project_root / relative).resolve(strict=False)
    try:
        resolved_target.relative_to(canonical_root)
    except ValueError:
        return f"target resolves outside selected project root: {relative}"
    cursor = project_root
    for part in relative.parts[:-1]:
        cursor = cursor / part
        if cursor.exists() and not cursor.is_dir():
            return f"target ancestor is not a directory: {cursor}"
    return None


def secure_exclusive_write(target: Path, payload: bytes, created_dirs: list[Path]) -> None:
    """Create one file through no-follow directory descriptors, never overwriting."""
    absolute = target.absolute()
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_fd = os.open(absolute.anchor, directory_flags)
    cursor = Path(absolute.anchor)
    try:
        for part in absolute.parent.parts[1:]:
            next_path = cursor / part
            try:
                child_fd = os.open(part, directory_flags, dir_fd=directory_fd)
            except FileNotFoundError:
                os.mkdir(part, 0o755, dir_fd=directory_fd)
                created_dirs.append(next_path)
                child_fd = os.open(part, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = child_fd
            cursor = next_path
        file_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        file_fd = os.open(absolute.name, file_flags, 0o644, dir_fd=directory_fd)
        try:
            with os.fdopen(file_fd, "wb", closefd=True) as handle:
                handle.write(payload)
        except BaseException:
            try:
                os.unlink(absolute.name, dir_fd=directory_fd)
            except OSError:
                pass
            raise
        return None
    finally:
        os.close(directory_fd)


def adapter_content(adapter: str) -> str:
    title = "Claude" if adapter == "claude" else "Codex"
    return (
        f"# {title} project entry\n\n"
        "Read `AGENTS.md`, then `project/state.yaml`, then the task named by "
        "`active_task`. Treat it as the default recovery focus, not a global lock. "
        "Use the harness's strongest native execution and delegation features inside "
        "the recorded task boundary.\n"
    )


def milestone_files(today: str) -> dict[Path, str]:
    return {
        Path("milestones/M01/milestone.yaml"): (
            'schema_version: 3\nprotocol_version: "3.0"\n'
            'id: M01\nstatus: proposed\ngoal: Define the first project milestone\n'
            f'updated: "{today}"\n'
        ),
        Path("milestones/M01/brief.md"): (
            "# M01\n\nOptional milestone context. Task records remain the execution authority.\n"
        ),
    }


def initialize(
    project_root: Path,
    project_name: str,
    project_id: str,
    task_id: str,
    adapters: tuple[str, ...],
    with_milestones: bool,
    dry_run: bool,
    force: bool = False,
) -> int:
    if not TASK_ID_RE.fullmatch(task_id):
        print(f"ERROR invalid protocol 3.0 task id: {task_id}", file=sys.stderr)
        return 2
    sources = {
        Path("AGENTS.md"): TEMPLATE_ROOT / "AGENTS.md",
        Path("project/state.yaml"): TEMPLATE_ROOT / "project" / "state.yaml",
        Path(f"work/active/{task_id}/task.yaml"): (
            TEMPLATE_ROOT / "templates" / "task" / "task.yaml"
        ),
    }
    missing = [source for source in sources.values() if not source.is_file()]
    if missing:
        print(f"ERROR template file not found: {missing[0]}", file=sys.stderr)
        return 2

    if ".." in project_root.parts:
        print("ERROR selected project root must not contain '..' path traversal", file=sys.stderr)
        return 2
    project_root = project_root.absolute()
    root_symlink = first_symlink_component(project_root)
    if root_symlink is not None:
        print(
            f"ERROR unsafe selected project root: path contains symlink component: {root_symlink}",
            file=sys.stderr,
        )
        return 2
    if project_root.exists() and not project_root.is_dir():
        print(f"ERROR selected project root is not a directory: {project_root}", file=sys.stderr)
        return 2
    root_blocker = first_non_directory_ancestor(project_root)
    if root_blocker is not None:
        print(
            f"ERROR unsafe selected project root: ancestor is not a directory: {root_blocker}",
            file=sys.stderr,
        )
        return 2
    if force:
        print("ERROR --force is not supported; protocol 3.0 initialization never overwrites", file=sys.stderr)
        return 2
    for authority_name in ("project", "work"):
        authority_root = project_root / authority_name
        if not authority_root.is_dir() or authority_root.is_symlink():
            continue
        try:
            descendants = list(authority_root.rglob("*"))
        except OSError as exc:
            print(f"ERROR cannot inspect existing {authority_name} authority: {exc}", file=sys.stderr)
            return 2
        for descendant in descendants:
            if descendant.is_symlink():
                print(
                    f"ERROR existing authority descendant must not be a symlink: {descendant.relative_to(project_root)}",
                    file=sys.stderr,
                )
                return 2

    def yaml_string(value: str) -> str:
        return json.dumps(value, ensure_ascii=False)[1:-1]

    today = date.today().isoformat()
    values = {
        "PROJECT_NAME": yaml_string(project_name),
        "PROJECT_ID": yaml_string(project_id),
        "TASK_ID": task_id,
        "DATE": today,
    }
    generated: dict[Path, str] = {}
    for adapter in adapters:
        relative = Path("CLAUDE.md" if adapter == "claude" else "CODEX.md")
        generated[relative] = adapter_content(adapter)
    if with_milestones:
        generated.update(milestone_files(today))

    targets = [*sources, *generated]
    for relative in targets:
        reason = unsafe_target_reason(project_root, relative)
        if reason:
            print(f"ERROR unsafe initialization target {relative}: {reason}", file=sys.stderr)
            return 2
        target = project_root / relative
        if target.exists() and not target.is_file():
            print(f"ERROR initialization target must be a file: {relative}", file=sys.stderr)
            return 2

    agents_path = project_root / "AGENTS.md"
    if agents_path.is_file():
        try:
            existing_agents = agents_path.read_bytes()
            expected_agents = sources[Path("AGENTS.md")].read_bytes()
        except OSError as exc:
            print(f"ERROR cannot compare existing AGENTS.md contract: {exc}", file=sys.stderr)
            return 2
        if existing_agents != expected_agents:
            print(
                "ERROR existing AGENTS.md is not the exact compatible protocol 3.0 contract; manual merge is required",
                file=sys.stderr,
            )
            return 2

    incompatibility = incompatible_existing_authority(
        project_root,
        task_id,
        tuple(targets),
    )
    if incompatibility:
        print(f"ERROR {incompatibility}", file=sys.stderr)
        return 2

    created_files: list[tuple[Path, bytes]] = []
    created_dirs: list[Path] = []

    def rollback_created() -> None:
        for path, expected in reversed(created_files):
            try:
                if path.is_file() and not path.is_symlink() and path.read_bytes() == expected:
                    path.unlink()
            except OSError:
                pass
        for path in sorted(set(created_dirs), key=lambda item: len(item.parts), reverse=True):
            try:
                path.rmdir()
            except OSError:
                pass

    def fail_after_writes(message: str) -> int:
        rollback_created()
        print(f"ERROR {message}", file=sys.stderr)
        return 2

    print(f"Project root: {project_root}")
    for relative in targets:
        target = project_root / relative
        if target.exists():
            print(f"SKIP {relative}")
            continue
        print(f"CREATE {relative}")
        if dry_run:
            continue
        try:
            content = generated[relative] if relative in generated else sources[relative].read_text(encoding="utf-8")
        except OSError as exc:
            return fail_after_writes(f"cannot read initialization source for {relative}: {exc}")
        reason = unsafe_target_reason(project_root, relative)
        if reason:
            return fail_after_writes(f"unsafe initialization target {relative}: {reason}")
        rendered = render_template(content, values)
        rendered_bytes = rendered.encode("utf-8")
        try:
            secure_exclusive_write(target, rendered_bytes, created_dirs)
            created_files.append((target, rendered_bytes))
        except FileExistsError:
            return fail_after_writes(
                f"initialization target appeared concurrently; refusing overwrite: {relative}"
            )
        except OSError as exc:
            return fail_after_writes(f"cannot create initialization target {relative}: {exc}")

    print("Project memory initialization complete")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Initialize the protocol 3.0 Minimal Continuity Kernel."
    )
    parser.add_argument("project_root", nargs="?", default=".")
    parser.add_argument("--project-name")
    parser.add_argument("--project-id")
    parser.add_argument("--task-id", default=DEFAULT_TASK_ID)
    parser.add_argument(
        "--adapter",
        action="append",
        choices=("claude", "codex"),
        default=[],
        help="Add a thin harness entry pointer; may be repeated.",
    )
    parser.add_argument("--with-milestones", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Deprecated safety trap: v3 never overwrites existing files.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing files.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    project_root = Path(args.project_root)
    project_name = args.project_name or project_root.absolute().name
    project_id = args.project_id or default_project_id(project_name)
    return initialize(
        project_root,
        project_name,
        project_id,
        args.task_id,
        tuple(dict.fromkeys(args.adapter)),
        args.with_milestones,
        args.dry_run,
        args.force,
    )


if __name__ == "__main__":
    raise SystemExit(main())
