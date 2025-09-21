"""Utilities for resolving commit ranges and date windows."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from enum import Enum
from typing import Mapping

try:  # pragma: no cover - optional dependency in minimal env
    from dateutil import parser as date_parser  # type: ignore
except ImportError:  # pragma: no cover - optional dependency in minimal env
    date_parser = None  # type: ignore


class RangeMode(str, Enum):
    """Enumeration of supported range selection modes."""

    SINCE_LAST_TAG = "since-tag"
    SINCE_SPECIFIC_TAG = "tag"
    SHA_RANGE = "sha"
    DATE_RANGE = "dates"
    WINDOW = "window"


@dataclass(slots=True)
class RangeRequest:
    """Normalized representation of the desired commit range."""

    mode: RangeMode
    tag: str | None = None
    from_sha: str | None = None
    to_sha: str | None = None
    since: dt.datetime | None = None
    until: dt.datetime | None = None
    window: dt.timedelta | None = None
    fallback_window_days: int | None = None


class RangeResolutionError(ValueError):
    """Raised when mutually exclusive range options are mis-specified."""


_WINDOW_RE = re.compile(r"^(?P<value>\d+)(?P<unit>[dhw])$")


def resolve_range_request(
    cli_args: Mapping[str, object],
    config: Mapping[str, object],
    *,
    now: dt.datetime | None = None,
) -> RangeRequest:
    """Determine the effective range request based on CLI args and config."""

    now = now or dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)
    selected_mode: RangeMode | None = None

    tag = _coerce_optional_str(cli_args.get("tag"))
    from_sha = _coerce_optional_str(cli_args.get("from_sha"))
    to_sha = _coerce_optional_str(cli_args.get("to_sha"))
    since_date_raw = _coerce_optional_str(cli_args.get("since_date"))
    until_date_raw = _coerce_optional_str(cli_args.get("until_date"))
    window_raw = _coerce_optional_str(cli_args.get("window"))

    mode_flags = []
    if tag:
        mode_flags.append(RangeMode.SINCE_SPECIFIC_TAG)
    if from_sha or to_sha:
        mode_flags.append(RangeMode.SHA_RANGE)
    if since_date_raw or until_date_raw:
        mode_flags.append(RangeMode.DATE_RANGE)
    if window_raw:
        mode_flags.append(RangeMode.WINDOW)

    if len({m.value for m in mode_flags}) > 1:
        raise RangeResolutionError(
            "Range flags are mutually exclusive. Choose only one of --tag, --from-sha/--to-sha, "
            "--since-date/--until-date, or --window."
        )

    default_range = str(config.get("default_range", RangeMode.SINCE_LAST_TAG.value))
    fallback_days = int(config.get("date_window_days", 7))

    if mode_flags:
        selected_mode = mode_flags[0]
    else:
        selected_mode = RangeMode(default_range) if default_range in RangeMode._value2member_map_ else RangeMode.SINCE_LAST_TAG

    if selected_mode is RangeMode.SINCE_SPECIFIC_TAG:
        if not tag and default_range == RangeMode.SINCE_SPECIFIC_TAG.value:
            raise RangeResolutionError("Configuration default_range=tag requires --tag.")
        return RangeRequest(mode=selected_mode, tag=tag, fallback_window_days=fallback_days)

    if selected_mode is RangeMode.SINCE_LAST_TAG:
        return RangeRequest(mode=selected_mode, fallback_window_days=fallback_days)

    if selected_mode is RangeMode.SHA_RANGE:
        if not from_sha:
            raise RangeResolutionError("--from-sha is required when selecting commit SHA range.")
        return RangeRequest(mode=selected_mode, from_sha=from_sha, to_sha=to_sha)

    if selected_mode is RangeMode.DATE_RANGE:
        since_dt = _parse_date_or_default(since_date_raw, now, fallback_days)
        until_dt = _parse_date_or_default(until_date_raw, now, 0)
        if since_dt and until_dt and since_dt > until_dt:
            raise RangeResolutionError("--since-date must be earlier than --until-date.")
        return RangeRequest(
            mode=selected_mode,
            since=since_dt,
            until=until_dt,
            fallback_window_days=fallback_days,
        )

    if selected_mode is RangeMode.WINDOW:
        window = _parse_window(window_raw, fallback_days)
        return RangeRequest(mode=selected_mode, window=window)

    return RangeRequest(mode=RangeMode.SINCE_LAST_TAG, fallback_window_days=fallback_days)


def summarize_range_request(range_request: RangeRequest) -> str:
    """Produce a short human readable description of the resolved range."""

    mode = range_request.mode
    if mode is RangeMode.SINCE_LAST_TAG:
        return "since last tag"
    if mode is RangeMode.SINCE_SPECIFIC_TAG:
        return f"since tag {range_request.tag}" if range_request.tag else "since tag"
    if mode is RangeMode.SHA_RANGE:
        suffix = f"..{range_request.to_sha[:7]}" if range_request.to_sha else "..HEAD"
        return f"commits {range_request.from_sha[:7]}{suffix}" if range_request.from_sha else "commit range"
    if mode is RangeMode.DATE_RANGE:
        parts: list[str] = []
        if range_request.since:
            parts.append(f"since {range_request.since.date().isoformat()}")
        if range_request.until:
            parts.append(f"until {range_request.until.date().isoformat()}")
        return " ".join(parts) or "date range"
    if mode is RangeMode.WINDOW:
        window = range_request.window or dt.timedelta(days=0)
        if window >= dt.timedelta(weeks=1) and window % dt.timedelta(weeks=1) == dt.timedelta():
            weeks = window.days // 7
            return f"last {weeks}w"
        if window >= dt.timedelta(days=1) and window.seconds == 0:
            return f"last {window.days}d"
        hours = int(window.total_seconds() // 3600)
        return f"last {hours}h"
    return mode.value


def _coerce_optional_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    return str(value)


def _parse_date_or_default(
    date_str: str | None,
    now: dt.datetime,
    fallback_days: int,
) -> dt.datetime | None:
    if date_str:
        parsed = _parse_datetime(date_str)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    if fallback_days:
        return now - dt.timedelta(days=fallback_days)
    return None


def _parse_datetime(value: str) -> dt.datetime:
    if date_parser is not None:
        return date_parser.parse(value)  # type: ignore[return-value]
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - fallback branch
        raise RangeResolutionError(
            "Unable to parse date. Provide ISO 8601 format (YYYY-MM-DD) or install python-dateutil."
        ) from exc


def _parse_window(window_str: str | None, fallback_days: int) -> dt.timedelta:
    if not window_str:
        return dt.timedelta(days=fallback_days)
    match = _WINDOW_RE.match(window_str.lower())
    if not match:
        raise RangeResolutionError(
            "--window must be specified as <number><unit> where unit is one of d, h, w."
        )
    value = int(match.group("value"))
    unit = match.group("unit")
    if unit == "d":
        return dt.timedelta(days=value)
    if unit == "h":
        return dt.timedelta(hours=value)
    if unit == "w":
        return dt.timedelta(weeks=value)
    raise RangeResolutionError("Unsupported window unit. Use d, h, or w.")
