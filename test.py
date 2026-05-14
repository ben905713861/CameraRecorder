import signal
import threading
import time

def test():
    try:
        while not exit_event.is_set():
            time.sleep(1)
            print("test")
    finally:
        print("exiting test thread...")


def signal_handler(signum, frame):
    """系统信号监听回调函数"""
    signame = signal.Signals(signum).name
    print(f"\n⚠️ 【主线程】接收到系统信号: {signame} ({signum})")

    # 2. 触发全局事件，通知所有子线程“该收工了”
    print("【主线程】正在通知所有守护线程停下手中的工作...")
    exit_event.set()

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    exit_event = threading.Event()
    thread = threading.Thread(target=test, daemon=True)
    thread.start()

    # try:
    #     exit_event.wait()
    # except KeyboardInterrupt:
    #     print("KeyboardInterrupt, exiting...")
    #     exit_event.set()

    try:
        thread.join()
    except KeyboardInterrupt:
        print("KeyboardInterrupt in main thread, exiting...")
