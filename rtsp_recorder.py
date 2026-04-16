import os
import subprocess
from datetime import datetime
from threading import Timer

class Recorder:
    def __init__(self, name, rtsp_url, output_path, record_interval=10):
        if output_path is None:
            raise ValueError("output_path variable is not set")
        self.output_path = output_path
        self.record_interval = record_interval
        self.recording_process = None
        self.name = name
        self.rtsp_url = rtsp_url
        self.is_recording = False
        self.timer = None

    def record(self):
        if self.is_recording:
            print("already recording")
            if self.timer:
                self.timer.cancel()
            self.timer = Timer(self.record_interval, self.stop_record)
            self.timer.start()
            return
        print("[INFO] starting recording")
        self.is_recording = True
        self.is_recording = True
        self.ffmpeg_record()
        self.timer = Timer(self.record_interval, self.stop_record)
        self.timer.start()

    def ffmpeg_record(self):
        now = datetime.now()
        output_file = os.path.join(
            self.output_path,
            now.strftime("%Y-%m-%d"),
            self.name,
            now.strftime("%H-%M-%S") + ".mp4"
        )
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        command = [
            "ffmpeg",
            "-rtsp_transport", "tcp",
            "-i", self.rtsp_url,
            "-c", "copy",
            "-c:a", "aac",
            output_file,
        ]
        self.recording_process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            # stdout=subprocess.DEVNULL,
            # stderr=subprocess.DEVNULL,
        )
        print("[INFO] started ffmpeg recording, output file: {}".format(output_file))

    def stop_record(self):
        if self.timer:
            self.timer.cancel()
        if self.recording_process:
            try:
                self.recording_process.stdin.write(b"q")
                self.recording_process.stdin.flush()
                self.recording_process.wait(timeout=10)
            except Exception:
                self.recording_process.kill()
            finally:
                print("[INFO] stopped recording")
                self.recording_process = None
                self.is_recording = False
