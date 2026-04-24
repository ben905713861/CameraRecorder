import threading
import cv2
import time


class MotionDetector:
    def __init__(self,
                 rtsp_url,
                 name,
                 pixel_threshold=25,
                 motion_ratio_threshold=0.02,
                 alert_interval=10,
                 frame_skip=3,
                 callback=None):

        self.rtsp_url = rtsp_url
        self.name = name
        self.pixel_threshold = pixel_threshold
        self.motion_ratio_threshold = motion_ratio_threshold
        self.alert_interval = alert_interval

        if frame_skip <= 0:
            raise ValueError("frame_skip must be > 0")

        self.frame_skip = frame_skip
        self.cap = None
        self.prev_gray = None
        self.callback = callback

        # 连续帧计数（用于过滤瞬时变化）
        self.motion_frames = 0

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

        print(f"starting motion detection on camera [{self.name}] (optimized anti-light-change)...")

        while True:
            ret, frame = self.cap.read()
            if not ret:
                self.cap.release()
                raise ConnectionError("video stream interrupted")

            # === 跳帧 ===
            frame_count += 1
            if frame_count % self.frame_skip != 0:
                continue

            # === 灰度 + 模糊 ===
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)

            if self.prev_gray is None:
                self.prev_gray = gray
                continue

            # =========================
            # ⭐ 1. 亮度归一化（关键）
            # =========================
            mean_prev = cv2.mean(self.prev_gray)[0]
            mean_curr = cv2.mean(gray)[0]

            if mean_prev < 1:
                mean_prev = 1

            scale = mean_curr / mean_prev
            normalized_prev = cv2.convertScaleAbs(self.prev_gray, alpha=scale, beta=0)

            # =========================
            # ⭐ 2. 差分
            # =========================
            diff = cv2.absdiff(normalized_prev, gray)

            # =========================
            # ⭐ 3. 二值化
            # =========================
            _, thresh = cv2.threshold(diff, self.pixel_threshold, 255, cv2.THRESH_BINARY)

            # =========================
            # ⭐ 4. 去噪
            # =========================
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
            thresh = cv2.dilate(thresh, kernel, iterations=1)

            # =========================
            # ⭐ 5. 连通域过滤
            # =========================
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            valid_area = 0
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area > 500:   # 最小目标面积（可调）
                    valid_area += area

            total_pixels = thresh.shape[0] * thresh.shape[1]
            motion_ratio = valid_area / total_pixels

            # =========================
            # ⭐ 6. 全局变化抑制（抗开灯）
            # =========================
            if motion_ratio > 0.6:
                # 认为是开灯/关灯
                self.prev_gray = gray
                self.motion_frames = 0
                continue

            # =========================
            # ⭐ 7. 连续帧判断
            # =========================
            if motion_ratio > self.motion_ratio_threshold:
                self.motion_frames += 1
            else:
                self.motion_frames = 0

            if self.motion_frames < 3:
                self.prev_gray = gray
                continue

            # =========================
            # ⭐ 8. 报警控制
            # =========================
            current_time = time.time()

            if current_time - last_alert_time > self.alert_interval:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{timestamp}] ⚠️ detected motion: {motion_ratio:.2%}")

                if self.callback:
                    try:
                        self.callback()
                    except Exception as e:
                        print("callback error:", e)

                last_alert_time = current_time

            # 更新上一帧
            self.prev_gray = gray
