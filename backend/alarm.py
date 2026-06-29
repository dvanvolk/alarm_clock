import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import TYPE_CHECKING, Optional

import backend.hardware as hw
import backend.leds as leds

if TYPE_CHECKING:
    from backend.ha_client import HAClient

log = logging.getLogger(__name__)

DAY_MAP = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3,
    "fri": 4, "sat": 5, "sun": 6,
}


class AlarmState(Enum):
    IDLE = auto()
    SUNRISE = auto()   # LED ramp running, alarm not yet fired
    FIRING = auto()
    SNOOZED = auto()


@dataclass
class Alarm:
    label: str
    time: str        # "HH:MM"
    days: list[str]  # ["mon", "tue", ...]
    enabled: bool
    sound: str       # "music_assistant" | "buzzer"
    music_uri: str = ""

    def matches(self, now: datetime) -> bool:
        if not self.enabled:
            return False
        h, m = map(int, self.time.split(":"))
        return now.weekday() in [DAY_MAP[d] for d in self.days if d in DAY_MAP] \
            and now.hour == h and now.minute == m

    def would_fire_today(self, now: datetime) -> bool:
        """True if this alarm is scheduled for today, regardless of time."""
        return self.enabled and \
            now.weekday() in [DAY_MAP[d] for d in self.days if d in DAY_MAP]


def _parse_alarms(config: dict) -> list[Alarm]:
    alarms = []
    for entry in config.get("alarms", []):
        alarms.append(Alarm(
            label=entry.get("label", ""),
            time=entry.get("time", "00:00"),
            days=entry.get("days", []),
            enabled=entry.get("enabled", True),
            sound=entry.get("sound", "buzzer"),
            music_uri=entry.get("music_uri", ""),
        ))
    return alarms


class AlarmScheduler:
    def __init__(self, config: dict, manager):
        self._manager = manager
        self._ha: Optional["HAClient"] = None
        self._alarms: list[Alarm] = []
        self._state = AlarmState.IDLE
        self._active: Optional[Alarm] = None
        self._snooze_until: Optional[datetime] = None
        self._volume_task: Optional[asyncio.Task] = None
        self._buzz_task: Optional[asyncio.Task] = None
        self._sunrise_task: Optional[asyncio.Task] = None
        self._snooze_minutes = 9
        self._audio_cfg: dict = {}
        self._sunrise_cfg: dict = {}
        self.reload(config)

    def set_ha_client(self, ha: "HAClient") -> None:
        self._ha = ha

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def reload(self, config: dict) -> None:
        self._alarms = _parse_alarms(config)
        self._snooze_minutes = config.get("snooze", {}).get("duration_minutes", 9)
        self._audio_cfg = config.get("audio", {})
        self._sunrise_cfg = config.get("sunrise", {})
        self._publish_ha_state()

    # ------------------------------------------------------------------
    # Tick — called every 30 s from main
    # ------------------------------------------------------------------

    async def tick(self, now: datetime) -> None:
        if self._state == AlarmState.IDLE:
            for alarm in self._alarms:
                if alarm.matches(now):
                    await self._fire(alarm)
                    return
            # Check if any alarm is within the sunrise window
            if self._sunrise_cfg.get("enabled"):
                for alarm in self._alarms:
                    if self._in_sunrise_window(alarm, now):
                        await self._start_sunrise(alarm, now)
                        return

        elif self._state == AlarmState.SUNRISE:
            for alarm in self._alarms:
                if alarm.matches(now):
                    await self._fire(alarm)
                    return

        elif self._state == AlarmState.SNOOZED:
            if self._snooze_until and now >= self._snooze_until:
                log.info("Snooze expired, re-firing alarm")
                await self._fire(self._active)

    # ------------------------------------------------------------------
    # Fire
    # ------------------------------------------------------------------

    def _in_sunrise_window(self, alarm: Alarm, now: datetime) -> bool:
        if not alarm.would_fire_today(now):
            return False
        ramp = self._sunrise_cfg.get("ramp_minutes", 20)
        h, m = map(int, alarm.time.split(":"))
        alarm_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if alarm_dt <= now:
            return False
        return (alarm_dt - now).total_seconds() <= ramp * 60

    async def _start_sunrise(self, alarm: Alarm, now: datetime) -> None:
        self._state = AlarmState.SUNRISE
        self._active = alarm
        num_leds = self._sunrise_cfg.get("num_leds", 6)
        max_brightness = self._sunrise_cfg.get("max_brightness", 255)
        h, m = map(int, alarm.time.split(":"))
        alarm_dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
        remaining_seconds = max(int((alarm_dt - now).total_seconds()), 1)
        log.info("Sunrise: %s — %ds ramp on %d LEDs", alarm.label, remaining_seconds, num_leds)
        self._sunrise_task = asyncio.create_task(
            leds.run_sunrise(num_leds, max_brightness, remaining_seconds)
        )

    async def _fire(self, alarm: Alarm) -> None:
        self._state = AlarmState.FIRING
        self._active = alarm
        log.info("Alarm firing: %s at %s", alarm.label, alarm.time)

        await self._manager.broadcast({
            "type": "alarm_firing",
            "label": alarm.label,
            "time": alarm.time,
        })
        self._publish_ha_state()

        num_leds = self._sunrise_cfg.get("num_leds", 6)
        max_brightness = self._sunrise_cfg.get("max_brightness", 255)
        leds.set_full(num_leds, max_brightness)

        # Start sound
        if alarm.sound == "music_assistant" and self._ha:
            await self._ha.trigger_music(alarm.music_uri, self._audio_cfg)
        elif alarm.sound == "music_assistant":
            log.info("[NO HA] Would play Music Assistant: %s", alarm.music_uri)
        else:
            self._buzz_task = asyncio.create_task(_buzz_loop())

        # Volume ramp — real via HA, stub fallback without it
        if self._ha:
            self._volume_task = asyncio.create_task(
                self._ha.volume_ramp(self._audio_cfg)
            )
        else:
            self._volume_task = asyncio.create_task(
                _volume_ramp(self._audio_cfg)
            )

    # ------------------------------------------------------------------
    # Snooze / Dismiss
    # ------------------------------------------------------------------

    async def snooze(self) -> None:
        if self._state not in (AlarmState.FIRING, AlarmState.SNOOZED):
            return
        self._cancel_tasks()
        hw.stop_buzz()
        if self._ha:
            await self._ha.stop_music()
        self._snooze_until = datetime.now() + timedelta(minutes=self._snooze_minutes)
        self._state = AlarmState.SNOOZED
        log.info("Snoozed until %s", self._snooze_until.strftime("%H:%M"))
        await self._manager.broadcast({"type": "alarm_snoozed", "until": self._snooze_until.strftime("%H:%M")})
        self._publish_ha_state()

    async def dismiss(self) -> None:
        if self._state == AlarmState.IDLE:
            return
        self._cancel_tasks()
        hw.stop_buzz()
        if self._ha:
            await self._ha.stop_music()
        leds.clear(self._sunrise_cfg.get("num_leds", 6))
        self._state = AlarmState.IDLE
        self._active = None
        self._snooze_until = None
        log.info("Alarm dismissed")
        await self._manager.broadcast({"type": "alarm_dismissed"})
        self._publish_ha_state()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _cancel_tasks(self) -> None:
        for task in (self._volume_task, self._buzz_task, self._sunrise_task):
            if task and not task.done():
                task.cancel()
        self._volume_task = None
        self._buzz_task = None
        self._sunrise_task = None

    def _publish_ha_state(self) -> None:
        if not self._ha:
            return
        next_alarm = self.next_alarm()
        next_label = next_alarm.label if next_alarm else "No alarm set"
        is_firing = self._state == AlarmState.FIRING
        weekday_on = any(
            a.enabled for a in self._alarms
            if any(d in {"mon", "tue", "wed", "thu", "fri"} for d in a.days)
        )
        weekend_on = any(
            a.enabled for a in self._alarms
            if any(d in {"sat", "sun"} for d in a.days)
        )
        self._ha.publish_alarm_state(next_label, is_firing, weekday_on, weekend_on)

    def state_message(self) -> dict:
        next_alarm = self.next_alarm()
        return {
            "type": "alarm_state",
            "state": self._state.name,
            "next_alarm_label": next_alarm.label if next_alarm else None,
            "next_alarm_time": next_alarm.time if next_alarm else None,
        }

    def next_alarm(self) -> Optional[Alarm]:
        now = datetime.now()
        best: Optional[tuple[timedelta, Alarm]] = None
        for alarm in self._alarms:
            if not alarm.enabled:
                continue
            h, m = map(int, alarm.time.split(":"))
            for days_ahead in range(7):
                candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
                candidate = candidate + timedelta(days=days_ahead)
                if candidate <= now:
                    continue
                if candidate.weekday() in [DAY_MAP[d] for d in alarm.days if d in DAY_MAP]:
                    delta = candidate - now
                    if best is None or delta < best[0]:
                        best = (delta, alarm)
                    break
        return best[1] if best else None


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------

async def _trigger_music(uri: str, audio_cfg: dict) -> None:
    """Stub — Phase 5 replaces this with a real HA service call."""
    log.info("[STUB] Would trigger Music Assistant: %s", uri)


async def _buzz_loop() -> None:
    """Beep the buzzer repeatedly until the task is cancelled."""
    try:
        while True:
            hw.buzz(880, 500)
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        hw.stop_buzz()


async def _volume_ramp(audio_cfg: dict) -> None:
    """Stub volume ramp — logs progress; Phase 5 sends real HA volume commands."""
    start = audio_cfg.get("volume_start", 20)
    maximum = audio_cfg.get("volume_max", 80)
    ramp_seconds = audio_cfg.get("volume_ramp_seconds", 120)
    steps = 10
    step_size = (maximum - start) / steps
    step_delay = ramp_seconds / steps
    volume = start
    try:
        for _ in range(steps):
            log.debug("[STUB] Volume -> %d%%", round(volume))
            volume += step_size
            await asyncio.sleep(step_delay)
    except asyncio.CancelledError:
        pass
