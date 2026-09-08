from __future__ import annotations

import pandas as pd

from .config import PROJECT_ROOT

RULE_DIR = PROJECT_ROOT / "data" / "tax_rules"


def load_rule_table(name: str) -> pd.DataFrame:
    """Load a dated rule table and normalize its effective dates."""
    path = RULE_DIR / f"{name}.csv"
    frame = pd.read_csv(path)
    for column in ("effective_from", "effective_to", "acquired_from", "acquired_to"):
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return frame


def active_rules(frame: pd.DataFrame, date: str | pd.Timestamp) -> pd.DataFrame:
    when = pd.Timestamp(date)
    return frame.loc[
        frame["effective_from"].le(when)
        & (frame["effective_to"].isna() | frame["effective_to"].ge(when))
    ].copy()


def assert_rule_coverage(frame: pd.DataFrame, start: str, end: str) -> None:
    """Raise if one or more calendar days have no active rule."""
    days = pd.date_range(start, end, freq="D")
    covered = pd.Series(False, index=days)
    for row in frame.itertuples():
        left = max(pd.Timestamp(row.effective_from), days.min())
        right = min(
            pd.Timestamp(row.effective_to) if pd.notna(row.effective_to) else days.max(),
            days.max(),
        )
        covered.loc[left:right] = True
    missing = covered.index[~covered]
    if len(missing):
        raise ValueError(
            f"Rule table has {len(missing)} uncovered days; first is {missing[0].date()}"
        )
