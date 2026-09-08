#!/usr/bin/env python3
"""Validate protocol 3.0 project memory and active claims (standard library only)."""

from __future__ import annotations
import argparse
import ast
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


CONTINUITY_KERNEL_PROTOCOL = "3.0"


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


V3_TASK_NAME_RE = re.compile(
    r"^T-(?:[A-Z][A-Z0-9]{1,11}-\d{3}|\d{3})-[a-z0-9]+(?:-[a-z0-9]+)*$"
)


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$", re.IGNORECASE)


SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


EXTERNAL_URI_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)


MUTABLE_IDENTITY_TOKENS = {"current", "draft", "head", "latest", "main", "master", "mutable", "working"}


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T ][^\s]+)?$")


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


def html_element_is_hidden(tag: str, attributes: dict[str, str]) -> bool:
    return (
        tag in INTRINSICALLY_HIDDEN_HTML_TAGS
        or "hidden" in attributes
        or attributes.get("aria-hidden", "").strip().lower() in {"true", "1"}
        or FORBIDDEN_HIDING_CSS_RE.search(attributes.get("style", "")) is not None
    )


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


def run_git(project_root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", str(project_root), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


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
        errors.append("project/state.yaml: unsupported schema; this distribution requires schema_version: 3")
    if str(state.get("protocol_version") or "") != CONTINUITY_KERNEL_PROTOCOL:
        errors.append('project/state.yaml: unsupported protocol; this distribution requires protocol_version: "3.0"')

    if state.get("schema_version") != 3 or str(state.get("protocol_version") or "") != CONTINUITY_KERNEL_PROTOCOL:
        return errors

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
        v3_validate_task(project_root, task_dir, location, mode, errors)

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate protocol 3.0 project memory.")
    parser.add_argument("project_root", nargs="?", default=".")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--focus", action="store_true", help="Check the recovery-focus task and its active claims (default).")
    modes.add_argument("--full", action="store_true", help="Check all active and archived protocol 3.0 tasks.")
    args = parser.parse_args()
    project_root = Path(args.project_root)
    if not project_root.is_dir():
        print(f"ERROR project root does not exist: {project_root}")
        return 2
    mode = "full" if args.full else "focus"
    errors = check_project_v3(project_root, mode)
    if errors:
        print(f"Project memory check failed with {len(errors)} error(s):")
        for error in errors:
            print(f"ERROR {error}")
        return 1
    print(f"Project memory check passed ({mode})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
