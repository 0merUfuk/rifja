"""Build and validate the session-recovery distributables from one canonical skill directory.

Outputs (all deterministic: sorted entries, fixed timestamps, no local paths):

* ``session-recovery-skill-<version>.zip``   standalone Agent Skills package
* ``rifja-session-recovery-claude-plugin/``  Claude Code plugin + one-plugin marketplace
* ``rifja-session-recovery-codex-marketplace/``  Codex marketplace root with one plugin
* ``…-claude-plugin-<version>.zip`` / ``…-codex-marketplace-<version>.zip``
* ``SHA256SUMS`` and ``MANIFEST.json``

``check`` validates the canonical skill against the Agent Skills specification and scans the
package for private data. Nothing is published or uploaded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import stat
import sys
import unicodedata
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "packaging" / "skills" / "session-recovery"
SKILL_NAME = "session-recovery"
PLUGIN_NAME = "rifja-session-recovery"
SKILL_VERSION_RE = re.compile(r'^\s+version:\s*"([^"]+)"', re.MULTILINE)
EXCLUDED_NAMES = {"ruff.toml", ".ruff_cache", "__pycache__", ".DS_Store", ".pytest_cache"}
HOMEPAGE = "https://github.com/0merUfuk/rifja"
DESCRIPTION = (
    "Resume interrupted coding work from an evidence-grounded, size-bounded brief that separates "
    "Git facts, user instructions, agent claims and uncertainty. Reads Claude Code, Codex and "
    "Hermes history imported by the local Rifja CLI."
)
KEYWORDS = ["session-recovery", "handoff", "git", "claude-code", "codex", "rifja", "local-first"]
INVISIBLE_LETTERS = frozenset([0x115F, 0x1160, 0x3164, 0xFFA0, 0x2800])
MAX_FILE_BYTES = 256 * 1024
MAX_SKILL_LINES = 500

# Data that must never ship inside a package.
PRIVATE_PATTERNS = {
    "home path": re.compile(
        r"/(?:Users|home)/(?!alice\b|bob\b|someone\b|you\b|user\b|name\b|<)[A-Za-z0-9._-]+"
    ),
    "windows home path": re.compile(r"[A-Za-z]:\\Users\\(?!name\b|user\b)[^\\\s]+", re.IGNORECASE),
    "github token": re.compile(r"\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}"),
    "slack token": re.compile(r"\bxox[a-z]-[A-Za-z0-9-]{10,}"),
    "aws key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "google key": re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"),
    "api key": re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{20,}"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY"),
    "email": re.compile(r"\b[\w.+-]+@(?!example\.|users\.noreply\.github\.com)[\w-]+\.[\w.]+\b"),
}


def invisible_characters(text: str) -> bool:
    """True if the text hides characters: format, control (except tab/newlines), fillers."""
    for ch in text:
        if ch in "\n\r\t":
            continue
        code = ord(ch)
        if (
            unicodedata.category(ch) in ("Cf", "Cc", "Cs", "Co")
            or code in INVISIBLE_LETTERS
            or 0xFE00 <= code <= 0xFE0F  # variation selectors
            or 0xE0100 <= code <= 0xE01EF
        ):
            return True
    return False


def skill_version() -> str:
    match = SKILL_VERSION_RE.search((SKILL_DIR / "SKILL.md").read_text(encoding="utf-8"))
    if not match:
        raise SystemExit("SKILL.md metadata.version missing")
    return match.group(1)


def parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Strict parser for the flat YAML subset the Agent Skills spec uses.

    Rejects empty values, duplicate keys, nested structures other than a one-level string map
    under ``metadata``, and unquoted non-string scalars in ``metadata``.
    """
    if not text.startswith("---\n"):
        raise ValueError("SKILL.md must start with YAML frontmatter")
    head, sep, body = text[4:].partition("\n---\n")
    if not sep:
        raise ValueError("frontmatter is not closed with ---")
    data: dict[str, object] = {}
    current: dict[str, str] | None = None
    for line in head.splitlines():
        if not line.strip():
            continue
        if line.startswith((" ", "\t")):
            if current is None:
                raise ValueError(f"unexpected indentation: {line!r}")
            key, colon, value = line.strip().partition(":")
            value = value.strip()
            if not colon or not value or key.strip() in current:
                raise ValueError(f"bad metadata entry: {line!r}")
            unquoted = value[0] not in "\"'"
            if unquoted and (
                value[0] in "{[|>&*!"
                or re.fullmatch(r"(?i)true|false|yes|no|null|~|[-+]?[\d.]+(?:e[-+]?\d+)?", value)
            ):
                raise ValueError(f"metadata values must be strings (quote them): {line!r}")
            current[key.strip()] = value.strip("\"'")
            continue
        key, colon, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if not colon or not key or key in data:
            raise ValueError(f"bad or duplicate frontmatter key: {line!r}")
        if value == "":
            current = {}
            data[key] = current
        else:
            current = None
            data[key] = value.strip("\"'")
    for key, value in data.items():
        if (isinstance(value, dict) and not value) or value == "":
            raise ValueError(f"frontmatter field {key!r} is empty")
    return data, body


def skill_files(skill: Path) -> list[Path]:
    files = []
    for path in sorted(skill.rglob("*")):
        rel = path.relative_to(skill)
        if any(part in EXCLUDED_NAMES for part in rel.parts):
            continue
        if path.is_dir() and not path.is_symlink():
            continue
        files.append(path)
    return files


def validate_skill(skill: Path = SKILL_DIR) -> list[str]:
    """Return a list of violations of the Agent Skills spec and packaging policy (empty = ok)."""
    problems: list[str] = []
    skill_md = skill / "SKILL.md"
    if not skill_md.is_file():
        return ["SKILL.md missing"]
    try:
        meta, body = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [str(exc)]
    name = str(meta.get("name", ""))
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64:
        problems.append(f"invalid name: {name!r}")
    if name != skill.name:
        problems.append(f"name {name!r} must match directory {skill.name!r}")
    description = str(meta.get("description", ""))
    if not 1 <= len(description) <= 1024:
        problems.append(f"description length {len(description)} not in 1..1024")
    if "compatibility" in meta and not 1 <= len(str(meta["compatibility"])) <= 500:
        problems.append("compatibility must be 1..500 characters")
    metadata = meta.get("metadata", {})
    if not isinstance(metadata, dict) or not all(isinstance(v, str) for v in metadata.values()):
        problems.append("metadata must map strings to strings")
    allowed = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
    for key in meta:
        if key not in allowed:
            problems.append(f"non-standard frontmatter field: {key}")
    if len(body.splitlines()) > MAX_SKILL_LINES:
        problems.append("SKILL.md body exceeds 500 lines")
    for target in re.findall(r"\]\(((?!https?:|#)[^)\s]+)\)", body):
        resolved = (skill / target).resolve()
        if target.startswith("/") or skill.resolve() not in (resolved, *resolved.parents):
            problems.append(f"link leaves the skill directory: {target}")
        elif not resolved.exists():
            problems.append(f"broken relative link: {target}")
    for target in re.findall(r"`(references/[\w./-]+)`", body):
        if not (skill / target).exists():
            problems.append(f"missing referenced file: {target}")
    if not (skill / "LICENSE").is_file():
        problems.append("LICENSE missing (MIT notice must travel with the skill)")
    elif "MIT License" not in (skill / "LICENSE").read_text(encoding="utf-8"):
        problems.append("LICENSE is not the MIT text")
    for path in skill_files(skill):
        rel = path.relative_to(skill)
        if path.is_symlink():
            problems.append(f"symlink not allowed: {rel}")
            continue
        if any(part.startswith(".") for part in rel.parts):
            problems.append(f"dotfile not allowed in a skill package: {rel}")
            continue
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            problems.append(f"{rel} is {size} bytes (> {MAX_FILE_BYTES})")
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            problems.append(f"binary file not allowed: {rel}")
            continue
        for label, pattern in PRIVATE_PATTERNS.items():
            if pattern.search(text):
                problems.append(f"{rel}: contains {label}")
        if invisible_characters(text):
            problems.append(f"{rel}: contains invisible or bidirectional characters")
    script = skill / "scripts" / "recover.py"
    if not script.is_file() or not script.stat().st_mode & stat.S_IXUSR:
        problems.append("scripts/recover.py must exist and be executable")
    return problems


# ----------------------------------------------------------------------------- building


def _write_zip(target: Path, source_root: Path, files: list[Path], prefix: str) -> None:
    with zipfile.ZipFile(
        target, "w", zipfile.ZIP_STORED
    ) as archive:  # no zlib: byte-stable everywhere
        for path in sorted(files, key=lambda p: p.relative_to(source_root).as_posix()):
            rel = path.relative_to(source_root).as_posix()
            info = zipfile.ZipInfo(
                f"{prefix}/{rel}" if prefix else rel, date_time=(1980, 1, 1, 0, 0, 0)
            )
            executable = bool(path.stat().st_mode & stat.S_IXUSR)
            info.external_attr = (0o100755 if executable else 0o100644) << 16  # regular file + mode
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, path.read_bytes())


def _copy_skill(dest: Path) -> None:
    for path in skill_files(SKILL_DIR):
        target = dest / path.relative_to(SKILL_DIR)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def _json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


PLUGIN_README = """# Rifja Session Recovery ({target} plugin)

A skill that rebuilds an evidence-grounded continuation brief for the repository you are in, from
Git (observed now) and from session history that the local [Rifja](https://github.com/0merUfuk/rifja)
CLI imported from Claude Code, Codex or Hermes. It separates Git facts, user instructions, agent
claims and uncertainty, redacts secrets, withholds instruction-like text and never exceeds a size
limit.

Requires `git`, Python 3.9+ and `rifja` 0.4.2+ (`brew install 0merUfuk/rifja/rifja`, then
`rifja init`). Read-only and offline. See `skills/{skill}/references/` for the output contract,
safety model and troubleshooting.

{install}

Licensed under MIT; see LICENSE. Rifja, Python, SQLite and Git retain their own licenses.
"""

CLAUDE_INSTALL = """Install (local checkout, no publication involved):

    claude plugin validate .
    /plugin marketplace add /path/to/this/directory
    /plugin install rifja-session-recovery@rifja-session-recovery

Then ask: "recover the session for this repo" (the skill is `rifja-session-recovery:session-recovery`)."""

CODEX_INSTALL = """Install (local checkout):

    codex plugin marketplace add /path/to/this/directory
    codex plugin add rifja-session-recovery@rifja-session-recovery

Or copy `skills/session-recovery/` to `$CODEX_HOME/skills/` (or `.agents/skills/` in a repo)."""


def build(out: Path) -> dict[str, object]:
    problems = validate_skill()
    if problems:
        raise SystemExit("skill validation failed:\n- " + "\n- ".join(problems))
    version = skill_version()
    if out.exists():
        if not out.is_dir() or (any(out.iterdir()) and not (out / "MANIFEST.json").is_file()):
            raise SystemExit(
                f"refusing to delete {out}: it is not empty and not a previous build output "
                "(no MANIFEST.json). Choose an empty or new directory."
            )
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # 1. standalone skill
    standalone = out / f"{SKILL_NAME}-skill-{version}.zip"
    _write_zip(standalone, SKILL_DIR, skill_files(SKILL_DIR), SKILL_NAME)

    # 2. Claude Code plugin (+ marketplace)
    claude = out / f"{PLUGIN_NAME}-claude-plugin"
    _copy_skill(claude / "skills" / SKILL_NAME)
    shutil.copy2(ROOT / "LICENSE", claude / "LICENSE")
    shutil.copy2(ROOT / "NOTICE", claude / "NOTICE")
    _json(
        claude / ".claude-plugin" / "plugin.json",
        {
            "name": PLUGIN_NAME,
            "displayName": "Rifja Session Recovery",
            "version": version,
            "description": DESCRIPTION,
            "author": {"name": "0merUfuk"},
            "homepage": HOMEPAGE,
            "repository": HOMEPAGE,
            "license": "MIT",
            "keywords": KEYWORDS,
        },
    )
    _json(
        claude / ".claude-plugin" / "marketplace.json",
        {
            "name": PLUGIN_NAME,
            "description": DESCRIPTION,
            "owner": {"name": "0merUfuk"},
            "plugins": [
                {
                    "name": PLUGIN_NAME,
                    "source": "./",
                    "description": DESCRIPTION,
                    "version": version,
                    "category": "productivity",
                }
            ],
        },
    )
    (claude / "README.md").write_text(
        PLUGIN_README.format(target="Claude Code", skill=SKILL_NAME, install=CLAUDE_INSTALL),
        encoding="utf-8",
    )

    # 3. Codex marketplace root containing one plugin
    codex_root = out / f"{PLUGIN_NAME}-codex-marketplace"
    codex = codex_root / "plugins" / PLUGIN_NAME
    _copy_skill(codex / "skills" / SKILL_NAME)
    shutil.copy2(ROOT / "LICENSE", codex / "LICENSE")
    shutil.copy2(ROOT / "NOTICE", codex / "NOTICE")
    _json(
        codex / ".codex-plugin" / "plugin.json",
        {
            "name": PLUGIN_NAME,
            "version": version,
            "description": DESCRIPTION,
            "author": {"name": "0merUfuk", "url": "https://github.com/0merUfuk"},
            "homepage": HOMEPAGE,
            "repository": HOMEPAGE,
            "license": "MIT",
            "keywords": KEYWORDS,
            "skills": "./skills/",
            "interface": {
                "displayName": "Rifja Session Recovery",
                "shortDescription": "Resume interrupted work from a verified-vs-claimed brief",
                "longDescription": DESCRIPTION,
                "developerName": "0merUfuk",
                "category": "Productivity",
                "capabilities": ["Read"],
                "defaultPrompt": ["Use $session-recovery to resume the work in this repository."],
                "websiteURL": HOMEPAGE,
            },
        },
    )
    _json(
        codex_root / ".agents" / "plugins" / "marketplace.json",
        {
            "name": PLUGIN_NAME,
            "interface": {"displayName": "Rifja Session Recovery"},
            "plugins": [
                {
                    "name": PLUGIN_NAME,
                    "source": {"source": "local", "path": f"./plugins/{PLUGIN_NAME}"},
                    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                    "category": "Productivity",
                }
            ],
        },
    )
    (codex / "README.md").write_text(
        PLUGIN_README.format(target="Codex", skill=SKILL_NAME, install=CODEX_INSTALL),
        encoding="utf-8",
    )

    zips = []
    for folder, label in ((claude, "claude-plugin"), (codex_root, "codex-marketplace")):
        target = out / f"{PLUGIN_NAME}-{label}-{version}.zip"
        files = [p for p in sorted(folder.rglob("*")) if p.is_file()]
        _write_zip(target, folder, files, folder.name)
        zips.append(target)

    artifacts = [standalone, *zips]
    sums = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts}
    (out / "SHA256SUMS").write_text(
        "".join(f"{digest}  {name}\n" for name, digest in sorted(sums.items())), encoding="utf-8"
    )
    manifest = {
        "version": version,
        "rifja_tested": "0.4.2",
        "artifacts": sums,
        "files": {
            p.relative_to(out).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(out.rglob("*"))
            if p.is_file() and p.suffix != ".zip" and p.name not in {"SHA256SUMS", "MANIFEST.json"}
        },
    }
    _json(out / "MANIFEST.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="Validate the canonical skill")
    b = sub.add_parser("build", help="Build all distributables")
    b.add_argument("--out", type=Path, default=ROOT / "dist" / "recovery")
    args = parser.parse_args(argv)
    if args.command == "check":
        problems = validate_skill()
        for problem in problems:
            print(f"FAIL {problem}")
        print("skill ok" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0
    manifest = build(args.out)
    print(
        json.dumps({"version": manifest["version"], "artifacts": manifest["artifacts"]}, indent=2)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
