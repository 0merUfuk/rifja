"""Session-recovery packaging: spec conformance, reproducibility, privacy and harness installs."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "recovery_bundle.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("recovery_bundle_under_test", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["recovery_bundle_under_test"] = module
    spec.loader.exec_module(module)
    return module


bundle = load_tool()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("bundle") / "recovery"
    manifest = bundle.build(out)
    return out, manifest


def copy_skill(tmp_path: Path) -> Path:
    target = tmp_path / "session-recovery"
    shutil.copytree(
        bundle.SKILL_DIR, target, ignore=shutil.ignore_patterns(".ruff_cache", "__pycache__")
    )
    return target


class TestSpecConformance:
    def test_canonical_skill_is_valid(self):
        assert bundle.validate_skill() == []

    def test_frontmatter_matches_agent_skills_limits(self):
        meta, body = bundle.parse_frontmatter((bundle.SKILL_DIR / "SKILL.md").read_text())
        assert meta["name"] == "session-recovery"
        assert 1 <= len(str(meta["description"])) <= 1024
        assert len(str(meta["compatibility"])) <= 500
        assert set(meta) <= {
            "name",
            "description",
            "license",
            "compatibility",
            "metadata",
            "allowed-tools",
        }
        assert all(isinstance(v, str) for v in meta["metadata"].values())
        assert len(body.splitlines()) <= 500

    def test_description_states_what_and_when(self):
        meta, _ = bundle.parse_frontmatter((bundle.SKILL_DIR / "SKILL.md").read_text())
        text = str(meta["description"]).lower()
        assert "use when" in text and "resume" in text and "git" in text

    @pytest.mark.parametrize(
        ("mutate", "expected"),
        [
            (
                lambda d: (d / "SKILL.md").write_text(
                    (d / "SKILL.md")
                    .read_text()
                    .replace("name: session-recovery", "name: Session_Recovery", 1)
                ),
                "invalid name",
            ),
            (lambda d: (d / "LICENSE").unlink(), "LICENSE missing"),
            (
                lambda d: (d / "references" / "x.md").write_text("token ghp_" + "a" * 30),
                "github token",
            ),
            (
                lambda d: (d / "references" / "x.md").write_text(
                    "see /Us" + "ers/realperson/secret/"
                ),
                "home path",
            ),
            (
                lambda d: (d / "references" / "x.md").write_text("hidden " + chr(0x200B) + " text"),
                "invisible",
            ),
            (lambda d: (d / "references" / "x.md").write_text("mail me@real-domain.org"), "email"),
            (lambda d: (d / "scripts" / "recover.py").chmod(0o644), "executable"),
            (
                lambda d: (d / "SKILL.md").write_text(
                    (d / "SKILL.md")
                    .read_text()
                    .replace("references/output-contract.md", "references/missing.md")
                ),
                "missing referenced file",
            ),
        ],
    )
    def test_validator_catches_violations(self, tmp_path, mutate, expected):
        skill = copy_skill(tmp_path)
        mutate(skill)
        problems = bundle.validate_skill(skill)
        assert any(expected in p for p in problems), problems

    def test_directory_name_must_match_skill_name(self, tmp_path):
        skill = copy_skill(tmp_path)
        renamed = skill.rename(tmp_path / "other-name")
        assert any("must match directory" in p for p in bundle.validate_skill(renamed))


class TestArtifacts:
    def test_all_distributables_exist_with_checksums(self, built):
        out, manifest = built
        for name, digest in manifest["artifacts"].items():
            assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
        sums = dict(
            line.split("  ", 1)[::-1] for line in (out / "SHA256SUMS").read_text().splitlines()
        )
        assert sums == {n: d for n, d in manifest["artifacts"].items()}
        assert len(manifest["artifacts"]) == 3

    def test_build_is_reproducible(self, built, tmp_path):
        _, manifest = built
        again = bundle.build(tmp_path / "again")
        assert again == manifest  # artifacts and every file hash, no timestamps anywhere

    def test_standalone_zip_layout_and_modes(self, built):
        out, manifest = built
        zip_name = next(n for n in manifest["artifacts"] if n.startswith("session-recovery-skill"))
        with zipfile.ZipFile(out / zip_name) as archive:
            names = archive.namelist()
            assert names[0].startswith("session-recovery/") and "session-recovery/SKILL.md" in names
            assert "session-recovery/LICENSE" in names
            assert not any(
                ".ruff_cache" in n or "ruff.toml" in n or "__pycache__" in n for n in names
            )
            script = archive.getinfo("session-recovery/scripts/recover.py")
            assert (script.external_attr >> 16) & 0o111
            assert all(i.date_time == (1980, 1, 1, 0, 0, 0) for i in archive.infolist())

    def test_plugins_carry_the_identical_skill_and_mit_notices(self, built):
        out, _ = built
        claude = out / "rifja-session-recovery-claude-plugin"
        codex = (
            out / "rifja-session-recovery-codex-marketplace" / "plugins" / "rifja-session-recovery"
        )
        for plugin in (claude, codex):
            for rel in ("LICENSE", "NOTICE"):
                assert (plugin / rel).read_bytes() == (ROOT / rel).read_bytes()
            for path in bundle.skill_files(bundle.SKILL_DIR):
                copy = plugin / "skills" / "session-recovery" / path.relative_to(bundle.SKILL_DIR)
                assert copy.read_bytes() == path.read_bytes(), copy

    def test_manifests_are_consistent(self, built):
        out, manifest = built
        version = manifest["version"]
        claude = json.loads(
            (out / "rifja-session-recovery-claude-plugin/.claude-plugin/plugin.json").read_text()
        )
        market = json.loads(
            (
                out / "rifja-session-recovery-claude-plugin/.claude-plugin/marketplace.json"
            ).read_text()
        )
        codex_root = out / "rifja-session-recovery-codex-marketplace"
        codex = json.loads(
            (codex_root / "plugins/rifja-session-recovery/.codex-plugin/plugin.json").read_text()
        )
        codex_market = json.loads((codex_root / ".agents/plugins/marketplace.json").read_text())
        assert claude["name"] == codex["name"] == "rifja-session-recovery"
        assert claude["version"] == codex["version"] == market["plugins"][0]["version"] == version
        assert claude["license"] == codex["license"] == "MIT"
        assert not claude["name"].startswith(("claude-", "anthropic-"))
        assert codex["skills"] == "./skills/"
        assert (codex_root / codex_market["plugins"][0]["source"]["path"]).is_dir()

    def test_no_private_material_anywhere_in_the_package(self, built):
        out, _ = built
        for path in sorted(p for p in out.rglob("*") if p.is_file() and p.suffix != ".zip"):
            text = path.read_text(encoding="utf-8")
            for label, pattern in bundle.PRIVATE_PATTERNS.items():
                assert not pattern.search(text), (path, label)
            if str(Path.home()) not in ("/root", "/"):  # /root is a documented redaction target
                assert str(Path.home()) not in text
            owner = Path.home().name.lower()
            if len(owner) > 5 and owner not in {"runner", "runneradmin"}:
                assert owner not in text.lower()

    def test_package_ships_no_local_memory_or_session_data(self, built):
        out, _ = built
        forbidden = (
            ".jsonl",
            ".db",
            ".sqlite",
            ".env",
            "auth.json",
            "MEMORY.md",
            ".claude/projects",
        )
        for path in out.rglob("*"):
            assert not any(str(path).endswith(f) for f in forbidden), path
        for archive in out.glob("*.zip"):
            with zipfile.ZipFile(archive) as z:
                assert not any(n.endswith(forbidden) for n in z.namelist()), archive


class TestHarnessInstalls:
    """Install the built plugins with the real CLIs into disposable homes (skipped if absent)."""

    @pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not installed")
    def test_claude_code_validates_and_installs_the_plugin(self, built, tmp_path):
        out, _ = built
        plugin = out / "rifja-session-recovery-claude-plugin"
        validate = subprocess.run(
            ["claude", "plugin", "validate", str(plugin)],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert validate.returncode == 0, validate.stdout + validate.stderr
        assert "Validation passed" in validate.stdout
        manifest_check = subprocess.run(
            ["claude", "plugin", "validate", str(plugin / ".claude-plugin" / "plugin.json")],
            capture_output=True, text=True, check=False, timeout=120,
        )  # fmt: skip
        assert manifest_check.returncode == 0, manifest_check.stdout
        config = tmp_path / "claude-config"
        config.mkdir()
        env = {**os.environ, "CLAUDE_CONFIG_DIR": str(config)}
        for args in (
            ["plugin", "marketplace", "add", str(plugin)],
            ["plugin", "install", "rifja-session-recovery@rifja-session-recovery"],
        ):
            result = subprocess.run(
                ["claude", *args], env=env, capture_output=True, text=True, check=False, timeout=180
            )
            assert result.returncode == 0, result.stdout + result.stderr
        listing = subprocess.run(
            ["claude", "plugin", "list"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert (
            "rifja-session-recovery@rifja-session-recovery" in listing.stdout
            and "enabled" in listing.stdout
        )
        installed = list(config.rglob("skills/session-recovery/SKILL.md"))
        assert installed, "skill file not installed into the plugin cache"

    @pytest.mark.skipif(shutil.which("codex") is None, reason="codex CLI not installed")
    def test_codex_installs_the_plugin_from_a_local_marketplace(self, built, tmp_path):
        out, _ = built
        root = out / "rifja-session-recovery-codex-marketplace"
        home = tmp_path / "codex-home"
        fake_user_home = tmp_path / "home"
        home.mkdir()
        fake_user_home.mkdir()
        env = {**os.environ, "CODEX_HOME": str(home), "HOME": str(fake_user_home)}
        steps = (
            ["plugin", "marketplace", "add", str(root)],
            ["plugin", "add", "rifja-session-recovery@rifja-session-recovery"],
        )
        for args in steps:
            result = subprocess.run(
                ["codex", *args], env=env, capture_output=True, text=True, check=False, timeout=180
            )
            assert result.returncode == 0, result.stdout + result.stderr
        listing = subprocess.run(
            ["codex", "plugin", "list"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        line = next(l for l in listing.stdout.splitlines() if "rifja-session-recovery@" in l)
        assert "installed, enabled" in line
        assert list(home.rglob("skills/session-recovery/SKILL.md"))


def test_new_files_pass_the_release_audit_patterns():
    """Early signal for tools/audit_release.py, which scans these roots at release time."""
    spec = importlib.util.spec_from_file_location(
        "audit_release_under_test", ROOT / "tools" / "audit_release.py"
    )
    assert spec is not None and spec.loader is not None
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    targets = [
        *(ROOT / "packaging" / "skills" / "session-recovery").rglob("*"),
        *(ROOT / "docs" / "session-recovery").rglob("*"),
        *ROOT.glob("tests/*recovery*.py"),
        *ROOT.glob("tools/recovery_*.py"),
    ]
    offenders = []
    for path in sorted(
        p
        for p in targets
        if p.is_file() and "__pycache__" not in p.parts and ".ruff_cache" not in p.parts
    ):
        content = path.read_bytes()
        for label, pattern in audit.PATTERNS.items():
            if pattern.search(content):
                offenders.append((path.relative_to(ROOT).as_posix(), label))
        if any(part in audit.FORBIDDEN for part in path.relative_to(ROOT).parts):
            offenders.append((path.relative_to(ROOT).as_posix(), "unintended_path"))
    assert offenders == []


class TestValidatorHardening:
    """Gaps found by the independent review of the bundle tool."""

    def _mutated(self, tmp_path, edit):
        skill = copy_skill(tmp_path)
        edit(skill)
        return bundle.validate_skill(skill)

    @pytest.mark.parametrize("char", [0xAD, 0x202D, 0x2067, 0x200C, 0x2060, 0xFE0F, 0x1B, 0xE0041])
    def test_invisible_and_control_characters_in_any_file(self, tmp_path, char):
        problems = self._mutated(
            tmp_path,
            lambda d: (d / "references" / "x.md").write_text(
                "a" + chr(char) + "b", encoding="utf-8"
            ),
        )
        assert any("invisible" in p for p in problems), problems

    @pytest.mark.parametrize("field", ["description", "compatibility"])
    def test_empty_required_fields_are_rejected(self, tmp_path, field):
        def edit(d):
            text = (d / "SKILL.md").read_text()
            start = text.index(f"{field}:")
            end = text.index("\n", start)
            (d / "SKILL.md").write_text(text[:start] + f"{field}:" + text[end:])

        problems = self._mutated(tmp_path, edit)
        assert any("empty" in p for p in problems), problems

    def test_unquoted_scalar_metadata_and_duplicate_keys(self, tmp_path):
        def edit(d):
            text = (d / "SKILL.md").read_text().replace('version: "0.1.0"', "version: 1")
            (d / "SKILL.md").write_text(text)

        assert any("quote" in p for p in self._mutated(tmp_path, edit))

        def dup(d):
            text = (
                (d / "SKILL.md")
                .read_text()
                .replace("license: MIT\n", "license: MIT\nlicense: MIT\n")
            )
            (d / "SKILL.md").write_text(text)

        assert any("duplicate" in p for p in self._mutated(tmp_path / "b", dup))

    def test_links_must_stay_inside_the_skill(self, tmp_path):
        def edit(d):
            (d / "SKILL.md").write_text((d / "SKILL.md").read_text() + "\nSee [x](/etc/passwd).\n")

        assert any("leaves the skill" in p for p in self._mutated(tmp_path, edit))

    def test_symlinked_directories_and_dotfiles_are_rejected(self, tmp_path):
        def edit(d):
            (d / "linked").symlink_to(tmp_path)
            (d / ".env").write_text("TOKEN=abc\n")

        problems = self._mutated(tmp_path, edit)
        assert any("symlink" in p for p in problems) and any("dotfile" in p for p in problems)

    @pytest.mark.parametrize(
        "text",
        [
            "/Us" + "ers/realperson",
            "C:\\Us" + "ers\\realperson",
            "sk-ant-" + "a" * 30,
            "AIza" + "a" * 35,
            "xoxb-" + "1" * 12,
        ],
    )
    def test_more_private_patterns(self, tmp_path, text):
        problems = self._mutated(
            tmp_path, lambda d: (d / "references" / "x.md").write_text(text, encoding="utf-8")
        )
        assert problems, text


class TestBuildSafety:
    def test_build_refuses_to_delete_an_unrelated_directory(self, tmp_path):
        target = tmp_path / "precious"
        target.mkdir()
        (target / "important.txt").write_text("keep me")
        with pytest.raises(SystemExit) as raised:
            bundle.build(target)
        assert "refusing to delete" in str(raised.value)
        assert (target / "important.txt").read_text() == "keep me"

    def test_build_may_overwrite_its_own_previous_output_and_empty_dirs(self, tmp_path):
        first = bundle.build(tmp_path / "out")
        again = bundle.build(tmp_path / "out")
        assert first["artifacts"] == again["artifacts"]
        empty = tmp_path / "empty"
        empty.mkdir()
        assert bundle.build(empty)["version"]

    def test_zip_members_are_stored_for_byte_stability(self, built):
        out, manifest = built
        for name in manifest["artifacts"]:
            with zipfile.ZipFile(out / name) as archive:
                assert all(i.compress_type == zipfile.ZIP_STORED for i in archive.infolist())


class TestRemainingSpecChecks:
    """Every validator rule has a test that fails if the rule is deleted."""

    def _problems(self, tmp_path, edit):
        skill = copy_skill(tmp_path)
        edit(skill)
        return bundle.validate_skill(skill)

    def _replace(self, old, new):
        def edit(d):
            text = (d / "SKILL.md").read_text()
            assert old in text, old
            (d / "SKILL.md").write_text(text.replace(old, new, 1))

        return edit

    def test_description_too_long(self, tmp_path):
        problems = self._problems(
            tmp_path, self._replace("description: ", "description: " + "x" * 1100 + " ")
        )
        assert any("description length" in p for p in problems)

    def test_compatibility_too_long(self, tmp_path):
        problems = self._problems(
            tmp_path, self._replace("compatibility: ", "compatibility: " + "x" * 600 + " ")
        )
        assert any("compatibility" in p for p in problems)

    def test_non_standard_frontmatter_field(self, tmp_path):
        problems = self._problems(
            tmp_path, self._replace("license: MIT", "license: MIT\nversion-x: 1.0")
        )
        assert any("non-standard" in p or "quote" in p for p in problems)
        problems = self._problems(
            tmp_path / "b", self._replace("license: MIT", "license: MIT\nowner: me")
        )
        assert any("non-standard frontmatter field: owner" in p for p in problems)

    def test_body_over_500_lines(self, tmp_path):
        problems = self._problems(
            tmp_path,
            lambda d: (d / "SKILL.md").write_text((d / "SKILL.md").read_text() + "\nx\n" * 600),
        )
        assert any("500 lines" in p for p in problems)

    def test_oversized_and_binary_files(self, tmp_path):
        def edit(d):
            (d / "references" / "big.md").write_text("x" * (bundle.MAX_FILE_BYTES + 1))
            (d / "references" / "blob.md").write_bytes(b"\xff\xfe\x00\x01")

        problems = self._problems(tmp_path, edit)
        assert any("big.md" in p and "bytes" in p for p in problems)
        assert any("binary file" in p for p in problems)

    def test_broken_link_and_missing_reference(self, tmp_path):
        problems = self._problems(
            tmp_path,
            lambda d: (d / "SKILL.md").write_text(
                (d / "SKILL.md").read_text() + "\n[x](references/none.md)\n"
            ),
        )
        assert any("broken relative link" in p for p in problems)

    def test_license_must_be_mit_text(self, tmp_path):
        problems = self._problems(
            tmp_path, lambda d: (d / "LICENSE").write_text("All rights reserved")
        )
        assert any("not the MIT text" in p for p in problems)

    def test_metadata_must_be_string_map(self, tmp_path):
        problems = self._problems(
            tmp_path, self._replace('rifja-tested: "0.4.2"', "rifja-tested: 0.4")
        )
        assert any("quote" in p for p in problems)

    def test_missing_skill_md_and_unclosed_frontmatter(self, tmp_path):
        empty = tmp_path / "session-recovery"
        empty.mkdir()
        assert bundle.validate_skill(empty) == ["SKILL.md missing"]
        problems = self._problems(
            tmp_path / "b", lambda d: (d / "SKILL.md").write_text("---\nname: x\nno close")
        )
        assert problems and "closed" in problems[0]

    def test_zip_entries_carry_regular_file_mode_bits(self, built):
        out, manifest = built
        name = next(n for n in manifest["artifacts"] if n.startswith("session-recovery-skill"))
        with zipfile.ZipFile(out / name) as archive:
            attr = archive.getinfo("session-recovery/scripts/recover.py").external_attr >> 16
            assert attr == 0o100755
            assert archive.getinfo("session-recovery/SKILL.md").external_attr >> 16 == 0o100644


def test_skill_does_not_pin_allowed_tools():
    """A `${CLAUDE_SKILL_DIR}`-pinned `allowed-tools` made the skill fail to load under Claude Code's
    permission check in the live evaluation (rubric 6/10 vs 10/10). The field is optional and
    experimental in the spec; first use prompts for the script instead."""
    meta, _ = bundle.parse_frontmatter((bundle.SKILL_DIR / "SKILL.md").read_text())
    assert "allowed-tools" not in meta


class TestDistributionContents:
    """What a user receives: only the allow-listed files, no hooks, MCP servers or binaries."""

    def test_every_packaged_file_is_on_the_allow_list(self, built):
        out, _ = built
        allowed_names = {
            "SKILL.md", "LICENSE", "NOTICE", "README.md", "recover.py", "openai.yaml", "output-contract.md",
            "safety-model.md", "troubleshooting.md", "plugin.json", "marketplace.json",
        }  # fmt: skip
        for path in out.rglob("*"):
            if (
                path.is_file()
                and path.suffix != ".zip"
                and path.name not in {"SHA256SUMS", "MANIFEST.json"}
            ):
                assert path.name in allowed_names, path.relative_to(out)

    def test_no_hooks_mcp_servers_binaries_or_privileged_components(self, built):
        out, _ = built
        forbidden = {
            "hooks",
            "bin",
            ".mcp.json",
            ".app.json",
            "agents.md",
            "commands",
            "monitors",
            "settings.json",
        }
        for path in out.rglob("*"):
            assert path.name.lower() not in forbidden - {"agents.md"}, path
            assert path.name != "hooks.json", path
        for manifest in out.rglob("plugin.json"):
            data = json.loads(manifest.read_text())
            for key in (
                "hooks",
                "mcpServers",
                "lspServers",
                "agents",
                "commands",
                "monitors",
                "settings",
                "userConfig",
                "channels",
            ):
                assert key not in data, (manifest, key)

    def test_script_has_no_network_or_write_capabilities(self):
        text = (bundle.SKILL_DIR / "scripts" / "recover.py").read_text()
        for needle in (
            "import socket",
            "urllib",
            "http.client",
            "requests",
            "shutil.rmtree",
            "os.remove",
            "os.unlink",
            ".write_text(",
            "os.system",
            "shell=True",
        ):
            assert needle not in text, needle
        assert not re.search(r"(?<![A-Za-z_.])open\(", text)  # no file handles at all
        # the only writes are to stdout/stderr
        assert text.count("sys.stdout.write(") == 3

    def test_no_host_specific_absolute_paths_in_packaged_text(self, built):
        out, _ = built
        for path in out.rglob("*"):
            if path.is_file() and path.suffix != ".zip":
                text = path.read_text(encoding="utf-8")
                for needle in ("/private/var", "/var/folders", "/private/tmp"):
                    assert needle not in text, (path, needle)

    def test_third_party_content_is_limited_to_the_project_license_texts(self, built):
        """The only licence texts shipped are the repository's own MIT LICENSE and NOTICE."""
        out, _ = built
        for path in out.rglob("LICENSE"):
            assert path.read_bytes() == (ROOT / "LICENSE").read_bytes()
        for path in out.rglob("NOTICE"):
            assert path.read_bytes() == (ROOT / "NOTICE").read_bytes()
