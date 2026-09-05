import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from session_visualizer.adapters import hermes_signature, iter_hermes, normalize
from session_visualizer.models import Diagnostic, Record

FIXTURES = Path(__file__).parent / "fixtures" / "providers"


def parse_fixture(provider):
    context = {}
    records, diagnostics = [], []
    for i, line in enumerate((FIXTURES / (provider + ".jsonl")).read_text().splitlines(), 1):
        result = normalize(provider, json.loads(line), context, f"line:{i}")
        records.extend(result.records)
        diagnostics.extend(result.diagnostics)
    return context, records, diagnostics


class JsonlAdapters(unittest.TestCase):
    def test_codex_fork_identity_and_inherited_prefix(self):
        context, records, diagnostics = parse_fixture("codex")
        self.assertEqual(context["session_id"], "child-task")
        self.assertEqual(context["cwd"], "/example/project")
        self.assertFalse(diagnostics)
        self.assertTrue(all(r.session_id == "child-task" for r in records))
        self.assertNotIn("Inherited", " ".join(r.text for r in records))
        self.assertEqual(
            [r.text for r in records if r.kind == "user_intent"], ["Add a bounded retry."]
        )

    def test_codex_completion_is_historical_not_verification(self):
        _, records, _ = parse_fixture("codex")
        tool = next(r for r in records if r.kind == "recorded_tool_result")
        self.assertEqual(tool.metadata["exit_status"], 0)
        self.assertEqual(tool.cwd, "/example/worktree")
        claim = next(r for r in records if "I believe" in r.text)
        self.assertEqual(claim.kind, "agent_claim")
        self.assertEqual(sum("I believe" in r.text for r in records), 1)
        self.assertNotIn("verified", tool.metadata)

    def test_codex_legacy_header_and_structured_output(self):
        ctx = {}
        header = normalize("codex", {"type": "session_meta", "payload": {"id": "legacy"}}, ctx, "1")
        self.assertEqual(header.records[0].session_id, "legacy")
        result = normalize(
            "codex",
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "x",
                    "output": [{"type": "input_text", "text": "result"}],
                },
            },
            ctx,
            "2",
        )
        self.assertEqual(result.records[0].text, "result")
        self.assertNotIn("exit_status", result.records[0].metadata)

    def test_codex_unknown_and_no_header_are_visible(self):
        self.assertEqual(
            normalize("codex", {"type": "response_item", "payload": {}}, {}, "1")
            .diagnostics[0]
            .code,
            "missing_header",
        )
        result = normalize(
            "codex", {"type": "future_event", "payload": {}}, {"session_id": "x"}, "2"
        )
        self.assertEqual(result.diagnostics[0].code, "unknown_event")

    def test_codex_opaque_agent_message(self):
        result = normalize(
            "codex",
            {
                "type": "response_item",
                "payload": {
                    "type": "agent_message",
                    "content": [{"type": "encrypted_content", "encrypted_content": "opaque"}],
                },
            },
            {"session_id": "x"},
            "3",
        )
        self.assertEqual(result.records[0].text, "")
        self.assertEqual(result.diagnostics[0].code, "opaque_content")

    def test_claude_subagent_and_tool_role(self):
        context, records, diagnostics = parse_fixture("claude")
        self.assertFalse(diagnostics)
        self.assertEqual(context["session_id"], "claude-parent/agent:review-agent")
        self.assertTrue(all(r.session_id == context["session_id"] for r in records))
        tool = next(r for r in records if r.kind == "recorded_tool_result")
        self.assertEqual(tool.actor, "tool")
        self.assertEqual(tool.text, "One retry test failed.")
        self.assertEqual(tool.metadata["exit_status"], 1)
        self.assertEqual(tool.metadata["call_id"], "tool-one")
        self.assertEqual(len([r for r in records if r.kind == "user_intent"]), 1)
        self.assertNotIn("Do not extract", " ".join(r.text for r in records))

    def test_claude_block_identity_and_unknown_content(self):
        _, records, _ = parse_fixture("claude")
        self.assertEqual(len({r.native_id for r in records}), len(records))
        result = normalize(
            "claude",
            {
                "type": "user",
                "sessionId": "x",
                "message": {"role": "user", "content": [{"type": "new_type"}]},
            },
            {},
            "1",
        )
        self.assertEqual(result.diagnostics[0].code, "unknown_content")

    def test_is_error_does_not_invent_numeric_exit(self):
        result = normalize(
            "claude",
            {
                "type": "user",
                "sessionId": "x",
                "message": {
                    "role": "user",
                    "content": [{"type": "tool_result", "is_error": True, "content": "failure"}],
                },
            },
            {},
            "1",
        )
        self.assertNotIn("exit_status", result.records[0].metadata)

    def test_untrusted_wrong_shapes_do_not_raise(self):
        values = [None, 1, [], {"type": []}, {"type": "response_item", "payload": []}]
        for value in values:
            self.assertTrue(normalize("codex", value, {}, "1").diagnostics)
        self.assertTrue(normalize("other", {}, {}, "1").diagnostics)

    def test_context_is_json_serializable(self):
        for provider in ("codex", "claude"):
            ctx, _, _ = parse_fixture(provider)
            self.assertEqual(json.loads(json.dumps(ctx)), ctx)


class HermesAdapter(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "state.db"
        self.writer = sqlite3.connect(self.path)
        self.writer.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE schema_version(version INTEGER);
            INSERT INTO schema_version VALUES(26);
            CREATE TABLE sessions(id TEXT PRIMARY KEY, started_at REAL, cwd TEXT, parent_session_id TEXT, git_branch TEXT, git_repo_root TEXT, ended_at REAL, end_reason TEXT);
            CREATE TABLE messages(id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, timestamp REAL, tool_call_id TEXT, tool_calls TEXT, tool_name TEXT, active INTEGER DEFAULT 1, compacted INTEGER DEFAULT 0, _compressed_summary INTEGER DEFAULT 0, display_kind TEXT);
            INSERT INTO sessions VALUES('one', 1000, '/example/project', NULL, 'topic', '/example/project', NULL, NULL);
        """)
        self.writer.commit()

    def tearDown(self):
        self.writer.close()
        self.temp.cleanup()

    def add(self, ident, role, content, timestamp=1001, **fields):
        row = {
            "id": ident,
            "session_id": "one",
            "role": role,
            "content": content,
            "timestamp": timestamp,
            **fields,
        }
        self.writer.execute(
            "INSERT INTO messages("
            + ",".join(row)
            + ") VALUES("
            + ",".join("?" for _ in row)
            + ")",
            list(row.values()),
        )
        self.writer.commit()

    def records(self):
        return [x for x in iter_hermes(self.path) if isinstance(x, Record)]

    def test_signature_and_uncheckpointed_wal_are_read(self):
        self.add(1, "user", "Persisted in WAL")
        before = self.writer.execute("PRAGMA data_version").fetchone()[0]
        paths = [self.path, Path(str(self.path) + "-wal")]
        hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
        sig = hermes_signature(self.path)
        self.assertEqual(sig["schema_version"], 26)
        self.assertIsNotNone(sig["wal"])
        self.assertEqual(self.records()[0].text, "Persisted in WAL")
        self.assertEqual(self.writer.execute("PRAGMA data_version").fetchone()[0], before)
        self.assertEqual([hashlib.sha256(p.read_bytes()).hexdigest() for p in paths], hashes)

    def test_read_snapshot_is_consistent_during_concurrent_append(self):
        self.add(1, "user", "first")
        self.add(2, "assistant", "second")
        reader = iter_hermes(self.path)
        first = next(reader)
        self.add(3, "user", "third")
        records = [first, *reader]
        self.assertEqual([r.native_id for r in records], ["1", "2"])
        self.assertEqual(len(self.records()), 3)

    def test_timestamp_regression_preserves_id_order(self):
        self.add(1, "assistant", "later timestamp", timestamp=3000)
        self.add(2, "tool", "earlier timestamp", timestamp=2000)
        self.assertEqual([r.native_id for r in self.records()], ["1", "2"])
        self.assertTrue(self.records()[0].timestamp.endswith("Z"))

    def test_rewind_excluded_compacted_retained_copies_deduped(self):
        self.add(1, "user", "compacted", active=0, compacted=1)
        self.add(2, "assistant", "rewound", active=0, compacted=0)
        self.add(3, "user", "compacted", active=1, compacted=0)
        self.add(4, "assistant", "old retained", active=0, compacted=1)
        self.assertEqual([r.native_id for r in self.records()], ["3", "4"])

    def test_distinct_tool_calls_do_not_collapse(self):
        self.add(1, "tool", "same", tool_call_id="a")
        self.add(2, "tool", "same", tool_call_id="b")
        self.assertEqual(len(self.records()), 2)

    def test_content_codec_and_json_looking_plain_text(self):
        self.add(1, "user", '\x00json:[{"type":"text","text":"structured"}]')
        self.add(2, "user", '[{"type":"text","text":"literal"}]')
        rows = self.records()
        self.assertEqual(rows[0].text, "structured")
        self.assertEqual(rows[1].text, '[{"type":"text","text":"literal"}]')

    def test_tool_call_and_observed_metadata(self):
        calls = [
            {
                "id": "call-one",
                "type": "function",
                "function": {"name": "terminal", "arguments": '{"command":"python -m unittest"}'},
            }
        ]
        self.add(1, "assistant", "Run check", tool_calls=json.dumps(calls))
        self.add(
            2,
            "tool",
            '{"exit_code":0,"output":"OK"}',
            tool_call_id="call-one",
            tool_name="terminal",
        )
        rows = self.records()
        self.assertEqual(
            [r.kind for r in rows], ["agent_claim", "agent_proposal", "recorded_tool_result"]
        )
        self.assertEqual(rows[-1].metadata["exit_status"], 0)
        self.assertEqual(rows[-1].cwd, "/example/project")
        self.assertNotIn("dirty", rows[-1].metadata)

    def test_summary_carrier_is_not_fresh_intent(self):
        self.add(1, "user", "Context summary", _compressed_summary=1)
        results = list(iter_hermes(self.path))
        self.assertTrue(
            any(isinstance(r, Diagnostic) and r.code == "compaction_projection" for r in results)
        )
        self.assertEqual([r.kind for r in results if isinstance(r, Record)], ["metadata"])

    def test_malformed_tool_calls_and_timestamp_are_diagnostics(self):
        self.add(1, "assistant", "message", timestamp="bad", tool_calls="{")
        codes = [r.code for r in iter_hermes(self.path) if isinstance(r, Diagnostic)]
        self.assertEqual(codes, ["invalid_timestamp", "invalid_tool_calls"])

    def test_after_id_and_wrong_schema(self):
        self.add(1, "user", "first")
        self.add(2, "assistant", "second")
        self.assertEqual([r.native_id for r in iter_hermes(self.path, after_id=1)], ["2"])
        other = Path(self.temp.name) / "unrelated.db"
        sqlite3.connect(other).close()
        self.assertEqual(next(iter(iter_hermes(other))).code, "unknown_format")

    def test_missing_store_is_not_created(self):
        missing = Path(self.temp.name) / "missing.db"
        self.assertEqual(next(iter(iter_hermes(missing))).code, "unreadable_source")
        self.assertFalse(missing.exists())

    def test_large_multibyte_content_skips_without_losing_next_row(self):
        self.add(1, "user", "界" * 400_000)
        self.add(2, "assistant", "still readable")
        result = list(iter_hermes(self.path))
        self.assertEqual(result[0].code, "oversized_record")
        self.assertEqual(result[1].text, "still readable")

    def test_older_schema_without_optional_fields(self):
        older = Path(self.temp.name) / "older.db"
        conn = sqlite3.connect(older)
        conn.executescript("""
            CREATE TABLE sessions(id TEXT PRIMARY KEY, started_at REAL);
            CREATE TABLE messages(id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, timestamp REAL);
            INSERT INTO sessions VALUES('old',1000);
            INSERT INTO messages VALUES(1,'old','user','plain message',1001);
        """)
        conn.close()
        self.assertIsNone(hermes_signature(older)["schema_version"])
        row = next(iter(iter_hermes(older)))
        self.assertEqual(row.text, "plain message")
        self.assertIsNone(row.cwd)


if __name__ == "__main__":
    unittest.main()
