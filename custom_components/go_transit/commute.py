"""Evaluate one dated commute against the latest departure and vehicle snapshots."""
from datetime import datetime, timedelta, timezone

from .pinning import GO_TIMEZONE, departure_key, go_datetime, on_route_line

CANCELLED = "departure_cancelled"
PLATFORM_CHANGED = "platform_changed"
DELAYED = "departure_delayed"
DESTINATION_NEXT = "destination_next"
EVENT_TYPES = [CANCELLED, PLATFORM_CHANGED, DELAYED, DESTINATION_NEXT]
DELAY_THRESHOLD = 5


def is_fresh(observed: datetime | None, now: datetime, max_age: timedelta) -> bool:
    now = now.astimezone(timezone.utc)
    return observed is not None and now - max_age <= observed <= now + timedelta(minutes=1)


def boarding_deadline(pin: dict) -> datetime | None:
    departure = departure_key(pin)
    if departure is None:
        return None
    predicted = go_datetime(pin.get("_commute", {}).get("computed_datetime"))
    return predicted or departure[1]


def backup_departure(data: dict, pin: dict, now: datetime, line_code: str) -> dict | None:
    """Find the next direct departure on the route with known schedule coverage."""
    watched = departure_key(pin)
    live = data.get("live_departures", [])
    candidates = []
    for row in data.get("departures", []):
        key = departure_key(row)
        if not key or key == watched or key[1] < watched[1]:
            continue
        if row.get("transfers") != 0 or not on_route_line(row, line_code):
            continue
        if any(c["trip_number"] == key[0] for c in data.get("boarding_cancellations", [])):
            continue
        predictions = [item for item in live if departure_key(item) == key]
        predicted = go_datetime(predictions[0].get("computed_datetime")) if len(predictions) == 1 else None
        when = predicted or key[1]
        if when >= now:
            candidates.append((when, key[0], predicted is None))
    if not candidates:
        return None
    when, trip, scheduled_only = min(candidates)
    time_label = when.astimezone(GO_TIMEZONE).strftime("%H:%M")
    return {"trip_number": trip, "time": time_label, "scheduled": scheduled_only}


def departure_alerts(
    pin: dict, state: dict, data: dict, now: datetime, line_code: str,
) -> list[tuple[str, dict]]:
    """Update the watch from a fresh poll without following a different departure."""
    watched = departure_key(pin)
    if watched is None:
        return []
    observed = go_datetime(data.get("live_departures_timestamp"))
    predictions_are_current = observed is None or is_fresh(observed, now, timedelta(minutes=4))
    matches = [
        row for row in data.get("live_departures", [])
        if predictions_are_current and departure_key(row) == watched
    ]
    live = matches[0] if len(matches) == 1 else {}
    deadline = boarding_deadline(pin)
    predicted = go_datetime(live.get("computed_datetime"))
    if predicted:
        # A late poll can establish a later boarding time for the same dated run.
        deadline = predicted
        state["computed_datetime"] = live["computed_datetime"]
    if deadline is None or now > deadline or state.get(CANCELLED):
        return []

    # Exceptions can omit scheduled dates. Once a cancelled run drops out of the
    # board, require one current, same-day exception that names our boarding stop.
    cancellations = [row for row in data.get("boarding_cancellations", []) if row["trip_number"] == watched[0]]
    timestamp = go_datetime(data.get("exceptions_timestamp"))
    current_day = (timestamp or now).astimezone(GO_TIMEZONE).date() == watched[1].astimezone(GO_TIMEZONE).date()
    current_report = timestamp is None or is_fresh(timestamp, now, timedelta(minutes=5))
    removed_from_board = (
        not matches and timestamp is not None and len(cancellations) == 1
        and cancellations[0]["origin_in_feed"] and watched[1] - now <= timedelta(minutes=30)
    )
    if len(cancellations) == 1 and current_day and current_report and (live or removed_from_board):
        state[CANCELLED] = True
        return [(CANCELLED, {"backup": backup_departure(data, pin, now, line_code)})]

    events = []
    platform = str(live.get("actual_platform") or "").strip()
    previous = state.get("platform")
    if platform and platform != previous:
        state["platform"] = platform
        if previous:
            events.append((PLATFORM_CHANGED, {"previous_platform": previous, "platform": platform}))

    delay = live.get("delay_minutes")
    if delay is not None and delay >= DELAY_THRESHOLD and not state.get(DELAYED):
        state[DELAYED] = True
        events.append((DELAYED, {"delay_minutes": delay}))

    if events:
        backup = backup_departure(data, pin, now, line_code)
        for _, attributes in events:
            attributes["backup"] = backup
    return events


def destination_is_next(pin: dict, train: dict, origin: str, destination: str, now: datetime) -> bool:
    """Check that a direct train has left the boarding stop and is approaching the destination."""
    deadline = boarding_deadline(pin)
    return bool(
        deadline and now >= deadline and pin.get("transfers") == 0
        and destination and station_code(train.get("next_stop")) == station_code(destination)
        and station_code(train.get("at_station")) not in (station_code(origin), station_code(destination))
    )


def station_code(code: str | None) -> str:
    return str(code or "").strip().upper()
