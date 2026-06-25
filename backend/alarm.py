import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Optional

import backend.hardware as hw

log = logging.getLogger(__name__)

DAY_MAP = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3,
    "fri": 4, "sat": 5, "sun": 6,
}


class AlarmState(Enum):
    IDLE = auto()
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
        self._alarms: list[Alarm] = []
        self._state = AlarmState.IDLE
        self._active: Optional[Alarm] = None
        self._snooze_until: Optional[datetime] = None
        self._volume_task: Optional[asyncio.Task] = None
        self._buzz_task: Optional[asyncio.Task] = None
        self._snooze_minutes = 9
        self._audio_cfg: dict = {}
        self.reload(config)

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def reload(self, config: dict) -> None:
        self._alarms = _parse_alarms(config)
        self._snooze_minutes = config.get("snooze", {}).get("duration_minutes", 9)
        self._audio_cfg = config.get("audio", {})

    # ------------------------------------------------------------------
    # Tick — called every 30 s from main
    # ------------------------------------------------------------------

    async def tick(self, now: datetime) -> None:
        if self._state == AlarmState.IDLE:
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

    async def _fire(self, alarm: Alarm) -> None:
        self._state = AlarmState.FIRING
        self._active = alarm
        log.info("Alarm firing: %s at %s", alarm.label, alarm.time)

        await self._manager.broadcast({
            "type": "alarm_firing",
            "label": alarm.label,
            "time": alarm.time,
        })

        # Start sound
        if alarm.sound == "music_assistant":
            await _trigger_music(alarm.music_uri, self._audio_cfg)
        else:
            self._buzz_task = asyncio.create_task(_buzz_loop())

        # Volume ramp (stub on Windows; real audio in Phase 5)
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
        self._snooze_until = datetime.now() + timedelta(minutes=self._snooze_minutes)
        self._state = AlarmState.SNOOZED
        log.info("Snoozed until %s", self._snooze_until.strftime("%H:%M"))
        await self._manager.broadcast({"type": "alarm_snoozed", "until": self._snooze_until.strftime("%H:%M")})

    async def dismiss(self) -> None:
        if self._state == AlarmState.IDLE:
            return
        self._cancel_tasks()
        hw.stop_buzz()
        self._state = AlarmState.IDLE
        self._active = None
        self._snooze_until = None
        log.info("Alarm dismissed")
        await self._manager.broadcast({"type": "alarm_dismissed"})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _cancel_tasks(self) -> None:
        for task in (self._volume_task, self._buzz_task):
            if task and not task.done():
                task.cancel()
        self._volume_task = None
        self._buzz_task = None

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
