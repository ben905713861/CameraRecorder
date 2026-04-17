from config import load_config
from rtsp_recorder import Recorder
from rtsp_motion_detect import motion_detect

if __name__ == '__main__':
    config = load_config()
    for camera_config in config.camera_list:
        if not camera_config.enabled:
            print("camera {} is disabled, skipping...".format(camera_config.name))
            continue
        main_stream_url = camera_config.rtsp_streams[0]
        sub_stream_url = camera_config.rtsp_streams[1]
        recorder = Recorder(camera_config.name, main_stream_url, config.output_path)

        def record():
            recorder.record()

        motion_detect(**camera_config.record_config.model_dump(),
                      name=camera_config.name,
                      rtsp_url=sub_stream_url,
                      callback=record)
