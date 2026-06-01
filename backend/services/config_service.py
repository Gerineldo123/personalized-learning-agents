import json
import os
from dotenv import load_dotenv
from pydantic import BaseModel

ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
if os.path.exists(ENV_FILE):
    load_dotenv(ENV_FILE)

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "api_config.json")


class ApiConfig(BaseModel):
    base_url: str = ""
    api_key: str = ""
    api_secret: str = ""
    model: str = ""


def _load_configs() -> dict[str, ApiConfig]:
    configs = {
        "main": ApiConfig(
            base_url=os.getenv("SPARK_BASE_URL", ""),
            api_key=os.getenv("SPARK_API_KEY", ""),
            api_secret=os.getenv("SPARK_API_SECRET", ""),
            model=os.getenv("SPARK_MODEL", ""),
        ),
        "video": ApiConfig(
            base_url=os.getenv("VIDEO_BASE_URL", ""),
            api_key=os.getenv("VIDEO_API_KEY", ""),
            api_secret=os.getenv("VIDEO_API_SECRET", ""),
        ),
    }

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key in ("main", "video"):
                json_cfg = data.get(key, {})
                cfg = configs[key]
                if json_cfg.get("base_url"):
                    cfg.base_url = json_cfg["base_url"]
                if json_cfg.get("api_key"):
                    cfg.api_key = json_cfg["api_key"]
                if json_cfg.get("api_secret"):
                    cfg.api_secret = json_cfg["api_secret"]
                if json_cfg.get("model"):
                    cfg.model = json_cfg["model"]
        except Exception:
            pass

    return configs


def _save_configs(configs: dict[str, ApiConfig]):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "main": configs["main"].model_dump(),
            "video": configs["video"].model_dump(),
        }, f, ensure_ascii=False, indent=2)


_configs = _load_configs()


def get_main_config() -> ApiConfig:
    return _configs["main"]


def set_main_config(cfg: ApiConfig):
    fields = cfg.model_fields_set
    if "model" in fields:
        _configs["main"].model = cfg.model
    if "base_url" in fields:
        _configs["main"].base_url = cfg.base_url
    if "api_key" in fields:
        _configs["main"].api_key = cfg.api_key
    if "api_secret" in fields:
        _configs["main"].api_secret = cfg.api_secret
    _save_configs(_configs)


def get_video_config() -> ApiConfig:
    return _configs["video"]


def set_video_config(cfg: ApiConfig):
    fields = cfg.model_fields_set
    if "model" in fields:
        _configs["video"].model = cfg.model
    if "base_url" in fields:
        _configs["video"].base_url = cfg.base_url
    if "api_key" in fields:
        _configs["video"].api_key = cfg.api_key
    if "api_secret" in fields:
        _configs["video"].api_secret = cfg.api_secret
    _save_configs(_configs)


def build_client_kwargs(config_key: str = "main") -> dict:
    cfg = _configs.get(config_key, _configs["main"])
    key = cfg.api_key
    if cfg.api_secret and ":" not in key:
        key = f"{key}:{cfg.api_secret}"
    return {"api_key": key, "base_url": cfg.base_url}


def get_model(config_key: str = "main") -> str:
    cfg = _configs.get(config_key, _configs["main"])
    return cfg.model


def is_configured(config_key: str = "main") -> bool:
    cfg = _configs.get(config_key, _configs["main"])
    return bool(cfg.api_key and cfg.base_url)
