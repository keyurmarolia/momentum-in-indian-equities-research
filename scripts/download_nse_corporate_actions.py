"""Make at most one market-wide NSE corporate-action request and cache it."""

from __future__ import annotations

import json

import requests
import yaml

from momentum_india.config import PROJECT_ROOT

TARGET = PROJECT_ROOT / "data" / "raw" / "reference" / "nse_corporate_actions_2000_2026.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-actions",
}


def main() -> None:
    if TARGET.exists():
        records = json.loads(TARGET.read_text(encoding="utf-8"))
        if not isinstance(records, list) or not records:
            raise RuntimeError("Cached corporate-action response is invalid")
        print(f"Cached: {len(records):,} official corporate-action records; no request made")
        return
    settings = yaml.safe_load(
        (PROJECT_ROOT / "config" / "data_acquisition.yaml").read_text(encoding="utf-8")
    )["nse_bulk_history"]
    start = str(settings["start"])
    end = str(settings["end"])
    from_date = "-".join(reversed(start.split("-")))
    to_date = "-".join(reversed(end.split("-")))
    session = requests.Session()
    bootstrap = session.get(
        "https://www.nseindia.com/companies-listing/corporate-filings-actions",
        headers=HEADERS,
        timeout=30,
    )
    bootstrap.raise_for_status()
    response = session.get(
        "https://www.nseindia.com/api/corporates-corporateActions",
        params={"index": "equities", "from_date": from_date, "to_date": to_date},
        headers=HEADERS,
        timeout=60,
    )
    if response.status_code in {403, 429}:
        raise RuntimeError(f"NSE returned {response.status_code}; stopped without retry")
    response.raise_for_status()
    records = response.json()
    if not isinstance(records, list) or not records:
        raise RuntimeError("NSE corporate-action response was empty or invalid")
    required = {"symbol", "series", "subject", "exDate"}
    if not required.issubset(records[0]):
        raise RuntimeError("Unexpected NSE corporate-action schema")
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    temporary = TARGET.with_suffix(".tmp")
    temporary.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    temporary.replace(TARGET)
    print(f"Downloaded once and cached: {len(records):,} official records")


if __name__ == "__main__":
    main()
