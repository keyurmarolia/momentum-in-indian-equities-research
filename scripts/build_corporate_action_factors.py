"""Convert the single cached NSE corporate-action response into share factors."""

from __future__ import annotations

import json

import pandas as pd

from momentum_india.config import PROJECT_ROOT
from momentum_india.corporate_actions import (
    apply_verified_share_action_overrides,
    build_share_action_table,
)


def main() -> None:
    raw = PROJECT_ROOT / "data" / "raw" / "reference" / "nse_corporate_actions_2000_2026.json"
    if not raw.exists():
        raise RuntimeError("The cached official NSE corporate-action response is missing")
    records = pd.DataFrame(json.loads(raw.read_text(encoding="utf-8")))
    actions = build_share_action_table(records)
    override_path = PROJECT_ROOT / "data" / "reference" / "share_action_overrides.csv"
    if override_path.exists():
        overrides = pd.read_csv(override_path, parse_dates=["ex_date"])
        actions = apply_verified_share_action_overrides(actions, overrides)
    target = PROJECT_ROOT / "data" / "reference" / "nse_share_action_factors.csv"
    actions.to_csv(target, index=False)
    audit = {
        "official_records": len(records),
        "ordinary_equity_records": int(records["series"].astype(str).str.strip().eq("EQ").sum()),
        "parsed_split_or_bonus_events": len(actions),
        "first_event": str(actions["ex_date"].min().date()),
        "last_event": str(actions["ex_date"].max().date()),
    }
    (PROJECT_ROOT / "data" / "interim" / "nse_corporate_action_audit.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )
    print(audit)


if __name__ == "__main__":
    main()
