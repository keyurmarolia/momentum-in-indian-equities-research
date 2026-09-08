from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or PROJECT_ROOT / "config" / "config.yaml"
    with config_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)
