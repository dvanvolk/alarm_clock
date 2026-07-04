"""
Hardware abstraction layer.

On Raspberry Pi OS Bookworm: uses gpiozero with the lgpio backend (default on
Bookworm) for the snooze button and software PWM buzzer. No daemon required.

On any other platform: all calls are no-ops or return plausible stub values
so the backend runs normally during development on a Windows/macOS machine.
"""

import logging
import platform
from datetime import datetime
from typing import Callable

log = logging.getLogger(__name__)

IS_PI = platform.machine().lower().startswith(("arm", "aarch"))

# GPIO pin assignments
PIN_SNOOZE = 17    # active-low, internal pull-up
_buzzer_gpio = 13  # BCM GPIO13; overridden by config

# ---------------------------------------------------------------------------
# Pi-only imports
# ---------------------------------------------------------------------------
if IS_PI:
    import board
    import busio
    import adafruit_bh1750
    import adafruit_dht
    from gpiozero import Button, PWMOutputDevice

    _button: Button | None = None
    _buzzer: PWMOutputDevice | None = None
    _i2c = None
    _light = None
    _dht = None
else:
    _button = None
    _buzzer = None
    _i2c = None
    _light = None
    _dht = None

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_hardware(config: dict) -> None:
    global _buzzer, _i2c, _light, _buzzer_gpio
    _buzzer_gpio = config.get("buzzer", {}).get("gpio_pin", 13)

    if not IS_PI:
        log.info("[STUB] Hardware setup skipped (not running on Pi)")
        return

    _buzzer = PWMOutputDevice(_buzzer_gpio, frequency=1000, initial_value=0)
    _i2c = busio.I2C(board.SCL, board.SDA)
    _light = adafruit_bh1750.BH1750(_i2c)
    log.info("Hardware initialised (gpiozero/lgpio, I2C, light sensor)")


def setup_dht22(gpio_pin: int) -> None:
    global _dht
    if not IS_PI:
        log.info("[STUB] DHT22 setup skipped (not on Pi), pin GPIO%d", gpio_pin)
        return
    board_pin = getattr(board, f"D{gpio_pin}", None)
    if board_pin is None:
        log.error("DHT22: invalid GPIO pin %d", gpio_pin)
        return
    _dht = adafruit_dht.DHT22(board_pin)
    log.info("DHT22 ready on GPIO%d", gpio_pin)


def read_dht22(unit: str = "F") -> tuple[float | None, float | None]:
    """
    Read temperature and humidity from the DHT22.
    Returns (temp, humidity) — either may be None on a transient read error.
    Temperature is in °F by default; pass unit="C" for Celsius.
    """
    if not IS_PI or _dht is None:
        return (72.0, 45.0) if unit == "F" else (22.2, 45.0)
    try:
        temp_c = _dht.temperature
        humidity = _dht.humidity
        if temp_c is None or humidity is None:
            return None, None
        temp = temp_c * 9 / 5 + 32 if unit == "F" else temp_c
        return round(temp, 1), round(humidity, 1)
    except RuntimeError as e:
        log.debug("DHT22 read error (transient): %s", e)
        return None, None


def cleanup() -> None:
    if not IS_PI:
        return
    stop_buzz()
    if _buzzer is not None:
        try:
            _buzzer.close()
        except Exception:
            pass
    if _button is not None:
        try:
            _button.close()
        except Exception:
            pass
    if _i2c is not None:
        try:
            _i2c.deinit()
        except Exception:
            pass
    log.info("Hardware cleaned up")


def get_lux() -> float:
    if not IS_PI or _light is None:
        return 100.0
    return _light.lux


def get_rtc_time() -> datetime:
    if not IS_PI:
        return datetime.now()
    try:
        # The kernel owns the DS3231 via i2c-rtc overlay; read through sysfs.
        date_str = open("/sys/class/rtc/rtc0/date").read().strip()
        time_str = open("/sys/class/rtc/rtc0/time").read().strip()
        return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
    except Exception as e:
        log.warning("RTC sysfs read failed, falling back to system time: %s", e)
        return datetime.now()


def set_rtc_time(dt: datetime) -> None:
    # On Bookworm with i2c-rtc overlay, systemd syncs the RTC automatically.
    log.debug("set_rtc_time(%s) — no-op, systemd manages RTC sync on Bookworm", dt)


def buzz(frequency: int = 880, duty: int = 50) -> None:
    """Start passive piezo via software PWM. Call stop_buzz() to silence."""
    if not IS_PI or _buzzer is None:
        log.info("[STUB] buzz(%d Hz, duty=%d%%)", frequency, duty)
        return
    _buzzer.frequency = frequency
    _buzzer.value = duty / 100


def stop_buzz() -> None:
    if not IS_PI or _buzzer is None:
        log.debug("[STUB] stop_buzz()")
        return
    _buzzer.value = 0


def setup_snooze_button(callback: Callable) -> None:
    global _button
    if not IS_PI:
        log.info("[STUB] Snooze button not wired (not on Pi)")
        return
    _button = Button(PIN_SNOOZE, pull_up=True, bounce_time=0.05)
    _button.when_pressed = callback
    log.info("Snooze button ready on GPIO%d (gpiozero/lgpio)", PIN_SNOOZE)
