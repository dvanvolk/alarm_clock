# Alarm Clock Requirements

## Hardware Platform
- **Raspberry Pi 3** with official **Raspberry Pi touchscreen**
- Can double as a **Home Assistant dashboard** when alarm UI is idle
- **RTC module** (e.g., DS3231) for timekeeping during power/internet outage
- **Light sensor** (e.g., BH1750 or LDR) for automatic display dimming
- **Physical snooze button** (GPIO)
- **Passive/active buzzer** on GPIO as backup alarm sound
- **Optional:** LED strip (WS2812B) for sunrise effect

---

## Time & Sync
- Sync to **NTP time server** as primary source
- **DS3231 RTC** as fallback when NTP is unavailable
- RTC is updated from NTP when internet is available
- Configurable **timezone** and automatic DST handling
- Configurable **display format** (12hr / 24hr, show/hide seconds)

---

## Display
- **Auto-dimming** based on light sensor readings
- Dim level configurable in software
- Smooth brightness transitions
- **Idle mode** shows Home Assistant Lovelace dashboard (via browser kiosk or embedded frame)

---

## Alarm Scheduling
- Independent alarm schedules for:
  - Weekdays (Mon–Fri)
  - Weekends (Sat–Sun)
  - Individual days if needed
- Multiple alarms supported
- Alarm scheduling logic lives in the **Python backend** for reliability
  - Continues to fire from RTC even if Home Assistant or network is unavailable
  - HA is notified of alarm events but does not control timing
- HA exposes alarms as **MQTT entities** (switches to enable/disable, sensors for next alarm time)
- **Next alarm label** displayed on clock face at all times (e.g. "Tomorrow at 6:00 AM", "Monday at 7:30 AM")
- Alarm settings fully manageable from the **touchscreen UI**:
  - Enable / disable per alarm
  - Set time via touch-friendly time picker
  - Select active days via day-toggle buttons (M T W T F S S)
  - Choose sound source (Music Assistant playlist/station or buzzer fallback)

---

## UI Screens

### Screen 1 — Clock Face (main/idle)
- Current time (large, prominent)
- Date and day of week
- Weather widget (temp, condition, high/low)
- **Next alarm label** — human-readable, e.g.:
  - "Tomorrow at 6:00 AM"
  - "Monday at 7:30 AM"
  - "Today at 6:00 AM" (if not yet fired)
  - "No alarm set"
- Buttons to navigate to Settings or HA Dashboard

### Screen 2 — Alarm Firing
- Time displayed prominently
- Visual alert state
- **Snooze** button (also triggered by physical button)
- **Dismiss** button

### Screen 3 — Settings
- Per-alarm config: enable/disable, time picker, day toggles, sound source
- Add / remove alarms
- General: snooze duration, volume ramp, display format, timezone
- Display: auto-dim toggle, min brightness
- Sunrise: enable, ramp duration
- Save button writes back to YAML and reschedules immediately — no restart needed

---
- **Primary:** Music via **Music Assistant** (e.g., specific playlist, radio station, or track)
- **Fallback:** Buzzer/beeper if Music Assistant is unavailable
- **Volume ramp** — starts quiet, gradually increases (ramp time configurable)
- **Snooze** via physical button
  - Snooze duration configurable in software

---

## Sunrise Effect *(Nice to Have)*
- Gradually brightens LED strip before alarm time
- Ramp duration configurable (e.g., 15–30 min before alarm)
- Color shift from warm red → orange → warm white
- Max brightness configurable

---

## Weather & Temperature *(Nice to Have)*
- Pulled from **Home Assistant** entities
- Display current temp, condition icon, high/low
- Optionally humidity or rain chance
- Refreshes on a configurable interval

---

## Home Assistant Integration
- Clock registers as a **device in Home Assistant**
- HA can trigger/cancel/modify alarms via automations
- Alarm firing can trigger HA events (e.g., turn on lights, start coffee maker)
- Weather and Music Assistant data flow through HA
- Idle screen shows **HA Lovelace dashboard**

---

## Software Configuration
All of the following are **software-configurable** (via UI or config file):

| Setting | Description |
|---|---|
| Timezone | Local timezone with DST support |
| Display format | 12hr / 24hr, show/hide seconds |
| Snooze duration | Minutes before alarm resumes |
| Volume ramp | Speed and max volume level |
| Sunrise ramp | Duration and max LED brightness |
| Auto-dim thresholds | Light sensor low/high boundaries |
| Minimum brightness | Floor brightness level at night |
| Weather refresh interval | How often to poll HA for weather |
| Music Assistant source | Playlist, station, or track URI |

---

## OTA Updates
- Software supports **Over-The-Air updates**
- Delivered via git pull + systemd service restart, or a lightweight update agent
- Update can be triggered from Home Assistant or a UI button on the clock

---

## Nice to Have Summary

| Feature | Priority |
|---|---|
| Sunrise LED effect | Nice to have |
| Weather & temperature display | Nice to have |
| HA dashboard idle screen | Nice to have |
| Music Assistant audio | Nice to have |
| Individual day alarm scheduling | Nice to have |

---

*Document version: 1.1 — June 2026*
