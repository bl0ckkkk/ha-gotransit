"""Pure parsing functions for GO Transit API responses.

These are deliberately free of any I/O, Home Assistant, or aiohttp dependency
so they can be unit-tested in isolation. Each takes a decoded JSON dict and
returns plain Python structures.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def _as_list(value: Any) -> list:
    """The GO API returns single items as a dict and multiples as a list.
    Normalise to always be a list. None/missing becomes []."""
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return value
    return []


def _parse_api_time(value):
    """Parse the GO API datetime format 'YYYY-MM-DD HH:MM:SS' into a datetime.
    Also tolerates a bare 'HH:MM'. Returns None on failure."""
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _hhmm(value):
    """Extract 'HH:MM' display string from an API datetime, or None."""
    dt = _parse_api_time(value)
    return dt.strftime("%H:%M") if dt else None


def _valid_coord(value):
    """GO uses -1.0 as a 'no GPS' sentinel. Return float or None."""
    try:
        f = float(value)
    except (ValueError, TypeError):
        return None
    if f == -1.0 or f == 0.0:
        return None
    return f


def parse_delay(obj: dict) -> int | None:
    """Extract delay in minutes from a trip/line object.
    Tries explicit delay fields first, then computes scheduled vs computed
    using the API's 'YYYY-MM-DD HH:MM:SS' datetime format."""
    for key in ("DelayMinutes", "Delay", "DelayInMinutes"):
        val = obj.get(key)
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
    sched = _parse_api_time(obj.get("ScheduledTime") or obj.get("ScheduledDepartureTime"))
    actual = _parse_api_time(obj.get("ActualTime") or obj.get("ComputedDepartureTime"))
    if sched and actual and sched != actual:
        return int((actual - sched).total_seconds() / 60)
    return None


def parse_next_service(raw: dict, line_code: str, destination: str = "") -> dict | None:
    """Parse Stop/NextService into the soonest departure toward `destination`.

    The API returns a flat Lines array mixing every direction from the stop
    (Aldershot, Union, West Harbour, ...). DirectionCode is the same line code
    for all of them, so we filter by DirectionName containing the destination
    station name, then pick the EARLIEST departure by actual clock time
    (TripOrder is per-direction and unreliable across mixed directions).

    Times come as 'YYYY-MM-DD HH:MM:SS'. Coordinates use -1.0 as 'no GPS'."""
    lines = _as_list(raw.get("NextService", {}).get("Lines"))

    # Filter by line code (trailing whitespace tolerated)
    candidates = [
        ln for ln in lines
        if not line_code or str(ln.get("LineCode", "")).strip().upper() == line_code.strip().upper()
    ]

    # Filter by destination station name if provided (case-insensitive substring)
    if destination:
        dest_l = destination.strip().lower()
        matched = [
            ln for ln in candidates
            if dest_l in str(ln.get("DirectionName", "")).lower()
        ]
        # Only narrow if we actually found destination matches; otherwise keep all
        if matched:
            candidates = matched

    if not candidates:
        return None

    # Sort by actual departure clock time, earliest first
    def _dep_key(ln):
        dt = _parse_api_time(ln.get("ComputedDepartureTime") or ln.get("ScheduledDepartureTime"))
        return dt or datetime.max
    candidates.sort(key=_dep_key)

    ln = candidates[0]
    return {
        "trip_number": ln.get("TripNumber"),
        "destination": str(ln.get("DirectionName", "")).strip(),
        "line_code": str(ln.get("LineCode", "")).strip(),
        "line_name": ln.get("LineName"),
        "service_type": ln.get("ServiceType"),
        "direction_code": str(ln.get("DirectionCode", "")).strip(),
        "scheduled_time": _hhmm(ln.get("ScheduledDepartureTime")),
        "computed_time": _hhmm(ln.get("ComputedDepartureTime")),
        "scheduled_datetime": ln.get("ScheduledDepartureTime"),
        "computed_datetime": ln.get("ComputedDepartureTime"),
        "departure_status": ln.get("DepartureStatus"),
        "scheduled_platform": ln.get("ScheduledPlatform"),
        "actual_platform": ln.get("ActualPlatform") or None,
        "status": ln.get("Status"),
        "delay_minutes": parse_delay(ln),
        "latitude": _valid_coord(ln.get("Latitude")),
        "longitude": _valid_coord(ln.get("Longitude")),
        "update_time": _hhmm(ln.get("UpdateTime")),
        "is_cancelled": False,
    }


def parse_consist(raw: dict, trip_number: str) -> dict:
    """Parse Fleet/Consist/All and join to trip_number via RemainingTrip."""
    result = {
        "coach_count": None, "engine_number": None,
        "consist_number": None, "lineup": [],
    }
    if not trip_number:
        return result
    consists = _as_list(raw.get("AllConsists", {}).get("Consists"))
    matched = None
    for consist in consists:
        for trip in _as_list(consist.get("RemainingTrip")):
            if str(trip.get("Number", "")).strip() == str(trip_number).strip():
                matched = consist
                break
        if matched:
            break
    if matched:
        lineup = _as_list(matched.get("Lineup"))
        lineup_sorted = sorted(lineup, key=lambda c: c.get("Order", 0))
        result.update({
            "coach_count": matched.get("CoachCount"),
            "engine_number": matched.get("EngineNumber"),
            "consist_number": matched.get("Number"),
            "lineup": [
                {"order": c.get("Order"), "type": c.get("Type"), "number": c.get("Number")}
                for c in lineup_sorted
            ],
        })
    return result


def parse_exceptions(raw: dict, trip_number: str, from_stop_code: str) -> dict:
    """Parse Exceptions/All for cancellation status of a given trip/stop."""
    result = {
        "is_cancelled": False,
        "stop_is_cancelled": False,
        "stop_is_stopping": True,
        "stop_actual_time": None,
        "matched": False,
    }
    if not trip_number:
        return result
    for exc_trip in _as_list(raw.get("Trip")):
        if str(exc_trip.get("TripNumber", "")).strip() != str(trip_number).strip():
            continue
        result["matched"] = True
        result["is_cancelled"] = str(exc_trip.get("IsCancelled", "false")).lower() == "true"
        for stop in _as_list(exc_trip.get("Stop")):
            if str(stop.get("Code", "")).upper() == from_stop_code.upper():
                result["stop_is_cancelled"] = str(stop.get("IsCancelled", "false")).lower() == "true"
                result["stop_is_stopping"] = str(stop.get("IsStopping", "true")).lower() == "true"
                result["stop_actual_time"] = stop.get("ActualTime")
                break
        break
    return result


def parse_guarantee(raw: dict, from_stop_code: str) -> dict:
    """Parse ServiceGuarantee for whether a refund guarantee applies."""
    result = {"guarantee_active": False, "affected_stops": [], "reason": None}
    stops = _as_list(raw.get("Stops", {}).get("Stop"))
    if not stops:
        return result
    result["guarantee_active"] = True
    reason = None
    affected = []
    for stop in stops:
        affected.append({
            "stop_code": stop.get("Code"),
            "scope": stop.get("Scope"),
            "reason": stop.get("ReasonEn"),
        })
        if str(stop.get("Code", "")).upper() == from_stop_code.upper():
            reason = stop.get("ReasonEn")
    result["affected_stops"] = affected
    result["reason"] = reason or (affected[0]["reason"] if affected else None)
    return result


def parse_alerts(raw: dict, line_code: str) -> list[dict]:
    """Parse ServiceAlert/All filtered to a line (plus system-wide alerts)."""
    all_alerts = _as_list(raw.get("ServiceAlerts", {}).get("ServiceAlert"))
    filtered = [
        a for a in all_alerts
        if not line_code
        or line_code.upper() in str(a.get("AffectedLines", "")).upper()
        or not a.get("AffectedLines")
    ]
    return [
        {
            "id": a.get("AlertId"),
            "header": a.get("HeaderText"),
            "description": a.get("DescriptionText"),
            "effect": a.get("Effect"),
            "start": a.get("ActivePeriodStart"),
            "end": a.get("ActivePeriodEnd"),
        }
        for a in filtered
    ]


def parse_trains(raw: dict, line_code: str) -> list[dict]:
    """Parse ServiceataGlance/Trains/All filtered to a line."""
    trains = _as_list(raw.get("ServiceataGlance", {}).get("Trains", {}).get("Train"))
    line_trains = [
        t for t in trains
        if not line_code or str(t.get("LineCode", "")).upper() == line_code.upper()
    ]
    return [
        {
            "trip_number": t.get("TripNumber"),
            "direction": t.get("Direction"),
            "latitude": t.get("Latitude"),
            "longitude": t.get("Longitude"),
            "next_stop": t.get("NextStopCode"),
            "status": t.get("Status"),
            "delay_minutes": parse_delay(t),
        }
        for t in line_trains
    ]


def in_commute_window(start_str: str, end_str: str, now_time=None) -> bool:
    """True if now_time (defaults to current) is within the window.
    Handles overnight windows (start > end)."""
    if now_time is None:
        now_time = datetime.now().time()
    try:
        start = datetime.strptime(start_str, "%H:%M").time()
        end = datetime.strptime(end_str, "%H:%M").time()
    except ValueError:
        return False
    if start <= end:
        return start <= now_time <= end
    return now_time >= start or now_time <= end


def minutes_until(departure_time: str, now_dt=None) -> int | None:
    """Minutes from now until a departure.

    Accepts either a full 'YYYY-MM-DD HH:MM:SS' datetime (preferred — has the
    date, so no rollover guessing needed) or a bare 'HH:MM'. Returns None if
    unparseable."""
    if not departure_time:
        return None
    if now_dt is None:
        now_dt = datetime.now()
    dep = _parse_api_time(departure_time)
    if dep is None:
        return None
    # If the parsed value has no real date (bare HH:MM -> year 1900), anchor to today
    if dep.year == 1900:
        dep = now_dt.replace(hour=dep.hour, minute=dep.minute, second=0, microsecond=0)
        diff = int((dep - now_dt).total_seconds() / 60)
        if diff < -180:
            diff += 24 * 60
        return diff
    return int((dep - now_dt).total_seconds() / 60)


def is_catchable(
    minutes_to_departure: int | None,
    travel_minutes: float | None,
    is_cancelled: bool,
    buffer_minutes: int = 2,
) -> bool:
    """Decide whether the user can still make the train from their platform.

    catchable = (time until departure) >= (travel time + safety buffer).
    Cancelled trains stay catchable=True so the user redirects to the next train.
    If we lack data to decide, default to True (fail open — don't tell someone
    they've missed a train when we're not sure)."""
    if is_cancelled:
        return True
    if minutes_to_departure is None or travel_minutes is None:
        return True
    return minutes_to_departure >= (travel_minutes + buffer_minutes)


def in_service_hours(start_str: str, end_str: str, now_time=None) -> bool:
    """Whether trains are running now (reuses overnight-window logic)."""
    return in_commute_window(start_str, end_str, now_time)
