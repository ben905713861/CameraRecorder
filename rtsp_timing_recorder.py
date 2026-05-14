import os
import subprocess
import threading
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger


class TimingRecorder:
    def __init__(self, name, rtsp_url, output_path, time_ranges: list[str], exit_event):
        if output_path is None:
            raise ValueError("output_path variable is not set")
        self.output_path = output_path
        self.name = name
        self.rtsp_url = rtsp_url
        self.time_ranges = time_ranges

        self.scheduler = BackgroundScheduler()
        self.record_process = None
        self.lock = threading.RLock()
        self.exit_event = exit_event

        self.time_range_objects = self.__get_time_range_objects()

    def start(self):
        print("TimingRecorder for camera [{}] starts successfully".format(self.name))
        self.__create_output_folder()
        self.__create_output_folder(timedelta_hours=1)
        self.__start_timer()
        self.__ensure_recording_state()
        self.cleanup()

    def __ensure_recording_state(self):
        while True:
            with self.lock:
                should_record_now = self.__should_record_now()
                if should_record_now:
                    is_ffmpeg_running = self.record_process is not None and self.record_process.poll() is None
                    if not is_ffmpeg_running:
                        print("bring up recording...")
                        self.__background_record()
            if self.exit_event.wait(30):
                break

    def __get_time_range_objects(self):
        time_range_list = []
        for time_range in self.time_ranges:
            _start_time, _end_time = time_range.split("-")
            start_time = datetime.strptime(_start_time, "%H:%M").time()
            end_time = datetime.strptime(_end_time, "%H:%M").time()
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
            CronTrigger.from_crontab("59 * * * *"),
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

    def __create_output_folder(self, timedelta_hours=0):
        now = datetime.now() + timedelta(hours=timedelta_hours)
        output_folder = os.path.join(self.output_path, now.strftime("%Y-%m-%d"), self.name)
        os.makedirs(output_folder, exist_ok=True)

    def __background_record(self):
        with self.lock:
            # record_process.poll() 返回 None：进程还在运行；返回整数（通常是退出码）：进程已经结束
            if self.record_process and self.record_process.poll() is None:
                return
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
                    "-segment_time", "3600",
                    "-segment_format", "matroska",
                    "-segment_atclocktime", "1",
                    "-reset_timestamps", "1",
                    "-strftime", "1",
                    os.path.join(self.output_path, "%Y-%m-%d/" + self.name + "/%H-%M-%S.mkv")
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
        print("[EXIT] TimingRecorder cleaning up...")
        self.__stop_record()
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
