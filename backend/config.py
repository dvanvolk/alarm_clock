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


def save_config(data: dict, path: str = "config/settings.yaml") -> None:
    """Write config atomically to avoid corruption on a partial write."""
    dir_name = os.path.dirname(os.path.abspath(path))
    with tempfile.NamedTemporaryFile(
        "w", dir=dir_name, delete=False, suffix=".tmp", encoding="utf-8"
    ) as tmp:
        yaml.dump(data, tmp, default_flow_style=False, allow_unicode=True)
        tmp_path = tmp.name
    os.replace(tmp_path, path)
