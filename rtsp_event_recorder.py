import atexit
import os
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from threading import Timer


class EventRecorder:
    def __init__(self, camera_name, rtsp_url, output_path, record_interval, segment_retain_time, exit_event):
        if output_path is None:
            raise ValueError("output_path variable is not set")
        self.output_path = output_path
        self.record_interval = record_interval
        self.segment_retain_time = segment_retain_time
        self.camera_name = camera_name
        self.rtsp_url = rtsp_url

        self.first_segment = None
        self.is_recording = False
        self.timer = None

        self.exit_event = exit_event
        self.event_time = None
        self.lock = threading.Lock()

        self.temp_dir = os.path.join(tempfile.gettempdir(), "camera", self.camera_name)
        self.__clear_temp_folder()
        os.makedirs(self.temp_dir, exist_ok=True)

        self.clear_thread = None

    def start(self):
        self.__clear_unused_temp_segments_process()
        self.__background_record_process()

    def __clear_unused_temp_segments_process(self):
        self.clear_thread = threading.Thread(target=self.__clear_unused_temp_segments, daemon=False)
        self.clear_thread.start()

    def __clear_unused_temp_segments(self):
        retain_number = int(self.segment_retain_time / self.record_interval)
        while not self.exit_event.wait(60):
            try:
                if not os.path.exists(self.temp_dir):
                    os.makedirs(self.temp_dir, exist_ok=True)
                file_paths = self.__get_temp_dir_filelist()
                print("__clear_unused_temp_segments, found {} files".format(len(file_paths)))
                for file_path in file_paths[retain_number:]:
                    if os.path.exists(file_path):
                        os.remove(file_path)
            except (FileNotFoundError, OSError):
                pass
        print("receive exit instruction, stop __clear_unused_temp_segments_process...")

    def __clear_temp_folder(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def __background_record_process(self):
        self.background_record_thread = threading.Thread(target=self.__background_record, daemon=False)
        self.background_record_thread.start()

    def __background_record(self):
        while True:
            try:
                command = [
                    "ffmpeg",
                    "-rtsp_transport", "tcp",
                    "-timeout", "5000000",  # 5s, 微秒
                    "-fflags", "+genpts",
                    "-use_wallclock_as_timestamps", "1",
                    "-i", self.rtsp_url,
                    "-c", "copy",
                    "-f", "segment",
                    "-segment_time", str(self.record_interval),
                    # "-segment_wrap", "20",
                    "-segment_format", "matroska",
                    "-reset_timestamps", "1",
                    os.path.join(self.temp_dir, "%09d.mkv")
                ]
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True
                )
                for line in process.stderr:
                    if not line.startswith("frame="):
                        print(line, end="")
                    if self.exit_event.is_set():
                        print("receive exit instruction, stop ffmpeg printing...")
                        self.__stop_process(process)
                        process.wait()
                        print("ffmpeg exit code", process.returncode)
                        return
            except Exception as e:
                print("ffmpeg recording process error:", e)
                if self.exit_event.wait(60):
                    print("receive exit instruction, stop retrying to start ffmpeg...")
                    return

    def record(self):
        with self.lock:
            if self.is_recording:
                print("already recording")
                if self.timer:
                    self.timer.cancel()
                self.timer = Timer(self.record_interval * 2, self.__stop_record)
                self.timer.start()
                return
            print("[INFO] starting recording")
            self.is_recording = True
            self.event_time = datetime.now()

            # self.ffmpeg_record()
            self.first_segment = self.__get_start_segment()
            print("first_segment", self.first_segment)
            if not self.first_segment:
                print("no segment found, skipping recording...")
                self.is_recording = False
                return

            self.timer = Timer(self.record_interval * 2, self.__stop_record)
            self.timer.start()

    def __get_start_segment(self) -> Path | None:
        file_paths = self.__get_temp_dir_filelist()
        if len(file_paths) == 0:
            return None
        if len(file_paths) == 1:
            return file_paths[0]
        return file_paths[1]

    def __get_end_segment(self) -> Path | None:
        file_paths = self.__get_temp_dir_filelist()
        if len(file_paths) == 0:
            return None
        return file_paths[0]

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
                last_segment = self.__get_end_segment()
                if not last_segment or not self.first_segment:
                    print("no segment found, skipping compacting...")
                    return
                print("last_segment", last_segment)
                first_index = int(self.first_segment.stem)
                last_index = int(last_segment.stem)
                file_list = []
                for i in range(first_index, last_index + 1):
                    output_filename = f"{i:09d}.mkv"
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
            event_output_temp_file = os.path.join(event_temp_list_path, "event.mkv")
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
            new_output_file = os.path.join(self.output_path, _date, self.camera_name, _time + ".mkv")
            os.makedirs(os.path.dirname(new_output_file), exist_ok=True)
            shutil.copy(event_output_temp_file, new_output_file)
        finally:
            if os.path.exists(event_temp_list_path):
                shutil.rmtree(event_temp_list_path)

    def __stop_process(self, process):
        try:
            process.stdin.write(b"q")
            process.stdin.flush()
            process.wait(timeout=10)
        except Exception:
            process.kill()
        finally:
            print("[INFO] EventRecorder stopped background recording")

    def cleanup(self):
        print("[EXIT] EventRecorder cleaning up...")
        if self.timer:
            self.timer.cancel()
        if self.clear_thread.is_alive():
            self.clear_thread.join(timeout=60)
        if self.background_record_thread.is_alive():
            self.background_record_thread.join(timeout=60)
        self.__clear_temp_folder()
