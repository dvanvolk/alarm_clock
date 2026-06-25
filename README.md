# Alarm Clock

Raspberry Pi alarm clock with a Python/FastAPI backend and a Vanilla JS frontend running in a Chromium kiosk. See `docs/` for full requirements and architecture.

## Quick start (Windows dev)

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` in a browser.

## Raspberry Pi deployment

```bash
# Clone and set up
git clone <repo-url> /home/pi/alarm-clock
cd /home/pi/alarm-clock
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Pi-only hardware libraries
pip install RPi.GPIO smbus2 \
  adafruit-circuitpython-ds3231 \
  adafruit-circuitpython-bh1750

# Install and enable systemd service
sudo cp systemd/alarm-clock.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable alarm-clock
sudo systemctl start alarm-clock

# View logs
sudo journalctl -u alarm-clock -f
```

## Chromium kiosk (Pi)

Add to `/etc/xdg/openbox/autostart`:

```bash
chromium-browser --kiosk --noerrdialogs --disable-infobars http://localhost:8000 &
```

## Config

Edit `config/settings.yaml` to change timezone, alarms, display options, and Home Assistant credentials. The backend picks up changes on the next restart (or via the Settings UI once built — Phase 7).

## Build phases

| Phase | Status | Description |
|---|---|---|
| 1 | Done | Backend skeleton — FastAPI, WebSocket, config |
| 2 | Done | Clock face UI |
| 3 | Done | Hardware layer (GPIO, I2C, RTC, light sensor) |
| 4 | Done | Alarm logic — scheduling, snooze, dismiss |
| 5 | Todo | Home Assistant integration — weather, Music Assistant, MQTT |
| 6 | Todo | Sunrise LED effect |
| 7 | Todo | Settings UI |
| 8 | Todo | HA dashboard idle screen |
| 9 | Todo | OTA updates |
