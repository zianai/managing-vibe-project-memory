#!/usr/bin/env python3
"""Convenience CLI; protocol text and templates remain directly readable files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = SKILL_ROOT / "assets" / "project-template"
TEMPLATE_FILES = {
    "agents": "AGENTS.md",
    "state": "project/state.yaml",
    "task": "templates/task/task.yaml",
    "decisions": "optional/decisions.md",
    "handoff": "optional/handoff.md",
    "review": "optional/review.md",
    "action": "optional/action-record.md",
}
GUIDE_SECTIONS = (
    "continuity-kernel",
    "human-alignment",
    "visual-alignment",
    "high-impact-actions",
    "parallel-harness",
)


def read_guide(section: str) -> str:
    """Read the same reference an agent can open without executing Python."""
    if section not in GUIDE_SECTIONS:
        raise ValueError(f"unknown guide section: {section}")
    return (SKILL_ROOT / "references" / f"{section}.md").read_text(encoding="utf-8")


def read_template(name: str) -> str:
    """Read the single template source used by humans, agents, and initialization."""
    if name not in TEMPLATE_FILES:
        raise ValueError(f"unknown template: {name}")
    return (TEMPLATE_ROOT / TEMPLATE_FILES[name]).read_text(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Protocol 3.0 project memory. Use COMMAND --help for options."
    )
    parser.add_argument(
        "command", choices=("init", "check", "template", "guide"),
        help="Initialize, validate, print a template, or print a reference.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    command = build_parser().parse_args(arguments[:1]).command
    remaining = arguments[1:]
    if command in {"init", "check"}:
        # These are the actual implementations, not copies or legacy-protocol paths.
        # Do not leave module caches in a user's skill installation during CLI use.
        sys.dont_write_bytecode = True
        if command == "init":
            from init_project_memory import main as initialize_main

            return initialize_main(remaining)
        from check_project_memory import main as check_main

        return check_main(remaining)

    parser = argparse.ArgumentParser(
        prog=f"{Path(sys.argv[0]).name} {command}",
        description="Print a runtime resource to stdout without modifying files.",
    )
    choices = tuple(TEMPLATE_FILES) if command == "template" else GUIDE_SECTIONS
    parser.add_argument("name", choices=choices)
    args = parser.parse_args(remaining)
    try:
        content = read_template(args.name) if command == "template" else read_guide(args.name)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"ERROR cannot read {command} resource: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
