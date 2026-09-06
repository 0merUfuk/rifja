"""Prepare checksummed Homebrew delivery and install an unpublished local release.

Only the owned local tap is changed; no remote, upload or user application state
is touched. Public formula output requires an explicitly selected release URL.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
TAP = "session-visualizer/local"
OWNER = "session-visualizer-local-installer-v1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wheel_info(wheel: Path) -> str:
    """Reject mismatched names/dependencies before generating executable Ruby."""
    with zipfile.ZipFile(wheel) as archive:
        names = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
        if len(names) != 1:
            raise ValueError("expected_one_wheel_metadata_file")
        meta = BytesParser().parsebytes(archive.read(names[0]))
    version = str(meta["Version"])
    if (
        meta["Name"] != "session-visualizer"
        or not re.fullmatch(r"\d+\.\d+\.\d+(?:rc\d+)?", version)
        or meta.get_all("Requires-Dist")
        or meta["Requires-Python"] != ">=3.14"
        or wheel.name != f"session_visualizer-{version}-py3-none-any.whl"
    ):
        raise ValueError("unsupported_wheel_metadata_or_filename")
    return version


def ruby_string(value: str) -> str:
    # JSON escaping alone does not escape Ruby interpolation in double quotes.
    return json.dumps(value).replace("#", r"\#")


def formula(wheel: Path, url: str) -> str:
    version = wheel_info(wheel)
    parsed = urlsplit(url)
    if parsed.scheme not in {"file", "https"} or parsed.username or parsed.password:
        raise ValueError("formula_url_requires_file_or_https_without_credentials")
    if parsed.scheme == "https" and not parsed.hostname:
        raise ValueError("formula_url_requires_host")
    if Path(parsed.path).name != wheel.name:
        raise ValueError("formula_url_filename_must_match_wheel")
    if parsed.query or parsed.fragment:
        raise ValueError("formula_url_must_be_immutable_without_query_or_fragment")
    result = (ROOT / "packaging/homebrew/session-visualizer.rb.in").read_text()
    for key, value in {
        "URL": url,
        "VERSION": version,
        "SHA256": digest(wheel),
        "WHEEL": wheel.name,
    }.items():
        result = result.replace(f"@@{key}@@", ruby_string(value))
    with zipfile.ZipFile(wheel) as archive:
        name = next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
        license_id = BytesParser().parsebytes(archive.read(name))["License-Expression"]
    if license_id not in {"MIT", "LicenseRef-Private-Local-Use"}:
        raise ValueError("unsupported_wheel_license")
    return result.replace("@@LICENSE@@", '"MIT"' if license_id == "MIT" else ":cannot_represent")


def checked_copy(source: Path, target: Path) -> None:
    if target.is_symlink():
        raise ValueError("refusing_symlink_destination")
    if target.exists():
        if digest(source) != digest(target):
            raise ValueError("immutable_release_bytes_changed_use_new_version")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as output:
        output.write(source.read_bytes())


def run(*args: str) -> str:
    result = subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE)
    if result.stdout:
        print(result.stdout, end="", flush=True)
    return result.stdout.strip()


def install(wheel: Path, reinstall: bool = False) -> None:
    wheel_info(wheel)
    brew = shutil.which("brew")
    if not brew:
        raise ValueError("Homebrew_required_see_https://brew.sh")
    for key in (
        "HOMEBREW_NO_AUTO_UPDATE",
        "HOMEBREW_NO_INSTALL_CLEANUP",
        "HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK",
        "HOMEBREW_NO_INSTALL_UPGRADE",
    ):
        os.environ[key] = "1"
    repository = Path(run(brew, "--repository"))
    tap = repository / "Library/Taps/session-visualizer/homebrew-local"
    marker = tap / ".session-visualizer-owner"
    if tap.exists():
        if tap.is_symlink() or not marker.is_file() or marker.read_text() != OWNER:
            raise ValueError("existing_local_tap_is_not_owned_by_this_installer")
    else:
        run(brew, "tap-new", "--no-git", TAP)
        marker.write_text(OWNER)
    target = tap / "releases" / wheel.name
    checked_copy(wheel, target)
    text = formula(target, target.as_uri())
    path = tap / "Formula/session-visualizer.rb"
    if path.is_symlink():
        raise ValueError("refusing_symlink_formula")
    path.write_text(text)
    # Homebrew handles dependencies, isolation, linking and version comparison.
    package = f"{TAP}/session-visualizer"
    installed = subprocess.run(
        [brew, "list", "--versions", package], capture_output=True, text=True, check=False
    )
    action = "reinstall" if reinstall else "upgrade" if installed.stdout.strip() else "install"
    run(brew, action, package)
    prefix = Path(run(brew, "--prefix", package))
    actual = run(str(prefix / "bin/session-visualizer"), "--version")
    if actual != wheel_info(wheel):
        raise ValueError("installed_version_does_not_match_selected_release")
    print("Ready: session-visualizer --help")


def bundle(wheel: Path, output: Path) -> Path:
    version = wheel_info(wheel)
    project_version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    if version != project_version:
        raise ValueError("installer_bundle_requires_current_project_version")
    output.mkdir(parents=True, exist_ok=True)
    archive_path = output / f"session-visualizer-{version}-homebrew.tar.gz"
    members = {
        "install.sh": ROOT / "install.sh",
        "tools/homebrew.py": ROOT / "tools/homebrew.py",
        "packaging/homebrew/session-visualizer.rb.in": ROOT
        / "packaging/homebrew/session-visualizer.rb.in",
        "pyproject.toml": ROOT / "pyproject.toml",
        "README.md": ROOT / "README.md",
        "NOTICE": ROOT / "NOTICE",
        f"dist/{wheel.name}": wheel,
    }
    for name in ("LICENSE", "CONTRIBUTING.md", "SECURITY.md"):
        if (ROOT / name).is_file():
            members[name] = ROOT / name
    members.update({f"docs/{p.name}": p for p in (ROOT / "docs").glob("*.md")})
    prefix = f"session-visualizer-{version}"
    # Stable bytes across rebuilds; no local absolute paths, user IDs or timestamps.
    with (
        archive_path.open("xb") as raw,
        gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as gz,
        tarfile.open(fileobj=gz, mode="w") as archive,
    ):
        for name, source in sorted(members.items()):
            info = tarfile.TarInfo(f"{prefix}/{name}")
            info.size = source.stat().st_size
            info.mode = 0o755 if name == "install.sh" else 0o644
            with source.open("rb") as stream:
                archive.addfile(info, stream)
    (output / "SHA256SUMS").write_text(f"{digest(archive_path)}  {archive_path.name}\n")
    return archive_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["install", "formula", "bundle"])
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--url", help="Exact already-selected HTTPS wheel release URL")
    parser.add_argument("--reinstall", action="store_true")
    args = parser.parse_args()
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    wheel = (
        args.wheel or ROOT / "dist" / f"session_visualizer-{version}-py3-none-any.whl"
    ).resolve()
    if not wheel.is_file():
        parser.error(
            "Release wheel missing. Use the supplied Homebrew bundle; maintainers run make dist."
        )
    try:
        if args.action == "install":
            install(wheel, args.reinstall)
        elif args.action == "formula":
            if args.output is None or args.url is None:
                parser.error(
                    "formula requires --url and --output; no remote destination is inferred"
                )
            if not args.url.startswith("https://"):
                parser.error("published formula requires an HTTPS release URL")
            with args.output.open("x") as output:
                output.write(formula(wheel, args.url))
        else:
            print(bundle(wheel, args.output or ROOT / "dist/homebrew"))
    except (ValueError, OSError, zipfile.BadZipFile, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Homebrew packaging failed: {exc}\n")


if __name__ == "__main__":
    main()
