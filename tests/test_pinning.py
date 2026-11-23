"""Train pin lifecycle and tracker regressions without a Home Assistant install."""
import asyncio
import importlib.util
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1] / "custom_components" / "go_transit"
sys.path.insert(0, str(ROOT))
from pinning import GO_TIMEZONE, UNPINNED, active_pin, departure_options, make_pin, match_train

NOW = datetime(2026, 10, 11, 23, 55, tzinfo=GO_TIMEZONE)
DEPARTURE = {"trip_number": "1234", "departure_datetime": "2026-10-11 23:58:00"}


def test_selection_survives_board_advance_and_midnight_but_expires():
    pin = make_pin("Tonight", DEPARTURE, NOW)
    assert active_pin(pin, NOW + timedelta(hours=2)) == pin
    assert active_pin(pin, NOW + timedelta(hours=12)) is None
    assert match_train([{"trip_number": "1236"}], pin["trip_number"]) is None
    assert match_train([{"trip_number": 1234}], pin["trip_number"])["trip_number"] == 1234


@pytest.mark.parametrize("pin", [None, {}, {"trip_number": "1234", "label": "x", "expires_at": "bad"},
                                    {"trip_number": "1234", "label": "x", "expires_at": "2026-10-12"}])
def test_invalid_saved_pin(pin):
    assert active_pin(pin, NOW) is None


def test_options_include_next_and_deduplicate_schedule():
    data = {"next_departure": {"trip_number": 1234, "scheduled_datetime": DEPARTURE["departure_datetime"],
                               "actual_platform": "2"}, "departures": [DEPARTURE, {}]}
    options = departure_options(data)
    assert len(options) == 1
    assert next(iter(options.values()))["actual_platform"] == "2"


@pytest.fixture
def runtime(monkeypatch):
    """Load production coordinator/tracker with small HA interface doubles."""
    def module(name, **attrs):
        mod = types.ModuleType(name)
        mod.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, mod)
        return mod

    class Coordinator:
        line_code = "LW"
        line_name = "Lakeshore West"
        from_stop_code = "UN"
        from_stop_name = "Union"
        to_stop_code = "BU"
        to_stop_name = "Burlington"

        def __init__(self, *args, **kwargs):
            self.hass = args[0] if args else None
            self.data = None
            self.last_update_success = True
            self.listeners = []
        def async_set_updated_data(self, data):
            self.data = data
            self.async_update_listeners()
        def async_update_listeners(self):
            for listener in self.listeners:
                listener()
        def async_add_listener(self, listener):
            self.listeners.append(listener)
            return lambda: self.listeners.remove(listener)

    class Entity:
        def __class_getitem__(cls, item):
            return cls
        def __init__(self, coordinator):
            self.coordinator = coordinator
        def async_write_ha_state(self):
            pass

    class Store:
        saved = {}
        def __init__(self, hass, version, key):
            self.key = key
        async def async_load(self):
            return self.saved.get(self.key)
        async def async_save(self, data):
            self.saved[self.key] = data

    class Tracker:
        pass
    class Select:
        pass
    class Sensor:
        pass

    class Event:
        async def async_added_to_hass(self):
            self.events = []

        def async_on_remove(self, remove):
            self.remove = remove

        def _trigger_event(self, event, attributes):
            self.events.append((event, attributes))

        def async_write_ha_state(self):
            pass

    for name in ["homeassistant", "homeassistant.components", "homeassistant.helpers", "homeassistant.util"]:
        module(name)
    module("homeassistant.core", HomeAssistant=object, callback=lambda f: f)
    module("homeassistant.config_entries", ConfigEntry=object)
    module("homeassistant.exceptions", HomeAssistantError=ValueError)
    module("homeassistant.helpers.storage", Store=Store)
    module("homeassistant.helpers.entity", DeviceInfo=dict)
    module("homeassistant.helpers.entity_platform", AddEntitiesCallback=object)
    module("homeassistant.helpers.update_coordinator", DataUpdateCoordinator=Coordinator, CoordinatorEntity=Entity)
    module("homeassistant.components.device_tracker", SourceType=types.SimpleNamespace(GPS="gps"), TrackerEntity=Tracker)
    module("homeassistant.components.select", SelectEntity=Select)
    module("homeassistant.components.event", EventEntity=Event)
    module("homeassistant.components.sensor", SensorEntity=Sensor,
           SensorDeviceClass=types.SimpleNamespace(TIMESTAMP="timestamp", ENUM="enum"))
    dt = module("homeassistant.util.dt", now=lambda: NOW)
    sys.modules["homeassistant.util"].dt = dt
    package = module("pin_test_package")
    package.__path__ = [str(ROOT)]
    module("pin_test_package.coordinator", DepartureCoordinator=Coordinator, VehicleCoordinator=Coordinator,
           AlertCoordinator=Coordinator, ConsistCoordinator=Coordinator, GuaranteeCoordinator=Coordinator)
    def load(name):
        full = "pin_test_package." + name
        spec = importlib.util.spec_from_file_location(full, ROOT / (name + ".py"))
        mod = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, full, mod)
        spec.loader.exec_module(mod)
        return mod
    pinned = load("pinned")
    tracker = load("device_tracker")
    select = load("select")
    sensor = load("sensor")
    event = load("event")
    return types.SimpleNamespace(
        Coordinator=Coordinator, Pin=pinned.PinnedTrainCoordinator,
        Tracker=tracker.GoTransitTrainTracker, Select=select.GoTransitPinnedTrainSelect,
        Sensor=sensor.GoTransitPinnedTrainStatusSensor, Event=event.GoTransitCommuteEvent, clock=dt,
    )


def test_pin_restore_clear_and_tracker_does_not_jump(runtime):
    async def scenario():
        dep, veh = runtime.Coordinator(), runtime.Coordinator()
        dep.data = {"next_departure": DEPARTURE, "departures": [DEPARTURE]}
        veh.data = {"updated_at": NOW.isoformat(),
                    "vehicle_positions": [{"trip_number": "1234", "latitude": 43, "longitude": -79},
                                          {"trip_number": "1236", "latitude": 44, "longitude": -80}]}
        veh.line_name = "Lakeshore West"
        entry = types.SimpleNamespace(entry_id="route1", title="Home to Union")
        pin = runtime.Pin(None, entry, dep, veh)
        await pin.async_load()
        selector = runtime.Select(pin, entry)
        tracker = runtime.Tracker(veh, dep, entry, pin)
        label = selector.options[1]
        await selector.async_select_option(label)
        dep.data = {"next_departure": {"trip_number": "1236"}, "departures": []}
        pin.async_feed_updated()
        assert selector.current_option == label
        assert label in selector.options
        assert tracker.latitude == 43
        restored = runtime.Pin(None, entry, dep, veh)
        await restored.async_load()
        assert restored.pin["trip_number"] == "1234"
        veh.data["vehicle_positions"] = [veh.data["vehicle_positions"][1]]
        assert tracker.latitude is None
        assert not tracker.available
        await selector.async_select_option(UNPINNED)
        assert tracker.latitude == 44
        assert selector.current_option == UNPINNED
        await restored.async_load()
        assert restored.pin is None
        with pytest.raises(ValueError):
            await selector.async_select_option("removed departure")
        other = runtime.Pin(None, types.SimpleNamespace(entry_id="route2"), dep, veh)
        await other.async_load()
        assert other.pin is None
    asyncio.run(scenario())


def test_status_needs_live_evidence_for_arrival(runtime):
    async def scenario():
        dep, veh = runtime.Coordinator(), runtime.Coordinator()
        dep.data = {"departures": [DEPARTURE]}
        dep.line_name, dep.to_stop_code = "LW", "UN"
        veh.data = {"updated_at": NOW.isoformat(), "vehicle_positions": []}
        entry = types.SimpleNamespace(entry_id="arrival", title="Home to Union")
        pin = runtime.Pin(None, entry, dep, veh)
        await pin.async_load()
        status = runtime.Sensor(pin, entry)
        assert status.native_value == "Not pinned"
        await pin.async_select(next(iter(pin.choices)))
        assert status.native_value == "Awaiting live data"
        veh.data["vehicle_positions"] = [{"trip_number": "1234", "at_station": "UN", "status": "Stopped"}]
        assert status.native_value == "At destination"
        veh.last_update_success = False
        assert status.native_value == "Awaiting live data"
        veh.last_update_success = True
        veh.data["vehicle_positions"][0]["at_station"] = "BU"
        assert status.native_value == "Stopped"
        assert status.extra_state_attributes["trip_number"] == "1234"
    asyncio.run(scenario())


def test_commute_alerts_follow_the_dated_pin_and_survive_reload(runtime):
    async def scenario():
        now = NOW
        runtime.clock.now = lambda: now
        hass = types.SimpleNamespace(async_create_task=asyncio.create_task)
        dep, veh = runtime.Coordinator(), runtime.Coordinator()
        entry = types.SimpleNamespace(entry_id="commute", title="Union to Burlington")
        departure = {**DEPARTURE, "transfers": 0, "actual_platform": "2", "direction": "W"}
        backup = {"trip_number": "5678", "departure_datetime": "2026-10-12 00:30", "transfers": 0}
        dep.data = {"next_departure": departure, "departures": [departure, backup], "updated_at": now.isoformat()}
        pin = runtime.Pin(hass, entry, dep, veh)
        await pin.async_load()
        event = runtime.Event(pin, entry)
        await event.async_added_to_hass()
        await pin.async_select(next(iter(pin.choices)))
        await pin.async_finish_pending_alerts()

        # The board advances. A separate live row still identifies our departure.
        dep.data.update(
            next_departure=backup,
            live_departures=[
                {**departure, "actual_platform": "3", "delay_minutes": 5,
                 "computed_datetime": "2026-10-12 00:03"},
                {**backup, "delay_minutes": 45, "actual_platform": "9"},
            ],
            departures=[backup],
        )
        pin.async_feed_updated()
        await pin.async_finish_pending_alerts()
        assert [kind for kind, _ in event.events] == ["platform_changed", "departure_delayed"]
        assert event.events[0][1]["platform"] == "3"
        assert event.events[1][1]["delay_minutes"] == 5
        assert event.events[1][1]["backup"] == {"trip_number": "5678", "time": "00:30", "scheduled": True}

        now += timedelta(minutes=10)
        # A stale or failed feed and a duplicate live match must not trigger.
        train = {"trip_number": "1234", "line_code": "LW", "direction": "W", "next_stop": " BU "}
        vehicle_snapshot = {"vehicle_positions": [train], "feed_timestamp": NOW.isoformat()}
        veh.data = vehicle_snapshot
        pin.async_feed_updated()
        await pin.async_finish_pending_alerts()
        assert len(event.events) == 2

        veh.data["feed_timestamp"] = now.isoformat()
        veh.last_update_success = False
        pin.async_feed_updated()
        await pin.async_finish_pending_alerts()
        assert len(event.events) == 2

        veh.last_update_success = True
        veh.data["vehicle_positions"] = [train, {**train, "direction": "E"}]
        pin.async_feed_updated()
        await pin.async_finish_pending_alerts()
        assert len(event.events) == 2

        # A return to live data for the correct run produces exactly one alert.
        veh.data["vehicle_positions"] = [train]
        pin.async_feed_updated()
        await pin.async_finish_pending_alerts()
        assert event.events[-1][0] == "destination_next"
        assert event.events[-1][1]["destination"] == "Burlington"

        event.remove()
        restored = runtime.Pin(hass, entry, dep, veh)
        await restored.async_load()
        restored_event = runtime.Event(restored, entry)
        await restored_event.async_added_to_hass()
        restored.async_feed_updated()
        await restored.async_finish_pending_alerts()
        assert restored_event.events == []
        assert restored.pin["trip_number"] == "1234"
        assert "_commute" not in runtime.Select(restored, entry).extra_state_attributes

    asyncio.run(scenario())
