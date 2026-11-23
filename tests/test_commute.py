"""Regression tests for alert rules against dated, controlled feed observations."""
import sys
from datetime import timedelta
from pathlib import Path
from types import ModuleType

# Load the pure helpers without invoking Home Assistant integration setup.
package = ModuleType("go_test_commute")
package.__path__ = [str(Path(__file__).parents[1] / "custom_components" / "go_transit")]
sys.modules[package.__name__] = package

from go_test_commute.commute import CANCELLED, departure_alerts, destination_is_next
from go_test_commute.parsers import parse_boarding_cancellations
from go_test_commute.pinning import departure_options, go_datetime, match_pinned_train

BOARDING = "2026-10-11 07:42"
NOW = go_datetime("2026-10-11 07:35")
PIN = {"trip_number": "1234", "departure_datetime": BOARDING, "transfers": 0, "direction": "W"}


def test_cancellation_after_board_advances_requires_current_boarding_stop_evidence():
    backup = {"trip_number": "5678", "departure_datetime": "2026-10-11 08:03", "line": "LW", "transfers": 0}
    data = {
        "departures": [backup],
        "live_departures": [{**backup, "computed_datetime": "2026-10-11 08:06"}],
        "boarding_cancellations": [{"trip_number": "1234", "origin_in_feed": True}],
        "exceptions_timestamp": "2026-10-10 07:35",
    }
    state = {}
    assert departure_alerts(PIN, state, data, NOW, "LW") == []
    data["exceptions_timestamp"] = "2026-10-11 07:35"
    data["boarding_cancellations"][0]["origin_in_feed"] = False
    assert departure_alerts(PIN, state, data, NOW, "LW") == []
    data["boarding_cancellations"][0]["origin_in_feed"] = True
    assert departure_alerts(PIN, state, data, NOW, "LW") == [
        (CANCELLED, {"backup": {"trip_number": "5678", "time": "08:06", "scheduled": False}})
    ]
    assert departure_alerts(PIN, state, data, NOW, "LW") == []


def test_live_watch_ignores_same_train_number_on_a_different_date():
    data = {
        "live_departures": [{**PIN, "departure_datetime": "2026-10-12 07:42", "actual_platform": "7", "delay_minutes": 9}]
    }
    assert departure_alerts(PIN, {"platform": "1"}, data, NOW, "LW") == []


def test_matching_rejects_previous_day_out_of_window_and_duplicate_runs():
    train = {"trip_number": "1234", "direction": "W", "line_code": " LW "}
    assert match_pinned_train([train], PIN, "LW", NOW) == train
    assert match_pinned_train([train], PIN, "LW", NOW - timedelta(days=1)) is None
    assert match_pinned_train([train], PIN, "LW", NOW + timedelta(hours=5)) is None
    assert match_pinned_train([train, {**train, "direction": "E"}], PIN, "LW", NOW) is None
    assert match_pinned_train([{**train, "direction": "E"}], PIN, "LW", NOW) is None


def test_get_off_requires_direct_trip_and_train_past_boarding_stop():
    now = go_datetime(BOARDING)
    train = {"next_stop": "BU", "at_station": "UN"}
    assert not destination_is_next(PIN, train, "UN", "BU", now)
    assert not destination_is_next({**PIN, "transfers": 1}, {"next_stop": "BU"}, "UN", "BU", now)
    assert not destination_is_next(PIN, {"next_stop": "BU"}, "UN", "BU", NOW)
    assert destination_is_next(PIN, {"next_stop": "BU"}, "UN", "BU", now)


def test_pin_options_merge_direct_itinerary_and_exclude_another_line():
    other_route = {**PIN, "line": "LE", "trip_number": "5555"}
    live = {**PIN, "destination": "LW - Aldershot", "actual_platform": "3"}
    data = {"next_departure": live, "departures": [PIN, other_route]}
    option, = departure_options(data, "LW", "Burlington").values()
    assert option["transfers"] == 0
    assert option["actual_platform"] == "3"
    assert not departure_options({"next_departure": live}, "LW", "Burlington")


def test_exceptions_parser_ignores_skipped_and_ambiguous_trips():
    cancelled_stop = {"TripNumber": "1234", "Stop": {"Code": "UN", "IsCancelled": "true"}}
    skipped_stop = {"TripNumber": "5678", "Stop": {"Code": "UN", "IsStopping": "false"}}
    raw = {"Trip": [cancelled_stop, skipped_stop]}
    assert parse_boarding_cancellations(raw, "UN") == [{"trip_number": "1234", "origin_in_feed": True}]
    raw["Trip"].append({"TripNumber": "1234", "IsCancelled": "false"})
    assert parse_boarding_cancellations(raw, "UN") == []
