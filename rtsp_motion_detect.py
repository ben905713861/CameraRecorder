import cv2
import time

def motion_detect(
         name,
         rtsp_url,
         pixel_threshold,
         motion_ratio_threshold,
         alert_interval,
         frame_skip,
         callback):
    cap = cv2.VideoCapture(rtsp_url)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)

    if not cap.isOpened():
        print("unable to connect to RTSP stream")
        return

    # read first frame
    ret, frame = cap.read()
    if not ret:
        print("unable to read from video stream")
        return

    prev_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    prev_gray = cv2.GaussianBlur(prev_gray, (5, 5), 0)

    frame_count = 0
    last_alert_time = 0

    print(f"starting motion detection on camera [{name}] (with frame skipping)...")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("video stream interrupted, trying to reconnect...")
            time.sleep(2)
            cap.release()
            cap = cv2.VideoCapture(rtsp_url)
            continue

        frame_count += 1

        # skip frames
        if frame_count % frame_skip != 0:
            continue

        # gary and blur
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        # calculate frame difference
        diff = cv2.absdiff(prev_gray, gray)

        # binary thresholding
        _, thresh = cv2.threshold(diff, pixel_threshold, 255, cv2.THRESH_BINARY)

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
        if motion_ratio > motion_ratio_threshold and \
           (current_time - last_alert_time > alert_interval):
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] ⚠️ detected motion: {motion_ratio:.2%}")
            callback()
            last_alert_time = current_time

        # update previous frame
        prev_gray = gray
