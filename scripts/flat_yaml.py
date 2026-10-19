#!/usr/bin/env python3
"""The flat YAML subset shared by the protocol 3.0 initializer and checker.

Supported: top-level ``key: value`` scalars, flow lists (``[a, "b, c"]``),
block lists directly under an empty ``key:`` (items at column 0 or indented),
``#`` comments outside quotes, and nested top-level ``x_*`` extensions, which
are skipped. Anything else (nested mappings, block scalars) is rejected with a
clear message rather than misread.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any


BLOCK_SCALAR_RE = re.compile(r"[|>][+-]?[1-9]?[+-]?")
NESTED_EXTENSION = "<nested-extension>"


def quoted_end(text: str, start: int) -> int:
    """Return the index just past the quoted string opening at ``start``, or -1."""
    quote = text[start]
    index = start + 1
    while index < len(text):
        char = text[index]
        if quote == '"' and char == "\\":
            index += 2
            continue
        if char == quote:
            if quote == "'" and text[index + 1 : index + 2] == "'":
                index += 2
                continue
            return index + 1
        index += 1
    return -1


def opens_quote(text: str, index: int) -> bool:
    """A quote opens a quoted token only at the start of a value or flow item."""
    if text[index] not in "\"'":
        return False
    before = text[:index].rstrip()
    return not before or before[-1] in "[,"


def strip_comment(text: str) -> str:
    """Drop a ``#`` comment that starts after whitespace and outside quotes."""
    index = 0
    while index < len(text):
        if opens_quote(text, index):
            end = quoted_end(text, index)
            if end < 0:
                break
            index = end
            continue
        if text[index] == "#" and (index == 0 or text[index - 1] in " \t"):
            return text[:index].rstrip()
        index += 1
    return text.rstrip()


def split_flow_items(body: str) -> list[str]:
    """Split a flow-list body on commas outside quotes."""
    items: list[str] = []
    start = 0
    index = 0
    while index < len(body):
        if opens_quote(body, index):
            end = quoted_end(body, index)
            if end < 0:
                break
            index = end
            continue
        if body[index] == ",":
            items.append(body[start:index].strip())
            start = index + 1
        index += 1
    items.append(body[start:].strip())
    if items and not items[-1]:
        items.pop()  # a trailing comma is allowed
    return items


def parse_scalar(raw: str) -> Any:
    value = raw.strip()
    lowered = value.lower()
    if lowered in {"null", "~", ""}:
        return None
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if value.startswith("[") and value.endswith("]"):
        body = value[1:-1].strip()
        if not body:
            return []
        return [parse_scalar(part) for part in split_flow_items(body)]
    if value[:1] in "\"'" and quoted_end(value, 0) == len(value):
        if value[0] == "'":
            return value[1:-1].replace("''", "'")
        try:
            return ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return value[1:-1]
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def parse_flat_yaml_text(content: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_list: str | None = None
    ignored_extension: str | None = None
    for line_number, raw_line in enumerate(content.splitlines(), 1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indented = raw_line[:1].isspace()
        is_item = stripped == "-" or stripped.startswith("- ")
        if ignored_extension is not None and (indented or is_item):
            continue
        if current_list is not None and is_item:
            item = strip_comment(stripped[1:])
            if BLOCK_SCALAR_RE.fullmatch(item.strip()):
                raise ValueError(
                    f"block scalars (| or >) are not supported at line {line_number}; "
                    "write the item on one line"
                )
            data[current_list].append(parse_scalar(item))
            continue
        if indented:
            raise ValueError(
                f"unsupported nested core YAML at line {line_number}; "
                "use a top-level x_* extension or a referenced native file"
            )
        if is_item:
            raise ValueError(
                f"list item at line {line_number} must directly follow an empty 'key:' line"
            )
        ignored_extension = None
        current_list = None
        if ":" not in raw_line:
            raise ValueError(f"expected key: value at line {line_number}")
        key, raw_value = raw_line.split(":", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"empty key at line {line_number}")
        if key in data:
            raise ValueError(f"duplicate key '{key}' at line {line_number}")
        value = strip_comment(raw_value).strip()
        if not value and key.startswith("x_"):
            data[key] = NESTED_EXTENSION
            ignored_extension = key
        elif not value:
            data[key] = []
            current_list = key
        elif BLOCK_SCALAR_RE.fullmatch(value):
            raise ValueError(
                f"block scalars (| or >) are not supported at line {line_number}; "
                f"write '{key}' on one line or reference a native file"
            )
        else:
            data[key] = parse_scalar(value)
    return data


def load_flat_yaml(path: Path) -> dict[str, Any]:
    return parse_flat_yaml_text(path.read_text(encoding="utf-8"))


def unquoted_integer_hint(key: str, value: Any, expected: int) -> str:
    """Explain a quoted integer such as ``schema_version: "3"``."""
    if isinstance(value, str) and value.strip() == str(expected):
        return f"; {key} must be unquoted: write {key}: {expected}"
    return ""
