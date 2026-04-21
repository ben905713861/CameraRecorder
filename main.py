import threading
import time

from camera_urls import get_streams
from config import load_config
from rtsp_motion_detect import MotionDetector
from rtsp_recorder import Recorder


def motion_detect_worker(config, camera_config):
    recorder = None
    while True:
        try:
            rtsp_streams = get_streams(**camera_config.model_dump())
            if not rtsp_streams:
                raise ConnectionError(f"camera [{camera_config.name}] returned no streams")
            main_stream_url = rtsp_streams[0]
            sub_stream_url = rtsp_streams[1] if len(rtsp_streams) > 1 else main_stream_url

            recorder = Recorder(
                camera_config.name,
                main_stream_url,
                config.output_path,
                record_interval=config.record_interval,
            )

            def record():
                recorder.record()

            motion_detector = MotionDetector(**camera_config.record_config.model_dump(),
                          name=camera_config.name,
                          rtsp_url=sub_stream_url,
                          callback=record)
            motion_detector.detect()
        except ConnectionError as e:
            print(f"camera [{camera_config.name}] connection lost, retrying in 60 seconds...", e)
            try:
                time.sleep(60)
            except KeyboardInterrupt:
                print("KeyboardInterrupt, exiting...")
                if recorder:
                    recorder.cleanup()
                break
        finally:
            if recorder:
                recorder.cleanup()
                recorder = None

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
