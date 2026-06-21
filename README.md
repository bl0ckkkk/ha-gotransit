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

Once installed, the integration creates a **device per monitored route** in Home Assistant, each with seven sensors, a catchable binary sensor, and a live train tracker:

| Sensor | What it shows |
|--------|--------------|
| **Next Departure** | The next train's departure time from your boarding station (actual time if available, scheduled otherwise) |
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

The integration uses three independent coordinators, each with a different polling rate to minimise API calls:

| Data | Endpoint | Poll rate |
|------|----------|-----------|
| Next departure + schedule | `Stop/NextService` + `Schedule/Journey` | Every **2 minutes** |
| Vehicle positions | `ServiceataGlance/Trains/All` | Every **30 seconds** during your commute window; every **5 minutes** outside it |
| Service alerts | `ServiceUpdate/ServiceAlert/All` | Every **15 minutes** |
| Train consist | `Fleet/Consist/All` | Every **5 minutes** |
| Service guarantee | `ServiceUpdate/ServiceGuarantee` | Every **5 minutes** |

**Smart polling:** Departure, consist, and guarantee coordinators **pause entirely outside service hours** (no trains = no calls). All coordinators **back off automatically** after repeated failures (protecting your API key from rate-limit disabling).

**Estimated daily API calls (1 route, 5hr commute window): ~1,644** — well within the undocumented Metrolinx limits.

The commute window is configurable at setup and can be changed anytime via the integration's ⚙️ Options menu.

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
| **Boarding Station** | ✅ | Dropdown populated live from the API — every GO stop |
| **Destination Station** | ✅ | Same list |
| **Line** | ❌ | Filters all sensors to this line only. Leave blank to get the next available train regardless of line |
| **Upcoming departures to fetch** | ❌ | 1–10, default 5 |
| **Commute window start** | ❌ | HH:MM format, default `05:00` |
| **Commute window end** | ❌ | HH:MM format, default `10:00` |

---

## Sensor details

### Next Departure
**State:** Departure time as `HH:MM` (actual if the train is running, scheduled otherwise). `None` outside service hours.

**Attributes:**
```yaml
trip_number: "1234"
destination: "Union Station"
scheduled_time: "07:12"
actual_time: "07:19"
delay_minutes: 7
status: "Delayed"
platform: "2"
line: "Lakeshore West"
updated_at: "2026-06-20T07:08:34.112"
```

---

### Delay
**State:** Integer minutes late. `0` means on time.

**Attributes:**
```yaml
trip_number: "1234"
status: "Delayed"
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
  - trip_number: "1234"
    direction: "Inbound"
    latitude: 43.3841
    longitude: -79.8053
    next_stop: "OA"
    status: "On Time"
    delay_minutes: 0
updated_at: "2026-06-20T07:09:01.883"
```

> **Note:** Latitude/longitude availability depends on what Metrolinx populates in their API. Fields may be `null` for some trips.

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
- **Delay data:** Delay is computed from `ScheduledTime` vs `ActualTime` when a dedicated delay field isn't present. Outside active service hours, delay sensors return `0`.
- **Schedule only outside service hours:** The `Stop/NextService` endpoint returns nothing when no trains are running. `Next Departure` will show `unavailable` overnight.

---

## Troubleshooting

The integration ships with a HA diagnostics endpoint that dumps everything useful in one download:

1. Settings → Devices & Services → GO Transit → ⋮ → **Download diagnostics**
2. The JSON file contains:
   - Your config (API key redacted)
   - Raw API responses from all three coordinators
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
| `GET /api/V1/ServiceUpdate/ServiceAlert/All` | Service alerts sensor |
| `GET /api/V1/ServiceataGlance/Trains/All` | Active trains / vehicle positions sensor |

---

## Credits

Built for Home Assistant by [bl0ck](https://github.com/bl0ckkkk). Data provided by [Metrolinx / GO Transit](https://www.metrolinx.com) via the [OpenMetrolinx Open Data API](https://api.openmetrolinx.com).

Not affiliated with or endorsed by Metrolinx.
