"""Release boundaries: immutable wheels, offline formulae and relocatable bundles."""

import importlib.util
import tarfile
import tomllib
import zipfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "homebrew_packaging", Path(__file__).parents[1] / "tools/homebrew.py"
)
assert spec and spec.loader
packaging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packaging)


def wheel(tmp_path, dependencies=""):
    version = tomllib.loads((packaging.ROOT / "pyproject.toml").read_text())["project"]["version"]
    path = tmp_path / f"rifja-{version}-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            f"rifja-{version}.dist-info/METADATA",
            f"Metadata-Version: 2.4\nName: rifja\nVersion: {version}\n"
            "Requires-Python: >=3.14\nLicense-Expression: MIT\n" + dependencies,
        )
    return path


def test_formula_rejects_unhandled_dependency(tmp_path):
    with pytest.raises(ValueError, match="unsupported_wheel"):
        packaging.formula(wheel(tmp_path, "Requires-Dist: requests\n"), "https://example.org/x.whl")


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org/x.whl",
        "https://user:secret@example.org/x.whl",
        "https://example.org/x?token=x",
    ],
)
def test_formula_rejects_insecure_or_credential_urls(tmp_path, url):
    with pytest.raises(ValueError):
        packaging.formula(wheel(tmp_path), url)


def test_formula_escapes_ruby_interpolation_from_local_path(tmp_path):
    source = wheel(tmp_path)
    output = packaging.formula(source, f"file:///tmp/evil%23%7Bname%7D/{source.name}")
    assert f'sha256 "{packaging.digest(source)}"' in output
    assert "@@" not in output
    assert packaging.ruby_string('#{system("false")}') == '"\\#{system(\\"false\\")}"'


def test_release_copy_refuses_changed_bytes_and_symlink(tmp_path):
    source = wheel(tmp_path)
    target = tmp_path / "release" / source.name
    packaging.checked_copy(source, target)
    packaging.checked_copy(source, target)
    assert target.read_bytes() == source.read_bytes()
    source.write_bytes(b"changed release")
    with pytest.raises(ValueError, match="immutable_release"):
        packaging.checked_copy(source, target)
    link = tmp_path / "alias"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        packaging.checked_copy(source, link)


def test_bundle_is_reproducible_relocatable_and_allowlisted(tmp_path):
    source = wheel(tmp_path)
    first = packaging.bundle(source, tmp_path / "one")
    second = packaging.bundle(source, tmp_path / "two")
    assert first.read_bytes() == second.read_bytes()
    with tarfile.open(first) as archive:
        members = archive.getmembers()
        assert len(members) >= 9
        assert any(m.name.endswith("/docs/usage.md") for m in members)
        assert any(m.name.endswith("/docs/homebrew.md") for m in members)
        assert all(m.isfile() and m.uid == m.gid == m.mtime == 0 for m in members)
        assert all(".local" not in m.name and not m.name.startswith("/") for m in members)
        installer = next(m for m in members if m.name.endswith("/install.sh"))
        assert installer.mode == 0o755
    with pytest.raises(FileExistsError):
        packaging.bundle(source, tmp_path / "one")


def test_claude_plugin_manifests_match_the_release_version() -> None:
    """Plugin distribution manifests must ship the released identity."""
    import json

    root = Path(__file__).parents[1] / "packaging" / "claude-plugin"
    plugin = json.loads((root / ".claude-plugin" / "plugin.json").read_text())
    marketplace = json.loads((root / "marketplace.json").read_text())
    mcp = json.loads((root / ".mcp.json").read_text())
    hooks = json.loads((root / "hooks" / "hooks.json").read_text())
    version = tomllib.loads((packaging.ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert plugin["name"] == "rifja" and plugin["version"] == version
    assert marketplace["plugins"][0]["version"] == version
    assert marketplace["plugins"][0]["name"] == "rifja"
    assert mcp["mcpServers"]["rifja"] == {"command": "rifja", "args": ["mcp"]}
    hook = hooks["hooks"]["SessionStart"][0]["hooks"][0]
    assert hook["timeout"] == 10
    assert "${CLAUDE_PLUGIN_ROOT}" in hook["command"]
    shipped = (root / "hooks" / "session-start.sh").read_text()
    canonical = (packaging.ROOT / "packaging" / "hooks" / "session-start.sh").read_text()
    assert shipped == canonical, "the plugin hook must match the canonical fail-open script"
    assert "exit 0" in shipped and "head -c" in shipped
