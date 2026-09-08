"""Cache and build the selected continuous liquid-fund Growth NAV reference."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import requests

from momentum_india.config import PROJECT_ROOT

SCHEMES = {
    "regular": {
        "code": "100047",
        "expected_name": "Aditya Birla Sun Life Liquid Fund - Regular Plan - GROWTH",
    },
    "direct": {
        "code": "119568",
        "expected_name": "Aditya Birla Sun Life Liquid Fund - Direct Plan - GROWTH",
    },
}
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "absl_liquid_nav"
OUTPUT = PROJECT_ROOT / "data" / "processed" / "absl_liquid_fund_continuous.csv"


def load_or_download(plan: str, details: dict[str, str]) -> pd.DataFrame:
    """Use one immutable cache file per scheme; never re-hit a cached URL."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    target = RAW_DIR / f"{details['code']}.json"
    if target.exists():
        payload = json.loads(target.read_text(encoding="utf-8"))
    else:
        response = requests.get(f"https://api.mfapi.in/mf/{details['code']}", timeout=60)
        response.raise_for_status()
        payload = response.json()
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(target)
    if payload.get("meta", {}).get("scheme_name") != details["expected_name"]:
        raise ValueError(f"Scheme identity mismatch for AMFI {details['code']}")
    frame = pd.DataFrame(payload["data"])
    frame["date"] = pd.to_datetime(frame["date"], format="%d-%m-%Y", errors="raise")
    frame["nav"] = pd.to_numeric(frame["nav"], errors="raise")
    frame = frame.sort_values("date").drop_duplicates("date", keep="last")
    frame["raw_nav"] = frame["nav"]
    raw_ratio = frame["raw_nav"].div(frame["raw_nav"].shift())
    frame["unit_rescale_factor"] = 1.0
    event = raw_ratio.gt(2.0) | raw_ratio.lt(0.5)
    frame.loc[event, "unit_rescale_factor"] = 10.0 ** np.round(np.log10(raw_ratio.loc[event]))
    corrected_ratio = raw_ratio.div(frame["unit_rescale_factor"])
    if corrected_ratio.loc[event].sub(1.0).abs().gt(0.05).any():
        raise ValueError(
            "A large NAV discontinuity is not explained by a power-of-ten unit rescaling"
        )
    frame["nav"] = frame["raw_nav"].iloc[0] * corrected_ratio.fillna(1.0).cumprod()
    frame["plan"] = plan
    frame["amfi_code"] = details["code"]
    return frame


def build_continuous(regular: pd.DataFrame, direct: pd.DataFrame) -> pd.DataFrame:
    transition = direct["date"].min()
    regular_at_transition = regular.set_index("date")["nav"].asof(transition)
    direct_at_transition = direct.set_index("date")["nav"].loc[transition]
    scale = regular_at_transition / direct_at_transition
    pre = regular.loc[regular["date"] < transition, ["date", "nav"]].copy()
    pre["source_plan"] = "regular"
    post = direct.loc[direct["date"] >= transition, ["date", "nav"]].copy()
    post["nav"] *= scale
    post["source_plan"] = "direct_scaled"
    output = pd.concat([pre, post], ignore_index=True).sort_values("date")
    output = output.rename(columns={"nav": "continuous_nav"})
    output["daily_reference_return"] = output["continuous_nav"].pct_change()
    output["transition_date"] = transition.date().isoformat()
    output["direct_scale_factor"] = scale
    return output


def main() -> None:
    plans = {name: load_or_download(name, details) for name, details in SCHEMES.items()}
    events = pd.concat(
        [
            frame.loc[
                frame["unit_rescale_factor"].ne(1.0), ["date", "raw_nav", "unit_rescale_factor"]
            ].assign(plan=name)
            for name, frame in plans.items()
        ],
        ignore_index=True,
    )
    output = build_continuous(plans["regular"], plans["direct"])
    if output["date"].duplicated().any() or (output["continuous_nav"] <= 0).any():
        raise ValueError("NAV validation failed")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(OUTPUT, index=False)
    events.to_csv(
        PROJECT_ROOT / "data" / "processed" / "liquid_nav_unit_rescale_events.csv", index=False
    )
    print(
        f"Complete: {len(output):,} NAV observations from {output.date.min().date()} "
        f"to {output.date.max().date()}; direct-plan transition {output.transition_date.iloc[0]}"
    )


if __name__ == "__main__":
    main()
