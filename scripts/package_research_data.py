"""Create the versioned research-input and dashboard release asset."""

import hashlib
import json
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = (
    "data/interim",
    "data/processed", "data/raw/nse_daily_bhavcopy", "data/raw/nse_delisted_history",
    "data/raw/reference", "data/raw/absl_liquid_nav", "data/raw/hdfc_liquid_nav",
    "reports/tables", "dashboard/public/data", "dashboard/dist/assets",
)
EXTRA = ("dashboard/public/plotly.min.js", "dashboard/dist/index.html",
         "dashboard/dist/dashboard-status.json")


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    files = sorted({p for folder in FOLDERS for p in (ROOT / folder).rglob("*")
                    if p.is_file() and not p.name.startswith(".")}
                   | {ROOT / name for name in EXTRA})
    if any(p.is_symlink() for p in files):
        raise ValueError("Release files must not be symbolic links")
    destination = ROOT / "tmp/research-data-v1.tar.gz"
    inventory = {str(p.relative_to(ROOT)): {"bytes": p.stat().st_size, "sha256": sha256(p)}
                 for p in files}
    with tarfile.open(destination, "w:gz", compresslevel=3) as archive:
        for path in files:
            archive.add(path, arcname=str(path.relative_to(ROOT)), recursive=False)
    manifest = {
        "schema": 1,
        "url": "https://github.com/keyurmarolia/momentum-in-indian-equities-research/releases/download/research-data-v1/research-data-v1.tar.gz",
        "sha256": sha256(destination), "bytes": destination.stat().st_size,
        "files": inventory,
    }
    (ROOT / "config/research_bundle.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Packaged {len(files)} files, {destination.stat().st_size / 1e6:.1f} MB", flush=True)


if __name__ == "__main__":
    main()
