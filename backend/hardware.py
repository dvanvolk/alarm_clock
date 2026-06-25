"""
Hardware abstraction layer.

On a Raspberry Pi: uses real RPi.GPIO, smbus2, and Adafruit CircuitPython
drivers for the DS3231 RTC and BH1750 light sensor.

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
PIN_SNOOZE = 17   # active-low, internal pull-up
PIN_BUZZER = 18   # hardware PWM

# ---------------------------------------------------------------------------
# Pi-only imports
# ---------------------------------------------------------------------------
if IS_PI:
    import RPi.GPIO as GPIO
    import board
    import busio
    import adafruit_ds3231
    import adafruit_bh1750

    _i2c = None
    _rtc = None
    _light = None
    _buzzer_pwm = None
else:
    GPIO = None
    _i2c = None
    _rtc = None
    _light = None
    _buzzer_pwm = None

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_hardware(config: dict) -> None:
    global _i2c, _rtc, _light

    if not IS_PI:
        log.info("[STUB] Hardware setup skipped (not running on Pi)")
        return

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PIN_SNOOZE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(PIN_BUZZER, GPIO.OUT)

    _i2c = busio.I2C(board.SCL, board.SDA)
    _rtc = adafruit_ds3231.DS3231(_i2c)
    _light = adafruit_bh1750.BH1750(_i2c)
    log.info("Hardware initialised (GPIO, I2C, RTC, light sensor)")


def cleanup() -> None:
    if not IS_PI:
        return
    stop_buzz()
    GPIO.cleanup()
    log.info("GPIO cleaned up")


def get_lux() -> float:
    if not IS_PI or _light is None:
        return 100.0  # stub: moderate daylight
    return _light.lux


def get_rtc_time() -> datetime:
    if not IS_PI or _rtc is None:
        return datetime.now()
    t = _rtc.datetime
    return datetime(t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec)


def set_rtc_time(dt: datetime) -> None:
    if not IS_PI or _rtc is None:
        log.debug("[STUB] set_rtc_time(%s)", dt)
        return
    import time
    _rtc.datetime = time.struct_time(
        (dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second, dt.weekday(), -1, -1)
    )


def buzz(frequency: int = 880, duration_ms: int = 500) -> None:
    """Start buzzer at frequency Hz; non-blocking on Pi (PWM runs in background)."""
    global _buzzer_pwm
    if not IS_PI:
        log.info("[STUB] buzz(%d Hz, %d ms)", frequency, duration_ms)
        return
    if _buzzer_pwm is None:
        _buzzer_pwm = GPIO.PWM(PIN_BUZZER, frequency)
    else:
        _buzzer_pwm.ChangeFrequency(frequency)
    _buzzer_pwm.start(50)  # 50% duty cycle


def stop_buzz() -> None:
    global _buzzer_pwm
    if not IS_PI:
        log.debug("[STUB] stop_buzz()")
        return
    if _buzzer_pwm is not None:
        _buzzer_pwm.stop()
        _buzzer_pwm = None


def setup_snooze_button(callback: Callable) -> None:
    if not IS_PI:
        log.info("[STUB] Snooze button not wired (not on Pi); callback registered but won't fire")
        return
    GPIO.add_event_detect(PIN_SNOOZE, GPIO.FALLING, callback=lambda _: callback(), bouncetime=300)
    log.info("Snooze button ready on GPIO%d", PIN_SNOOZE)
