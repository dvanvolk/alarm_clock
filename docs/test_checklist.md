# Alarm Clock — Software Test Checklist

Use this checklist to verify all software features on the Pi.
Mark each item **Pass / Fail / N/A** as you go.
Items marked **[Pi only]** cannot be verified on a Windows dev machine.

---

## 1. Startup & Server

| # | Test | Expected | Result |
|---|------|----------|--------|
| 1.1 | Start backend: `uvicorn backend.main:app --host 0.0.0.0 --port 8000` | Server starts, no import errors in log | |
| 1.2 | Log shows hardware init message | "Hardware initialised (GPIO, I2C, RTC, light sensor)" on Pi; "[STUB] Hardware setup skipped" on dev | |
| 1.3 | Log shows LED setup | "LED strip ready" on Pi; "[STUB] LED setup" on dev | |
| 1.4 | Log shows alarm clock started | "Alarm clock backend started" logged | |
| 1.5 | Open `http://<pi-ip>:8000` in browser | Clock face loads, no 404 or console errors | |
| 1.6 | WebSocket indicator shows connected | Green dot or equivalent in top-right corner | |

---

## 2. Clock Face Display

| # | Test | Expected | Result |
|---|------|----------|--------|
| 2.1 | Clock shows correct time | Time matches system clock within ±2 s | |
| 2.2 | Seconds tick visually every second | Time string updates each second | |
| 2.3 | Date and day-of-week display correctly | Format: "July 4, 2026" and "Saturday" | |
| 2.4 | 12hr format (default) | Time shows AM/PM, no leading zero on hour | |
| 2.5 | Switch to 24hr in settings.yaml, restart | Time shows HH:MM:SS without AM/PM | |
| 2.6 | `show_seconds: false` in settings.yaml, restart | Seconds hidden from time display | |
| 2.7 | Next alarm label shows on clock face | e.g., "Tomorrow at 6:30 AM" | |
| 2.8 | Next alarm label shows "No alarm set" when all disabled | "No alarm set" displayed | |
| 2.9 | Custom font applies from `clock.font` setting | Font change visible on reload | |
| 2.10 | Custom accent color applies from `clock.accent_color` | UI accent color changes on reload | |

---

## 3. Weather Widget

| # | Test | Expected | Result |
|---|------|----------|--------|
| 3.1 | Weather widget hidden on load when HA is unavailable | Weather area not shown | |
| 3.2 | With valid HA token and weather entity, weather displays | Condition, temperature, high/low visible | |
| 3.3 | Weather updates at configured `refresh_interval_seconds` | Log shows "Weather updated" at interval | |
| 3.4 | New browser tab/reload receives last weather immediately | Weather populates without waiting for next poll | |
| 3.5 | HA unreachable mid-session | Warning logged; previous weather value stays on screen | |

---

## 4. Settings UI

| # | Test | Expected | Result |
|---|------|----------|--------|
| 4.1 | Navigate to Settings from clock face | settings.html loads, alarm cards populate from config | |
| 4.2 | WebSocket indicator shows connected on settings page | Connection indicator green | |
| 4.3 | Alarm label is editable | Text input accepts changes | |
| 4.4 | Alarm time picker works | Native time picker changes HH:MM | |
| 4.5 | Day checkboxes reflect current config | Days from settings.yaml pre-checked | |
| 4.6 | Toggle alarm enabled checkbox | Checkbox state changes visually | |
| 4.7 | Sound source dropdown shows "Buzzer" and "Music Assistant" | Both options present | |
| 4.8 | Selecting "Music Assistant" shows music URI field | URI input appears | |
| 4.9 | Melody dropdown visible when Buzzer is selected | Default/Gentle/Classic options present | |
| 4.10 | Dashboard URL field shows current value from config | Pre-populated from `home_assistant.dashboard_url` | |
| 4.11 | Save button triggers `settings_save` WebSocket message | Log shows "Settings saved" | |
| 4.12 | Save status shows "Saved" or equivalent feedback | Status text updates after save | |
| 4.13 | settings.yaml is updated on disk after Save | File contains new values | |
| 4.14 | Back button returns to clock face | Navigates to index.html | |

---

## 5. Alarm Scheduling

| # | Test | Expected | Result |
|---|------|----------|--------|
| 5.1 | Alarm fires at exact configured time (test with a 2-min future time) | `alarm_firing` WS message broadcast; overlay shown | |
| 5.2 | Alarm only fires on configured days | Set for one day of week; confirm no fire on other days | |
| 5.3 | Disabled alarm does not fire | `enabled: false` alarm skipped | |
| 5.4 | Multiple alarms configured — correct one fires | Only the matching alarm triggers | |
| 5.5 | Alarm check runs every 30 s | Log confirms `tick()` running; alarm fires within 30 s of target time | |
| 5.6 | `next_alarm()` returns soonest future alarm | Next alarm label on clock face is accurate | |
| 5.7 | Settings save reschedules alarms | After changing alarm time and saving, new next-alarm label shows immediately | |

---

## 6. Alarm Firing — Overlay UI

| # | Test | Expected | Result |
|---|------|----------|--------|
| 6.1 | Alarm overlay appears when alarm fires | Full-screen overlay with alarm label and time | |
| 6.2 | Alarm label and time in overlay match alarm config | Correct label and HH:MM displayed | |
| 6.3 | Snooze button visible and tappable | Button present, tap sends `snooze` message | |
| 6.4 | Dismiss button visible and tappable | Button present, tap sends `dismiss` message | |

---

## 7. Alarm Firing — Buzzer `[Pi only]`

| # | Test | Expected | Result |
|---|------|----------|--------|
| 7.1 | Alarm with `sound: buzzer` plays on GPIO13 | Audible tone from piezo on alarm fire | |
| 7.2 | Default melody ("default") plays ascending pattern | A4-A4-A5 repeating pattern | |
| 7.3 | "gentle" melody plays correctly | Ascending triad C5-E5-G5-C5 with long pauses | |
| 7.4 | "classic" melody plays correctly | Single 500 ms A5 beep with 500 ms pause | |
| 7.5 | Buzzer stops on snooze | No sound after snooze | |
| 7.6 | Buzzer stops on dismiss | No sound after dismiss | |
| 7.7 | Custom duty cycle from `buzzer.duty_cycle` config | Louder/quieter based on duty % | |

---

## 8. Alarm Firing — Music Assistant

| # | Test | Expected | Result |
|---|------|----------|--------|
| 8.1 | Alarm with `sound: music_assistant` triggers HA media player | Music starts on configured `music_player_entity` | |
| 8.2 | Playback starts at `audio.volume_start` % | Initial volume matches config | |
| 8.3 | Volume ramps to `audio.volume_max` % over `volume_ramp_seconds` | Volume increases gradually | |
| 8.4 | Snooze stops music | `media_stop` called on media player | |
| 8.5 | Dismiss stops music | `media_stop` called on media player | |
| 8.6 | Music Assistant unavailable (no HA) — alarm falls back to buzzer | Warning logged; buzzer fires instead | |

---

## 9. Snooze

| # | Test | Expected | Result |
|---|------|----------|--------|
| 9.1 | Tap Snooze during alarm | Overlay closes (or shows snooze state); sound stops | |
| 9.2 | `alarm_snoozed` WS message received with resume time | Resume time = now + `snooze.duration_minutes` | |
| 9.3 | Alarm re-fires after snooze duration | Alarm overlay returns after configured minutes | |
| 9.4 | Snooze ignored when no alarm is firing | No action, no error | |

---

## 10. Physical Snooze Button `[Pi only]`

| # | Test | Expected | Result |
|---|------|----------|--------|
| 10.1 | Press GPIO17 button while alarm firing | Same result as tapping Snooze on screen | |
| 10.2 | Button debounce (300 ms) prevents double-snooze | Rapid press counts as one snooze | |
| 10.3 | Press button when idle | No action, no error | |

---

## 11. Dismiss

| # | Test | Expected | Result |
|---|------|----------|--------|
| 11.1 | Tap Dismiss during alarm | Overlay hides; sound stops; LEDs off | |
| 11.2 | `alarm_dismissed` WS message received | Frontend returns to clock face | |
| 11.3 | State returns to IDLE; next alarm label updates | Clock shows next scheduled alarm | |
| 11.4 | Dismiss during snooze | Alarm cleared; no re-fire | |

---

## 12. Sunrise LED Effect `[Pi only]`

| # | Test | Expected | Result |
|---|------|----------|--------|
| 12.1 | LEDs begin ramping at `sunrise.ramp_minutes` before alarm time | Strip starts deep red before alarm fires | |
| 12.2 | Color progresses: deep red → orange → warm white | Color visibly transitions over ramp window | |
| 12.3 | LEDs at full warm white when alarm fires | Full brightness maintained during firing | |
| 12.4 | LEDs off after dismiss | Strip goes dark | |
| 12.5 | Sunrise effect cancels on snooze | LEDs go off; re-start when alarm re-fires | |
| 12.6 | `sunrise.enabled: false` skips the ramp | No LED activity before alarm; log confirms skip | |
| 12.7 | `sunrise.num_leds` and `max_brightness` respected | Number of lit LEDs and peak brightness match config | |

---

## 13. Auto-Dim / Light Sensor `[Pi only]`

| # | Test | Expected | Result |
|---|------|----------|--------|
| 13.1 | `brightness_update` WS message received every 60 s | Log or browser console shows brightness messages | |
| 13.2 | Cover BH1750 sensor | Brightness value drops toward `dim_min_brightness` | |
| 13.3 | Shine light at BH1750 | Brightness value rises toward `dim_max_brightness` | |
| 13.4 | `auto_dim: false` in config | No brightness_update messages; brightness static | |

---

## 14. DHT22 Temperature & Humidity `[Pi only]`

| # | Test | Expected | Result |
|---|------|----------|--------|
| 14.1 | `dht22.enabled: true` in config; server starts | Log shows "DHT22 ready on GPIO4" | |
| 14.2 | DHT22 poll reads valid values | Log shows "DHT22: 72.0°F  45.0%RH" (or similar) | |
| 14.3 | Temperature and humidity published to MQTT | HA shows `sensor.alarm_clock_temperature` and `sensor.alarm_clock_humidity` updating | |
| 14.4 | Transient read error | Debug log only; next poll retries | |
| 14.5 | `dht22.enabled: false` | DHT22 loop does not start; no GPIO setup | |

---

## 15. DS3231 RTC `[Pi only]`

| # | Test | Expected | Result |
|---|------|----------|--------|
| 15.1 | RTC accessible over I2C at startup | No I2C error in log | |
| 15.2 | System clock is NTP-synced (chrony running) | `chronyc tracking` shows offset < 1 s | |
| 15.3 | Disconnect network, reboot Pi | Clock still shows correct time (from RTC) | |
| 15.4 | Reconnect network — chrony resyncs and updates RTC | `chronyc tracking` shows in-sync within a few minutes | |

---

## 16. Home Assistant Integration — MQTT Discovery

| # | Test | Expected | Result |
|---|------|----------|--------|
| 16.1 | HA token and MQTT broker configured; backend starts | Log shows "MQTT connected" | |
| 16.2 | "Alarm Clock" device appears in HA Devices list | Device with 6 entities visible in HA | |
| 16.3 | `sensor.alarm_clock_next` shows correct next alarm label | Matches label on clock face | |
| 16.4 | `binary_sensor.alarm_clock_firing` turns ON when alarm fires | HA entity state = ON during alarm | |
| 16.5 | `binary_sensor.alarm_clock_firing` turns OFF after dismiss | HA entity state = OFF | |
| 16.6 | `switch.alarm_clock_weekday` reflects weekday alarm enabled state | Switch matches alarm enabled setting | |
| 16.7 | Turn off `switch.alarm_clock_weekday` from HA | Weekday alarm disabled in settings.yaml; next alarm label updates | |
| 16.8 | Turn on `switch.alarm_clock_weekday` from HA | Weekday alarm re-enabled; label updates | |
| 16.9 | MQTT broker unavailable at startup | Warning logged (rc=5 or similar); integration disabled gracefully | |
| 16.10 | MQTT broker reconnects after outage | Reconnects automatically; discovery republished | |

---

## 17. Home Assistant Integration — WebSocket

| # | Test | Expected | Result |
|---|------|----------|--------|
| 17.1 | HA WebSocket connects at startup | Log shows "HA WebSocket authenticated (HA x.x)" | |
| 17.2 | HA WS disconnects mid-session | Log shows disconnect warning; reconnects within 30 s | |
| 17.3 | Bad/expired HA token | Log shows "auth failed"; WS retries every 60 s | |

---

## 18. HA Dashboard View

| # | Test | Expected | Result |
|---|------|----------|--------|
| 18.1 | Dashboard URL set in settings | dashboard.html loads as iframe | |
| 18.2 | Navigate to Settings → change Dashboard URL → Save | New URL reflected in dashboard.html on next load | |
| 18.3 | No Dashboard URL set | dashboard.html shows placeholder / empty iframe | |

---

## 19. OTA Update

| # | Test | Expected | Result |
|---|------|----------|--------|
| 19.1 | Click "Update Software" button on clock face | `ota_trigger` message sent; `ota_status: starting` received | |
| 19.2 | Git pull succeeds (repo is up to date or has new commits) | `ota_status: success` logged and broadcast | |
| 19.3 | After successful pull, service restarts `[Pi only]` | `ota_status: restarting` broadcast; process exits; systemd restarts within seconds | |
| 19.4 | Git pull fails (no internet, bad branch) | `ota_status: error` with stderr detail shown | |
| 19.5 | `ota.git_branch` setting respected | Pull targets configured branch | |

---

## 20. Multi-Client / WebSocket Robustness

| # | Test | Expected | Result |
|---|------|----------|--------|
| 20.1 | Open clock face in two browser tabs | Both tabs show same time; both receive alarm events | |
| 20.2 | Close one tab mid-session | Backend removes dead client; no error loop | |
| 20.3 | Reload browser during alarm | Alarm overlay reappears after reconnect (state_message sent on connect) | |
| 20.4 | Backend restart while browser is open | WebSocket indicator shows disconnected; auto-reconnects when server is back | |
| 20.5 | New client connects — receives cached weather immediately | Weather appears on load without waiting for next poll | |

---

## 21. systemd Service `[Pi only]`

| # | Test | Expected | Result |
|---|------|----------|--------|
| 21.1 | `sudo systemctl start alarm-clock` — service starts | `systemctl status alarm-clock` shows "active (running)" | |
| 21.2 | `sudo systemctl stop alarm-clock` — service stops cleanly | Log shows "GPIO cleaned up" and "Alarm clock backend stopped" | |
| 21.3 | Kill backend process unexpectedly | systemd restarts it automatically (check Restart= in unit file) | |
| 21.4 | Reboot Pi | Service auto-starts; clock face loads after boot | |
| 21.5 | `sudo journalctl -u alarm-clock -f` shows live logs | Backend log output visible | |

---

## 22. Edge Cases & Error Handling

| # | Test | Expected | Result |
|---|------|----------|--------|
| 22.1 | settings.yaml missing or corrupted | Backend logs error and uses defaults; does not crash | |
| 22.2 | `.env` / HA token missing | Log shows "no HA token — integration disabled"; app still runs | |
| 22.3 | Alarm configured with no days selected | Does not fire on any day; next_alarm() returns None | |
| 22.4 | Alarm time in the past today | next_alarm() calculates correct day next week | |
| 22.5 | Two alarms at the same time | One fires (first match in list); no crash | |
| 22.6 | Unknown WebSocket message type from client | "Unknown message type" warning logged; no crash | |
| 22.7 | Settings save with empty alarm list | Config saved; no error; "No alarm set" on clock face | |
| 22.8 | `music_player_entity` not set when Music Assistant selected | Warning logged; no crash; buzzer fallback (if configured) | |

---

*Document version: 1.0 — July 2026*
