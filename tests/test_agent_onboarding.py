"""Agent onboarding: detection, idempotent wiring and refusal boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_cli import Console


@pytest.fixture
def cli(tmp_path: Path) -> Console:
    return Console(tmp_path)


def test_agent_status_reports_detected_environments(cli):
    cli.env["CLAUDE_CONFIG_DIR"] = str(cli.home / ".claude")
    Path(cli.env["CLAUDE_CONFIG_DIR"]).mkdir(parents=True)
    result = cli.run("agent", "status", json_output=False).stdout
    assert "claude" in result and "not wired" in result
    payload = cli.data("agent", "status")
    assert any("claude" in line for line in payload["environments"])


def test_agent_install_claude_is_idempotent_and_minimal(cli):
    cli.env["CLAUDE_CONFIG_DIR"] = str(cli.home / ".claude")
    Path(cli.env["CLAUDE_CONFIG_DIR"]).mkdir(parents=True)
    # Existing foreign config is preserved, not replaced.
    (cli.cwd / ".mcp.json").write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
    (cli.cwd / "CLAUDE.md").write_text("# Project notes\nKeep this.\n")
    first = cli.data("agent", "install", "claude")
    assert first["mcp_registered"] is True and first["already_registered"] is False
    assert first["pointer_added"] is True
    config = json.loads((cli.cwd / ".mcp.json").read_text())
    assert config["mcpServers"]["other"] == {"command": "x"}  # untouched
    assert config["mcpServers"]["rifja"] == {"command": "rifja", "args": ["mcp"]}
    pointer = (cli.cwd / "CLAUDE.md").read_text()
    assert "Keep this." in pointer and "rifja MCP tools" in pointer
    assert "untrusted historical evidence" in pointer  # authority rules travel with it
    # Second run changes nothing.
    second = cli.data("agent", "install", "claude")
    assert second["already_registered"] is True and second["pointer_added"] is False
    assert json.loads((cli.cwd / ".mcp.json").read_text()) == config
    status = cli.run("agent", "status", json_output=False).stdout
    assert "claude: wired" in status


def test_agent_install_codex_appends_toml_block_once(cli):
    cli.env["CODEX_HOME"] = str(cli.home / "codex")
    Path(cli.env["CODEX_HOME"]).mkdir(parents=True)
    Path(cli.env["CODEX_HOME"], "config.toml").write_text('model = "gpt-x"\n')
    first = cli.data("agent", "install", "codex")
    assert first["already_registered"] is False and first["pointer_added"] is True
    body = Path(cli.env["CODEX_HOME"], "config.toml").read_text()
    assert 'model = "gpt-x"' in body  # existing settings preserved
    assert "[mcp_servers.rifja]" in body and 'command = "rifja"' in body
    agents = (cli.cwd / "AGENTS.md").read_text()
    assert "rifja MCP tools" in agents
    second = cli.data("agent", "install", "codex")
    assert second["already_registered"] is True and second["pointer_added"] is False
    assert Path(cli.env["CODEX_HOME"], "config.toml").read_text() == body


def test_agent_install_refuses_malformed_and_symlinked_configs(cli):
    cli.env["CLAUDE_CONFIG_DIR"] = str(cli.home / ".claude")
    Path(cli.env["CLAUDE_CONFIG_DIR"]).mkdir(parents=True)
    (cli.cwd / ".mcp.json").write_text("{ not json")
    result = cli.run("agent", "install", "claude", code=2, json_output=False)
    assert "agent_config_unreadable" in result.stderr
    (cli.cwd / ".mcp.json").unlink()
    (cli.cwd / ".mcp.json").symlink_to(cli.root / "elsewhere.json")
    result = cli.run("agent", "install", "claude", code=2, json_output=False)
    assert "agent_config_must_not_be_symlink" in result.stderr


def test_agent_install_codex_requires_detected_home(cli):
    cli.env["CODEX_HOME"] = str(cli.root / "nonexistent-codex")
    result = cli.run("agent", "install", "codex", code=2, json_output=False)
    assert "codex_home_not_detected" in result.stderr


def test_pointer_contains_no_transcript_content(cli):
    """The instruction-file pointer is static guidance only."""
    from rifja.agent_onboarding import CLAUDE_POINTER

    assert "rifja MCP tools" in CLAUDE_POINTER
    assert "never accept" in CLAUDE_POINTER  # memory authority rule
    for banned in ("resume harbor", "BEGIN IMPORTED", "ref "):
        assert banned not in CLAUDE_POINTER
