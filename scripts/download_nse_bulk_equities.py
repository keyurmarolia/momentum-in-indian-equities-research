"""Cache and normalize official NSE daily equity bhavcopies.

One exchange-wide file supplies every security for a trading day.  The script
is resumable, records genuine 404/non-trading days, writes files atomically,
and stops immediately if the archive signals a rate limit.  It never calls the
FYERS history API.
"""

from __future__ import annotations

import argparse
import io
import json
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests
import yaml

from momentum_india.config import PROJECT_ROOT

RAW_ROOT = PROJECT_ROOT / "data" / "raw" / "nse_daily_bhavcopy"
YEAR_ROOT = PROJECT_ROOT / "data" / "interim" / "nse_mainboard_equity_by_year"
MANIFEST_PATH = PROJECT_ROOT / "data" / "interim" / "nse_bhavcopy_manifest.csv"
LEGACY_TEMPLATE = (
    "https://nsearchives.nseindia.com/content/historical/EQUITIES/"
    "{year}/{month}/cm{day}bhav.csv.zip"
)
UDIFF_TEMPLATE = (
    "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{compact}_F_0000.csv.zip"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "application/zip,application/octet-stream,*/*",
}


def archive_url(day: pd.Timestamp, legacy_last_date: pd.Timestamp) -> tuple[str, str]:
    if day <= legacy_last_date:
        return (
            LEGACY_TEMPLATE.format(
                year=day.strftime("%Y"),
                month=day.strftime("%b").upper(),
                day=day.strftime("%d%b%Y").upper(),
            ),
            "legacy",
        )
    return UDIFF_TEMPLATE.format(compact=day.strftime("%Y%m%d")), "udiff"


def read_single_csv(archive: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        names = [name for name in bundle.namelist() if name.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"Expected one CSV in archive, found {len(names)}")
        return pd.read_csv(bundle.open(names[0]), low_memory=False, skipinitialspace=True)


def normalize_bhavcopy(archive: bytes, source_format: str) -> pd.DataFrame:
    frame = read_single_csv(archive)
    frame.columns = frame.columns.astype(str).str.strip()
    if source_format == "legacy":
        required = {
            "SYMBOL",
            "SERIES",
            "OPEN",
            "HIGH",
            "LOW",
            "CLOSE",
            "TOTTRDQTY",
            "TOTTRDVAL",
            "TIMESTAMP",
        }
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"Legacy bhavcopy missing columns: {sorted(missing)}")
        frame = frame.loc[frame["SERIES"].astype(str).str.strip().eq("EQ")].copy()
        output = pd.DataFrame(
            {
                # Legacy archives use both 13-Jul-20 and 13-JUL-2020. Pandas'
                # mixed parser handles both explicitly while dayfirst avoids
                # locale ambiguity.
                "date": pd.to_datetime(
                    frame["TIMESTAMP"], format="mixed", dayfirst=True, errors="coerce"
                ),
                "nse_symbol": frame["SYMBOL"].astype(str).str.strip(),
                "series": "EQ",
                # ISIN was added to the legacy bhavcopy after the beginning of
                # this study.  Symbol + EQ series remains the historical key.
                "isin": (
                    frame["ISIN"].astype(str).str.strip()
                    if "ISIN" in frame.columns
                    else pd.Series(pd.NA, index=frame.index, dtype="string")
                ),
                "open": pd.to_numeric(frame["OPEN"], errors="coerce"),
                "high": pd.to_numeric(frame["HIGH"], errors="coerce"),
                "low": pd.to_numeric(frame["LOW"], errors="coerce"),
                "close": pd.to_numeric(frame["CLOSE"], errors="coerce"),
                "volume": pd.to_numeric(frame["TOTTRDQTY"], errors="coerce"),
                "official_traded_value_inr": pd.to_numeric(frame["TOTTRDVAL"], errors="coerce"),
            }
        )
    elif source_format == "udiff":
        required = {
            "TradDt",
            "TckrSymb",
            "SctySrs",
            "ISIN",
            "OpnPric",
            "HghPric",
            "LwPric",
            "ClsPric",
            "TtlTradgVol",
            "TtlTrfVal",
        }
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"UDiFF bhavcopy missing columns: {sorted(missing)}")
        frame = frame.loc[frame["SctySrs"].astype(str).str.strip().eq("EQ")].copy()
        output = pd.DataFrame(
            {
                "date": pd.to_datetime(frame["TradDt"], errors="coerce"),
                "nse_symbol": frame["TckrSymb"].astype(str).str.strip(),
                "series": "EQ",
                "isin": frame["ISIN"].astype(str).str.strip(),
                "open": pd.to_numeric(frame["OpnPric"], errors="coerce"),
                "high": pd.to_numeric(frame["HghPric"], errors="coerce"),
                "low": pd.to_numeric(frame["LwPric"], errors="coerce"),
                "close": pd.to_numeric(frame["ClsPric"], errors="coerce"),
                "volume": pd.to_numeric(frame["TtlTradgVol"], errors="coerce"),
                "official_traded_value_inr": pd.to_numeric(frame["TtlTrfVal"], errors="coerce"),
            }
        )
    else:
        raise ValueError(f"Unknown bhavcopy format: {source_format}")

    output["date"] = output["date"].dt.normalize()
    output["symbol"] = "NSE:" + output["nse_symbol"] + "-EQ"
    output = output.dropna(subset=["date", "nse_symbol", "open", "high", "low", "close", "volume"])
    valid_isin = output["isin"].isna() | output["isin"].str.startswith("INE", na=False)
    output = output.loc[
        valid_isin
        & (output[["open", "high", "low", "close"]] > 0).all(axis=1)
        & output["volume"].ge(0)
    ]
    columns = [
        "date",
        "symbol",
        "nse_symbol",
        "series",
        "isin",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "official_traded_value_inr",
    ]
    return output[columns].drop_duplicates(["date", "symbol"], keep="last").sort_values("symbol")


def validate_archive(content: bytes, source_format: str) -> pd.DataFrame:
    if not content.startswith(b"PK"):
        raise ValueError("Response is not a ZIP archive")
    normalized = normalize_bhavcopy(content, source_format)
    if normalized.empty:
        raise ValueError("Archive contains no main-board EQ securities")
    return normalized


def download_one(
    session: requests.Session,
    day: pd.Timestamp,
    legacy_last_date: pd.Timestamp,
    timeout: float,
    maximum_attempts: int,
) -> dict:
    url, source_format = archive_url(day, legacy_last_date)
    year_dir = RAW_ROOT / day.strftime("%Y")
    year_dir.mkdir(parents=True, exist_ok=True)
    target = year_dir / f"{day.date()}.zip"
    absent = year_dir / f"{day.date()}.missing.json"
    if target.exists():
        try:
            frame = validate_archive(target.read_bytes(), source_format)
            return {
                "date": day.date(),
                "status": "cached",
                "format": source_format,
                "rows": len(frame),
                "url": url,
                "path": str(target),
            }
        except Exception:
            target.rename(target.with_suffix(".invalid.zip"))
    if absent.exists():
        return {
            "date": day.date(),
            "status": "known_non_trading_day",
            "format": source_format,
            "rows": 0,
            "url": url,
            "path": str(absent),
        }

    last_error = "unknown"
    for attempt in range(1, maximum_attempts + 1):
        try:
            response = session.get(url, headers=HEADERS, timeout=timeout)
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < maximum_attempts:
                time.sleep(1.0)
            continue
        if response.status_code == 404:
            payload = {"date": str(day.date()), "status": 404, "url": url}
            temporary = absent.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            temporary.replace(absent)
            return {
                "date": day.date(),
                "status": "not_found",
                "format": source_format,
                "rows": 0,
                "url": url,
                "path": str(absent),
            }
        if response.status_code in {403, 429}:
            raise RuntimeError(
                f"Archive returned HTTP {response.status_code} on {day.date()}; "
                "stopped immediately without repeated requests"
            )
        if response.status_code != 200:
            last_error = f"HTTP {response.status_code}"
            if response.status_code >= 500 and attempt < maximum_attempts:
                time.sleep(1.0)
                continue
            break
        try:
            frame = validate_archive(response.content, source_format)
        except Exception as exc:
            last_error = f"invalid archive: {exc}"
            break
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(response.content)
        temporary.replace(target)
        return {
            "date": day.date(),
            "status": "downloaded",
            "format": source_format,
            "rows": len(frame),
            "url": url,
            "path": str(target),
        }
    return {
        "date": day.date(),
        "status": "failed",
        "format": source_format,
        "rows": 0,
        "url": url,
        "path": "",
        "error": last_error,
    }


def build_year(year: int, legacy_last_date: pd.Timestamp) -> tuple[int, Path | None]:
    frames: list[pd.DataFrame] = []
    year_dir = RAW_ROOT / str(year)
    if not year_dir.exists():
        return 0, None
    for path in sorted(year_dir.glob("*.zip")):
        day = pd.Timestamp(path.stem)
        _, source_format = archive_url(day, legacy_last_date)
        frames.append(normalize_bhavcopy(path.read_bytes(), source_format))
    if not frames:
        return 0, None
    YEAR_ROOT.mkdir(parents=True, exist_ok=True)
    output = pd.concat(frames, ignore_index=True).sort_values(["date", "symbol"])
    if output.duplicated(["date", "symbol"]).any():
        raise ValueError(f"Duplicate date-symbol rows in normalized year {year}")
    target = YEAR_ROOT / f"nse_mainboard_equity_{year}.parquet"
    temporary = target.with_suffix(".tmp.parquet")
    output.to_parquet(temporary, index=False)
    temporary.replace(target)
    return len(output), target


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", help="Override start date (YYYY-MM-DD)")
    parser.add_argument("--end", help="Override end date (YYYY-MM-DD)")
    parser.add_argument("--no-normalize", action="store_true", help="Only cache ZIP files")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = yaml.safe_load(
        (PROJECT_ROOT / "config" / "data_acquisition.yaml").read_text(encoding="utf-8")
    )["nse_bulk_history"]
    start = pd.Timestamp(args.start or settings["start"])
    end = pd.Timestamp(args.end or settings["end"])
    legacy_last_date = pd.Timestamp(settings["legacy_last_date"])
    interval = float(settings["request_interval_seconds"])
    timeout = float(settings["request_timeout_seconds"])
    attempts = int(settings["maximum_attempts"])
    weekdays = pd.date_range(start, end, freq="B")
    print(
        f"Preflight: {len(weekdays):,} weekday archive dates from {start.date()} to {end.date()}; "
        "cache and 404 markers prevent repeat requests"
    )

    session = requests.Session()
    records: list[dict] = []
    network_results = {"downloaded", "not_found", "failed"}
    for number, day in enumerate(weekdays, start=1):
        record = download_one(session, day, legacy_last_date, timeout, attempts)
        records.append(record)
        if record["status"] in network_results:
            time.sleep(interval)
        if number % 100 == 0 or number == len(weekdays):
            counts = pd.Series([row["status"] for row in records]).value_counts().to_dict()
            print(f"Archive dates {number:,}/{len(weekdays):,}: {counts}", flush=True)

    manifest = pd.DataFrame(records).sort_values("date")
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(MANIFEST_PATH, index=False)
    failures = manifest.loc[manifest["status"].eq("failed")]
    if not failures.empty:
        raise RuntimeError(f"{len(failures)} archive dates failed; see {MANIFEST_PATH}")

    if not args.no_normalize:
        total = 0
        for year in range(start.year, end.year + 1):
            rows, target = build_year(year, legacy_last_date)
            total += rows
            if target:
                print(f"Normalized {year}: {rows:,} rows -> {target.name}", flush=True)
        print(f"Complete: {total:,} main-board EQ date-symbol rows")


if __name__ == "__main__":
    main()
