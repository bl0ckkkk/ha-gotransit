"""Pure helpers for stable, date-scoped train selections."""
from datetime import datetime, timedelta

UNPINNED = "Follow next departure"


def departure_options(data: dict) -> dict[str, dict]:
    """Include the live next departure and scheduled alternatives."""
    result = {}
    rows = [data.get("next_departure") or {}, *data.get("departures", [])]
    for row in rows:
        trip = str(row.get("trip_number") or "").strip()
        when = row.get("departure_datetime") or row.get("scheduled_datetime")
        if not trip or not when:
            continue
        label = f"{when} · Train {trip}"
        result.setdefault(label, {**row, "trip_number": trip, "departure_datetime": when})
    return result


def active_pin(pin: dict | None, now: datetime) -> dict | None:
    """Never match a trip number indefinitely or restore malformed storage."""
    if not isinstance(pin, dict) or not pin.get("trip_number") or not pin.get("label"):
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
            "expires_at": (now + timedelta(hours=12)).isoformat()}


def match_train(trains: list[dict], trip_number: str | None) -> dict | None:
    if not trip_number:
        return None
    return next((train for train in trains
                 if str(train.get("trip_number") or "").strip() == str(trip_number).strip()), None)
