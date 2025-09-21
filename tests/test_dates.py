from __future__ import annotations

import datetime as dt

import pytest

from whatsnew.utils.dates import RangeMode, RangeResolutionError, resolve_range_request


CONFIG = {"default_range": "since-tag", "date_window_days": 7}


def test_mutually_exclusive_range_flags():
    args = {
        "tag": "v1.0.0",
        "from_sha": None,
        "to_sha": None,
        "since_date": None,
        "until_date": None,
        "window": "7d",
    }
    with pytest.raises(RangeResolutionError) as exc:
        resolve_range_request(args, CONFIG)
    assert "mutually exclusive" in str(exc.value)


def test_window_range_parsing():
    args = {
        "tag": None,
        "from_sha": None,
        "to_sha": None,
        "since_date": None,
        "until_date": None,
        "window": "14d",
    }
    request = resolve_range_request(args, CONFIG)
    assert request.mode is RangeMode.WINDOW
    assert request.window.days == 14


def test_date_range_defaults_to_fallback():
    now = dt.datetime(2024, 1, 10, tzinfo=dt.timezone.utc)
    args = {
        "tag": None,
        "from_sha": None,
        "to_sha": None,
        "since_date": "2024-01-09",
        "until_date": None,
        "window": None,
    }
    request = resolve_range_request(args, CONFIG, now=now)
    assert request.mode is RangeMode.DATE_RANGE
    assert request.since.date() == dt.date(2024, 1, 9)


def test_invalid_date_range_order():
    args = {
        "tag": None,
        "from_sha": None,
        "to_sha": None,
        "since_date": "2024-02-01",
        "until_date": "2024-01-01",
        "window": None,
    }
    with pytest.raises(RangeResolutionError) as exc:
        resolve_range_request(args, CONFIG)
    assert "earlier" in str(exc.value)
