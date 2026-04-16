import yaml
from pydantic import BaseModel

from camera_urls import get_streams

class RecordConfig(BaseModel):
    # enabled: bool = True
    pixel_threshold: int = 25  # 像素差异阈值
    motion_ratio_threshold: float = 0.02  # 像素变化比例阈值（2%）
    alert_interval: int = 5  # 告警间隔（秒）
    resize_width: int = 640  # 处理分辨率
    frame_skip: int = 5  # 跳帧间隔（每5帧检测一次）

class CameraConfig(BaseModel):
    name: str
    host: str
    port: int = 80
    username: str = "admin"
    password: str = ""
    enabled: bool = True
    record_config: RecordConfig
    rtsp_streams: list[str] = []

class BaseConfig(BaseModel):
    output_path: str
    record_interval: int
    camera_list: list[CameraConfig]

def load_config():
    with open("config.yml", "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    config = BaseConfig(**raw)

    for camera_config in config.camera_list:
        camera_config.rtsp_streams = get_streams(**camera_config.model_dump())
    return config

if __name__ == '__main__':
    res = load_config()
    print(res)
