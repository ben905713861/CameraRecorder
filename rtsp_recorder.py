import atexit
import os
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from threading import Timer

class Recorder:
    def __init__(self, name, rtsp_url, output_path, record_interval=10):
        if output_path is None:
            raise ValueError("output_path variable is not set")
        self.output_path = output_path
        self.record_interval = record_interval
        self.name = name
        self.rtsp_url = rtsp_url

        self.is_recording = False
        self.timer = None

        self.temp_dir = os.path.join(tempfile.gettempdir(), "camera", self.name)
        self.__clear_temp_folder()
        os.makedirs(self.temp_dir, exist_ok=True)

        self.background_record_process = None
        self.__background_record()
        threading.Thread(target=self.__clear_unused_temp_segments, daemon=True).start()

        # ensure cleanup on exit
        atexit.register(self.cleanup)

        self.event_time = None
        self.event_temp_list_path = None


    def __clear_unused_temp_segments(self):
        while True:
            time.sleep(60)
            file_paths = self.__get_temp_dir_filelist()
            for file_path in file_paths[50:]:
                os.remove(file_path)

    def __clear_temp_folder(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def __background_record(self):
        command = [
            "ffmpeg",
            "-rtsp_transport", "tcp",
            "-i", self.rtsp_url,
            "-c", "copy",
            "-f", "segment",
            "-segment_time", str(self.record_interval),
            # "-segment_wrap", "20",
            os.path.join(self.temp_dir, "%09d.ts")
        ]
        self.background_record_process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            # stderr=subprocess.PIPE,
        )

    def record(self):
        if self.is_recording:
            print("already recording")
            if self.timer:
                self.timer.cancel()
            self.timer = Timer(self.record_interval, self.__stop_record)
            self.timer.start()
            return
        print("[INFO] starting recording")
        self.is_recording = True
        self.event_time = datetime.now()
        self.event_temp_list_path = os.path.join(self.temp_dir, self.event_time.strftime("%Y%m%d_%H%M%S"))
        os.makedirs(self.event_temp_list_path, exist_ok=True)

        # self.ffmpeg_record()
        self.__record_1st_segment()

        self.timer = Timer(self.record_interval, self.__stop_record)
        self.timer.start()

    def __get_latest_segment(self) -> Path:
        file_paths = self.__get_temp_dir_filelist()
        if len(file_paths) <= 1:
            return file_paths[0]
        return file_paths[1]

    def __get_temp_dir_filelist(self) -> list[Path]:
        dir_path = Path(self.temp_dir)
        file_paths = [f
                      for f in dir_path.iterdir()
                      if f.is_file()
                      ]
        file_paths.sort(key=lambda f: f.name, reverse=True)
        return file_paths

    def __record_1st_segment(self):
        self.first_segment = self.__get_latest_segment()
        print("first_segment", self.first_segment)

    def __stop_record(self):
        if self.timer:
            self.timer.cancel()
        try:
            Timer(self.record_interval * 2, self.__compact_videos).start()
        finally:
            print("[INFO] stopped recording")
            self.is_recording = False

    def __compact_videos(self):
        last_segment = self.__get_latest_segment()
        print("last_segment", last_segment)
        first_index = int(self.first_segment.stem)
        last_index = int(last_segment.stem)
        file_list = []
        for i in range(first_index, last_index + 1):
            file_path = os.path.join(self.temp_dir, f"{i:09d}.ts")
            file_list.append(f"file '{file_path}'")
        print(file_list)
        if len(file_list) >= 3:
            file_list.pop()

        compact_file_list_path = os.path.join(self.event_temp_list_path, "list.txt")
        with open(compact_file_list_path, "w", encoding="utf-8") as f:
            file_content = "\n".join(file_list)
            f.write(file_content)
        event_output_temp_file = os.path.join(self.event_temp_list_path, "event.mp4")
        command = [
            "ffmpeg",
            "-f", "concat",
            "-safe", "0",
            "-i", compact_file_list_path,
            "-c", "copy",
            event_output_temp_file,
        ]
        result = subprocess.run(command, stderr=subprocess.PIPE)
        if result.returncode != 0:
            print(result.stderr.decode())
            return

        _date = self.event_time.strftime("%Y-%m-%d")
        _time = self.event_time.strftime("%H-%M-%S")
        new_output_file = os.path.join(self.output_path, _date, self.name, _time + ".mp4")
        os.makedirs(os.path.dirname(new_output_file), exist_ok=True)
        shutil.copy(event_output_temp_file, new_output_file)
        shutil.rmtree(self.event_temp_list_path)

    def __stop_background_record(self):
        if self.background_record_process:
            try:
                self.background_record_process.stdin.write(b"q")
                self.background_record_process.stdin.flush()
                self.background_record_process.wait(timeout=10)
            except Exception:
                self.background_record_process.kill()
            finally:
                print("[INFO] stopped background recording")

    def cleanup(self):
        print("[EXIT] cleaning up...")
        self.__stop_background_record()
        self.__clear_temp_folder()
