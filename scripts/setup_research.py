"""Download and verify the pinned research bundle; no broker access required."""

import argparse
import hashlib
import json
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_member(member, expected):
    name = PurePosixPath(member.name)
    return (member.isfile() and not name.is_absolute() and ".." not in name.parts
            and "\\" not in member.name and member.name in expected
            and member.size == expected[member.name]["bytes"])


def install_bundle(archive_path, manifest, root):
    if archive_path.stat().st_size != manifest["bytes"] or sha256(archive_path) != manifest["sha256"]:
        raise ValueError("Research archive checksum or size mismatch")
    expected = manifest["files"]
    # Validate the entire archive and every existing destination before writing.
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        if len(members) != len(expected) or {m.name for m in members} != set(expected):
            raise ValueError("Research archive inventory mismatch")
        for member in members:
            target = root / member.name
            if not safe_member(member, expected):
                raise ValueError(f"Unsafe archive member: {member.name}")
            if not target.resolve().is_relative_to(root.resolve()) or target.is_symlink():
                raise ValueError(f"Unsafe destination: {member.name}")
            if target.exists() and sha256(target) != expected[member.name]["sha256"]:
                raise ValueError(f"Existing file differs; preserved without overwriting: {member.name}")
        with tempfile.TemporaryDirectory(prefix="momentum-unpack-") as temporary:
            staging = Path(temporary)
            for member in members:
                target = staging / member.name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                if sha256(target) != expected[member.name]["sha256"]:
                    raise ValueError(f"File checksum mismatch: {member.name}")
            for member in members:
                target = root / member.name
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(staging / member.name, target)
    public = root / "dashboard/public"
    dist = root / "dashboard/dist"
    if (public / "data").exists():
        shutil.copytree(public / "data", dist / "data", dirs_exist_ok=True)
    if (public / "plotly.min.js").exists():
        shutil.copy2(public / "plotly.min.js", dist / "plotly.min.js")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, help="Use a previously downloaded release archive")
    parser.add_argument("--verify", action="store_true", help="Check installed files without downloading")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "config/research_bundle.json").read_text())
    if args.verify:
        failures = [name for name, info in manifest["files"].items()
                    if not (ROOT / name).is_file() or sha256(ROOT / name) != info["sha256"]]
        if failures:
            raise SystemExit(f"Missing or changed bundle files: {len(failures)}; first: {failures[0]}")
        print(f"Verified {len(manifest['files'])} research files.")
        return
    with tempfile.TemporaryDirectory(prefix="momentum-download-") as temporary:
        path = args.archive
        if path is None:
            path = Path(temporary) / "research-data.tar.gz"
            print(f"Downloading pinned research bundle ({manifest['bytes'] / 1e6:.0f} MB).", flush=True)
            request = urllib.request.Request(manifest["url"], headers={"User-Agent": "momentum-research-setup"})
            with urllib.request.urlopen(request, timeout=120) as response, path.open("wb") as output:
                shutil.copyfileobj(response, output)
        install_bundle(path, manifest, ROOT)
    print("Research inputs and dashboard installed. No broker credentials or requests used.")


if __name__ == "__main__":
    main()
