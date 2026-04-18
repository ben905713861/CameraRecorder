import os
import re

import yaml
from pydantic import BaseModel

PLACEHOLDER_PATTERN = re.compile(r"\$\{([A-Za-z_]\w*)(?::([^}]*))?}")

class RecordConfig(BaseModel):
    # enabled: bool = True
    pixel_threshold: int = 25  # 像素差异阈值
    motion_ratio_threshold: float = 0.02  # 像素变化比例阈值（2%）
    alert_interval: int = 5  # 告警间隔（秒）
    frame_skip: int = 5  # 跳帧间隔（每5帧检测一次）

class CameraConfig(BaseModel):
    name: str
    host: str
    port: int = 80
    username: str = "admin"
    password: str = ""
    enabled: bool = True
    record_config: RecordConfig

class BaseConfig(BaseModel):
    output_path: str
    record_interval: int
    camera_list: list[CameraConfig]

def _resolve_placeholders(value):
    if isinstance(value, dict):
        return {key: _resolve_placeholders(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_placeholders(item) for item in value]
    if isinstance(value, str):
        def _replace(match):
            env_name = match.group(1)
            default_value = match.group(2)
            env_value = os.getenv(env_name)
            if env_value is not None:
                return env_value
            if default_value is not None:
                return default_value
            raise ValueError(
                f"Missing environment variable '{env_name}' for placeholder '{match.group(0)}'"
            )

        return PLACEHOLDER_PATTERN.sub(_replace, value)
    return value

def load_config():
    with open("config.yml", "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    raw = _resolve_placeholders(raw)
    config = BaseConfig(**raw)
    return config
