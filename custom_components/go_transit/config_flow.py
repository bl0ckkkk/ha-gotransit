"""Config flow for GO Transit integration.

Step 1 — api_key  : Validate key, fetch live stops + lines
Step 2 — route    : Dynamic dropdowns + commute window
Options flow      : Adjust max_departures and commute window post-setup
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    BASE_URL,
    CONF_API_KEY,
    CONF_COMMUTE_END,
    CONF_COMMUTE_START,
    CONF_SERVICE_END,
    CONF_SERVICE_START,
    CONF_TRAVEL_TIME_FIXED,
    CONF_TRAVEL_TIME_SENSOR,
    DEFAULT_SERVICE_END,
    DEFAULT_SERVICE_START,
    DEFAULT_TRAVEL_TIME_FIXED,
    CONF_FROM_STOP,
    CONF_FROM_STOP_CODE,
    CONF_LINE_CODE,
    CONF_LINE_NAME,
    CONF_MAX_DEPARTURES,
    CONF_TO_STOP,
    CONF_TO_STOP_CODE,
    DEFAULT_COMMUTE_END,
    DEFAULT_COMMUTE_START,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def _api_get(api_key: str, path: str) -> Any:
    url = f"{BASE_URL}/{path}.json"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params={"key": api_key}, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                raise aiohttp.ClientError(f"HTTP {resp.status}")
            return await resp.json(content_type=None)


async def _fetch_stops(api_key: str) -> dict[str, str]:
    data = await _api_get(api_key, "Stop/All")
    stations = data.get("Stations", {}).get("Station", [])
    if isinstance(stations, dict):
        stations = [stations]
    result = {}
    for s in stations:
        name = s.get("LocationName", "").strip()
        code = s.get("LocationCode", "").strip()
        if name and code:
            result[name] = code
    return dict(sorted(result.items()))


async def _fetch_lines(api_key: str) -> dict[str, str]:
    today = datetime.now().strftime("%Y%m%d")
    data = await _api_get(api_key, f"Schedule/Line/All/{today}")
    lines = data.get("AllLines", {}).get("Line", [])
    if isinstance(lines, dict):
        lines = [lines]
    result = {}
    for line in lines:
        if not line.get("IsTrain", False):
            continue
        name = line.get("Name", "").strip()
        code = line.get("Code", "").strip()
        if name and code:
            result[name] = code
    return dict(sorted(result.items()))


def _time_validator(value: str) -> str:
    """Validate HH:MM format."""
    try:
        datetime.strptime(value, "%H:%M")
        return value
    except ValueError:
        raise vol.Invalid("Time must be in HH:MM format (e.g. 05:30)")


class GoTransitConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._api_key: str = ""
        self._stops: dict[str, str] = {}
        self._lines: dict[str, str] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            try:
                stops = await _fetch_stops(api_key)
                lines = await _fetch_lines(api_key)
                if not stops:
                    errors["base"] = "no_stops"
                else:
                    self._api_key = api_key
                    self._stops = stops
                    self._lines = lines
                    return await self.async_step_route()
            except aiohttp.ClientError:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
            description_placeholders={
                "register_url": "https://api.openmetrolinx.com/OpenDataAPI/Help/Registration/en"
            },
        )

    async def async_step_route(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        stop_names = list(self._stops.keys())
        line_names = list(self._lines.keys()) if self._lines else []

        if user_input is not None:
            from_name = user_input[CONF_FROM_STOP]
            to_name = user_input[CONF_TO_STOP]

            if from_name == to_name:
                errors["base"] = "same_stop"
            else:
                line_name = user_input.get(CONF_LINE_CODE, "")
                line_code = self._lines.get(line_name, "")
                title = f"GO — {from_name} \u2192 {to_name}"
                if line_name:
                    title += f" ({line_name})"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_API_KEY: self._api_key,
                        CONF_FROM_STOP: from_name,
                        CONF_FROM_STOP_CODE: self._stops[from_name],
                        CONF_TO_STOP: to_name,
                        CONF_TO_STOP_CODE: self._stops[to_name],
                        CONF_LINE_CODE: line_code,
                        CONF_LINE_NAME: line_name,
                        CONF_MAX_DEPARTURES: user_input.get(CONF_MAX_DEPARTURES, 5),
                        CONF_COMMUTE_START: user_input.get(CONF_COMMUTE_START, DEFAULT_COMMUTE_START),
                        CONF_COMMUTE_END: user_input.get(CONF_COMMUTE_END, DEFAULT_COMMUTE_END),
                        CONF_TRAVEL_TIME_SENSOR: user_input.get(CONF_TRAVEL_TIME_SENSOR, "").strip(),
                        CONF_TRAVEL_TIME_FIXED: user_input.get(CONF_TRAVEL_TIME_FIXED, DEFAULT_TRAVEL_TIME_FIXED),
                        CONF_SERVICE_START: user_input.get(CONF_SERVICE_START, DEFAULT_SERVICE_START),
                        CONF_SERVICE_END: user_input.get(CONF_SERVICE_END, DEFAULT_SERVICE_END),
                    },
                )

        schema_dict: dict = {
            vol.Required(CONF_FROM_STOP): vol.In(stop_names),
            vol.Required(CONF_TO_STOP): vol.In(stop_names),
        }
        if line_names:
            schema_dict[vol.Optional(CONF_LINE_CODE)] = vol.In(line_names)
        schema_dict.update({
            vol.Optional(CONF_MAX_DEPARTURES, default=5): vol.All(int, vol.Range(min=1, max=10)),
            vol.Optional(CONF_COMMUTE_START, default=DEFAULT_COMMUTE_START): _time_validator,
            vol.Optional(CONF_COMMUTE_END, default=DEFAULT_COMMUTE_END): _time_validator,
            vol.Optional(CONF_TRAVEL_TIME_SENSOR, default=""): str,
            vol.Optional(CONF_TRAVEL_TIME_FIXED, default=DEFAULT_TRAVEL_TIME_FIXED): vol.All(int, vol.Range(min=0, max=120)),
            vol.Optional(CONF_SERVICE_START, default=DEFAULT_SERVICE_START): _time_validator,
            vol.Optional(CONF_SERVICE_END, default=DEFAULT_SERVICE_END): _time_validator,
        })

        return self.async_show_form(
            step_id="route",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return GoTransitOptionsFlow(config_entry)


class GoTransitOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        data = self._config_entry.data
        opts = self._config_entry.options

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_MAX_DEPARTURES,
                    default=opts.get(CONF_MAX_DEPARTURES, data.get(CONF_MAX_DEPARTURES, 5)),
                ): vol.All(int, vol.Range(min=1, max=10)),
                vol.Optional(
                    CONF_COMMUTE_START,
                    default=opts.get(CONF_COMMUTE_START, data.get(CONF_COMMUTE_START, DEFAULT_COMMUTE_START)),
                ): _time_validator,
                vol.Optional(
                    CONF_COMMUTE_END,
                    default=opts.get(CONF_COMMUTE_END, data.get(CONF_COMMUTE_END, DEFAULT_COMMUTE_END)),
                ): _time_validator,
                vol.Optional(
                    CONF_TRAVEL_TIME_SENSOR,
                    default=opts.get(CONF_TRAVEL_TIME_SENSOR, data.get(CONF_TRAVEL_TIME_SENSOR, "")),
                ): str,
                vol.Optional(
                    CONF_TRAVEL_TIME_FIXED,
                    default=opts.get(CONF_TRAVEL_TIME_FIXED, data.get(CONF_TRAVEL_TIME_FIXED, DEFAULT_TRAVEL_TIME_FIXED)),
                ): vol.All(int, vol.Range(min=0, max=120)),
                vol.Optional(
                    CONF_SERVICE_START,
                    default=opts.get(CONF_SERVICE_START, data.get(CONF_SERVICE_START, DEFAULT_SERVICE_START)),
                ): _time_validator,
                vol.Optional(
                    CONF_SERVICE_END,
                    default=opts.get(CONF_SERVICE_END, data.get(CONF_SERVICE_END, DEFAULT_SERVICE_END)),
                ): _time_validator,
            }),
        )
