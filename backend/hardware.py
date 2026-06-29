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
    import adafruit_dht

    _i2c = None
    _rtc = None
    _light = None
    _buzzer_pwm = None
    _dht = None
else:
    GPIO = None
    _i2c = None
    _rtc = None
    _light = None
    _buzzer_pwm = None
    _dht = None

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


def setup_dht22(gpio_pin: int) -> None:
    """Initialise the DHT22 sensor on the given BCM GPIO pin."""
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
    Returns (temp, humidity) — either may be None on a read error.
    Temperature is in °F by default; pass unit="C" for Celsius.
    """
    if not IS_PI or _dht is None:
        # Stub: return plausible indoor values
        return (72.0, 45.0) if unit == "F" else (22.2, 45.0)
    try:
        temp_c = _dht.temperature
        humidity = _dht.humidity
        if temp_c is None or humidity is None:
            return None, None
        temp = temp_c * 9 / 5 + 32 if unit == "F" else temp_c
        return round(temp, 1), round(humidity, 1)
    except RuntimeError as e:
        # DHT22 occasionally fails a read — not an error worth logging loudly
        log.debug("DHT22 read error (transient): %s", e)
        return None, None


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
