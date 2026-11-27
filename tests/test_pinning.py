"""Train pin lifecycle and tracker regressions without a Home Assistant install."""
import asyncio
import importlib.util
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1] / "custom_components" / "go_transit"
sys.path.insert(0, str(ROOT))
from pinning import UNPINNED, active_pin, departure_options, make_pin, match_train

NOW = datetime(2026, 10, 11, 23, 55, tzinfo=timezone.utc)
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
        def __init__(self, *args, **kwargs):
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
    return types.SimpleNamespace(Coordinator=Coordinator, Pin=pinned.PinnedTrainCoordinator,
                                 Tracker=tracker.GoTransitTrainTracker,
                                 Select=select.GoTransitPinnedTrainSelect, Sensor=sensor.GoTransitPinnedTrainStatusSensor)


def test_pin_restore_clear_and_tracker_does_not_jump(runtime):
    async def scenario():
        dep, veh = runtime.Coordinator(), runtime.Coordinator()
        dep.data = {"next_departure": DEPARTURE, "departures": [DEPARTURE]}
        veh.data = {"vehicle_positions": [{"trip_number": "1234", "latitude": 43, "longitude": -79},
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
        veh.data = {"vehicle_positions": []}
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
