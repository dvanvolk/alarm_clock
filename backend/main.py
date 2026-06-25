import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from backend.config import load_config, save_config
from backend.alarm import AlarmScheduler
import backend.hardware as hw

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App state shared across the request lifecycle
# ---------------------------------------------------------------------------
config: dict = {}
scheduler: AlarmScheduler | None = None


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
    global config, scheduler
    config = load_config()
    hw.setup_hardware(config)

    scheduler = AlarmScheduler(config, manager)

    def snooze_button_pressed():
        asyncio.create_task(scheduler.snooze())

    hw.setup_snooze_button(snooze_button_pressed)

    asyncio.create_task(tick_loop())
    asyncio.create_task(hardware_poll_loop())
    asyncio.create_task(alarm_check_loop())

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
    # Send current alarm state immediately on connect
    if scheduler:
        await ws.send_text(json.dumps(scheduler.state_message()))
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
