# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

Phases 1–6 are built and in testing. Phases 7–9 are not started. Phase 10 (voice control) is a future phase. See `docs/alarm_clock_architecture.md` for the full build order and phase details.

## Architecture

Two-layer design communicating over a local WebSocket:

- **Python backend** (`backend/`) — FastAPI + Uvicorn server, all hardware access, alarm logic, Home Assistant integration, YAML config
- **HTML/JS frontend** (`frontend/`) — Vanilla JS (no framework), runs in a Chromium kiosk; receives pushed state from backend, sends user actions back

All frontend ↔ backend communication is WebSocket only. Python pushes state (time, brightness, weather, alarm state); the browser sends actions (`snooze`, `dismiss`, `settings_save`, `ota_trigger`, `switch_view`).

## Planned Project Structure

```
alarm-clock/
├── backend/
│   ├── main.py        # FastAPI app, WebSocket server, startup, asyncio task orchestration
│   ├── alarm.py       # Alarm scheduling, firing, snooze, Music Assistant trigger
│   ├── hardware.py    # GPIO (snooze button, buzzer PWM), I2C (DS3231 RTC, BH1750 light sensor), DHT22
│   ├── leds.py        # WS2812B sunrise LED effect via rpi_ws281x
│   ├── ha_client.py   # Home Assistant WebSocket API + MQTT Discovery integration
│   ├── config.py      # Load/save config/settings.yaml
│   └── updater.py     # OTA: git pull + systemd restart
├── frontend/
│   ├── index.html     # Clock face (primary view)
│   ├── settings.html  # Settings screen
│   ├── dashboard.html # HA Lovelace iframe wrapper
│   ├── css/styles.css
│   └── js/
│       ├── clock.js    # Time display, WebSocket client
│       ├── alarm.js    # Alarm UI, snooze/dismiss handling
│       ├── weather.js  # Weather widget
│       └── settings.js # Settings form
├── config/settings.yaml  # All user-configurable settings (see docs for schema)
└── systemd/alarm-clock.service
```

## Runtime Environment

- **Target hardware:** Raspberry Pi 3, Raspberry Pi OS Lite, Openbox for kiosk windowing; HiFiBerry DAC+ Pro for audio output (RCA → powered speakers, volume via ALSA); DHT22 on GPIO4 for temperature/humidity reporting to HA via MQTT
- **Python:** 3.11+; backend runs as a systemd service
- **Frontend:** served by FastAPI's static file hosting, opened by Chromium in kiosk mode

## Key Design Constraints

- The backend must be fully async (`asyncio`) — hardware polling, WebSocket clients, and the alarm scheduler all run as concurrent tasks under the same event loop.
- `rpi_ws281x` (WS2812B LED control) requires root or a udev rule; plan accordingly.
- `RPi.GPIO` and I2C libraries (`smbus2`, Adafruit CircuitPython) are hardware-specific — mock or skip on non-Pi dev machines.
- The DS3231 RTC is a fallback time source only; `chrony` syncs NTP → system clock → DS3231.
- Home Assistant integration uses both MQTT Discovery (device registration) and the HA WebSocket API (weather entity polling, Music Assistant service calls).
- HiFiBerry DAC+ Pro volume is controlled via ALSA — use `subprocess` to call `amixer` or use the `alsaaudio` Python library. Do not use `RPi.GPIO` for volume.
- YAML config (`config/settings.yaml`) is the single source of truth for all user settings. The settings UI writes back to it.

## Commands (once code exists)

```bash
# Run backend (dev)
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Run on Pi (production via systemd)
sudo systemctl start alarm-clock
sudo systemctl status alarm-clock
sudo journalctl -u alarm-clock -f

# Install Python dependencies
pip install fastapi uvicorn websockets RPi.GPIO smbus2 \
  adafruit-circuitpython-ds3231 adafruit-circuitpython-bh1750 \
  adafruit-circuitpython-dht rpi-ws281x pyyaml paho-mqtt \
  python-dateutil alsaaudio
```
