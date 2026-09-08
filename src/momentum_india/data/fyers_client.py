from __future__ import annotations

import hashlib
import json
import time
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path


class RequestBudgetExceeded(RuntimeError):
    pass


@dataclass
class RequestBudget:
    """Conservative local guard, intentionally below published platform ceilings."""

    max_per_second: int = 5
    max_per_minute: int = 60
    max_per_day: int = 5000
    minimum_interval_seconds: float = 0.25
    ledger_path: Path | None = None
    calls_today: int = 0
    _last_call_at: float = 0.0
    _second_calls: deque[float] = field(default_factory=deque)
    _minute_calls: deque[float] = field(default_factory=deque)

    def __post_init__(self) -> None:
        if self.ledger_path and self.ledger_path.exists():
            ledger = json.loads(self.ledger_path.read_text())
            if ledger.get("date") == date.today().isoformat():
                self.calls_today = int(ledger.get("calls", 0))

    def _persist(self) -> None:
        if not self.ledger_path:
            return
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.ledger_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"date": date.today().isoformat(), "calls": self.calls_today}),
            encoding="utf-8",
        )
        temporary.replace(self.ledger_path)

    def before_call(self) -> None:
        if self.calls_today >= self.max_per_day:
            raise RequestBudgetExceeded("Local daily request budget exhausted; stopping safely")
        now = time.monotonic()
        while self._second_calls and now - self._second_calls[0] >= 1:
            self._second_calls.popleft()
        while self._minute_calls and now - self._minute_calls[0] >= 60:
            self._minute_calls.popleft()
        if len(self._second_calls) >= self.max_per_second:
            time.sleep(max(0.0, 1.0 - (now - self._second_calls[0])))
        now = time.monotonic()
        while self._minute_calls and now - self._minute_calls[0] >= 60:
            self._minute_calls.popleft()
        if len(self._minute_calls) >= self.max_per_minute:
            raise RequestBudgetExceeded("Local per-minute request budget reached; pause and resume later")
        elapsed = time.monotonic() - self._last_call_at
        if elapsed < self.minimum_interval_seconds:
            time.sleep(self.minimum_interval_seconds - elapsed)
        self.calls_today += 1
        self._last_call_at = time.monotonic()
        self._second_calls.append(self._last_call_at)
        self._minute_calls.append(self._last_call_at)
        self._persist()


class JsonFileCache:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, payload: dict) -> Path:
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return self.root / f"{digest}.json"

    def get(self, payload: dict) -> dict | None:
        path = self._path(payload)
        return json.loads(path.read_text()) if path.exists() else None

    def contains(self, payload: dict) -> bool:
        return self._path(payload).exists()

    def put(self, payload: dict, response: dict) -> None:
        path = self._path(payload)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(response), encoding="utf-8")
        temporary.replace(path)


def daily_history_windows(start: date, end: date, maximum_days: int = 366) -> Iterator[tuple[date, date]]:
    """Split requests into bounded inclusive windows; FYERS support states 366 daily bars/request."""
    cursor = start
    while cursor <= end:
        window_end = min(end, cursor + timedelta(days=maximum_days - 1))
        yield cursor, window_end
        cursor = window_end + timedelta(days=1)


def plan_daily_history_requests(
    symbols: list[str],
    start: date,
    end: date,
    cache_dir: Path,
) -> dict[str, object]:
    """Create a zero-network preflight plan and exclude already cached windows."""
    cache = JsonFileCache(cache_dir)
    requests: list[dict] = []
    cached = 0
    for symbol in symbols:
        for left, right in daily_history_windows(start, end):
            payload = {
                "symbol": symbol,
                "resolution": "D",
                "date_format": "1",
                "range_from": left.isoformat(),
                "range_to": right.isoformat(),
                "cont_flag": "0",
            }
            if cache.contains(payload):
                cached += 1
            else:
                requests.append(payload)
    return {
        "symbols": len(symbols),
        "cached_windows": cached,
        "missing_windows": len(requests),
        "requests": requests,
    }


class FyersHistoryClient:
    """A read-only adapter around an injected FYERS history callable.

    No order methods exist. Completed responses are cached, 429 stops the run,
    and transient server errors use bounded exponential backoff.
    """

    def __init__(
        self,
        history_call: Callable[[dict], dict],
        cache_dir: Path,
        budget: RequestBudget | None = None,
        max_retries: int = 3,
    ) -> None:
        self.history_call = history_call
        self.cache = JsonFileCache(cache_dir)
        self.budget = budget or RequestBudget(ledger_path=cache_dir / "request_ledger.json")
        self.max_retries = max_retries

    def history(self, payload: dict) -> dict:
        cached = self.cache.get(payload)
        if cached is not None:
            return cached
        for attempt in range(self.max_retries + 1):
            self.budget.before_call()
            response = self.history_call(payload)
            code = int(response.get("code", 200))
            if code == 429:
                raise RequestBudgetExceeded("FYERS returned 429; stopped without retrying")
            # A definitive no-data response is a useful depth-probe result and
            # must be cached so the same empty window is never requested again.
            if response.get("s") in {"ok", "no_data"} or code == 200:
                self.cache.put(payload, response)
                return response
            if 500 <= code < 600 and attempt < self.max_retries:
                time.sleep(2**attempt)
                continue
            raise RuntimeError(f"FYERS history request failed with code {code}: {response.get('message', '')}")
        raise AssertionError("Unreachable")
