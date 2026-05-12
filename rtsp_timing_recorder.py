import atexit
import os
import subprocess
import threading
from datetime import datetime, timedelta

import cv2
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger


class TimingRecorder:
    def __init__(self, camera_name, rtsp_url, output_path, time_ranges: list[str]):
        if output_path is None:
            raise ValueError("output_path variable is not set")
        self.output_path = output_path
        self.camera_name = camera_name
        self.rtsp_url = rtsp_url
        self.time_ranges = time_ranges

        self.scheduler = BackgroundScheduler()
        self.record_process = None
        self.lock = threading.RLock()
        self.exit_event = threading.Event()

        self.time_range_objects = self.__get_time_range_objects()

        # ensure cleanup on exit
        atexit.register(self.cleanup)

    def start(self):
        self.__create_output_folder()
        self.__create_output_folder(timedelta_hours=1)
        self.__start_timer()
        self.__ensure_recording_state()

    def __ensure_recording_state(self):
        while not self.exit_event.wait(60):
            should_record_now = self.__should_record_now()
            is_ffmpeg_running = self.record_process is not None and self.record_process.poll() is None
            is_rtsp_connection_live = self.__rtsp_alive()

            if should_record_now:
                if is_rtsp_connection_live:
                    if not is_ffmpeg_running:
                        print("starting recording...")
                        self.__background_record()
                else:
                    print("rtsp connection is not live, stopping recording if needed...")
                    if is_ffmpeg_running:
                        self.__stop_record()
            else:
                if is_ffmpeg_running:
                    print("stopping recording...")
                    self.__stop_record()

    def __get_time_range_objects(self):
        time_range_list = []
        for time_range in self.time_ranges:
            _start_time, _end_time = time_range.split("-")
            start_time = datetime.strptime(_start_time, "%H:%M:%S").time()
            end_time = datetime.strptime(_end_time, "%H:%M:%S").time()
            if start_time >= end_time:
                raise ValueError("start_time must be less than end_time")
            for existing_time_range in time_range_list:
                existing_start_time, existing_end_time = existing_time_range
                if start_time < existing_end_time and end_time > existing_start_time:
                    raise ValueError("time ranges must not overlap")
            time_range_list.append((start_time, end_time))
        return time_range_list

    def __start_timer(self):
        for time_range_object in self.time_range_objects:
            start_time, end_time = time_range_object
            self.scheduler.add_job(
                self.__background_record,
                trigger='cron',
                hour=start_time.hour,
                minute=start_time.minute,
                second=start_time.second,
            )
            self.scheduler.add_job(
                self.__stop_record,
                'cron',
                hour=end_time.hour,
                minute=end_time.minute,
                second=end_time.second,
            )
        self.scheduler.add_job(
            self.__create_output_folder,
            CronTrigger.from_crontab("0 * * * *"),
            args=[1],
        )
        self.scheduler.start()

    def __should_record_now(self):
        now = datetime.now().time()
        for time_range in self.time_range_objects:
            start_time, end_time = time_range
            if start_time <= now < end_time:
                return True
        return False

    def __rtsp_connect_detect(self):
        cap = None
        try:
            cap = cv2.VideoCapture(self.rtsp_url)
            return cap.isOpened()
        except Exception as e:
            print("rtsp connection error:", e)
            return False
        finally:
            if cap:
                cap.release()

    def __create_output_folder(self, timedelta_hours=0):
        now = datetime.now() + timedelta(hours=timedelta_hours)
        output_folder = os.path.join(self.output_path, now.strftime("%Y-%m-%d"), self.camera_name)
        os.makedirs(output_folder, exist_ok=True)

    def __rtsp_alive(self, timeout_sec: int = 4) -> bool:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-rtsp_transport", "tcp",
            "-timeout", "3000000",  # 3s, 微秒
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_type",
            "-of", "default=nw=1:nk=1",
            self.rtsp_url,
        ]
        try:
            r = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout_sec,
                check=False,
            )
            return r.returncode == 0
        except subprocess.TimeoutExpired as e:
            print("rtsp connection check timeout:", e)
            return False
        except Exception as e:
            print("rtsp connection check error:", e)
            return False

    def __background_record(self):
        with self.lock:
            # record_process.poll() 返回 None：进程还在运行；返回整数（通常是退出码）：进程已经结束
            if self.record_process and self.record_process.poll() is None:
                return
            try:
                command = [
                    "ffmpeg",
                    "-rtsp_transport", "tcp",
                    "-fflags", "+genpts",
                    "-use_wallclock_as_timestamps", "1",
                    "-i", self.rtsp_url,
                    "-c", "copy",
                    "-f", "segment",
                    "-segment_time", "3600",
                    "-segment_format", "matroska",
                    "-segment_atclocktime", "1",
                    "-reset_timestamps", "1",
                    "-strftime", "1",
                    os.path.join(self.output_path, "%Y-%m-%d/" + self.camera_name +"/%H-%M.mkv")
                ]
                self.record_process = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception as e:
                print("failed to start recording:", e)
                self.record_process = None

    def __stop_record(self):
        with self.lock:
            if self.record_process is not None:
                try:
                    self.record_process.stdin.write(b"q")
                    self.record_process.stdin.flush()
                    self.record_process.wait(timeout=10)
                except Exception:
                    self.record_process.kill()
                finally:
                    self.record_process = None
                    print("[INFO] stopped background recording")

    def cleanup(self):
        print("[EXIT] cleaning up...")
        self.exit_event.set()
        self.__stop_record()
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
