"""Unit tests for GO Transit pure parsing functions."""
import sys
import os
from datetime import time

# Make the parsers module importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "custom_components", "go_transit"))

import parsers
import fixtures as fx


# ----------------------------------------------------------------------------
# _as_list
# ----------------------------------------------------------------------------

def test_as_list_none():
    assert parsers._as_list(None) == []

def test_as_list_dict():
    assert parsers._as_list({"a": 1}) == [{"a": 1}]

def test_as_list_list():
    assert parsers._as_list([1, 2]) == [1, 2]

def test_as_list_garbage():
    assert parsers._as_list("string") == []
    assert parsers._as_list(42) == []


# ----------------------------------------------------------------------------
# parse_delay
# ----------------------------------------------------------------------------

def test_delay_explicit_field():
    assert parsers.parse_delay({"DelayMinutes": "7"}) == 7

def test_delay_computed_from_times():
    assert parsers.parse_delay({"ScheduledDepartureTime": "07:12", "ComputedDepartureTime": "07:19"}) == 7

def test_delay_on_time_returns_none():
    assert parsers.parse_delay({"ScheduledDepartureTime": "07:12", "ComputedDepartureTime": "07:12"}) is None

def test_delay_no_data():
    assert parsers.parse_delay({}) is None

def test_delay_malformed_time():
    assert parsers.parse_delay({"ScheduledDepartureTime": "garbage", "ComputedDepartureTime": "07:19"}) is None

def test_delay_negative_early():
    # Train running early — negative delay
    assert parsers.parse_delay({"ScheduledDepartureTime": "07:19", "ComputedDepartureTime": "07:12"}) == -7


# ----------------------------------------------------------------------------
# parse_next_service
# ----------------------------------------------------------------------------

def test_next_service_picks_earliest_to_destination():
    # Two LW trips; only 1234 goes to Union. Must pick it, not the Aldershot one.
    result = parsers.parse_next_service(fx.NEXT_SERVICE_NORMAL, "LW", "Union")
    assert result["trip_number"] == "1234"
    assert result["scheduled_platform"] == "3"

def test_next_service_destination_filter_excludes_other_dirs():
    result = parsers.parse_next_service(fx.NEXT_SERVICE_NORMAL, "LW", "Union")
    assert "Union" in result["destination"]

def test_next_service_times_converted_to_hhmm():
    result = parsers.parse_next_service(fx.NEXT_SERVICE_NORMAL, "LW", "Union")
    assert result["computed_time"] == "07:19"
    assert result["scheduled_time"] == "07:12"

def test_next_service_delay_from_datetimes():
    # 1234: scheduled 07:12, computed 07:19 = 7 min
    result = parsers.parse_next_service(fx.NEXT_SERVICE_NORMAL, "LW", "Union")
    assert result["delay_minutes"] == 7

def test_next_service_gps_sentinel_nulled():
    # 1234 has real coords; confirm they pass through
    result = parsers.parse_next_service(fx.NEXT_SERVICE_NORMAL, "LW", "Union")
    assert result["latitude"] == 43.3140

def test_next_service_single_dict():
    result = parsers.parse_next_service(fx.NEXT_SERVICE_SINGLE_DICT, "LW", "Union")
    assert result["trip_number"] == "5678"
    # -1.0 coords must be nulled
    assert result["latitude"] is None

def test_next_service_empty():
    assert parsers.parse_next_service(fx.NEXT_SERVICE_EMPTY, "LW", "Union") is None

def test_next_service_line_filter():
    # Mixed LE + LW, want Union on LW -> trip 1234
    result = parsers.parse_next_service(fx.NEXT_SERVICE_MIXED, "LW", "Union")
    assert result["trip_number"] == "1234"
    assert result["line_code"] == "LW"

def test_next_service_no_destination_takes_earliest():
    # No destination filter -> earliest by clock; in NORMAL that's 1232 at 06:42
    result = parsers.parse_next_service(fx.NEXT_SERVICE_NORMAL, "LW", "")
    assert result["trip_number"] == "1232"

def test_next_service_is_cancelled_defaults_false():
    result = parsers.parse_next_service(fx.NEXT_SERVICE_NORMAL, "LW", "Union")
    assert result["is_cancelled"] is False


def test_consist_match_coach_count():
    result = parsers.parse_consist(fx.CONSIST_ALL, "1234")
    assert result["coach_count"] == 12
    assert result["engine_number"] == "560"

def test_consist_lineup_sorted_by_order():
    result = parsers.parse_consist(fx.CONSIST_ALL, "1234")
    orders = [car["order"] for car in result["lineup"]]
    assert orders == [1, 2, 3]  # must be sorted even though fixture is 1,3,2

def test_consist_remaining_trip_as_dict():
    # Trip 9999's consist has RemainingTrip as a dict, not list
    result = parsers.parse_consist(fx.CONSIST_ALL, "9999")
    assert result["coach_count"] == 10

def test_consist_no_match():
    result = parsers.parse_consist(fx.CONSIST_NO_MATCH, "1234")
    assert result["coach_count"] is None
    assert result["lineup"] == []

def test_consist_no_trip_number():
    result = parsers.parse_consist(fx.CONSIST_ALL, "")
    assert result["coach_count"] is None


# ----------------------------------------------------------------------------
# parse_exceptions
# ----------------------------------------------------------------------------

def test_exceptions_trip_cancelled():
    result = parsers.parse_exceptions(fx.EXCEPTIONS_CANCELLED, "1234", "BU")
    assert result["is_cancelled"] is True
    assert result["matched"] is True
    assert result["stop_is_cancelled"] is True

def test_exceptions_stop_skipped_not_cancelled():
    result = parsers.parse_exceptions(fx.EXCEPTIONS_STOP_SKIPPED, "1234", "BU")
    assert result["is_cancelled"] is False
    assert result["stop_is_stopping"] is False

def test_exceptions_no_match():
    result = parsers.parse_exceptions(fx.EXCEPTIONS_NONE, "1234", "BU")
    assert result["matched"] is False
    assert result["is_cancelled"] is False

def test_exceptions_wrong_stop():
    # Trip matches but our stop (XX) isn't in the list — stop fields stay default
    result = parsers.parse_exceptions(fx.EXCEPTIONS_CANCELLED, "1234", "XX")
    assert result["is_cancelled"] is True  # trip-level still applies
    assert result["stop_is_stopping"] is True  # default, our stop not found

def test_exceptions_no_trip_number():
    result = parsers.parse_exceptions(fx.EXCEPTIONS_CANCELLED, "", "BU")
    assert result["matched"] is False


# ----------------------------------------------------------------------------
# parse_guarantee
# ----------------------------------------------------------------------------

def test_guarantee_active():
    result = parsers.parse_guarantee(fx.GUARANTEE_ACTIVE, "BU")
    assert result["guarantee_active"] is True
    assert result["reason"] == "Train delayed 15+ minutes"
    assert len(result["affected_stops"]) == 2

def test_guarantee_none():
    result = parsers.parse_guarantee(fx.GUARANTEE_NONE, "BU")
    assert result["guarantee_active"] is False
    assert result["reason"] is None

def test_guarantee_reason_fallback():
    # Our stop ZZ not in list, reason falls back to first stop
    result = parsers.parse_guarantee(fx.GUARANTEE_ACTIVE, "ZZ")
    assert result["guarantee_active"] is True
    assert result["reason"] == "Train delayed 15+ minutes"


# ----------------------------------------------------------------------------
# parse_alerts
# ----------------------------------------------------------------------------

def test_alerts_line_filter():
    # LW filter: should include ALT-1 (LW) and ALT-3 (system-wide, no AffectedLines)
    result = parsers.parse_alerts(fx.ALERTS_ALL, "LW")
    ids = {a["id"] for a in result}
    assert ids == {"ALT-1", "ALT-3"}

def test_alerts_no_filter_all():
    result = parsers.parse_alerts(fx.ALERTS_ALL, "")
    assert len(result) == 3

def test_alerts_field_mapping():
    result = parsers.parse_alerts(fx.ALERTS_ALL, "LW")
    alt1 = next(a for a in result if a["id"] == "ALT-1")
    assert alt1["header"] == "LW Delays"
    assert alt1["effect"] == "SIGNIFICANT_DELAYS"


# ----------------------------------------------------------------------------
# parse_trains
# ----------------------------------------------------------------------------

def test_trains_line_filter():
    result = parsers.parse_trains(fx.TRAINS_ALL, "LW")
    assert len(result) == 1
    assert result[0]["trip_number"] == "1234"
    assert result[0]["delay_minutes"] == 1  # 66s -> 1 min
    assert result[0]["direction"] == "E"
    assert result[0]["destination"] == "LW - Union Station"
    assert result[0]["in_motion"] is True

def test_trains_no_filter():
    result = parsers.parse_trains(fx.TRAINS_ALL, "")
    assert len(result) == 2


# ----------------------------------------------------------------------------
# in_commute_window
# ----------------------------------------------------------------------------

def test_commute_window_inside():
    assert parsers.in_commute_window("05:00", "10:00", time(7, 30)) is True

def test_commute_window_outside():
    assert parsers.in_commute_window("05:00", "10:00", time(14, 0)) is False

def test_commute_window_boundary_start():
    assert parsers.in_commute_window("05:00", "10:00", time(5, 0)) is True

def test_commute_window_boundary_end():
    assert parsers.in_commute_window("05:00", "10:00", time(10, 0)) is True

def test_commute_window_overnight():
    # 22:00 - 02:00 window
    assert parsers.in_commute_window("22:00", "02:00", time(23, 30)) is True
    assert parsers.in_commute_window("22:00", "02:00", time(1, 0)) is True
    assert parsers.in_commute_window("22:00", "02:00", time(12, 0)) is False

def test_commute_window_malformed():
    assert parsers.in_commute_window("garbage", "10:00", time(7, 0)) is False


# ----------------------------------------------------------------------------
# minutes_until
# ----------------------------------------------------------------------------
from datetime import datetime as _dt

def test_minutes_until_future():
    now = _dt(2026, 6, 20, 7, 0)
    assert parsers.minutes_until("2026-06-20 07:19:00", now) == 19

def test_minutes_until_now():
    now = _dt(2026, 6, 20, 7, 19)
    assert parsers.minutes_until("2026-06-20 07:19:00", now) == 0

def test_minutes_until_just_passed():
    now = _dt(2026, 6, 20, 7, 20)
    assert parsers.minutes_until("2026-06-20 07:19:00", now) == -1

def test_minutes_until_bare_hhmm_rolls_to_tomorrow():
    # Bare HH:MM (no date): 00:30 viewed at 23:00 -> ~90 min via rollover
    now = _dt(2026, 6, 20, 23, 0)
    assert parsers.minutes_until("00:30", now) == 90

def test_minutes_until_bad():
    assert parsers.minutes_until("garbage", _dt(2026,6,20,7,0)) is None
    assert parsers.minutes_until("", _dt(2026,6,20,7,0)) is None

def test_minutes_until_full_datetime_no_rollover_guess():
    # Full datetime in the past stays negative (real date present, no guessing)
    now = _dt(2026, 6, 20, 12, 0)
    assert parsers.minutes_until("2026-06-20 07:00:00", now) == -300


# ----------------------------------------------------------------------------
# is_catchable
# ----------------------------------------------------------------------------

def test_catchable_plenty_of_time():
    # 19 min to departure, 10 min travel + 2 buffer = 12 needed
    assert parsers.is_catchable(19, 10, False) is True

def test_catchable_too_late():
    # 5 min to departure, 10 min travel — can't make it
    assert parsers.is_catchable(5, 10, False) is False

def test_catchable_exactly_enough():
    # 12 min to departure, 10 travel + 2 buffer = exactly 12
    assert parsers.is_catchable(12, 10, False) is True

def test_catchable_cancelled_stays_on():
    # Even with no time, cancelled keeps it True so user redirects
    assert parsers.is_catchable(1, 10, True) is True

def test_catchable_no_data_fails_open():
    assert parsers.is_catchable(None, 10, False) is True
    assert parsers.is_catchable(10, None, False) is True

def test_catchable_custom_buffer():
    # 14 to departure, 10 travel + 5 buffer = 15 needed -> not catchable
    assert parsers.is_catchable(14, 10, False, buffer_minutes=5) is False


# ----------------------------------------------------------------------------
# in_service_hours (overnight window)
# ----------------------------------------------------------------------------
from datetime import time as _time

def test_service_hours_midday():
    assert parsers.in_service_hours("05:00", "01:30", _time(12, 0)) is True

def test_service_hours_late_night_still_running():
    # 00:45 is before the 01:30 end of the overnight window
    assert parsers.in_service_hours("05:00", "01:30", _time(0, 45)) is True

def test_service_hours_dead_zone():
    # 03:00 — no trains
    assert parsers.in_service_hours("05:00", "01:30", _time(3, 0)) is False
