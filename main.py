import threading
import time

from camera_urls import get_streams
from config import load_config
from rtsp_motion_detect import MotionDetector
from rtsp_event_recorder import EventRecorder
from rtsp_timing_recorder import TimingRecorder


def motion_detect_worker(config, camera_config, record_config):
    recorder = None
    while True:
        try:
            rtsp_streams = get_streams(**camera_config.model_dump())
            if not rtsp_streams:
                raise ConnectionError(f"camera [{camera_config.name}] returned no streams")
            main_stream_url = rtsp_streams[0]
            sub_stream_url = rtsp_streams[1] if len(rtsp_streams) > 1 else main_stream_url

            recorder = EventRecorder(
                camera_config.name,
                main_stream_url,
                config.output_path,
                config.record_interval,
                config.segment_retain_time,
            )

            def record():
                recorder.record()

            motion_detector = MotionDetector(rtsp_url=sub_stream_url,
                                             name=camera_config.name,
                                             pixel_threshold=record_config.pixel_threshold,
                                             motion_ratio_threshold=record_config.motion_ratio_threshold,
                                             alert_interval=record_config.alert_interval,
                                             frame_skip=record_config.frame_skip,
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

def timer_record_worker(config, camera_config, record_config):
    print("timer_record_worker starts successfully")
    rtsp_streams = get_streams(**camera_config.model_dump())
    if not rtsp_streams:
        raise ConnectionError(f"camera [{camera_config.name}] returned no streams")
    main_stream_url = rtsp_streams[0]
    TimingRecorder(name=camera_config.name,
                   rtsp_url=main_stream_url,
                   output_path=config.output_path,
                   time_ranges=record_config.scheduler).start()

def main():
    config = load_config()
    for camera_config in config.camera_list:
        if not camera_config.enabled:
            print("camera {} is disabled, skipping...".format(camera_config.name))
            continue
        threads = []
        for record_config in camera_config.record_configs:
            if record_config.type == "event":
                thread = threading.Thread(target=motion_detect_worker, args=(config, camera_config, record_config), daemon=False)
            elif record_config.type == "timing":
                thread = threading.Thread(target=timer_record_worker, args=(config, camera_config, record_config), daemon=False)
            else:
                raise ValueError(f"unsupported record type [{record_config.type}] for camera [{camera_config.name}]")
            thread.start()
            threads.append(thread)
        # for thread in threads:
        #     thread.join()

if __name__ == '__main__':
    main()
