from __future__ import annotations

import re

import numpy as np
import pandas as pd

NUMBER = r"(\d+(?:\.\d+)?)"


def share_multiplier_from_subject(subject: str) -> dict[str, float | None]:
    """Parse mechanical share-count changes from an NSE action description.

    Dividends, rights, mergers, and demergers are deliberately not guessed.
    Only explicit bonus ratios and face-value split/consolidation ratios are
    converted to adjustment factors.
    """
    text = re.sub(r"\s+", " ", str(subject or "")).strip().lower()
    bonus_multiplier: float | None = None
    split_multiplier: float | None = None

    non_equity_bonus = (
        any(word in text for word in ("debenture", "preference", "ncrps", "dvr"))
        or re.search(r"bonus\s+deb(?:\b|\d)", text) is not None
    )
    bonus = (
        None
        if non_equity_bonus
        else re.search(rf"(?:bonus|bon)(?:\s+shares|\s+issue)?[^0-9]*{NUMBER}\s*:\s*{NUMBER}", text)
    )
    if bonus:
        new_shares, old_shares = map(float, bonus.groups())
        if new_shares > 0 and old_shares > 0:
            bonus_multiplier = (old_shares + new_shares) / old_shares

    if any(
        marker in text
        for marker in ("split", "spl-", "spl ", "sub-division", "subdivision", "consolidation")
    ):
        compact = re.sub(r"\s+", "", text)
        split = re.search(
            rf"(?:split|spl-|spl|sub-division|subdivision|consolidation).*?"
            rf"(?:rs\.?|re\.?)?{NUMBER}.*?to.*?(?:rs\.?|re\.?)?{NUMBER}",
            compact,
        )
        if split:
            old_face_value, new_face_value = map(float, split.groups())
            if old_face_value > 0 and new_face_value > 0:
                split_multiplier = old_face_value / new_face_value

    factors = [factor for factor in (bonus_multiplier, split_multiplier) if factor is not None]
    total = float(np.prod(factors)) if factors else None
    return {
        "bonus_multiplier": bonus_multiplier,
        "split_multiplier": split_multiplier,
        "share_multiplier": total,
    }


def build_share_action_table(actions: pd.DataFrame) -> pd.DataFrame:
    required = {"symbol", "series", "subject", "exDate"}
    missing = required.difference(actions.columns)
    if missing:
        raise ValueError(f"Corporate-action data missing columns: {sorted(missing)}")
    frame = actions.loc[actions["series"].astype(str).str.strip().eq("EQ")].copy()
    frame["nse_symbol"] = frame["symbol"].astype(str).str.strip()
    frame["ex_date"] = pd.to_datetime(frame["exDate"], format="%d-%b-%Y", errors="coerce")
    parsed = frame["subject"].apply(share_multiplier_from_subject).apply(pd.Series)
    frame = pd.concat([frame, parsed], axis=1)
    frame = frame.dropna(subset=["nse_symbol", "ex_date", "share_multiplier"])
    frame = frame.loc[frame["share_multiplier"].gt(0) & frame["share_multiplier"].ne(1.0)]
    # Revisions can repeat the same action.  Deduplicate the mechanical factor,
    # but retain distinct split and bonus factors occurring on the same date.
    factor_rows: list[dict] = []
    for (symbol, ex_date), group in frame.groupby(["nse_symbol", "ex_date"]):
        unique_bonus = group["bonus_multiplier"].dropna().round(10).drop_duplicates()
        unique_split = group["split_multiplier"].dropna().round(10).drop_duplicates()
        event_factors = pd.concat([unique_bonus, unique_split], ignore_index=True)
        factor_rows.append(
            {
                "nse_symbol": symbol,
                "ex_date": ex_date,
                "share_multiplier": float(event_factors.prod()),
                "source_records": len(group),
                "parsed_unique_factors": len(event_factors),
                "subjects": " | ".join(group["subject"].astype(str).drop_duplicates()),
            }
        )
    return pd.DataFrame(factor_rows).sort_values(["nse_symbol", "ex_date"])


def apply_verified_share_action_overrides(
    share_actions: pd.DataFrame, overrides: pd.DataFrame
) -> pd.DataFrame:
    """Apply separately sourced corrections to ambiguous NSE descriptions.

    Some legacy NSE subjects state that a split occurred without recording the
    face-value ratio.  Such rows cannot be parsed safely from the subject alone.
    The small override table is therefore explicit, source-linked and audited.
    """
    required = {"nse_symbol", "ex_date", "share_multiplier", "source_url"}
    missing = required.difference(overrides.columns)
    if missing:
        raise ValueError(f"Share-action overrides missing columns: {sorted(missing)}")
    corrected = share_actions.copy()
    corrected["ex_date"] = pd.to_datetime(corrected["ex_date"]).dt.normalize()
    override_frame = overrides.copy()
    override_frame["ex_date"] = pd.to_datetime(override_frame["ex_date"]).dt.normalize()
    if override_frame.duplicated(["nse_symbol", "ex_date"]).any():
        raise ValueError("Share-action overrides contain duplicate symbol-date rows")
    for row in override_frame.itertuples(index=False):
        mask = corrected["nse_symbol"].eq(row.nse_symbol) & corrected["ex_date"].eq(row.ex_date)
        if mask.sum() != 1:
            raise ValueError(
                f"Expected one parsed action for {row.nse_symbol} on {row.ex_date.date()}"
            )
        corrected.loc[mask, "share_multiplier"] = float(row.share_multiplier)
        corrected.loc[mask, "subjects"] = (
            corrected.loc[mask, "subjects"].astype(str) + f" | verified override: {row.note}"
        )
    return corrected.sort_values(["nse_symbol", "ex_date"]).reset_index(drop=True)


def adjust_prices_for_share_actions(
    market: pd.DataFrame, share_actions: pd.DataFrame
) -> pd.DataFrame:
    """Back-adjust OHLC for explicit split and bonus share multipliers."""
    required = {"date", "nse_symbol", "open", "high", "low", "close"}
    missing = required.difference(market.columns)
    if missing:
        raise ValueError(f"Market data missing columns: {sorted(missing)}")
    output = market.copy()
    output["date"] = pd.to_datetime(output["date"]).dt.normalize()
    actions = share_actions[["nse_symbol", "ex_date", "share_multiplier"]].copy()
    actions["ex_date"] = pd.to_datetime(actions["ex_date"]).dt.normalize()
    event = actions.groupby(["nse_symbol", "ex_date"])["share_multiplier"].prod()
    key = pd.MultiIndex.from_frame(output[["nse_symbol", "date"]])
    output["share_multiplier_event"] = event.reindex(key).fillna(1.0).to_numpy()
    output = output.sort_values(["nse_symbol", "date"])

    def future_product(values: pd.Series) -> pd.Series:
        inclusive = values.iloc[::-1].cumprod().iloc[::-1]
        return inclusive / values

    output["back_adjustment_factor"] = output.groupby("nse_symbol", sort=False)[
        "share_multiplier_event"
    ].transform(future_product)
    for column in ("open", "high", "low", "close"):
        if f"raw_{column}" not in output:
            output[f"raw_{column}"] = output[column]
        output[column] = output[column] / output["back_adjustment_factor"]
    return output.sort_values(["date", "symbol"]).reset_index(drop=True)
