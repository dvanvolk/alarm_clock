import os
import tempfile

import yaml
from dotenv import load_dotenv

load_dotenv()  # loads .env into os.environ (no-op if file absent)


def load_config(path: str = "config/settings.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # Overlay secrets from environment — env vars win over YAML values.
    ha_token = os.environ.get("HA_TOKEN", "").strip()
    if ha_token:
        cfg.setdefault("home_assistant", {})["token"] = ha_token

    return cfg


def save_config(data: dict, path: str = "config/settings.yaml") -> None:
    """Write config atomically to avoid corruption on a partial write."""
    dir_name = os.path.dirname(os.path.abspath(path))
    with tempfile.NamedTemporaryFile(
        "w", dir=dir_name, delete=False, suffix=".tmp", encoding="utf-8"
    ) as tmp:
        yaml.dump(data, tmp, default_flow_style=False, allow_unicode=True)
        tmp_path = tmp.name
    os.replace(tmp_path, path)
