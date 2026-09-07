"""Input limits and best-effort redaction, applied before durable storage."""

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

MAX_RECORD_BYTES = 1024 * 1024
MAX_EXCERPT = 4096
MAX_DEPTH = 40
GENERATED = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".cache"}
SENSITIVE = {
    ".ssh",
    ".aws",
    ".gnupg",
    "credentials",
    "auth.json",
    "credentials.json",
    "secrets.json",
}
SECRET_PATTERNS = [
    re.compile(r"(?i)\b(?:sk-(?:proj-)?|gh[pousr]_|github_pat_|xox[baprs]-)[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"(?is)-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)"),
    re.compile(
        r"(?i)(\b(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|password|secret|authorization)\b[\"']?\s*[:=]\s*[\"']?)(?:Bearer\s+)?[^\s\"',;}]{4,}"
    ),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*"),
    re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@"),
]
ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
CONTROLS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")


def clean_text(value: str, limit: int = MAX_EXCERPT) -> str:
    text = ANSI.sub("", value)
    text = CONTROLS.sub("", text)
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    if len(text) > limit:
        return text[: max(0, limit - 14)] + " …[truncated]"
    return text


def clean(value: Any, depth: int = 0) -> Any:
    if depth > MAX_DEPTH:
        return "[depth limit]"
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, dict):
        return {clean_text(str(k), 200): clean(v, depth + 1) for k, v in list(value.items())[:100]}
    if isinstance(value, (list, tuple)):
        return [clean(v, depth + 1) for v in value[:100]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return clean_text(str(value))


def parse_json(raw: bytes) -> dict[str, Any]:
    if len(raw) > MAX_RECORD_BYTES:
        raise ValueError("record_size_limit")
    # Bound JSON nesting before invoking the recursive decoder; ignore string braces.
    depth, quoted, escaped = 0, False, False
    for ch in raw:
        if quoted:
            if escaped:
                escaped = False
            elif ch == 92:
                escaped = True
            elif ch == 34:
                quoted = False
        elif ch == 34:
            quoted = True
        elif ch in (91, 123):
            depth += 1
            if depth > MAX_DEPTH:
                raise ValueError("record_depth_limit")
        elif ch in (93, 125):
            depth -= 1
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise TypeError("record_not_object")
    return value


def digest(*values: Any) -> str:
    return hashlib.sha256(
        json.dumps(values, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def private_dir(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("state_directory_must_not_be_symlink")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)


def excluded(path: Path, state: Path, exclusions: list[str]) -> bool:
    import fnmatch

    if symlink_component(path):
        return True
    resolved = path.resolve()
    if resolved == state.resolve() or state.resolve() in resolved.parents:
        return True
    if any(p in GENERATED | SENSITIVE or p.startswith(".env") for p in path.parts):
        return True
    return any(
        fnmatch.fnmatch(str(path), pattern) or fnmatch.fnmatch(path.name, pattern)
        for pattern in exclusions
    )


def within(path: Path, root: Path) -> bool:
    return path.resolve() == root.resolve() or root.resolve() in path.resolve().parents


def symlink_component(path: Path) -> bool:
    """Reject user-controlled symlink traversal, allowing macOS system aliases."""
    import sys

    allowed = {Path("/var"), Path("/tmp"), Path("/etc")} if sys.platform == "darwin" else set()
    absolute = path.expanduser().absolute()
    return any(p.is_symlink() and p not in allowed for p in (absolute, *absolute.parents))


def open_regular(path: Path) -> int:
    """Open a regular source without following user-controlled path components."""
    import stat
    import sys

    path = path.expanduser().absolute()
    parts = path.parts[1:]
    if sys.platform == "darwin" and parts and parts[0] in {"var", "tmp", "etc"}:
        parts = ("private", *parts)
    parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise ValueError("source_must_be_regular_file")
        return fd
    finally:
        os.close(parent)
