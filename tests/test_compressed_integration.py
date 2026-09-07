import json
import subprocess
from compression import zstd

from rifja.app import App
from rifja.ingest import Ingestor
from rifja.store import Store


def test_compressed_rollout_complete_connector_and_archived_copy(tmp_path):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    data = [
        {
            "type": "session_meta",
            "timestamp": "2026-09-05T10:00:00Z",
            "payload": {"id": "compressed-fixture", "cwd": str(repo)},
        },
        {
            "type": "response_item",
            "timestamp": "2026-09-05T10:01:00Z",
            "payload": {
                "id": "action",
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "NEXT: Inspect the local parser fixture."}
                ],
            },
        },
    ]
    raw = b"".join(json.dumps(x).encode() + b"\n" for x in data)
    source = tmp_path / "rollout.jsonl.zst"
    source.write_bytes(zstd.compress(raw))
    with Store(tmp_path / "state") as store:
        app = App(store)
        project = app.register(repo)["project"]["id"]
        app.source_add("codex", source)
        result = Ingestor(store).refresh()
        assert result["status"] == "passed" and result["inserted_records"] == 2
        assert app.resume(project)["next_actions"][0]["text"] == "Inspect the local parser fixture."
        assert Ingestor(store).refresh()["parsed_records"] == 0
        copy = tmp_path / "rollout.jsonl"
        copy.write_bytes(raw)
        app.source_add("codex", copy)
        assert Ingestor(store).refresh()["inserted_records"] == 0
        action = app.items(project)["items"][0]
        assert len(action["evidence"]["locations"]) == 2
        source.write_bytes(source.read_bytes() + b"corrupt frame")
        assert Ingestor(store).refresh()["status"] == "partial"
        assert "zstd_decompression_error" in json.dumps(app.coverage())
