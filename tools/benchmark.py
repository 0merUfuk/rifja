"""Generate isolated synthetic native transcripts and measure the installed CLI.

No application imports, private stores, network, credentials, or dependency setup.
Outputs are confined to a new .local/benchmark-* directory. Existing data is never
removed. Full CLI subprocess wall time includes Python startup and JSON rendering.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import signal
import sqlite3
import subprocess
import sys
import time
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

PRESETS = {
    "tiny": {
        "sessions": 8,
        "records_per_session": 20,
        "repositories": 2,
        "worktrees": 1,
        "bytes": 192 * 1024,
    },
    "small": {
        "sessions": 100,
        "records_per_session": 100,
        "repositories": 20,
        "worktrees": 5,
        "bytes": 10 * 1024 * 1024,
    },
    "large": {
        "sessions": 1000,
        "records_per_session": 250,
        "repositories": 20,
        "worktrees": 5,
        "bytes": 250 * 1024 * 1024,
    },
}
BUDGETS = {
    "cold_seconds": 120,
    "unchanged_seconds": 5,
    "append_seconds": 2,
    "query_p95_seconds": 1,
    "peak_ingestion_bytes": 512 * 1024 * 1024,
}
PHRASES = [
    "The latency histogram has separate buckets for the network and the queue. ",
    "An adapter keeps the original timestamp alongside the source sequence. ",
    "A bounded buffer carries ordinary diagnostic records between components. ",
    "The retry interval uses the supplied limit and the observed response type. ",
    "This context describes a local fixture and contains no production account. ",
    "The directory identity remains distinct from the display label. ",
    "A reader obtains an immutable view of the current transaction. ",
    "The output includes a small sample of the operation history. ",
]
NAMESPACE = uuid.UUID("0d1a54cd-79bb-4c74-998d-a0c2a79d59ad")


def synthetic_uuid(label: str) -> str:
    return str(uuid.uuid5(NAMESPACE, label))


class Harness:
    def __init__(self, root: Path, cli: Path, repetitions: int, timeout: float):
        self.root, self.cli, self.repetitions, self.timeout = root, cli, repetitions, timeout
        self.root.mkdir(mode=0o700)
        for name in ("home", "state", "cwd", "evidence", "sources", "repos", "worktrees"):
            (root / name).mkdir(mode=0o700)
        installed = sorted(
            (cli.parent.parent / "lib").glob("python*/site-packages/session_visualizer")
        )
        self.code_root = (
            installed[0]
            if installed
            else Path(__file__).resolve().parents[1] / "src" / "session_visualizer"
        )
        self.code_scope = "installed_package" if installed else "checkout_editable_fallback"
        generator = Path(__file__).read_bytes()
        (root / "generator.py").write_bytes(generator)
        self.generator_sha256 = hashlib.sha256(generator).hexdigest()
        self.env = {
            "HOME": str(root / "home"),
            "PATH": str(cli.parent) + ":/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONNOUSERSITE": "1",
            "XDG_CONFIG_HOME": str(root / "home" / ".config"),
            "XDG_CACHE_HOME": str(root / "home" / ".cache"),
            "XDG_DATA_HOME": str(root / "home" / ".local" / "share"),
            "CODEX_HOME": str(root / "home" / ".codex"),
            "CLAUDE_CONFIG_DIR": str(root / "home" / ".claude"),
            "HERMES_HOME": str(root / "home" / ".hermes"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": "Benchmark Author",
            "GIT_COMMITTER_NAME": "Benchmark Author",
            "GIT_AUTHOR_EMAIL": "benchmark@example.invalid",
            "GIT_COMMITTER_EMAIL": "benchmark@example.invalid",
            "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
            "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
        }
        self.measurements: list[dict] = []
        self.sequence = 0

    def source_fingerprint(self) -> str:
        digest = hashlib.sha256()
        for path in sorted(self.code_root.glob("*.py")):
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()

    def run(self, label: str, args: list[str], *, raw: bool = False, quiet: bool = False) -> dict:
        self.sequence += 1
        stem = f"{self.sequence:03d}-{label}"
        stdout, stderr = (
            self.root / "evidence" / (stem + ".json"),
            self.root / "evidence" / (stem + ".stderr"),
        )
        command = (
            args if raw else [str(self.cli), "--home", str(self.root / "state"), "--json", *args]
        )
        fingerprint = self.source_fingerprint()
        start = time.perf_counter()
        with stdout.open("wb") as out, stderr.open("wb") as err:
            process = subprocess.Popen(
                command,
                cwd=self.root / "cwd",
                env=self.env,
                stdout=out,
                stderr=err,
                start_new_session=True,
            )
            timed_out = False
            while True:
                pid, status, usage = os.wait4(process.pid, os.WNOHANG)
                if pid:
                    break
                if time.perf_counter() - start > self.timeout:
                    os.killpg(process.pid, signal.SIGKILL)
                    _, status, usage = os.wait4(process.pid, 0)
                    timed_out = True
                    break
                time.sleep(0.002)
            process.returncode = os.waitstatus_to_exitcode(status)
        elapsed = time.perf_counter() - start
        rss = int(usage.ru_maxrss if sys.platform == "darwin" else usage.ru_maxrss * 1024)
        entry = {
            "label": label,
            "argv": args,
            "seconds": elapsed,
            "peak_rss_bytes": rss,
            "user_seconds": usage.ru_utime,
            "system_seconds": usage.ru_stime,
            "exit_code": process.returncode,
            "timed_out": timed_out,
            "checkout_fingerprint_before": fingerprint,
            "checkout_fingerprint_after": self.source_fingerprint(),
            "stdout": str(stdout.relative_to(self.root)),
            "stderr": str(stderr.relative_to(self.root)),
        }
        if not raw:
            try:
                entry["data"] = json.loads(stdout.read_text())["data"]
            except ValueError, KeyError:
                entry["data"] = None
        self.measurements.append(entry)
        (self.root / "measurements.json").write_text(json.dumps(self.measurements, indent=2) + "\n")
        if not quiet:
            print(
                json.dumps(
                    {k: entry[k] for k in ("label", "seconds", "peak_rss_bytes", "exit_code")}
                ),
                flush=True,
            )
        if process.returncode:
            print("COMMAND_FAILED " + label + " " + stderr.read_text()[:1000], flush=True)
            raise RuntimeError(f"{label} exit {process.returncode}")
        return entry

    def git(self, path: Path, *args: str) -> None:
        self.run(
            "git-build",
            [
                "git",
                "-c",
                "init.defaultBranch=main",
                "-c",
                "core.hooksPath=" + os.devnull,
                "-C",
                str(path),
                *args,
            ],
            raw=True,
            quiet=True,
        )

    def repositories(self, count: int, linked: int) -> tuple[list[Path], list[Path]]:
        repos, worktrees = [], []
        for i in range(count):
            path = self.root / "repos" / f"repo-{i:02d}"
            path.mkdir()
            self.git(path, "init", "--quiet")
            for commit in range(3):
                (path / "example.txt").write_text(f"Synthetic repository {i}; revision {commit}.\n")
                self.git(path, "add", "example.txt")
                self.git(path, "commit", "--quiet", "-m", f"Fixture revision {commit}")
            if i < linked:
                worktree = self.root / "worktrees" / f"repo-{i:02d}-topic"
                self.git(path, "worktree", "add", "--quiet", "-b", "topic", str(worktree))
                (worktree / "example.txt").write_text("Synthetic uncommitted worktree change.\n")
                worktrees.append(worktree)
            if i % 4 == 0:
                (path / "untracked.txt").write_text("A controlled untracked file.\n")
            repos.append(path)
        return repos, worktrees

    def counts(self) -> dict:
        path = self.root / "state" / "state.sqlite3"
        conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        try:
            conn.execute("PRAGMA query_only=ON")
            result = {
                name: conn.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
                for name in ("sessions", "records", "occurrences", "items", "projects", "worktrees")
            }
            result["derived_kinds"] = dict(
                conn.execute("SELECT kind,count(*) FROM items GROUP BY kind")
            )
            result["duplicate_native_records"] = conn.execute(
                "SELECT count(*) FROM (SELECT session_id,native_id,actor,kind,count(*) n FROM records GROUP BY session_id,native_id,actor,kind HAVING n>1)"
            ).fetchone()[0]
            return result
        finally:
            conn.close()


def native_record(
    provider: str, session: int, index: int, cwd: Path, *, append: bool = False
) -> tuple[dict, dict, str]:
    sid = synthetic_uuid(f"{provider}/session/{session}")
    timestamp = (
        (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=session * 1000 + index))
        .isoformat()
        .replace("+00:00", "Z")
    )
    ident = synthetic_uuid(f"{provider}/session/{session}/record/{index}")
    phrases = (
        PHRASES[(session + index) % len(PHRASES) :] + PHRASES[: (session + index) % len(PHRASES)]
    )
    prefix = f"Observation {session:04d}/{index:05d}. " + phrases[0]
    role = "user" if index % 10 in (0, 5) else "assistant"
    if index in (1, 2, 3, 6):
        role = "user"
        prefix = {
            1: f"TASK: [bench-{session}] Add a continuityanchor retry bound.\n",
            2: f"BLOCKER: [block-{session}] The fixture dependency is unavailable.\n",
            3: f"NEXT: [next-{session}] Inspect the retry observation.\n",
            6: f"DECISION: Keep the retry bound explicit for fixture {session}.\n",
        }[index]
    if append:
        role = "assistant"
        prefix = f"Additional observation {session:04d}/{index:05d}. " + phrases[0]
    if provider == "codex":
        envelope = {"timestamp": timestamp, "ordinal": index, "type": "response_item"}
        if index == 0 and not append:
            payload = {
                "id": sid,
                "session_id": sid,
                "cwd": str(cwd),
                "timestamp": timestamp,
                "cli_version": "0.153.4",
                "originator": "synthetic-benchmark",
                "model_provider": "synthetic",
                "base_instructions": {"text": ""},
            }
            envelope.update(type="session_meta", payload=payload)
            return envelope, payload["base_instructions"], "text"
        if index % 10 == 4 and not append:
            payload = {
                "type": "function_call",
                "id": ident,
                "call_id": f"call-{session}-{index}",
                "name": "terminal",
                "arguments": '{"command":"printf synthetic # "}',
            }
            envelope["payload"] = payload
            return envelope, payload, "arguments"
        if index % 10 == 9 and not append:
            payload = {
                "type": "function_call_output",
                "id": ident,
                "call_id": f"call-{session}-{index - 5}",
                "output": "",
            }
            envelope["payload"] = payload
            return envelope, payload, "output"
        part = {"type": "input_text" if role == "user" else "output_text", "text": prefix}
        envelope["payload"] = {"type": "message", "id": ident, "role": role, "content": [part]}
        return envelope, part, "text"
    envelope = {
        "type": role,
        "uuid": ident,
        "sessionId": sid,
        "cwd": str(cwd),
        "timestamp": timestamp,
        "parentUuid": synthetic_uuid(f"{provider}/session/{session}/record/{index - 1}")
        if index
        else None,
        "version": "2.1.260",
        "isSidechain": False,
        "message": {"role": role, "content": []},
    }
    if index % 10 == 4 and not append:
        part = {
            "type": "tool_use",
            "id": f"call-{session}-{index}",
            "name": "Bash",
            "input": {"command": "printf synthetic # "},
        }
        envelope["message"]["content"] = [part]
        return envelope, part["input"], "command"
    if index % 10 == 9 and not append:
        envelope["type"] = "user"
        envelope["message"]["role"] = "user"
        part = {
            "type": "tool_result",
            "tool_use_id": f"call-{session}-{index - 5}",
            "content": "",
            "is_error": False,
        }
        envelope["message"]["content"] = [part]
        return envelope, part, "content"
    part = {"type": "text", "text": prefix}
    envelope["message"]["content"] = [part]
    return envelope, part, "text"


def encode_record(
    provider: str, session: int, index: int, cwd: Path, target_bytes: int, *, append: bool = False
) -> bytes:
    row, target, field = native_record(provider, session, index, cwd, append=append)
    base = json.dumps(row, separators=(",", ":"), ensure_ascii=True)
    required = target_bytes - len(base.encode()) - 1
    if required < 0:
        raise ValueError("Requested source line too short for the native envelope")
    filler = " ".join(PHRASES[(session + index) % 8 :] + PHRASES[: (session + index) % 8]) + " "
    padding = (filler * (required // len(filler) + 1))[:required]
    if field == "arguments":
        target[field] = target[field][:-2] + padding + target[field][-2:]
    else:
        target[field] += padding
    result = (json.dumps(row, separators=(",", ":"), ensure_ascii=True) + "\n").encode()
    assert len(result) == target_bytes
    return result


def corpus(harness: Harness, spec: dict, repos: list[Path], worktrees: list[Path]) -> dict:
    total = spec["sessions"] * spec["records_per_session"]
    base, remainder = divmod(spec["bytes"], total)
    digest = hashlib.sha256()
    files, by_provider = [], Counter()
    observed = 0
    for session in range(spec["sessions"]):
        provider = "codex" if session % 2 == 0 else "claude"
        repo = repos[session % len(repos)]
        cwd = worktrees[session % len(worktrees)] if worktrees and session % 7 == 0 else repo
        sid = synthetic_uuid(f"{provider}/session/{session}")
        if provider == "codex":
            directory = (
                harness.root
                / "sources"
                / provider
                / "sessions"
                / "2026"
                / "01"
                / f"{1 + session % 28:02d}"
            )
            name = f"rollout-2026-01-{1 + session % 28:02d}T09-00-00-{sid}.jsonl"
        else:
            directory = harness.root / "sources" / provider / "projects" / ("-" + cwd.name)
            name = sid + ".jsonl"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        with path.open("wb") as stream:
            for index in range(spec["records_per_session"]):
                size = base + int(observed < remainder)
                line = encode_record(provider, session, index, cwd, size)
                stream.write(line)
                digest.update(line)
                observed += 1
                by_provider[provider] += 1
        files.append({"provider": provider, "path": str(path), "session": session, "cwd": str(cwd)})
    result = {
        **spec,
        "source_records": total,
        "expected_normalized_records": total,
        "actual_bytes": sum(Path(f["path"]).stat().st_size for f in files),
        "provider_records": dict(by_provider),
        "source_sha256": digest.hexdigest(),
        "files": files,
        "native_formats": [
            "Codex observed writer 0.153.4 rollout envelope",
            "Claude Code observed transcript writer 2.1.260 message envelope; separately inspected PATH CLI 2.1.63",
        ],
        "generation": "Deterministic fields and ASCII sentence rotation; paths depend on chosen output directory.",
    }
    (harness.root / "corpus.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def p95(values: list[float]) -> float:
    return sorted(values)[math.ceil(len(values) * 0.95) - 1]


def run_benchmark(harness: Harness, preset: str) -> dict:
    spec = PRESETS[preset]
    start = time.perf_counter()
    repos, worktrees = harness.repositories(spec["repositories"], spec["worktrees"])
    dataset = corpus(harness, spec, repos, worktrees)
    generation_seconds = time.perf_counter() - start
    print(
        json.dumps(
            {
                "stage": "corpus_ready",
                "preset": preset,
                "bytes": dataset["actual_bytes"],
                "records": dataset["source_records"],
                "seconds": generation_seconds,
            }
        ),
        flush=True,
    )
    version = harness.run("version", [str(harness.cli), "--version"], raw=True)
    python = harness.run("python-version", [str(harness.cli.parent / "python"), "-V"], raw=True)
    git = harness.run("git-version", ["git", "--version"], raw=True)
    startup = [
        harness.run("startup", [str(harness.cli), "--version"], raw=True, quiet=True)["seconds"]
        for _ in range(harness.repetitions)
    ]
    harness.run("setup", ["setup", "--timezone", "UTC"])
    registration_start = time.perf_counter()
    for i, repo in enumerate(repos):
        harness.run(
            f"register-{i:02d}",
            ["project", "add", str(repo), "--name", f"bench-{i:02d}"],
            quiet=True,
        )
    registration_seconds = time.perf_counter() - registration_start
    for provider in ("codex", "claude"):
        harness.run(
            "source-" + provider,
            ["source", "add", provider, str(harness.root / "sources" / provider)],
        )
    cold = harness.run("cold-refresh", ["refresh"])
    cold_counts = harness.counts()
    assert cold["data"]["parsed_records"] == dataset["source_records"], "cold parsed count"
    assert cold_counts["records"] == dataset["expected_normalized_records"], (
        "normalized record count"
    )
    assert cold_counts["sessions"] == spec["sessions"], "session count"
    assert cold_counts["projects"] == spec["repositories"], "repository count"
    assert cold_counts["worktrees"] == spec["repositories"] + spec["worktrees"], (
        "linked worktree count"
    )
    assert cold_counts["duplicate_native_records"] == 0, "duplicate initial records"
    unchanged = [harness.run("unchanged-refresh", ["refresh"]) for _ in range(harness.repetitions)]
    assert all(
        row["data"]["parsed_records"] == 0 and row["data"]["inserted_records"] == 0
        for row in unchanged
    ), "unchanged refresh reparsed"
    assert harness.counts() == cold_counts, "unchanged refresh altered record counts"
    append_count = 100
    append_file = dataset["files"][0]
    with Path(append_file["path"]).open("ab") as output:
        output.writelines(
            encode_record(
                append_file["provider"],
                append_file["session"],
                spec["records_per_session"] + offset,
                Path(append_file["cwd"]),
                1049,
                append=True,
            )
            for offset in range(append_count)
        )
    appended = harness.run("append-refresh", ["refresh"])
    after = harness.counts()
    assert appended["data"]["parsed_records"] == append_count, "append parsed more than 100"
    assert appended["data"]["inserted_records"] == append_count, "append inserted count"
    assert after["records"] == cold_counts["records"] + append_count, "append database count"
    assert after["occurrences"] == after["records"] and after["duplicate_native_records"] == 0, (
        "duplicate appended records"
    )
    queries = {
        "search-sparse": ["search", "continuityanchor", "--project", "bench-00", "--limit", "20"],
        "search-common": ["search", "latency", "--limit", "20"],
        "tasks": ["tasks", "--project", "bench-00", "--limit", "50"],
        "decisions": ["decisions", "--project", "bench-00", "--limit", "50"],
    }
    query_stats = {}
    for label, args in queries.items():
        warm = harness.run(label + "-warmup", args, quiet=True)
        if label in {"search-sparse", "search-common"}:
            assert warm["data"].get("matches"), "search returned no useful data"
        if label == "tasks":
            assert any(
                x["kind"] in {"task", "next_action", "blocker"} for x in warm["data"]["items"]
            ), "tasks returned no continuity data"
        if label == "decisions":
            assert warm["data"]["items"], "decisions returned no useful data"
        values = [
            harness.run(label, args, quiet=True)["seconds"] for _ in range(harness.repetitions)
        ]
        query_stats[label] = {
            "seconds": values,
            "p95_seconds": p95(values),
            "budget_pass": p95(values) <= BUDGETS["query_p95_seconds"],
        }
        print(json.dumps({"query": label, **query_stats[label]}), flush=True)
    git_values = [
        harness.run(
            "git-status",
            [
                "git",
                "--no-optional-locks",
                "-C",
                str(worktrees[0]),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ],
            raw=True,
            quiet=True,
        )["seconds"]
        for _ in range(harness.repetitions)
    ]
    observe = [
        harness.run("project-observe", ["project", "show", "bench-00", "--observe"], quiet=True)[
            "seconds"
        ]
        for _ in range(harness.repetitions)
    ]
    resume = []
    for _ in range(harness.repetitions):
        measured = harness.run("complete-resume", ["resume", "bench-00"], quiet=True)
        assert measured["data"]["next_actions"], "resume returned no actions"
        assert any(x["kind"] == "blocker" for x in measured["data"]["unfinished"]), (
            "resume omitted controlled blockers"
        )
        resume.append(measured["seconds"])
    ingestion_peak = max(
        cold["peak_rss_bytes"],
        appended["peak_rss_bytes"],
        *(r["peak_rss_bytes"] for r in unchanged),
    )
    gates = {
        "cold": cold["seconds"] <= BUDGETS["cold_seconds"],
        "unchanged": max(r["seconds"] for r in unchanged) <= BUDGETS["unchanged_seconds"],
        "append": appended["seconds"] <= BUDGETS["append_seconds"],
        "query_p95": all(q["budget_pass"] for q in query_stats.values()),
        "peak_ingestion": ingestion_peak <= BUDGETS["peak_ingestion_bytes"],
        "unchanged_parsed_zero": True,
        "append_only_100": True,
        "no_duplicates": True,
    }
    result = {
        "preset": preset,
        "status": "passed" if all(gates.values()) else "failed",
        "budgets": BUDGETS,
        "gates": gates,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "macos": platform.mac_ver()[0],
            "logical_cpus": os.cpu_count(),
            "python": (harness.root / python["stdout"]).read_text().strip(),
            "git": (harness.root / git["stdout"]).read_text().strip(),
            "cli": (harness.root / version["stdout"]).read_text().strip(),
        },
        "dataset": {k: v for k, v in dataset.items() if k != "files"},
        "repetitions": harness.repetitions,
        "generation_seconds": generation_seconds,
        "registration_seconds": registration_seconds,
        "startup_seconds": startup,
        "startup_p95_seconds": p95(startup),
        "cold_seconds": cold["seconds"],
        "unchanged_seconds": [r["seconds"] for r in unchanged],
        "append_seconds": appended["seconds"],
        "peak_ingestion_bytes": ingestion_peak,
        "cold_counts": cold_counts,
        "after_append_counts": after,
        "queries": query_stats,
        "git_status_seconds": git_values,
        "git_status_p95_seconds": p95(git_values),
        "project_observe_seconds": observe,
        "project_observe_p95_seconds": p95(observe),
        "complete_resume_seconds": resume,
        "complete_resume_p95_seconds": p95(resume),
        "measurement": "Wall time via perf_counter; child peak RSS via wait4. Darwin ru_maxrss bytes; Linux KiB converted to bytes. Includes CLI startup and JSON rendering. OS filesystem caches were not flushed; cold means empty application index.",
        "checkout_fingerprints": sorted(
            {
                r["checkout_fingerprint_before"]
                for r in harness.measurements
                if r["label"] != "git-build"
            }
        ),
        "source_changed_during_commands": [
            r["label"]
            for r in harness.measurements
            if r["checkout_fingerprint_before"] != r["checkout_fingerprint_after"]
        ],
        "fingerprint_scope": harness.code_scope,
        "fingerprint_source": str(harness.code_root),
        "generator_sha256": harness.generator_sha256,
    }
    (harness.root / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", choices=PRESETS, default="tiny")
    parser.add_argument(
        "--output", type=Path, required=True, help="New .local/benchmark-* directory"
    )
    parser.add_argument("--cli", type=Path)
    parser.add_argument("--repetitions", type=int, default=7)
    parser.add_argument("--command-timeout", type=float, default=600)
    args = parser.parse_args()
    workspace = Path(__file__).resolve().parents[1]
    root = args.output.expanduser().resolve()
    local = workspace / ".local"
    if root.parent != local or not root.name.startswith("benchmark-"):
        parser.error("output must be a direct .local/benchmark-* directory in this workspace")
    if root.exists():
        parser.error("output already exists; choose a fresh directory")
    if args.repetitions < 3:
        parser.error("at least three measured repetitions are required")
    cli = (args.cli or workspace / ".venv" / "bin" / "session-visualizer").absolute()
    if not cli.is_file():
        parser.error("installed CLI is missing")
    local.mkdir(exist_ok=True)
    harness = Harness(root, cli, args.repetitions, args.command_timeout)
    try:
        result = run_benchmark(harness, args.preset)
    except (AssertionError, KeyError, OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        failure = {
            "status": "failed",
            "phase": harness.measurements[-1]["label"] if harness.measurements else "generation",
            "error": str(exc),
        }
        (root / "failure.json").write_text(json.dumps(failure, indent=2) + "\n")
        print(json.dumps(failure), flush=True)
        return 1
    print(
        json.dumps(
            {
                "status": result["status"],
                "gates": result["gates"],
                "result": str(root / "result.json"),
            }
        ),
        flush=True,
    )
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
