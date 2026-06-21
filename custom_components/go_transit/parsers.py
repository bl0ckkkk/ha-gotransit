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


def parse_delay(obj: dict) -> int | None:
    """Extract delay in minutes from a trip/line object.
    Tries explicit delay fields first, then computes scheduled vs actual."""
    for key in ("DelayMinutes", "Delay", "DelayInMinutes"):
        val = obj.get(key)
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
    sched = obj.get("ScheduledTime") or obj.get("ScheduledDepartureTime")
    actual = obj.get("ActualTime") or obj.get("ComputedDepartureTime")
    if sched and actual and sched != actual:
        try:
            s = datetime.strptime(sched, "%H:%M")
            a = datetime.strptime(actual, "%H:%M")
            return int((a - s).total_seconds() / 60)
        except ValueError:
            pass
    return None


def parse_next_service(raw: dict, line_code: str) -> dict | None:
    """Parse Stop/NextService into the soonest departure dict, or None.

    The API returns a flat Lines array; each entry is a trip prediction.
    Filter to line_code (if set), then pick the lowest TripOrder."""
    lines = _as_list(raw.get("NextService", {}).get("Lines"))
    candidates = [
        ln for ln in lines
        if not line_code or str(ln.get("LineCode", "")).upper() == line_code.upper()
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda x: x.get("TripOrder", 9999))
    ln = candidates[0]
    return {
        "trip_number": ln.get("TripNumber"),
        "destination": ln.get("DirectionName"),
        "line_code": ln.get("LineCode"),
        "line_name": ln.get("LineName"),
        "service_type": ln.get("ServiceType"),
        "direction_code": ln.get("DirectionCode"),
        "scheduled_time": ln.get("ScheduledDepartureTime"),
        "computed_time": ln.get("ComputedDepartureTime"),
        "departure_status": ln.get("DepartureStatus"),
        "scheduled_platform": ln.get("ScheduledPlatform"),
        "actual_platform": ln.get("ActualPlatform"),
        "status": ln.get("Status"),
        "delay_minutes": parse_delay(ln),
        "latitude": ln.get("Latitude"),
        "longitude": ln.get("Longitude"),
        "update_time": ln.get("UpdateTime"),
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


def minutes_until(departure_hhmm: str, now_dt=None) -> int | None:
    """Minutes from now until a HH:MM departure today.
    Returns None if unparseable. Handles departures up to ~3h past midnight
    by rolling forward when the time looks like it's already passed by a lot."""
    if not departure_hhmm:
        return None
    if now_dt is None:
        now_dt = datetime.now()
    try:
        dep = datetime.strptime(departure_hhmm, "%H:%M")
    except ValueError:
        return None
    dep_today = now_dt.replace(hour=dep.hour, minute=dep.minute, second=0, microsecond=0)
    diff = int((dep_today - now_dt).total_seconds() / 60)
    # If the departure appears to be well in the past (>180 min), it's tomorrow's
    if diff < -180:
        diff += 24 * 60
    return diff


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
