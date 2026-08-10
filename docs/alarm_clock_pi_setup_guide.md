# Alarm Clock — Raspberry Pi Setup Guide

Complete step-by-step guide to setting up the Raspberry Pi 3B for the alarm clock project,
from a fresh SD card to a running kiosk.

---

## What You Need

### Hardware
- Raspberry Pi 3B
- Official Raspberry Pi 7" Touchscreen (DSI)
- 2× Adafruit MAX98357A I2S Amplifier Breakout (#3006)
- 2× Adafruit Mono Enclosed Speaker 3W 4Ω (#4445)
- DS3231 RTC module + CR2032 battery
- Adafruit BH1750 light sensor breakout (or GY-302 bare module)
- Momentary pushbutton × 2 (snooze + power)
- Active buzzer
- WS2812B LED strip
- 74AHCT125 level shifter IC
- MicroSD card (16GB minimum, Class 10 or better)
- 5V/4A power supply with barrel jack (5.5mm/2.1mm)
- Jumper wires and breadboard or terminal blocks
- TONOR G11 USB microphone (for future voice control)

### On Your Computer
- [Raspberry Pi Imager](https://www.raspberrypi.com/software/) installed
- SSH client (Terminal on Mac/Linux, Windows Terminal on Windows)

---

## Part 1 — Flash the SD Card

### 1.1 Open Raspberry Pi Imager

1. Launch Raspberry Pi Imager
2. Click **Choose Device** → **Raspberry Pi 3**
3. Click **Choose OS** → **Raspberry Pi OS (64-bit)** (full desktop version)
4. Click **Choose Storage** → select your SD card

### 1.2 Configure Before Writing

Click **Edit Settings** before writing:

**General tab:**
- Hostname: `alarmclock`
- Username: `pi`, set a strong password
- Configure WiFi: network name, password, country code
- Locale: your timezone and keyboard layout

**Services tab:**
- Enable SSH → Use password authentication

Click **Save** → **Yes** → **Yes** to write.

### 1.3 Boot the Pi

1. Insert SD card into Pi
2. Connect touchscreen via DSI ribbon cable before powering on
3. Power on — first boot takes 1–2 minutes
4. Connect via SSH: `ssh pi@alarmclock.local`

---

## Part 2 — Initial System Setup

### 2.1 Update the System

```bash
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

Reconnect after reboot: `ssh pi@alarmclock.local`

### 2.2 Set the Timezone

```bash
sudo raspi-config
```

Navigate to: **5 Localisation Options** → **L2 Timezone** → select your region.

---

## Part 3 — Enable Required Interfaces

```bash
sudo raspi-config
```

Under **3 Interface Options**, enable:
- **I2C** — for DS3231 RTC and BH1750 light sensor

Exit and reboot:
```bash
sudo reboot
```

---

## Part 4 — Configure the MAX98357A Stereo Amplifiers

### 4.1 Disable Default Audio

```bash
sudo nano /boot/config.txt
```

Comment out the default audio line:
```
# dtparam=audio=on
```

### 4.2 Enable I2S DAC Overlay

Add to the bottom of `/boot/config.txt`:
```
# MAX98357A I2S stereo amplifier
dtoverlay=hifiberry-dac
```

Save and reboot:
```bash
sudo reboot
```

### 4.3 Verify I2S Audio Device

```bash
aplay -l
```

You should see a HifiBerry DAC or similar I2S device listed.

### 4.4 Configure ALSA Software Volume

The MAX98357A has no hardware volume control — use ALSA softvol:

```bash
sudo nano /etc/asound.conf
```

Add:
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

Save and test audio:
```bash
speaker-test -c 2 -t wav
```

### 4.5 Wire the MAX98357A Boards

Both boards share the same I2S lines from the Pi:

| Signal | GPIO | Pi Pin | Both boards |
|---|---|---|---|
| BCLK | GPIO18 | Pin 12 | ✓ |
| LRCLK | GPIO19 | Pin 35 | ✓ |
| DIN | GPIO20 | Pin 38 | ✓ |
| GND | — | Pin 39 | ✓ |
| VIN | — | Pin 2 (5V) | ✓ |

**Stereo channel selection via SD pin:**

| Board | SD Pin Connection | Channel |
|---|---|---|
| Amp #1 (Left) | SD → 3.3V via 100kΩ resistor | Left only |
| Amp #2 (Right) | SD → GND via 100kΩ resistor | Right only |

Connect speakers (Adafruit #4445 bare wires) to the green screw terminal on each board.

---

## Part 5 — Configure the DS3231 RTC

### 5.1 Wire the DS3231

Connect to the Pi GPIO header (or HAT pass-through):

| DS3231 Pin | Pi Pin | GPIO |
|---|---|---|
| VCC | Pin 1 | 3.3V |
| GND | Pin 6 | GND |
| SDA | Pin 3 | GPIO2 |
| SCL | Pin 5 | GPIO3 |

Insert CR2032 battery into the module.

### 5.2 Enable the RTC Driver

```bash
sudo nano /boot/config.txt
```

Add:
```
# DS3231 RTC
dtoverlay=i2c-rtc,ds3231
```

Save and reboot:
```bash
sudo reboot
```

### 5.3 Verify RTC Detection

```bash
sudo i2cdetect -y 1
```

You should see `68` in the grid.

### 5.4 Remove the Fake Hardware Clock

```bash
sudo apt remove -y fake-hwclock
sudo update-rc.d -f fake-hwclock remove
sudo systemctl disable fake-hwclock
```

### 5.5 Fix hwclock Script

```bash
sudo nano /lib/udev/hwclock-set
```

Comment out these three lines:
```bash
#if [ -e /run/systemd/system ] ; then
# exit 0
#fi
```

### 5.6 Sync and Verify

Once NTP is synced (`timedatectl` shows synchronized), write to RTC:
```bash
sudo hwclock -w
sudo hwclock -r
```

---

## Part 6 — Configure the BH1750 Light Sensor

### 6.1 Wire the BH1750

Shares the I2C bus with the DS3231:

| BH1750 Pin | Pi Pin | GPIO |
|---|---|---|
| VCC | Pin 1 | 3.3V |
| GND | Pin 6 | GND |
| SDA | Pin 3 | GPIO2 |
| SCL | Pin 5 | GPIO3 |
| ADDR | GND | Sets address to 0x23 |

If using the Adafruit BH1750 with STEMMA QT, use a STEMMA QT to JST SH cable to the I2C pins.

### 6.2 Verify Detection

```bash
sudo i2cdetect -y 1
```

You should now see both `23` (BH1750) and `68` (DS3231).

---

## Part 7 — Wire the GPIO Components

### Snooze Button (GPIO17)
| Connection | Detail |
|---|---|
| One leg | GPIO17 (Pin 11) |
| Other leg | GND (Pin 9) |

Internal pull-up used in software — no external resistor needed.

### Power Shutdown Button (GPIO26)
| Connection | Detail |
|---|---|
| One leg | GPIO26 (Pin 37) via 330Ω resistor |
| Other leg | GND |

Add to `/boot/config.txt`:
```
dtoverlay=gpio-shutdown,gpio_pin=26
```

### Power-On Button (GPIO3)
| Connection | Detail |
|---|---|
| One leg | GPIO3 (Pin 5) via 330Ω resistor |
| Other leg | GND |

This is a Pi hardware feature — pressing it wakes the Pi from halt state. No software config needed. Can be the same button as shutdown or a separate one.

### Active Buzzer (GPIO13)
| Buzzer Pin | Connection |
|---|---|
| + (positive) | GPIO13 (Pin 33) |
| - (negative) | GND (Pin 34) |

> **Note:** GPIO13 is hardware PWM1 — ideal for buzzer tone generation.
> GPIO18 (PWM0) is reserved for I2S BCLK and cannot be used for the buzzer.

### WS2812B LED Strip (GPIO12) via 74AHCT125

The Pi's 3.3V logic is technically out of spec for WS2812B — use a 74AHCT125 level shifter:

```
GPIO12 (3.3V) → 74AHCT125 input → 74AHCT125 output (5V) → WS2812B Data In
```

74AHCT125 wiring:
- VCC → 5V
- GND → GND
- OE (output enable) → GND (always enabled)
- Input A → GPIO12
- Output Y → WS2812B Data In

WS2812B power:
| LED Strip Wire | Connection |
|---|---|
| Data In | 74AHCT125 output |
| +5V | External 5V supply |
| GND | External GND + Pi GND (common ground) |

> **Important:** Power WS2812B from an external 5V supply — NOT the Pi's 5V pin.
> A 60mA-per-LED rule applies. Always connect external supply GND to Pi GND.

---

## Part 8 — Configure Display Brightness Control

The official RPi touchscreen brightness is controlled via sysfs:

```bash
# Set brightness (0–255)
echo 150 | sudo tee /sys/class/backlight/rpi_backlight/brightness
```

Allow the `pi` user to control backlight without sudo:

```bash
sudo nano /etc/udev/rules.d/99-backlight.rules
```

Add:
```
SUBSYSTEM=="backlight", ACTION=="add", RUN+="/bin/chgrp video /sys/class/backlight/%k/brightness", RUN+="/bin/chmod g+w /sys/class/backlight/%k/brightness"
```

Add pi to video group:
```bash
sudo usermod -a -G video pi
sudo udevadm control --reload-rules && sudo udevadm trigger
```

### Display Rotation (if needed)

Add to `/boot/config.txt`:
```
display_rotate=2    # 0=normal, 1=90°, 2=180°, 3=270°
```

---

## Part 9 — Install System Dependencies

### 9.1 Core Packages

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
  python3-alsaaudio \
  chrony \
  i2c-tools \
  libgpiod2
```

### 9.2 WS2812B LED Support

```bash
sudo pip3 install rpi_ws281x --break-system-packages
```

Add udev rule for PWM access without root:
```bash
sudo nano /etc/udev/rules.d/99-pwm.rules
```

Add:
```
SUBSYSTEM=="pwm*", PROGRAM="/bin/sh -c 'chown -R root:gpio /sys/class/pwm && chmod -R 770 /sys/class/pwm'"
```

```bash
sudo usermod -a -G gpio pi
```

---

## Part 10 — Clone the Project and Install Python Dependencies

### 10.1 Clone the Repository

```bash
cd /home/pi
git clone https://github.com/YOUR_USERNAME/alarm-clock.git
cd alarm-clock
```

### 10.2 Create a Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 10.3 Install Python Dependencies

```bash
pip install \
  fastapi \
  uvicorn \
  websockets \
  RPi.GPIO \
  smbus2 \
  adafruit-circuitpython-ds3231 \
  adafruit-circuitpython-bh1750 \
  rpi-ws281x \
  pyyaml \
  paho-mqtt \
  aiohttp \
  python-dateutil \
  alsaaudio
```

### 10.4 Copy and Edit the Config File

```bash
cp config/settings.yaml.example config/settings.yaml
nano config/settings.yaml
```

Fill in: timezone, HA URL, HA token, MQTT broker, alarm times, music URIs.

---

## Part 11 — Configure NTP with chrony

```bash
sudo systemctl enable chrony
sudo systemctl start chrony
chronyc tracking
```

Optionally add your HA NTP server to `/etc/chrony/chrony.conf`:
```
server homeassistant.local iburst prefer
```

---

## Part 12 — Configure Kiosk Mode

### 12.1 Set Up Openbox Autostart

```bash
mkdir -p /home/pi/.config/openbox
nano /home/pi/.config/openbox/autostart
```

Add:
```bash
# Disable screen blanking
xset s off
xset s noblank
xset -dpms

# Hide cursor when idle
unclutter -idle 0.5 -root &

# Start alarm clock backend
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

### 12.2 Configure Auto-Login to Desktop

```bash
sudo raspi-config
```

Navigate to: **1 System Options** → **S5 Boot / Auto Login** → **B4 Desktop Autologin**

### 12.3 Configure X to Start Openbox

```bash
nano /home/pi/.xinitrc
```

Add:
```bash
exec openbox-session
```

### 12.4 Auto-Start X on Login

```bash
nano /home/pi/.bash_profile
```

Add:
```bash
if [ -z "$DISPLAY" ] && [ "$XDG_VTNR" = "1" ]; then
  startx
fi
```

---

## Part 13 — Install the systemd Service

```bash
sudo cp /home/pi/alarm-clock/systemd/alarm-clock.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable alarm-clock
sudo systemctl start alarm-clock
sudo systemctl status alarm-clock
```

View live logs:
```bash
journalctl -u alarm-clock -f
```

> **Note:** If using the Openbox autostart method (Part 12), choose one approach
> for starting the backend — systemd is more robust and recommended.

---

## Part 14 — Touch Calibration (if needed)

```bash
sudo apt install -y xinput-calibrator
xinput_calibrator
```

Save output to:
```bash
sudo nano /etc/X11/xorg.conf.d/99-calibration.conf
```

---

## Part 15 — Final Checklist

```
Hardware
[ ] DS3231 wired to I2C, CR2032 battery inserted
[ ] BH1750 wired to I2C (ADDR pin to GND)
[ ] Snooze button wired to GPIO17 and GND
[ ] Power shutdown button wired to GPIO26 via 330Ω and GND
[ ] Power-on button wired to GPIO3 via 330Ω and GND
[ ] Active buzzer wired to GPIO13 and GND
[ ] 74AHCT125 level shifter wired between GPIO12 and WS2812B data
[ ] WS2812B powered from external 5V, GND shared with Pi
[ ] MAX98357A #1: I2S lines connected, SD → 3.3V via 100kΩ (Left)
[ ] MAX98357A #2: I2S lines connected, SD → GND via 100kΩ (Right)
[ ] Speakers connected to amp screw terminals
[ ] Touchscreen DSI cable connected

Software
[ ] aplay -l shows I2S DAC device
[ ] i2cdetect -y 1 shows 0x23 (BH1750) and 0x68 (DS3231)
[ ] hwclock -r returns correct time
[ ] chronyc tracking shows time is synced
[ ] Python venv created and all packages installed
[ ] config/settings.yaml filled in
[ ] systemd service enabled and running
[ ] Pi reboots into kiosk UI
[ ] Clock face shows correct time
[ ] Snooze button triggers snooze in logs
[ ] Buzzer sounds on test alarm (GPIO13)
[ ] Both speakers produce audio (speaker-test -c 2 -t wav)
[ ] LED strip responds to test command
[ ] Display brightness changes via backlight sysfs
```

---

## Useful Commands Reference

```bash
# Service management
sudo systemctl status alarm-clock
sudo systemctl restart alarm-clock
journalctl -u alarm-clock -f

# Hardware checks
sudo i2cdetect -y 1          # Show I2C devices (expect 0x23 and 0x68)
sudo hwclock -r               # Read RTC time
sudo hwclock -w               # Write system time to RTC
chronyc tracking              # NTP sync status
aplay -l                      # List audio devices

# Audio
speaker-test -c 2 -t wav      # Test both speakers
amixer sset 'Speaker' 80%     # Set ALSA softvol level

# Display brightness (0–255)
echo 150 | sudo tee /sys/class/backlight/rpi_backlight/brightness

# GPIO test
python3 -c "import RPi.GPIO as GPIO; GPIO.setmode(GPIO.BCM); print('GPIO OK')"

# Restart kiosk
pkill chromium-browser
```

---

## Troubleshooting

**No sound from speakers**
- Run `aplay -l` — confirm I2S DAC is listed
- Check `dtoverlay=hifiberry-dac` is in `/boot/config.txt` and `dtparam=audio=on` is commented out
- Verify speaker wires in MAX98357A screw terminals
- Check SD pin wiring — 100kΩ to 3.3V (Left) and 100kΩ to GND (Right)
- Run `amixer` to confirm softvol control exists

**RTC not detected (no 0x68 on i2cdetect)**
- Check SDA/SCL wiring
- Confirm I2C enabled in raspi-config
- Confirm `dtoverlay=i2c-rtc,ds3231` in `/boot/config.txt`

**BH1750 not detected (no 0x23 on i2cdetect)**
- Check ADDR pin is tied to GND
- Verify VCC is 3.3V not 5V

**Buzzer not sounding**
- Confirm buzzer is on GPIO13 (Pin 33), not GPIO18
- Test: `python3 -c "import RPi.GPIO as GPIO; GPIO.setmode(GPIO.BCM); GPIO.setup(13,GPIO.OUT); GPIO.output(13,1)"`

**WS2812B LEDs not lighting**
- Confirm 74AHCT125 level shifter is in circuit between GPIO12 and LED data
- Confirm external 5V power supply for LEDs
- Confirm GND is shared between external supply and Pi
- rpi_ws281x may need root — check udev rules

**Kiosk doesn't start / Chromium shows "connection refused"**
- Check backend is running: `sudo systemctl status alarm-clock`
- Increase sleep delay in Openbox autostart
- Check backend logs: `journalctl -u alarm-clock -f`

**Touch input wrong orientation**
- Adjust `display_rotate` in `/boot/config.txt`
- Run `xinput_calibrator` to recalibrate

---

*Setup guide version: 1.1 — August 2026*
