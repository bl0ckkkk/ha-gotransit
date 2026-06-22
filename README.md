```
 __  __       _              _  _            
|  \/  | ___ | |_  _ _  ___ | |(_) _ _  __ __
| |\/| |/ -_)|  _|| '_|/ _ \| || || ' \ \ \ /
|_|  |_|\___| \__||_|  \___/|_||_||_||_|/_\_\
```

# GO Transit — Home Assistant Integration

A HACS-compatible custom integration that brings live GO Transit data into Home Assistant via the [OpenMetrolinx API](https://api.openmetrolinx.com/OpenDataAPI/Help/Index/en). Monitor departures, delays, service alerts, and active train positions for any route — with smart adaptive polling to stay well within API limits.

---

## What it does

Once installed, the integration creates a **device per monitored route** in Home Assistant, each with nine sensors, a catchable binary sensor, and a live train tracker:

| Sensor | What it shows |
|--------|--------------|
| **Next Departure** | The next train's departure as a timestamp — Home Assistant renders it as the clock time plus a relative "in X minutes" countdown |
| **Platform** | The boarding platform for your next train (actual track once posted, scheduled otherwise) |
| **Status** | Human-readable `On time` / `Delayed` / `Cancelled` for your next train |
| **Delay** | How many minutes late the next train is (0 = on time) |
| **Upcoming Departures** | A count of upcoming trips with the full schedule list in attributes |
| **Service Alerts** | Count of active alerts affecting your line, with full alert details in attributes |
| **Active Trains** | Number of trains currently running on your line, with position data in attributes |
| **Train Consist** | Coach count for your next train (e.g. 10 or 12), with the full car lineup in attributes |
| **Service Guarantee** | Whether GO's delay refund guarantee applies to your trip |
| **Catchable** (binary) | `On` when you can still make the next train from your platform, given live travel time |
| **Train** (device_tracker) | Live position of your train on HA's map |

You can monitor **multiple routes simultaneously** — just add the integration again for each one. Each entry is fully independent.

---

## How polling works

The integration uses five independent coordinators, each with a different polling rate to minimise API calls:

| Data | Endpoint | Poll rate |
|------|----------|-----------|
| Next departure + schedule | `Stop/NextService` + `Schedule/Journey` + `ServiceUpdate/Exceptions` | Every **2 minutes** |
| Vehicle positions | `ServiceataGlance/Trains/All` | Every **30 seconds** during your commute window; every **5 minutes** outside it |
| Service alerts | `ServiceUpdate/ServiceAlert/All` | Every **15 minutes** |
| Train consist | `Fleet/Consist/All` | Every **5 minutes** |
| Service guarantee | `ServiceUpdate/ServiceGuarantee` | Every **5 minutes** |

**Smart polling:** Departure, consist, and guarantee coordinators **pause entirely outside service hours** (no trains = no calls). All coordinators **back off automatically** after repeated failures (protecting your API key from rate-limit disabling).

**Estimated daily API calls (1 route, 5hr commute window): ~1,644** — well within the undocumented Metrolinx limits.

The commute window and service hours are configurable at setup and can be changed anytime via the integration's ⚙️ Options menu.

---

## Installation

### Via HACS (recommended)
1. In HACS → Integrations → ⋮ → **Custom repositories**
2. Add this repo URL, category: **Integration**
3. Install **GO Transit** → restart Home Assistant
4. Settings → Devices & Services → **+ Add Integration** → search **GO Transit**

### Manual
1. Copy `custom_components/go_transit/` into your HA config at `config/custom_components/go_transit/`
2. Restart Home Assistant
3. Settings → Devices & Services → **+ Add Integration** → search **GO Transit**

---

## Setup

The config flow is two steps:

### Step 1 — API Key
Enter your OpenMetrolinx API key. The integration will immediately call the GO API to validate it and fetch your live station and line lists.

> Register free at https://api.openmetrolinx.com/OpenDataAPI/Help/Registration/en
> Note: registration is processed manually and can take up to 10 business days.

### Step 2 — Route & Schedule

| Field | Required | Description |
|-------|----------|-------------|
| **Boarding Station** | ✅ | Dropdown populated live from the API — every GO rail stop |
| **Destination Station** | ✅ | Same list |
| **Line** | ❌ | Filters all sensors to this line only. Leave blank to get the next available train regardless of line |
| **Upcoming departures to fetch** | ❌ | 1–10, default 5 |
| **Commute window start** | ❌ | HH:MM format, default `05:00` |
| **Commute window end** | ❌ | HH:MM format, default `10:00` |
| **Travel time sensor** | ❌ | HA entity ID (e.g. `sensor.commute_time`) whose state is travel minutes to your station. Used by the Catchable sensor |
| **Travel time (fixed)** | ❌ | Fallback travel time in minutes if no sensor is set or it's unavailable. Default `10` |
| **Service hours start** | ❌ | HH:MM — departure/consist/guarantee coordinators pause before this. Default `05:00` |
| **Service hours end** | ❌ | HH:MM — same coordinators pause after this. Default `01:30` (overnight window) |

All fields except boarding and destination stations can be changed anytime via the ⚙️ Options menu.

---

## Sensor details

### Next Departure
**State:** The next departure as a **timestamp** (`device_class: timestamp`) — a full timezone-aware datetime, which Home Assistant displays as the clock time plus a relative "in X minutes" countdown. Computed (live) time if the train is running, scheduled otherwise. `unavailable` outside service hours. The bare `HH:MM` values remain available as the `scheduled_time` / `computed_time` attributes.

**Attributes:**
```yaml
trip_number: "1234"
destination: "Union Station"
line: "Lakeshore West"
service_type: "Train"
direction: "LSW"
scheduled_time: "07:12"
computed_time: "07:19"
departure_status: "Delayed"
scheduled_platform: "2"
actual_platform: "2"
status: "Delayed"
delay_minutes: 7
is_cancelled: false
stop_is_cancelled: false
stop_is_stopping: true
latitude: 43.3841
longitude: -79.8053
update_time: "07:08"
updated_at: "2026-06-20T07:08:34.112"
```

---

### Platform
**State:** The boarding platform for your next train — the actual track once Metrolinx posts it, falling back to the scheduled platform. `None` if neither is known yet.

**Attributes:**
```yaml
scheduled_platform: "3"
actual_platform: "2"
track_confirmed: true   # true once the actual platform is assigned
trip_number: "1234"
updated_at: "2026-06-20T07:08:34.112"
```

> Tip: trigger a "your platform is posted" notification on `track_confirmed` flipping to `true`, or on the state changing.

---

### Status
**State:** Human-readable `On time` / `Delayed` / `Cancelled` (`Unknown` when there's no upcoming train). Derived from cancellation and delay rather than the API's cryptic status codes (`device_class: enum`).

**Attributes:**
```yaml
delay_minutes: 7
departure_status: "E"      # raw API code
raw_status: "S"            # raw API code
is_cancelled: false
stop_is_cancelled: false
trip_number: "1234"
updated_at: "2026-06-20T07:08:34.112"
```

---

### Delay
**State:** Integer minutes late. `0` means on time.

**Attributes:**
```yaml
trip_number: "1234"
departure_status: "Delayed"
status: "Delayed"
is_cancelled: false
```

---

### Upcoming Departures
**State:** Integer count of upcoming trips fetched.

**Attributes:**
```yaml
from: "Burlington"
to: "Union Station"
departures:
  - trip_number: "1234"
    departure_time: "07:12"
    arrival_time: "08:14"
    duration: "62 min"
    line: "Lakeshore West"
    status: "Scheduled"
  - trip_number: "1236"
    departure_time: "07:42"
    ...
updated_at: "2026-06-20T07:08:34.112"
```

---

### Service Alerts
**State:** Integer count of active alerts for your line (plus system-wide alerts with no line specified). `0` = no alerts.

**Attributes:**
```yaml
alerts:
  - id: "ALT-9921"
    header: "Lakeshore West — Delays Expected"
    description: "Due to a mechanical issue near Oakville, trains are running 10–15 minutes late."
    effect: "SIGNIFICANT_DELAYS"
    start: "2026-06-20T06:30:00"
    end: "2026-06-20T09:00:00"
updated_at: "2026-06-20T07:00:12.004"
```

---

### Active Trains
**State:** Integer count of trains currently running on your line.

**Attributes:**
```yaml
in_commute_window: true
poll_interval_seconds: 30
trains:
  - trip_number: "1636"
    direction: "E"            # VariantDir: E/W/N/S
    destination: "LW - Union Station"
    latitude: 43.3841
    longitude: -79.8053
    next_stop: "WATE"
    at_station: "AL"          # null when between stops
    in_motion: true
    cars: "12"
    status: "In motion"       # "In motion" / "Stopped"
    delay_minutes: 4          # derived from DelaySeconds
updated_at: "2026-06-20T07:09:01.883"
```

> **Note:** Coordinates use `-1.0` as a "no GPS" sentinel in the API; those are normalised to `null`.

---

### Train Consist
**State:** Integer coach count (e.g. `10`). `None` if not yet matched.

**Attributes:**
```yaml
trip_number: "1234"
consist_number: "C42"
engine_number: "912"
lineup:
  - order: 1
    type: "Locomotive"
    number: "912"
  - order: 2
    type: "BiLevel Coach"
    number: "2341"
updated_at: "2026-06-20T07:05:00.000"
```

---

### Service Guarantee
**State:** `Active` or `Not active`.

**Attributes:**
```yaml
trip_number: "1234"
reason: "Train delayed more than 15 minutes"
affected_stops:
  - stop_code: "BU"
    scope: "Boarding"
    reason: "Train delayed more than 15 minutes"
updated_at: "2026-06-20T07:05:00.000"
```

---

### Catchable (binary sensor)
**State:** `On` when you can still make the next train from your boarding platform.

Logic: `minutes_to_departure >= travel_minutes + 2 min buffer`. Cancelled trains always return `On` (redirect to next departure). Defaults to `On` when data is missing (fail-open — don't tell someone they've missed a train when uncertain).

**Attributes:**
```yaml
minutes_to_departure: 14
travel_minutes: 10
departure_time: "2026-06-20 07:19:00"
trip_number: "1234"
is_cancelled: false
travel_sensor: "sensor.commute_time"
updated_at: "2026-06-20T07:08:34.112"
```

---

## Example automations

### Notify if your train is delayed at departure time
```yaml
automation:
  - alias: "GO Train delay alert"
    trigger:
      - platform: time
        at: "06:50:00"
    condition:
      - condition: numeric_state
        entity_id: sensor.go_burlington_union_delay
        above: 4
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "GO Train delayed"
          message: >
            Train {{ state_attr('sensor.go_burlington_union_next_departure', 'trip_number') }}
            is running {{ states('sensor.go_burlington_union_delay') }} minutes late.
            New departure: {{ states('sensor.go_burlington_union_next_departure') }}.
```

### Alert when a service disruption is posted
```yaml
automation:
  - alias: "GO service alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.go_burlington_union_service_alerts
        above: 0
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "GO Transit alert"
          message: >
            {{ state_attr('sensor.go_burlington_union_service_alerts', 'alerts')[0]['header'] }}
```

---

## Known limitations

- **Vehicle positions:** The Metrolinx GTFS Realtime vehicle feed (`Gtfs/Feed/VehiclePosition`) returns protobuf binary — this integration does not parse it. Positions come from `ServiceataGlance/Trains/All` instead, which is JSON but may have null lat/lon for some trips.
- **Rate limits:** Metrolinx does not publish rate limit numbers. Their docs state keys can be disabled for "excessive" use. The tiered polling in this integration is conservative by design.
- **API field names:** The OpenMetrolinx API docs show sample field names that may not exactly match live responses. If sensors show `unknown`, use the diagnostics tool (below) to inspect the raw API response and open an issue.
- **Delay data:** Delay is computed from `ScheduledDepartureTime` vs `ComputedDepartureTime` when a dedicated delay field isn't present. Outside active service hours, delay sensors return `0`.
- **Schedule only outside service hours:** The `Stop/NextService` endpoint returns nothing when no trains are running. `Next Departure` will show `unavailable` overnight.

---

## Troubleshooting

The integration ships with a HA diagnostics endpoint that dumps everything useful in one download:

1. Settings → Devices & Services → GO Transit → ⋮ → **Download diagnostics**
2. The JSON file contains:
   - Your config (API key redacted)
   - Raw API responses from all five coordinators
   - Processed sensor data
   - Last error message per coordinator
   - Current poll intervals

Share this file (with any personal data removed) when opening an issue.

---

## API reference

This integration uses the following OpenMetrolinx endpoints:

| Endpoint | Used for |
|----------|----------|
| `GET /api/V1/Stop/All` | Populating station dropdowns at setup |
| `GET /api/V1/Schedule/Line/All/{date}` | Populating line dropdowns at setup |
| `GET /api/V1/Stop/NextService/{StopCode}` | Next departure sensor |
| `GET /api/V1/Schedule/Journey/{date}/{from}/{to}/{time}/{max}` | Upcoming departures sensor |
| `GET /api/V1/ServiceUpdate/Exceptions/All` | Trip cancellation / stop exception data |
| `GET /api/V1/ServiceUpdate/ServiceAlert/All` | Service alerts sensor |
| `GET /api/V1/ServiceataGlance/Trains/All` | Active trains / vehicle positions sensor |
| `GET /api/V1/Fleet/Consist/All` | Train consist sensor |
| `GET /api/V1/ServiceUpdate/ServiceGuarantee/{trip}/{date}` | Service guarantee sensor |

---

## Credits

Built for Home Assistant by [bl0ck](https://github.com/bl0ckkkk). Data provided by [Metrolinx / GO Transit](https://www.metrolinx.com) via the [OpenMetrolinx Open Data API](https://api.openmetrolinx.com).

Not affiliated with or endorsed by Metrolinx.
