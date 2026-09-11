"""Build an exact release set and update the tap from attested hosted assets."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
import tempfile
import tomllib
from pathlib import Path

from homebrew import ROOT, bundle, checked_copy, formula

REPOSITORY = "0merUfuk/rifja"
TAP_REPOSITORY = "0merUfuk/homebrew-rifja"


def run(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


def version() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def check_tag(tag: str) -> str:
    if not re.fullmatch(r"v\d+\.\d+\.\d+(?:rc\d+)?", tag) or tag != f"v{version()}":
        raise ValueError("release_tag_must_match_project_version")
    return tag[1:]


def prepare(output: Path, tag: str | None) -> None:
    v = check_tag(tag) if tag else version()
    if tag:
        if run("git", "rev-parse", f"{tag}^{{commit}}") != run("git", "rev-parse", "HEAD"):
            raise ValueError("release_tag_must_point_to_checkout")
        subprocess.run(["git", "diff", "--exit-code", "HEAD"], check=True)
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    if project["license"] != "MIT":
        raise ValueError("public_release_requires_approved_license")
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("release_output_must_be_empty")
    wheel = ROOT / "dist" / f"rifja-{v}-py3-none-any.whl"
    source = ROOT / "dist" / f"rifja-{v}.tar.gz"
    for artifact in (wheel, source):
        checked_copy(artifact, output / artifact.name)
    bundle(wheel, output)
    url = f"https://github.com/{REPOSITORY}/releases/download/v{v}/{wheel.name}"
    (output / "rifja.rb").write_text(formula(wheel, url))
    files = sorted(p for p in output.iterdir() if p.name != "SHA256SUMS")
    (output / "SHA256SUMS").write_text(
        "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in files)
    )
    notes = (ROOT / "docs/releases.md").read_text()
    section = notes.split(f"## {v}\n", 1)[1].split("\n## ", 1)[0].strip()
    (output / "RELEASE-NOTES.md").write_text(section + "\n")
    print(output)


def publish_tap(tag: str) -> None:
    v = check_tag(tag)
    release = json.loads(run("gh", "api", f"repos/{REPOSITORY}/releases/tags/{tag}"))
    if release["draft"]:
        raise ValueError("release_must_be_public_before_tap_update")
    with tempfile.TemporaryDirectory(prefix="rifja-tap-") as temporary:
        folder = Path(temporary)
        run("gh", "release", "download", tag, "--repo", REPOSITORY, "--dir", temporary)
        expected = {}
        for line in (folder / "SHA256SUMS").read_text().splitlines():
            digest, name = line.split("  ", 1)
            if Path(name).name != name or not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise ValueError("invalid_release_checksum_manifest")
            expected[name] = digest
        wheel = folder / f"rifja-{v}-py3-none-any.whl"
        rb = folder / "rifja.rb"
        for p in (wheel, rb):
            if hashlib.sha256(p.read_bytes()).hexdigest() != expected[p.name]:
                raise ValueError("hosted_release_checksum_mismatch")
            run(
                "gh",
                "attestation",
                "verify",
                str(p),
                "--repo",
                REPOSITORY,
                "--signer-workflow",
                f"{REPOSITORY}/.github/workflows/release.yml",
            )
        url = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{wheel.name}"
        if rb.read_text() != formula(wheel, url):
            raise ValueError("hosted_formula_does_not_match_release_wheel")
        endpoint = f"repos/{TAP_REPOSITORY}/contents/Formula/rifja.rb"
        existing = subprocess.run(
            ["gh", "api", endpoint], capture_output=True, text=True, check=False
        )
        payload = {
            "message": f"Update rifja to {v}",
            "content": base64.b64encode(rb.read_bytes()).decode(),
            "branch": "main",
        }
        if existing.returncode == 0:
            metadata = json.loads(existing.stdout)
            if base64.b64decode(metadata["content"]) == rb.read_bytes():
                print("Tap already matches the attested release")
                return
            payload["sha"] = metadata["sha"]
        elif "HTTP 404" not in existing.stderr:
            raise RuntimeError(existing.stderr)
        request = folder / "tap-update.json"
        request.write_text(json.dumps(payload))
        run("gh", "api", "--method", "PUT", endpoint, "--input", str(request))
        actual = json.loads(run("gh", "api", endpoint))
        if base64.b64decode(actual["content"]) != rb.read_bytes():
            raise ValueError("published_tap_content_mismatch")
        print(f"Verified {TAP_REPOSITORY}: rifja {v}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "publish-tap"])
    parser.add_argument("--tag")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/release")
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.output, args.tag)
    elif args.tag:
        publish_tap(args.tag)
    else:
        parser.error("publish-tap requires --tag")


if __name__ == "__main__":
    main()
