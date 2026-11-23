"""Regression tests for safe GO Transit request errors and diagnostic exports."""
import asyncio
import importlib
import json
import sys
from datetime import timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

SYNTHETIC_KEY = "synthetic-metrolinx-test-credential"
ROOT = Path(__file__).parents[1] / "custom_components" / "go_transit"


@pytest.fixture
def integration(monkeypatch):
    """Import the integration modules with only the HA interfaces they use here."""

    def stub(name, **attrs):
        module = ModuleType(name)
        vars(module).update(attrs)
        monkeypatch.setitem(sys.modules, name, module)
        return module

    class ConfigFlow:
        def __init_subclass__(cls, *, domain):
            super().__init_subclass__()

        def async_show_form(self, **result):
            return result

    class UpdateFailed(RuntimeError):
        pass

    class ClientError(Exception):
        pass

    package = stub("go_privacy_test", __path__=[str(ROOT)])
    dt = stub("homeassistant.util.dt")
    stub("homeassistant", __path__=[])
    entries = stub("homeassistant.config_entries", ConfigFlow=ConfigFlow, ConfigEntry=object, OptionsFlow=object)
    sys.modules["homeassistant"].config_entries = entries
    stub("homeassistant.core", HomeAssistant=object, callback=lambda fn: fn)
    stub("homeassistant.helpers", __path__=[], selector=object)
    stub("homeassistant.helpers.aiohttp_client", async_get_clientsession=lambda hass: None)
    stub("homeassistant.helpers.update_coordinator", DataUpdateCoordinator=object, UpdateFailed=UpdateFailed)
    stub("homeassistant.data_entry_flow", FlowResult=dict)
    stub("homeassistant.util", __path__=[], dt=dt)
    stub("voluptuous", Schema=dict, Required=lambda key: key)
    http = stub("aiohttp", ClientError=ClientError, ClientSession=object, ClientTimeout=dict)
    try:
        yield SimpleNamespace(
            flow=importlib.import_module(f"{package.__name__}.config_flow"),
            coordinator=importlib.import_module(f"{package.__name__}.coordinator"),
            diagnostics=importlib.import_module(f"{package.__name__}.diagnostics"),
            http=http,
        )
    finally:
        for module in list(sys.modules):
            if module.startswith(f"{package.__name__}."):
                del sys.modules[module]


class Session:
    def __init__(self, *, status=200, body="", error=None):
        self.status = status
        self.body = body
        self.error = error

    def get(self, url, *, params, timeout):
        assert params == {"key": SYNTHETIC_KEY}
        return self

    async def text(self):
        return self.body

    async def __aenter__(self):
        if self.error:
            raise self.error
        return self

    async def __aexit__(self, *args):
        pass


@pytest.mark.parametrize(
    ("status", "body", "incoming_error", "expected"),
    [
        (503, SYNTHETIC_KEY, None, "cannot_connect"),
        (200, SYNTHETIC_KEY, None, "cannot_connect"),
        (200, json.dumps({"Metadata": {"ErrorCode": "403", "ErrorMessage": SYNTHETIC_KEY}}), None, "invalid_auth"),
        (200, "", "ClientError", "cannot_connect"),
    ],
)
def test_setup_logs_omit_credentials(integration, monkeypatch, caplog, status, body, incoming_error, expected):
    error = integration.http.ClientError(SYNTHETIC_KEY) if incoming_error else None
    if error:
        class ConnectingSession(Session):
            def get(self, *args, **kwargs):
                raise error
        session = ConnectingSession()
    else:
        session = Session(status=status, body=body)
    monkeypatch.setattr(integration.http, "ClientSession", lambda: session)

    result = asyncio.run(integration.flow.GoTransitConfigFlow().async_step_user({"api_key": SYNTHETIC_KEY}))
    assert result["errors"] == {"base": expected}
    assert SYNTHETIC_KEY not in caplog.text


@pytest.mark.parametrize("transport_error", [False, True])
def test_poll_errors_omit_credentials(integration, transport_error):
    error = integration.http.ClientError(SYNTHETIC_KEY) if transport_error else None
    session = Session(body=SYNTHETIC_KEY, error=error)
    with pytest.raises(integration.coordinator.UpdateFailed) as caught:
        asyncio.run(integration.coordinator._api_get(session, SYNTHETIC_KEY, f"fixture/{SYNTHETIC_KEY}"))
    assert SYNTHETIC_KEY not in str(caught.value)
    assert caught.value.__suppress_context__


def test_diagnostics_only_export_poll_health(integration):
    health = SimpleNamespace(
        last_update_success=False,
        last_successful_request="2026-11-23T07:00:00-05:00",
        last_exception=RuntimeError(SYNTHETIC_KEY),
        update_interval=timedelta(seconds=120),
        _consecutive_failures=1,
        data={"from_stop": "Private station"},
        last_raw={"echo": SYNTHETIC_KEY},
    )
    feeds = ("departures", "vehicles", "alerts", "consist", "guarantee")
    hass = SimpleNamespace(data={"go_transit": {"route": dict.fromkeys(feeds, health)}})
    entry = SimpleNamespace(entry_id="route", data={"api_key": SYNTHETIC_KEY}, options={"route": "Private station"})

    report = asyncio.run(integration.diagnostics.async_get_config_entry_diagnostics(hass, entry))
    assert report == {"coordinators": dict.fromkeys(feeds, {
        "last_update_success": False,
        "last_successful_request": "2026-11-23T07:00:00-05:00",
        "last_error_type": "RuntimeError",
        "update_interval_seconds": 120,
        "consecutive_failures": 1,
    })}
