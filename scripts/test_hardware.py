"""
Hardware interface test script for the alarm clock Pi build.

Tests all seven hardware components and reports PASS/FAIL for each.
Run from the project root with the venv active:

    sudo /home/pi/alarm-clock/venv/bin/python scripts/test_hardware.py

Options:
    --leds N                Number of WS2812B LEDs in your strip (default: 6)
    --test NAME[,NAME...]   Run only specific tests (comma-separated)
                            Valid names: i2c, bh1750, ds3231, dht22, buzzer, leds, snooze, audio

Note: the buzzer, LED strip, and ws281x PWM tests may require sudo unless
the Part 8.2 udev rules are already applied.
"""

import argparse
import errno
import platform
import subprocess
import sys
import threading
import time
from datetime import datetime

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

IS_PI = platform.machine().lower().startswith(("arm", "aarch"))

# ---------------------------------------------------------------------------
# Constants — pin numbers and tuning values match settings.yaml defaults
# ---------------------------------------------------------------------------

PIN_SNOOZE     = 17
PIN_BUZZER     = 13
PIN_DHT22      = 4
PIN_LED        = 12

I2C_BH1750     = 0x23
I2C_DS3231     = 0x68

LED_FREQ       = 800_000
LED_DMA        = 10
LED_INVERT     = False
LED_CHANNEL    = 0
LED_BRIGHTNESS = 64        # ~25% — visible without being blinding

BUZZ_FREQ      = 880       # Hz (A5)
BUZZ_DUTY      = 50        # PWM duty cycle %

SNOOZE_TIMEOUT  = 10       # seconds to wait for button press
DHT_RETRIES     = 5
DHT_RETRY_DELAY = 2        # seconds between DHT22 attempts
RTC_DRIFT_WARN  = 60       # seconds — emit warning above this threshold

# ---------------------------------------------------------------------------
# Module-level state for cleanup (set inside test functions)
# ---------------------------------------------------------------------------

_buzzer_pwm  = None   # RPi.GPIO PWM — must be stopped before GPIO.cleanup()
_dht_device  = None   # adafruit_dht — must call .exit() to release gpiod handle
_strip       = None   # rpi_ws281x PixelStrip — clear pixels before GPIO.cleanup()
_num_leds    = 6      # set from --leds arg in main()

# ---------------------------------------------------------------------------
# Results tracking
# ---------------------------------------------------------------------------

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

results: dict[str, dict] = {}


def record(name: str, status: str, detail: str = "") -> None:
    results[name] = {"status": status, "detail": detail}
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def _ask(question: str) -> bool:
    while True:
        ans = input(f"  {question} [y/n]: ").strip().lower()
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False


# ---------------------------------------------------------------------------
# Cleanup — runs in finally block regardless of test outcome
# ---------------------------------------------------------------------------

def cleanup() -> None:
    global _buzzer_pwm, _dht_device, _strip

    # 1. Stop buzzer PWM before GPIO.cleanup() to avoid segfault
    if _buzzer_pwm is not None:
        try:
            _buzzer_pwm.stop()
        except Exception:
            pass
        _buzzer_pwm = None

    # 2. Clear LED strip so it doesn't freeze on last colour
    if _strip is not None:
        try:
            from rpi_ws281x import Color
            for i in range(_num_leds):
                _strip.setPixelColor(i, Color(0, 0, 0))
            _strip.show()
        except Exception:
            pass
        _strip = None

    # 3. Release DHT22 gpiod file handle
    if _dht_device is not None:
        try:
            _dht_device.exit()
        except Exception:
            pass
        _dht_device = None

    # 4. Release all GPIO channels
    try:
        import RPi.GPIO as GPIO
        GPIO.cleanup()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Test functions
# ---------------------------------------------------------------------------

def test_i2c() -> None:
    try:
        import smbus2
    except ImportError:
        record("i2c", FAIL, "smbus2 not installed")
        return

    bus = None
    try:
        bus = smbus2.SMBus(1)
        found: dict[int, str] = {}
        for addr in range(0x03, 0x78):
            try:
                bus.read_byte(addr)
                found[addr] = "present"
            except OSError as e:
                if e.errno == errno.EBUSY:
                    found[addr] = "kernel-claimed"
        has_bh1750 = I2C_BH1750 in found
        has_ds3231 = I2C_DS3231 in found
        parts = []
        if has_bh1750:
            parts.append(f"0x{I2C_BH1750:02x} (BH1750: {found[I2C_BH1750]})")
        else:
            parts.append(f"0x{I2C_BH1750:02x} (BH1750: NOT FOUND)")
        if has_ds3231:
            parts.append(f"0x{I2C_DS3231:02x} (DS3231: {found[I2C_DS3231]})")
        else:
            parts.append(f"0x{I2C_DS3231:02x} (DS3231: NOT FOUND)")
        other = [f"0x{a:02x}" for a in found if a not in (I2C_BH1750, I2C_DS3231)]
        if other:
            parts.append(f"other: {', '.join(other)}")
        status = PASS if (has_bh1750 and has_ds3231) else FAIL
        record("i2c", status, "  ".join(parts))
    except Exception as e:
        record("i2c", FAIL, str(e))
    finally:
        if bus is not None:
            bus.close()


def test_bh1750() -> None:
    i2c = None
    try:
        import board
        import busio
        import adafruit_bh1750
        i2c = busio.I2C(board.SCL, board.SDA)
        sensor = adafruit_bh1750.BH1750(i2c)
        lux = sensor.lux
        record("bh1750", PASS, f"{lux:.1f} lux")
    except ImportError as e:
        record("bh1750", FAIL, f"missing library: {e}")
    except Exception as e:
        record("bh1750", FAIL, str(e))
    finally:
        if i2c is not None:
            try:
                i2c.deinit()
            except Exception:
                pass


def test_ds3231() -> None:
    i2c = None
    try:
        import board
        import busio
        import adafruit_ds3231
        i2c = busio.I2C(board.SCL, board.SDA)
        rtc = adafruit_ds3231.DS3231(i2c)
        t = rtc.datetime
        rtc_dt = datetime(t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec)
        sys_dt = datetime.utcnow()
        diff = (rtc_dt - sys_dt).total_seconds()
        detail = f"RTC={rtc_dt.strftime('%Y-%m-%d %H:%M:%S')}  sys-diff={diff:+.0f}s"
        if abs(diff) > RTC_DRIFT_WARN:
            detail += f"  [WARNING: drift >{RTC_DRIFT_WARN}s — run: sudo hwclock -w]"
        record("ds3231", PASS, detail)
    except ImportError as e:
        record("ds3231", FAIL, f"missing library: {e}")
    except Exception as e:
        record("ds3231", FAIL, str(e))
    finally:
        if i2c is not None:
            try:
                i2c.deinit()
            except Exception:
                pass


def test_dht22() -> None:
    global _dht_device
    try:
        import board
        import adafruit_dht
    except ImportError as e:
        record("dht22", FAIL, f"missing library: {e}")
        return

    try:
        board_pin = getattr(board, f"D{PIN_DHT22}")
        _dht_device = adafruit_dht.DHT22(board_pin)
        temp_c = humidity = None
        attempt = 0
        for attempt in range(1, DHT_RETRIES + 1):
            try:
                temp_c = _dht_device.temperature
                humidity = _dht_device.humidity
                if temp_c is not None and humidity is not None:
                    break
            except RuntimeError:
                if attempt < DHT_RETRIES:
                    time.sleep(DHT_RETRY_DELAY)
        if temp_c is not None and humidity is not None:
            temp_f = temp_c * 9 / 5 + 32
            record("dht22", PASS, f"{temp_f:.1f}°F ({temp_c:.1f}°C), {humidity:.1f}%RH  (attempt {attempt}/{DHT_RETRIES})")
        else:
            record("dht22", FAIL, f"no valid reading after {DHT_RETRIES} attempts")
    except Exception as e:
        record("dht22", FAIL, str(e))
    finally:
        if _dht_device is not None:
            try:
                _dht_device.exit()
            except Exception:
                pass
            _dht_device = None


def test_buzzer() -> None:
    global _buzzer_pwm
    try:
        import RPi.GPIO as GPIO
    except ImportError as e:
        record("buzzer", FAIL, f"missing library: {e}")
        return

    try:
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(PIN_BUZZER, GPIO.OUT)
        _buzzer_pwm = GPIO.PWM(PIN_BUZZER, BUZZ_FREQ)
        print(f"  Playing {BUZZ_FREQ}Hz tone for 3 seconds...")
        _buzzer_pwm.start(BUZZ_DUTY)
        time.sleep(3)
        _buzzer_pwm.stop()
        _buzzer_pwm = None
        GPIO.cleanup(PIN_BUZZER)
        passed = _ask("Did you hear the buzzer?")
        record("buzzer", PASS if passed else FAIL, "User confirmed" if passed else "User did not confirm")
    except Exception as e:
        record("buzzer", FAIL, str(e))


def test_leds() -> None:
    global _strip
    try:
        from rpi_ws281x import PixelStrip, Color
    except ImportError as e:
        record("leds", FAIL, f"missing library: {e}")
        return

    try:
        _strip = PixelStrip(_num_leds, PIN_LED, LED_FREQ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
        try:
            _strip.begin()
        except PermissionError:
            record("leds", FAIL, "PermissionError — run with sudo or apply Part 8.2 udev rules")
            _strip = None
            return

        colours = [
            ("Red",   Color(255, 0, 0)),
            ("Green", Color(0, 255, 0)),
            ("Blue",  Color(0, 0, 255)),
        ]
        for name, colour in colours:
            print(f"  Setting LEDs to {name}...")
            for i in range(_num_leds):
                _strip.setPixelColor(i, colour)
            _strip.show()
            time.sleep(1)

        for i in range(_num_leds):
            _strip.setPixelColor(i, Color(0, 0, 0))
        _strip.show()

        passed = _ask("Did you see red, green, and blue on the LED strip?")
        record("leds", PASS if passed else FAIL, "User confirmed" if passed else "User did not confirm")
    except Exception as e:
        record("leds", FAIL, str(e))


def test_snooze() -> None:
    try:
        import RPi.GPIO as GPIO
    except ImportError as e:
        record("snooze", FAIL, f"missing library: {e}")
        return

    pressed_event = threading.Event()
    press_time: list[float] = []

    try:
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(PIN_SNOOZE, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        def _on_press(channel):
            press_time.append(time.time())
            pressed_event.set()

        start = time.time()
        GPIO.add_event_detect(PIN_SNOOZE, GPIO.FALLING, callback=_on_press, bouncetime=300)
        print(f"  Press the snooze button within {SNOOZE_TIMEOUT} seconds...")
        pressed_event.wait(timeout=SNOOZE_TIMEOUT)

        try:
            GPIO.remove_event_detect(PIN_SNOOZE)
        except Exception:
            pass

        GPIO.cleanup(PIN_SNOOZE)

        if pressed_event.is_set():
            elapsed = press_time[0] - start if press_time else 0.0
            record("snooze", PASS, f"pressed in {elapsed:.1f}s")
        else:
            record("snooze", FAIL, f"timeout — not pressed within {SNOOZE_TIMEOUT}s")
    except Exception as e:
        record("snooze", FAIL, str(e))


def test_audio() -> None:
    try:
        result = subprocess.run(
            ["aplay", "-l"],
            capture_output=True, text=True, timeout=10,
        )
        output = result.stdout
        detected = any(kw in output.lower() for kw in ("hifiberry", "sndrpihifiberry", "dacplus"))
        for line in output.splitlines():
            print(f"    {line}")
        print()
        print("  To test playback:  speaker-test -D hw:1,0 -c 2 -t wav")
        if detected:
            card_line = next((l for l in output.splitlines() if "hifiberry" in l.lower()), "")
            record("audio", PASS, card_line.strip() or "HiFiBerry found")
        else:
            record("audio", FAIL, "HiFiBerry not found in aplay -l")
    except FileNotFoundError:
        record("audio", FAIL, "aplay not found — install alsa-utils")
    except subprocess.TimeoutExpired:
        record("audio", FAIL, "aplay -l timed out")
    except Exception as e:
        record("audio", FAIL, str(e))


# ---------------------------------------------------------------------------
# Test registry
# ---------------------------------------------------------------------------

ALL_TESTS = [
    ("i2c",    test_i2c),
    ("bh1750", test_bh1750),
    ("ds3231", test_ds3231),
    ("dht22",  test_dht22),
    ("buzzer", test_buzzer),
    ("leds",   test_leds),
    ("snooze", test_snooze),
    ("audio",  test_audio),
]

VALID_NAMES = [name for name, _ in ALL_TESTS]

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary() -> None:
    print()
    print("=" * 60)
    print(" HARDWARE TEST SUMMARY")
    print("=" * 60)
    print(f"  {'Test':<12} {'Status':<8} Detail")
    print("  " + "─" * 56)
    for name, _ in ALL_TESTS:
        if name not in results:
            continue
        r = results[name]
        print(f"  {name:<12} {r['status']:<8} {r['detail']}")
    print("=" * 60)
    counts = {PASS: 0, FAIL: 0, SKIP: 0}
    for r in results.values():
        counts[r["status"]] += 1
    print(f"  Result: {counts[PASS]} PASS, {counts[FAIL]} FAIL, {counts[SKIP]} SKIP")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    global _num_leds

    parser = argparse.ArgumentParser(description="Alarm clock hardware interface tests")
    parser.add_argument("--leds", type=int, default=6, metavar="N",
                        help="Number of WS2812B LEDs in the strip (default: 6)")
    parser.add_argument("--test", type=str, default=None, metavar="NAMES",
                        help=f"Comma-separated tests to run. Valid: {', '.join(VALID_NAMES)}")
    args = parser.parse_args()

    _num_leds = args.leds

    # Resolve which tests to run
    if args.test is not None:
        requested = [n.strip() for n in args.test.split(",")]
        unknown = [n for n in requested if n not in VALID_NAMES]
        if unknown:
            print(f"Unknown test(s): {', '.join(unknown)}")
            print(f"Valid names: {', '.join(VALID_NAMES)}")
            sys.exit(1)
    else:
        requested = VALID_NAMES

    if not IS_PI:
        print("Not running on a Raspberry Pi — skipping all hardware tests.")
        for name, _ in ALL_TESTS:
            record(name, SKIP, "not on Pi")
        print_summary()
        sys.exit(0)

    print()
    print("Alarm Clock Hardware Test")
    print(f"LEDs: {_num_leds}   Tests: {', '.join(requested)}")
    print("Stop the alarm-clock service before running if it is active.")
    print()

    # Mark skipped tests up front so they appear in the summary
    for name, _ in ALL_TESTS:
        if name not in requested:
            record(name, SKIP, "not selected")

    try:
        for name, fn in ALL_TESTS:
            if name not in requested:
                continue
            print(f"\n── {name} ──")
            fn()
    except KeyboardInterrupt:
        print("\n\nInterrupted.")
    finally:
        cleanup()

    print_summary()
    failed = any(r["status"] == FAIL for r in results.values())
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
