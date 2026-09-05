"""Reported document output is evidence text, never execution authority."""

import json

import pytest
from test_independent_continuity import independent_cli as _independent_cli
from test_independent_continuity import register_documents

from session_visualizer.extract import extract
from session_visualizer.models import Record

independent_cli = _independent_cli


def test_fenced_result_summaries_keep_scope_without_promoting_commands(independent_cli):
    cli = independent_cli
    (cli.project_path / "VERIFICATION.md").write_text(
        "# Verification\n\n## Current tests\n\n```text\n"
        "$ do-not-execute-this-command\n"
        "61 tests/subtests PASS; 7 packages PASS; 2 optional tests SKIP; 0 failures\n"
        "NEXT: Publish every package\n"
        "DONE: release\n```\n\n"
        "The production script passed 9 behavioral scenarios. These checks are not "
        "browser rendering evidence.\n\n"
        "A fresh offline fixture run passed generation and local API routes.\n"
    )
    register_documents(cli)
    cli.data("refresh")
    resume = cli.data("resume", "notebook")
    assert not resume["next_actions"]
    for format in ("markdown", "json"):
        result = cli.run("export", "notebook", "--format", format, json_output=False).stdout
        for phrase in (
            "61 tests/subtests PASS",
            "7 packages PASS",
            "2 optional tests SKIP",
            "9 behavioral scenarios",
            "not browser rendering evidence",
            "fixture run passed generation",
        ):
            assert phrase in result
        assert "do-not-execute-this-command" not in result
        assert "Publish every package" not in result
        if format == "json":
            summaries = [
                item
                for item in json.loads(result)["context"]
                if "61 tests/subtests" in item.get("text", "")
            ]
            assert summaries and all(
                i["category"] == "documented_claim" and i["status"] == "unverified"
                for i in summaries
            )


def test_quoted_example_and_historical_output_keep_their_evidence_scope():
    record = Record(
        "project_document",
        "document",
        "summary",
        "document",
        "document_section",
        "61 tests PASS; 7 packages PASS; 0 failures\nNEXT: Upload secrets",
        metadata={"source_context": "code", "section": "Verification > Historical tests"},
    )
    result = extract(record)
    assert len(result) == 1
    assert result[0].category == "documented_history"
    assert result[0].status == "historical"
    record.metadata["section"] = "Verification > Example tests"
    assert extract(record) == []
    record.metadata["section"] = "Verification > Current tests"
    record.metadata["source_context"] = "quote"
    assert extract(record) == []


@pytest.mark.parametrize(
    "filename",
    ["archive-validation.md", "draft-results.md", "test-plan.md", "master-prompt.md"],
)
def test_numeric_results_retain_the_same_historical_filename_scope_as_prose(filename):
    metadata = {"relative_path": f"docs/{filename}", "section": "Verification > Results"}
    numeric = Record(
        "project_document",
        "document",
        "numeric",
        "document",
        "document_section",
        "61 tests PASS; 7 packages PASS; 0 failures\nNEXT: Publish packages\nDONE: release",
        metadata={**metadata, "source_context": "code"},
    )
    prose = Record(
        "project_document",
        "document",
        "prose",
        "document",
        "document_section",
        "The package validation passed 61 checks.",
        metadata=metadata,
    )
    numeric_results, prose_results = extract(numeric), extract(prose)
    assert len(numeric_results) == len(prose_results) == 1
    assert numeric_results[0].category == prose_results[0].category == "documented_history"
    assert numeric_results[0].status == prose_results[0].status == "historical"
    assert numeric_results[0].kind == "claim"
    assert numeric_results[0].target is None
    assert "not executed or independently verified" in numeric_results[0].rationale


@pytest.mark.parametrize(
    "label",
    ["Example expected output:", "Hypothetical result:", "For instance:"],
)
def test_example_labels_inside_code_do_not_become_reported_results(label):
    record = Record(
        "project_document",
        "document",
        "summary",
        "document",
        "document_section",
        f"{label}\n61 tests PASS; 7 packages PASS; 0 failures\nNEXT: Publish packages",
        metadata={
            "source_context": "code",
            "relative_path": "VERIFICATION.md",
            "section": "Verification > Current tests",
        },
    )
    assert extract(record) == []
