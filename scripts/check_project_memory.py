#!/usr/bin/env python3
"""Check project-memory structure and cross-file governance invariants."""

from __future__ import annotations

import argparse
import ast
import base64
import binascii
import hashlib
import json
import re
import struct
import subprocess
import zlib
from datetime import datetime, time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


REQUIRED_PROJECT_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    "CODEX.md",
    "project/state.yaml",
    "project/charter.md",
    "project/architecture.md",
    "project/glossary.md",
)
REQUIRED_TASK_FILES = ("task.yaml", "brief.md", "decisions.md", "handoff.md", "review.md")
REQUIRED_TASK_KEYS = (
    "id",
    "title",
    "status",
    "milestone",
    "owner",
    "verifier",
    "priority",
    "created",
    "updated",
    "goal",
    "allowed_files",
    "forbidden_files",
    "acceptance_criteria",
    "dependencies",
    "commits",
    "verification_status",
    "not_committed_reason",
)
REQUIRED_TASK_V2_KEYS = (
    "schema_version",
    "task_types",
    "alignment_mode",
    "design_governance_ref",
)
REQUIRED_TASK_PROTOCOL_21_KEYS = (
    "protocol_version",
    "risk_level",
    "alignment_governance_ref",
    "builder_id",
    "verifier_id",
)
REQUIRED_ALIGNMENT_KEYS = (
    "schema_version",
    "protocol_version",
    "task_id",
    "risk_level",
    "risk_factors",
    "risk_downgrade_ref",
    "start_status",
    "start_ref",
    "start_sha256",
    "start_authority_by",
    "start_authority_at",
    "start_authority_ref",
    "decision_status",
    "decision_ref",
    "decision_sha256",
    "decision_confirmed_by",
    "decision_confirmed_at",
    "decision_confirmation_ref",
    "readout_status",
    "readout_ref",
    "readout_sha256",
    "completion_accepted_by",
    "completion_accepted_at",
    "completion_acceptance_ref",
    "material_deviation",
    "waiver_used",
    "unresolved_risk",
    "h2_required",
    "effect_reversibility",
    "effect_data",
    "effect_environment",
    "effect_external",
    "effect_security_safety",
    "effect_user_impact",
)
REQUIRED_DESIGN_KEYS = (
    "schema_version",
    "task_id",
    "gate_profile",
    "target_maturity",
    "current_maturity",
    "experience_status",
    "experience_ref",
    "experience_sha256",
    "experience_approved_by",
    "experience_approved_at",
    "experience_approval_ref",
    "visual_status",
    "visual_ref",
    "visual_sha256",
    "visual_approved_by",
    "visual_approved_at",
    "visual_approval_ref",
    "conformance_status",
    "conformance_ref",
    "conformance_sha256",
    "difference_approved_by",
    "difference_approved_at",
    "difference_approval_ref",
    "emergency_waiver_ref",
)
VALID_STATES = {
    "proposed",
    "approved",
    "implementing",
    "reviewing",
    "verifying",
    "done",
    "blocked",
    "cancelled",
}
VALID_TASK_TYPES = {
    "product",
    "ux",
    "ui",
    "engineering",
    "research",
    "verification",
    "governance",
}
VALID_ALIGNMENT_MODES = {"text", "diagram", "visual", "mixed"}
SUPPORTED_GOVERNANCE_PROTOCOL = "2.1"
SUPPORTED_GOVERNANCE_PROTOCOLS = ("2.1", "2.2")
CONTINUITY_KERNEL_PROTOCOL = "3.0"
SUPPORTED_PROJECT_SCHEMAS = (1, 2, 3)
ADAPTIVE_REVIEW_PROTOCOL = "2.2"
VALID_RISK_LEVELS = {"low", "medium", "high"}
RISK_LEVEL_RANK = {"low": 0, "medium": 1, "high": 2}
RISK_FACTOR_FLOORS = {
    "local-reversible": "low",
    "cross-component": "medium",
    "product-choice": "medium",
    "reversible-migration": "medium",
    "irreversible-or-destructive": "high",
    "real-user-or-sensitive-data": "high",
    "security-or-safety": "high",
    "difficult-migration": "high",
    "publication-or-deployment": "high",
    "payment-or-message": "high",
    "legal-impact": "high",
}
EFFECT_FIELDS = {
    "effect_reversibility": {
        "reversible": "low",
        "partially_reversible": "medium",
        "irreversible": "high",
    },
    "effect_data": {
        "none": "low",
        "internal": "medium",
        "personal-or-sensitive": "high",
    },
    "effect_environment": {
        "local-only": "low",
        "shared-nonproduction": "medium",
        "production": "high",
    },
    "effect_external": {
        "none": "low",
        "draft-only": "medium",
        "message-or-publish": "high",
        "payment-or-legal": "high",
    },
    "effect_security_safety": {
        "none": "low",
        "involved": "high",
    },
    "effect_user_impact": {
        "none": "low",
        "indirect": "medium",
        "direct": "high",
    },
}
VALID_START_STATUSES = {
    "draft",
    "awaiting_human",
    "changes_requested",
    "direct_instruction",
    "confirmed",
}
VALID_DECISION_STATUSES = {
    "not_required",
    "draft",
    "awaiting_human",
    "changes_requested",
    "confirmed",
}
VALID_READOUT_STATUSES = {
    "not_started",
    "draft",
    "ready",
    "awaiting_human",
    "changes_requested",
    "accepted",
}
VALID_GATE_PROFILES = {"one_gate", "two_gate", "design_only"}
VALID_MATURITY = {
    "spike",
    "functional_prototype",
    "design_candidate",
    "owner_approved",
    "user_validated",
}
VALID_GATE_STATUSES = {
    "not_required",
    "not_started",
    "draft",
    "awaiting_human",
    "changes_requested",
    "approved",
}
VALID_CONFORMANCE_STATUSES = {
    "not_required",
    "not_started",
    "pending_review",
    "matched",
    "changes_requested",
    "accepted_with_differences",
}
ARTIFACT_GATE_STATUSES = {"draft", "awaiting_human", "changes_requested", "approved"}
CONFORMANCE_ARTIFACT_STATUSES = {
    "pending_review",
    "matched",
    "changes_requested",
    "accepted_with_differences",
}
FORMAL_REVIEW_PACKAGE_STATUSES = (
    (ARTIFACT_GATE_STATUSES - {"draft"}) | CONFORMANCE_ARTIFACT_STATUSES
)
EXECUTION_STATES = {"approved", "implementing", "reviewing", "verifying", "done"}
STRICT_GATE_STATES = {"reviewing", "verifying", "done"}
TASK_NAME_RE = re.compile(r"^T-[A-Z][A-Z0-9]{1,11}-\d{3}-[a-z0-9]+(?:-[a-z0-9]+)*$")
V3_TASK_NAME_RE = re.compile(
    r"^T-(?:[A-Z][A-Z0-9]{1,11}-\d{3}|\d{3})-[a-z0-9]+(?:-[a-z0-9]+)*$"
)
MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$", re.IGNORECASE)
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PACKAGE_VERSION_RE = re.compile(r"^v[1-9][0-9]*$")
EXTERNAL_URI_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
VALID_REVIEW_IDENTITY_METHODS = {
    "mutable",
    "file_sha256",
    "provider_revision",
    "git_commit",
    "external_attestation",
}
CUSTOM_REVIEW_IDENTITY_METHOD_RE = re.compile(
    r"^custom/[a-z0-9]+(?:-[a-z0-9]+)*$"
)
MUTABLE_IDENTITY_TOKENS = {"current", "draft", "head", "latest", "main", "master", "mutable", "working"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T ][^\s]+)?$")
AUTOMATION_ID_RE = re.compile(
    r"(?:^|[^a-z0-9])(agent|automation|bot|chatgpt|claude|codex|model|system)(?:$|[^a-z0-9])",
    re.IGNORECASE,
)
PLACEHOLDER_PATTERNS = (
    re.compile(r"\{\{[^{}]+\}\}"),
    re.compile(r"\bTODO\b", re.IGNORECASE),
    re.compile(r"\bTBD\b", re.IGNORECASE),
    re.compile(r"REPLACE[_ -]?ME", re.IGNORECASE),
    re.compile(r"\bREPLACE\s+(?:THIS|THE|WITH)\b", re.IGNORECASE),
    re.compile(r"\bT-[A-Z][A-Z0-9]{1,11}-\d{3}-short-name\b", re.IGNORECASE),
    re.compile(r"LOREM\s+IPSUM", re.IGNORECASE),
    re.compile(r"<!--[^>]*(?:placeholder|template)[^>]*-->", re.IGNORECASE),
)
REMOTE_HTML_RE = re.compile(
    r"(?:\b(?:src|href)\s*=\s*['\"](?:https?:)?//|url\(\s*['\"]?https?://|\bfetch\s*\(|\bXMLHttpRequest\b|\bWebSocket\s*\()",
    re.IGNORECASE,
)
MARKDOWN_ARTIFACT_MARKER_RE = re.compile(
    r"<!--\s*project-memory-artifact\s*:\s*([^>]+?)\s*-->", re.IGNORECASE
)
MARKDOWN_TASK_MARKER_RE = re.compile(
    r"<!--\s*task-id\s*:\s*([^>]+?)\s*-->", re.IGNORECASE
)
MARKDOWN_VERSION_MARKER_RE = re.compile(
    r"<!--\s*artifact-version\s*:\s*(v[1-9][0-9]*)\s*-->", re.IGNORECASE
)
DECISION_BINDING_RE = re.compile(
    r"<!--\s*project-memory-decision-binding\s*\n(?P<body>.*?)-->",
    re.IGNORECASE | re.DOTALL,
)
DECISION_BINDING_FIELDS = (
    "task-id",
    "decision-kind",
    "artifact-path",
    "artifact-version",
    "artifact-sha256",
    "gate",
    "decision-outcome",
    "scope",
)
VALID_DECISION_KINDS = {
    "start-direction",
    "start-confirmation",
    "h2-confirmation",
    "completion-acceptance",
    "experience-approval",
    "visual-approval",
    "difference-acceptance",
    "emergency-waiver",
    "risk-downgrade",
}
DECISION_KIND_OUTCOMES = {
    "start-direction": "recorded",
    "start-confirmation": "confirmed",
    "h2-confirmation": "confirmed",
    "completion-acceptance": "accepted",
    "experience-approval": "approved",
    "visual-approval": "approved",
    "difference-acceptance": "accepted",
    "emergency-waiver": "approved",
    "risk-downgrade": "approved",
}
DECISION_OUTCOME_LINE_RE = re.compile(
    r"^Decision outcome: (recorded|confirmed|accepted|approved)$",
    re.MULTILINE,
)
DECISION_OUTCOME_PREFIX_RE = re.compile(r"^\s*Decision outcome\s*:.*$", re.MULTILINE)
REQUIRED_ALIGNMENT_HEADINGS = {
    "human-start-alignment": (
        "Human Start Alignment",
        "Outcome And H0 Boundary",
        "Scope And Non-goals",
        "Acceptance And Evidence",
        "Risk Assessment",
        "H1 Execution Boundary",
        "Assumptions And Unknowns",
    ),
    "human-decision-checkpoint": (
        "Human Decision Checkpoint",
        "Trigger",
        "Options And Tradeoffs",
        "Recommendation",
        "Human Decision",
        "AI Autonomous Boundary",
    ),
    "human-readout": (
        "Human Readout",
        "Outcome",
        "Before And After",
        "Boundaries Preserved",
        "Acceptance Map",
        "Evidence And Confidence",
        "Residual Risk And Unknowns",
        "Next Decision",
    ),
}
REQUIRED_VISUAL_HEADINGS = {
    "experience-alignment": (
        "L0 boundary",
        "L1 journey",
        "Key alternatives",
        "L2 page map",
        "L3 complete screens",
        "State coverage",
        "Approval requested",
    ),
    "visual-alignment": (
        "Selected visual language",
        "Actual device frames",
        "Dynamic Type",
        "Complete key states",
        "Mapping to approved experience",
        "Approval requested",
    ),
    "design-conformance": (
        "Baseline identity",
        "Capture environment",
        "Page-state comparison",
        "Required state matrix",
        "Difference register",
        "Independent disposition",
    ),
}
ONE_GATE_VISUAL_HEADINGS = (
    "Experience context",
    "User journey",
    "Affected page relationship",
    "Affected states",
)

REVIEW_PACKAGE_FIELDS = (
    "schema_version",
    "protocol_version",
    "task_id",
    "checkpoint",
    "package_version",
    "question",
    "covers",
    "binding_surfaces",
    "supporting_surfaces",
    "excluded",
    "limitations",
    "extensions",
)
CANONICAL_REVIEW_PACKAGE_FIELDS = (
    "schema_version",
    "protocol_version",
    "task_id",
    "checkpoint",
    "package_version",
    "question",
    "covers",
    "binding_surfaces",
    "excluded",
    "limitations",
    "extensions",
)
VALID_REVIEW_COVERS = {
    "H0",
    "H1",
    "H2",
    "H3",
    "HumanReadout",
    "L0",
    "L1",
    "L2",
    "L3",
    "L4",
    "L5",
}

REQUIRED_HANDOFF_HEADINGS = (
    "Execution Basis",
    "Universal Alignment Baseline",
    "Approved Design Baseline",
    "Delivered",
    "Changed Files",
    "Verification",
    "Acceptance Criteria",
    "Human Readout",
    "Design Differences",
    "Risks And Open Questions",
    "Git",
    "Next Action",
)
REQUIRED_REVIEW_HEADINGS = (
    "Review Basis",
    "Engineering Findings",
    "Human Readout Findings",
    "Design Conformance Findings",
    "Acceptance Decision",
    "Residual Risk",
)

INTRINSICALLY_HIDDEN_HTML_TAGS = {"script", "style", "template"}
HTML_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
FORBIDDEN_HIDING_CSS_RE = re.compile(
    r"(?:display\s*:\s*none|visibility\s*:\s*hidden|content-visibility\s*:\s*hidden|opacity\s*:\s*0(?:[;\s}]|$))",
    re.IGNORECASE,
)

SVG_DRAWABLE_TAGS = {
    "path",
    "rect",
    "circle",
    "ellipse",
    "line",
    "polyline",
    "polygon",
}


def positive_svg_number(value: str) -> float | None:
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(?:px)?\s*", value, re.IGNORECASE)
    if not match:
        return None
    number = float(match.group(1))
    return number if number > 0 else None


def valid_svg_dimensions(attributes: dict[str, str]) -> bool:
    width = positive_svg_number(attributes.get("width", ""))
    height = positive_svg_number(attributes.get("height", ""))
    if width is not None and height is not None:
        return True
    numbers = re.findall(r"-?[0-9]+(?:\.[0-9]+)?", attributes.get("viewbox", ""))
    return len(numbers) == 4 and float(numbers[2]) > 0 and float(numbers[3]) > 0


def substantive_svg_drawable(tag: str, attributes: dict[str, str]) -> bool:
    if tag == "path":
        path_data = re.sub(r"\s+", "", attributes.get("d", ""))
        return len(path_data) >= 8 and len(re.findall(r"[A-Za-z]", path_data)) >= 2
    if tag == "rect":
        return (
            positive_svg_number(attributes.get("width", "")) is not None
            and positive_svg_number(attributes.get("height", "")) is not None
        )
    if tag == "circle":
        return positive_svg_number(attributes.get("r", "")) is not None
    if tag == "ellipse":
        return (
            positive_svg_number(attributes.get("rx", "")) is not None
            and positive_svg_number(attributes.get("ry", "")) is not None
        )
    if tag == "line":
        coordinates = [attributes.get(key, "") for key in ("x1", "y1", "x2", "y2")]
        return len({value for value in coordinates if value}) >= 2
    if tag in {"polyline", "polygon"}:
        minimum = 6 if tag == "polygon" else 4
        return len(re.findall(r"-?[0-9]+(?:\.[0-9]+)?", attributes.get("points", ""))) >= minimum
    return False


def png_dimensions(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    offset = 8
    dimensions: tuple[int, int] | None = None
    bit_depth: int | None = None
    color_type: int | None = None
    interlace: int | None = None
    compressed = bytearray()
    saw_end = False
    saw_palette = False
    chunk_index = 0
    while offset + 12 <= len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_end = offset + 12 + length
        if chunk_end > len(data):
            return None
        payload = data[offset + 8 : offset + 8 + length]
        recorded_crc = struct.unpack(">I", data[offset + 8 + length : chunk_end])[0]
        if zlib.crc32(chunk_type + payload) & 0xFFFFFFFF != recorded_crc:
            return None
        if chunk_type == b"IHDR":
            if length != 13 or dimensions is not None or chunk_index != 0:
                return None
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            if (
                width <= 0
                or height <= 0
                or width * height > 100_000_000
                or compression != 0
                or filtering != 0
                or interlace not in {0, 1}
            ):
                return None
            valid_depths = {
                0: {1, 2, 4, 8, 16},
                2: {8, 16},
                3: {1, 2, 4, 8},
                4: {8, 16},
                6: {8, 16},
            }
            if color_type not in valid_depths or bit_depth not in valid_depths[color_type]:
                return None
            dimensions = (width, height)
        elif chunk_type == b"PLTE":
            if length == 0 or length % 3 or length > 768:
                return None
            saw_palette = True
        elif chunk_type == b"IDAT":
            if dimensions is None:
                return None
            compressed.extend(payload)
        elif chunk_type == b"IEND":
            if length != 0 or chunk_end != len(data):
                return None
            saw_end = True
            break
        offset = chunk_end
        chunk_index += 1
    if (
        dimensions is None
        or bit_depth is None
        or color_type is None
        or interlace is None
        or not compressed
        or not saw_end
        or (color_type == 3 and not saw_palette)
    ):
        return None
    try:
        decoder = zlib.decompressobj()
        decoded = decoder.decompress(bytes(compressed), 200_000_000)
        decoded += decoder.flush()
        if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            return None
    except zlib.error:
        return None

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    bits_per_pixel = channels * bit_depth
    width, height = dimensions
    if interlace == 0:
        passes = ((width, height),)
    else:
        passes = tuple(
            (
                0 if width <= start_x else (width - start_x + step_x - 1) // step_x,
                0 if height <= start_y else (height - start_y + step_y - 1) // step_y,
            )
            for start_x, start_y, step_x, step_y in (
                (0, 0, 8, 8),
                (4, 0, 8, 8),
                (0, 4, 4, 8),
                (2, 0, 4, 4),
                (0, 2, 2, 4),
                (1, 0, 2, 2),
                (0, 1, 1, 2),
            )
        )
    cursor = 0
    for pass_width, pass_height in passes:
        if pass_width == 0 or pass_height == 0:
            continue
        row_bytes = (pass_width * bits_per_pixel + 7) // 8
        for _ in range(pass_height):
            if cursor >= len(decoded) or decoded[cursor] > 4:
                return None
            cursor += 1 + row_bytes
            if cursor > len(decoded):
                return None
    if cursor != len(decoded):
        return None
    return dimensions


def substantive_raster_data_uri(source: str) -> bool:
    match = re.fullmatch(
        r"data:(image/png);base64,([A-Za-z0-9+/=\s]+)",
        source.strip(),
        re.IGNORECASE,
    )
    if not match:
        return False
    try:
        payload = base64.b64decode(re.sub(r"\s+", "", match.group(2)), validate=True)
    except (binascii.Error, ValueError):
        return False
    if len(payload) < 512:
        return False
    dimensions = png_dimensions(payload)
    return bool(dimensions and dimensions[0] >= 160 and dimensions[1] >= 240)


def html_element_is_hidden(tag: str, attributes: dict[str, str]) -> bool:
    return (
        tag in INTRINSICALLY_HIDDEN_HTML_TAGS
        or "hidden" in attributes
        or attributes.get("aria-hidden", "").strip().lower() in {"true", "1"}
        or FORBIDDEN_HIDING_CSS_RE.search(attributes.get("style", "")) is not None
    )


class VisibleHeadingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._depth = 0
        self._parts: list[str] = []
        self._hidden_depth = 0
        self._element_stack: list[tuple[str, bool]] = []
        self._active_section: int | None = None
        self._capture_stack: list[dict[str, Any]] = []
        self._svg_stack: list[dict[str, Any]] = []
        self.headings: list[str] = []
        self.section_bodies: list[str] = []
        self.capture_payloads: list[tuple[str, str, bool]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        attributes = {str(key).lower(): str(value or "") for key, value in attrs}
        starts_hidden = html_element_is_hidden(lowered, attributes)
        if lowered not in HTML_VOID_TAGS:
            self._element_stack.append((lowered, starts_hidden))
            if starts_hidden:
                self._hidden_depth += 1
        if self._hidden_depth or (lowered in HTML_VOID_TAGS and starts_hidden):
            return
        side = attributes.get("data-conformance-capture", "").strip().lower()
        if side:
            capture = {
                "tag": lowered,
                "side": side,
                "state": attributes.get("data-page-state", "").strip(),
                "payload": False,
            }
            self._capture_stack.append(capture)
        for svg in self._svg_stack:
            svg["depth"] += 1
            if lowered in SVG_DRAWABLE_TAGS and substantive_svg_drawable(lowered, attributes):
                svg["drawables"] += 1
                svg["detail"] += sum(len(value.strip()) for value in attributes.values())
        if lowered == "svg" and self._capture_stack:
            self._svg_stack.append(
                {
                    "depth": 1,
                    "dimensions": valid_svg_dimensions(attributes),
                    "drawables": 0,
                    "detail": sum(len(value.strip()) for value in attributes.values()),
                    "captures": list(self._capture_stack),
                }
            )
        if (
            lowered == "img"
            and self._capture_stack
            and substantive_raster_data_uri(attributes.get("src", ""))
        ):
            for capture in self._capture_stack:
                capture["payload"] = True
        if re.fullmatch(r"h[1-6]", tag, re.IGNORECASE):
            if self._depth == 0:
                self._parts = []
            self._depth += 1

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if not self._hidden_depth:
            if re.fullmatch(r"h[1-6]", tag, re.IGNORECASE) and self._depth:
                self._depth -= 1
                if self._depth == 0:
                    self.headings.append("".join(self._parts))
                    self.section_bodies.append("")
                    self._active_section = len(self.section_bodies) - 1
            completed_svgs: list[dict[str, Any]] = []
            for svg in self._svg_stack:
                svg["depth"] -= 1
                if svg["depth"] == 0:
                    completed_svgs.append(svg)
            for svg in completed_svgs:
                self._svg_stack.remove(svg)
                substantive = (
                    svg["dimensions"]
                    and svg["drawables"] >= 2
                    and svg["detail"] >= 20
                )
                if substantive:
                    for capture in svg["captures"]:
                        if capture["side"] == "approved":
                            capture["payload"] = True
            if self._capture_stack and self._capture_stack[-1]["tag"] == lowered:
                capture = self._capture_stack.pop()
                self.capture_payloads.append(
                    (capture["side"], capture["state"], bool(capture["payload"]))
                )
        if lowered not in HTML_VOID_TAGS:
            for index in range(len(self._element_stack) - 1, -1, -1):
                element_tag, _ = self._element_stack[index]
                if element_tag != lowered:
                    continue
                popped = self._element_stack[index:]
                del self._element_stack[index:]
                self._hidden_depth -= sum(1 for _, starts_hidden in popped if starts_hidden)
                self._hidden_depth = max(0, self._hidden_depth)
                break

    def handle_data(self, data: str) -> None:
        if self._hidden_depth:
            return
        if self._depth:
            self._parts.append(data)
        elif not self._hidden_depth and self._active_section is not None:
            self.section_bodies[self._active_section] += data


class VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._hidden_depth = 0
        self._element_stack: list[tuple[str, bool]] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.lower()
        attributes = {str(key).lower(): str(value or "") for key, value in attrs}
        starts_hidden = html_element_is_hidden(lowered, attributes)
        if lowered not in HTML_VOID_TAGS:
            self._element_stack.append((lowered, starts_hidden))
            if starts_hidden:
                self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in HTML_VOID_TAGS:
            return
        for index in range(len(self._element_stack) - 1, -1, -1):
            element_tag, _ = self._element_stack[index]
            if element_tag != lowered:
                continue
            popped = self._element_stack[index:]
            del self._element_stack[index:]
            self._hidden_depth -= sum(1 for _, starts_hidden in popped if starts_hidden)
            self._hidden_depth = max(0, self._hidden_depth)
            break

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth:
            self.parts.append(data)


def normalized_heading(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def low_information_repetition(text: str) -> bool:
    compact = "".join(
        character.casefold()
        for character in text
        if character.isalnum() or "\u3400" <= character <= "\u9fff"
    )
    if re.search(r"(.)\1{7,}", compact):
        return True
    for width in range(1, min(9, len(compact) // 5 + 1)):
        repeated = re.compile(rf"(.{{{width}}})\1{{4,}}")
        if repeated.search(compact):
            return True

    tokens = [
        token.casefold()
        for token in re.findall(r"[A-Za-z0-9]+|[\u3400-\u9fff]", text)
    ]
    if len(tokens) >= 8:
        distinct = len(set(tokens))
        if distinct <= 3 or distinct / len(tokens) < 0.24:
            return True
        for width in range(1, min(13, len(tokens) // 3 + 1)):
            for start in range(0, len(tokens) - width * 3 + 1):
                phrase = tokens[start : start + width]
                if all(
                    tokens[start + repeat * width : start + (repeat + 1) * width] == phrase
                    for repeat in range(1, 3)
                ):
                    return True
    return len(compact) >= 20 and len(set(compact)) <= 4


def substantive_section_body(text: str) -> bool:
    if any(pattern.search(text) for pattern in PLACEHOLDER_PATTERNS):
        return False
    cleaned = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    cleaned = re.sub(r"[`*_>#|\[\]()-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) < 20:
        return False
    return not low_information_repetition(cleaned)


def normalized_body_fingerprint(text: str) -> str:
    cleaned = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL).casefold()
    return " ".join(re.findall(r"[a-z0-9]+|[\u3400-\u9fff]", cleaned))


def duplicate_required_bodies(
    required_headings: tuple[str, ...],
    sections: dict[str, str],
    *,
    markdown: bool = False,
) -> list[str]:
    observed: dict[str, str] = {}
    duplicates: list[str] = []
    for heading in required_headings:
        key = heading_anchor(heading) if markdown else normalized_heading(heading)
        if key not in sections:
            continue
        fingerprint = normalized_body_fingerprint(sections[key])
        if len(fingerprint) < 20:
            continue
        if fingerprint in observed:
            duplicates.extend([observed[fingerprint], heading])
        else:
            observed[fingerprint] = heading
    return list(dict.fromkeys(duplicates))


def html_heading_sections(parser: VisibleHeadingParser) -> dict[str, str]:
    sections: dict[str, str] = {}
    for heading, body in zip(parser.headings, parser.section_bodies):
        sections.setdefault(normalized_heading(heading), body)
    return sections


def markdown_visible_headings(content: str) -> set[str]:
    headings: set[str] = set()
    fence: str | None = None
    for line in content.splitlines():
        fence_match = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if fence_match:
            marker = fence_match.group(1)[0]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if fence is not None:
            continue
        heading_match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
        if heading_match:
            headings.add(
                re.sub(r"\s+", " ", heading_match.group(1).strip()).lower()
            )
    return headings


def markdown_visible_body(content: str) -> str:
    without_comments = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    outside_fences: list[str] = []
    fence: str | None = None
    for line in without_comments.splitlines():
        fence_match = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if fence_match:
            marker = fence_match.group(1)[0]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if fence is None:
            outside_fences.append(line)
    parser = VisibleTextParser()
    parser.feed("\n".join(outside_fences))
    parser.close()
    return "".join(parser.parts)


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
        return [parse_scalar(part) for part in body.split(",")]
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
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
    for line_number, raw_line in enumerate(content.splitlines(), 1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line.startswith("  - ") and current_list:
            data[current_list].append(parse_scalar(raw_line[4:]))
            continue
        if raw_line[:1].isspace():
            raise ValueError(f"unsupported nested YAML at line {line_number}")
        if ":" not in raw_line:
            raise ValueError(f"expected key: value at line {line_number}")
        key, raw_value = raw_line.split(":", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"empty key at line {line_number}")
        if key in data:
            raise ValueError(f"duplicate key '{key}' at line {line_number}")
        if not raw_value.strip():
            data[key] = []
            current_list = key
        else:
            data[key] = parse_scalar(raw_value)
            current_list = None
    return data


def load_flat_yaml(path: Path) -> dict[str, Any]:
    return parse_flat_yaml_text(path.read_text(encoding="utf-8"))


def parse_v3_yaml_text(content: str) -> dict[str, Any]:
    """Parse the flat portable core while ignoring nested top-level x_* extensions."""
    data: dict[str, Any] = {}
    current_list: str | None = None
    ignored_extension: str | None = None
    for line_number, raw_line in enumerate(content.splitlines(), 1):
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if raw_line[:1].isspace():
            if ignored_extension is not None:
                continue
            if raw_line.startswith("  - ") and current_list:
                data[current_list].append(parse_scalar(raw_line[4:]))
                continue
            raise ValueError(f"unsupported nested YAML at line {line_number}; use a top-level x_* extension or a referenced native file")
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
        if not raw_value.strip() and key.startswith("x_"):
            data[key] = "<nested-extension>"
            ignored_extension = key
        elif not raw_value.strip():
            data[key] = []
            current_list = key
        else:
            data[key] = parse_scalar(raw_value)
    return data


def load_v3_yaml(path: Path) -> dict[str, Any]:
    return parse_v3_yaml_text(path.read_text(encoding="utf-8"))


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def risk_factor_floor(factor: str) -> str | None:
    if factor in RISK_FACTOR_FLOORS:
        return RISK_FACTOR_FLOORS[factor]
    match = re.fullmatch(r"custom-(low|medium|high):[a-z0-9]+(?:-[a-z0-9]+)*", factor)
    return match.group(1) if match else None


def highest_risk(levels: list[str]) -> str:
    return max(levels, key=lambda value: RISK_LEVEL_RANK[value]) if levels else "low"


def goal_high_risk_signals(goal: Any) -> list[str]:
    text = re.sub(r"\s+", " ", str(goal or "")).strip().lower()
    if not text:
        return []
    clauses = [
        clause.strip()
        for clause in re.split(
            r"[\n.!?;,。！？；，]+|\b(?:but|and)\b|(?:但是|但|并且|且)",
            str(goal or "").lower(),
            flags=re.IGNORECASE,
        )
        if clause.strip()
    ]
    exclusion = re.compile(
        r"\b(?:non-goal|non goal|out of scope|mock|fixture|test-only|example only)\b"
        r"|\b(?:do not|don't|must not|never|dry[- ]run|preview only|plan only|documentation only|simulate)\b"
        r"|非目标|不在范围|不(?:可(?!逆)|向|要|得|应|会|能|允许|触发|执行|处理|发送|通知|部署|发布|扣款|收费|退款|删除|撤销|修改|影响|接触|触碰|读取|写入|导出|迁移|采用|使用)|禁止|仅(?:预览|计划|文档)|演练|模拟(?:数据|场景)?|测试(?:夹具|数据|场景)",
        re.IGNORECASE,
    )
    patterns = (
        (
            "destructive customer-data deletion",
            r"\b(?:permanently\s+)?(?:delete|erase|destroy|purge)\b.{0,40}\b(?:customer|user)\s+(?:data|records?)\b"
            r"|(?:永久)?删除.{0,12}(?:客户|用户)(?:数据|记录)|销毁.{0,12}(?:客户|用户)(?:数据|记录)",
        ),
        (
            "production key invalidation",
            r"\b(?:invalidate|revoke|disable|destroy)\b.{0,40}\bproduction\s+(?:api\s+)?keys?\b"
            r"|使.{0,10}生产(?:环境)?(?:api)?密钥失效|撤销.{0,10}生产(?:环境)?(?:api)?密钥",
        ),
        (
            "customer notification",
            r"\b(?:notify|message|email|alert)\b.{0,30}\b(?:customers?|users?)\b"
            r"|\b(?:customer|user)\s+notification\b|(?:通知|告知|发送消息给)(?:客户|用户)|向(?:客户|用户)发送(?:通知|消息)",
        ),
        (
            "production deployment or public release",
            r"\b(?:deploy|release|ship|roll\s*out|publish)\b.{0,40}\b(?:to\s+)?(?:production|live|public(?:ly)?)\b"
            r"|(?:部署|发布|上线).{0,16}(?:生产环境|正式环境|线上环境|公开发布)|向公众发布",
        ),
        (
            "real customer payment",
            r"\b(?:charge|bill|debit)\b.{0,40}\b(?:customers?|users?|credit\s+cards?|bank\s+accounts?)\b"
            r"|\b(?:process|capture|refund)\b.{0,30}\b(?:real|live|customer)\s+payments?\b"
            r"|(?:向|对)(?:客户|用户).{0,10}(?:扣款|收费|退款)|处理.{0,10}(?:真实|线上)(?:支付|扣款|退款)",
        ),
        (
            "personal or sensitive data transfer",
            r"\b(?:export|migrate|copy|upload|share|send|process)\b.{0,50}\b(?:personal|sensitive|health|medical|financial)\s+(?:data|records?|information)\b"
            r"|(?:导出|迁移|复制|上传|共享|发送|处理).{0,16}(?:个人|敏感|医疗|健康|金融)(?:数据|记录|信息)",
        ),
        (
            "irreversible migration",
            r"\b(?:irreversibly|permanently)\s+(?:migrate|rewrite|convert)\b"
            r"|\b(?:migration|conversion)\b.{0,35}\b(?:cannot|can't)\s+be\s+(?:rolled\s+back|reversed)\b"
            r"|(?:不可逆|永久)(?:迁移|转换|重写)|(?:迁移|转换).{0,12}(?:无法|不能)(?:回滚|撤销)",
        ),
        (
            "security or safety control change",
            r"\b(?:disable|bypass|remove|weaken)\b.{0,35}\b(?:authentication|authorization|encryption|security|safety|interlock|guardrail)\b"
            r"|(?:禁用|绕过|移除|削弱).{0,16}(?:认证|授权|加密|安全控制|安全联锁|防护措施)",
        ),
        (
            "direct real-user state change",
            r"\b(?:activate|suspend|terminate|modify|replace|cancel)\b.{0,40}\b(?:customer|user)\s+(?:accounts?|subscriptions?|plans?)\b"
            r"|(?:激活|暂停|终止|修改|替换|取消).{0,16}(?:客户|用户)(?:账户|订阅|计划)",
        ),
        (
            "binding legal action",
            r"\b(?:sign|execute|accept|file)\b.{0,40}\b(?:binding\s+)?(?:contract|legal\s+agreement|terms|lawsuit)\b"
            r"|(?:签署|执行|接受|提交).{0,16}(?:合同|法律协议|诉讼|具有约束力的条款)",
        ),
    )
    signals: list[str] = []
    for clause in clauses:
        if exclusion.search(clause):
            continue
        for name, pattern in patterns:
            if name not in signals and re.search(pattern, clause, re.IGNORECASE):
                signals.append(name)
    return signals


def substantive_markdown(path: Path) -> bool:
    if not path.is_file():
        return False
    useful: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("<!--"):
            continue
        if "{{" in stripped or "TODO" in stripped or "TEMPLATE" in stripped.upper():
            continue
        useful.append(stripped)
    return len(" ".join(useful)) >= 10


def is_human_identity(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and not AUTOMATION_ID_RE.search(text)


def is_approval_time(value: Any) -> bool:
    return parse_iso_datetime(value) is not None


def parse_iso_datetime(value: Any, *, date_is_end_of_day: bool = False) -> datetime | None:
    text = str(value or "").strip()
    if not DATE_RE.fullmatch(text):
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if len(text) == 10 and date_is_end_of_day:
        parsed = datetime.combine(parsed.date(), time.max)
    return parsed


def not_after_adoption(updated: Any, adopted: Any) -> bool:
    updated_time = parse_iso_datetime(updated, date_is_end_of_day=True)
    adopted_time = parse_iso_datetime(adopted)
    if updated_time is None or adopted_time is None:
        return False
    if updated_time.tzinfo is None and adopted_time.tzinfo is not None:
        updated_time = updated_time.replace(tzinfo=adopted_time.tzinfo)
    elif updated_time.tzinfo is not None and adopted_time.tzinfo is None:
        adopted_time = adopted_time.replace(tzinfo=updated_time.tzinfo)
    return updated_time <= adopted_time


def chronological_timestamps(created: Any, updated: Any) -> bool:
    created_time = parse_iso_datetime(created)
    updated_time = parse_iso_datetime(updated)
    if created_time is None or updated_time is None:
        return False
    if created_time.tzinfo is None and updated_time.tzinfo is not None:
        created_time = created_time.replace(tzinfo=updated_time.tzinfo)
    elif created_time.tzinfo is not None and updated_time.tzinfo is None:
        updated_time = updated_time.replace(tzinfo=created_time.tzinfo)
    return created_time <= updated_time


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def first_symlink_component(path: Path) -> Path | None:
    absolute = path.absolute()
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor = cursor / part
        if cursor.is_symlink():
            return cursor
    return None


def resolve_task_path(
    task_dir: Path,
    project_root: Path,
    raw_ref: Any,
    label: str,
    errors: list[str],
    source_label: str = "design/design.yaml",
) -> Path | None:
    relative = task_dir.relative_to(project_root)
    text = str(raw_ref or "").strip()
    if not text:
        errors.append(f"{relative}/{source_label}: missing {label}")
        return None
    ref = Path(text)
    if ref.is_absolute():
        errors.append(f"{relative}/{source_label}: {label} must be a relative path")
        return None
    if ".." in ref.parts:
        errors.append(f"{relative}/{source_label}: {label} escapes task directory")
        return None

    project_prefix = tuple(relative.parts)
    if tuple(ref.parts[: len(project_prefix)]) == project_prefix:
        candidate = project_root / ref
    else:
        candidate = task_dir / ref
    try:
        lexical_relative = candidate.relative_to(task_dir)
    except ValueError:
        errors.append(f"{relative}/{source_label}: {label} escapes task directory")
        return None
    cursor = task_dir
    for component in lexical_relative.parts:
        cursor = cursor / component
        if cursor.is_symlink():
            errors.append(
                f"{relative}/{source_label}: {label} must not traverse a symlink component"
            )
            return None
    resolved = candidate.resolve()
    try:
        resolved.relative_to(task_dir.resolve())
    except ValueError:
        errors.append(f"{relative}/{source_label}: {label} escapes task directory")
        return None
    return resolved


def canonical_review_package_digest(package: dict[str, Any]) -> str:
    """Return the protocol-2.2 digest, intentionally excluding supporting surfaces."""
    canonical = {
        field: package.get(field) for field in CANONICAL_REVIEW_PACKAGE_FIELDS
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def review_value_contains_placeholder(value: Any) -> bool:
    if isinstance(value, str):
        return bool(
            re.search(
                r"\breplace(?:[-_\s]+)(?:me|this|the|with)\b",
                value,
                re.IGNORECASE,
            )
        ) or any(pattern.search(value) for pattern in PLACEHOLDER_PATTERNS)
    if isinstance(value, list):
        return any(review_value_contains_placeholder(item) for item in value)
    if isinstance(value, dict):
        return any(
            review_value_contains_placeholder(key)
            or review_value_contains_placeholder(item)
            for key, item in value.items()
        )
    return False


def review_surface_requires_local_fallback(surface: Any) -> bool:
    if not isinstance(surface, dict):
        return False
    identity = surface.get("identity")
    method = (
        str(identity.get("method") or "").strip()
        if isinstance(identity, dict)
        else ""
    )
    locator = str(surface.get("locator") or "").strip()
    return (
        method in {"provider_revision", "external_attestation"}
        or method.startswith("custom/")
        or EXTERNAL_URI_RE.match(locator) is not None
    )


def load_review_package(path: Path) -> dict[str, Any] | None:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON member: {key}")
            value[key] = item
        return value

    def reject_nonstandard_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant: {value}")

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_nonstandard_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def validate_adaptive_html_surface(
    path: Path,
    label: str,
    errors: list[str],
) -> None:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        errors.append(f"{label}: local HTML surface must be UTF-8 text")
        return
    if len(content.strip()) < 200 or "<html" not in content.lower():
        errors.append(f"{label}: local HTML surface is not substantive HTML")
    for pattern in PLACEHOLDER_PATTERNS:
        if pattern.search(content):
            errors.append(f"{label}: local HTML surface contains unresolved template placeholder")
            break
    if REMOTE_HTML_RE.search(content):
        errors.append(f"{label}: local HTML surface is not self-contained and offline")
    parser = VisibleTextParser()
    try:
        parser.feed(content)
        parser.close()
    except ValueError:
        errors.append(f"{label}: local HTML surface contains malformed HTML")
        return
    if not substantive_section_body(" ".join(parser.parts)):
        errors.append(f"{label}: local HTML surface lacks substantive visible content")


def validate_review_surface(
    surface: Any,
    *,
    index: int,
    collection_name: str,
    package_label: str,
    task_dir: Path,
    project_root: Path,
    errors: list[str],
    require_identity: bool,
) -> tuple[str, str, bool, str | None] | None:
    label = f"{package_label}: {collection_name}[{index}]"
    if not isinstance(surface, dict):
        errors.append(f"{label} must be an object")
        return None

    surface_id = str(surface.get("id") or "").strip()
    role = str(surface.get("role") or "").strip()
    kind = str(surface.get("kind") or "").strip()
    locator = str(surface.get("locator") or "").strip()
    if not surface_id:
        errors.append(f"{label}.id must be nonempty")
    if not role:
        errors.append(f"{label}.role must be nonempty")
    elif collection_name == "supporting_surfaces" and role != "context-only/non-binding":
        errors.append(
            f"{label}.role must be exactly context-only/non-binding because supporting surfaces are excluded from the canonical digest"
        )
    if not SLUG_RE.fullmatch(kind):
        errors.append(f"{label}.kind must be a nonempty lowercase slug")
    if not locator:
        errors.append(f"{label}.locator must be nonempty")

    identity = surface.get("identity")
    if identity is None and not require_identity:
        identity = {}
    elif not isinstance(identity, dict):
        errors.append(f"{label}.identity must be an object")
        return None
    if require_identity and not identity:
        errors.append(f"{label}.identity must contain method, value, and immutable")
        return None
    method = str(identity.get("method") or "").strip()
    value = str(identity.get("value") or "").strip()
    immutable = identity.get("immutable")
    if identity:
        valid_method = (
            method in VALID_REVIEW_IDENTITY_METHODS
            or CUSTOM_REVIEW_IDENTITY_METHOD_RE.fullmatch(method) is not None
        )
        if not valid_method:
            errors.append(
                f"{label}.identity.method must be a supported method or custom/<slug>"
            )
        if not value:
            errors.append(f"{label}.identity.value must be nonempty")
        if not isinstance(immutable, bool):
            errors.append(f"{label}.identity.immutable must be true or false")

    if "capabilities" in surface:
        capabilities = surface.get("capabilities")
        if not isinstance(capabilities, list) or any(
            not isinstance(item, str) or not item.strip() for item in capabilities
        ):
            errors.append(f"{label}.capabilities must be a list of nonempty strings")
    page_state_value = surface.get("page_state")
    page_state: str | None = None
    if page_state_value is not None:
        page_state = str(page_state_value).strip()
        if not page_state:
            errors.append(f"{label}.page_state must be nonempty when present")

    if method == "mutable" and immutable is not False:
        errors.append(f"{label}.identity method mutable requires immutable false")
    if method == "provider_revision" and value.casefold() in MUTABLE_IDENTITY_TOKENS:
        errors.append(
            f"{label}.identity provider_revision must name a stable provider revision, not a mutable alias"
        )
    if method == "git_commit" and not GIT_COMMIT_RE.fullmatch(value):
        errors.append(f"{label}.identity git_commit requires a full 40- or 64-hex commit ID")
    if method.startswith("custom/") and immutable is not True:
        errors.append(f"{label}.identity custom methods require immutable true")
    if method == "file_sha256":
        local_path = resolve_task_path(
            task_dir,
            project_root,
            locator,
            f"{collection_name}[{index}].locator",
            errors,
            package_label,
        )
        if local_path is not None:
            if not local_path.is_file():
                errors.append(f"{label}.locator does not reference an existing local file")
            else:
                recorded = value.lower()
                if value != recorded or not SHA256_RE.fullmatch(recorded):
                    errors.append(f"{label}.identity.value requires a valid SHA-256")
                elif recorded != sha256(local_path):
                    errors.append(f"{label}.identity.value does not match the local file bytes")
                if local_path.suffix.lower() == ".html":
                    validate_adaptive_html_surface(local_path, label, errors)

    return surface_id, method, immutable is True, page_state


def validate_review_package(
    task: dict[str, Any],
    task_dir: Path,
    project_root: Path,
    ref: Any,
    expected_digest: Any,
    ref_field: str,
    checkpoint: str,
    expected_covers: tuple[str, ...],
    status: str,
    errors: list[str],
    *,
    source_label: str,
    force_formal: bool = False,
) -> dict[str, Any] | None:
    relative = task_dir.relative_to(project_root)
    package_path = resolve_task_path(
        task_dir,
        project_root,
        ref,
        ref_field,
        errors,
        source_label,
    )
    if package_path is None:
        return None
    label = str(package_path.relative_to(project_root))
    if package_path.suffix.lower() != ".json":
        errors.append(f"{relative}/{source_label}: {ref_field} must reference a JSON review package")
        return None
    if not package_path.is_file():
        errors.append(f"{relative}/{source_label}: {ref_field} does not exist: {ref}")
        return None
    package = load_review_package(package_path)
    if package is None:
        errors.append(f"{label}: review package must contain one valid JSON object")
        return None

    missing = [field for field in REVIEW_PACKAGE_FIELDS if field not in package]
    if missing:
        errors.append(f"{label}: missing required field(s): {', '.join(missing)}")
    unexpected = sorted(set(package) - set(REVIEW_PACKAGE_FIELDS))
    if unexpected:
        errors.append(f"{label}: unexpected top-level field(s): {', '.join(unexpected)}")
    if package.get("schema_version") != 1:
        errors.append(f"{label}: schema_version must be 1")
    if str(package.get("protocol_version") or "") != ADAPTIVE_REVIEW_PROTOCOL:
        errors.append(f'{label}: protocol_version must be "{ADAPTIVE_REVIEW_PROTOCOL}"')
    if str(package.get("task_id") or "") != task_dir.name:
        errors.append(f"{label}: task_id must match task directory")
    if str(package.get("checkpoint") or "") != checkpoint:
        errors.append(f"{label}: checkpoint must be {checkpoint}")
    package_version = str(package.get("package_version") or "")
    if not PACKAGE_VERSION_RE.fullmatch(package_version):
        errors.append(f"{label}: package_version must use vN format")
    filename_version = re.search(r"-v(\d+)\.json$", package_path.name)
    if filename_version is None:
        errors.append(f"{label}: review package filename must end in -vN.json")
    elif package_version != f"v{filename_version.group(1)}":
        errors.append(f"{label}: package_version must match the -vN.json filename")
    if not substantive_section_body(str(package.get("question") or "")):
        errors.append(f"{label}: question must be substantive and placeholder-free")

    covers = package.get("covers")
    if not isinstance(covers, list) or any(
        not isinstance(item, str) or not item.strip() for item in covers
    ):
        errors.append(f"{label}: covers must be a list of nonempty level tokens")
    else:
        normalized_covers = [item.strip() for item in covers]
        invalid_covers = sorted(set(normalized_covers) - VALID_REVIEW_COVERS)
        if invalid_covers:
            errors.append(f"{label}: covers contains invalid token(s): {', '.join(invalid_covers)}")
        if len(normalized_covers) != len(set(normalized_covers)):
            errors.append(f"{label}: covers must not contain duplicates")
        missing_covers = [item for item in expected_covers if item not in normalized_covers]
        if missing_covers:
            errors.append(
                f"{label}: covers must include {', '.join(expected_covers)} for checkpoint {checkpoint}"
            )

    for field in ("excluded", "limitations"):
        values = package.get(field)
        if not isinstance(values, list) or any(
            not isinstance(item, str) or not item.strip() for item in values
        ):
            errors.append(f"{label}: {field} must be a list of nonempty strings")
    if not isinstance(package.get("extensions"), dict):
        errors.append(f"{label}: extensions must be an object")

    surface_results: dict[str, list[tuple[str, str, bool, str | None]]] = {}
    for collection_name in ("binding_surfaces", "supporting_surfaces"):
        surfaces = package.get(collection_name)
        if not isinstance(surfaces, list):
            errors.append(f"{label}: {collection_name} must be a list")
            continue
        results: list[tuple[str, str, bool, str | None]] = []
        for index, surface in enumerate(surfaces):
            result = validate_review_surface(
                surface,
                index=index,
                collection_name=collection_name,
                package_label=label,
                task_dir=task_dir,
                project_root=project_root,
                errors=errors,
                require_identity=collection_name == "binding_surfaces",
            )
            if result is not None:
                results.append(result)
        surface_results[collection_name] = results

    binding_results = surface_results.get("binding_surfaces", [])
    all_surface_ids = [
        surface_id
        for results in surface_results.values()
        for surface_id, _, _, _ in results
        if surface_id
    ]
    if len(all_surface_ids) != len(set(all_surface_ids)):
        errors.append(
            f"{label}: surface id values must be unique across binding and supporting surfaces"
        )
    formal = force_formal or status in FORMAL_REVIEW_PACKAGE_STATUSES or status in {
        "direct_instruction",
        "confirmed",
        "ready",
        "accepted",
    }
    if formal:
        canonical_payload = {
            field: package.get(field) for field in CANONICAL_REVIEW_PACKAGE_FIELDS
        }
        if review_value_contains_placeholder(canonical_payload):
            errors.append(
                f"{label}: formal review package contains an unresolved placeholder in digest-covered content"
            )
    if formal and not binding_results:
        errors.append(f"{label}: formal status {status} requires at least one binding surface")
    if formal:
        for _, method, immutable, _ in binding_results:
            if method == "mutable" or not immutable:
                errors.append(
                    f"{label}: formal status {status} requires immutable binding-surface identities"
                )
                break

    if str(task.get("risk_level") or "") == "high":
        raw_binding_surfaces = package.get("binding_surfaces")
        has_external = isinstance(raw_binding_surfaces, list) and any(
            review_surface_requires_local_fallback(surface)
            for surface in raw_binding_surfaces
        )
        has_local_fallback = any(method == "file_sha256" for _, method, _, _ in binding_results)
        if has_external and not has_local_fallback:
            errors.append(
                f"{label}: high-risk package with an external binding surface requires a local file_sha256 binding fallback"
            )

    if checkpoint == "conformance" and status in {"matched", "accepted_with_differences"}:
        surfaces = package.get("binding_surfaces")
        approved_states: set[str] = set()
        implementation_states: set[str] = set()
        if isinstance(surfaces, list):
            for surface in surfaces:
                if not isinstance(surface, dict):
                    continue
                role = str(surface.get("role") or "")
                page_state = str(surface.get("page_state") or "").strip()
                if role == "approved-baseline":
                    if page_state:
                        approved_states.add(page_state)
                    else:
                        errors.append(
                            f"{label}: approved-baseline binding surface requires page_state"
                        )
                elif role == "implementation-capture":
                    if page_state:
                        implementation_states.add(page_state)
                    else:
                        errors.append(
                            f"{label}: implementation-capture binding surface requires page_state"
                        )
        if not approved_states or approved_states != implementation_states:
            errors.append(
                f"{label}: {status} conformance requires approved-baseline and implementation-capture binding surfaces sharing page_state values with identical sets"
            )

    raw_recorded_digest = str(expected_digest or "").strip()
    recorded_digest = raw_recorded_digest.lower()
    if not recorded_digest and status == "draft" and not force_formal:
        return package
    if raw_recorded_digest != recorded_digest or not SHA256_RE.fullmatch(recorded_digest):
        errors.append(f"{relative}/{source_label}: {ref_field} requires a valid canonical package SHA-256")
    else:
        observed_digest = canonical_review_package_digest(package)
        if recorded_digest != observed_digest:
            errors.append(
                f"{relative}/{source_label}: {ref_field} canonical package digest mismatch; approval or review state is invalid"
            )
    return package


def heading_anchor(text: str) -> str:
    heading = re.sub(r"`([^`]*)`", r"\1", text).lower()
    heading = re.sub(r"[^\w\s-]", "", heading, flags=re.UNICODE)
    return re.sub(r"[\s-]+", "-", heading).strip("-")


def markdown_heading_sections(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    entries: list[tuple[int, int, str]] = []
    heading_re = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
    fence: str | None = None
    for index, line in enumerate(lines):
        fence_match = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if fence_match:
            marker = fence_match.group(1)[0]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if fence is not None:
            continue
        match = heading_re.match(line)
        if not match:
            continue
        anchor = heading_anchor(match.group(2))
        if anchor:
            entries.append((index, len(match.group(1)), anchor))

    sections: dict[str, str] = {}
    for position, (line_index, level, anchor) in enumerate(entries):
        end = len(lines)
        for next_index, next_level, _ in entries[position + 1 :]:
            if next_level <= level:
                end = next_index
                break
        sections.setdefault(anchor, "\n".join(lines[line_index + 1 : end]))
    return sections


def markdown_heading_anchors(path: Path) -> set[str]:
    return set(markdown_heading_sections(path))


def validate_required_markdown_document(
    path: Path,
    project_root: Path,
    required_headings: tuple[str, ...],
    document_name: str,
    errors: list[str],
    governance_protocol: str = SUPPORTED_GOVERNANCE_PROTOCOL,
) -> None:
    label = str(path.relative_to(project_root))
    if path.is_symlink() or not path.is_file():
        errors.append(f"{label}: protocol {governance_protocol} requires a regular {document_name} file")
        return
    sections = markdown_heading_sections(path)
    missing = [heading for heading in required_headings if heading_anchor(heading) not in sections]
    if missing:
        errors.append(
            f"{label}: protocol {governance_protocol} {document_name} missing required heading(s): {', '.join(missing)}"
        )
    empty = [
        heading
        for heading in required_headings
        if heading_anchor(heading) in sections
        and not substantive_section_body(sections[heading_anchor(heading)])
    ]
    if empty:
        errors.append(
            f"{label}: protocol {governance_protocol} {document_name} section(s) lack substantive content: {', '.join(empty)}"
        )
    duplicates = duplicate_required_bodies(required_headings, sections, markdown=True)
    if duplicates:
        errors.append(
            f"{label}: protocol {governance_protocol} {document_name} sections reuse identical normalized body content: {', '.join(duplicates)}"
        )


def substantive_evidence_file(path: Path) -> bool:
    if path.is_symlink() or not path.is_file() or path.name == ".gitkeep":
        return False
    try:
        size = path.stat().st_size
    except OSError:
        return False
    text_suffixes = {
        ".csv",
        ".html",
        ".json",
        ".log",
        ".md",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
    if path.suffix.lower() not in text_suffixes:
        return size >= 512
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    if path.suffix.lower() == ".md":
        visible = markdown_visible_body(content)
    elif path.suffix.lower() == ".html":
        parser = VisibleTextParser()
        parser.feed(content)
        parser.close()
        visible = " ".join(parser.parts)
    else:
        visible = content
    return substantive_section_body(visible)


def validate_decision_reference(
    task_dir: Path,
    project_root: Path,
    raw_ref: Any,
    field: str,
    errors: list[str],
    source_label: str = "design/design.yaml",
) -> tuple[Path, str] | None:
    relative = task_dir.relative_to(project_root)
    text = str(raw_ref or "").strip()
    path_text, separator, anchor = text.partition("#")
    if not separator or not path_text or not anchor:
        errors.append(
            f"{relative}/{source_label}: {field} must reference a heading in task-local decisions.md"
        )
        return None
    decision_path = resolve_task_path(
        task_dir,
        project_root,
        path_text,
        field,
        errors,
        source_label,
    )
    if decision_path is None:
        return None
    if (
        decision_path.name != "decisions.md"
        or not decision_path.is_file()
        or decision_path.is_symlink()
    ):
        errors.append(
            f"{relative}/{source_label}: {field} must reference task-local decisions.md"
        )
        return None
    sections = markdown_heading_sections(decision_path)
    if anchor.lower() not in sections:
        errors.append(
            f"{relative}/{source_label}: {field} heading '#{anchor}' does not exist in decisions.md"
        )
        return None
    return decision_path, sections[anchor.lower()]


def artifact_marker_version(path: Path) -> str | None:
    if path.suffix.lower() == ".json":
        package = load_review_package(path)
        if package is None:
            return None
        version = str(package.get("package_version") or "").strip().lower()
        return version if PACKAGE_VERSION_RE.fullmatch(version) else None
    content = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".html":
        match = re.search(
            r"data-artifact-version\s*=\s*['\"](v[1-9][0-9]*)['\"]",
            content,
            re.IGNORECASE,
        )
    else:
        match = MARKDOWN_VERSION_MARKER_RE.search(content)
    return match.group(1).lower() if match else None


def validate_decision_binding(
    task_dir: Path,
    project_root: Path,
    decision_ref: Any,
    decision_ref_field: str,
    source_label: str,
    artifact_ref: Any,
    artifact_sha: Any,
    decision_kind: str,
    gate: str,
    errors: list[str],
) -> None:
    relative = task_dir.relative_to(project_root)
    label = f"{relative}/{source_label}"
    referenced = validate_decision_reference(
        task_dir,
        project_root,
        decision_ref,
        decision_ref_field,
        errors,
        source_label,
    )
    if referenced is None:
        return
    _, section = referenced
    visible_section = markdown_visible_body(section)
    outcome_lines = DECISION_OUTCOME_PREFIX_RE.findall(visible_section)
    canonical_outcomes = DECISION_OUTCOME_LINE_RE.findall(visible_section)
    expected_outcome = DECISION_KIND_OUTCOMES.get(decision_kind, "")
    if (
        len(outcome_lines) != 1
        or len(canonical_outcomes) != 1
        or canonical_outcomes[0] != expected_outcome
    ):
        errors.append(
            f"{label}: {decision_ref_field} heading requires exactly one canonical 'Decision outcome: {expected_outcome}' visible line; local decision records are trusted input, not identity or authorship authentication"
        )
    natural_language = DECISION_OUTCOME_PREFIX_RE.sub("", visible_section)
    if not substantive_section_body(natural_language):
        errors.append(
            f"{label}: {decision_ref_field} heading requires a substantive visible natural-language decision in addition to the canonical outcome and binding"
        )
    matches = list(DECISION_BINDING_RE.finditer(section))
    if len(matches) != 1:
        errors.append(
            f"{label}: {decision_ref_field} heading must contain exactly one project-memory-decision-binding block"
        )
        return

    values: dict[str, str] = {}
    malformed = False
    for raw_line in matches[0].group("body").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ":" not in line:
            malformed = True
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        if key in values:
            malformed = True
        values[key] = value.strip()
    if malformed or set(values) != set(DECISION_BINDING_FIELDS):
        errors.append(
            f"{label}: {decision_ref_field} has a malformed decision binding; required fields are {', '.join(DECISION_BINDING_FIELDS)}"
        )
        return

    artifact = resolve_task_path(
        task_dir,
        project_root,
        artifact_ref,
        decision_ref_field,
        errors,
        source_label,
    )
    if artifact is None or not artifact.is_file():
        return
    canonical_path = artifact.relative_to(task_dir.resolve()).as_posix()
    version = artifact_marker_version(artifact)
    expected_sha = str(artifact_sha or "").strip().lower()
    expected = {
        "task-id": task_dir.name,
        "decision-kind": decision_kind,
        "artifact-path": canonical_path,
        "artifact-version": version or "",
        "artifact-sha256": expected_sha,
        "gate": gate,
        "decision-outcome": expected_outcome,
    }
    if values.get("decision-kind") not in VALID_DECISION_KINDS:
        errors.append(f"{label}: {decision_ref_field} binding has invalid decision-kind")
    for field, expected_value in expected.items():
        observed = values.get(field, "")
        if field == "artifact-sha256":
            observed = observed.lower()
        if observed != expected_value:
            errors.append(
                f"{label}: {decision_ref_field} decision binding {field} does not match the current artifact"
            )
    scope = values.get("scope", "").strip()
    if not substantive_section_body(scope):
        errors.append(
            f"{label}: {decision_ref_field} decision binding scope must be substantive and placeholder-free"
        )
    if SHA256_RE.fullmatch(expected_sha):
        if artifact.suffix.lower() == ".json":
            package = load_review_package(artifact)
            observed_sha = (
                canonical_review_package_digest(package) if package is not None else None
            )
        else:
            observed_sha = sha256(artifact)
        if expected_sha != observed_sha:
            errors.append(
                f"{label}: {decision_ref_field} decision binding cannot authorize an artifact whose recorded SHA-256 is stale"
            )


def validate_html_artifact(
    task_dir: Path,
    project_root: Path,
    ref: Any,
    expected_sha: Any,
    ref_field: str,
    artifact_kind: str,
    errors: list[str],
    extra_required_headings: tuple[str, ...] = (),
    require_capture_pair: bool = False,
    enforce_content_contract: bool = False,
) -> None:
    relative = task_dir.relative_to(project_root)
    artifact = resolve_task_path(task_dir, project_root, ref, ref_field, errors)
    if artifact is None:
        return
    if artifact.suffix.lower() != ".html":
        errors.append(f"{relative}/design/design.yaml: {ref_field} must reference an HTML file")
        return
    if not artifact.is_file():
        errors.append(f"{relative}/design/design.yaml: {ref_field} does not exist: {ref}")
        return
    if artifact.is_symlink():
        errors.append(f"{relative}/design/design.yaml: {ref_field} must not be a symlink")
        return

    content = artifact.read_text(encoding="utf-8")
    if len(content.strip()) < 200 or "<html" not in content.lower():
        errors.append(f"{relative}/design/design.yaml: {ref_field} is not substantive HTML")
    for pattern in PLACEHOLDER_PATTERNS:
        if pattern.search(content):
            errors.append(
                f"{relative}/design/design.yaml: {ref_field} contains unresolved template placeholder"
            )
            break
    if REMOTE_HTML_RE.search(content):
        errors.append(
            f"{relative}/design/design.yaml: {ref_field} is not self-contained and offline"
        )

    if enforce_content_contract:
        parser = VisibleHeadingParser()
        try:
            parser.feed(content)
            parser.close()
        except ValueError:
            errors.append(f"{relative}/design/design.yaml: {ref_field} contains malformed HTML")
        sections = html_heading_sections(parser)
        required_headings = REQUIRED_VISUAL_HEADINGS.get(artifact_kind, ()) + extra_required_headings
        missing_headings = [
            heading for heading in required_headings if normalized_heading(heading) not in sections
        ]
        if missing_headings:
            errors.append(
                f"{relative}/design/design.yaml: {ref_field} missing required visible heading(s): {', '.join(missing_headings)}"
            )
        empty_headings = [
            heading
            for heading in required_headings
            if normalized_heading(heading) in sections
            and not substantive_section_body(sections[normalized_heading(heading)])
        ]
        if empty_headings:
            errors.append(
                f"{relative}/design/design.yaml: {ref_field} required section(s) lack substantive body: {', '.join(empty_headings)}"
            )
        duplicate_headings = duplicate_required_bodies(required_headings, sections)
        if duplicate_headings:
            errors.append(
                f"{relative}/design/design.yaml: {ref_field} required sections reuse identical normalized body content: {', '.join(duplicate_headings)}"
            )

        if require_capture_pair:
            captures: dict[str, set[str]] = {}
            for side, state, has_payload in parser.capture_payloads:
                if side not in {"approved", "implementation"} or not state or not has_payload:
                    errors.append(
                        f"{relative}/design/design.yaml: {ref_field} conformance captures require a valid side and data-page-state; approved requires a substantive inline SVG or raster data URI, while implementation requires a decodable raster data URI of at least 160x240 and 512 bytes"
                    )
                    continue
                captures.setdefault(state, set()).add(side)
            if not any(sides == {"approved", "implementation"} for sides in captures.values()):
                errors.append(
                    f"{relative}/design/design.yaml: {ref_field} requires a self-contained approved/implementation capture pair for the same page state"
                )

    marker_patterns = (
        rf"data-project-memory-artifact\s*=\s*['\"]{re.escape(artifact_kind)}['\"]",
        rf"data-task-id\s*=\s*['\"]{re.escape(task_dir.name)}['\"]",
        r"data-artifact-version\s*=\s*['\"](v[1-9][0-9]*)['\"]",
    )
    marker_names = ("artifact", "task", "version")
    version_match: re.Match[str] | None = None
    for marker_name, pattern in zip(marker_names, marker_patterns):
        match = re.search(pattern, content, re.IGNORECASE)
        if not match:
            errors.append(
                f"{relative}/design/design.yaml: {ref_field} missing {marker_name} marker"
            )
        if marker_name == "version":
            version_match = match

    filename_version = re.search(r"[-_]v([1-9][0-9]*)\.html$", artifact.name, re.IGNORECASE)
    if filename_version and version_match:
        expected_version = f"v{filename_version.group(1)}".lower()
        if version_match.group(1).lower() != expected_version:
            errors.append(
                f"{relative}/design/design.yaml: {ref_field} version marker does not match filename"
            )

    recorded_sha = str(expected_sha or "").strip().lower()
    if not SHA256_RE.fullmatch(recorded_sha):
        errors.append(f"{relative}/design/design.yaml: {ref_field} requires a valid SHA-256")
    else:
        observed_sha = sha256(artifact)
        if recorded_sha != observed_sha:
            errors.append(
                f"{relative}/design/design.yaml: {ref_field} SHA-256 mismatch; approval is invalid"
            )


def validate_alignment_artifact(
    task: dict[str, Any],
    task_dir: Path,
    project_root: Path,
    alignment_source: str,
    ref: Any,
    expected_sha: Any,
    ref_field: str,
    artifact_kind: str,
    errors: list[str],
) -> None:
    relative = task_dir.relative_to(project_root)
    label = f"{relative}/{alignment_source}"
    artifact = resolve_task_path(
        task_dir,
        project_root,
        ref,
        ref_field,
        errors,
        alignment_source,
    )
    if artifact is None:
        return
    suffix = artifact.suffix.lower()
    if suffix not in {".md", ".html"}:
        errors.append(f"{label}: {ref_field} must reference a Markdown or HTML file")
        return
    if not artifact.is_file():
        errors.append(f"{label}: {ref_field} does not exist: {ref}")
        return

    content = artifact.read_text(encoding="utf-8")
    if len(content.strip()) < 120:
        errors.append(f"{label}: {ref_field} is not a substantive human-alignment artifact")
    for pattern in PLACEHOLDER_PATTERNS:
        if pattern.search(content):
            errors.append(f"{label}: {ref_field} contains unresolved template placeholder")
            break

    version: str | None = None
    visible_headings: set[str] = set()
    section_bodies: dict[str, str] = {}
    if suffix == ".html":
        if "<html" not in content.lower():
            errors.append(f"{label}: {ref_field} is not substantive HTML")
        if REMOTE_HTML_RE.search(content):
            errors.append(f"{label}: {ref_field} is not self-contained and offline")
        marker_patterns = (
            (
                "artifact",
                rf"data-project-memory-artifact\s*=\s*['\"]{re.escape(artifact_kind)}['\"]",
            ),
            ("task", rf"data-task-id\s*=\s*['\"]{re.escape(task_dir.name)}['\"]"),
            ("version", r"data-artifact-version\s*=\s*['\"](v[1-9][0-9]*)['\"]"),
        )
        for marker_name, pattern in marker_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if not match:
                errors.append(f"{label}: {ref_field} missing {marker_name} marker")
            elif marker_name == "version":
                version = match.group(1).lower()
        heading_parser = VisibleHeadingParser()
        try:
            heading_parser.feed(content)
        except ValueError:
            errors.append(f"{label}: {ref_field} contains malformed HTML")
        visible_headings = {
            re.sub(r"\s+", " ", heading).strip().lower()
            for heading in heading_parser.headings
            if heading.strip()
        }
        section_bodies = html_heading_sections(heading_parser)
    else:
        artifact_marker = MARKDOWN_ARTIFACT_MARKER_RE.search(content)
        task_marker = MARKDOWN_TASK_MARKER_RE.search(content)
        version_marker = MARKDOWN_VERSION_MARKER_RE.search(content)
        if not artifact_marker or artifact_marker.group(1).strip().lower() != artifact_kind:
            errors.append(f"{label}: {ref_field} missing artifact marker '{artifact_kind}'")
        if not task_marker or task_marker.group(1).strip() != task_dir.name:
            errors.append(f"{label}: {ref_field} missing task marker '{task_dir.name}'")
        if not version_marker:
            errors.append(f"{label}: {ref_field} missing version marker")
        else:
            version = version_marker.group(1).lower()

        visible_headings = markdown_visible_headings(content)
        section_bodies = {
            heading_anchor_value: body
            for heading_anchor_value, body in markdown_heading_sections(artifact).items()
        }
        if (
            ref_field == "start_ref"
            and str(task.get("alignment_mode") or "") == "diagram"
            and not re.search(r"```mermaid\s*\n", content, re.IGNORECASE)
        ):
            errors.append(f"{label}: diagram start_ref requires a fenced Mermaid diagram")

    missing_headings = [
        heading
        for heading in REQUIRED_ALIGNMENT_HEADINGS[artifact_kind]
        if heading.lower() not in visible_headings
    ]
    if missing_headings:
        errors.append(
            f"{label}: {ref_field} missing required visible heading(s): {', '.join(missing_headings)}"
        )
    empty_headings: list[str] = []
    for heading in REQUIRED_ALIGNMENT_HEADINGS[artifact_kind]:
        key = normalized_heading(heading) if suffix == ".html" else heading_anchor(heading)
        if key in section_bodies and not substantive_section_body(section_bodies[key]):
            empty_headings.append(heading)
    if empty_headings:
        errors.append(
            f"{label}: {ref_field} required section(s) lack substantive body: {', '.join(empty_headings)}"
        )
    duplicate_headings = duplicate_required_bodies(
        REQUIRED_ALIGNMENT_HEADINGS[artifact_kind],
        section_bodies,
        markdown=suffix != ".html",
    )
    if duplicate_headings:
        errors.append(
            f"{label}: {ref_field} required sections reuse identical normalized body content: {', '.join(duplicate_headings)}"
        )

    filename_version = re.search(r"[-_]v([1-9][0-9]*)\.(?:md|html)$", artifact.name, re.IGNORECASE)
    if not filename_version:
        errors.append(f"{label}: {ref_field} filename must include a version such as -v1")
    elif version and version != f"v{filename_version.group(1)}".lower():
        errors.append(f"{label}: {ref_field} version marker does not match filename")

    recorded_sha = str(expected_sha or "").strip().lower()
    if not SHA256_RE.fullmatch(recorded_sha):
        errors.append(f"{label}: {ref_field} requires a valid SHA-256")
    elif recorded_sha != sha256(artifact):
        errors.append(f"{label}: {ref_field} SHA-256 mismatch; confirmation is invalid")


def validate_alignment_checkpoint(
    task: dict[str, Any],
    task_dir: Path,
    project_root: Path,
    alignment_source: str,
    ref: Any,
    expected_sha: Any,
    ref_field: str,
    artifact_kind: str,
    checkpoint: str,
    covers: tuple[str, ...],
    status: str,
    governance_protocol: str,
    errors: list[str],
) -> None:
    if governance_protocol == ADAPTIVE_REVIEW_PROTOCOL:
        validate_review_package(
            task,
            task_dir,
            project_root,
            ref,
            expected_sha,
            ref_field,
            checkpoint,
            covers,
            status,
            errors,
            source_label=alignment_source,
            force_formal=(
                checkpoint == "readout"
                and str(task.get("status") or "") in {"reviewing", "verifying", "done"}
            ),
        )
    else:
        validate_alignment_artifact(
            task,
            task_dir,
            project_root,
            alignment_source,
            ref,
            expected_sha,
            ref_field,
            artifact_kind,
            errors,
        )


def validate_human_confirmation(
    alignment: dict[str, Any],
    prefix: str,
    label: str,
    task_dir: Path,
    project_root: Path,
    alignment_source: str,
    errors: list[str],
) -> None:
    identity_field = {
        "start": "start_authority_by",
        "decision": "decision_confirmed_by",
        "completion": "completion_accepted_by",
    }[prefix]
    time_field = {
        "start": "start_authority_at",
        "decision": "decision_confirmed_at",
        "completion": "completion_accepted_at",
    }[prefix]
    ref_field = {
        "start": "start_authority_ref",
        "decision": "decision_confirmation_ref",
        "completion": "completion_acceptance_ref",
    }[prefix]
    artifact_ref_field = {
        "start": "start_ref",
        "decision": "decision_ref",
        "completion": "readout_ref",
    }[prefix]
    artifact_sha_field = {
        "start": "start_sha256",
        "decision": "decision_sha256",
        "completion": "readout_sha256",
    }[prefix]
    decision_kind = {
        "start": "start-direction"
        if str(alignment.get("start_status") or "") == "direct_instruction"
        else "start-confirmation",
        "decision": "h2-confirmation",
        "completion": "completion-acceptance",
    }[prefix]
    gate = {
        "start": "human-start-alignment",
        "decision": "human-decision-checkpoint",
        "completion": "human-readout",
    }[prefix]
    action = (
        "acceptance"
        if prefix == "completion"
        else "authority record"
        if prefix == "start" and str(alignment.get("start_status") or "") == "direct_instruction"
        else "confirmation"
    )
    if not is_human_identity(alignment.get(identity_field)):
        errors.append(
            f"{label}: {action} requires a declared human identity in {identity_field}; this trusted local record is not identity authentication"
        )
    if not is_approval_time(alignment.get(time_field)):
        errors.append(f"{label}: {action} requires a time in {time_field}")
    decision_ref = alignment.get(ref_field)
    if not str(decision_ref or "").strip():
        errors.append(f"{label}: {action} requires a decision reference in {ref_field}")
    else:
        validate_decision_binding(
            task_dir,
            project_root,
            decision_ref,
            ref_field,
            alignment_source,
            alignment.get(artifact_ref_field),
            alignment.get(artifact_sha_field),
            decision_kind,
            gate,
            errors,
        )


def validate_alignment_governance(
    task: dict[str, Any],
    task_dir: Path,
    project_root: Path,
    errors: list[str],
    *,
    governance_protocol: str = SUPPORTED_GOVERNANCE_PROTOCOL,
) -> None:
    relative = task_dir.relative_to(project_root)
    raw_alignment_ref = task.get("alignment_governance_ref")
    alignment_path = resolve_task_path(
        task_dir,
        project_root,
        raw_alignment_ref,
        "alignment_governance_ref",
        errors,
        "task.yaml",
    )
    if alignment_path is None:
        return
    if alignment_path.name != "alignment.yaml" or not alignment_path.is_file():
        errors.append(
            f"{relative}/task.yaml: alignment_governance_ref must reference an existing alignment.yaml"
        )
        return
    alignment_source = str(alignment_path.relative_to(task_dir))
    label = str(alignment_path.relative_to(project_root))
    try:
        alignment = load_flat_yaml(alignment_path)
    except ValueError as exc:
        errors.append(f"{label}: {exc}")
        return

    for key in REQUIRED_ALIGNMENT_KEYS:
        if key not in alignment:
            errors.append(f"{label}: missing required field '{key}'")
    expected_schema = 2 if governance_protocol == ADAPTIVE_REVIEW_PROTOCOL else 1
    if alignment.get("schema_version") != expected_schema:
        errors.append(f"{label}: schema_version must be {expected_schema}")
    if str(alignment.get("protocol_version") or "") != governance_protocol:
        errors.append(f'{label}: protocol_version must be "{governance_protocol}"')
    if governance_protocol == ADAPTIVE_REVIEW_PROTOCOL:
        if str(alignment.get("review_model") or "") != "adaptive":
            errors.append(f"{label}: review_model must be adaptive")
    if str(alignment.get("task_id") or "") != task_dir.name:
        errors.append(f"{label}: task_id must match task directory")

    risk_level = str(alignment.get("risk_level") or "")
    if risk_level not in VALID_RISK_LEVELS:
        errors.append(f"{label}: invalid risk_level '{risk_level}'")
    if risk_level != str(task.get("risk_level") or ""):
        errors.append(f"{label}: risk_level must match task.yaml")

    effect_floors: list[str] = []
    for effect_field, allowed_values in EFFECT_FIELDS.items():
        effect_value = str(alignment.get(effect_field) or "")
        if effect_value not in allowed_values:
            errors.append(
                f"{label}: invalid {effect_field} '{effect_value}'; expected one of {', '.join(allowed_values)}"
            )
        else:
            effect_floors.append(allowed_values[effect_value])
    effect_floor = highest_risk(effect_floors)

    risk_factors = alignment.get("risk_factors")
    factor_floor = "low"
    if not isinstance(risk_factors, list):
        errors.append(f"{label}: risk_factors must be a list")
    elif not [item for item in risk_factors if str(item).strip()]:
        errors.append(f"{label}: risk_factors must contain at least one structured factor")
    else:
        floors: list[str] = []
        invalid_factors: list[str] = []
        for item in risk_factors:
            factor = str(item).strip()
            floor = risk_factor_floor(factor)
            if floor is None:
                invalid_factors.append(factor)
            else:
                floors.append(floor)
        if invalid_factors:
            errors.append(
                f"{label}: risk_factors contains unsupported value(s): {', '.join(invalid_factors)}"
            )
        if floors:
            factor_floor = max(floors, key=lambda value: RISK_LEVEL_RANK[value])

    if RISK_LEVEL_RANK[factor_floor] < RISK_LEVEL_RANK[effect_floor]:
        errors.append(
            f"{label}: risk_factors floor {factor_floor} is below structured effect floor {effect_floor}; risk_factors may raise but must not understate recorded effects"
        )

    goal_signals = goal_high_risk_signals(task.get("goal"))
    goal_floor = "high" if goal_signals else "low"
    if goal_signals and (
        effect_floor != "high" or factor_floor != "high"
    ):
        errors.append(
            f"{label}: task goal contains high-confidence high-risk signal(s) ({', '.join(goal_signals)}) that contradict structured effects or risk_factors; correct the authoritative records because this safety check cannot be bypassed by risk_downgrade_ref"
        )
    hard_floor = highest_risk([effect_floor, goal_floor])
    effective_floor = highest_risk([effect_floor, factor_floor, goal_floor])

    for boolean_field in (
        "material_deviation",
        "waiver_used",
        "unresolved_risk",
        "h2_required",
    ):
        if not isinstance(alignment.get(boolean_field), bool):
            errors.append(f"{label}: {boolean_field} must be true or false")

    status = str(task.get("status") or "")
    start_status = str(alignment.get("start_status") or "")
    if start_status not in VALID_START_STATUSES:
        errors.append(f"{label}: invalid start_status '{start_status}'")
    else:
        validate_alignment_checkpoint(
            task,
            task_dir,
            project_root,
            alignment_source,
            alignment.get("start_ref"),
            alignment.get("start_sha256"),
            "start_ref",
            "human-start-alignment",
            "start",
            ("H0", "H1"),
            start_status,
            governance_protocol,
            errors,
        )
        if start_status in {"direct_instruction", "confirmed"}:
            validate_human_confirmation(
                alignment,
                "start",
                label,
                task_dir,
                project_root,
                alignment_source,
                errors,
            )
    if start_status == "direct_instruction" and (
        risk_level != "low" or effective_floor != "low"
    ):
        errors.append(
            f"{label}: direct_instruction is only valid when declared and effective risk are low"
        )
    declared_below_hard_floor = (
        risk_level in RISK_LEVEL_RANK
        and RISK_LEVEL_RANK[risk_level] < RISK_LEVEL_RANK[hard_floor]
    )
    if declared_below_hard_floor:
        errors.append(
            f"{label}: risk_level {risk_level} is below structured effect/goal floor {hard_floor}; update the task risk because this floor cannot be downgraded"
        )
    declared_below_floor = (
        not declared_below_hard_floor
        and risk_level in RISK_LEVEL_RANK
        and RISK_LEVEL_RANK[risk_level] < RISK_LEVEL_RANK[factor_floor]
    )
    downgrade_ref = alignment.get("risk_downgrade_ref")
    if declared_below_floor:
        if start_status != "confirmed":
            errors.append(
                f"{label}: risk_level {risk_level} below factor floor {factor_floor} requires start_status confirmed"
            )
        if not str(downgrade_ref or "").strip():
            errors.append(
                f"{label}: risk_level {risk_level} below factor floor {factor_floor} requires risk_downgrade_ref"
            )
        else:
            validate_decision_binding(
                task_dir,
                project_root,
                downgrade_ref,
                "risk_downgrade_ref",
                alignment_source,
                alignment.get("start_ref"),
                alignment.get("start_sha256"),
                "risk-downgrade",
                "risk-classification",
                errors,
            )
    elif str(downgrade_ref or "").strip():
        errors.append(f"{label}: risk_downgrade_ref is only valid below the factor-derived risk floor")
    if status in EXECUTION_STATES:
        permitted_start = (
            {"direct_instruction", "confirmed"}
            if risk_level == "low" and effective_floor == "low"
            else {"confirmed"}
        )
        if start_status not in permitted_start:
            errors.append(
                f"{label}: declared {risk_level} / effective {effective_floor} risk status {status} requires "
                + (
                    "confirmed or direct_instruction start alignment"
                    if effective_floor == "low" and risk_level == "low"
                    else "confirmed start alignment"
                )
            )

    decision_status = str(alignment.get("decision_status") or "")
    if decision_status not in VALID_DECISION_STATUSES:
        errors.append(f"{label}: invalid decision_status '{decision_status}'")
    elif decision_status != "not_required":
        validate_alignment_checkpoint(
            task,
            task_dir,
            project_root,
            alignment_source,
            alignment.get("decision_ref"),
            alignment.get("decision_sha256"),
            "decision_ref",
            "human-decision-checkpoint",
            "decision",
            ("H2",),
            decision_status,
            governance_protocol,
            errors,
        )
        if decision_status == "confirmed":
            validate_human_confirmation(
                alignment,
                "decision",
                label,
                task_dir,
                project_root,
                alignment_source,
                errors,
            )
    if status in EXECUTION_STATES and decision_status in {
        "draft",
        "awaiting_human",
        "changes_requested",
    }:
        errors.append(f"{label}: status {status} cannot proceed with decision_status {decision_status}")

    readout_status = str(alignment.get("readout_status") or "")
    if readout_status not in VALID_READOUT_STATUSES:
        errors.append(f"{label}: invalid readout_status '{readout_status}'")
    elif readout_status != "not_started":
        validate_alignment_checkpoint(
            task,
            task_dir,
            project_root,
            alignment_source,
            alignment.get("readout_ref"),
            alignment.get("readout_sha256"),
            "readout_ref",
            "human-readout",
            "readout",
            ("HumanReadout", "H3"),
            readout_status,
            governance_protocol,
            errors,
        )
        if readout_status == "accepted":
            validate_human_confirmation(
                alignment,
                "completion",
                label,
                task_dir,
                project_root,
                alignment_source,
                errors,
            )

    if status == "reviewing" and readout_status == "not_started":
        errors.append(f"{label}: status reviewing requires a versioned Human Readout")
    if status == "verifying" and readout_status not in {"ready", "awaiting_human", "accepted"}:
        errors.append(
            f"{label}: status verifying requires readout_status ready, awaiting_human, or accepted"
        )
    if status == "done" and readout_status not in {"ready", "accepted"}:
        errors.append(f"{label}: status done requires readout_status ready or accepted")

    material_deviation = alignment.get("material_deviation") is True
    waiver_used = alignment.get("waiver_used") is True
    unresolved_risk = alignment.get("unresolved_risk") is True
    h2_required = alignment.get("h2_required") is True
    if (material_deviation or waiver_used) and not h2_required:
        errors.append(
            f"{label}: material_deviation or waiver_used requires h2_required true"
        )
    if h2_required and decision_status == "not_required":
        errors.append(
            f"{label}: h2_required true requires a versioned H2 decision"
        )
    if not h2_required and decision_status != "not_required":
        errors.append(
            f"{label}: decision_status {decision_status} requires h2_required true"
        )
    if status in EXECUTION_STATES and (
        h2_required or material_deviation or waiver_used
    ) and decision_status != "confirmed":
        errors.append(
            f"{label}: H2-triggered status {status} requires decision_status confirmed"
        )
    if status == "done" and (
        risk_level == "high" or material_deviation or waiver_used or unresolved_risk
    ) and readout_status != "accepted":
        errors.append(
            f"{label}: high-risk or exceptional done task requires human-accepted readout"
        )


def validate_approval(
    design: dict[str, Any],
    prefix: str,
    design_label: str,
    task_dir: Path,
    project_root: Path,
    errors: list[str],
    enforce_protocol_21: bool,
) -> None:
    if not is_human_identity(design.get(f"{prefix}_approved_by")):
        errors.append(
            f"{design_label}: approved {prefix} gate requires a human approver declaration; this trusted local record is not identity authentication"
        )
    if not is_approval_time(design.get(f"{prefix}_approved_at")):
        errors.append(f"{design_label}: approved {prefix} gate requires an approval time")
    approval_ref = design.get(f"{prefix}_approval_ref")
    if not str(approval_ref or "").strip():
        errors.append(f"{design_label}: approved {prefix} gate requires a decision reference")
    elif enforce_protocol_21:
        validate_decision_binding(
            task_dir,
            project_root,
            approval_ref,
            f"{prefix}_approval_ref",
            "design/design.yaml",
            design.get(f"{prefix}_ref"),
            design.get(f"{prefix}_sha256"),
            f"{prefix}-approval",
            f"{prefix}-alignment",
            errors,
        )
    else:
        validate_decision_reference(
            task_dir,
            project_root,
            approval_ref,
            f"{prefix}_approval_ref",
            errors,
        )


def validate_design_governance(
    task: dict[str, Any],
    task_dir: Path,
    project_root: Path,
    errors: list[str],
    governance_protocol: str | None,
) -> None:
    enforce_managed_protocol = governance_protocol in SUPPORTED_GOVERNANCE_PROTOCOLS
    adaptive_review = governance_protocol == ADAPTIVE_REVIEW_PROTOCOL
    relative = task_dir.relative_to(project_root)
    raw_design_ref = task.get("design_governance_ref")
    design_path = resolve_task_path(
        task_dir,
        project_root,
        raw_design_ref,
        "design_governance_ref",
        errors,
    )
    if design_path is None:
        return
    if design_path.name != "design.yaml" or not design_path.is_file():
        errors.append(f"{relative}/task.yaml: design_governance_ref must reference an existing design.yaml")
        return
    try:
        design = load_flat_yaml(design_path)
    except ValueError as exc:
        errors.append(f"{design_path.relative_to(project_root)}: {exc}")
        return

    design_label = str(design_path.relative_to(project_root))
    for key in REQUIRED_DESIGN_KEYS:
        if key not in design:
            errors.append(f"{design_label}: missing required field '{key}'")

    expected_schema = 3 if adaptive_review else 2
    if design.get("schema_version") != expected_schema:
        errors.append(f"{design_label}: schema_version must be {expected_schema}")
    if adaptive_review:
        if str(design.get("protocol_version") or "") != ADAPTIVE_REVIEW_PROTOCOL:
            errors.append(
                f'{design_label}: protocol_version must be "{ADAPTIVE_REVIEW_PROTOCOL}"'
            )
        if str(design.get("review_model") or "") != "adaptive":
            errors.append(f"{design_label}: review_model must be adaptive")
    if str(design.get("task_id") or "") != task_dir.name:
        errors.append(f"{design_label}: task_id must match task directory")

    gate_profile = str(design.get("gate_profile") or "")
    if gate_profile not in VALID_GATE_PROFILES:
        errors.append(f"{design_label}: invalid gate_profile '{gate_profile}'")
    for maturity_field in ("target_maturity", "current_maturity"):
        maturity = str(design.get(maturity_field) or "")
        if maturity not in VALID_MATURITY:
            errors.append(f"{design_label}: invalid {maturity_field} '{maturity}'")

    gate_statuses: dict[str, str] = {}
    for prefix, artifact_kind in (
        ("experience", "experience-alignment"),
        ("visual", "visual-alignment"),
    ):
        status = str(design.get(f"{prefix}_status") or "")
        gate_statuses[prefix] = status
        if status not in VALID_GATE_STATUSES:
            errors.append(f"{design_label}: invalid {prefix}_status '{status}'")
            continue
        if status in ARTIFACT_GATE_STATUSES:
            if adaptive_review:
                validate_review_package(
                    task,
                    task_dir,
                    project_root,
                    design.get(f"{prefix}_ref"),
                    design.get(f"{prefix}_sha256"),
                    f"{prefix}_ref",
                    prefix,
                    ("L1", "L2", "L3", "L4")
                    if prefix == "visual"
                    and (
                        gate_profile == "one_gate"
                        or (
                            gate_profile == "design_only"
                            and str(design.get("experience_status") or "")
                            == "not_required"
                        )
                    )
                    else ("L1", "L2", "L3")
                    if prefix == "experience"
                    else ("L4",),
                    status,
                    errors,
                    source_label="design/design.yaml",
                )
            else:
                validate_html_artifact(
                    task_dir,
                    project_root,
                    design.get(f"{prefix}_ref"),
                    design.get(f"{prefix}_sha256"),
                    f"{prefix}_ref",
                    artifact_kind,
                    errors,
                    ONE_GATE_VISUAL_HEADINGS
                    if enforce_managed_protocol
                    and prefix == "visual"
                    and gate_profile == "one_gate"
                    else (),
                    enforce_content_contract=enforce_managed_protocol,
                )
        if status == "approved":
            validate_approval(
                design,
                prefix,
                design_label,
                task_dir,
                project_root,
                errors,
                enforce_managed_protocol,
            )

    if gate_profile == "one_gate" and gate_statuses.get("experience") != "not_required":
        errors.append(f"{design_label}: one_gate requires experience_status not_required")
    if gate_profile == "two_gate" and gate_statuses.get("experience") == "not_required":
        errors.append(f"{design_label}: {gate_profile} requires an experience gate")
    if (
        gate_profile in {"two_gate", "design_only"}
        and gate_statuses.get("experience") != "not_required"
        and gate_statuses.get("visual") in ARTIFACT_GATE_STATUSES
        and gate_statuses.get("experience") != "approved"
    ):
        errors.append(
            f"{design_label}: {gate_profile} visual gate cannot start before the experience gate is approved"
        )
    if gate_profile in VALID_GATE_PROFILES and gate_statuses.get("visual") == "not_required":
        errors.append(f"{design_label}: {gate_profile} requires a visual gate")

    status = str(task.get("status") or "")
    priority = str(task.get("priority") or "")
    waiver_ref = str(design.get("emergency_waiver_ref") or "").strip()
    emergency_bypass = status in {"approved", "implementing"} and priority == "P0" and bool(waiver_ref)

    required_gates = (
        ["visual"]
        if gate_profile == "one_gate"
        or (
            gate_profile == "design_only"
            and gate_statuses.get("experience") == "not_required"
        )
        else ["experience", "visual"]
    )
    if status in EXECUTION_STATES and gate_profile in VALID_GATE_PROFILES and not emergency_bypass:
        for prefix in required_gates:
            if gate_statuses.get(prefix) != "approved":
                errors.append(f"{design_label}: status {status} requires approved {prefix} gate")
    if waiver_ref and priority != "P0":
        errors.append(f"{design_label}: emergency_waiver_ref is only valid for a P0 task")
    if waiver_ref:
        validate_decision_reference(
            task_dir,
            project_root,
            waiver_ref,
            "emergency_waiver_ref",
            errors,
        )
        if enforce_managed_protocol:
            alignment_path = resolve_task_path(
                task_dir,
                project_root,
                task.get("alignment_governance_ref"),
                "alignment_governance_ref",
                errors,
                "task.yaml",
            )
            if alignment_path is None or not alignment_path.is_file():
                errors.append(
                    f"{design_label}: protocol {governance_protocol} emergency waiver requires alignment governance"
                )
            else:
                try:
                    waiver_alignment = load_flat_yaml(alignment_path)
                except ValueError as exc:
                    errors.append(f"{alignment_path.relative_to(project_root)}: {exc}")
                else:
                    if waiver_alignment.get("waiver_used") is not True:
                        errors.append(
                            f"{design_label}: emergency_waiver_ref requires alignment waiver_used true"
                        )
                    if waiver_alignment.get("h2_required") is not True:
                        errors.append(
                            f"{design_label}: emergency_waiver_ref requires alignment h2_required true"
                        )
                    if str(waiver_alignment.get("decision_status") or "") != "confirmed":
                        errors.append(
                            f"{design_label}: emergency_waiver_ref requires a confirmed H2 decision"
                        )
                    if status == "done" and str(waiver_alignment.get("readout_status") or "") != "accepted":
                        errors.append(
                            f"{design_label}: emergency waiver done task requires an accepted Human Readout"
                        )
                    validate_decision_binding(
                        task_dir,
                        project_root,
                        waiver_ref,
                        "emergency_waiver_ref",
                        "design/design.yaml",
                        waiver_alignment.get("decision_ref"),
                        waiver_alignment.get("decision_sha256"),
                        "emergency-waiver",
                        "emergency-waiver",
                        errors,
                    )

    conformance_status = str(design.get("conformance_status") or "")
    if conformance_status not in VALID_CONFORMANCE_STATUSES:
        errors.append(f"{design_label}: invalid conformance_status '{conformance_status}'")
    elif conformance_status in CONFORMANCE_ARTIFACT_STATUSES:
        if adaptive_review:
            validate_review_package(
                task,
                task_dir,
                project_root,
                design.get("conformance_ref"),
                design.get("conformance_sha256"),
                "conformance_ref",
                "conformance",
                ("L5",),
                conformance_status,
                errors,
                source_label="design/design.yaml",
            )
        else:
            validate_html_artifact(
                task_dir,
                project_root,
                design.get("conformance_ref"),
                design.get("conformance_sha256"),
                "conformance_ref",
                "design-conformance",
                errors,
                require_capture_pair=enforce_managed_protocol
                and conformance_status in {"matched", "accepted_with_differences"},
                enforce_content_contract=enforce_managed_protocol,
            )

    if conformance_status == "accepted_with_differences":
        if not is_human_identity(design.get("difference_approved_by")):
            errors.append(
                f"{design_label}: accepted_with_differences requires a human approver declaration; this trusted local record is not identity authentication"
            )
        if not is_approval_time(design.get("difference_approved_at")):
            errors.append(f"{design_label}: accepted_with_differences requires an approval time")
        difference_ref = design.get("difference_approval_ref")
        if not str(difference_ref or "").strip():
            errors.append(
                f"{design_label}: accepted_with_differences requires a decision reference"
            )
        elif enforce_managed_protocol:
            validate_decision_binding(
                task_dir,
                project_root,
                difference_ref,
                "difference_approval_ref",
                "design/design.yaml",
                design.get("conformance_ref"),
                design.get("conformance_sha256"),
                "difference-acceptance",
                "design-conformance",
                errors,
            )
        else:
            validate_decision_reference(
                task_dir,
                project_root,
                difference_ref,
                "difference_approval_ref",
                errors,
            )

    if gate_profile == "design_only":
        if conformance_status != "not_required":
            errors.append(f"{design_label}: design_only requires conformance_status not_required")
        return

    if status == "reviewing" and conformance_status not in CONFORMANCE_ARTIFACT_STATUSES:
        errors.append(f"{design_label}: status reviewing requires design conformance")
    if status in {"verifying", "done"} and conformance_status not in {
        "matched",
        "accepted_with_differences",
    }:
        errors.append(
            f"{design_label}: status {status} requires conformance_status matched or accepted_with_differences"
        )


def check_markdown_links(project_root: Path, errors: list[str]) -> None:
    roots = [project_root / name for name in ("AGENTS.md", "CLAUDE.md", "CODEX.md")]
    roots.extend((project_root / "project").rglob("*.md"))
    roots.extend((project_root / "milestones").rglob("*.md"))
    roots.extend((project_root / "work").rglob("*.md"))

    for markdown in roots:
        if markdown.is_symlink() or not markdown.is_file():
            continue
        for match in MARKDOWN_LINK_RE.finditer(markdown.read_text(encoding="utf-8")):
            target = match.group(1).strip().strip("<>").split()[0]
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            file_part = target.split("#", 1)[0]
            if not file_part:
                continue
            resolved = Path(file_part) if Path(file_part).is_absolute() else markdown.parent / file_part
            if not resolved.exists():
                errors.append(
                    f"{markdown.relative_to(project_root)}: broken local link '{target}'"
                )


def check_task(
    task_dir: Path,
    location: str,
    project_root: Path,
    project_schema: int,
    project_protocol: str | None,
    protocol_version_adopted_at: Any,
    legacy_archive_ids: set[str],
    errors: list[str],
) -> str | None:
    relative = task_dir.relative_to(project_root)
    if task_dir.is_symlink():
        errors.append(
            f"{relative}: project-memory task directory must not be a symlink"
        )
        return None
    if not TASK_NAME_RE.fullmatch(task_dir.name):
        errors.append(f"{relative}: invalid task directory name")

    for name in REQUIRED_TASK_FILES:
        if not (task_dir / name).is_file():
            errors.append(f"{relative}: missing {name}")
    evidence_dir = task_dir / "evidence"
    if not evidence_dir.is_dir():
        errors.append(f"{relative}: missing evidence/ directory")

    task_file = task_dir / "task.yaml"
    if task_file.is_symlink():
        errors.append(
            f"{relative}/task.yaml: project-memory authority file must not be a symlink"
        )
        return None
    if not task_file.is_file():
        return None
    try:
        task = load_flat_yaml(task_file)
    except ValueError as exc:
        errors.append(f"{relative}/task.yaml: {exc}")
        return None

    for key in REQUIRED_TASK_KEYS:
        if key not in task:
            errors.append(f"{relative}/task.yaml: missing required field '{key}'")

    task_id = str(task.get("id") or "")
    if task_id and task_id != task_dir.name:
        errors.append(f"{relative}/task.yaml: id '{task_id}' does not match directory name")

    status = str(task.get("status") or "")
    if status not in VALID_STATES:
        errors.append(f"{relative}/task.yaml: invalid status '{status}'")
    if location == "active" and status in {"done", "cancelled"}:
        errors.append(f"{relative}: terminal task must be moved to work/archive")
    if location == "archive" and status not in {"done", "cancelled"}:
        errors.append(f"{relative}: archived task must have status done or cancelled")

    allowed = {str(item) for item in as_list(task.get("allowed_files")) if item is not None}
    forbidden = {str(item) for item in as_list(task.get("forbidden_files")) if item is not None}
    overlap = sorted(allowed & forbidden)
    if overlap:
        errors.append(
            f"{relative}/task.yaml: allowed_files and forbidden_files overlap: {', '.join(overlap)}"
        )

    raw_task_schema = task.get("schema_version", 1)
    task_schema = raw_task_schema if isinstance(raw_task_schema, int) else 0
    if task_schema not in {1, 2}:
        errors.append(f"{relative}/task.yaml: schema_version must be 1 or 2")
    if project_schema == 2 and location == "active" and task_schema != 2:
        errors.append(f"{relative}/task.yaml: schema v2 active task requires schema_version: 2")

    raw_task_protocol = task.get("protocol_version")
    task_protocol = str(raw_task_protocol or "").strip()
    if raw_task_protocol is not None and task_protocol not in SUPPORTED_GOVERNANCE_PROTOCOLS:
        errors.append(
            f"{relative}/task.yaml: protocol_version must be one of {', '.join(SUPPORTED_GOVERNANCE_PROTOCOLS)}"
        )
    project_manages_task = (
        project_protocol in SUPPORTED_GOVERNANCE_PROTOCOLS
        and (location == "active" or task_dir.name not in legacy_archive_ids)
    )
    grandfathered_protocol_21 = (
        project_protocol == ADAPTIVE_REVIEW_PROTOCOL
        and project_manages_task
        and location == "archive"
        and status in {"done", "cancelled"}
        and task_protocol == SUPPORTED_GOVERNANCE_PROTOCOL
        and chronological_timestamps(task.get("created"), task.get("updated"))
        and not_after_adoption(task.get("updated"), protocol_version_adopted_at)
    )
    project_requires_protocol = project_manages_task and not grandfathered_protocol_21
    governance_protocol = (
        project_protocol
        if project_requires_protocol
        else task_protocol
        if task_protocol in SUPPORTED_GOVERNANCE_PROTOCOLS
        else None
    )
    enforce_managed_protocol = governance_protocol in SUPPORTED_GOVERNANCE_PROTOCOLS

    if enforce_managed_protocol:
        symlink_descendants = [
            descendant for descendant in task_dir.rglob("*") if descendant.is_symlink()
        ]
        if symlink_descendants:
            for descendant in symlink_descendants:
                errors.append(
                    f"{descendant.relative_to(project_root)}: protocol {governance_protocol} project-memory paths must not be symlinks"
                )
            return task_id or None

    if task_schema == 2:
        for key in REQUIRED_TASK_V2_KEYS:
            if key not in task:
                errors.append(f"{relative}/task.yaml: missing required field '{key}'")
        task_types = [str(item) for item in as_list(task.get("task_types")) if item]
        if not task_types:
            errors.append(f"{relative}/task.yaml: task_types must contain at least one type")
        invalid_types = sorted({item for item in task_types if item not in VALID_TASK_TYPES})
        if invalid_types:
            errors.append(
                f"{relative}/task.yaml: task_types contains invalid value(s): {', '.join(invalid_types)}"
            )
        if len(task_types) != len(set(task_types)):
            errors.append(f"{relative}/task.yaml: task_types must not contain duplicates")

        alignment_mode = str(task.get("alignment_mode") or "")
        if alignment_mode not in VALID_ALIGNMENT_MODES:
            errors.append(f"{relative}/task.yaml: invalid alignment_mode '{alignment_mode}'")
        visual_task = bool({"ui", "ux"} & set(task_types))
        visual_alignment = alignment_mode in {"visual", "mixed"}
        if visual_task and alignment_mode not in {"visual", "mixed"}:
            errors.append(
                f"{relative}/task.yaml: ui/ux task requires alignment_mode visual or mixed"
            )
        if visual_alignment:
            validate_design_governance(
                task,
                task_dir,
                project_root,
                errors,
                governance_protocol,
            )
        elif task.get("design_governance_ref"):
            validate_design_governance(
                task,
                task_dir,
                project_root,
                errors,
                governance_protocol,
            )

    if project_requires_protocol:
        if task_protocol != project_protocol:
            if location == "archive":
                errors.append(
                    f"{relative}/task.yaml: governance protocol {project_protocol} archived task requires protocol_version: \"{project_protocol}\"; migrate it or list a pre-2.1 task ID in project/state.yaml legacy_archive_ids"
                )
            else:
                errors.append(
                    f"{relative}/task.yaml: governance protocol {project_protocol} active task requires protocol_version: \"{project_protocol}\""
                )
    if (
        project_protocol == ADAPTIVE_REVIEW_PROTOCOL
        and location == "archive"
        and status in {"done", "cancelled"}
        and task_protocol == SUPPORTED_GOVERNANCE_PROTOCOL
        and not grandfathered_protocol_21
    ):
        errors.append(
            f"{relative}/task.yaml: archived protocol 2.1 task requires valid created <= updated <= governance_protocol_version_adopted_at to remain historical; otherwise it must migrate to protocol 2.2"
        )
    if enforce_managed_protocol:
        if task_schema != 2 and not (project_schema == 2 and location == "active"):
            errors.append(f"{relative}/task.yaml: protocol {governance_protocol} task requires schema_version: 2")
        missing_protocol_fields = {
            key for key in REQUIRED_TASK_PROTOCOL_21_KEYS if key not in task
        }
        for key in REQUIRED_TASK_PROTOCOL_21_KEYS:
            if key in missing_protocol_fields and not (
                key == "protocol_version" and project_requires_protocol
            ):
                errors.append(f"{relative}/task.yaml: missing required field '{key}'")
        risk_level = str(task.get("risk_level") or "")
        if "risk_level" not in missing_protocol_fields and risk_level not in VALID_RISK_LEVELS:
            errors.append(f"{relative}/task.yaml: invalid risk_level '{risk_level}'")
        builder_id = str(task.get("builder_id") or "").strip()
        verifier_id = str(task.get("verifier_id") or "").strip()
        unassigned = {"", "unassigned", "none", "null", "tbd"}
        if status in EXECUTION_STATES:
            if "builder_id" not in missing_protocol_fields and builder_id.lower() in unassigned:
                errors.append(f"{relative}/task.yaml: status {status} requires assigned builder_id")
            if "verifier_id" not in missing_protocol_fields and verifier_id.lower() in unassigned:
                errors.append(f"{relative}/task.yaml: status {status} requires assigned verifier_id")
            if (
                builder_id.lower() not in unassigned
                and verifier_id.lower() not in unassigned
                and builder_id.casefold() == verifier_id.casefold()
            ):
                errors.append(f"{relative}/task.yaml: builder_id and verifier_id must differ")
        if "alignment_governance_ref" not in missing_protocol_fields:
            validate_alignment_governance(
                task,
                task_dir,
                project_root,
                errors,
                governance_protocol=governance_protocol or SUPPORTED_GOVERNANCE_PROTOCOL,
            )

    if status in EXECUTION_STATES:
        if not substantive_markdown(task_dir / "brief.md"):
            errors.append(f"{relative}: status {status} requires a substantive brief.md")
    if status in {"reviewing", "verifying", "done"}:
        if enforce_managed_protocol:
            validate_required_markdown_document(
                task_dir / "handoff.md",
                project_root,
                REQUIRED_HANDOFF_HEADINGS,
                "handoff",
                errors,
                governance_protocol or SUPPORTED_GOVERNANCE_PROTOCOL,
            )
        elif not substantive_markdown(task_dir / "handoff.md"):
            errors.append(f"{relative}: status {status} requires a substantive handoff.md")
    if status in {"verifying", "done"}:
        if enforce_managed_protocol:
            validate_required_markdown_document(
                task_dir / "review.md",
                project_root,
                REQUIRED_REVIEW_HEADINGS,
                "independent review",
                errors,
                governance_protocol or SUPPORTED_GOVERNANCE_PROTOCOL,
            )
        elif not substantive_markdown(task_dir / "review.md"):
            errors.append(f"{relative}: status {status} requires a substantive review.md")
    if status == "done":
        if task.get("verification_status") != "passed":
            errors.append(f"{relative}/task.yaml: verification_status must be 'passed' for done")
        evidence_files = (
            [path for path in evidence_dir.rglob("*") if path.is_file()]
            if evidence_dir.is_dir()
            else []
        )
        if enforce_managed_protocol:
            if not any(substantive_evidence_file(path) for path in evidence_files):
                errors.append(
                    f"{relative}: protocol {governance_protocol} done task requires at least one substantive nonempty evidence file"
                )
        elif not evidence_files:
            errors.append(f"{relative}: done task requires at least one evidence file")
        commits = [item for item in as_list(task.get("commits")) if item]
        reason = task.get("not_committed_reason")
        if not commits and not reason:
            errors.append(f"{relative}/task.yaml: done task requires commits or not_committed_reason")

    return task_id or None


def run_git(project_root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(project_root), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def validate_legacy_adoption_anchor(
    project_root: Path,
    state: dict[str, Any],
    legacy_archive_ids: set[str],
    task_ids: dict[str, Path],
    errors: list[str],
) -> None:
    if not legacy_archive_ids:
        return
    trust_note = "local Git history is trusted input and is not tamper-proof"
    raw_anchor = str(state.get("governance_protocol_adoption_commit") or "").strip()
    if not raw_anchor:
        errors.append(
            f"project/state.yaml: nonempty legacy_archive_ids requires governance_protocol_adoption_commit; {trust_note}"
        )
        return

    top_result = run_git(project_root, "rev-parse", "--show-toplevel")
    if top_result.returncode != 0:
        errors.append(
            f"project/state.yaml: governance_protocol_adoption_commit requires the selected project to be inside a Git repository; {trust_note}"
        )
        return
    repository_root = Path(top_result.stdout.decode("utf-8", "replace").strip()).resolve()
    try:
        project_relative = project_root.relative_to(repository_root)
    except ValueError:
        errors.append(
            f"project/state.yaml: selected project is outside the Git repository reported by Git; {trust_note}"
        )
        return

    resolved_result = run_git(project_root, "rev-parse", "--verify", f"{raw_anchor}^{{commit}}")
    if resolved_result.returncode != 0:
        errors.append(
            f"project/state.yaml: governance_protocol_adoption_commit is not a commit in the current Git repository; {trust_note}"
        )
        return
    anchor = resolved_result.stdout.decode("ascii", "replace").strip().lower()
    if raw_anchor.lower() != anchor or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", anchor):
        errors.append(
            "project/state.yaml: governance_protocol_adoption_commit must record the full resolved commit ID"
        )

    head_result = run_git(project_root, "rev-parse", "HEAD")
    if head_result.returncode != 0:
        errors.append(f"project/state.yaml: cannot resolve current Git HEAD; {trust_note}")
        return
    head = head_result.stdout.decode("ascii", "replace").strip().lower()
    ancestor_result = run_git(project_root, "merge-base", "--is-ancestor", anchor, head)
    if ancestor_result.returncode != 0:
        errors.append(
            f"project/state.yaml: governance_protocol_adoption_commit must be an ancestor of current HEAD; {trust_note}"
        )
        return

    state_path = (project_relative / "project" / "state.yaml").as_posix()
    state_tree_result = run_git(
        project_root,
        "ls-tree",
        anchor,
        "--",
        f":(top){state_path}",
    )
    state_tree = state_tree_result.stdout.decode("utf-8", "replace").strip()
    if state_tree_result.returncode != 0 or not re.match(r"^100(?:644|755)\s+blob\s+", state_tree):
        errors.append(
            "project/state.yaml: adoption commit must contain project/state.yaml as a regular Git blob, not a symlink"
        )
        return
    state_result = run_git(project_root, "show", f"{anchor}:{state_path}")
    if state_result.returncode != 0:
        errors.append(
            "project/state.yaml: adoption commit does not contain the project state file"
        )
        return
    try:
        anchor_state = parse_flat_yaml_text(state_result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        errors.append(f"project/state.yaml: adoption commit state is unreadable: {exc}")
        return
    if anchor_state.get("schema_version") != 2:
        errors.append(
            "project/state.yaml: adoption commit state must use schema_version 2"
        )
    if str(anchor_state.get("governance_protocol_version") or "") != SUPPORTED_GOVERNANCE_PROTOCOL:
        errors.append(
            'project/state.yaml: adoption commit state must declare governance_protocol_version "2.1"'
        )
    if str(anchor_state.get("governance_protocol_adopted_at") or "") != str(
        state.get("governance_protocol_adopted_at") or ""
    ):
        errors.append(
            "project/state.yaml: adoption commit state must contain the current governance_protocol_adopted_at"
        )
    anchor_legacy = [str(value).strip() for value in as_list(anchor_state.get("legacy_archive_ids"))]
    current_legacy = [str(value).strip() for value in as_list(state.get("legacy_archive_ids"))]
    if anchor_legacy != current_legacy:
        errors.append(
            "project/state.yaml: adoption commit state must contain the same ordered legacy_archive_ids"
        )
    anchor_self_ref = str(anchor_state.get("governance_protocol_adoption_commit") or "").strip().lower()
    if anchor_self_ref not in {"", "null", "pending"}:
        errors.append(
            "project/state.yaml: adoption commit state must leave governance_protocol_adoption_commit null or pending before the next commit records its full ID"
        )

    for legacy_id in sorted(legacy_archive_ids):
        task_path = task_ids.get(legacy_id)
        if task_path is None:
            continue
        relative_task = (
            project_relative / "work" / "archive" / legacy_id / "task.yaml"
        ).as_posix()
        tree_result = run_git(
            project_root,
            "ls-tree",
            anchor,
            "--",
            f":(top){relative_task}",
        )
        tree_entry = tree_result.stdout.decode("utf-8", "replace").strip()
        tree_match = re.match(
            r"^(100(?:644|755))\s+blob\s+([0-9a-f]{40}|[0-9a-f]{64})\t",
            tree_entry,
        )
        if tree_result.returncode != 0 or tree_match is None:
            errors.append(
                f"project/state.yaml: adoption commit must contain work/archive/{legacy_id}/task.yaml as a regular Git blob, not a symlink"
            )
            continue
        anchor_blob = tree_match.group(2)
        index_result = run_git(
            project_root,
            "ls-files",
            "--stage",
            "--",
            f":(top){relative_task}",
        )
        index_entries = [
            match
            for line in index_result.stdout.decode("utf-8", "replace").splitlines()
            if (
                match := re.match(
                    r"^(100(?:644|755))\s+([0-9a-f]{40}|[0-9a-f]{64})\s+0\t",
                    line,
                )
            )
        ]
        if (
            index_result.returncode != 0
            or len(index_entries) != 1
            or index_entries[0].group(2) != anchor_blob
        ):
            errors.append(
                f"project/state.yaml: work/archive/{legacy_id}/task.yaml index blob differs from its adoption-commit version"
            )
        worktree_result = run_git(
            project_root,
            "hash-object",
            f"--path={relative_task}",
            "--",
            str(task_path / "task.yaml"),
        )
        worktree_blob = worktree_result.stdout.decode("ascii", "replace").strip().lower()
        if worktree_result.returncode != 0 or worktree_blob != anchor_blob:
            errors.append(
                f"project/state.yaml: work/archive/{legacy_id}/task.yaml worktree blob differs from its adoption-commit version; assume-unchanged and skip-worktree flags do not bypass this comparison"
            )


# Protocol 3.0 is intentionally implemented as a small, separate validation
# kernel.  The v1/v2 validator below remains untouched so projects can finish
# under the rules they adopted instead of being silently reinterpreted.
V3_REQUIRED_STATE_KEYS = (
    "schema_version",
    "protocol_version",
    "project_id",
    "project_name",
    "status",
    "active_task",
    "updated",
)
V3_REQUIRED_TASK_KEYS = (
    "schema_version",
    "protocol_version",
    "id",
    "status",
    "goal",
    "scope",
    "non_goals",
    "acceptance",
    "risk",
    "risk_reasons",
    "protected_paths",
    "context_refs",
    "decision_refs",
    "evidence_refs",
    "updated",
)
V3_CONFORMANCE_STATUSES = {
    "not_required",
    "pending",
    "matched",
    "changes_requested",
    "differences_accepted",
}
V3_AUTHORITY_DENIALS = {
    "next",
    "generic-next",
    "continue",
    "okay",
    "silence",
    "in-artifact-control",
    "agent-relay",
    "summarized-approval",
}
V3_ACTION_AUTHORITY_DENIALS = {
    "next",
    "generic-next",
    "continue",
    "ok",
    "okay",
    "yes",
    "silence",
    "in-artifact-control",
    "agent-relay",
    "summarized-approval",
}
V3_ACTION_AUTHORITY_ALLOWED = {
    "direct-human-instruction",
    "durable-decision",
    "platform-authority",
    "external-attestation",
    "delegated-authority",
}
V3_HIGH_RISK_REASONS = {
    "irreversible-or-destructive",
    "real-user-or-sensitive-data",
    "security-or-safety",
    "difficult-migration",
    "publication-or-deployment",
    "payment-or-message",
    "legal-impact",
}
V3_HIGH_IMPACT_EFFECTS = {
    "effect_reversibility": {"irreversible"},
    "effect_data": {"personal-or-sensitive"},
    "effect_environment": {"production"},
    "effect_external": {"message-or-publish", "payment-or-legal"},
    "effect_security_safety": {"involved"},
    "effect_user_impact": {"direct"},
}
V3_ACTION_LIVE_STATUSES = {"authorized", "executing"}
V3_ACTION_EFFECT_STATUSES = {"succeeded", "compensated"}
V3_ACTION_AUTHORITY_STATUSES = {
    "authorized",
    "executing",
    "succeeded",
    "failed",
    "unknown",
    "compensated",
}
V3_ACTION_STATUSES = {
    "planned",
    "authorized",
    "executing",
    "succeeded",
    "failed",
    "unknown",
    "compensated",
}
V3_REVIEW_OWNED_TASK_FIELDS = {
    "verification_mode",
    "verification_status",
    "verification_subject",
    "verification_subject_ref",
    "verification_subject_paths",
    "verification_actor",
    "verification_actor_modified_subject",
    "review_subject",
    "review_subject_ref",
    "review_subject_paths",
    "review_mode",
    "review_verdict",
}


def v3_project_relative_path(
    project_root: Path,
    raw_value: Any,
    label: str,
    errors: list[str],
    *,
    require_exists: bool = True,
    require_file: bool = True,
) -> Path | None:
    """Resolve one v3 repository reference without following an authority symlink."""
    value = str(raw_value or "").strip()
    if not value:
        errors.append(f"{label}: reference must not be empty")
        return None
    if EXTERNAL_URI_RE.match(value):
        errors.append(f"{label}: external URIs are not portable authority references; use a local project file")
        return None
    value = value.split("#", 1)[0]
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts or candidate == Path("."):
        errors.append(f"{label}: path must be a contained project-relative path")
        return None
    target = project_root / candidate
    try:
        target.resolve(strict=False).relative_to(project_root.resolve())
    except ValueError:
        errors.append(f"{label}: path resolves outside the project root")
        return None
    symlink = first_symlink_component(target)
    if symlink is not None:
        errors.append(f"{label}: authority path traverses symlink component {symlink}")
        return None
    if require_exists and not target.exists():
        errors.append(f"{label}: referenced path does not exist: {value}")
        return None
    if target.exists() and require_file and (target.is_symlink() or not target.is_file()):
        errors.append(f"{label}: referenced path must be a regular file: {value}")
        return None
    return target


def v3_git_head(project_root: Path) -> str | None:
    result = run_git(project_root, "rev-parse", "HEAD")
    if result.returncode != 0:
        return None
    value = result.stdout.decode("utf-8", errors="replace").strip().lower()
    return value if GIT_COMMIT_RE.fullmatch(value) else None


def v3_git_status(project_root: Path, *pathspecs: str) -> bytes | None:
    args = ["status", "--porcelain=v1", "-z", "--untracked-files=all"]
    if pathspecs:
        args.extend(("--", *pathspecs))
    result = run_git(project_root, *args)
    return result.stdout if result.returncode == 0 else None


def v3_worktree_digest(project_root: Path, subject_paths: list[str]) -> str | None:
    head = v3_git_head(project_root)
    if head is None:
        return None
    if not subject_paths:
        return None
    status = v3_git_status(project_root, *subject_paths)
    diff = run_git(project_root, "diff", "--binary", "HEAD", "--", *subject_paths)
    if status is None or diff.returncode != 0:
        return None
    digest = hashlib.sha256()
    digest.update(b"goalos-continuity-worktree-v1\0")
    digest.update(head.encode("ascii"))
    digest.update(b"\0")
    digest.update(status)
    digest.update(b"\0")
    digest.update(diff.stdout)
    untracked = run_git(
        project_root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
        "--",
        *subject_paths,
    )
    if untracked.returncode != 0:
        return None
    for raw_name in sorted(name for name in untracked.stdout.split(b"\0") if name):
        digest.update(b"\0path\0")
        digest.update(raw_name)
        path = project_root / raw_name.decode("utf-8", errors="surrogateescape")
        if path.is_file() and not path.is_symlink():
            digest.update(b"\0bytes\0")
            try:
                digest.update(path.read_bytes())
            except OSError:
                return None
        else:
            digest.update(b"\0non-regular\0")
    return digest.hexdigest()


def v3_validate_subject(
    project_root: Path,
    subject: Any,
    label: str,
    errors: list[str],
    *,
    artifact: Path | None = None,
    subject_paths: list[str] | None = None,
) -> None:
    value = str(subject or "").strip().lower()
    if not value:
        errors.append(f"{label}: exact subject is required")
        return
    paths = [str(path).strip() for path in (subject_paths or []) if str(path).strip()]
    path_targets: list[tuple[str, Path]] = []
    for index, path in enumerate(paths):
        target = v3_project_relative_path(
            project_root,
            path,
            f"{label}:subject_paths[{index}]",
            errors,
            require_exists=False,
            require_file=False,
        )
        if target is not None:
            path_targets.append((path, target))
    if value.startswith("git:") or GIT_COMMIT_RE.fullmatch(value):
        expected = value.removeprefix("git:")
        exists = run_git(project_root, "cat-file", "-e", f"{expected}^{{commit}}")
        if not paths:
            errors.append(f"{label}: git subject requires explicit subject_paths")
            return
        for path, target in path_targets:
            in_subject = run_git(project_root, "cat-file", "-t", f"{expected}:{path}")
            subject_is_file = in_subject.returncode == 0 and in_subject.stdout.strip() == b"blob"
            current_is_file = target.is_file() and not target.is_symlink()
            if target.exists() and not current_is_file:
                errors.append(f"{label}: subject path must be a regular file: {path}")
            if not current_is_file and not subject_is_file:
                errors.append(f"{label}: subject path never identifies a regular file in the worktree or named commit: {path}")
        diff = run_git(project_root, "diff", "--quiet", expected, "--", *paths)
        status = v3_git_status(project_root, *paths)
        if exists.returncode != 0 or diff.returncode != 0 or status is None or status:
            errors.append(
                f"{label}: git subject is stale for its declared subject_paths"
            )
        return
    if value.startswith("worktree:") or value.startswith("patch:"):
        expected = value.split(":", 1)[1]
        head = v3_git_head(project_root)
        for path, target in path_targets:
            in_head = (
                run_git(project_root, "cat-file", "-t", f"{head}:{path}")
                if head is not None
                else None
            )
            head_is_file = in_head is not None and in_head.returncode == 0 and in_head.stdout.strip() == b"blob"
            current_is_file = target.is_file() and not target.is_symlink()
            if target.exists() and not current_is_file:
                errors.append(f"{label}: subject path must be a regular file: {path}")
            if not current_is_file and not head_is_file:
                errors.append(f"{label}: subject path never identifies a regular file in the worktree or HEAD: {path}")
        actual = v3_worktree_digest(project_root, paths)
        if not SHA256_RE.fullmatch(expected) or actual != expected:
            errors.append(f"{label}: worktree subject is stale")
        return
    if value.startswith("sha256:"):
        expected = value.split(":", 1)[1]
        if artifact is None or not artifact.is_file() or sha256(artifact) != expected:
            errors.append(f"{label}: artifact subject is stale")
        return
    if value.startswith("provider:") or value.startswith("artifact:"):
        identity = value.split(":", 1)[1].strip()
        tokens = {token for token in re.split(r"[^a-z0-9]+", identity) if token}
        if len(identity) < 8 or tokens & MUTABLE_IDENTITY_TOKENS:
            errors.append(f"{label}: provider/artifact subject must contain a stable revision")
        for path, target in path_targets:
            if not target.is_file() or target.is_symlink():
                errors.append(f"{label}: provider/artifact subject path must be a current regular file: {path}")
        return
    errors.append(
        f"{label}: subject must be git:<full-sha>, worktree:<sha256>, sha256:<artifact-digest>, or a stable provider/artifact revision"
    )


def v3_load_action_record(path: Path) -> dict[str, Any]:
    if path.suffix.lower() in {".yaml", ".yml"}:
        return load_flat_yaml(path)
    if path.suffix.lower() == ".md":
        content = path.read_text(encoding="utf-8")
        lines = content.splitlines()
        if not lines or lines[0].strip() != "---":
            raise ValueError("Markdown action record requires flat YAML front matter")
        try:
            end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
        except StopIteration as exc:
            raise ValueError("Markdown action record has unclosed YAML front matter") from exc
        return parse_flat_yaml_text("\n".join(lines[1:end]))
    raise ValueError("action record must be YAML or Markdown with YAML front matter")


def v3_load_claim_record(path: Path, kind: str) -> dict[str, Any]:
    """Load a handoff/review record's flat, portable front matter."""
    if path.suffix.lower() not in {".md", ".yaml", ".yml"}:
        raise ValueError(f"{kind} record must be YAML or Markdown with YAML front matter")
    if path.suffix.lower() in {".yaml", ".yml"}:
        return load_v3_yaml(path)
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"current {kind} record requires flat YAML front matter")
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise ValueError(f"current {kind} record has unclosed YAML front matter") from exc
    return parse_v3_yaml_text("\n".join(lines[1:end]))


def v3_validate_claim_file(path: Path, label: str, errors: list[str]) -> None:
    """Check only mechanical usability; v3 does not score prose or headings."""
    try:
        payload = path.read_bytes()
    except OSError as exc:
        errors.append(f"{label}: cannot read claim artifact: {exc}")
        return
    if not payload.strip():
        errors.append(f"{label}: claim artifact must not be empty")
        return
    if path.suffix.lower() in {".md", ".txt", ".yaml", ".yml", ".json", ".html"}:
        text = payload.decode("utf-8", errors="replace")
        if any(pattern.search(text) for pattern in PLACEHOLDER_PATTERNS):
            errors.append(f"{label}: claim artifact contains an unresolved placeholder")


def v3_validate_decision_file(path: Path, label: str, errors: list[str]) -> None:
    before = len(errors)
    v3_validate_claim_file(path, label, errors)
    if len(errors) != before:
        return
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    words = re.findall(r"[A-Za-z0-9\u3400-\u9fff]+", text)
    if len("".join(words)) < 12:
        errors.append(f"{label}: decision record must contain a substantive decision")


def v3_validate_record_body(path: Path, label: str, errors: list[str]) -> None:
    """Require a visible claim body; front-matter identity alone is not a finding."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        try:
            end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
        except StopIteration:
            return
        text = "\n".join(lines[end + 1 :])
    words = re.findall(r"[A-Za-z0-9\u3400-\u9fff]+", text)
    if len("".join(words)) < 12:
        errors.append(f"{label}: review record must contain substantive findings outside front matter")


def v3_claim_file_is_substantive(path: Path) -> bool:
    local_errors: list[str] = []
    v3_validate_claim_file(path, "claim", local_errors)
    return not local_errors


def v3_validate_visual_artifact(
    path: Path,
    label: str,
    errors: list[str],
    *,
    role: str,
) -> None:
    """Validate a conservative media/package shape without judging its design."""
    suffix = path.suffix.lower()
    try:
        payload = path.read_bytes()
    except OSError as exc:
        errors.append(f"{label}: cannot read visual artifact: {exc}")
        return
    valid = False
    if suffix == ".png":
        dimensions = png_dimensions(payload)
        valid = dimensions is not None and dimensions[0] >= 16 and dimensions[1] >= 16
    elif suffix in {".jpg", ".jpeg"}:
        valid = len(payload) >= 256 and payload.startswith(b"\xff\xd8\xff") and payload.endswith(b"\xff\xd9")
    elif suffix == ".gif":
        if len(payload) >= 32 and payload[:6] in {b"GIF87a", b"GIF89a"} and payload.endswith(b";"):
            width = int.from_bytes(payload[6:8], "little")
            height = int.from_bytes(payload[8:10], "little")
            valid = width >= 16 and height >= 16
    elif suffix == ".webp":
        valid = (
            len(payload) >= 32
            and payload.startswith(b"RIFF")
            and payload[8:12] == b"WEBP"
            and payload[12:16] in {b"VP8 ", b"VP8L", b"VP8X"}
        )
    elif suffix == ".svg":
        text = payload.decode("utf-8", errors="replace")
        valid = len(text.strip()) >= 100 and "<svg" in text.lower() and re.search(r"<(?:path|rect|circle|ellipse|line|polyline|polygon|text)\b", text, re.I) is not None
    elif suffix == ".html":
        if role == "render":
            errors.append(f"{label}: HTML is a design surface, not a real implementation render")
            return
        before = len(errors)
        validate_adaptive_html_surface(path, label, errors)
        text = payload.decode("utf-8", errors="replace")
        has_visual_surface = bool(
            re.search(r"<(?:svg|canvas)\b", text, re.I)
            or re.search(r"data:image/(?:png|jpeg|gif|webp|svg\+xml);base64,", text, re.I)
            or re.search(r"\bdata-visual-surface(?:\s*=|\s|>)", text, re.I)
        )
        if not has_visual_surface:
            errors.append(
                f"{label}: HTML baseline needs SVG, canvas, embedded image data, or an explicit data-visual-surface marker"
            )
        valid = len(errors) == before
    elif suffix == ".pdf":
        valid = (
            len(payload) >= 128
            and payload.startswith(b"%PDF-")
            and b"%%EOF" in payload[-1024:]
            and re.search(rb"/Type\s*/Page\b", payload) is not None
        )
    elif suffix in {".mp4", ".mov", ".m4v"}:
        valid = (
            len(payload) >= 128
            and payload[4:8] == b"ftyp"
            and (b"moov" in payload or b"moof" in payload)
            and b"mdat" in payload
        )
    elif suffix == ".json":
        try:
            value = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            value = None
        valid = isinstance(value, dict) and len(payload) >= 100 and any(
            (
                isinstance(value.get(key), list)
                and bool(value.get(key))
                and all(isinstance(item, dict) for item in value.get(key))
            )
            or (isinstance(value.get(key), dict) and bool(value.get(key)))
            for key in ("frames", "screens", "nodes", "surfaces", "pages")
        )
    elif suffix == ".md":
        text = payload.decode("utf-8", errors="replace")
        valid = len(text.strip()) >= 120 and re.search(r"```mermaid\s+[^`]+```", text, re.I | re.S) is not None
    if not valid and suffix != ".html":
        errors.append(
            f"{label}: visual artifact must have a supported image, SVG, PDF, video, visual HTML baseline, Mermaid, or structured local visual-manifest shape"
        )


def v3_validate_provider_visual_subject(subject: Any, label: str, errors: list[str]) -> bool:
    value = str(subject or "").strip().lower()
    if not (value.startswith("provider:") or value.startswith("artifact:")):
        return False
    identity = value.split(":", 1)[1]
    has_revision = re.search(
        r"(?:^|[:/@._-])(?:rev(?:ision)?|version|snapshot|commit|file)[-:=/@._]?[a-z0-9][a-z0-9._-]{1,}",
        identity,
    ) is not None
    has_surface = re.search(
        r"(?:^|[:/@._-])(?:node|frame|screen|page)[-:=/@._]?[a-z0-9][a-z0-9._-]{0,}",
        identity,
    ) is not None
    tokens = {token for token in re.split(r"[^a-z0-9]+", identity) if token}
    if not has_revision or not has_surface or tokens & MUTABLE_IDENTITY_TOKENS:
        errors.append(
            f"{label}: provider visual subject requires an immutable revision/file identity and frame/node/page/screen identity"
        )
    return True


def v3_validate_action_record(
    project_root: Path,
    path: Path,
    errors: list[str],
) -> None:
    label = str(path.relative_to(project_root))
    try:
        record = v3_load_action_record(path)
    except (OSError, ValueError) as exc:
        errors.append(f"{label}: {exc}")
        return
    required = (
        "action_id",
        "target",
        "environment",
        "payload_scope",
        "subject",
        "authorization_basis",
        "authority_ref",
        "one_shot",
        "idempotency_key",
        "expires_at",
        "timeout_seconds",
        "status",
        "observation",
        "compensation",
    )
    for key in required:
        if key not in record:
            errors.append(f"{label}: missing required field '{key}'")
        elif review_value_contains_placeholder(record.get(key)):
            errors.append(f"{label}: field '{key}' contains an unresolved placeholder")
    for key in ("action_id", "target", "environment", "payload_scope", "subject"):
        if not str(record.get(key) or "").strip():
            errors.append(f"{label}: field '{key}' must be nonempty")
    if record.get("one_shot") is not True:
        errors.append(f"{label}: one_shot must be true for a high-impact action")
    expires_at = parse_iso_datetime(record.get("expires_at"))
    if expires_at is None:
        errors.append(f"{label}: expires_at must be an ISO date or date-time")
    timeout = record.get("timeout_seconds")
    if not isinstance(timeout, int) or timeout <= 0:
        errors.append(f"{label}: timeout_seconds must be a positive integer")
    status = str(record.get("status") or "")
    if status not in V3_ACTION_STATUSES:
        errors.append(f"{label}: invalid action status '{status}'")
    if "reconciliation_outcome" in record:
        errors.append(f"{label}: reconciliation_outcome is obsolete; use reconciliation_result")
    subject_ref: Path | None = None
    if record.get("subject_ref"):
        subject_ref = v3_project_relative_path(
            project_root,
            record.get("subject_ref"),
            f"{label}:subject_ref",
            errors,
        )
    if "subject" in record:
        v3_validate_subject(
            project_root,
            record.get("subject"),
            f"{label}:subject",
            errors,
            artifact=subject_ref,
            subject_paths=[str(value) for value in as_list(record.get("subject_paths"))],
        )
    authority_ref = None
    if record.get("authority_ref"):
        authority_ref = v3_project_relative_path(
            project_root,
            record.get("authority_ref"),
            f"{label}:authority_ref",
            errors,
        )
    if status in V3_ACTION_AUTHORITY_STATUSES:
        authority_category = str(record.get("authorization_basis") or "").strip().lower()
        if not SLUG_RE.fullmatch(authority_category):
            errors.append(f"{label}: action execution requires a normalized authorization_basis category slug")
        elif authority_category in V3_ACTION_AUTHORITY_DENIALS:
            errors.append(f"{label}: authorization_basis '{authority_category}' cannot authorize an external effect")
        elif authority_category not in V3_ACTION_AUTHORITY_ALLOWED:
            errors.append(f"{label}: authorization_basis '{authority_category}' is not a recognized direct authority category")
        if not record.get("authority_ref"):
            errors.append(f"{label}: action execution requires authority_ref")
        if authority_ref is not None:
            v3_validate_claim_file(authority_ref, f"{label}:authority_ref", errors)
        if not str(record.get("idempotency_key") or "").strip():
            errors.append(f"{label}: action execution requires idempotency_key")
        for key in ("observation", "compensation"):
            value = str(record.get(key) or "").strip().lower()
            if not value or value in {"none", "unknown", "not-observed", "not observed"}:
                errors.append(f"{label}: executed action requires substantive {key}")
    if status in {"authorized", "executing"} and expires_at is not None:
        now = datetime.now(tz=expires_at.tzinfo) if expires_at.tzinfo else datetime.now()
        if expires_at <= now:
            errors.append(f"{label}: expired authority cannot authorize an external effect")
    if status == "unknown":
        if record.get("retry_allowed") is not False:
            errors.append(f"{label}: unknown action must set retry_allowed: false")
    if record.get("reconciliation_ref"):
        reconciliation_ref = v3_project_relative_path(
            project_root,
            record.get("reconciliation_ref"),
            f"{label}:reconciliation_ref",
            errors,
        )
        if reconciliation_ref is not None:
            v3_validate_claim_file(
                reconciliation_ref, f"{label}:reconciliation_ref", errors
            )
    reconciliation_result = str(record.get("reconciliation_result") or "").strip().lower()
    resolved_results = {"effect-confirmed", "no-effect-confirmed", "compensated-confirmed"}
    if reconciliation_result in resolved_results and not record.get("reconciliation_ref"):
        errors.append(f"{label}: resolved reconciliation_result requires reconciliation_ref")
    if status == "compensated":
        if reconciliation_result != "compensated-confirmed":
            errors.append(f"{label}: compensated action requires reconciliation_result: compensated-confirmed")
        if not record.get("reconciliation_ref"):
            errors.append(f"{label}: compensated action requires substantive compensation evidence in reconciliation_ref")
    for field, value in record.items():
        if field.startswith("x_") or not field.endswith("_ref") or field in {"subject_ref", "authority_ref", "reconciliation_ref"} or not value:
            continue
        v3_project_relative_path(project_root, value, f"{label}:{field}", errors)
    for field, values in record.items():
        if field.startswith("x_") or not field.endswith("_refs"):
            continue
        for index, value in enumerate(as_list(values)):
            v3_project_relative_path(project_root, value, f"{label}:{field}[{index}]", errors)


def v3_validate_task(
    project_root: Path,
    task_dir: Path,
    location: str,
    mode: str,
    errors: list[str],
) -> str | None:
    relative = task_dir.relative_to(project_root)
    if task_dir.is_symlink():
        errors.append(f"{relative}: task authority directory must not be a symlink")
        return None
    try:
        task_descendants = sorted(task_dir.rglob("*"))
    except OSError as exc:
        errors.append(f"{relative}: cannot inspect task authority descendants: {exc}")
        return None
    for descendant in task_descendants:
        if descendant.is_symlink():
            errors.append(
                f"{descendant.relative_to(project_root)}: task authority descendant must not be a symlink"
            )
    if not V3_TASK_NAME_RE.fullmatch(task_dir.name):
        errors.append(f"{relative}: invalid protocol 3.0 task directory name")
    task_file = task_dir / "task.yaml"
    if task_file.is_symlink() or not task_file.is_file():
        errors.append(f"{relative}: missing regular task.yaml")
        return None
    try:
        task = load_v3_yaml(task_file)
    except (OSError, ValueError) as exc:
        errors.append(f"{relative}/task.yaml: {exc}")
        return None
    for key in V3_REQUIRED_TASK_KEYS:
        if key not in task:
            errors.append(f"{relative}/task.yaml: missing required field '{key}'")

    task_id = str(task.get("id") or "").strip()
    if task_id != task_dir.name:
        errors.append(f"{relative}/task.yaml: id '{task_id}' does not match directory name")
    if task.get("schema_version") != 3:
        errors.append(f"{relative}/task.yaml: schema_version must be 3")
    if str(task.get("protocol_version") or "") != CONTINUITY_KERNEL_PROTOCOL:
        errors.append(f'{relative}/task.yaml: protocol_version must be "3.0"')

    status = str(task.get("status") or "").strip()
    if not status:
        errors.append(f"{relative}/task.yaml: status must not be empty")
    completion_claim = status.lower() in {"done", "completed"} or task.get("completion_claim") is True
    if "result_status" in task:
        errors.append(
            f"{relative}/task.yaml: result_status is ambiguous in protocol 3.0; use completion_claim: true"
        )
    for field in sorted(V3_REVIEW_OWNED_TASK_FIELDS & set(task)):
        errors.append(
            f"{relative}/task.yaml: {field} duplicates review-owned formal metadata; keep it only in review front matter"
        )
    try:
        task_text = task_file.read_text(encoding="utf-8")
    except OSError:
        task_text = ""
    if any(pattern.search(task_text) for pattern in PLACEHOLDER_PATTERNS) and (
        status != "proposed" or task.get("implementation_started") is True or completion_claim
    ):
        errors.append(
            f"{relative}/task.yaml: unresolved template placeholders are valid only while status is proposed"
        )

    for key in ("goal", "scope", "acceptance"):
        values = [str(item).strip() for item in as_list(task.get(key))]
        if not any(values):
            errors.append(f"{relative}/task.yaml: '{key}' must describe a concrete boundary")

    risk = str(task.get("risk") or "")
    if risk not in VALID_RISK_LEVELS:
        errors.append(f"{relative}/task.yaml: invalid risk '{risk}'")
    risk_reasons = [str(item).strip() for item in as_list(task.get("risk_reasons"))]
    if not risk_reasons or any(not item for item in risk_reasons):
        errors.append(f"{relative}/task.yaml: risk_reasons must contain at least one reason")
    floors: list[str] = []
    for reason in risk_reasons:
        floor = risk_factor_floor(reason)
        if floor is None:
            # v3 permits future extension reasons but a custom reason must carry
            # its risk implication so an older harness can fail safely.
            custom = re.fullmatch(r"custom-(low|medium|high):[a-z0-9]+(?:-[a-z0-9]+)*", reason)
            if custom:
                floor = custom.group(1)
        if floor:
            floors.append(floor)
    if floors and risk in RISK_LEVEL_RANK and RISK_LEVEL_RANK[risk] < RISK_LEVEL_RANK[highest_risk(floors)]:
        errors.append(f"{relative}/task.yaml: risk is below the declared risk-reason floor")
    high_impact = bool(set(risk_reasons) & V3_HIGH_RISK_REASONS) or any(
        reason.startswith("custom-high:") for reason in risk_reasons
    )
    for field, high_values in V3_HIGH_IMPACT_EFFECTS.items():
        if str(task.get(field) or "").strip().lower() in high_values:
            high_impact = True
    external_effects = str(task.get("external_effects") or "").strip().lower()
    if external_effects and external_effects != "none":
        high_impact = True
    if as_list(task.get("action_refs")):
        high_impact = True
    prose_risk_signals = goal_high_risk_signals(task.get("goal")) + goal_high_risk_signals(task.get("scope"))
    if prose_risk_signals:
        high_impact = True
    if high_impact and risk in RISK_LEVEL_RANK and risk != "high":
        errors.append(f"{relative}/task.yaml: risk is below the activated high-impact floor")

    resolved_refs: dict[str, list[Path]] = {}
    for field in ("context_refs", "decision_refs", "evidence_refs"):
        resolved_refs[field] = []
        for index, value in enumerate(as_list(task.get(field))):
            path = v3_project_relative_path(
                project_root,
                value,
                f"{relative}/task.yaml:{field}[{index}]",
                errors,
            )
            if path is not None:
                resolved_refs[field].append(path)

    protected_paths = [str(value).strip() for value in as_list(task.get("protected_paths"))]
    for index, value in enumerate(protected_paths):
        path = v3_project_relative_path(
            project_root,
            value,
            f"{relative}/task.yaml:protected_paths[{index}]",
            errors,
            require_exists=False,
            require_file=False,
        )
        if path is None:
            continue

    authority_basis = str(task.get("authorization_basis") or "").strip().lower()
    if authority_basis and not SLUG_RE.fullmatch(authority_basis):
        errors.append(
            f"{relative}/task.yaml: authorization_basis must be a normalized category slug, not literal approval language"
        )
    elif authority_basis in V3_AUTHORITY_DENIALS:
        errors.append(
            f"{relative}/task.yaml: '{authority_basis}' cannot establish human authorization"
        )
    unresolved = [str(value).strip() for value in as_list(task.get("unresolved_choices")) if str(value).strip()]
    if unresolved and (
        task.get("implementation_started") is True
        or completion_claim
    ):
        errors.append(
            f"{relative}/task.yaml: unresolved product choices cannot be crossed by implementation or completion claims"
        )

    optional_ref_fields = (
        "handoff_ref",
        "review_ref",
        "completion_acceptance_ref",
        "approved_baseline_ref",
        "implementation_render_ref",
        "baseline_decision_ref",
        "difference_decision_ref",
        "handoff_subject_ref",
        "merge_resolution_ref",
        "merge_resolution_subject_ref",
    )
    optional_paths: dict[str, Path | None] = {}
    for field in optional_ref_fields:
        if field not in task or task.get(field) is None:
            optional_paths[field] = None
            continue
        optional_paths[field] = v3_project_relative_path(
            project_root, task.get(field), f"{relative}/task.yaml:{field}", errors
        )
    for field, value in task.items():
        if field.startswith("x_") or not field.endswith("_ref") or field in optional_ref_fields or value is None:
            continue
        v3_project_relative_path(
            project_root, value, f"{relative}/task.yaml:{field}", errors
        )
    known_plural_refs = {
        "context_refs", "decision_refs", "evidence_refs", "action_refs",
        "approved_baseline_refs", "implementation_render_refs",
    }
    for field, values in task.items():
        if field.startswith("x_") or not field.endswith("_refs") or field in known_plural_refs:
            continue
        for index, value in enumerate(as_list(values)):
            v3_project_relative_path(
                project_root, value, f"{relative}/task.yaml:{field}[{index}]", errors
            )

    task_ref = f"{relative.as_posix()}/task.yaml"
    handoff_path = optional_paths.get("handoff_ref")
    if task.get("handoff_current") is True and handoff_path is None:
        errors.append(f"{relative}/task.yaml: handoff_current requires handoff_ref")
    if handoff_path is not None:
        v3_validate_claim_file(
            handoff_path, f"{relative}/task.yaml:handoff_ref", errors
        )
        if task.get("handoff_current") is True:
            try:
                handoff_record = v3_load_claim_record(handoff_path, "handoff")
            except (OSError, ValueError) as exc:
                errors.append(f"{relative}/task.yaml:handoff_ref: {exc}")
            else:
                handoff_task_ref = v3_project_relative_path(
                    project_root, handoff_record.get("task_ref"),
                    f"{relative}/task.yaml:handoff_ref:task_ref", errors,
                )
                if handoff_task_ref != task_file or str(handoff_record.get("task_ref") or "").strip() != task_ref:
                    errors.append(f"{relative}/task.yaml: current handoff task_ref must identify this exact task.yaml")
                handoff_subject_ref = None
                if handoff_record.get("subject_ref"):
                    handoff_subject_ref = v3_project_relative_path(
                        project_root, handoff_record.get("subject_ref"),
                        f"{relative}/task.yaml:handoff_ref:subject_ref", errors,
                    )
                v3_validate_subject(
                    project_root, handoff_record.get("subject"),
                    f"{relative}/task.yaml:handoff_ref:subject", errors,
                    artifact=handoff_subject_ref,
                    subject_paths=[str(value) for value in as_list(handoff_record.get("subject_paths"))],
                )
                for field, value in handoff_record.items():
                    if not field.startswith("x_") and field.endswith("_ref") and field not in {"task_ref", "subject_ref"} and value:
                        v3_project_relative_path(
                            project_root, value,
                            f"{relative}/task.yaml:handoff_ref:{field}", errors,
                        )
                    elif not field.startswith("x_") and field.endswith("_refs"):
                        for index, item in enumerate(as_list(value)):
                            v3_project_relative_path(
                                project_root, item,
                                f"{relative}/task.yaml:handoff_ref:{field}[{index}]", errors,
                            )
    review_path = optional_paths.get("review_ref")
    conformance = str(task.get("conformance_status") or "not_required")
    conformance_claim = conformance in {"matched", "differences_accepted"}
    review_required = (
        task.get("review_current") is True
        or (completion_claim and high_impact)
        or conformance_claim
    )
    review_record: dict[str, Any] | None = None
    if review_required and review_path is None:
        errors.append(f"{relative}/task.yaml: activated formal review claim requires review_ref")
    if review_path is not None:
        v3_validate_claim_file(review_path, f"{relative}/task.yaml:review_ref", errors)
        if review_required:
            v3_validate_record_body(review_path, f"{relative}/task.yaml:review_ref", errors)
            try:
                review_record = v3_load_claim_record(review_path, "review")
            except (OSError, ValueError) as exc:
                errors.append(f"{relative}/task.yaml:review_ref: {exc}")
            else:
                review_task_ref = v3_project_relative_path(
                    project_root, review_record.get("task_ref"),
                    f"{relative}/task.yaml:review_ref:task_ref", errors,
                )
                if review_task_ref != task_file or str(review_record.get("task_ref") or "").strip() != task_ref:
                    errors.append(f"{relative}/task.yaml: current review task_ref must identify this exact task.yaml")
                review_subject_ref = None
                if review_record.get("subject_ref"):
                    review_subject_ref = v3_project_relative_path(
                        project_root, review_record.get("subject_ref"),
                        f"{relative}/task.yaml:review_ref:subject_ref", errors,
                    )
                v3_validate_subject(
                    project_root, review_record.get("subject"),
                    f"{relative}/task.yaml:review_ref:subject", errors,
                    artifact=review_subject_ref,
                    subject_paths=[str(value) for value in as_list(review_record.get("subject_paths"))],
                )
                if completion_claim and high_impact:
                    if str(review_record.get("verdict") or "") != "passed":
                        errors.append(f"{relative}/task.yaml: high-impact completion requires review verdict: passed")
                    if str(review_record.get("mode") or "") != "independent_actor":
                        errors.append(f"{relative}/task.yaml: high-impact completion requires review mode: independent_actor")
                    if review_record.get("actor_modified_subject") is not False:
                        errors.append(f"{relative}/task.yaml: reviewer who modified the subject is not independent")
                for field, value in review_record.items():
                    if not field.startswith("x_") and field.endswith("_ref") and field not in {"task_ref", "subject_ref"} and value:
                        v3_project_relative_path(
                            project_root, value,
                            f"{relative}/task.yaml:review_ref:{field}", errors,
                        )
                    elif not field.startswith("x_") and field.endswith("_refs"):
                        for index, item in enumerate(as_list(value)):
                            v3_project_relative_path(
                                project_root, item,
                                f"{relative}/task.yaml:review_ref:{field}[{index}]", errors,
                            )
    if conformance not in V3_CONFORMANCE_STATUSES:
        errors.append(f"{relative}/task.yaml: invalid conformance_status '{conformance}'")
    for ambiguous_field in ("approved_baseline_refs", "implementation_render_refs"):
        if ambiguous_field in task:
            errors.append(
                f"{relative}/task.yaml: {ambiguous_field} is ambiguous; use the singular stable reference"
            )
    if conformance in {"matched", "differences_accepted"} and (
        not task.get("approved_baseline_subject")
        or not task.get("implementation_render_subject")
    ):
        errors.append(
            f"{relative}/task.yaml: conformance claim requires stable approved-baseline and implementation-render subjects"
        )
    if conformance in {"matched", "differences_accepted"}:
        if optional_paths.get("baseline_decision_ref") is None:
            errors.append(
                f"{relative}/task.yaml: approved-baseline conformance requires an explicit human decision reference"
            )
        else:
            v3_validate_decision_file(
                optional_paths["baseline_decision_ref"],
                f"{relative}/task.yaml:baseline_decision_ref",
                errors,
            )
        local_baseline = optional_paths.get("approved_baseline_ref")
        baseline_subject = str(task.get("approved_baseline_subject") or "").strip()
        baseline_is_provider = v3_validate_provider_visual_subject(
            baseline_subject,
            f"{relative}/task.yaml:approved_baseline_subject",
            errors,
        )
        if baseline_is_provider:
            v3_validate_subject(
                project_root,
                baseline_subject,
                f"{relative}/task.yaml:approved_baseline_subject",
                errors,
            )
            if local_baseline is not None:
                v3_validate_claim_file(
                    local_baseline,
                    f"{relative}/task.yaml:approved_baseline_ref",
                    errors,
                )
        elif baseline_subject:
            if local_baseline is None:
                errors.append(
                    f"{relative}/task.yaml: sha256/local approved baseline subject requires approved_baseline_ref"
                )
            else:
                v3_validate_visual_artifact(
                    local_baseline,
                    f"{relative}/task.yaml:approved_baseline_ref",
                    errors,
                    role="baseline",
                )
                v3_validate_subject(
                    project_root,
                    baseline_subject,
                    f"{relative}/task.yaml:approved_baseline_subject",
                    errors,
                    artifact=local_baseline,
                )
                if not baseline_subject.lower().startswith("sha256:"):
                    errors.append(f"{relative}/task.yaml: local approved baseline must be bound by sha256 or a stable provider subject")
        local_render = optional_paths.get("implementation_render_ref")
        render_subject = str(task.get("implementation_render_subject") or "").strip()
        render_is_provider = v3_validate_provider_visual_subject(
            render_subject,
            f"{relative}/task.yaml:implementation_render_subject",
            errors,
        )
        if render_is_provider:
            v3_validate_subject(
                project_root,
                render_subject,
                f"{relative}/task.yaml:implementation_render_subject",
                errors,
            )
            if local_render is not None:
                v3_validate_claim_file(
                    local_render,
                    f"{relative}/task.yaml:implementation_render_ref",
                    errors,
                )
        elif render_subject:
            if local_render is None:
                errors.append(
                    f"{relative}/task.yaml: sha256/local implementation render subject requires implementation_render_ref"
                )
            else:
                v3_validate_visual_artifact(
                    local_render,
                    f"{relative}/task.yaml:implementation_render_ref",
                    errors,
                    role="render",
                )
                v3_validate_subject(
                    project_root,
                    render_subject,
                    f"{relative}/task.yaml:implementation_render_subject",
                    errors,
                    artifact=local_render,
                )
                if not render_subject.lower().startswith("sha256:"):
                    errors.append(f"{relative}/task.yaml: local implementation render must be bound by sha256 or a stable provider subject")
        if review_record is not None:
            if str(review_record.get("verdict") or "") != "passed":
                errors.append(f"{relative}/task.yaml: visual conformance requires review verdict: passed")
            if str(review_record.get("baseline_subject") or "").strip() != str(task.get("approved_baseline_subject") or "").strip():
                errors.append(f"{relative}/task.yaml: conformance review must bind the exact approved_baseline_subject")
            if str(review_record.get("implementation_render_subject") or "").strip() != str(task.get("implementation_render_subject") or "").strip():
                errors.append(f"{relative}/task.yaml: conformance review must bind the exact implementation_render_subject")
        if conformance == "differences_accepted":
            if optional_paths.get("difference_decision_ref") is None:
                errors.append(
                    f"{relative}/task.yaml: accepted visual differences require an exact human decision record"
                )
            else:
                v3_validate_decision_file(
                    optional_paths["difference_decision_ref"],
                    f"{relative}/task.yaml:difference_decision_ref",
                    errors,
                )
    if str(task.get("visual_alignment") or "") == "reserved" and (
        task.get("implementation_started") is True
        or conformance != "not_required"
    ):
        if str(task.get("visual_alignment_status") or "") not in {"accepted", "delegated"}:
            errors.append(
                f"{relative}/task.yaml: reserved human visual preference is unresolved"
            )

    action_records: list[tuple[Path, dict[str, Any]]] = []
    action_ref_values = as_list(task.get("action_refs"))
    for index, raw_ref in enumerate(action_ref_values):
        action_path = v3_project_relative_path(
            project_root,
            raw_ref,
            f"{relative}/task.yaml:action_refs[{index}]",
            errors,
        )
        if action_path is not None:
            v3_validate_action_record(project_root, action_path, errors)
            try:
                action_records.append((action_path, v3_load_action_record(action_path)))
            except (OSError, ValueError):
                pass
    if action_ref_values:
        high_impact = True
        if risk != "high":
            errors.append(f"{relative}/task.yaml: activated high-impact action records require risk: high")
    action_ids: dict[str, Path] = {}
    for action_path, record in action_records:
        action_id = str(record.get("action_id") or "").strip()
        if action_id and action_id in action_ids:
            errors.append(
                f"{relative}/task.yaml: action_id '{action_id}' is duplicated across action_refs"
            )
        elif action_id:
            action_ids[action_id] = action_path
    action_groups: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    for action_path, record in action_records:
        key = str(record.get("idempotency_key") or "").strip()
        if key:
            action_groups.setdefault(key, []).append((action_path, record))
    action_group_terminal: dict[str, bool] = {}
    for key, rows in sorted(action_groups.items()):
        identities = {
            (
                str(record.get("target") or "").strip(),
                str(record.get("environment") or "").strip(),
                str(record.get("payload_scope") or "").strip(),
                str(record.get("subject") or "").strip(),
            )
            for _, record in rows
        }
        if len(identities) > 1:
            errors.append(
                f"{relative}/task.yaml: idempotency key '{key}' is reused with a different target, environment, payload scope, or subject"
            )
        states = [str(record.get("status") or "").strip() for _, record in rows]
        has_reconciliation = False
        reconciliation_results: set[str] = set()
        for _, record in rows:
            if not record.get("reconciliation_ref"):
                continue
            reconciliation_path = v3_project_relative_path(
                project_root, record.get("reconciliation_ref"),
                f"{relative}/task.yaml:action reconciliation_ref", [],
            )
            outcome = str(record.get("reconciliation_result") or "").strip().lower()
            if (
                reconciliation_path is not None
                and v3_claim_file_is_substantive(reconciliation_path)
                and outcome in {"effect-confirmed", "no-effect-confirmed", "compensated-confirmed"}
            ):
                has_reconciliation = True
                reconciliation_results.add(outcome)
        if "unknown" in states and not has_reconciliation and any(
            state in {"authorized", "executing", "succeeded", "failed", "compensated"}
            for state in states
        ):
            errors.append(
                f"{relative}/task.yaml: unknown outcome for idempotency key '{key}' requires reconciliation before retry"
            )
        effect_rows = sum(state in V3_ACTION_EFFECT_STATUSES for state in states)
        if effect_rows > 1:
            errors.append(
                f"{relative}/task.yaml: idempotency key '{key}' must represent only one external effect"
            )
        action_group_terminal[key] = (
            (
                any(state in {"succeeded", "compensated"} for state in states)
                or ("failed" in states and bool(reconciliation_results & {"no-effect-confirmed", "compensated-confirmed"}))
            )
            and not ("unknown" in states and not has_reconciliation)
        )

    if completion_claim and high_impact and review_record is not None:
        review_action_refs = [str(value).strip() for value in as_list(review_record.get("action_refs"))]
        task_action_refs = [str(value).strip() for value in action_ref_values]
        if sorted(review_action_refs) != sorted(task_action_refs):
            errors.append(
                f"{relative}/task.yaml: high-impact review action_refs must exactly cover task action_refs"
            )
        required_review_paths = set(task_action_refs)
        for _, record in action_records:
            if record.get("subject_ref"):
                required_review_paths.add(str(record.get("subject_ref")).strip())
            required_review_paths.update(
                str(value).strip()
                for value in as_list(record.get("subject_paths"))
                if str(value).strip()
            )
        review_subject_paths = {
            str(value).strip()
            for value in as_list(review_record.get("subject_paths"))
            if str(value).strip()
        }
        missing_review_paths = sorted(required_review_paths - review_subject_paths)
        if missing_review_paths:
            errors.append(
                f"{relative}/task.yaml: high-impact review subject_paths omit action scope: {', '.join(missing_review_paths)}"
            )
        if task_action_refs:
            review_subject = str(review_record.get("subject") or "").strip().lower()
            if not (
                review_subject.startswith("git:")
                or review_subject.startswith("worktree:")
                or review_subject.startswith("patch:")
            ):
                errors.append(
                    f"{relative}/task.yaml: high-impact action review requires a scoped git/worktree subject"
                )

    overlap_paths = [str(value).strip() for value in as_list(task.get("parallel_overlap_paths")) if str(value).strip()]
    for index, value in enumerate(overlap_paths):
        v3_project_relative_path(
            project_root, value,
            f"{relative}/task.yaml:parallel_overlap_paths[{index}]", errors,
            require_exists=False, require_file=False,
        )
    integration_status = str(task.get("integration_status") or "").strip().lower()
    if integration_status in {"resolved", "merged"}:
        merge_ref = optional_paths.get("merge_resolution_ref")
        if merge_ref is None:
            errors.append(f"{relative}/task.yaml: resolved integration requires merge_resolution_ref")
        else:
            v3_validate_decision_file(merge_ref, f"{relative}/task.yaml:merge_resolution_ref", errors)
        merge_subject = str(task.get("merge_resolution_subject") or "").strip().lower()
        merge_paths = [str(value) for value in as_list(task.get("merge_resolution_subject_paths"))]
        if not (merge_subject.startswith("git:") or merge_subject.startswith("worktree:") or merge_subject.startswith("patch:")):
            errors.append(
                f"{relative}/task.yaml: resolved integration subject must bind a git commit or scoped worktree digest"
            )
        if not merge_paths:
            errors.append(f"{relative}/task.yaml: resolved integration subject requires combined source subject_paths")
        missing_overlap_paths = sorted(set(overlap_paths) - {str(value).strip() for value in merge_paths})
        if missing_overlap_paths:
            errors.append(
                f"{relative}/task.yaml: resolved integration subject_paths must cover every parallel_overlap_path: {', '.join(missing_overlap_paths)}"
            )
        if task.get("merge_resolution_subject_ref"):
            errors.append(
                f"{relative}/task.yaml: merge_resolution_subject_ref cannot substitute a combined source scope"
            )
        v3_validate_subject(
            project_root, merge_subject,
            f"{relative}/task.yaml:merge_resolution_subject", errors,
            subject_paths=merge_paths,
        )
    if completion_claim:
        if high_impact and not action_records and external_effects != "none":
            errors.append(
                f"{relative}/task.yaml: high-impact completion requires action_refs or explicit external_effects: none"
            )
        if action_records:
            if not action_groups or not all(action_group_terminal.values()):
                errors.append(
                    f"{relative}/task.yaml: completion cannot claim unfinished or ambiguous external actions"
                )
        acceptance_required = (
            risk == "high"
            or task.get("material_deviation") is True
            or bool(task.get("residual_risk"))
            or task.get("human_completion_reserved") is True
        )
        if acceptance_required and optional_paths.get("completion_acceptance_ref") is None:
            errors.append(
                f"{relative}/task.yaml: risk or deviation requires exact Human Completion acceptance before done"
            )
        elif acceptance_required:
            v3_validate_claim_file(
                optional_paths["completion_acceptance_ref"],
                f"{relative}/task.yaml:completion_acceptance_ref",
                errors,
            )
    return task_id or None


def check_project_v3(project_root: Path, mode: str = "focus") -> list[str]:
    errors: list[str] = []
    selected_root = project_root.absolute()
    selected_symlink = first_symlink_component(selected_root)
    project_root = selected_root.resolve()
    if selected_symlink is not None:
        errors.append(
            f"selected project root traverses symlink component {selected_symlink}; authority paths must not be redirected"
        )
    for relative in ("AGENTS.md", "project/state.yaml"):
        path = project_root / relative
        symlink = first_symlink_component(path)
        if symlink is not None:
            errors.append(
                f"{relative}: project authority path traverses symlink component {symlink}"
            )
        elif not path.is_file():
            errors.append(f"missing regular project authority file: {relative}")

    state_path = project_root / "project" / "state.yaml"
    if first_symlink_component(state_path) is not None or not state_path.is_file():
        return errors
    project_authority = project_root / "project"
    if project_authority.is_dir():
        try:
            project_descendants = sorted(project_authority.rglob("*"))
        except OSError as exc:
            errors.append(f"project: cannot inspect authority descendants: {exc}")
            project_descendants = []
        for descendant in project_descendants:
            if descendant.is_symlink():
                errors.append(
                    f"{descendant.relative_to(project_root)}: project authority descendant must not be a symlink"
                )
    try:
        state = load_v3_yaml(state_path)
    except (OSError, ValueError) as exc:
        errors.append(f"project/state.yaml: {exc}")
        return errors
    for key in V3_REQUIRED_STATE_KEYS:
        if key not in state:
            errors.append(f"project/state.yaml: missing required field '{key}'")
    if state.get("schema_version") != 3:
        errors.append("project/state.yaml: schema_version must be 3")
    if str(state.get("protocol_version") or "") != CONTINUITY_KERNEL_PROTOCOL:
        errors.append('project/state.yaml: protocol_version must be "3.0"')

    if "focus_task" in state:
        errors.append("project/state.yaml: focus_task alias is not part of protocol 3.0; use active_task")
    if "protected_paths" in state:
        errors.append("project/state.yaml: protected_paths belongs to task.yaml, not recovery state")
    active_value = state.get("active_task")
    focus_id = "" if active_value is None else str(active_value).strip()
    if focus_id and not V3_TASK_NAME_RE.fullmatch(focus_id):
        errors.append(f"project/state.yaml: active_task recovery focus '{focus_id}' is invalid")

    selected: list[tuple[str, tuple[Path, str]]] = []
    work_root = project_root / "work"
    work_symlink = first_symlink_component(work_root)
    if work_symlink is not None:
        errors.append(f"work: task authority root traverses symlink component {work_symlink}")
    active_root_symlink = first_symlink_component(work_root / "active")
    if work_symlink is None and active_root_symlink is not None:
        errors.append(
            f"work/active: task authority root traverses symlink component {active_root_symlink}"
        )
    elif mode == "full":
        task_locations: dict[str, tuple[Path, str]] = {}
        for location in ("active", "archive"):
            root = work_root / location
            root_symlink = first_symlink_component(root)
            if root_symlink is not None:
                errors.append(f"work/{location}: task authority root traverses symlink component {root_symlink}")
                continue
            if not root.is_dir():
                continue
            try:
                children = sorted(root.iterdir())
            except OSError as exc:
                errors.append(f"work/{location}: cannot inspect task authority root: {exc}")
                continue
            for path in children:
                if path.is_symlink():
                    errors.append(f"{path.relative_to(project_root)}: task authority path must not be a symlink")
                    continue
                if not path.is_dir():
                    continue
                if path.name in task_locations:
                    errors.append(f"duplicate task id '{path.name}' across work/active and work/archive")
                task_locations[path.name] = (path, location)
        selected = list(task_locations.items())
    elif focus_id:
        focus_dir = work_root / "active" / focus_id
        focus_symlink = first_symlink_component(focus_dir)
        if focus_symlink is not None:
            errors.append(
                f"work/active/{focus_id}: recovery-focus authority traverses symlink component {focus_symlink}"
            )
        elif not focus_dir.is_dir():
            errors.append(f"project/state.yaml: active_task recovery focus '{focus_id}' does not exist in work/active")
        else:
            selected = [(focus_id, (focus_dir, "active"))]

    for _, (task_dir, location) in selected:
        task_path = task_dir / "task.yaml"
        task_symlink = first_symlink_component(task_path)
        if task_symlink is not None:
            errors.append(
                f"{task_path.relative_to(project_root)}: task authority path traverses symlink component {task_symlink}"
            )
            continue
        try:
            record = load_v3_yaml(task_path) if task_path.is_file() else {}
        except (OSError, ValueError):
            record = {}
        task_schema = record.get("schema_version", 1)
        task_protocol = str(record.get("protocol_version") or "").strip()
        if task_schema == 3 or task_protocol == CONTINUITY_KERNEL_PROTOCOL:
            v3_validate_task(project_root, task_dir, location, mode, errors)
        else:
            legacy_schema = task_schema if task_schema in {1, 2} else 1
            legacy_protocol = (
                task_protocol if task_protocol in SUPPORTED_GOVERNANCE_PROTOCOLS else None
            )
            check_task(
                task_dir,
                location,
                project_root,
                legacy_schema,
                legacy_protocol,
                "9999-12-31T23:59:59Z",
                set(),
                errors,
            )

    return errors


def check_project(
    project_root: Path,
    target_schema: int | None = None,
    target_protocol: str | None = None,
    mode: str = "focus",
    migration: bool = False,
) -> list[str]:
    # Detect the compact v3 kernel before applying legacy structural
    # requirements.  Migration mode is deliberately read-only and performs a
    # full scan of whichever protocol the repository already declares.
    probe = project_root.absolute() / "project" / "state.yaml"
    probe_symlink = first_symlink_component(probe)
    if probe_symlink is not None:
        return [
            f"project/state.yaml: project authority path traverses symlink component {probe_symlink}"
        ]
    if probe.is_file() and not probe.is_symlink():
        try:
            probed_state = load_v3_yaml(probe)
        except (OSError, ValueError):
            probed_state = {}
        actual_v3 = (
            probed_state.get("schema_version") == 3
            or str(probed_state.get("protocol_version") or "") == CONTINUITY_KERNEL_PROTOCOL
        )
        target_v3 = (
            target_schema == 3 or target_protocol == CONTINUITY_KERNEL_PROTOCOL
        )
        if actual_v3:
            return check_project_v3(project_root, "full" if migration else mode)
        if target_v3:
            return [
                'project/state.yaml: migration preflight requires adopting schema_version: 3 and protocol_version: "3.0"; existing legacy records may remain unchanged'
            ]

    errors: list[str] = []
    selected_project_root = project_root.absolute()
    selected_root_symlink = first_symlink_component(selected_project_root)
    project_root = selected_project_root.resolve()
    if selected_root_symlink is not None:
        errors.append(
            f"selected project root traverses symlink component {selected_root_symlink}; project-memory authority paths must not be redirected"
        )
    for relative in REQUIRED_PROJECT_FILES:
        if not (project_root / relative).is_file():
            errors.append(f"missing required project file: {relative}")

    for relative in ("project/decisions", "milestones", "work/active", "work/archive", "templates"):
        if not (project_root / relative).is_dir():
            errors.append(f"missing required directory: {relative}/")

    state_file = project_root / "project" / "state.yaml"
    state: dict[str, Any] = {}
    project_schema = 1
    project_protocol: str | None = None
    if state_file.is_symlink():
        errors.append("project/state.yaml: project-memory authority file must not be a symlink")
    elif state_file.is_file():
        try:
            state = load_flat_yaml(state_file)
        except ValueError as exc:
            errors.append(f"project/state.yaml: {exc}")
        for key in (
            "schema_version",
            "project_id",
            "project_name",
            "status",
            "active_milestone",
            "active_task",
            "updated",
            "source_of_truth",
        ):
            if key not in state:
                errors.append(f"project/state.yaml: missing required field '{key}'")
        raw_project_schema = state.get("schema_version", 1)
        if isinstance(raw_project_schema, int) and raw_project_schema in {1, 2}:
            project_schema = raw_project_schema
        else:
            errors.append("project/state.yaml: schema_version must be 1 or 2")
        raw_project_protocol = state.get("governance_protocol_version")
        if raw_project_protocol is not None:
            normalized_protocol = str(raw_project_protocol).strip()
            if normalized_protocol in SUPPORTED_GOVERNANCE_PROTOCOLS:
                project_protocol = normalized_protocol
            else:
                errors.append(
                    "project/state.yaml: governance_protocol_version must be \"2.1\" or \"2.2\" when present"
                )
    effective_schema = target_schema or project_schema
    effective_protocol = target_protocol or project_protocol
    if effective_protocol in SUPPORTED_GOVERNANCE_PROTOCOLS:
        if str(state.get("governance_protocol_version") or "").strip() != effective_protocol:
            errors.append(
                f'project/state.yaml: target governance requires governance_protocol_version: "{effective_protocol}"'
            )
        structural_paths = (
            *(project_root / relative for relative in REQUIRED_PROJECT_FILES),
            project_root / "project",
            project_root / "project" / "decisions",
            project_root / "milestones",
            project_root / "work",
            project_root / "work" / "active",
            project_root / "work" / "archive",
            project_root / "templates",
        )
        for structural_path in structural_paths:
            if structural_path.is_symlink():
                errors.append(
                    f"{structural_path.relative_to(project_root)}: protocol {effective_protocol} authority paths must not be symlinks"
                )
        for authority_root in (
            project_root / "project" / "decisions",
            project_root / "milestones",
            project_root / "templates",
        ):
            if not authority_root.is_dir() or authority_root.is_symlink():
                continue
            for descendant in authority_root.rglob("*"):
                if descendant.is_symlink():
                    errors.append(
                        f"{descendant.relative_to(project_root)}: protocol {effective_protocol} authority descendants must not be symlinks"
                    )
    legacy_archive_ids: set[str] = set()
    legacy_manifest_available = False
    protocol_version_adopted_at: Any = None
    if effective_protocol in SUPPORTED_GOVERNANCE_PROTOCOLS:
        if effective_schema != 2:
            errors.append(f"project/state.yaml: governance protocol {effective_protocol} requires schema_version: 2")
        if "governance_protocol_adopted_at" not in state:
            errors.append(
                f"project/state.yaml: governance protocol {effective_protocol} requires governance_protocol_adopted_at"
            )
        elif parse_iso_datetime(state.get("governance_protocol_adopted_at")) is None:
            errors.append(
                "project/state.yaml: governance_protocol_adopted_at must be an ISO date or date-time"
            )
        if "governance_protocol_adoption_commit" not in state:
            errors.append(
                f"project/state.yaml: governance protocol {effective_protocol} requires governance_protocol_adoption_commit; use null when legacy_archive_ids is empty"
            )
        if "legacy_archive_ids" not in state:
            errors.append(
                f"project/state.yaml: governance protocol {effective_protocol} requires legacy_archive_ids; list only pre-adoption archived task IDs"
            )
        elif not isinstance(state.get("legacy_archive_ids"), list):
            errors.append("project/state.yaml: legacy_archive_ids must be a list")
        else:
            legacy_manifest_available = True
            legacy_values = [str(value).strip() for value in state.get("legacy_archive_ids", [])]
            if any(not value for value in legacy_values):
                errors.append("project/state.yaml: legacy_archive_ids must not contain empty IDs")
            if len(legacy_values) != len(set(legacy_values)):
                errors.append("project/state.yaml: legacy_archive_ids must not contain duplicates")
            invalid_legacy = [value for value in legacy_values if not TASK_NAME_RE.fullmatch(value)]
            if invalid_legacy:
                errors.append(
                    f"project/state.yaml: legacy_archive_ids contains invalid task ID(s): {', '.join(invalid_legacy)}"
                )
            legacy_archive_ids = set(legacy_values)
        if effective_protocol == ADAPTIVE_REVIEW_PROTOCOL:
            if "governance_protocol_version_adopted_at" not in state:
                errors.append(
                    "project/state.yaml: governance protocol 2.2 requires governance_protocol_version_adopted_at"
                )
            else:
                protocol_version_adopted_at = state.get(
                    "governance_protocol_version_adopted_at"
                )
                if parse_iso_datetime(protocol_version_adopted_at) is None:
                    errors.append(
                        "project/state.yaml: governance_protocol_version_adopted_at must be an ISO date or date-time"
                    )
                original_adoption = parse_iso_datetime(
                    state.get("governance_protocol_adopted_at")
                )
                version_adoption = parse_iso_datetime(protocol_version_adopted_at)
                if (
                    original_adoption is not None
                    and version_adoption is not None
                    and original_adoption.tzinfo is None
                    and version_adoption.tzinfo is not None
                ):
                    original_adoption = original_adoption.replace(
                        tzinfo=version_adoption.tzinfo
                    )
                elif (
                    original_adoption is not None
                    and version_adoption is not None
                    and original_adoption.tzinfo is not None
                    and version_adoption.tzinfo is None
                ):
                    version_adoption = version_adoption.replace(
                        tzinfo=original_adoption.tzinfo
                    )
                if (
                    original_adoption is not None
                    and version_adoption is not None
                    and version_adoption < original_adoption
                ):
                    errors.append(
                        "project/state.yaml: governance_protocol_version_adopted_at must not precede governance_protocol_adopted_at"
                    )

    if (
        target_protocol == ADAPTIVE_REVIEW_PROTOCOL
        and project_protocol != ADAPTIVE_REVIEW_PROTOCOL
        and parse_iso_datetime(protocol_version_adopted_at) is None
    ):
        # A read-only upgrade preview cannot know the future adoption instant yet.
        # Treat already-terminal 2.1 archives as provisionally historical so the
        # preflight reports the missing adoption fact and active migration work,
        # rather than falsely demanding that every valid 2.1 archive be rewritten.
        protocol_version_adopted_at = "9999-12-31T23:59:59Z"

    protocol_exempt_archive_ids = legacy_archive_ids
    if (
        effective_protocol in SUPPORTED_GOVERNANCE_PROTOCOLS
        and not legacy_manifest_available
    ):
        archive_root = project_root / "work" / "archive"
        protocol_exempt_archive_ids = (
            {
                path.name
                for path in archive_root.iterdir()
                if path.is_dir()
            }
            if archive_root.is_dir()
            else set()
        )

    task_ids: dict[str, Path] = {}
    for location in ("active", "archive"):
        task_root = project_root / "work" / location
        if task_root.is_symlink():
            errors.append(
                f"work/{location}: project-memory task root must not be a symlink"
            )
            continue
        if not task_root.is_dir():
            continue
        for task_dir in sorted(task_root.iterdir()):
            if task_dir.is_symlink():
                errors.append(
                    f"{task_dir.relative_to(project_root)}: project-memory task directory must not be a symlink"
                )
                continue
            if not task_dir.is_dir():
                continue
            task_id = check_task(
                task_dir,
                location,
                project_root,
                effective_schema,
                effective_protocol,
                protocol_version_adopted_at,
                protocol_exempt_archive_ids,
                errors,
            )
            if task_id:
                if task_id in task_ids:
                    errors.append(
                        f"duplicate task id '{task_id}' in {task_ids[task_id].relative_to(project_root)} and {task_dir.relative_to(project_root)}"
                    )
                task_ids[task_id] = task_dir

    if effective_protocol in SUPPORTED_GOVERNANCE_PROTOCOLS:
        validate_legacy_adoption_anchor(
            project_root,
            state,
            legacy_archive_ids,
            task_ids,
            errors,
        )

    for legacy_id in sorted(legacy_archive_ids):
        legacy_path = task_ids.get(legacy_id)
        if legacy_path is None:
            errors.append(
                f"project/state.yaml: legacy_archive_ids task '{legacy_id}' does not exist"
            )
        elif "work/archive" not in str(legacy_path.relative_to(project_root)):
            errors.append(
                f"project/state.yaml: legacy_archive_ids task '{legacy_id}' is not in work/archive"
            )
        else:
            try:
                legacy_task = load_flat_yaml(legacy_path / "task.yaml")
            except (OSError, ValueError):
                continue
            for provenance_field in ("created", "updated"):
                if not not_after_adoption(
                    legacy_task.get(provenance_field),
                    state.get("governance_protocol_adopted_at"),
                ):
                    errors.append(
                        f"project/state.yaml: legacy archive task '{legacy_id}' {provenance_field} after governance_protocol_adopted_at or invalid and cannot be downgraded"
                    )
            if not chronological_timestamps(
                legacy_task.get("created"),
                legacy_task.get("updated"),
            ):
                errors.append(
                    f"project/state.yaml: legacy archive task '{legacy_id}' requires valid created <= updated provenance"
                )

    active_task = state.get("active_task")
    if active_task and str(active_task) not in task_ids:
        errors.append(f"project/state.yaml: active_task '{active_task}' does not exist")
    elif active_task and "work/active" not in str(task_ids[str(active_task)].relative_to(project_root)):
        errors.append(f"project/state.yaml: active_task '{active_task}' is not in work/active")

    active_task_records: dict[str, dict[str, Any]] = {}
    for task_id, task_path in task_ids.items():
        if task_path.parent.name != "active":
            continue
        try:
            active_task_records[task_id] = load_flat_yaml(task_path / "task.yaml")
        except (OSError, ValueError):
            continue

    active_task_id = str(active_task or "").strip()
    if effective_protocol == ADAPTIVE_REVIEW_PROTOCOL:
        execution_task_ids = sorted(
            task_id
            for task_id, task_record in active_task_records.items()
            if str(task_record.get("status") or "")
            in {"approved", "implementing", "reviewing", "verifying"}
        )
        if len(execution_task_ids) > 1:
            errors.append(
                "project/state.yaml: protocol 2.2 permits only one approved-through-verifying active task"
            )
        if execution_task_ids and active_task_id not in execution_task_ids:
            errors.append(
                "project/state.yaml: active_task must point to the approved-through-verifying task"
            )
        pointed_record = active_task_records.get(active_task_id)
        if pointed_record is not None and str(pointed_record.get("status") or "") == "proposed":
            errors.append(
                "project/state.yaml: active_task must remain null while the task is proposed"
            )

    active_milestone = str(state.get("active_milestone") or "").strip()
    active_milestone_record: dict[str, Any] | None = None
    if effective_protocol in SUPPORTED_GOVERNANCE_PROTOCOLS:
        if active_milestone:
            milestone_root = project_root / "milestones"
            matches = [
                path
                for path in milestone_root.iterdir()
                if path.is_dir()
                and not path.is_symlink()
                and (path.name == active_milestone or path.name.startswith(f"{active_milestone}-"))
            ] if milestone_root.is_dir() and not milestone_root.is_symlink() else []
            if len(matches) != 1:
                errors.append(
                    f"project/state.yaml: active_milestone '{active_milestone}' must resolve to exactly one regular directory under milestones/"
                )
            else:
                milestone_dir = matches[0]
                for required_name in ("milestone.yaml", "brief.md"):
                    required_path = milestone_dir / required_name
                    if required_path.is_symlink() or not required_path.is_file():
                        errors.append(
                            f"{required_path.relative_to(project_root)}: active milestone authority file must be a regular file"
                        )
                milestone_file = milestone_dir / "milestone.yaml"
                if milestone_file.is_file() and not milestone_file.is_symlink():
                    try:
                        milestone = load_flat_yaml(milestone_file)
                    except ValueError as exc:
                        errors.append(
                            f"{milestone_file.relative_to(project_root)}: {exc}"
                        )
                    else:
                        active_milestone_record = milestone
                        if str(milestone.get("id") or "") != active_milestone:
                            errors.append(
                                f"{milestone_file.relative_to(project_root)}: id must match project/state.yaml active_milestone"
                            )

    if effective_protocol == ADAPTIVE_REVIEW_PROTOCOL and active_task_id:
        pointed_record = active_task_records.get(active_task_id)
        if pointed_record is not None:
            task_milestone = str(pointed_record.get("milestone") or "").strip()
            if not active_milestone:
                errors.append(
                    "project/state.yaml: active_task requires active_milestone"
                )
            elif task_milestone != active_milestone:
                errors.append(
                    f"work/active/{active_task_id}/task.yaml: milestone must match project/state.yaml active_milestone"
                )
            if active_milestone_record is not None:
                milestone_tasks = {
                    str(item).strip()
                    for item in as_list(active_milestone_record.get("tasks"))
                    if str(item).strip()
                }
                if active_task_id not in milestone_tasks:
                    errors.append(
                        f"project/state.yaml: active_task '{active_task_id}' must be indexed by the active milestone"
                    )

    check_markdown_links(project_root, errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate durable project-memory governance.")
    parser.add_argument("project_root", nargs="?", default=".")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--focus",
        action="store_true",
        help="Validate the recovery focus and its activated overlays (protocol 3.0 default).",
    )
    mode.add_argument(
        "--full",
        action="store_true",
        help="Validate every task and completion claim.",
    )
    mode.add_argument(
        "--migration",
        action="store_true",
        help="Run a read-only full compatibility/migration audit.",
    )
    parser.add_argument(
        "--target-schema",
        type=int,
        choices=(2, 3),
        help="Run a read-only migration preflight against the target schema.",
    )
    parser.add_argument(
        "--target-protocol",
        choices=(*SUPPORTED_GOVERNANCE_PROTOCOLS, CONTINUITY_KERNEL_PROTOCOL),
        help="Run a read-only migration preflight against the target governance protocol.",
    )
    args = parser.parse_args()
    project_root = Path(args.project_root)
    if not project_root.is_dir():
        print(f"ERROR project root does not exist: {project_root}")
        return 2

    declared_v3 = False
    state_probe = project_root / "project" / "state.yaml"
    if state_probe.is_file() and not state_probe.is_symlink():
        try:
            state_record = load_v3_yaml(state_probe)
        except (OSError, ValueError):
            state_record = {}
        declared_v3 = (
            state_record.get("schema_version") == 3
            or str(state_record.get("protocol_version") or "") == CONTINUITY_KERNEL_PROTOCOL
        )

    errors = check_project(
        project_root,
        target_schema=args.target_schema,
        target_protocol=args.target_protocol,
        mode="full" if args.full else "focus",
        migration=args.migration,
    )
    if errors:
        targets: list[str] = []
        if args.target_schema:
            targets.append(f"schema {args.target_schema}")
        if args.target_protocol:
            targets.append(f"protocol {args.target_protocol}")
        prefix = f"Project memory target {' / '.join(targets)} preflight" if targets else "Project memory check"
        print(f"{prefix} failed with {len(errors)} error(s):")
        for error in errors:
            print(f"ERROR {error}")
        return 1

    if args.target_schema or args.target_protocol:
        targets = []
        if args.target_schema:
            targets.append(f"schema {args.target_schema}")
        if args.target_protocol:
            targets.append(f"protocol {args.target_protocol}")
        print(f"Project memory target {' / '.join(targets)} preflight passed (read-only)")
    elif args.migration:
        print("Project memory migration audit passed (read-only)")
    elif not declared_v3:
        print("Project memory check passed")
    else:
        selected_mode = "full" if args.full else "focus"
        print(f"Project memory check passed ({selected_mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
