"""Pure helpers for stable, date-scoped train selections."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

UNPINNED = "Follow next departure"
GO_TIMEZONE = ZoneInfo("America/Toronto")


def go_datetime(value: str | None) -> datetime | None:
    """Read dated GO timestamps in agency time, returning comparable UTC instants."""
    if not isinstance(value, str) or len(value.strip()) <= 10:
        return None
    try:
        stamp = datetime.fromisoformat(value.strip())
    except (TypeError, ValueError):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=GO_TIMEZONE)
    return stamp.astimezone(timezone.utc)


def departure_key(row: dict) -> tuple[str, datetime] | None:
    trip = str(row.get("trip_number") or "").strip()
    when = go_datetime(row.get("departure_datetime") or row.get("scheduled_datetime"))
    return (trip, when) if trip and when else None


def on_route_line(row: dict, line_code: str) -> bool:
    line = str(row.get("line_code") or row.get("line") or "").strip().upper()
    service_type = str(row.get("service_type") or "").strip().upper()
    return (not line_code or not line or line == line_code.strip().upper()) and service_type != "B"


def departure_options(data: dict, line_code: str = "", destination: str = "") -> dict[str, dict]:
    """Combine the live next departure with its route itinerary when available."""
    scheduled = {
        key: row for row in data.get("departures", [])
        if (key := departure_key(row)) and on_route_line(row, line_code)
    }
    live = data.get("next_departure") or {}
    live_key = departure_key(live)
    rows = list(scheduled.values())
    live_destination = str(live.get("destination") or "").casefold()
    if live_key and on_route_line(live, line_code) and (
        live_key in scheduled or not destination or destination.casefold() in live_destination
    ):
        itinerary = scheduled.pop(live_key, {})
        rows = [{**itinerary, **live}, *scheduled.values()]

    result = {}
    for row in rows:
        trip, _ = departure_key(row)
        when = row.get("departure_datetime") or row["scheduled_datetime"]
        label = f"{when} · Train {trip}"
        result[label] = {**row, "trip_number": trip, "departure_datetime": when}
    return result


def active_pin(pin: dict | None, now: datetime) -> dict | None:
    """Never match a trip number indefinitely or restore malformed storage."""
    if not isinstance(pin, dict) or not departure_key(pin) or not isinstance(pin.get("label"), str):
        return None
    try:
        expires = datetime.fromisoformat(pin["expires_at"])
        if expires.tzinfo is None or expires <= now:
            return None
    except (KeyError, TypeError, ValueError):
        return None
    return pin


def make_pin(label: str, departure: dict, now: datetime) -> dict:
    return {**departure, "label": label, "pinned_at": now.isoformat(),
            "expires_at": (now.astimezone(timezone.utc) + timedelta(hours=12)).isoformat()}


def match_train(trains: list[dict], trip_number: str | None) -> dict | None:
    if not trip_number:
        return None
    return next((train for train in trains
                 if str(train.get("trip_number") or "").strip() == str(trip_number).strip()), None)


def match_pinned_train(
    trains: list[dict], pin: dict, line_code: str, observed_at: datetime | None,
) -> dict | None:
    """Constrain the undated vehicle ID to the selected departure's run window."""
    key = departure_key(pin)
    if not key or observed_at is None or not on_route_line(pin, line_code):
        return None
    trip, departure = key
    arrival = go_datetime(pin.get("arrival_datetime"))
    if not arrival or arrival < departure or pin.get("transfers"):
        arrival = departure + timedelta(hours=2)
    last_seen = min(arrival + timedelta(minutes=45), departure + timedelta(hours=4))
    if not departure - timedelta(minutes=30) <= observed_at <= last_seen:
        return None

    matches = [train for train in trains if on_route_line(train, line_code)
               and str(train.get("trip_number") or "").strip() == trip]
    if len(matches) != 1:
        return None
    train = matches[0]
    direction = str(pin.get("direction") or "").strip().upper()
    if direction and direction != str(train.get("direction") or "").strip().upper():
        return None
    return train
