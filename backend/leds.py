"""
leds.py — WS2812B sunrise LED effect.

On Raspberry Pi: drives LED strip via rpi_ws281x on GPIO12 (PWM0).
On Windows/dev: all calls are no-ops that log so you can trace the ramp.
"""

import asyncio
import logging
import platform

log = logging.getLogger(__name__)

IS_PI = platform.machine().lower().startswith(("arm", "aarch"))

if IS_PI:
    try:
        from rpi_ws281x import PixelStrip, Color
        _HW_OK = True
    except ImportError:
        log.warning("rpi_ws281x not installed — LED effect disabled")
        _HW_OK = False
else:
    _HW_OK = False

# Hardware constants (Pi only)
_LED_PIN     = 12       # GPIO12 = PWM0
_LED_FREQ    = 800_000  # 800 kHz
_LED_DMA     = 10
_LED_INVERT  = False
_LED_CHANNEL = 0

_strip = None  # PixelStrip instance, set by setup_leds()


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def setup_leds(num_leds: int, max_brightness: int) -> None:
    """Initialise the LED strip. Must be called once at startup."""
    global _strip
    if not _HW_OK:
        log.info("[STUB] LED setup: %d LEDs, max_brightness=%d", num_leds, max_brightness)
        return
    _strip = PixelStrip(
        num_leds, _LED_PIN, _LED_FREQ, _LED_DMA,
        _LED_INVERT, max_brightness, _LED_CHANNEL,
    )
    _strip.begin()
    log.info("LED strip ready: %d LEDs on GPIO%d", num_leds, _LED_PIN)


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

def _sunrise_color(progress: float) -> tuple[int, int, int]:
    """
    Map sunrise progress (0.0–1.0) to an RGB value.

    0.0  — off (before dawn)
    0.4  — deep red  (ember glow)
    0.75 — orange    (sunrise)
    1.0  — warm white (full daylight)
    """
    p = max(0.0, min(1.0, progress))

    if p <= 0.4:
        t = p / 0.4
        r = int(180 * t)
        g = int(20 * t)
        b = 0
    elif p <= 0.75:
        t = (p - 0.4) / 0.35
        r = int(180 + 75 * t)   # 180 → 255
        g = int(20 + 110 * t)   # 20  → 130
        b = 0
    else:
        t = (p - 0.75) / 0.25
        r = 255
        g = int(130 + 100 * t)  # 130 → 230
        b = int(100 * t)        # 0   → 100

    return r, g, b


def _set_all(num_leds: int, r: int, g: int, b: int) -> None:
    if not _HW_OK or _strip is None:
        log.debug("[STUB] LED RGB=(%d, %d, %d)", r, g, b)
        return
    color = Color(r, g, b)
    for i in range(num_leds):
        _strip.setPixelColor(i, color)
    _strip.show()


# ---------------------------------------------------------------------------
# Public API (called from AlarmScheduler)
# ---------------------------------------------------------------------------

async def run_sunrise(num_leds: int, max_brightness: int, ramp_seconds: int) -> None:
    """
    Animate the sunrise ramp over ramp_seconds.
    Runs as a cancellable asyncio task — cancelled on snooze/dismiss.
    Updates every 10 s (fine-grained enough for a slow ramp).
    """
    scale = max_brightness / 255.0
    update_interval = 10  # seconds between LED updates
    steps = max(ramp_seconds // update_interval, 1)
    step_delay = ramp_seconds / steps

    log.info("[LED] Sunrise starting: %d LEDs, %ds ramp", num_leds, ramp_seconds)
    try:
        for step in range(steps + 1):
            progress = step / steps
            r, g, b = _sunrise_color(progress)
            r = int(r * scale)
            g = int(g * scale)
            b = int(b * scale)
            _set_all(num_leds, r, g, b)
            log.debug("[LED] %.0f%% → RGB(%d, %d, %d)", progress * 100, r, g, b)
            if step < steps:
                await asyncio.sleep(step_delay)
    except asyncio.CancelledError:
        pass
    log.info("[LED] Sunrise ramp complete")


def set_full(num_leds: int, max_brightness: int) -> None:
    """Full warm-white — called when the alarm fires."""
    scale = max_brightness / 255.0
    r, g, b = int(255 * scale), int(230 * scale), int(100 * scale)
    log.info("[LED] Full warm-white: RGB(%d, %d, %d)", r, g, b)
    _set_all(num_leds, r, g, b)


def clear(num_leds: int) -> None:
    """Turn all LEDs off — called on dismiss."""
    log.info("[LED] Cleared")
    _set_all(num_leds, 0, 0, 0)
