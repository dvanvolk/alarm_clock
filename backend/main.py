import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from backend.config import load_config, save_config, load_alarms, save_alarms
from backend.alarm import AlarmScheduler
from backend.ha_client import HAClient
import backend.hardware as hw
import backend.leds as leds

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App state shared across the request lifecycle
# ---------------------------------------------------------------------------
config: dict = {}
scheduler: AlarmScheduler | None = None
ha_client: HAClient | None = None

# Last known hardware reading — gives hardware_poll_loop hysteresis memory across
# ticks, and lets newly-connected clients get an immediate day/night picture instead
# of waiting up to 30s for the next poll.
_hw_state: dict = {"brightness": 100, "is_night": False}


class ConnectionManager:
    def __init__(self):
        self._clients: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.append(ws)
        log.info("Client connected (%d total)", len(self._clients))

    def disconnect(self, ws: WebSocket):
        self._clients.remove(ws)
        log.info("Client disconnected (%d total)", len(self._clients))

    async def broadcast(self, message: dict):
        data = json.dumps(message)
        dead = []
        for ws in self._clients:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.remove(ws)


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------

async def tick_loop():
    """Push a time_update to all clients every second."""
    while True:
        now = datetime.now()
        fmt = config.get("clock", {}).get("display_format", "12hr")
        show_sec = config.get("clock", {}).get("show_seconds", True)

        hour = now.strftime("%I").lstrip("0") or "12"  # cross-platform no-leading-zero hour
        if fmt == "12hr":
            if show_sec:
                time_str = f"{hour}:{now.strftime('%M:%S %p')}"
            else:
                time_str = f"{hour}:{now.strftime('%M %p')}"
        else:
            time_str = now.strftime("%H:%M:%S" if show_sec else "%H:%M")

        day_num = str(now.day)  # no leading zero, cross-platform
        await manager.broadcast({
            "type": "time_update",
            "time": time_str,
            "date": now.strftime(f"%B {day_num}, %Y"),
            "day": now.strftime("%A"),
        })
        await asyncio.sleep(1)


def _compute_hw_state(lux: float, display_cfg: dict, previous_is_night: bool) -> tuple[int, bool]:
    """Compute brightness % and day/night state from a lux reading.

    is_night uses dim_low_lux/dim_high_lux as a hysteresis band (the same
    thresholds that drive brightness dimming): it flips on once brightness has
    bottomed out and flips off once brightness is back at its ceiling, holding
    the previous value in between so it doesn't flicker at the boundary.
    """
    lux_low = display_cfg.get("dim_low_lux", 20)
    lux_high = display_cfg.get("dim_high_lux", 300)
    br_min = display_cfg.get("dim_min_brightness", 10)
    br_max = display_cfg.get("dim_max_brightness", 100)
    auto_dim = display_cfg.get("auto_dim", True)

    if lux <= lux_low:
        is_night = True
    elif lux >= lux_high:
        is_night = False
    else:
        is_night = previous_is_night

    if auto_dim:
        pct = br_min + (br_max - br_min) * min(max((lux - lux_low) / (lux_high - lux_low), 0), 1)
    else:
        pct = br_max

    return round(pct), is_night


async def hardware_poll_loop():
    """Poll light sensor every 30 s and push brightness_update (brightness + is_night)."""
    display_cfg = config.get("display", {})

    while True:
        lux = hw.get_lux()
        pct, is_night = _compute_hw_state(lux, display_cfg, _hw_state["is_night"])
        _hw_state["brightness"], _hw_state["is_night"] = pct, is_night
        log.info("BH1750: %.1f lux → brightness %d%% (night=%s)", lux, pct, is_night)
        await manager.broadcast({"type": "brightness_update", "brightness": pct, "is_night": is_night})
        await asyncio.sleep(30)


async def alarm_check_loop():
    """Check every 30 s whether an alarm should fire."""
    while True:
        if scheduler:
            await scheduler.tick(datetime.now())
        await asyncio.sleep(30)


async def dht22_poll_loop():
    """Read DHT22 and publish to HA MQTT on each interval."""
    dht_cfg = config.get("dht22", {})
    interval = int(dht_cfg.get("poll_interval_seconds", 60))
    unit = dht_cfg.get("temperature_unit", "F")
    while True:
        temp, humidity = hw.read_dht22(unit)
        if temp is not None and humidity is not None:
            log.info("DHT22: %.1f°%s  %.1f%%RH", temp, unit, humidity)
            if ha_client:
                ha_client.publish_dht22(temp, humidity)
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global config, scheduler, ha_client
    config = load_config()
    config["alarms"] = load_alarms()
    hw.setup_hardware(config)
    _hw_state["brightness"], _hw_state["is_night"] = _compute_hw_state(
        hw.get_lux(), config.get("display", {}), previous_is_night=False
    )
    sunrise_cfg = config.get("sunrise", {})
    leds.setup_leds(
        sunrise_cfg.get("num_leds", 6),
        sunrise_cfg.get("max_brightness", 255),
    )

    scheduler = AlarmScheduler(config, manager)

    def snooze_button_pressed():
        asyncio.create_task(scheduler.snooze())

    hw.setup_snooze_button(snooze_button_pressed)

    ha_client = HAClient(config, manager)

    async def on_alarm_switch(switch_name: str, enabled: bool) -> None:
        for alarm in config.get("alarms", []):
            days = set(alarm.get("days", []))
            if switch_name == "weekday" and days & {"mon", "tue", "wed", "thu", "fri"}:
                alarm["enabled"] = enabled
            elif switch_name == "weekend" and days & {"sat", "sun"}:
                alarm["enabled"] = enabled
        save_alarms(config["alarms"])
        scheduler.reload(config)
        log.info("HA switch: %s alarms → %s", switch_name, "enabled" if enabled else "disabled")

    ha_client.set_switch_callback(on_alarm_switch)
    scheduler.set_ha_client(ha_client)

    asyncio.create_task(tick_loop())
    asyncio.create_task(hardware_poll_loop())
    asyncio.create_task(alarm_check_loop())
    await ha_client.start()

    dht_cfg = config.get("dht22", {})
    if dht_cfg.get("enabled"):
        hw.setup_dht22(int(dht_cfg.get("gpio_pin", 4)))
        asyncio.create_task(dht22_poll_loop())

    log.info("Alarm clock backend started")
    yield
    hw.cleanup()
    log.info("Alarm clock backend stopped")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(lifespan=lifespan)


def _settings_update_message(cfg: dict) -> dict:
    clock_cfg = cfg.get("clock", {})
    return {
        "type": "settings_update",
        "seconds_scale": clock_cfg.get("seconds_scale", 0.55),
        "font": clock_cfg.get("font", "Orbitron"),
        "size_scale": clock_cfg.get("size_scale", 1.0),
        "color_day": clock_cfg.get("color_day", "#e8a020"),
        "color_night": clock_cfg.get("color_night", "#c0392b"),
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    await ws.send_text(json.dumps(_settings_update_message(config)))
    await ws.send_text(json.dumps({
        "type": "brightness_update",
        "brightness": _hw_state["brightness"],
        "is_night": _hw_state["is_night"],
    }))
    await ws.send_text(json.dumps({
        "type": "config_update",
        "alarms": config.get("alarms", []),
        "buzzer": config.get("buzzer", {}),
        "dashboard_url": config.get("home_assistant", {}).get("dashboard_url", ""),
    }))
    if scheduler:
        await ws.send_text(json.dumps(scheduler.state_message()))
    if ha_client and ha_client.last_weather:
        await ws.send_text(json.dumps(ha_client.last_weather))
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            await handle_message(msg, ws)
    except WebSocketDisconnect:
        manager.disconnect(ws)


async def handle_message(msg: dict, ws: WebSocket):
    global config
    mtype = msg.get("type")

    if mtype == "snooze" and scheduler:
        await scheduler.snooze()

    elif mtype == "dismiss" and scheduler:
        await scheduler.dismiss()

    elif mtype == "settings_save":
        new_cfg = msg.get("settings", {})
        dashboard_url = new_cfg.pop("dashboard_url", None)
        clock_updates = new_cfg.pop("clock", None)
        config_dirty = False

        if dashboard_url is not None:
            config.setdefault("home_assistant", {})["dashboard_url"] = dashboard_url
            config_dirty = True

        if clock_updates:
            clock_cfg = config.setdefault("clock", {})
            if "size_scale" in clock_updates:
                try:
                    clock_cfg["size_scale"] = max(0.5, min(2.0, float(clock_updates["size_scale"])))
                except (TypeError, ValueError):
                    pass
            for key in ("color_day", "color_night"):
                if key in clock_updates:
                    clock_cfg[key] = clock_updates[key]
            config_dirty = True

        if config_dirty:
            save_config(config)

        if "alarms" in new_cfg:
            config["alarms"] = new_cfg["alarms"]
            save_alarms(config["alarms"])

        scheduler.reload(config)
        await manager.broadcast({
            "type": "config_update",
            "alarms": config.get("alarms", []),
            "buzzer": config.get("buzzer", {}),
            "dashboard_url": config.get("home_assistant", {}).get("dashboard_url", ""),
        })
        if clock_updates:
            await manager.broadcast(_settings_update_message(config))
            # Kiosk tabs stay open for weeks and never re-navigate, so a live
            # settings_update is only picked up by JS that already knows how to
            # read it. Force a reload too so stale/older clients (or anyone who
            # skipped a kiosk restart after a code update) stay in sync.
            await manager.broadcast({"type": "reload"})
        log.info("Settings saved")

    elif mtype == "switch_view":
        # Broadcast so all clients switch (e.g., multiple browser tabs)
        await manager.broadcast({"type": "switch_view", "view": msg.get("view")})

    elif mtype == "ota_trigger":
        from backend.updater import run_ota
        branch = config.get("ota", {}).get("git_branch", "main")
        asyncio.create_task(run_ota(manager, branch))

    else:
        log.warning("Unknown message type: %s", mtype)


# Serve frontend — must come last so /ws is registered first
app.mount("/", StaticFiles(directory="frontend", html=True), name="static")
