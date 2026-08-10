# Alarm Clock — Architecture & Tech Stack

## Overview

The alarm clock runs on a **Raspberry Pi 3B** with the official 7" touchscreen.
The software is split into two layers that communicate over a local WebSocket connection:

- **Python backend** — handles all hardware, logic, and external integrations
- **HTML/JS frontend** — handles all display and user interaction in a Chromium kiosk

---

## System Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                          Raspberry Pi 3B                          │
│                                                                  │
│  ┌──────────────────────────┐   ┌──────────────────────────────┐ │
│  │      Python Backend      │   │     Chromium Kiosk           │ │
│  │                          │   │     (HTML/JS Frontend)       │ │
│  │  ┌──────────────────┐    │   │                              │ │
│  │  │  FastAPI +       │◄───┼───┼──► WebSocket (localhost)     │ │
│  │  │  Uvicorn         │    │   │                              │ │
│  │  └──────────────────┘    │   │  ┌────────────────────────┐  │ │
│  │  ┌──────────────────┐    │   │  │  Clock Face UI          │  │ │
│  │  │  Alarm Logic     │    │   │  ├────────────────────────┤  │ │
│  │  ├──────────────────┤    │   │  │  Alarm Firing UI        │  │ │
│  │  │  Hardware Layer  │    │   │  ├────────────────────────┤  │ │
│  │  ├──────────────────┤    │   │  │  Settings UI            │  │ │
│  │  │  HA Client       │    │   │  ├────────────────────────┤  │ │
│  │  ├──────────────────┤    │   │  │  Weather Widget         │  │ │
│  │  │  Config (YAML)   │    │   │  ├────────────────────────┤  │ │
│  │  ├──────────────────┤    │   │  │  HA Dashboard (iframe)  │  │ │
│  │  │  OTA Updater     │    │   │  └────────────────────────┘  │ │
│  │  └──────────────────┘    │   └──────────────────────────────┘ │
│  └──────────────────────────┘                                    │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                  Hardware (GPIO / I2C / I2S)                │  │
│  │  DS3231 RTC (I2C)   │  BH1750 Light Sensor (I2C)           │  │
│  │  Snooze Button      │  Power Button                        │  │
│  │  Active Buzzer PWM  │  WS2812B LED Strip                   │  │
│  │  2× MAX98357A (I2S) │  2× Speakers (4Ω 3W enclosed)       │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
          │                                │
          ▼                                ▼
┌──────────────────┐           ┌──────────────────────┐
│  NTP Time Server │           │    Home Assistant     │
│  (chrony)        │           │  - Weather entities   │
└──────────────────┘           │  - Music Assistant    │
                               │  - MQTT Discovery     │
                               │  - Lovelace Dashboard │
                               └──────────────────────┘
```

---

## GPIO Pin Assignment

| Function | GPIO | Pi Pin | Notes |
|---|---|---|---|
| I2C SDA | GPIO2 | Pin 3 | DS3231 + BH1750 shared bus |
| I2C SCL | GPIO3 | Pin 5 | DS3231 + BH1750; also Power-on wake |
| I2S BCLK | GPIO18 | Pin 12 | Both MAX98357A amps |
| I2S LRCLK | GPIO19 | Pin 35 | Both MAX98357A amps |
| I2S DIN | GPIO20 | Pin 38 | Both MAX98357A amps |
| Snooze button | GPIO17 | Pin 11 | Active low, internal pull-up |
| Power shutdown | GPIO26 | Pin 37 | dtoverlay=gpio-shutdown,gpio_pin=26 |
| Power wake | GPIO3 | Pin 5 | Hardware feature, shared with I2C SCL |
| Buzzer | GPIO13 | Pin 33 | Hardware PWM1, fallback alarm tone |
| WS2812B data | GPIO12 | Pin 32 | Hardware PWM0, via 74AHCT125 level shifter |

> **Note:** GPIO18 is used for I2S BCLK — the buzzer was moved from GPIO18 to GPIO13 to avoid conflict.
> GPIO3 serves dual duty as I2C SCL and the Pi's hardware power-on wake pin — this is a Pi hardware feature and does not require software configuration.

---

## Audio Architecture

### Stereo Setup — Two MAX98357A Breakouts

Both MAX98357A boards share the same I2S bus from the Pi. The SD pin selects channel:

```
Pi I2S (GPIO18/19/20)
        │
        ├──────────────────────────────┐
        │                              │
  MAX98357A #1                   MAX98357A #2
  SD → 3.3V via 100kΩ            SD → GND via 100kΩ
  (Left channel)                  (Right channel)
        │                              │
  Speaker L                      Speaker R
  (Adafruit #4445)               (Adafruit #4445)
  4Ω 3W enclosed                 4Ω 3W enclosed
```

Output power: **3.2W per channel** into 4Ω at 5V.

### Volume Control
The MAX98357A has no I2C/SPI volume register. Volume is controlled via **ALSA softvol** in `/etc/asound.conf`. The Python backend calls `amixer` via subprocess or uses `alsaaudio` library.

### ALSA Configuration (`/etc/asound.conf`)
```
pcm.speakersafevol {
  type softvol
  slave.pcm "hw:0"
  control {
    name "Speaker"
    card 0
  }
  min_dB -90.0
  max_dB 0.0
}

pcm.!default {
  type plug
  slave.pcm "speakersafevol"
}
```

### I2S Device Tree Overlay (`/boot/config.txt`)
```
dtoverlay=hifiberry-dac
```

---

## Power Distribution Architecture

```
5V/4A Barrel Jack (on HAT)
        │
  [SS34 Schottky Diode]    ← reverse polarity protection
        │
  [Polyfuse 3.5A]          ← whole-system protection
        │
    5V Rail ───────────────────────────────────────┐
        │                                          │
        ├──[Polyfuse 2.5A]── Pi GPIO Pin 2 & 4    │
        │                                          │
        ├──[Polyfuse 2A]──── Display 5V (JST-PH)  │
        │                                          │
        └──[Polyfuse 2A]──── WS2812B strip 5V     │
                                                   │
                         Common GND ───────────────┘
```

### Power Button Circuit
- **Shutdown:** GPIO26 → 330Ω resistor → momentary button → GND
  - `/boot/config.txt`: `dtoverlay=gpio-shutdown,gpio_pin=26`
- **Power-on:** GPIO3 → 330Ω resistor → same or separate button → GND
  - Hardware feature of the Pi — no software needed
- **Power LED:** Green LED + 330Ω resistor from 3.3V

### Power Budget

| Component | Current |
|---|---|
| Raspberry Pi 3B | ~800mA |
| Official touchscreen | ~500mA |
| 2× MAX98357A + speakers | ~700mA peak |
| WS2812B LEDs (typical) | ~600mA |
| DS3231 + BH1750 + buzzer | ~50mA |
| **Total** | **~2.65A typical** |

5V/4A adapter provides comfortable headroom.

---

## Frontend ↔ Backend Communication

All communication uses **WebSocket** on localhost. Python pushes state; browser sends actions.

### Python → Browser (push)
| Message | Payload | Description |
|---|---|---|
| `time_update` | time, date, day | Current time, date, day of week |
| `brightness_update` | level (0–100) | New display brightness from light sensor |
| `weather_update` | temp, condition, high, low | Weather data from HA |
| `alarm_state` | alarms list, next_alarm_label | All alarm configs + next alarm label |
| `alarm_firing` | alarm label, time | Alarm firing — trigger alert UI |
| `alarm_snoozed` | resume_time | Alarm snoozed — show resume time |
| `alarm_dismissed` | — | Alarm stopped — return to clock face |
| `ota_status` | status, message | OTA update progress/result |

### Browser → Python (send)
| Message | Payload | Description |
|---|---|---|
| `snooze` | — | Snooze triggered (touch or physical button) |
| `dismiss` | — | Alarm dismissed |
| `settings_save` | full settings object | Save settings, reschedule alarms immediately |
| `ota_trigger` | — | Request OTA update |
| `switch_view` | view name | Navigate between clock/settings/dashboard |

---

## Alarm Logic Design

Alarm scheduling runs entirely in Python — independent of Home Assistant availability.

### next_alarm() function
Iterates all enabled alarms, finds the soonest future firing time, returns a human-readable label:

| Condition | Label |
|---|---|
| Fires later today | "Today at 6:00 AM" |
| Fires tomorrow | "Tomorrow at 6:00 AM" |
| Fires in 2–6 days | "Monday at 7:30 AM" |
| No enabled alarms | "No alarm set" |

Recalculated on every alarm update and at midnight.

### Alarm State Machine
```
IDLE → SUNRISE  (if enabled — starts ramp_minutes before alarm time)
     → FIRING   (at alarm time — plays Music Assistant or buzzer)
     → SNOOZED  (on snooze — resumes after snooze_duration_minutes)
     → IDLE     (on dismiss)
```

### HA MQTT Entities
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
│       Monday, August 4          │
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

---

## Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| OS | Raspberry Pi OS (64-bit) | Full desktop; Openbox kiosk mode |
| Backend language | Python 3.11+ | Main application runtime |
| Backend server | FastAPI + Uvicorn | REST endpoints + WebSocket server |
| Frontend | HTML5 / CSS3 / Vanilla JS | No framework; Chromium kiosk |
| HA Dashboard | Chromium iframe | Points to Lovelace URL |
| HA Integration | MQTT Discovery + HA WebSocket API | Device registration + entity polling |
| Time Sync | chrony (NTP) | Syncs system clock from NTP pool |
| RTC | DS3231 over I2C | Fallback; updated when NTP confirmed |
| Light Sensor | BH1750 over I2C | Auto-dimming; shared I2C bus |
| Audio (stereo) | 2× MAX98357A I2S breakout | Adafruit #3006 |
| Speakers | 2× Adafruit #4445 4Ω 3W enclosed | Built into enclosure |
| Audio (fallback) | Active buzzer via GPIO13 PWM | Fires if Music Assistant unavailable |
| Volume control | ALSA softvol | No hardware volume on MAX98357A |
| LED Sunrise | WS2812B via rpi_ws281x | GPIO12 via 74AHCT125 level shifter |
| Config | YAML file | Written back by settings UI |
| Process manager | systemd | Auto-start, restart on crash |
| OTA Updates | git pull + systemd restart | Via MQTT or UI button |
| Voice (future) | Wyoming satellite, faster-whisper, Piper | Phase 10, USB mic |

---

## Key Python Libraries

| Library | Purpose |
|---|---|
| `fastapi` | REST API and WebSocket server |
| `uvicorn` | ASGI server to run FastAPI |
| `websockets` | WebSocket client for HA connection |
| `RPi.GPIO` | GPIO — snooze button, power button, buzzer PWM |
| `smbus2` | I2C communication — DS3231, BH1750 |
| `adafruit-circuitpython-ds3231` | RTC read/write |
| `adafruit-circuitpython-bh1750` | Light sensor readings |
| `rpi_ws281x` | WS2812B LED strip control |
| `pyyaml` | Load and save YAML config file |
| `paho-mqtt` | MQTT client for HA Discovery |
| `aiohttp` | Async HA REST API calls |
| `python-dateutil` | Timezone and DST handling |
| `alsaaudio` | ALSA volume control for MAX98357A |
| `asyncio` | Async task management |

---

## Project Structure

```
alarm-clock/
├── backend/
│   ├── main.py              # FastAPI app, WebSocket server, startup
│   ├── alarm.py             # Alarm scheduling, firing, next_alarm()
│   ├── hardware.py          # GPIO, buzzer, BH1750, DS3231, power button
│   ├── leds.py              # WS2812B sunrise effect
│   ├── ha_client.py         # HA REST/WebSocket API, MQTT Discovery
│   ├── audio.py             # ALSA volume control, Music Assistant trigger
│   ├── config.py            # Load/save settings.yaml
│   └── updater.py           # OTA git pull + systemd restart
├── frontend/
│   ├── index.html           # Main clock face
│   ├── settings.html        # Settings screen
│   ├── dashboard.html       # HA Lovelace iframe
│   ├── css/
│   │   └── styles.css       # Shared styles, theme, animations
│   └── js/
│       ├── clock.js         # Time display, WebSocket client
│       ├── alarm.js         # Alarm UI, snooze/dismiss handling
│       ├── weather.js       # Weather widget
│       └── settings.js      # Settings form logic
├── config/
│   └── settings.yaml        # All user-configurable settings
├── systemd/
│   └── alarm-clock.service  # systemd unit file
└── README.md
```

---

## Build Phases

| Phase | Description | Status |
|---|---|---|
| 1 | Python backend skeleton — FastAPI, WebSocket, config | ✅ Built — testing |
| 2 | Clock face UI — time display, WebSocket client | ✅ Built — testing |
| 3 | Hardware layer — RTC, light sensor, GPIO, buzzer | ✅ Built — testing |
| 4 | Alarm logic — scheduling, firing, snooze | ✅ Built — testing |
| 5 | Home Assistant integration — MQTT, weather | 🔲 Not started |
| 6 | Sunrise LED effect | 🔲 Not started |
| 7 | Settings UI | 🔲 Not started |
| 8 | HA dashboard idle screen | 🔲 Not started |
| 9 | OTA update mechanism | 🔲 Not started |
| 10 | Voice control — Wyoming satellite | 🔲 Future |
| 11 | Custom HAT PCB design and fabrication | 🔲 Future |

---

## Configuration File (settings.yaml — example)

```yaml
clock:
  timezone: "America/New_York"
  display_format: "12hr"
  show_seconds: true

display:
  auto_dim: true
  dim_min_brightness: 10
  dim_max_brightness: 100
  dim_low_lux: 20
  dim_high_lux: 300
  dashboard_timeout_seconds: 120

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
  volume_start: 20
  volume_max: 80
  volume_ramp_seconds: 120
  fallback_buzzer: true
  buzzer_gpio: 13

snooze:
  duration_minutes: 9

sunrise:
  enabled: true
  ramp_minutes: 20
  max_brightness: 255

weather:
  enabled: true
  ha_temp_entity: "sensor.outdoor_temperature"
  ha_condition_entity: "weather.home"
  refresh_interval_seconds: 300

home_assistant:
  url: "http://homeassistant.local:8123"
  token: ""
  mqtt_broker: "homeassistant.local"
  mqtt_port: 1883
  dashboard_url: "http://homeassistant.local:8123/lovelace/0"

ota:
  git_branch: "main"
  auto_check: false
```

---

*Document version: 1.2 — August 2026*
