# Alarm Clock — Architecture & Tech Stack

## Overview

The alarm clock runs on a **Raspberry Pi 3** with the official touchscreen display.
The software is split into two layers that communicate over a local WebSocket connection:

- **Python backend** — handles all hardware, logic, and external integrations
- **HTML/JS frontend** — handles all display and user interaction in a Chromium kiosk

---

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        Raspberry Pi 3                        │
│                                                             │
│  ┌─────────────────────────┐   ┌─────────────────────────┐ │
│  │     Python Backend      │   │   Chromium Kiosk        │ │
│  │                         │   │   (HTML/JS Frontend)    │ │
│  │  ┌─────────────────┐    │   │                         │ │
│  │  │   FastAPI +     │◄───┼───┼──► WebSocket (localhost)│ │
│  │  │   Uvicorn       │    │   │                         │ │
│  │  └─────────────────┘    │   │  ┌──────────────────┐   │ │
│  │                         │   │  │  Clock Face UI   │   │ │
│  │  ┌─────────────────┐    │   │  ├──────────────────┤   │ │
│  │  │  Alarm Logic    │    │   │  │  Settings UI     │   │ │
│  │  ├─────────────────┤    │   │  ├──────────────────┤   │ │
│  │  │  Hardware Layer │    │   │  │  Weather Widget  │   │ │
│  │  ├─────────────────┤    │   │  ├──────────────────┤   │ │
│  │  │  HA Client      │    │   │  │  HA Dashboard    │   │ │
│  │  ├─────────────────┤    │   │  │  (iframe)        │   │ │
│  │  │  Config (YAML)  │    │   │  └──────────────────┘   │ │
│  │  ├─────────────────┤    │   │                         │ │
│  │  │  OTA Updater    │    │   └─────────────────────────┘ │
│  │  └─────────────────┘    │                               │
│  └─────────────────────────┘                               │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                    Hardware (GPIO / I2C)              │  │
│  │  DS3231 RTC │ BH1750 Light Sensor │ Snooze Button    │  │
│  │  Buzzer (PWM) │ WS2812B LED Strip                    │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
          │                            │
          ▼                            ▼
┌──────────────────┐       ┌──────────────────────┐
│  NTP Time Server │       │    Home Assistant     │
│  (chrony)        │       │                       │
└──────────────────┘       │  - Weather entities   │
                           │  - Music Assistant    │
                           │  - MQTT Discovery     │
                           │  - Lovelace Dashboard │
                           └──────────────────────┘
```

---

## Frontend ↔ Backend Communication

All communication between the HTML/JS frontend and Python backend uses **WebSocket** on localhost.
Python pushes state to the browser; the browser sends user actions back to Python.

### Python → Browser (push)
| Message | Payload | Description |
|---|---|---|
| `time_update` | time, date, day | Current time, date, day of week |
| `brightness_update` | level (0–100) | New brightness level from light sensor |
| `weather_update` | temp, condition, high, low | Weather data from HA |
| `alarm_state` | alarms list, next_alarm_label | All alarm configs + next alarm human label |
| `alarm_firing` | alarm label, time | Alarm is going off — trigger alert UI |
| `alarm_snoozed` | resume_time | Alarm snoozed — show resume time |
| `alarm_dismissed` | — | Alarm stopped — return to clock face |
| `ota_status` | status, message | Progress/result of OTA update |

### Browser → Python (send)
| Message | Payload | Description |
|---|---|---|
| `snooze` | — | User tapped snooze button or on-screen button |
| `dismiss` | — | User dismissed the alarm |
| `settings_save` | full settings object | Updated settings from settings screen; Python saves to YAML and reschedules |
| `ota_trigger` | — | User requested OTA update |
| `switch_view` | view name | Switch between clock, settings, HA dashboard |

---

## Alarm Logic Design

Alarm scheduling runs entirely in Python for reliability — it does not depend on Home Assistant being available.

### next_alarm() function
`alarm.py` exposes a `next_alarm()` function that:
- Iterates all enabled alarms and their configured days
- Finds the soonest future firing time from now
- Returns a human-readable label:

| Condition | Label example |
|---|---|
| Fires later today | "Today at 6:00 AM" |
| Fires tomorrow | "Tomorrow at 6:00 AM" |
| Fires in 2–6 days | "Monday at 7:30 AM" |
| No enabled alarms | "No alarm set" |

This label is included in every `alarm_state` WebSocket push, and recalculated whenever alarms are updated or at midnight.

### Alarm state machine
```
IDLE → SUNRISE (if enabled, ramp_minutes before alarm time)
     → FIRING  (at alarm time — plays music or buzzer)
     → SNOOZED (on snooze — resumes after snooze_duration_minutes)
     → IDLE    (on dismiss or after max snooze count)
```

### HA exposure via MQTT
| Entity | Type | Description |
|---|---|---|
| `switch.alarm_clock_weekday` | Switch | Enable/disable weekday alarm |
| `switch.alarm_clock_weekend` | Switch | Enable/disable weekend alarm |
| `sensor.alarm_clock_next` | Sensor | Next alarm label string |
| `binary_sensor.alarm_clock_firing` | Binary sensor | True while alarm is active |

---

## UI Screens

### Screen 1 — Clock Face
```
┌─────────────────────────────────┐
│       Monday, June 23           │
│                                 │
│           6:42 AM               │
│                                 │
│  🌤  72°F   High 78 / Low 61   │
│                                 │
│    ⏰ Tomorrow at 6:00 AM       │
│                                 │
│  [ ⚙ Settings ]  [ 🏠 Dashboard ]│
└─────────────────────────────────┘
```

### Screen 2 — Alarm Firing
```
┌─────────────────────────────────┐
│           6:00 AM               │
│                                 │
│         🔔 WAKE UP!             │
│                                 │
│  [ 💤 SNOOZE ]   [ ✕ DISMISS ] │
└─────────────────────────────────┘
```

### Screen 3 — Settings
```
┌─────────────────────────────────┐
│  ⚙ Settings              [Back] │
├─────────────────────────────────┤
│  ALARMS                         │
│  Weekdays  [ON]  06:30          │
│  M  T  W  T  F  ✓ ✓ ✓ ✓ ✓    │
│  Source: Morning Playlist        │
│                                 │
│  Weekends  [ON]  08:00          │
│  S  S  ✓ ✓                      │
│  Source: Weekend Playlist        │
│  [+ Add Alarm]                  │
├─────────────────────────────────┤
│  GENERAL                        │
│  Snooze duration      9 min     │
│  Volume ramp          2 min     │
│  Display format       12hr      │
│  Timezone    America/New_York   │
├─────────────────────────────────┤
│  DISPLAY                        │
│  Auto-dim             [ON]      │
│  Min brightness       10%       │
├─────────────────────────────────┤
│  SUNRISE EFFECT                 │
│  Enabled              [ON]      │
│  Ramp duration        20 min    │
├─────────────────────────────────┤
│       [ 💾 Save Settings ]      │
└─────────────────────────────────┘
```



| Layer | Technology | Notes |
|---|---|---|
| OS | Raspberry Pi OS Lite | Minimal footprint; Openbox for kiosk windowing |
| Backend language | Python 3.11+ | Main application runtime |
| Backend server | FastAPI + Uvicorn | REST endpoints + WebSocket server |
| Frontend | HTML5 / CSS3 / Vanilla JS | No framework needed; keeps it simple |
| HA Dashboard | Chromium iframe | Points to Lovelace URL |
| HA Integration | MQTT Discovery + HA WebSocket API | Device registration + entity polling |
| Time Sync | chrony (NTP) | Syncs system clock from NTP pool |
| RTC | DS3231 over I2C | Fallback when NTP unavailable; updated by chrony |
| Light Sensor | BH1750 over I2C | Auto-dimming; shares I2C bus with DS3231 |
| LED Sunrise | WS2812B via rpi_ws281x | GPIO PWM, requires root or udev rule |
| Audio (primary) | Music Assistant via HA service call | HA triggers playback on alarm |
| Audio (fallback) | GPIO buzzer via RPi.GPIO PWM | Fires if Music Assistant unavailable |
| Config | YAML file | Loaded at startup; written back by settings UI |
| Process manager | systemd | Auto-start, restart on crash, logging |
| OTA Updates | git pull + systemd restart | Triggered via MQTT message or UI button |

---

## Key Python Libraries

| Library | Purpose |
|---|---|
| `fastapi` | REST API and WebSocket server |
| `uvicorn` | ASGI server to run FastAPI |
| `websockets` | WebSocket client (for HA connection) |
| `RPi.GPIO` | GPIO control — snooze button, buzzer PWM |
| `smbus2` | I2C communication — DS3231, BH1750 |
| `adafruit-circuitpython-ds3231` | RTC read/write |
| `adafruit-circuitpython-bh1750` | Light sensor readings |
| `rpi_ws281x` | WS2812B LED strip control |
| `pyyaml` | Load and save YAML config file |
| `paho-mqtt` | MQTT client for HA Discovery and messaging |
| `python-dateutil` | Timezone and DST handling |
| `asyncio` | Async task management across all subsystems |

---

## Project Structure

```
alarm-clock/
├── backend/
│   ├── main.py              # FastAPI app, WebSocket server, startup
│   ├── alarm.py             # Alarm scheduling and firing logic
│   ├── hardware.py          # GPIO, buzzer, light sensor, RTC
│   ├── leds.py              # Sunrise LED effect
│   ├── ha_client.py         # Home Assistant API integration
│   ├── config.py            # Load/save YAML config
│   └── updater.py           # OTA git pull logic
├── frontend/
│   ├── index.html           # Main clock face
│   ├── settings.html        # Settings screen
│   ├── dashboard.html       # HA dashboard iframe wrapper
│   ├── css/
│   │   └── styles.css       # Shared styles, theme, animations
│   └── js/
│       ├── clock.js         # Time display, WebSocket client
│       ├── alarm.js         # Alarm UI, snooze handling
│       ├── weather.js       # Weather widget rendering
│       └── settings.js      # Settings form logic
├── config/
│   └── settings.yaml        # All user-configurable settings
├── systemd/
│   └── alarm-clock.service  # systemd unit file
└── README.md
```

---

## Hardware Connections

| Component | Interface | Pin(s) |
|---|---|---|
| DS3231 RTC | I2C | SDA (GPIO2), SCL (GPIO3) |
| BH1750 Light Sensor | I2C | SDA (GPIO2), SCL (GPIO3) |
| Snooze Button | GPIO | GPIO17 (pull-up, active low) |
| Buzzer | GPIO PWM | GPIO18 (hardware PWM) |
| WS2812B LED Strip | GPIO PWM | GPIO12 (PWM0, requires root) |
| RPi Touchscreen | DSI | DSI connector |

---

## Suggested Build Order

| Phase | Description |
|---|---|
| 1 | Python backend skeleton — FastAPI, WebSocket, config loading |
| 2 | Clock face UI — time display, WebSocket client, basic styling |
| 3 | Hardware layer — RTC, light sensor, GPIO snooze button, buzzer |
| 4 | Alarm logic — scheduling, firing, snooze, Music Assistant trigger |
| 5 | Home Assistant integration — MQTT discovery, weather polling |
| 6 | Sunrise LED effect |
| 7 | Settings UI — form, save back to YAML |
| 8 | HA dashboard idle/embed screen |
| 9 | OTA update mechanism |

---

## Configuration File (settings.yaml — example)

```yaml
clock:
  timezone: "America/New_York"
  display_format: "12hr"       # 12hr or 24hr
  show_seconds: true

display:
  auto_dim: true
  dim_min_brightness: 10       # % brightness floor at night
  dim_max_brightness: 100      # % brightness ceiling in daylight
  dim_low_lux: 20              # lux threshold to start dimming
  dim_high_lux: 300            # lux threshold for full brightness

alarms:
  - label: "Weekdays"
    time: "06:30"
    days: [mon, tue, wed, thu, fri]
    enabled: true
    sound: music_assistant
    music_uri: "media-source://music_assistant/playlist/morning"
  - label: "Weekends"
    time: "08:00"
    days: [sat, sun]
    enabled: true
    sound: music_assistant
    music_uri: "media-source://music_assistant/playlist/morning"

audio:
  volume_start: 20             # % volume when alarm starts
  volume_max: 80               # % volume ceiling
  volume_ramp_seconds: 120     # seconds to ramp from start to max
  fallback_buzzer: true        # use buzzer if Music Assistant unavailable

snooze:
  duration_minutes: 9

sunrise:
  enabled: true
  ramp_minutes: 20             # how long before alarm to start
  max_brightness: 255

weather:
  enabled: true
  ha_temp_entity: "sensor.outdoor_temperature"
  ha_condition_entity: "weather.home"
  refresh_interval_seconds: 300

home_assistant:
  url: "http://homeassistant.local:8123"
  token: ""                    # Long-lived access token
  mqtt_broker: "homeassistant.local"
  mqtt_port: 1883

ota:
  git_branch: "main"
  auto_check: false
```

---

*Document version: 1.1 — June 2026*
