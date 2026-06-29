import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from backend.config import load_config, save_config
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


async def hardware_poll_loop():
    """Poll light sensor every 60 s and push brightness_update."""
    display_cfg = config.get("display", {})
    lux_low = display_cfg.get("dim_low_lux", 20)
    lux_high = display_cfg.get("dim_high_lux", 300)
    br_min = display_cfg.get("dim_min_brightness", 10)
    br_max = display_cfg.get("dim_max_brightness", 100)
    auto_dim = display_cfg.get("auto_dim", True)

    while True:
        if auto_dim:
            lux = hw.get_lux()
            pct = br_min + (br_max - br_min) * min(max((lux - lux_low) / (lux_high - lux_low), 0), 1)
            await manager.broadcast({"type": "brightness_update", "brightness": round(pct)})
        await asyncio.sleep(60)


async def alarm_check_loop():
    """Check every 30 s whether an alarm should fire."""
    while True:
        if scheduler:
            await scheduler.tick(datetime.now())
        await asyncio.sleep(30)


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global config, scheduler, ha_client
    config = load_config()
    hw.setup_hardware(config)
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
        save_config(config)
        scheduler.reload(config)
        log.info("HA switch: %s alarms → %s", switch_name, "enabled" if enabled else "disabled")

    ha_client.set_switch_callback(on_alarm_switch)
    scheduler.set_ha_client(ha_client)

    asyncio.create_task(tick_loop())
    asyncio.create_task(hardware_poll_loop())
    asyncio.create_task(alarm_check_loop())
    await ha_client.start()

    log.info("Alarm clock backend started")
    yield
    hw.cleanup()
    log.info("Alarm clock backend stopped")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(lifespan=lifespan)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    clock_cfg = config.get("clock", {})
    await ws.send_text(json.dumps({
        "type": "settings_update",
        "seconds_scale": clock_cfg.get("seconds_scale", 0.55),
        "font": clock_cfg.get("font", "Orbitron"),
        "accent_color": clock_cfg.get("accent_color", "#e8a020"),
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
        config.update(new_cfg)
        save_config(config)
        scheduler.reload(config)
        log.info("Settings saved")

    elif mtype == "switch_view":
        # Broadcast so all clients switch (e.g., multiple browser tabs)
        await manager.broadcast({"type": "switch_view", "view": msg.get("view")})

    elif mtype == "ota_trigger":
        from backend.updater import run_ota
        asyncio.create_task(run_ota(manager))

    else:
        log.warning("Unknown message type: %s", mtype)


# Serve frontend — must come last so /ws is registered first
app.mount("/", StaticFiles(directory="frontend", html=True), name="static")
