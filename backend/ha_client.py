"""
ha_client.py — Home Assistant integration.

Three channels:
  MQTT (paho-mqtt)   — entity discovery, state publishing, switch commands
  HA REST (urllib)   — weather entity polling (no extra dependency)
  HA WebSocket       — service calls: Music Assistant, volume control
"""

import asyncio
import json
import logging
import urllib.error
import urllib.request
from typing import Callable, Optional

log = logging.getLogger(__name__)

try:
    import paho.mqtt.client as _mqtt_lib
    _MQTT_OK = True
except ImportError:
    _MQTT_OK = False
    log.warning("paho-mqtt not installed — MQTT Discovery disabled")

try:
    import websockets as _ws_lib
    _WS_OK = True
except ImportError:
    _WS_OK = False

_DISCOVERY_PREFIX = "homeassistant"
_NODE_ID = "alarm_clock"


class HAClient:
    """
    Integrates the alarm clock with Home Assistant.

    Call start() from the FastAPI lifespan after creating the instance.
    Fails gracefully if HA is unreachable or paho-mqtt is absent.
    """

    def __init__(self, config: dict, ws_manager):
        self._ha_cfg = config.get("home_assistant", {})
        self._weather_cfg = config.get("weather", {})
        self._ws_manager = ws_manager  # ConnectionManager from main.py

        # MQTT
        self._mqtt = None
        self._mqtt_connected = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._command_queue: asyncio.Queue = asyncio.Queue()

        # HA WebSocket
        self._ha_ws = None
        self._ha_ws_connected = False
        self._ha_ws_id = 0
        self._ha_ws_pending: dict[int, asyncio.Future] = {}
        self._ha_ws_lock = asyncio.Lock()

        # Callback invoked when HA sends a switch ON/OFF command
        # Signature: async (switch_name: str, enabled: bool) -> None
        self._switch_callback: Optional[Callable] = None

    def set_switch_callback(self, callback: Callable) -> None:
        self._switch_callback = callback

    async def start(self) -> None:
        """Launch integration tasks. No-ops if token is missing."""
        self._loop = asyncio.get_running_loop()
        token = self._ha_cfg.get("token", "")
        url = self._ha_cfg.get("url", "")

        if not token:
            log.info("HAClient: no HA token — integration disabled")
            return

        if _MQTT_OK and self._ha_cfg.get("mqtt_broker"):
            asyncio.create_task(self._mqtt_task())

        if self._weather_cfg.get("enabled") and url:
            asyncio.create_task(self._weather_poll_task())

        if _WS_OK and url:
            asyncio.create_task(self._ha_ws_task())

    # ------------------------------------------------------------------
    # MQTT
    # ------------------------------------------------------------------

    async def _mqtt_task(self) -> None:
        broker = self._ha_cfg.get("mqtt_broker", "homeassistant.local")
        port = int(self._ha_cfg.get("mqtt_port", 1883))
        loop = self._loop

        client = _mqtt_lib.Client(client_id=_NODE_ID)

        def on_connect(c, userdata, flags, rc):
            if rc != 0:
                log.warning("MQTT connect failed rc=%d", rc)
                return
            log.info("MQTT connected to %s:%d", broker, port)
            self._mqtt_connected = True
            self._mqtt = c
            c.subscribe(f"{_NODE_ID}/switch/+/command")
            asyncio.run_coroutine_threadsafe(self._publish_discovery(), loop)

        def on_message(c, userdata, msg):
            loop.call_soon_threadsafe(
                self._command_queue.put_nowait,
                (msg.topic, msg.payload.decode()),
            )

        def on_disconnect(c, userdata, rc):
            self._mqtt_connected = False
            log.warning("MQTT disconnected (rc=%d)", rc)

        client.on_connect = on_connect
        client.on_message = on_message
        client.on_disconnect = on_disconnect
        client.reconnect_delay_set(min_delay=5, max_delay=60)

        try:
            client.connect_async(broker, port)
            client.loop_start()
            while True:
                topic, payload = await self._command_queue.get()
                await self._handle_switch_command(topic, payload)
        except Exception as e:
            log.error("MQTT task fatal: %s", e)
        finally:
            client.loop_stop()

    async def _publish_discovery(self) -> None:
        if not (self._mqtt_connected and self._mqtt):
            return

        device = {
            "identifiers": [_NODE_ID],
            "name": "Alarm Clock",
            "model": "Pi Alarm Clock",
            "manufacturer": "DIY",
        }

        def pub(component: str, obj_id: str, payload: dict) -> None:
            topic = f"{_DISCOVERY_PREFIX}/{component}/{_NODE_ID}_{obj_id}/config"
            self._mqtt.publish(topic, json.dumps(payload), retain=True)
            log.debug("MQTT Discovery: %s", topic)

        pub("switch", "weekday", {
            "name": "Alarm Clock Weekday",
            "unique_id": f"{_NODE_ID}_switch_weekday",
            "state_topic": f"{_NODE_ID}/switch/weekday/state",
            "command_topic": f"{_NODE_ID}/switch/weekday/command",
            "payload_on": "ON", "payload_off": "OFF",
            "device": device,
        })
        pub("switch", "weekend", {
            "name": "Alarm Clock Weekend",
            "unique_id": f"{_NODE_ID}_switch_weekend",
            "state_topic": f"{_NODE_ID}/switch/weekend/state",
            "command_topic": f"{_NODE_ID}/switch/weekend/command",
            "payload_on": "ON", "payload_off": "OFF",
            "device": device,
        })
        pub("sensor", "next_alarm", {
            "name": "Alarm Clock Next",
            "unique_id": f"{_NODE_ID}_next_alarm",
            "state_topic": f"{_NODE_ID}/sensor/next_alarm/state",
            "device": device,
        })
        pub("binary_sensor", "firing", {
            "name": "Alarm Clock Firing",
            "unique_id": f"{_NODE_ID}_firing",
            "state_topic": f"{_NODE_ID}/binary_sensor/firing/state",
            "payload_on": "ON", "payload_off": "OFF",
            "device_class": "sound",
            "device": device,
        })

    async def _handle_switch_command(self, topic: str, payload: str) -> None:
        # topic: alarm_clock/switch/<name>/command
        parts = topic.split("/")
        if len(parts) < 3:
            return
        switch_name = parts[2]  # "weekday" or "weekend"
        enabled = payload.strip().upper() == "ON"
        log.info("MQTT switch: %s → %s", switch_name, "ON" if enabled else "OFF")
        if self._switch_callback:
            if asyncio.iscoroutinefunction(self._switch_callback):
                await self._switch_callback(switch_name, enabled)
            else:
                self._switch_callback(switch_name, enabled)

    def publish_alarm_state(
        self,
        next_label: str,
        is_firing: bool,
        weekday_enabled: bool,
        weekend_enabled: bool,
    ) -> None:
        """Publish current alarm state to MQTT topics (thread-safe)."""
        if not (self._mqtt_connected and self._mqtt):
            return
        self._mqtt.publish(
            f"{_NODE_ID}/sensor/next_alarm/state", next_label, retain=True
        )
        self._mqtt.publish(
            f"{_NODE_ID}/binary_sensor/firing/state",
            "ON" if is_firing else "OFF", retain=True,
        )
        self._mqtt.publish(
            f"{_NODE_ID}/switch/weekday/state",
            "ON" if weekday_enabled else "OFF", retain=True,
        )
        self._mqtt.publish(
            f"{_NODE_ID}/switch/weekend/state",
            "ON" if weekend_enabled else "OFF", retain=True,
        )

    # ------------------------------------------------------------------
    # Weather polling (HA REST via urllib — no aiohttp dependency)
    # ------------------------------------------------------------------

    async def _weather_poll_task(self) -> None:
        interval = int(self._weather_cfg.get("refresh_interval_seconds", 300))
        while True:
            try:
                update = await asyncio.to_thread(self._fetch_weather_sync)
                if update:
                    await self._ws_manager.broadcast(update)
            except Exception as e:
                log.warning("Weather poll error: %s", e)
            await asyncio.sleep(interval)

    def _fetch_weather_sync(self) -> Optional[dict]:
        """Blocking HA REST calls — runs in thread pool via asyncio.to_thread."""
        base_url = self._ha_cfg.get("url", "").rstrip("/")
        token = self._ha_cfg.get("token", "")
        temp_entity = self._weather_cfg.get("ha_temp_entity", "sensor.outdoor_temperature")
        cond_entity = self._weather_cfg.get("ha_condition_entity", "weather.home")

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        def get_state(entity_id: str) -> dict:
            req = urllib.request.Request(
                f"{base_url}/api/states/{entity_id}",
                headers=headers,
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())

        update: dict = {"type": "weather_update"}

        try:
            state = get_state(temp_entity)
            update["temp"] = state.get("state")
        except Exception as e:
            log.warning("HA: could not fetch %s: %s", temp_entity, e)

        try:
            state = get_state(cond_entity)
            update["condition"] = state.get("state")
            forecast = state.get("attributes", {}).get("forecast", [])
            if forecast:
                update["high"] = forecast[0].get("temperature")
                update["low"] = forecast[0].get("templow")
        except Exception as e:
            log.warning("HA: could not fetch %s: %s", cond_entity, e)

        return update if ("temp" in update or "condition" in update) else None

    # ------------------------------------------------------------------
    # HA WebSocket (service calls: Music Assistant, volume)
    # ------------------------------------------------------------------

    def _next_ws_id(self) -> int:
        self._ha_ws_id += 1
        return self._ha_ws_id

    async def _ha_ws_task(self) -> None:
        """Maintain a persistent HA WebSocket connection for service calls."""
        url = self._ha_cfg.get("url", "").rstrip("/")
        token = self._ha_cfg.get("token", "")
        ws_url = (
            url.replace("http://", "ws://").replace("https://", "wss://")
            + "/api/websocket"
        )

        while True:
            try:
                async with _ws_lib.connect(ws_url) as ws:
                    greeting = json.loads(await ws.recv())
                    if greeting.get("type") != "auth_required":
                        log.error("HA WS: unexpected greeting type: %s", greeting.get("type"))
                        await asyncio.sleep(30)
                        continue

                    await ws.send(json.dumps({"type": "auth", "access_token": token}))
                    auth_result = json.loads(await ws.recv())

                    if auth_result.get("type") != "auth_ok":
                        log.error("HA WS: auth failed — check long-lived token")
                        await asyncio.sleep(60)
                        continue

                    log.info("HA WebSocket authenticated (HA %s)", auth_result.get("ha_version", "?"))
                    self._ha_ws = ws
                    self._ha_ws_connected = True

                    async for raw in ws:
                        await self._dispatch_ws_msg(json.loads(raw))

            except Exception as e:
                log.warning("HA WS disconnected: %s — retrying in 30s", e)
            finally:
                self._ha_ws = None
                self._ha_ws_connected = False
                for fut in self._ha_ws_pending.values():
                    if not fut.done():
                        fut.cancel()
                self._ha_ws_pending.clear()

            await asyncio.sleep(30)

    async def _dispatch_ws_msg(self, msg: dict) -> None:
        if msg.get("type") == "result":
            msg_id = msg.get("id")
            if msg_id in self._ha_ws_pending:
                fut = self._ha_ws_pending.pop(msg_id)
                if not fut.done():
                    fut.set_result(msg)

    async def _ha_ws_call(self, payload: dict, wait_result: bool = False) -> Optional[dict]:
        """Send a command on the HA WebSocket. Fails silently if not connected."""
        if not (self._ha_ws_connected and self._ha_ws):
            log.debug("HA WS: not connected — skipping %s", payload.get("type"))
            return None

        msg_id = self._next_ws_id()
        payload = {"id": msg_id, **payload}

        fut: Optional[asyncio.Future] = None
        if wait_result:
            fut = asyncio.get_event_loop().create_future()
            self._ha_ws_pending[msg_id] = fut

        try:
            async with self._ha_ws_lock:
                await self._ha_ws.send(json.dumps(payload))
        except Exception as e:
            log.warning("HA WS send error: %s", e)
            self._ha_ws_pending.pop(msg_id, None)
            return None

        if fut:
            try:
                return await asyncio.wait_for(fut, timeout=10.0)
            except asyncio.TimeoutError:
                log.warning("HA WS call timed out (id=%d)", msg_id)
                self._ha_ws_pending.pop(msg_id, None)
        return None

    def _svc(self, domain: str, service: str, data: dict) -> dict:
        return {"type": "call_service", "domain": domain, "service": service, "service_data": data}

    # ------------------------------------------------------------------
    # Music / Volume (called from AlarmScheduler)
    # ------------------------------------------------------------------

    async def trigger_music(self, uri: str, audio_cfg: dict) -> None:
        """Set initial volume and start Music Assistant playback."""
        player = self._ha_cfg.get("music_player_entity", "")
        if not player:
            log.warning("HAClient: music_player_entity not set in config")
            return

        vol_start = audio_cfg.get("volume_start", 20) / 100.0
        await self._ha_ws_call(self._svc(
            "media_player", "volume_set",
            {"entity_id": player, "volume_level": round(vol_start, 2)},
        ))
        await self._ha_ws_call(self._svc(
            "music_assistant", "play_media",
            {"entity_id": player, "media_id": uri, "enqueue": "replace"},
        ))
        log.info("Music Assistant: playing %s on %s", uri, player)

    async def stop_music(self) -> None:
        """Stop media player playback."""
        player = self._ha_cfg.get("music_player_entity", "")
        if not player:
            return
        await self._ha_ws_call(self._svc(
            "media_player", "media_stop", {"entity_id": player}
        ))

    async def volume_ramp(self, audio_cfg: dict) -> None:
        """Gradually ramp media player volume from start % to max % over ramp_seconds."""
        player = self._ha_cfg.get("music_player_entity", "")
        if not player:
            return

        start = audio_cfg.get("volume_start", 20) / 100.0
        maximum = audio_cfg.get("volume_max", 80) / 100.0
        ramp_seconds = audio_cfg.get("volume_ramp_seconds", 120)
        steps = 10
        step_size = (maximum - start) / steps
        step_delay = ramp_seconds / steps
        volume = start

        try:
            for _ in range(steps):
                volume = min(volume + step_size, maximum)
                await self._ha_ws_call(self._svc(
                    "media_player", "volume_set",
                    {"entity_id": player, "volume_level": round(volume, 2)},
                ))
                log.debug("Volume → %.0f%%", volume * 100)
                await asyncio.sleep(step_delay)
        except asyncio.CancelledError:
            pass
