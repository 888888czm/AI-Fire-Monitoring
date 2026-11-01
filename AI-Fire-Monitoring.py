# -*- coding: utf-8 -*-
"""
生命危险行为监控系统 (LifeGuard Monitor) v2.0
====================================================================
功能：
  • 实时分析摄像头画面
  • 火焰/烟雾检测 → 报警 + 抓拍 + 微信推送
  • 疑似跌倒/水平危险姿态 → 报警 + 抓拍 + 微信推送
  • 正常行为 → 不报警
  • 停止监控 → 生成含位置信息的 HTML 报告
  • 随时启动 / 随时停止

依赖安装：
  pip install opencv-python mediapipe pillow numpy requests

打包 exe（推荐方式）：
  pyinstaller --noconfirm --onefile --windowed ^
      --collect-all mediapipe ^
      --collect-all cv2 ^
      --hidden-import mediapipe.python._framework_bindings ^
      --name LifeGuardMonitor lifeguard_monitor.py

  如果打包后运行时报 protobuf 相关错误，追加：
      --collect-all google.protobuf
====================================================================
"""

import os
import sys
import time
import json
import datetime
import threading
import traceback

import cv2
import numpy as np
import requests
from PIL import Image, ImageTk

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

try:
    import winsound
    HAS_BEEP = True
except Exception:
    HAS_BEEP = False

try:
    import mediapipe as mp
    HAS_MP = True
except Exception:
    HAS_MP = False


# ==================================================================
# 路径与目录
# ==================================================================
def _base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _pick_dir():
    for c in (_base_dir(), os.path.join(os.path.expanduser("~"), "LifeGuardData")):
        try:
            os.makedirs(c, exist_ok=True)
            p = os.path.join(c, ".w")
            with open(p, "w") as f:
                f.write("1")
            os.remove(p)
            return c
        except Exception:
            continue
    return os.getcwd()


DATA_DIR = _pick_dir()
SNAP_DIR = os.path.join(DATA_DIR, "snapshots")
REPORT_DIR = os.path.join(DATA_DIR, "reports")
for d in (SNAP_DIR, REPORT_DIR):
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass


def save_jpg(path, img):
    try:
        ext = os.path.splitext(path)[1] or ".jpg"
        ok, buf = cv2.imencode(ext, img)
        if ok:
            buf.tofile(path)
            return True
    except Exception:
        pass
    return False


# ==================================================================
# 地理位置（IP 定位，无 Key 回退）
# ==================================================================
class GeoLocator:
    """
    依次尝试多个免费 IP 定位端点。每个端点返回结构不同，
    这里用统一的提取逻辑解析出 纬度/经度/城市/国家。
    不使用任何第三方 SDK，全部为原生 requests 调用。
    """

    ENDPOINTS = [
        ("https://ipwho.org/json", ["latitude", "longitude", "city", "country"]),
        ("https://ipapi.co/json/", ["latitude", "longitude", "city", "country_name"]),
        ("https://ipinfo.io/json", None),  # 特殊处理 loc 字段
    ]

    def __init__(self, timeout=6):
        self.timeout = timeout
        self._cache = None

    def locate(self):
        if self._cache is not None:
            return self._cache
        result = {
            "lat": None, "lon": None,
            "city": "未知", "country": "未知",
            "ip": "未知", "source": "unavailable",
        }
        for url, keys in self.ENDPOINTS:
            try:
                r = requests.get(url, timeout=self.timeout,
                                 headers={"User-Agent": "LifeGuardMonitor/2.0"})
                if r.status_code != 200:
                    continue
                j = r.json()

                lat = lon = None
                city = country = None

                if "ipwho" in url:
                    lat, lon = j.get("latitude"), j.get("longitude")
                    city, country = j.get("city"), j.get("country")
                elif "ipapi.co" in url:
                    lat, lon = j.get("latitude"), j.get("longitude")
                    city, country = j.get("city"), j.get("country_name")
                elif "ipinfo.io" in url:
                    loc = j.get("loc", "")
                    if "," in loc:
                        lat, lon = [float(x) for x in loc.split(",")]
                    city, country = j.get("city"), j.get("country")

                if lat is not None and lon is not None:
                    result.update({
                        "lat": round(float(lat), 5),
                        "lon": round(float(lon), 5),
                        "city": city or "未知",
                        "country": country or "未知",
                        "ip": j.get("ip") or j.get("query") or "未知",
                        "source": url,
                    })
                    self._cache = result
                    return result
            except Exception:
                continue

        self._cache = result
        return result

    def text(self):
        g = self.locate()
        if g["lat"] is not None:
            return f"{g['city']}, {g['country']}  ({g['lat']}, {g['lon']})"
        return "位置不可用（IP 定位失败）"


# ==================================================================
# 微信推送（Server酱）
# ==================================================================
class WeChatNotifier:
    def __init__(self, sendkey=""):
        self.sendkey = (sendkey or "").strip()

    def send(self, title, body):
        if not self.sendkey:
            return False, "未配置 SendKey"
        try:
            url = f"https://sctapi.ftqq.com/{self.sendkey}.send"
            r = requests.post(url, data={"title": title[:100], "desp": body},
                              timeout=10)
            j = r.json()
            if j.get("code") == 0:
                return True, "推送成功"
            return False, str(j.get("message", "推送失败"))
        except Exception as e:
            return False, str(e)[:80]


# ==================================================================
# 检测器 1：火焰 / 烟雾
# ==================================================================
class FlameGuard:
    """
    火焰判定：HSV 橙色–红色区间 → 连通域面积占比 + 连续帧确认。
    烟雾判定：低饱和度、中高亮度的灰白区域，且面积占比明显更大才触发，
    避免把浅色墙壁/衣物误判为烟雾。
    两者都不使用深度学习权重，保证 exe 打包后的稳定性。
    """

    def __init__(self):
        self.fire_streak = 0
        self.smoke_streak = 0
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))

    def reset(self):
        self.fire_streak = 0
        self.smoke_streak = 0

    def analyze(self, frame):
        h, w = frame.shape[:2]
        area_total = float(h * w) if h * w else 1.0
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # --- 火焰颜色掩膜（自定义上下界，覆盖橙红高亮区域）---
        fire_mask = cv2.inRange(
            hsv,
            np.array([0, 110, 140], dtype=np.uint8),
            np.array([28, 255, 255], dtype=np.uint8),
        )
        fire_mask = cv2.morphologyEx(fire_mask, cv2.MORPH_CLOSE, self.kernel)
        fire_mask = cv2.morphologyEx(fire_mask, cv2.MORPH_OPEN, self.kernel)
        fire_px = cv2.countNonZero(fire_mask)
        fire_ratio = fire_px / area_total

        # --- 烟雾颜色掩膜（低饱和 + 较高亮度）---
        smoke_mask = cv2.inRange(
            hsv,
            np.array([0, 0, 150], dtype=np.uint8),
            np.array([180, 45, 255], dtype=np.uint8),
        )
        smoke_mask = cv2.morphologyEx(smoke_mask, cv2.MORPH_CLOSE, self.kernel)
        smoke_px = cv2.countNonZero(smoke_mask)
        smoke_ratio = smoke_px / area_total

        # 连续帧确认
        fire_now = fire_ratio > 0.006
        smoke_now = smoke_ratio > 0.12  # 烟雾阈值更高，防止浅色大面积误报

        self.fire_streak = self.fire_streak + 1 if fire_now else 0
        self.smoke_streak = self.smoke_streak + 1 if smoke_now else 0

        fire_confirmed = self.fire_streak >= 5
        smoke_confirmed = self.smoke_streak >= 8

        boxes = []
        if fire_confirmed:
            cnts, _ = cv2.findContours(fire_mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
            for c in cnts:
                if cv2.contourArea(c) > area_total * 0.002:
                    boxes.append(cv2.boundingRect(c))

        return {
            "fire": fire_confirmed,
            "smoke": smoke_confirmed,
            "fire_ratio": fire_ratio,
            "smoke_ratio": smoke_ratio,
            "fire_boxes": boxes,
        }


# ==================================================================
# 检测器 2：水平危险姿态（跌倒 / 濒死近似）
# ==================================================================
class PoseGuard:
    """
    使用 MediaPipe Pose 的肩、髋关键点：
      • 肩–髋在垂直方向上的距离过小  → 躯干接近水平
      • 同时肩部 x 坐标与髋部 x 坐标差异明显 → 倾斜而非直立
    连续多帧满足才确认，避免弯腰、坐下等正常动作误报。
    这是“自杀/濒死”场景在无深度学习行为分类模型时的轻量几何近似。
    """

    def __init__(self):
        self.streak = 0
        if HAS_MP:
            self.pose = mp.solutions.pose.Pose(
                static_image_mode=False,
                model_complexity=0,
                smooth_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
        else:
            self.pose = None

    def reset(self):
        self.streak = 0

    def analyze(self, frame_rgb):
        if self.pose is None:
            return {"danger": False, "visible": False, "reason": ""}

        try:
            res = self.pose.process(frame_rgb)
        except Exception:
            return {"danger": False, "visible": False, "reason": ""}

        if not res.pose_landmarks:
            self.streak = 0
            return {"danger": False, "visible": False, "reason": ""}

        lm = res.pose_landmarks.landmark
        try:
            ls = lm[mp.solutions.pose.PoseLandmark.LEFT_SHOULDER]
            rs = lm[mp.solutions.pose.PoseLandmark.RIGHT_SHOULDER]
            lh = lm[mp.solutions.pose.PoseLandmark.LEFT_HIP]
            rh = lm[mp.solutions.pose.PoseLandmark.RIGHT_HIP]
        except Exception:
            self.streak = 0
            return {"danger": False, "visible": False, "reason": ""}

        shoulder_y = (ls.y + rs.y) / 2.0
        hip_y = (lh.y + rh.y) / 2.0
        shoulder_x = (ls.x + rs.x) / 2.0
        hip_x = (lh.x + rh.x) / 2.0

        vert = abs(shoulder_y - hip_y)
        horiz = abs(shoulder_x - hip_x)

        # 躯干接近水平：垂直差很小，且水平偏移明显
        horizontal_torso = (vert < 0.10) and (horiz > 0.045)

        if horizontal_torso:
            self.streak += 1
        else:
            self.streak = max(0, self.streak - 1)

        danger = self.streak >= 12  # 约 0.5–1 秒的持续水平姿态

        return {
            "danger": danger,
            "visible": True,
            "reason": "躯干持续水平，疑似跌倒/生命危险" if danger else "",
            "vert": round(vert, 3),
            "horiz": round(horiz, 3),
        }


# ==================================================================
# 报告
# ==================================================================
REPORT_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>生命危险监控报告</title>
<style>
body{{font-family:"Microsoft YaHei",sans-serif;background:#f7f7f9;margin:0;padding:22px;color:#1f2328}}
h1{{font-size:20px;margin:0 0 10px}}
.meta{{color:#57606a;font-size:13px;margin-bottom:16px;line-height:1.8}}
table{{border-collapse:collapse;width:100%;background:#fff;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
th,td{{border:1px solid #d0d7de;padding:8px 9px;font-size:12.5px;vertical-align:top}}
th{{background:#f0f2f5;text-align:left}}
.danger{{color:#b42318;font-weight:700}}
.loc{{font-size:11.5px;color:#0969da}}
.snap{{display:inline-block;margin:4px;text-align:center;font-size:10px;color:#57606a}}
.snap img{{width:200px;display:block;border:1px solid #d0d7de;border-radius:3px}}
.foot{{margin-top:16px;font-size:11.5px;color:#8b949e}}
</style></head><body>
<h1>生命危险行为监控报告</h1>
<div class="meta">
生成时间：{gen_time}<br>
会话开始：{session_start}<br>
监控位置：<span class="loc">{location}</span><br>
异常事件：<span class="danger">{count}</span> 起
</div>
<table>
<tr><th style="width:34px">#</th><th>开始</th><th>结束</th><th>持续(秒)</th>
<th>类型</th><th>峰值指标</th><th>位置</th><th>现场抓拍</th></tr>
{rows}
</table>
<div class="foot">本报告由 LifeGuard Monitor 自动生成。检测结果基于颜色分析与姿态几何规则，仅供参考，不能替代人工判断。</div>
</body></html>"""


# ==================================================================
# 主程序
# ==================================================================
class App:
    W, H = 660, 495

    def __init__(self, root):
        self.root = root
        root.title("生命危险行为监控  v2.0")
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.resizable(False, False)

        self.cap = None
        self.running = False
        self.flame = FlameGuard()
        self.pose = PoseGuard()
        self.geo = GeoLocator()
        self.notifier = WeChatNotifier()
        self.location_text = "定位中..."

        self.events = []
        self.cur_event = None
        self.session_start = None
        self._photo = None
        self._img_id = None
        self._fail = 0
        self._last_alarm = 0.0
        self._last_snap = 0.0
        self._ev_snap_count = 0
        self._busy = False

        self._build_ui()
        self._async_locate()

    # ---------------- UI ----------------
    def _build_ui(self):
        main = ttk.Frame(self.root, padding=8)
        main.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(main, width=self.W, height=self.H,
                                bg="#111", highlightthickness=0)
        self.canvas.pack()
        self.canvas.create_text(self.W // 2, self.H // 2, text="摄像头未启动",
                                fill="gray", tags="hint")

        bar = ttk.Frame(main)
        bar.pack(fill="x", pady=5)

        self.btn_start = ttk.Button(bar, text="▶ 启动监控", command=self.start)
        self.btn_start.pack(side="left")
        self.btn_stop = ttk.Button(bar, text="■ 停止监控",
                                   command=lambda: self.stop(False), state="disabled")
        self.btn_stop.pack(side="left", padx=5)
        ttk.Button(bar, text="📄 生成报告",
                   command=lambda: self.make_report(False)).pack(side="left")
        ttk.Button(bar, text="📂 打开目录",
                   command=lambda: self.open_dir(DATA_DIR)).pack(side="left", padx=5)

        ttk.Label(bar, text="摄像头:").pack(side="left", padx=(12, 2))
        self.var_cam = tk.IntVar(value=0)
        ttk.Spinbox(bar, from_=0, to=5, width=3,
                    textvariable=self.var_cam).pack(side="left")

        # Server酱 SendKey
        ttk.Label(bar, text="SendKey:").pack(side="left", padx=(12, 2))
        self.var_key = tk.StringVar()
        ttk.Entry(bar, textvariable=self.var_key, width=22, show="•").pack(side="left")
        ttk.Button(bar, text="保存", width=5,
                   command=self._save_key).pack(side="left", padx=2)

        self.status = tk.StringVar(value="待机")
        ttk.Label(main, textvariable=self.status, foreground="#0969da").pack(anchor="w")

        logf = ttk.LabelFrame(main, text="事件日志", padding=3)
        logf.pack(fill="both", expand=True, pady=(5, 0))
        self.logtxt = tk.Text(logf, height=6, width=92, state="disabled", wrap="word")
        self.logtxt.pack(fill="both", expand=True)

        self._load_key()
        self.log("系统就绪。数据目录：" + DATA_DIR)
        if not HAS_MP:
            self.log("⚠ MediaPipe 未安装，姿态检测不可用（火焰检测仍正常工作）")

    def _save_key(self):
        k = self.var_key.get().strip()
        self.notifier.sendkey = k
        try:
            p = os.path.join(DATA_DIR, "sendkey.txt")
            with open(p, "w", encoding="utf-8") as f:
                f.write(k)
            self.log("SendKey 已保存")
        except Exception:
            self.log("SendKey 保存失败")

    def _load_key(self):
        try:
            p = os.path.join(DATA_DIR, "sendkey.txt")
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    k = f.read().strip()
                self.var_key.set(k)
                self.notifier.sendkey = k
        except Exception:
            pass

    def log(self, msg):
        try:
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            self.logtxt.configure(state="normal")
            self.logtxt.insert("end", f"[{ts}] {msg}\n")
            self.logtxt.see("end")
            self.logtxt.configure(state="disabled")
        except Exception:
            pass

    def open_dir(self, p):
        try:
            if os.name == "nt":
                os.startfile(p)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", p])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", p])
        except Exception:
            messagebox.showinfo("目录", str(p))

    def show_hint(self, txt):
        try:
            self.canvas.delete("all")
            self._img_id = None
            self.canvas.create_text(self.W // 2, self.H // 2,
                                    text=txt, fill="gray", tags="hint")
        except Exception:
            pass

    def show_frame(self, frame):
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            im = Image.fromarray(rgb).resize((self.W, self.H), Image.BILINEAR)
            self._photo = ImageTk.PhotoImage(im)
            if self._img_id is None:
                self._img_id = self.canvas.create_image(0, 0, anchor="nw",
                                                        image=self._photo)
            else:
                self.canvas.itemconfigure(self._img_id, image=self._photo)
        except Exception:
            pass

    # ---------------- 定位（后台）----------------
    def _async_locate(self):
        def run():
            self.location_text = self.geo.text()
            try:
                self.root.after(0, lambda: self.status.set(
                    f"定位：{self.location_text}"))
            except Exception:
                pass
        threading.Thread(target=run, daemon=True).start()

    # ---------------- 启停 ----------------
    def start(self):
        if self.running:
            return
        try:
            idx = int(self.var_cam.get())
        except Exception:
            idx = 0

        cap = None
        try:
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW) if os.name == "nt" \
                else cv2.VideoCapture(idx)
            if cap is None or not cap.isOpened():
                try:
                    cap.release()
                except Exception:
                    pass
                cap = cv2.VideoCapture(idx)
        except Exception:
            cap = None

        if cap is None or not cap.isOpened():
            messagebox.showerror("错误", f"无法打开摄像头（索引 {idx}）。\n"
                                         "请确认设备未被其他程序占用。")
            return

        try:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.W)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.H)
        except Exception:
            pass

        self.cap = cap
        self.flame.reset()
        self.pose.reset()
        self.running = True
        self._fail = 0
        self.cur_event = None
        self._last_alarm = 0.0
        self._last_snap = 0.0
        self._ev_snap_count = 0
        self.session_start = datetime.datetime.now()

        self.canvas.delete("all")
        self._img_id = None
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.status.set(f"监控中… | 位置：{self.location_text}")
        self.log("监控已启动")
        self.root.after(25, self.loop)

    def stop(self, silent=True):
        if not self.running:
            return
        self.running = False
        try:
            if self.cap:
                self.cap.release()
        except Exception:
            pass
        self.cap = None

        if self.cur_event:
            self.cur_event["end"] = datetime.datetime.now()
            self.cur_event = None

        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.status.set("已停止")
        self.show_hint("监控已停止")
        self.log("监控已停止")

        report = self.make_report(True)
        if report and not silent:
            try:
                if messagebox.askyesno("监控结束",
                                       f"共记录 {len(self.events)} 起异常事件。\n"
                                       "是否打开报告？"):
                    self.open_dir(report)
            except Exception:
                pass

    def on_close(self):
        try:
            self.stop(True)
        except Exception:
            pass
        try:
            if HAS_MP and self.pose.pose:
                self.pose.pose.close()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass

    # ---------------- 主循环 ----------------
    def loop(self):
        if not self.running:
            return
        ok, frame = False, None
        try:
            ok, frame = self.cap.read()
        except Exception:
            ok = False

        if not ok or frame is None:
            self._fail += 1
            if self._fail > 60:
                self.log("摄像头读取失败，自动停止")
                self.stop(True)
                return
            self.root.after(100, self.loop)
            return

        self._fail = 0
        try:
            self.process(frame)
        except Exception:
            self.log("处理异常：" + traceback.format_exc(limit=1))

        self.root.after(15, self.loop)

    def process(self, frame):
        now = time.time()
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        fr = self.flame.analyze(frame)
        pr = self.pose.analyze(rgb)

        danger = fr["fire"] or fr["smoke"] or pr["danger"]
        kind = None
        metric = None

        if fr["fire"]:
            kind = "火焰"
            metric = fr["fire_ratio"]
        elif fr["smoke"]:
            kind = "烟雾"
            metric = fr["smoke_ratio"]
        elif pr["danger"]:
            kind = "水平危险姿态"
            metric = pr.get("vert", 0)

        # ---- 事件开始 ----
        if danger and self.cur_event is None:
            self.cur_event = {
                "id": len(self.events) + 1,
                "start": datetime.datetime.now(),
                "end": None,
                "kind": kind,
                "peak": metric,
                "location": self.location_text,
                "snaps": [],
            }
            self.events.append(self.cur_event)
            self._ev_snap_count = 0
            self._snap(frame, fr, pr, "start")
            self._alarm()
            self._last_alarm = now
            self.status.set(f"⚠ {kind}报警中！")
            self.log(f"⚠ 检测到{kind}，运动指标 {metric:.4f}")
            self._push_wechat(kind, metric)

        # ---- 事件持续 ----
        if danger and self.cur_event:
            if metric is not None and (self.cur_event["peak"] is None
                                       or metric > self.cur_event["peak"]):
                self.cur_event["peak"] = metric
            if now - self._last_snap > 2.5 and self._ev_snap_count < 6:
                self._snap(frame, fr, pr, "during")
            if now - self._last_alarm > 6.0:
                self._alarm()
                self._last_alarm = now

        # ---- 事件结束 ----
        if (not danger) and self.cur_event is not None:
            self.cur_event["end"] = datetime.datetime.now()
            dur = (self.cur_event["end"] - self.cur_event["start"]).total_seconds()
            self.log(f"{self.cur_event['kind']}事件结束，持续 {dur:.1f} 秒，"
                     f"抓拍 {len(self.cur_event['snaps'])} 张")
            self.cur_event = None
            self.status.set(f"监控中… | {self.location_text}")

        # ---- 绘制 ----
        vis = frame.copy()
        alarm_color = (0, 0, 255) if danger else (0, 190, 0)
        for (x, y, w, h) in fr.get("fire_boxes", []):
            cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 140, 255), 2)
        if pr.get("danger") and pr.get("visible"):
            cv2.putText(vis, "HORIZONTAL DANGER", (12, 32),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        cv2.putText(vis, f"F:{fr['fire_ratio']*100:.2f}% S:{fr['smoke_ratio']*100:.1f}%",
                    (12, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.62, alarm_color, 1)
        if danger:
            cv2.putText(vis, "ALARM", (12, 100),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.05, (0, 0, 255), 3)
        self.show_frame(vis)

    # ---------------- 抓拍 ----------------
    def _snap(self, frame, fr, pr, tag):
        try:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            p = os.path.join(SNAP_DIR, f"lg_{ts}_{tag}.jpg")
            vis = frame.copy()
            for (x, y, w, h) in fr.get("fire_boxes", []):
                cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 0, 255), 2)
            stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cv2.putText(vis, stamp, (10, vis.shape[0] - 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)
            if save_jpg(p, vis):
                if self.cur_event:
                    self.cur_event["snaps"].append(p)
                self._last_snap = time.time()
                self._ev_snap_count += 1
                self.log("抓拍：" + os.path.basename(p))
        except Exception:
            pass

    def _alarm(self):
        if HAS_BEEP:
            def run():
                try:
                    for _ in range(5):
                        if not self.running:
                            break
                        winsound.Beep(1800, 260)
                        time.sleep(0.1)
                except Exception:
                    pass
            threading.Thread(target=run, daemon=True).start()
        else:
            try:
                self.root.bell()
            except Exception:
                pass

    # ---------------- 微信推送（异步）----------------
    def _push_wechat(self, kind, metric):
        if not self.notifier.sendkey:
            self.log("未配置 SendKey，跳过微信推送")
            return

        loc = self.location_text
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        def run():
            title = f"⚠ 生命危险报警：{kind}"
            body = (
                f"**类型**：{kind}\n\n"
                f"**时间**：{ts}\n\n"
                f"**位置**：{loc}\n\n"
                f"**指标**：{metric:.4f}\n\n"
                "请立即查看监控并确认现场情况。"
            )
            ok, msg = self.notifier.send(title, body)
            self.log(("微信推送成功" if ok else "微信推送失败：" + msg))

        threading.Thread(target=run, daemon=True).start()

    # ---------------- 报告 ----------------
    def make_report(self, auto=False):
        try:
            if not self.events:
                if not auto:
                    messagebox.showinfo("提示", "本次没有异常事件。")
                return None

            now = datetime.datetime.now()
            p = os.path.join(REPORT_DIR,
                             "report_" + now.strftime("%Y%m%d_%H%M%S") + ".html")
            rows = []
            for i, ev in enumerate(self.events, 1):
                st = ev["start"].strftime("%Y-%m-%d %H:%M:%S")
                en = ev["end"].strftime("%Y-%m-%d %H:%M:%S") if ev["end"] else "进行中"
                dur = ((ev["end"] or now) - ev["start"]).total_seconds()
                peak = f"{ev['peak']:.4f}" if ev["peak"] is not None else "-"
                loc = ev.get("location") or self.location_text
                imgs = "".join(
                    '<div class="snap"><img src="file:///{}"><div>{}</div></div>'.format(
                        x.replace("\\", "/"), os.path.basename(x))
                    for x in ev["snaps"]
                ) or "无"
                rows.append(
                    f"<tr><td>{i}</td><td>{st}</td><td>{en}</td><td>{dur:.1f}</td>"
                    f"<td class='danger'>{ev['kind']}</td><td>{peak}</td>"
                    f"<td class='loc'>{loc}</td><td>{imgs}</td></tr>"
                )

            html = REPORT_HTML.format(
                gen_time=now.strftime("%Y-%m-%d %H:%M:%S"),
                session_start=(self.session_start or now).strftime("%Y-%m-%d %H:%M:%S"),
                location=self.location_text,
                count=len(self.events),
                rows="\n".join(rows),
            )
            with open(p, "w", encoding="utf-8") as f:
                f.write(html)

            self.log("报告已生成：" + p)
            if not auto:
                self.open_dir(p)
            return p
        except Exception:
            self.log("生成报告失败：" + traceback.format_exc(limit=1))
            return None


# ==================================================================
def main():
    try:
        root = tk.Tk()
    except Exception as e:
        print("创建窗口失败：", e)
        return
    try:
        App(root)
    except Exception:
        messagebox.showerror("启动失败", traceback.format_exc())
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()