import os
import shutil
import tempfile

import yaml
from dotenv import load_dotenv

ALARMS_PATH = "config/alarms.yaml"
ALARMS_EXAMPLE_PATH = "config/alarms.yaml.example"

load_dotenv()  # loads .env into os.environ (no-op if file absent)


def load_config(path: str = "config/settings.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # Overlay secrets from environment — env vars win over YAML values.
    ha = cfg.setdefault("home_assistant", {})

    ha_token = os.environ.get("HA_TOKEN", "").strip()
    if ha_token:
        ha["token"] = ha_token

    mqtt_user = os.environ.get("MQTT_USER", "").strip()
    mqtt_pass = os.environ.get("MQTT_PASS", "").strip()
    if mqtt_user:
        ha["mqtt_user"] = mqtt_user
    if mqtt_pass:
        ha["mqtt_pass"] = mqtt_pass

    ha_dashboard_url = os.environ.get("HA_DASHBOARD_URL", "").strip()
    if ha_dashboard_url:
        ha["dashboard_url"] = ha_dashboard_url

    return cfg


def load_alarms(path: str = ALARMS_PATH) -> list:
    if not os.path.exists(path):
        shutil.copy(ALARMS_EXAMPLE_PATH, path)
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("alarms", [])


def save_alarms(alarms: list, path: str = ALARMS_PATH) -> None:
    """Write alarms atomically to alarms.yaml."""
    dir_name = os.path.dirname(os.path.abspath(path))
    with tempfile.NamedTemporaryFile(
        "w", dir=dir_name, delete=False, suffix=".tmp", encoding="utf-8"
    ) as tmp:
        yaml.dump({"alarms": alarms}, tmp, default_flow_style=False, allow_unicode=True)
        tmp_path = tmp.name
    os.replace(tmp_path, path)


# home_assistant keys that load_config() overlays from .env — these must never
# round-trip back onto disk, only ever live in the environment.
_HA_ENV_SECRET_KEYS = ("token", "mqtt_user", "mqtt_pass")


def save_config(data: dict, path: str = "config/settings.yaml") -> None:
    """Write config atomically to avoid corruption on a partial write.

    `data` is the live in-memory config, which has env secrets overlaid onto
    `home_assistant` (see load_config) and `alarms` merged in from alarms.yaml
    (see load_alarms/save_alarms) for runtime convenience. Neither should be
    persisted here — secrets must stay in .env only, and alarms already have
    their own on-disk file — so both are stripped before writing.
    """
    to_write = {k: v for k, v in data.items() if k != "alarms"}
    ha = to_write.get("home_assistant")
    if ha:
        to_write["home_assistant"] = {k: v for k, v in ha.items() if k not in _HA_ENV_SECRET_KEYS}

    dir_name = os.path.dirname(os.path.abspath(path))
    with tempfile.NamedTemporaryFile(
        "w", dir=dir_name, delete=False, suffix=".tmp", encoding="utf-8"
    ) as tmp:
        yaml.dump(to_write, tmp, default_flow_style=False, allow_unicode=True)
        tmp_path = tmp.name
    os.replace(tmp_path, path)
