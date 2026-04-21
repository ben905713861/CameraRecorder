import threading

import cv2
import time

class MotionDetector:
    def __init__(self,
                 rtsp_url,
                 name,
                 pixel_threshold,
                 motion_ratio_threshold,
                 alert_interval,
                 frame_skip,
                 callback):
        self.rtsp_url = rtsp_url
        self.name = name
        self.pixel_threshold = pixel_threshold
        self.motion_ratio_threshold = motion_ratio_threshold
        self.alert_interval = alert_interval
        if frame_skip <= 0:
            raise ValueError("frame_skip must be a positive integer, > 0")
        self.frame_skip = frame_skip
        self.cap = None
        self.prev_gray = None
        self.callback = callback

    def __connect(self):
        self.cap = cv2.VideoCapture(self.rtsp_url)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        if self.cap.isOpened():
            print("connect to RTSP stream successfully")
            return
        raise ConnectionError("unable to connect to RTSP stream")

    def detect(self):
        self.__connect()

        frame_count = 0
        last_alert_time = 0
        print(f"starting motion detection on camera [{self.name}] (with frame skipping)...")

        while True:
            ret, frame = self.cap.read()
            if not ret:
                self.cap.release()
                raise ConnectionError("video stream interrupted, trying to reconnect...")

            # skip frames
            frame_count += 1
            if frame_count % self.frame_skip != 0:
                continue

            # gary and blur
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)

            if self.prev_gray is None:
                self.prev_gray = gray
                continue

            # calculate frame difference
            diff = cv2.absdiff(self.prev_gray, gray)

            # binary thresholding
            _, thresh = cv2.threshold(diff, self.pixel_threshold, 255, cv2.THRESH_BINARY)

            # remove noise
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
            thresh = cv2.dilate(thresh, kernel, iterations=1)

            # calculate motion ratio
            changed_pixels = cv2.countNonZero(thresh)
            total_pixels = thresh.shape[0] * thresh.shape[1]
            motion_ratio = changed_pixels / total_pixels
            # print(motion_ratio)

            # alert if motion detected and alert interval has passed
            current_time = time.time()
            if motion_ratio > self.motion_ratio_threshold and \
               (current_time - last_alert_time > self.alert_interval):
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{timestamp}] ⚠️ detected motion: {motion_ratio:.2%}")

                try:
                    self.callback()
                except:
                    print("callback error, ignoring...")

                last_alert_time = current_time

            # update previous frame
            self.prev_gray = gray
