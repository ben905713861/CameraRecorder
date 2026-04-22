import atexit
import os
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from threading import Timer


class Recorder:
    def __init__(self, camera_name, rtsp_url, output_path, record_interval=10):
        if output_path is None:
            raise ValueError("output_path variable is not set")
        self.output_path = output_path
        self.record_interval = record_interval
        self.camera_name = camera_name
        self.rtsp_url = rtsp_url

        self.first_segment = None
        self.is_recording = False
        self.timer = None

        self.exit_event = threading.Event()
        self.event_time = None
        self.lock = threading.Lock()

        self.temp_dir = os.path.join(tempfile.gettempdir(), "camera", self.camera_name)
        self.__clear_temp_folder()
        os.makedirs(self.temp_dir, exist_ok=True)

        self.background_record_process = self.__background_record()
        self.clear_thread = self.__clear_unused_temp_segments_process()

        # ensure cleanup on exit
        atexit.register(self.cleanup)

    def __clear_unused_temp_segments_process(self):
        clear_thread = threading.Thread(target=self.__clear_unused_temp_segments, daemon=True)
        clear_thread.start()
        return clear_thread

    def __clear_unused_temp_segments(self):
        while not self.exit_event.wait(60):
            try:
                if not os.path.exists(self.temp_dir):
                    os.makedirs(self.temp_dir, exist_ok=True)
                file_paths = self.__get_temp_dir_filelist()
                print("__clear_unused_temp_segments, found {} files".format(len(file_paths)))
                for file_path in file_paths[50:]:
                    if os.path.exists(file_path):
                        os.remove(file_path)
            except (FileNotFoundError, OSError):
                pass

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
        return subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def record(self):
        with self.lock:
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

            # self.ffmpeg_record()
            self.first_segment = self.__get_latest_segment()
            print("first_segment", self.first_segment)
            if not self.first_segment:
                print("no segment found, skipping recording...")
                self.is_recording = False
                return

            self.timer = Timer(self.record_interval, self.__stop_record)
            self.timer.start()

    def __get_latest_segment(self) -> Path | None:
        file_paths = self.__get_temp_dir_filelist()
        if len(file_paths) == 0:
            return None
        if len(file_paths) == 1:
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

    def __stop_record(self):
        with (self.lock):
            if self.timer:
                self.timer.cancel()
            try:
                # prepare the segment list for ffmpeg concat
                last_segment = self.__get_latest_segment()
                if not last_segment or not self.first_segment:
                    print("no segment found, skipping compacting...")
                    return
                print("last_segment", last_segment)
                first_index = int(self.first_segment.stem)
                last_index = int(last_segment.stem)
                file_list = []
                for i in range(first_index, last_index + 1):
                    output_filename = f"{i:09d}.ts"
                    file_path = os.path.join(self.temp_dir, output_filename)
                    file_list.append(f"file '{file_path}'")
                print(file_list)
                if len(file_list) >= 3:
                    file_list.pop()
                self.__compact_videos(file_list)
            finally:
                print("[INFO] stopped recording")
                self.is_recording = False

    def __compact_videos(self, file_list):
        event_temp_list_path = os.path.join(self.temp_dir, self.event_time.strftime("%Y%m%d_%H%M%S"))
        os.makedirs(event_temp_list_path, exist_ok=True)
        compact_file_list_path = os.path.join(event_temp_list_path, "list.txt")
        try:
            with open(compact_file_list_path, "w", encoding="utf-8") as f:
                file_content = "\n".join(file_list)
                f.write(file_content)
            event_output_temp_file = os.path.join(event_temp_list_path, "event.mp4")
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
            new_output_file = os.path.join(self.output_path, _date, self.camera_name, _time + ".mp4")
            os.makedirs(os.path.dirname(new_output_file), exist_ok=True)
            shutil.copy(event_output_temp_file, new_output_file)
        finally:
            if os.path.exists(event_temp_list_path):
                shutil.rmtree(event_temp_list_path)

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
        self.exit_event.set()
        if self.clear_thread.is_alive():
            self.clear_thread.join(timeout=2)
        self.__stop_background_record()
        self.__clear_temp_folder()
