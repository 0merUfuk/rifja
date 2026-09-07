import json
import subprocess

from rifja.app import App
from rifja.ingest import Ingestor
from rifja.render import bounded_export, resume_markdown
from rifja.store import Store


def test_moved_repository_preserves_previously_observed_event_identity(tmp_path):
    original = tmp_path / "original"
    subprocess.run(["git", "init", "-q", str(original)], check=True)
    source = tmp_path / "session.jsonl"
    source.write_text(
        json.dumps(
            {
                "type": "user",
                "sessionId": "moved-session",
                "uuid": "moved-message",
                "timestamp": "2026-09-05T00:00:00Z",
                "cwd": str(original),
                "message": {"role": "user", "content": "NEXT: Inspect the moved project."},
            }
        )
        + "\n"
    )
    with Store(tmp_path / "state") as store:
        app = App(store)
        pid = app.register(original)["project"]["id"]
        app.source_add("claude", source)
        Ingestor(store).refresh()
        before = store.rows("SELECT project_id,worktree_id FROM records WHERE text!=''")[0]
        moved = tmp_path / "moved"
        original.rename(moved)
        assert app.register(moved)["project"]["id"] == pid
        after = store.rows("SELECT project_id,worktree_id FROM records WHERE text!=''")[0]
        assert before == after
        resume = app.resume(pid)
        assert resume["next_actions"] and resume["worktrees"][0]["path"] == str(moved)


def test_authoritative_local_memory_and_objective_in_context_exports(tmp_path):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    with Store(tmp_path / "state") as store:
        app = App(store)
        pid = app.register(repo)["project"]["id"]
        memory = app.memory_add("fact", "The support fixture is stored locally.", scope=pid)
        principle = app.memory_add("principle", "Keep evidence references.")
        app.memory_update(
            principle["id"],
            exceptions="Except excluded credentials.",
            conflicts="Private source references may not be shareable.",
        )
        data = app.resume(pid)
        assert "Except excluded credentials." in resume_markdown(data)
        for format in ("json", "markdown"):
            output = bounded_export(data, format)
            assert memory["text"] in output and memory["id"] in output
            assert "Keep evidence references." in output
            assert "Except excluded credentials." in output
            assert "Private source references may not be shareable." in output
            assert len(output) < 24000


def test_new_scope_and_missing_roots_cannot_reuse_passed_coverage(tmp_path):
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    first.write_text("")
    second.write_text("")
    with Store(tmp_path / "state") as store:
        app = App(store)
        app.source_add("claude", first)
        assert Ingestor(store).refresh()["status"] == "passed"
        assert app.coverage()["status"] == "passed"
        app.source_add("claude", second)
        assert app.coverage()["status"] == "refresh_required"
        assert app.coverage()["source_total"] == 1
        assert Ingestor(store).refresh()["status"] == "passed"
        second.unlink()
        assert app.coverage()["status"] == "partial"
