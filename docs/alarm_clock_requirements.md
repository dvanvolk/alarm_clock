# Alarm Clock Requirements

## Hardware Platform

| Component | Part | Notes |
|---|---|---|
| SBC | Raspberry Pi 3B | Running only the alarm clock application |
| Display | Official Raspberry Pi 7" Touchscreen | DSI connector |
| Audio amplifier | 2× Adafruit MAX98357A breakout (#3006) | I2S, one per stereo channel |
| Speakers | 2× Adafruit Mono Enclosed Speaker 3W 4Ω (#4445) | Built into clock enclosure, bare wire leads |
| RTC | DS3231 module | I2C, CR2032 battery backup |
| Light sensor | Adafruit BH1750 breakout | I2C, STEMMA QT, auto-dimming |
| Snooze button | Momentary pushbutton | GPIO17, active low |
| Power button | Momentary pushbutton | GPIO26 (shutdown) + GPIO3 (wake) |
| Buzzer | Active buzzer | GPIO13, PWM fallback alarm |
| LED strip | WS2812B | GPIO12, sunrise effect |
| Level shifter | 74AHCT125 | 3.3V → 5V for WS2812B data line |
| Microphone | TONOR G11 USB omnidirectional | USB, future voice control Phase 10 |

---

## Enclosure & Physical Design
- All components (Pi, amplifiers, speakers, HAT) housed in a **single custom enclosure**
- Speakers mounted internally — no separate speaker units on the nightstand
- BH1750 light sensor remote-mounted to face the room via a small hole in the case
  - GY-302 bare module or Adafruit BH1750 wired via short JST/STEMMA QT extension
- Power button accessible on enclosure exterior
- Single power cable in (5V/4A barrel jack)

---

## Custom HAT PCB *(Future Phase)*
A custom Raspberry Pi HAT will consolidate all peripheral connections:
- DS3231 RTC (I2C) with battery holder
- BH1750 light sensor connector (JST remote mount)
- Snooze button + 10kΩ pull-up resistor
- Power button circuit (GPIO26 shutdown + GPIO3 wake, 330Ω series resistors)
- Active buzzer with transistor driver
- WS2812B LED strip screw terminal (3-pin: Data, 5V, GND)
- 74AHCT125 level shifter for WS2812B data
- 5V power input (barrel jack), polyfuse protection, reverse polarity Schottky diode
- Power distribution: Pi via GPIO header, display via 2-pin JST-PH, LED strip via screw terminal
- 2× MAX98357A amp chips with JST-PH2.0 speaker output connectors
- Speaker connections via 2-pin screw terminals (bare wire from Adafruit #4445)
- I2C pull-up resistors (4.7kΩ on SDA/SCL)
- Bulk 1000µF capacitor + 100nF decoupling caps on 5V rail
- 40-pin GPIO pass-through header

---

## Power
- Single **5V/4A barrel jack** input on HAT
- HAT distributes 5V to: Pi GPIO header, touchscreen, WS2812B LED strip
- Polyfuse protection per branch (2.5A Pi, 2A display, 2A LEDs)
- Reverse polarity protection via Schottky diode (SS34)
- **Physical power button**: GPIO26 triggers safe shutdown; GPIO3 wakes Pi from halt
- Green power LED indicator on enclosure

---

## Time & Sync
- Sync to **NTP time server** as primary source (via chrony)
- **DS3231 RTC** as fallback when NTP is unavailable
- RTC updated from system clock whenever NTP sync is confirmed
- Configurable **timezone** and automatic DST handling
- Configurable **display format** (12hr / 24hr, show/hide seconds)

---

## Display
- **Auto-dimming** based on BH1750 light sensor lux readings
- Smooth brightness transitions via backlight control
- Dim thresholds and min/max brightness configurable in software
- **Idle mode** shows Home Assistant Lovelace dashboard (Chromium iframe)

---

## Audio
- **Primary alarm sound:** Music via **Music Assistant** triggered through Home Assistant service call
- **Fallback:** Active buzzer on GPIO13 if Music Assistant or HA is unavailable
- **Stereo output:** 2× MAX98357A I2S amplifiers, one per channel (Left/Right)
  - Chip #1: SD pin → 3.3V via 100kΩ → Left channel
  - Chip #2: SD pin → GND via 100kΩ → Right channel
  - Both share BCLK (GPIO18), LRCLK (GPIO19), DIN (GPIO20)
- **Volume ramp:** starts at configurable low level, ramps up gradually over configurable time
- **Software volume:** ALSA softvol (no hardware volume register on MAX98357A)
- **Click/pop suppression:** built into MAX98357A

---

## Alarm Scheduling
- Multiple independent alarms supported
- Per-alarm day selection: weekdays (Mon–Fri), weekends (Sat–Sun), or individual days
- Alarm scheduling logic lives entirely in the **Python backend** for reliability
  - Fires from RTC even if Home Assistant or network is unavailable
  - HA is notified of alarm events but does not control timing
- HA exposes alarms as **MQTT entities** (switches, sensors)
- **Next alarm label** displayed on clock face at all times:
  - "Today at 6:00 AM" / "Tomorrow at 6:00 AM" / "Monday at 7:30 AM" / "No alarm set"
- Alarm settings fully manageable from the **touchscreen UI**

---

## UI Screens

### Screen 1 — Clock Face (main/idle)
- Current time (large, prominent)
- Date and day of week
- Weather widget (temp, condition, high/low) from Home Assistant
- Next alarm label (human-readable)
- Navigation buttons: Settings, HA Dashboard

### Screen 2 — Alarm Firing
- Time displayed prominently
- Visual alert state
- **Snooze** button (also triggered by physical GPIO17 button)
- **Dismiss** button

### Screen 3 — Settings
- Per-alarm config: enable/disable toggle, time picker, day toggles (M T W T F S S), sound source
- Add / remove alarms
- General: snooze duration, volume ramp speed, volume max, display format, timezone
- Display: auto-dim toggle, min/max brightness, lux thresholds
- Sunrise effect: enable toggle, ramp duration, max brightness
- Save button writes back to YAML and reschedules alarms immediately — no restart needed

### Screen 4 — HA Dashboard
- Chromium iframe pointing to Lovelace URL
- Back button returns to clock face
- Auto-return to clock face after configurable idle timeout

---

## Sunrise Effect *(Nice to Have)*
- WS2812B LED strip gradually brightens before alarm time
- Ramp starts configurable minutes before alarm (e.g. 15–30 min)
- Color shift: deep red → orange → warm white
- Max brightness configurable
- Cancelled cleanly if alarm is dismissed early

---

## Weather & Temperature *(Nice to Have)*
- Pulled from **Home Assistant** entities (temp sensor + weather entity)
- Displays current temp, condition icon, high/low
- Optionally humidity or rain chance
- Refresh interval configurable

---

## Home Assistant Integration
- Clock registers as a **device in Home Assistant** via MQTT Discovery
- MQTT entities: weekday alarm switch, weekend alarm switch, next alarm sensor, firing binary sensor
- HA automations can react when alarm fires (lights, coffee maker, etc.)
- Weather and Music Assistant data flow through HA
- Idle screen shows HA Lovelace dashboard

---

## Voice Control *(Future — Phase 10)*
- USB microphone: TONOR G11 (omnidirectional, plug and play, no drivers)
- Wyoming satellite protocol via Home Assistant
- Wake word: openWakeWord (local)
- Speech-to-text: faster-whisper (local)
- Text-to-speech: Piper (local, output via MAX98357A + speakers)
- Intent handling: Home Assistant local intents
- Echo cancellation handled in software (mute/pause music on wake word detection)

---

## Software Configuration
All of the following are **software-configurable** via settings UI or YAML:

| Setting | Description |
|---|---|
| Timezone | Local timezone with DST support |
| Display format | 12hr / 24hr, show/hide seconds |
| Snooze duration | Minutes before alarm resumes |
| Volume start | Initial volume % when alarm begins |
| Volume max | Ceiling volume % |
| Volume ramp duration | Seconds to ramp from start to max |
| Sunrise ramp duration | Minutes before alarm to start LED ramp |
| Sunrise max brightness | LED strip max brightness (0–255) |
| Auto-dim enabled | Toggle auto-dimming |
| Dim min brightness | Floor brightness level at night (%) |
| Dim max brightness | Ceiling brightness in daylight (%) |
| Dim low lux | Lux threshold to start dimming |
| Dim high lux | Lux threshold for full brightness |
| Weather refresh interval | How often to poll HA for weather (seconds) |
| Music Assistant source | Playlist, station, or track URI per alarm |
| HA dashboard URL | Lovelace URL for idle screen |
| HA dashboard timeout | Seconds before auto-returning to clock face |

---

## OTA Updates
- Software supports **Over-The-Air updates** via git pull + systemd restart
- Triggered from HA (MQTT message) or UI button in Settings screen
- `ota_status` WebSocket message reports progress and result to frontend

---

## Nice to Have Summary

| Feature | Status |
|---|---|
| Sunrise LED effect | Nice to have |
| Weather & temperature display | Nice to have |
| HA dashboard idle screen | Nice to have |
| Music Assistant audio | Nice to have |
| Individual day alarm scheduling | Nice to have |
| Voice control (Wyoming satellite) | Future — Phase 10 |
| Custom HAT PCB | Future — Phase 11 |

---

*Document version: 1.2 — August 2026*
