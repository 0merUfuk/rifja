"""Small shared contracts. Adapters and collectors do not write application state."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Record:
    provider: str
    session_id: str
    native_id: str
    actor: str
    kind: str
    text: str
    timestamp: str | None = None
    cwd: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Diagnostic:
    code: str
    message: str
    locator: str | None = None


@dataclass
class ParseResult:
    records: list[Record] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)


@dataclass
class GitSnapshot:
    path: str
    common_dir: str | None
    git_dir: str | None
    common_identity: str | None
    worktree_identity: str | None
    branch: str | None
    head: str | None
    status: list[dict[str, str]]
    commits: list[dict[str, str]]
    worktrees: list[dict[str, str]]
    observed_at: str
    available: bool = True
    diagnostics: list[str] = field(default_factory=list)


@dataclass
class Candidate:
    kind: str
    text: str
    status: str
    category: str
    target: str | None = None
    rationale: str | None = None
    priority: str | None = None
    dependencies: list[str] = field(default_factory=list)
    method: str = "explicit-v1"
