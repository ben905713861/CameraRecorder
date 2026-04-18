import threading
import time
import traceback

from camera_urls import get_streams
from config import load_config
from rtsp_motion_detect import MotionDetector
from rtsp_recorder import Recorder


def motion_detect_worker(config, camera_config):
    while True:
        try:
            rtsp_streams = get_streams(**camera_config.model_dump())
            main_stream_url = rtsp_streams[0]
            sub_stream_url = rtsp_streams[1]

            recorder = Recorder(camera_config.name, main_stream_url, config.output_path)

            def record():
                recorder.record()

            motion_detector = MotionDetector(**camera_config.record_config.model_dump(),
                          name=camera_config.name,
                          rtsp_url=sub_stream_url,
                          callback=record)
            motion_detector.detect()

        except Exception:
            traceback.print_exc()
            print(f"camera [{camera_config.name}] connection error, retrying in 5 seconds...")
            time.sleep(5)

def main():
    config = load_config()
    for camera_config in config.camera_list:
        if not camera_config.enabled:
            print("camera {} is disabled, skipping...".format(camera_config.name))
            continue
        t = threading.Thread(target=motion_detect_worker, args=(config, camera_config), daemon=False)
        t.start()

if __name__ == '__main__':
    main()
