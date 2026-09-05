"""Synthetic public-CLI regressions disclosed after independent rc3 challenges.

No private oracle, project document, transcript, or installed-source expectation
is available to the application through these fixtures.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest
from test_cli import Console


@pytest.fixture
def independent_cli(tmp_path):
    cli = Console(tmp_path)
    cli.data("setup", "--timezone", "UTC")
    cli.project_path = cli.repo("Independent notebook")
    (cli.project_path / "README.md").write_text(
        "# Pebble Ledger\n\nAn offline report of workstation build activity.\n"
    )
    cli.data("project", "add", str(cli.project_path), "--name", "notebook")
    return cli


def register_documents(cli):
    cli.data("document", "add", "notebook", "--include", "*.md")


def register_events(cli, events, name="independent", cwd=None):
    source = cli.source_dir / (name + ".jsonl")
    cli.source(
        source,
        cwd or cli.project_path,
        name,
        [(f"message-{n}", actor, text) for n, (actor, text) in enumerate(events)],
    )
    cli.data("source", "add", "codex", str(source))
    return source


def active_text(resume):
    return "\n".join(item["text"] for item in resume["next_actions"]).casefold()


def exported(cli, format):
    return cli.run(
        "export", "notebook", "--format", format, "--max-chars", "8000", json_output=False
    ).stdout


@pytest.mark.parametrize(
    ("document", "revision", "reported_result"),
    [
        (
            (
                "# Delivery notes\n\n## Earlier validation\n"
                "On revision a17, all unit checks passed.\n\n## Before handoff\n"
                "Browser rendering remains unverified.\n"
            ),
            "a17",
            "all unit checks passed",
        ),
        (
            (
                "# Current state\n\nNo open release checks remain in this documented snapshot.\n\n"
                "## Historical work\n"
                "The operator reported the checksum review complete on revision b23.\n"
            ),
            "b23",
            "checksum review complete",
        ),
        (
            (
                "# Current report\n\nBrowser verification is no longer pending. "
                "The owner reported it completed on revision c42. "
                "This document is not a fresh test result for a later revision.\n"
            ),
            "c42",
            "owner reported it completed",
        ),
    ],
)
def test_documented_historical_results_survive_exports_with_their_revision(
    independent_cli, document, revision, reported_result
):
    cli = independent_cli
    (cli.project_path / "STATUS.md").write_text(document)
    register_documents(cli)
    register_events(cli, [("user", "Please repeat the previous explanation.")])
    cli.data("refresh")
    for format in ("markdown", "json"):
        result = exported(cli, format)
        # The phrase cannot accidentally match an opaque identifier containing c42.
        assert f"revision {revision}" in result
        assert reported_result in result
        if format == "json":
            data = json.loads(result)
            statements = [
                item
                for item in data["context"] + data["items"]
                if f"revision {revision}" in item.get("text", "")
            ]
            assert statements
            assert all(item.get("status") != "verified" for item in statements)
            assert all("documented" in item.get("category", "") for item in statements)


def test_greeting_and_repeat_request_are_not_latest_work_instructions(independent_cli):
    cli = independent_cli
    register_documents(cli)
    register_events(
        cli,
        [
            ("user", "Hello!"),
            ("user", "Merhaba!"),
            ("user", "Can you repeat that last explanation?"),
            ("assistant", "We could add collaboration later."),
        ],
    )
    cli.data("refresh")
    resume = cli.data("resume", "notebook")
    assert resume["next_actions"] == []
    assert resume["latest_user_instruction"] is None
    for format in ("markdown", "json"):
        result = exported(cli, format)
        if format == "json":
            assert not any(
                item["kind"] == "latest_user_instruction" for item in json.loads(result)["context"]
            )
        else:
            assert "**latest user instruction**" not in result


def test_rebuilt_result_retains_commit_scope_despite_incidental_only_clause(independent_cli):
    cli = independent_cli
    (cli.project_path / "STATUS.md").write_text(
        "# Release evidence\n\n"
        "The command-line binary and four target packages were rebuilt from clean commit d41ac79. "
        "Later edits affect only this record and the temporary diagnostic helper; "
        "production assets were unchanged.\n\n"
        "## Publication gate\n"
        "Do not publish any packages without explicit owner approval.\n"
    )
    register_documents(cli)
    cli.data("refresh")
    for format in ("markdown", "json"):
        result = exported(cli, format)
        assert "rebuilt from clean commit d41ac79" in result
        assert "owner approval" in result
        if format == "json":
            data = json.loads(result)
            claims = [
                item
                for item in data["context"] + data["items"]
                if "commit d41ac79" in item.get("text", "")
            ]
            assert claims
            assert all(item.get("category") == "documented_claim" for item in claims)
            assert all(item.get("status") != "verified" for item in claims)


def test_qa_claim_keeps_changed_input_and_negative_verification_scope(independent_cli):
    cli = independent_cli
    (cli.project_path / "VERIFICATION.md").write_text(
        "# Validation memo\n\n## Captured visual checks\n"
        "Reported browser checks passed 37 assertions with three screenshots.\n\n"
        "The source report used for validation is real data from changing attempt 6; "
        "it is not an equality-verified report.\n\n"
        "## Historical notes\n"
        "Old parser smoke checks passed.\n\n"
        "Old formatting checks passed.\n\n"
        "Old temporary-file checks passed.\n"
    )
    register_documents(cli)
    cli.data("refresh")
    for format in ("markdown", "json"):
        result = exported(cli, format)
        assert "37 assertions" in result and "three screenshots" in result
        assert "changing attempt 6" in result
        assert "not an equality-verified report" in result
        if format == "json":
            data = json.loads(result)
            scopes = [
                item
                for item in data["context"] + data["items"]
                if "changing attempt 6" in item.get("text", "")
            ]
            assert scopes
            assert all(item.get("category", "").startswith("documented") for item in scopes)
            assert all(item.get("status") != "verified" for item in scopes)


def test_tight_json_keeps_document_limits_before_verbose_agent_updates(independent_cli):
    cli = independent_cli
    (cli.project_path / "STATUS.md").write_text(
        "# Continuation record\n\n## Constraints\n"
        "Original stores must remain read-only. Temporary artifacts must stay outside "
        "all protected source directories.\n\n"
        "No package publication is authorized without explicit owner approval.\n\n"
        "## Limitations\n"
        "Solaris runtime behavior remains unverified. A cross-compiled artifact is not "
        "evidence of execution on Solaris.\n\n"
        "## Decisions\n"
        "Decision: retain the manually approved distribution queue.\n"
    )
    register_documents(cli)
    cli.data("refresh")
    baseline = cli.run(
        "export", "notebook", "--format", "json", "--max-chars", "24000", json_output=False
    ).stdout
    phrases = ["owner approval", "Solaris runtime", "manually approved distribution queue"]
    assert all(phrase in baseline for phrase in phrases)
    assert any(item["kind"] == "decisions" for item in json.loads(baseline)["context"])
    # The baseline fits the critical document context. Reserve additional space
    # for a bounded stopping point, but not several optional long status updates.
    budget = len(baseline) + 1000
    register_events(
        cli,
        [
            (
                "assistant",
                f"I implemented diagnostic stage {stage}. "
                + "The local helper now reports its progress and preserves temporary observations. "
                * 13,
            )
            for stage in range(3)
        ],
    )
    cli.data("refresh")
    result = cli.run(
        "export", "notebook", "--format", "json", "--max-chars", str(budget), json_output=False
    ).stdout
    assert len(result) <= budget
    assert all(phrase in result for phrase in phrases)
    data = json.loads(result)
    assert any(item["kind"] == "decisions" for item in data["context"])
    updates = [item for item in data["context"] if item["kind"] == "recent_agent_update"]
    assert all(item.get("status") == "unverified" for item in updates)


def test_ordinary_verification_gap_survives_chat_noise_and_exports(independent_cli):
    cli = independent_cli
    (cli.project_path / "STATUS.md").write_text(
        "# Delivery notes\n\n## Before handoff\n"
        "The clean-source comparison is still waiting for 45 uninterrupted quiet seconds, "
        "within a seven-minute allowance. The last attempt ended before report generation. "
        "The application reads inputs without writing them; normal use allows other processes "
        "to continue.\n"
        "Fresh browser rendering and interaction checks have not yet been verified.\n\n"
        "## Later ideas\nPDF export is deferred beyond this release.\n"
    )
    register_documents(cli)
    register_events(
        cli,
        [
            ("user", "Please restate the earlier brief."),
            ("user", "I want you to continue this session."),
        ],
    )
    cli.data("refresh")
    resume = cli.data("resume", "notebook")
    primary = active_text(resume)
    assert "quiet" in primary and "browser" in primary
    assert not any(text in primary for text in ("restate", "continue this session", "pdf export"))
    assert resume["purpose"] and resume["objective"] is None
    for format in ("markdown", "json"):
        result = exported(cli, format)
        for meaning in (
            "45",
            "seven-minute",
            "before report generation",
            "without writing",
            "browser",
        ):
            assert meaning in result


def test_conversation_only_history_does_not_invent_work(independent_cli):
    cli = independent_cli
    register_documents(cli)
    register_events(
        cli,
        [
            ("user", "Hello!"),
            ("user", "Can you repeat that last explanation?"),
            ("assistant", "We could add collaboration later."),
        ],
    )
    cli.data("refresh")
    resume = cli.data("resume", "notebook")
    assert resume["next_actions"] == []
    history = cli.data("items", "--project", "notebook", "--all")["items"]
    conversation = [item for item in history if "repeat that last explanation" in item["text"]]
    assert conversation, "Suppression must retain conversational provenance"
    assert all(item["status"] not in {"completed", "user_completed"} for item in conversation)


def test_ordinary_cancellation_is_scoped_to_its_worktree(independent_cli):
    cli = independent_cli
    other = cli.root / "experimental notebook"
    cli.git(cli.project_path, "worktree", "add", "-q", "-b", "experiment", str(other))
    cli.data("project", "add", str(cli.project_path), "--name", "notebook")
    register_events(cli, [("user", "Please verify the package manifest.")], name="main")
    register_events(
        cli,
        [
            ("user", "Please verify the package manifest."),
            ("user", "Cancel the package manifest verification."),
        ],
        name="experiment",
        cwd=other,
    )
    cli.data("refresh")
    main = cli.data("resume", "notebook", "--worktree", str(cli.project_path))
    experiment = cli.data("resume", "notebook", "--worktree", str(other))
    assert "package manifest" in active_text(main)
    assert "package manifest" not in active_text(experiment)
    history = cli.data("items", "--project", "notebook", "--all")["items"]
    assert any(
        item["status"] == "cancelled" and "package manifest" in item["text"] for item in history
    )


def test_mixed_language_cancellation_does_not_erase_other_work(independent_cli):
    cli = independent_cli
    register_events(
        cli,
        [
            ("user", "Please verify the archive signature."),
            ("user", "Please check keyboard navigation."),
            ("user", "İmza kontrolünü iptal et. Klavye gezintisi kontrolü hâlâ gerekli."),
            ("assistant", "Everything is done; all checks passed."),
        ],
    )
    cli.data("refresh")
    resume = cli.data("resume", "notebook")
    primary = active_text(resume)
    assert "archive signature" not in primary
    assert "keyboard" in primary
    assert any(item["status"] == "unverified" for item in resume["claims"])


def test_ordinary_completion_prose_is_visible_as_claim_not_verification(independent_cli):
    cli = independent_cli
    register_events(
        cli,
        [
            ("user", "Please verify the rollback procedure."),
            ("assistant", "The rollback procedure passed and the release is complete."),
        ],
    )
    cli.data("refresh")
    resume = cli.data("resume", "notebook")
    assert "rollback" in active_text(resume)
    claims = [item for item in resume["claims"] if "release is complete" in item["text"]]
    assert claims and all(item["status"] == "unverified" for item in claims)


def test_opaque_native_history_remains_partial_in_both_exports(independent_cli):
    cli = independent_cli
    (cli.project_path / "VERIFICATION.md").write_text(
        "# Release status\n\nThe fresh visual review remains unverified because no browser is available.\n"
    )
    register_documents(cli)
    source = register_events(cli, [("user", "Continue our chat.")])
    with source.open("a") as stream:
        stream.write(
            json.dumps(
                {
                    "type": "response_item",
                    "timestamp": "2026-09-05T07:00:00Z",
                    "payload": {
                        "type": "agent_message",
                        "content": [
                            {
                                "type": "encrypted_content",
                                "encrypted_content": "unavailable-native-content",
                            }
                        ],
                    },
                }
            )
            + "\n"
        )
    cli.data("refresh", code=3)
    resume = cli.data("resume", "notebook")
    assert resume["coverage"]["status"] == "partial"
    assert "visual" in active_text(resume)
    assert "partial" in exported(cli, "markdown")
    assert json.loads(exported(cli, "json"))["coverage"]["status"] == "partial"


def test_separate_yet_to_paragraphs_keep_pending_work_and_conditions(independent_cli):
    cli = independent_cli
    (cli.project_path / "STATUS.md").write_text(
        "# Handoff checkpoint\n\n## Work still to verify\n"
        "The source equality run has yet to finish.\n\n"
        "Before retrying, require 75 uninterrupted quiet seconds within a nine-minute budget. "
        "The last attempt stopped before generation.\n\n"
        "This release-only condition does not restrict normal read-only collection. "
        "Producers may keep running during ordinary use.\n\n"
        "Browser rendering has yet to be checked on the revised viewer.\n"
    )
    register_documents(cli)
    register_events(cli, [("user", "Please carry on with this chat.")])
    cli.data("refresh")
    primary = active_text(cli.data("resume", "notebook"))
    assert "equality" in primary and "browser" in primary
    assert "carry on with this chat" not in primary
    for format in ("markdown", "json"):
        result = exported(cli, format)
        for meaning in (
            "75",
            "nine-minute",
            "before generation",
            "normal read-only",
            "keep running",
        ):
            assert meaning in result


@pytest.mark.parametrize(
    "instruction,other,cancellation,target,retained",
    [
        (
            "Please validate the transport manifest.",
            "Please inspect the terminal layout.",
            "Cancel validation of the transport manifest.",
            "transport manifest",
            "terminal layout",
        ),
        (
            "Lütfen paket dizinini doğrula.",
            "Lütfen klavye kısayollarını denetle.",
            "Paket dizini doğrulamasını iptal et.",
            "paket dizin",
            "klavye",
        ),
    ],
)
def test_new_nominal_cancellation_forms_resolve_only_matching_request(
    independent_cli, instruction, other, cancellation, target, retained
):
    cli = independent_cli
    register_events(cli, [("user", instruction), ("user", other), ("user", cancellation)])
    cli.data("refresh")
    primary = active_text(cli.data("resume", "notebook"))
    assert target not in primary
    assert retained in primary
    history = cli.data("items", "--project", "notebook", "--all")["items"]
    assert any(
        item["kind"] in {"task", "next_action"}
        and item["status"] == "cancelled"
        and target in item["text"].casefold()
        for item in history
    ), "The cancelled predecessor and its provenance must survive"


def test_negated_blocker_keeps_actual_pending_rerun_without_blocked_state(independent_cli):
    cli = independent_cli
    (cli.project_path / "STATUS.md").write_text(
        "# Current check\n\nThe streaming benchmark is not blocked, "
        "but validation still needs to be rerun on the latest checkout.\n"
    )
    register_documents(cli)
    register_events(
        cli,
        [
            ("user", "Please verify the packaging manifest."),
            ("user", "Do not cancel the packaging manifest verification."),
        ],
    )
    cli.data("refresh")
    resume = cli.data("resume", "notebook")
    primary = active_text(resume)
    assert "packaging manifest" in primary and "streaming benchmark" in primary
    streaming = [item for item in resume["next_actions"] if "streaming benchmark" in item["text"]]
    assert streaming and all(item["status"] != "blocked" for item in streaming)


def append_recorded_tools(source, cli, count=85):
    start = datetime(2026, 9, 5, 8, 0, tzinfo=UTC)
    with source.open("a") as stream:
        for number in range(count):
            output = f"Observed diagnostic batch {number}."
            if number == count - 1:
                output = (
                    "outer_comparison attempt=1 verified=false changed_files=3\n"
                    "release_generation attempt=2 started_at=2026-09-05T08:01:24Z\n"
                )
            stream.write(
                json.dumps(
                    {
                        "type": "event_msg",
                        "timestamp": (start + timedelta(seconds=number)).isoformat(),
                        "payload": {
                            "type": "item_completed",
                            "item": {
                                "type": "CommandExecution",
                                "id": f"diagnostic-{number}",
                                "command": ["read-recorded-status"],
                                "cwd": str(cli.project_path),
                                "exit_code": 0,
                                "status": "completed",
                                "stdout": output,
                                "aggregated_output": output,
                            },
                        },
                    }
                )
                + "\n"
            )


def test_changed_user_procedure_survives_more_than_sixty_recorded_tools(independent_cli):
    cli = independent_cli
    (cli.project_path / "VERIFICATION.md").write_text(
        "# Verification\n\n"
        "The equality check remains unfinished. The documented verifier requires 45 continuous "
        "quiet seconds within eight minutes. The last attempt stopped before generation.\n"
    )
    instruction = (
        "The old preflight is counterproductive. Remove the 45-second quiet requirement and "
        "instead verify digest equality during generation with retries. Get one equality record. "
        "Browser QA must use the installed headless engine and inspect non-local requests."
    )
    register_documents(cli)
    source = register_events(cli, [("user", instruction)])
    append_recorded_tools(source, cli)
    cli.data("refresh")
    resume = cli.data("resume", "notebook")
    latest = resume["latest_user_instruction"]
    assert latest["text"] == instruction
    assert latest["category"] == "recorded_user_instruction" and latest["record_id"]
    assert latest["status"] == "recorded"
    pending = json.dumps(resume["continuity"]["pending"], ensure_ascii=False)
    assert "45 continuous" in pending, "Contradictory old document evidence must remain inspectable"
    conflicts = json.dumps(resume["continuity"]["conflicts"], ensure_ascii=False).casefold()
    assert "instruction" in conflicts and "document" in conflicts
    results = resume["recent_recorded_results"]
    assert "verified=false" in json.dumps(results)
    assert all(result["category"] == "recorded_tool_result" for result in results)
    assert all(result["status"] == "captured" for result in results)
    for format in ("markdown", "json"):
        output = cli.run(
            "export", "notebook", "--format", format, "--max-chars", "24000", json_output=False
        ).stdout
        assert "Remove the 45-second quiet requirement" in output
        assert "45 continuous" in output and "verified=false" in output
        if format == "json":
            context = json.loads(output)["context"]
            assert any(item["kind"] == "latest_user_instruction" for item in context)
            assert any(item["kind"] == "recent_recorded_result" for item in context)


def test_empty_agent_wrapper_does_not_replace_meaningful_stopping_context(independent_cli):
    cli = independent_cli
    register_documents(cli)
    source = register_events(cli, [("user", "Please inspect the native window navigation.")])
    append_recorded_tools(source, cli, count=2)
    wrapper = "Message Type: MESSAGE\nTask name: /root\nSender: /root/checker\nPayload:\n"
    with source.open("a") as stream:
        stream.write(
            json.dumps(
                {
                    "type": "response_item",
                    "timestamp": "2026-09-05T09:00:00Z",
                    "payload": {
                        "type": "agent_message",
                        "id": "empty-wrapper",
                        "author": "/root/checker",
                        "recipient": "/root",
                        "content": [{"type": "input_text", "text": wrapper}],
                    },
                }
            )
            + "\n"
        )
    cli.data("refresh")
    resume = cli.data("resume", "notebook")
    assert (
        resume["latest_user_instruction"]["text"] == "Please inspect the native window navigation."
    )
    stopped = json.dumps(resume["where_work_stopped"], ensure_ascii=False)
    assert "Message Type:" not in stopped and "Payload:" not in stopped
    assert "verified=false" in json.dumps(resume["recent_recorded_results"])
    document = json.loads(
        cli.run("export", "notebook", "--format", "json", json_output=False).stdout
    )
    stopping = [item for item in document["context"] if item["kind"] == "stopping_point"]
    assert stopping and all("Message Type:" not in json.dumps(item) for item in stopping)
