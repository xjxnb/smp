
# web_control.py (人脸识别版 - CAN总线控制版)

from flask import Flask, render_template_string, Response
from picamera2 import Picamera2
import cv2
import threading
import time
import signal
import sys
import os
import face_recognition
import numpy as np
import can

# ==================== 配置区域 ====================
# CAN 配置
CAN_INTERFACE = 'canalystii'       # 接口类型
CAN_CHANNEL = 0                     # CAN1通道
CAN_BITRATE = 500000
CAN_DEVICE = '/dev/ttyUSB1'         # 实际设备节点（请确认）
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
KNOWN_FACES_DIR = '/home/xjx/known_faces'
# =================================================

running = True
output_frame = None
lock = threading.Lock()

# ---------- CAN 总线初始化 ----------
try:
    can_bus = can.interface.Bus(
        interface=CAN_INTERFACE,
        channel=CAN_CHANNEL,
        bitrate=CAN_BITRATE,
        serial_device=CAN_DEVICE
    )
    print("CAN总线初始化成功")
except Exception as e:
    print(f"CAN总线初始化失败: {e}")
    can_bus = None

# ---------- 加载已知人脸 ----------
known_face_encodings = []
known_face_names = []

if os.path.exists(KNOWN_FACES_DIR):
    for filename in os.listdir(KNOWN_FACES_DIR):
        if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            name = os.path.splitext(filename)[0]
            image_path = os.path.join(KNOWN_FACES_DIR, filename)
            image = face_recognition.load_image_file(image_path)
            encodings = face_recognition.face_encodings(image)
            if encodings:
                known_face_encodings.append(encodings[0])
                known_face_names.append(name)
                print(f"已加载人脸: {name}")
            else:
                print(f"警告: {filename} 中未检测到人脸，已跳过")
else:
    print(f"警告: 文件夹 {KNOWN_FACES_DIR} 不存在，将只进行人脸检测")

print(f"共加载 {len(known_face_names)} 个已知人脸")

# ---------- 初始化摄像头 ----------
picam2 = Picamera2()
config = picam2.create_preview_configuration(main={"format": 'XRGB8888', "size": (CAMERA_WIDTH, CAMERA_HEIGHT)})
picam2.configure(config)
picam2.start()
time.sleep(2)
print("摄像头初始化完成")

# ---------- Flask应用 ----------
app = Flask(__name__)

# ==================== 核心功能函数 ====================
def detect_faces():
    global output_frame, lock, running

    DETECT_INTERVAL = 0.3
    CONFIDENCE_THRESHOLD = 0.75

    last_detect_time = 0
    last_cmd = None          # 上次发送的指令，避免重复

    while running:
        loop_start = time.time()

        frame = picam2.capture_array()
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
        display_frame = frame_bgr.copy()

        if time.time() - last_detect_time > DETECT_INTERVAL:
            last_detect_time = time.time()

            small = cv2.resize(frame_bgr, (0,0), fx=0.5, fy=0.5)
            rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

            face_locations = face_recognition.face_locations(rgb_small, model="hog")
            current_name = "Unknown"
            confidence = 0

            if face_locations:
                top, right, bottom, left = [int(v*2) for v in face_locations[0]]
                cv2.rectangle(display_frame, (left, top), (right, bottom), (0,255,0), 2)

                face_encodings = face_recognition.face_encodings(rgb_small, face_locations)
                if face_encodings and known_face_encodings:
                    distances = face_recognition.face_distance(known_face_encodings, face_encodings[0])
                    min_dist = np.min(distances)
                    best_index = np.argmin(distances)
                    print(f"最匹配: {known_face_names[best_index]}, 距离: {min_dist:.3f}")

                    if min_dist < CONFIDENCE_THRESHOLD:
                        current_name = known_face_names[best_index]
                        confidence = (CONFIDENCE_THRESHOLD - min_dist) / CONFIDENCE_THRESHOLD * 100
                        print(f"识别为: {current_name} ({confidence:.1f}%)")
                    else:
                        print("距离超过阈值，Unknown")

                label = f"{current_name} ({confidence:.1f}%)"
                cv2.putText(display_frame, label, (left, top-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)

            # 发送CAN指令（仅当状态变化时）
            should_send = (current_name != "Unknown")
            cmd = b'A' if should_send else b'B'
            if cmd != last_cmd and can_bus:
                # 构造CAN消息，数据域为 ASCII 码
                msg = can.Message(arbitration_id=0x12, data=[cmd[0]], is_extended_id=False)
                can_bus.send(msg)
                print(f"发送指令: {cmd}")
                last_cmd = cmd

        cv2.putText(display_frame, f"Status: {current_name if 'current_name' in locals() else 'Unknown'}", (10,30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)

        with lock:
            ret, jpeg = cv2.imencode('.jpg', display_frame)
            output_frame = jpeg.tobytes()

        elapsed = time.time() - loop_start
        time.sleep(max(0, 0.05 - elapsed))

def generate_video():
    global output_frame, lock, running
    while running:
        with lock:
            if output_frame is None:
                continue
            frame_data = output_frame
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
        time.sleep(0.03)

# ==================== Flask路由 ====================
@app.route('/')
def index():
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>树莓派智能监控 - 人脸识别</title>
        <style>
            body { text-align: center; font-family: Arial; margin-top: 50px; background-color: #f0f0f0; }
            img { width: 80%; max-width: 640px; border: 2px solid #333; border-radius: 10px; }
            .status { font-size: 24px; margin: 20px; color: #333; }
            .button { padding: 15px 30px; font-size: 18px; margin: 10px; cursor: pointer; border: none; border-radius: 5px; }
            .button-on { background-color: #4CAF50; color: white; }
            .button-off { background-color: #f44336; color: white; }
        </style>
    </head>
    <body>
        <h1>🎥 树莓派人脸识别监控</h1>
        <p class="status">实时画面 (绿色框: 检测到人脸，标注姓名)</p>
        <img src="{{ url_for('video_feed') }}" />
        <p class="status">手动控制LED (测试用)</p>
        <button class="button button-on" onclick="sendCommand('ON')">🔛 打开LED</button>
        <button class="button button-off" onclick="sendCommand('OFF')">🔴 关闭LED</button>

        <script>
            function sendCommand(state) {
                fetch('/command/' + state)
                    .then(response => response.text())
                    .then(data => alert(data))
                    .catch(error => console.error('Error:', error));
            }
        </script>
    </body>
    </html>
    ''')

@app.route('/video_feed')
def video_feed():
    return Response(generate_video(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/command/<cmd>')
def command(cmd):
    if can_bus:
        if cmd == 'ON':
            msg = can.Message(arbitration_id=0x12, data=[65], is_extended_id=False)
            can_bus.send(msg)
            return "LED 已打开 (CAN)"
        elif cmd == 'OFF':
            msg = can.Message(arbitration_id=0x12, data=[66], is_extended_id=False)
            can_bus.send(msg)
            return "LED 已关闭 (CAN)"
        else:
            return "未知命令"
    else:
        return "CAN总线未初始化"

# ==================== 启动与退出处理 ====================
def signal_handler(sig, frame):
    global running
    print("\n正在关闭程序，请稍候...")
    running = False
    if detect_thread.is_alive():
        detect_thread.join(timeout=2)
    if can_bus:
        # can_bus 可能没有 close 方法，忽略
        pass
    sys.exit(0)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)

    detect_thread = threading.Thread(target=detect_faces, daemon=False)
    detect_thread.start()
    print("人脸识别线程已启动")

    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
