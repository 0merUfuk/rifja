"""Audit explicitly selected source, Git history and local build archives.

This bounded scanner is an additional release check, not perfect secret detection.
It reports rule names and file names, never matching sensitive content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

ROOTS = ("src", "tests", "docs", "tools", ".github")
FILES = (".gitignore", "README.md", "NOTICE", "pyproject.toml", "uv.lock")
FORBIDDEN = {
    ".local",
    ".venv",
    ".git",
    "__pycache__",
    ".DS_Store",
    ".env",
    "AGENTS.md",
    "FOUNDATIONS.md",
}
PATTERNS = {
    "personal_home_path": re.compile(rb"/(?:Users|home)/[A-Za-z0-9_.-]+/"),
    "private_attachment": re.compile(
        rb"(?:pasted-text-[0-9]+\.txt|\.codex/attachments/[a-f0-9-]{16,})"
    ),
    "private_key_body": re.compile(
        rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s+[A-Za-z0-9+/=]{32}"
    ),
    "credential_token": re.compile(
        rb"\b(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AKIA[A-Z0-9]{16}|sk-(?:proj-)?[A-Za-z0-9_-]{32,})"
    ),
    "private_owner": re.compile(re.escape(Path.home().name.encode()), re.IGNORECASE)
    if len(Path.home().name) > 5
    else re.compile(rb"(?!)"),
}


def digest_files(files: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name, content in sorted(files.items()):
        digest.update(name.encode() + b"\0" + content)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    findings: list[dict] = []
    synthetic_matches: list[dict] = []

    def inspect(name: str, content: bytes, scope: str) -> None:
        parts = PurePosixPath(name).parts
        if any(p in FORBIDDEN for p in parts) or ".." in parts or name.startswith("/"):
            findings.append({"scope": scope, "file": name, "rule": "unintended_path"})
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(content):
                if (
                    label == "credential_token"
                    and name.endswith("tests/test_resilience.py")
                    and match.group() == b"ghp_" + b"SYNTHETICTOKENTHATNEVEREXISTED1234"
                ):
                    synthetic_matches.append(
                        {
                            "scope": scope,
                            "file": name,
                            "rule": "explicitly_synthetic_redaction_fixture",
                        }
                    )
                else:
                    findings.append({"scope": scope, "file": name, "rule": label})

    source: dict[str, bytes] = {}
    candidates = [root / name for name in FILES]
    for directory in ROOTS:
        candidates.extend((root / directory).rglob("*"))
    for path in sorted(candidates):
        relative = path.relative_to(root).as_posix()
        if "__pycache__" in path.parts:
            continue
        if path.is_symlink():
            findings.append({"scope": "source", "file": relative, "rule": "symlink"})
        elif path.is_file():
            source[relative] = path.read_bytes()
            inspect(relative, source[relative], "source")

    def git(*argv: str) -> bytes:
        return subprocess.check_output(["git", *argv], cwd=root, timeout=15)

    tracked = git("ls-files", "-z").decode().split("\0")
    for name in filter(None, tracked):
        inspect(name, git("show", ":" + name), "git_index")
        if name not in source:
            findings.append(
                {"scope": "git_index", "file": name, "rule": "outside_release_allowlist"}
            )
    commits = git("rev-list", "--all", "--max-count=21").decode().splitlines()
    if len(commits) > 20:
        findings.append(
            {"scope": "history", "rule": "history_exceeds_fresh_repository_audit_bound"}
        )
    history_files = 0
    for commit in commits:
        inspect("commit-metadata", git("show", "-s", "--format=fuller", commit), "history")
        for name in filter(None, git("ls-tree", "-rz", "--name-only", commit).decode().split("\0")):
            inspect(name, git("show", commit + ":" + name), "history")
            history_files += 1

    archives = []
    for path in sorted((root / "dist").glob("*")):
        if path.suffix == ".whl":
            with zipfile.ZipFile(path) as archive:
                members = {
                    info.filename: archive.read(info)
                    for info in archive.infolist()
                    if not info.is_dir()
                }
                for info in archive.infolist():
                    if (info.external_attr >> 16) & 0o170000 == 0o120000:
                        findings.append(
                            {"scope": path.name, "file": info.filename, "rule": "archive_symlink"}
                        )
            for name, content in members.items():
                inspect(name, content, path.name)
                if name.startswith("session_visualizer/"):
                    if source.get("src/" + name) != content:
                        findings.append(
                            {"scope": path.name, "file": name, "rule": "wheel_source_mismatch"}
                        )
                elif ".dist-info/" not in name:
                    findings.append(
                        {"scope": path.name, "file": name, "rule": "unexpected_wheel_member"}
                    )
            metadata = next(
                content for name, content in members.items() if name.endswith("/METADATA")
            )
            if b"Requires-Dist:" in metadata or b"Requires-Python: >=3.14" not in metadata:
                findings.append({"scope": path.name, "rule": "unexpected_runtime_metadata"})
            if not any(name.endswith("/licenses/NOTICE") for name in members):
                findings.append({"scope": path.name, "rule": "missing_private_use_notice"})
        elif path.name.endswith(".tar.gz"):
            members = {}
            with tarfile.open(path) as archive:
                for info in archive.getmembers():
                    if info.isdir():
                        continue
                    if not info.isfile():
                        findings.append(
                            {"scope": path.name, "file": info.name, "rule": "archive_nonregular"}
                        )
                        continue
                    stream = archive.extractfile(info)
                    assert stream is not None
                    members[info.name] = stream.read()
                    inspect(info.name, members[info.name], path.name)
                    relative = info.name.partition("/")[2]
                    if relative != "PKG-INFO" and source.get(relative) != members[info.name]:
                        findings.append(
                            {"scope": path.name, "file": info.name, "rule": "sdist_source_mismatch"}
                        )
        else:
            continue
        archives.append(
            {
                "file": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size,
                "members": len(members),
            }
        )
    runtime = {
        Path(name).name: content
        for name, content in source.items()
        if name.startswith("src/session_visualizer/") and name.endswith(".py")
    }
    runtime_digest = hashlib.sha256()
    for name, content in sorted(runtime.items()):
        runtime_digest.update(name.encode())
        runtime_digest.update(content)
    report = {
        "status": "passed" if not findings else "failed",
        "findings": findings,
        "reviewed_synthetic_matches": synthetic_matches,
        "source_files": len(source),
        "source_fingerprint": digest_files(source),
        "runtime_fingerprint": runtime_digest.hexdigest(),
        "tracked_files": len(list(filter(None, tracked))),
        "history_commits": len(commits),
        "history_files": history_files,
        "archives": archives,
        "file_sha256": {
            name: hashlib.sha256(content).hexdigest() for name, content in sorted(source.items())
        },
        "limitations": "Bounded pattern and allowlist audit; synthetic fixtures reviewed separately; not perfect secret or PII detection.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "status",
                    "source_files",
                    "tracked_files",
                    "history_commits",
                    "runtime_fingerprint",
                    "archives",
                    "findings",
                )
            },
            indent=2,
        )
    )
    raise SystemExit(0 if not findings else 1)


if __name__ == "__main__":
    main()
