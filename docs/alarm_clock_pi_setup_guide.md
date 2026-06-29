# Alarm Clock — Raspberry Pi Setup Guide

Complete step-by-step guide to setting up the Raspberry Pi 3 for the alarm clock project,
from a fresh SD card to a running kiosk.

---

## What You Need

### Hardware
- Raspberry Pi 3B
- Official Raspberry Pi 7" Touchscreen (DSI)
- HiFiBerry DAC+ Pro HAT
- DS3231 RTC module
- BH1750 light sensor module
- DHT22 temperature and humidity sensor module
- 4.7kΩ resistor (pull-up for DHT22 data line — skip if your DHT22 module has one built in)
- Momentary push button (snooze)
- Active buzzer
- WS2812B LED strip
- MicroSD card (16GB minimum, Class 10 or better)
- 5V/3A USB-C power supply (the official Pi PSU is recommended)
- Powered speakers with RCA input
- Jumper wires and breadboard or terminal block for GPIO connections
- CR2032 battery for DS3231 RTC

### On Your Computer
- [Raspberry Pi Imager](https://www.raspberrypi.com/software/) installed
- SSH client (Terminal on Mac/Linux, PuTTY or Windows Terminal on Windows)

---

## Part 1 — Flash the SD Card

### 1.1 Open Raspberry Pi Imager

1. Launch **Raspberry Pi Imager** on your computer
2. Click **Choose Device** → select **Raspberry Pi 3**
3. Click **Choose OS** → select **Raspberry Pi OS (64-bit)** (the full desktop version)
4. Click **Choose Storage** → select your SD card

### 1.2 Configure Before Writing

Click the **gear icon (⚙)** or **Edit Settings** before writing to pre-configure:

**General tab:**
- Set hostname: `alarmclock`
- Enable **Set username and password** → username: `pi`, set a strong password
- Configure **WiFi**: enter your network name and password, set country code
- Set **locale**: your timezone and keyboard layout

**Services tab:**
- Enable **SSH** → select **Use password authentication**

Click **Save**, then **Yes** to apply settings, then **Yes** to write.

### 1.3 Boot the Pi

1. Insert the SD card into the Pi
2. Connect the touchscreen via DSI ribbon cable before powering on
3. Power on — first boot takes 1–2 minutes
4. Find the Pi's IP address from your router, or use `alarmclock.local`

---

## Part 2 — Initial SSH Setup

Connect from your computer:

```bash
ssh pi@alarmclock.local
```

### 2.1 Update the System

```bash
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

Reconnect after reboot:
```bash
ssh pi@alarmclock.local
```

### 2.2 Set the Timezone

```bash
sudo raspi-config
```

Navigate to: **5 Localisation Options** → **L2 Timezone** → select your region and city.

Exit raspi-config and reboot if prompted.

---

## Part 3 — Enable Required Interfaces

```bash
sudo raspi-config
```

Enable the following under **3 Interface Options**:

- **I2C** — for DS3231 RTC and BH1750 light sensor
- **SPI** — not required now but useful for future expansion

Exit and reboot:
```bash
sudo reboot
```

---

## Part 4 — Configure the HiFiBerry DAC+ Pro

### 4.1 Disable the Default Audio

```bash
sudo nano /boot/config.txt
```

Find this line and comment it out (add `#` at the start):
```
# dtparam=audio=on
```

### 4.2 Enable the HiFiBerry Overlay

Add these lines at the bottom of `/boot/config.txt`:
```
# HiFiBerry DAC+ Pro
dtoverlay=hifiberry-dacplus
```

Save and exit (`Ctrl+X`, `Y`, `Enter`).

### 4.3 Reboot and Verify

```bash
sudo reboot
```

After reboot, verify the DAC is detected:
```bash
aplay -l
```

You should see something like:
```
card 0: sndrpihifiberry [snd_rpi_hifiberry_dacplus], device 0: HiFiBerry DAC+ Pro HiFi pcm512x-hifi-0
```

Test audio output:
```bash
speaker-test -c 2 -t wav
```

### 4.4 Set Default Volume

```bash
amixer sset 'Digital' 80%
```

To make volume persistent, install `alsa-utils` and save state:
```bash
sudo apt install -y alsa-utils
sudo alsactl store
```

---

## Part 5 — Configure the DS3231 RTC

### 5.1 Wire the DS3231

Connect the DS3231 module to the Pi GPIO header (or the HiFiBerry's pass-through header):

| DS3231 Pin | Pi GPIO Pin | GPIO Number |
|---|---|---|
| VCC | Pin 1 | 3.3V |
| GND | Pin 6 | GND |
| SDA | Pin 3 | GPIO2 |
| SCL | Pin 5 | GPIO3 |

Insert the CR2032 battery into the DS3231 module.

> **Note:** The HiFiBerry DAC+ Pro passes through the I2C pins on its header.
> Connect the DS3231 to the HiFiBerry's GPIO pass-through, not directly to the Pi.

### 5.2 Enable the RTC Driver

```bash
sudo nano /boot/config.txt
```

Add at the bottom:
```
# DS3231 RTC
dtoverlay=i2c-rtc,ds3231
```

Save and reboot:
```bash
sudo reboot
```

### 5.3 Verify the RTC is Detected

```bash
sudo i2cdetect -y 1
```

You should see `68` in the grid — that is the DS3231 address.

### 5.4 Remove the Fake Hardware Clock

```bash
sudo apt remove -y fake-hwclock
sudo update-rc.d -f fake-hwclock remove
sudo systemctl disable fake-hwclock
```

### 5.5 Configure hwclock

```bash
sudo nano /lib/udev/hwclock-set
```

Comment out these three lines:
```bash
#if [ -e /run/systemd/system ] ; then
# exit 0
#fi
```

### 5.6 Sync System Time to RTC

Once the Pi has synced via NTP (check with `timedatectl`), write the time to the RTC:
```bash
sudo hwclock -w
```

Read back from RTC to verify:
```bash
sudo hwclock -r
```

---

## Part 6 — Configure the BH1750 Light Sensor

### 6.1 Wire the BH1750

The BH1750 shares the I2C bus with the DS3231:

| BH1750 Pin | Pi GPIO Pin | GPIO Number |
|---|---|---|
| VCC | Pin 1 | 3.3V |
| GND | Pin 6 | GND |
| SDA | Pin 3 | GPIO2 |
| SCL | Pin 5 | GPIO3 |
| ADDR | GND | (sets I2C address to 0x23) |

### 6.2 Verify Detection

```bash
sudo i2cdetect -y 1
```

You should now see both `23` (BH1750) and `68` (DS3231) in the grid.

---

## Part 7 — Wire the GPIO Components

### 7.0 Full Wiring Diagram

The diagram below shows all GPIO connections for the complete hardware build.
The HiFiBerry DAC+ Pro sits on top of the 40-pin header; all wiring goes to
the HiFiBerry's pass-through header (same pin numbers).

```
              Raspberry Pi 3B — 40-Pin GPIO Header
              ─────────────────────────────────────
              (viewed from above; pin 1 = top-left)

  3.3V  ──[01]●  ●[02]── 5V
  GPIO2 ──[03]●  ●[04]── 5V
  GPIO3 ──[05]●  ●[06]── GND
  GPIO4 ──[07]●  ●[08]
  GND   ──[09]●  ●[10]
  GPIO17──[11]●  ●[12]── GPIO18
          [13]●  ●[14]── GND
          [15]●  ●[16]
  3.3V  ──[17]●  ●[18]
          [19]●  ●[20]── GND
          [21]●  ●[22]
          [23]●  ●[24]
  GND   ──[25]●  ●[26]
          [27]●  ●[28]
          [29]●  ●[30]── GND
          [31]●  ●[32]── GPIO12
          [33]●  ●[34]── GND
          [35]●  ●[36]
          [37]●  ●[38]
  GND   ──[39]●  ●[40]
```

**Pin-to-component map:**

| Pin | Signal | → Component |
|-----|--------|-------------|
| 1 | 3.3V | DS3231 VCC, BH1750 VCC, DHT22 VCC |
| 3 | GPIO2 (SDA) | DS3231 SDA ── BH1750 SDA (shared I2C bus) |
| 5 | GPIO3 (SCL) | DS3231 SCL ── BH1750 SCL (shared I2C bus) |
| 6 | GND | DS3231 GND, BH1750 GND |
| 7 | GPIO4 | DHT22 DATA (+ 4.7kΩ pull-up to 3.3V) |
| 9 | GND | DHT22 GND, Snooze button (one leg) |
| 11 | GPIO17 | Snooze button (other leg) — internal pull-up, no resistor needed |
| 12 | GPIO18 | Buzzer (+) ⚠ see conflict note below |
| 14 | GND | Buzzer (−) |
| 32 | GPIO12 | WS2812B Data In |
| 34 | GND | WS2812B GND (tie to external 5V supply GND) |

> ⚠ **GPIO18 / HiFiBerry conflict:** GPIO18 (Pin 12) is also the I2S bit-clock
> used by the HiFiBerry DAC+ Pro. The buzzer and HiFiBerry I2S cannot both use
> GPIO18 simultaneously. The buzzer fires only as a fallback when Music Assistant
> is unavailable — most users can omit it. If you need both, use a different
> hardware PWM pin (GPIO13 / Pin 33 is the other PWM1 option on Pi 3).

---

### 7.1 Snooze Button (GPIO17)

| Button Pin | Connection |
|---|---|
| One leg | GPIO17 (Pin 11) |
| Other leg | GND (Pin 9) |

The software uses the Pi's internal pull-up resistor — no external resistor needed.

### 7.2 Active Buzzer (GPIO18)

| Buzzer Pin | Connection |
|---|---|
| + (positive) | GPIO18 (Pin 12) |
| − (negative) | GND (Pin 14) |

See GPIO18/HiFiBerry conflict note in the wiring diagram above.

### 7.3 WS2812B LED Strip (GPIO12)

| LED Strip Wire | Connection |
|---|---|
| Data In | GPIO12 (Pin 32) |
| +5V | External 5V supply |
| GND | External GND (also connect to Pi GND Pin 34) |

> **Important:** WS2812B strips draw significant current. Do NOT power them from
> the Pi's 5V pin. Use a separate 5V power supply rated for the number of LEDs
> you are using (roughly 60mA per LED at full white).
> Connect the GND of the external supply to a Pi GND pin.

### 7.4 DHT22 Temperature and Humidity Sensor (GPIO4)

| DHT22 Pin | Connection |
|---|---|
| VCC | 3.3V (Pin 1) |
| GND | GND (Pin 9) |
| DATA | GPIO4 (Pin 7) |

The data line requires a pull-up resistor to ensure reliable reads:

```
3.3V (Pin 1) ──┬──[4.7kΩ]──┬── GPIO4 (Pin 7)
               │            │
             DHT22 VCC    DHT22 DATA
             DHT22 GND ── GND (Pin 9)
```

> **Note:** Many DHT22 breakout modules (the three-pin variety sold on Amazon)
> include the pull-up resistor on the PCB. If your module has only three pins
> (VCC, DATA, GND) rather than four, the resistor is already built in and you
> can wire DATA directly to GPIO4.

---

## Part 8 — Install System Dependencies

### 8.1 Core Packages

```bash
sudo apt install -y \
  python3-pip \
  python3-venv \
  git \
  chromium-browser \
  unclutter \
  xdotool \
  openbox \
  xinit \
  xserver-xorg \
  alsa-utils \
  chrony \
  i2c-tools \
  libgpiod2
```

### 8.2 WS2812B LED Support

The `rpi_ws281x` library requires root or a specific udev rule to access PWM.
Install the library:

```bash
sudo pip3 install rpi_ws281x --break-system-packages
```

Add a udev rule so the app can access PWM without running as root:
```bash
sudo nano /etc/udev/rules.d/99-pwm.rules
```

Add:
```
SUBSYSTEM=="pwm*", PROGRAM="/bin/sh -c 'chown -R root:gpio /sys/class/pwm && chmod -R 770 /sys/class/pwm'"
```

Add `pi` to the gpio group:
```bash
sudo usermod -a -G gpio pi
```

---

## Part 9 — Clone the Project and Install Python Dependencies

### 9.1 Clone the Repository

```bash
cd /home/pi
git clone https://github.com/YOUR_USERNAME/alarm-clock.git
cd alarm-clock
```

> Replace `YOUR_USERNAME/alarm-clock` with your actual repository path.

### 9.2 Create a Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 9.3 Install Python Dependencies

```bash
pip install \
  fastapi \
  uvicorn \
  websockets \
  RPi.GPIO \
  smbus2 \
  adafruit-circuitpython-ds3231 \
  adafruit-circuitpython-bh1750 \
  adafruit-circuitpython-dht \
  rpi-ws281x \
  pyyaml \
  paho-mqtt \
  python-dateutil \
  python-dotenv \
  alsaaudio
```

> `adafruit-circuitpython-dht` requires `libgpiod2`, which is included in the
> `apt install` command in Part 8.1.

### 9.4 Edit the Config File

Open `config/settings.yaml` and fill in your timezone, alarm times, Home
Assistant URL, MQTT broker address, and DHT22 settings:

```bash
nano config/settings.yaml
```

Key settings to review:

```yaml
clock:
  timezone: "America/New_York"  # your local tz

dht22:
  enabled: true
  gpio_pin: 4                   # BCM pin the DHT22 DATA wire is on
  temperature_unit: "F"         # F or C

home_assistant:
  url: "http://homeassistant.local:8123"
  mqtt_broker: "homeassistant.local"
```

> **Do not** put your HA token or MQTT password in `settings.yaml` — use the
> `.env` file instead (see Part 9.5 below).

### 9.5 Create the Secrets File (.env)

Credentials are loaded from a `.env` file that is never committed to git.
Copy the example and fill in your values:

```bash
cp .env.example .env
nano .env
```

The file should look like this (replace the placeholder values):

```bash
# Home Assistant long-lived access token
# Generate at: HA → Profile → Security → Long-Lived Access Tokens
HA_TOKEN=eyJ0eXAiOiJKV1Q...your_full_token_here

# MQTT broker credentials (if your broker requires authentication)
MQTT_USER=your_mqtt_username
MQTT_PASS=your_mqtt_password
```

To generate a long-lived access token in Home Assistant:
1. Open Home Assistant → click your profile (bottom-left)
2. Scroll to **Security** → **Long-Lived Access Tokens**
3. Click **Create Token**, name it `alarm-clock`, copy the token

> `.env` is listed in `.gitignore` and will never be committed. The file
> `.env.example` (committed) shows the required variable names without values.

---

## Part 10 — Configure NTP with chrony

```bash
sudo nano /etc/chrony/chrony.conf
```

The defaults are fine for most setups. If your Home Assistant instance runs
an NTP server, you can add it as a preferred source:

```
server homeassistant.local iburst prefer
```

Enable and start chrony:
```bash
sudo systemctl enable chrony
sudo systemctl start chrony
```

Check sync status:
```bash
chronyc tracking
```

---

## Part 11 — Configure Kiosk Mode

### 11.1 Set Up Openbox Autostart

```bash
mkdir -p /home/pi/.config/openbox
nano /home/pi/.config/openbox/autostart
```

Add:
```bash
# Disable screen blanking and screensaver
xset s off
xset s noblank
xset -dpms

# Hide the cursor when idle
unclutter -idle 0.5 -root &

# Start the alarm clock backend
/home/pi/alarm-clock/venv/bin/python /home/pi/alarm-clock/backend/main.py &

# Wait for backend to start
sleep 3

# Launch Chromium in kiosk mode
chromium-browser \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-restore-session-state \
  --autoplay-policy=no-user-gesture-required \
  --check-for-update-interval=31536000 \
  http://localhost:8000 &
```

Save and exit.

### 11.2 Configure Auto-Login to Desktop

```bash
sudo raspi-config
```

Navigate to: **1 System Options** → **S5 Boot / Auto Login** → **B4 Desktop Autologin**

Exit raspi-config.

### 11.3 Configure X to Start Openbox

```bash
nano /home/pi/.xinitrc
```

Add:
```bash
exec openbox-session
```

### 11.4 Auto-Start X on Login

```bash
nano /home/pi/.bash_profile
```

Add at the bottom:
```bash
if [ -z "$DISPLAY" ] && [ "$XDG_VTNR" = "1" ]; then
  startx
fi
```

---

## Part 12 — Configure the Touchscreen

### 12.1 Check Orientation

The official RPi touchscreen may need rotation depending on how you mount it.
To rotate 180 degrees, add to `/boot/config.txt`:

```
display_rotate=2
```

Common values: `0` = normal, `1` = 90°, `2` = 180°, `3` = 270°

### 12.2 Touch Calibration (if needed)

```bash
sudo apt install -y xinput-calibrator
xinput_calibrator
```

Follow the on-screen prompts and save the calibration output to:
```bash
sudo nano /etc/X11/xorg.conf.d/99-calibration.conf
```

---

## Part 13 — Install the systemd Service

This ensures the alarm clock restarts automatically after a crash or reboot.

```bash
sudo cp /home/pi/alarm-clock/systemd/alarm-clock.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable alarm-clock
sudo systemctl start alarm-clock
```

Check the service status:
```bash
sudo systemctl status alarm-clock
```

View live logs:
```bash
journalctl -u alarm-clock -f
```

> **Note:** If using the Openbox autostart method (Part 11), you may run the
> backend directly from autostart rather than systemd. Choose one approach —
> systemd is more robust and recommended for production.

---

## Part 14 — Display Brightness Control

The official RPi touchscreen brightness is controlled via:

```bash
# Set brightness (0–255)
echo 100 | sudo tee /sys/class/backlight/rpi_backlight/brightness
```

The Python backend controls this from `hardware.py`. To allow the `pi` user
to write to the backlight without sudo:

```bash
sudo nano /etc/udev/rules.d/99-backlight.rules
```

Add:
```
SUBSYSTEM=="backlight", ACTION=="add", RUN+="/bin/chgrp video /sys/class/backlight/%k/brightness", RUN+="/bin/chmod g+w /sys/class/backlight/%k/brightness"
```

Add pi to the video group:
```bash
sudo usermod -a -G video pi
```

Reload udev rules:
```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
```

---

## Part 15 — Final Checks

Run through this checklist before considering the setup complete:

```
Hardware
[ ] HiFiBerry DAC+ Pro seated firmly on GPIO header
[ ] DS3231 wired to I2C pins, battery inserted
[ ] BH1750 wired to I2C pins
[ ] DHT22 wired to GPIO4 (VCC → 3.3V, GND → GND, DATA → GPIO4 + pull-up)
[ ] Snooze button wired to GPIO17 and GND
[ ] Active buzzer wired to GPIO18 and GND (if fitted — see HiFiBerry note)
[ ] WS2812B data wire on GPIO12, powered from external 5V
[ ] Touchscreen DSI cable connected
[ ] Speakers connected via RCA to DAC+ Pro

Software
[ ] aplay -l shows HiFiBerry DAC+ Pro
[ ] i2cdetect -y 1 shows 0x23 (BH1750) and 0x68 (DS3231)
[ ] hwclock -r returns correct time
[ ] chronyc tracking shows time is synced
[ ] Python venv created and all packages installed
[ ] config/settings.yaml filled in (timezone, HA URL, MQTT broker, DHT22 pin)
[ ] .env file created with HA_TOKEN, MQTT_USER, MQTT_PASS
[ ] Backend logs show "DHT22: XX.X°F  XX.X%RH" on each poll interval
[ ] Home Assistant shows alarm_clock temperature and humidity sensors
[ ] systemd service enabled and running (or Openbox autostart configured)
[ ] Pi reboots cleanly into the kiosk UI
[ ] WebSocket connection established (check backend logs)
[ ] Clock face displays correct time and weather widget
[ ] Snooze button triggers snooze in backend logs
[ ] Buzzer sounds on test alarm (if fitted)
[ ] LED strip responds (sunrise effect triggers before alarm)
```

---

## Useful Commands Reference

```bash
# Check service status
sudo systemctl status alarm-clock

# View live logs
journalctl -u alarm-clock -f

# Restart the service
sudo systemctl restart alarm-clock

# Check I2C devices
sudo i2cdetect -y 1

# Check audio devices
aplay -l

# Set DAC volume
amixer sset 'Digital' 80%

# Read RTC time
sudo hwclock -r

# Write system time to RTC
sudo hwclock -w

# Check NTP sync
chronyc tracking

# Check GPIO (requires pigpio or RPi.GPIO)
python3 -c "import RPi.GPIO as GPIO; GPIO.setmode(GPIO.BCM); print('GPIO OK')"

# Test DHT22 sensor directly (run from project root, venv active)
python3 -c "
import board, adafruit_dht
dht = adafruit_dht.DHT22(board.D4)
print(f'Temp: {dht.temperature}°C  Humidity: {dht.humidity}%')
dht.exit()
"

# Manually set display brightness (0-255)
echo 150 | sudo tee /sys/class/backlight/rpi_backlight/brightness

# Restart kiosk (kill Chromium and let autostart relaunch)
pkill chromium-browser
```

---

## Troubleshooting

**No sound from DAC+ Pro**
- Run `aplay -l` — if HiFiBerry is not listed, check `/boot/config.txt` for `dtoverlay=hifiberry-dacplus` and confirm `dtparam=audio=on` is commented out
- Check speaker power and RCA cable connections

**RTC not detected**
- Run `sudo i2cdetect -y 1` — if `68` is missing, check wiring on SDA/SCL pins
- Confirm I2C is enabled in `raspi-config`
- Confirm `dtoverlay=i2c-rtc,ds3231` is in `/boot/config.txt`

**BH1750 not detected**
- Run `sudo i2cdetect -y 1` — if `23` is missing, check ADDR pin is tied to GND
- Both DS3231 and BH1750 share I2C — both should appear at the same time

**Kiosk doesn't start**
- Check `~/.config/openbox/autostart` syntax
- Run `startx` manually from SSH to see X error output
- Check backend is running: `sudo systemctl status alarm-clock`

**Chromium shows "connection refused"**
- The backend hasn't started yet — increase the `sleep` delay in the Openbox autostart
- Check backend logs: `journalctl -u alarm-clock -f`

**Touch input not working or wrong orientation**
- Check `display_rotate` value in `/boot/config.txt`
- Run `xinput_calibrator` to recalibrate

**WS2812B LEDs not lighting**
- Confirm GPIO12 data connection and external 5V power
- Confirm GND is shared between external supply and Pi
- The rpi_ws281x library may need to run as root — check udev rules in Part 8

**DHT22 not reading / RuntimeError in logs**
- DHT22 transient read errors are normal — the library retries automatically and
  the backend logs them at DEBUG level; isolated errors can be ignored
- If readings never succeed, check wiring: VCC → 3.3V, GND → GND, DATA → GPIO4
- Confirm the 4.7kΩ pull-up resistor is present between DATA and VCC (unless
  your module has one built in)
- Run the one-line test command from the Useful Commands section above
- Confirm `libgpiod2` is installed: `dpkg -l libgpiod2`

**DHT22 sensors not appearing in Home Assistant**
- Check MQTT is connected: look for "MQTT connected" in backend logs
- Confirm MQTT credentials in `.env` match your broker's user/password
- Check the MQTT broker is reachable: `mosquitto_pub -h homeassistant.local -t test -m hello`
- In HA, check **Settings → Devices & Services → MQTT** for the alarm-clock device
- Discovery messages are published at startup — restart the backend service and
  wait 30 seconds for HA to register the entities

**HA token rejected (401 Unauthorized in logs)**
- Confirm `HA_TOKEN` in `.env` is the full token (they are very long — ~180 chars)
- The token is tied to the HA user who created it; confirm that user still exists
- Regenerate the token: HA → Profile → Security → Long-Lived Access Tokens

---

*Setup guide version: 1.1 — June 2026*
