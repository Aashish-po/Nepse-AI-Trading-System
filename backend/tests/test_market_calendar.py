"""Tests for the Calendarific-backed market calendar (NEPSE trading days)."""

import datetime as dt

import requests
from app.services.market_calendar import MarketCalendar

# January 2024 reference weekdays:
#   Mon 1, Tue 2 ... Sat 6, Sun 7, Tue 9, Thu 11
SATURDAY = dt.date(2024, 1, 6)
SUNDAY = dt.date(2024, 1, 7)
TUESDAY = dt.date(2024, 1, 9)
THURSDAY = dt.date(2024, 1, 11)


def _holiday_entry(iso: str, types: list[str] | None = None) -> dict:
    return {
        "name": f"Holiday {iso}",
        "date": {
            "iso": iso,
            "datetime": {"year": 2024, "month": int(iso[5:7]), "day": int(iso[8:10])},
        },
        "type": types if types is not None else ["National holiday"],
    }


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeHTTP:
    """Stub matching the subset of the ``requests`` API used by the service."""

    def __init__(self, holidays: list[dict] | None = None, error: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self._payload = {"response": {"holidays": holidays or []}}
        self._error = error

    def get(self, url: str, params: dict | None = None, timeout: float | None = None):
        self.calls.append(params or {})
        if self._error is not None:
            raise self._error
        return _FakeResponse(self._payload)


def _calendar(http: _FakeHTTP, **kwargs) -> MarketCalendar:
    kwargs.setdefault("api_key", "test-key")
    return MarketCalendar(http=http, **kwargs)


def test_saturday_is_closed_without_api_call() -> None:
    http = _FakeHTTP()
    cal = _calendar(http)
    assert cal.is_market_open(SATURDAY) is False
    # Weekend short-circuits before any network call.
    assert http.calls == []


def test_sunday_is_a_trading_day() -> None:
    cal = _calendar(_FakeHTTP(holidays=[]))
    assert cal.is_market_open(SUNDAY) is True


def test_holiday_closes_the_market() -> None:
    http = _FakeHTTP(holidays=[_holiday_entry("2024-01-09")])
    cal = _calendar(http)
    assert cal.is_holiday(TUESDAY) is True
    assert cal.is_market_open(TUESDAY) is False


def test_non_holiday_weekday_is_open() -> None:
    http = _FakeHTTP(holidays=[_holiday_entry("2024-01-09")])
    cal = _calendar(http)
    assert cal.is_market_open(THURSDAY) is True


def test_holiday_dates_cached_one_call_per_year() -> None:
    http = _FakeHTTP(holidays=[_holiday_entry("2024-01-09")])
    cal = _calendar(http)

    cal.is_holiday(TUESDAY)
    cal.is_holiday(THURSDAY)
    cal.is_market_open(SUNDAY)

    assert len(http.calls) == 1
    assert http.calls[0]["country"] == "NP"
    assert http.calls[0]["year"] == 2024


def test_api_failure_falls_back_to_weekend_logic() -> None:
    http = _FakeHTTP(error=requests.ConnectionError("boom"))
    cal = _calendar(http)

    # Holiday cannot be confirmed -> treated as non-holiday (fail-open).
    assert cal.is_holiday(TUESDAY) is False
    # Weekday stays open, Saturday stays closed.
    assert cal.is_market_open(TUESDAY) is True
    assert cal.is_market_open(SATURDAY) is False


def test_api_failure_is_not_cached() -> None:
    http = _FakeHTTP(error=requests.Timeout("slow"))
    cal = _calendar(http)
    cal.is_holiday(TUESDAY)
    cal.is_holiday(THURSDAY)
    # Each lookup retries because failures are never cached.
    assert len(http.calls) == 2


def test_missing_api_key_skips_network_and_fails_open() -> None:
    http = _FakeHTTP(holidays=[_holiday_entry("2024-01-09")])
    cal = MarketCalendar(api_key="", http=http)
    assert cal.is_holiday(TUESDAY) is False
    assert http.calls == []


def test_national_only_filters_observances() -> None:
    http = _FakeHTTP(
        holidays=[
            _holiday_entry("2024-01-09", types=["National holiday"]),
            _holiday_entry("2024-01-11", types=["Observance"]),
        ]
    )
    cal = _calendar(http, national_only=True)
    assert cal.is_holiday(TUESDAY) is True  # national holiday
    assert cal.is_holiday(THURSDAY) is False  # observance filtered out


def test_accepts_datetime_input() -> None:
    http = _FakeHTTP(holidays=[_holiday_entry("2024-01-09")])
    cal = _calendar(http)
    assert cal.is_holiday(dt.datetime(2024, 1, 9, 14, 30)) is True
    assert cal.is_market_open(dt.datetime(2024, 1, 6, 10, 0)) is False  # Saturday


def test_clear_cache_forces_refetch() -> None:
    http = _FakeHTTP(holidays=[_holiday_entry("2024-01-09")])
    cal = _calendar(http)
    cal.is_holiday(TUESDAY)
    cal.clear_cache()
    cal.is_holiday(TUESDAY)
    assert len(http.calls) == 2
