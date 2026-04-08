# Zhipu Tray 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Zhipu ASR 语音输入法创建带系统托盘和 GUI 的桌面应用

**Architecture:** PySide6 GUI + Qt SystemTrayIcon + 封装 asr_cli.py 为 ASREngine，托盘图标在录音时显示脉冲动画

**Tech Stack:** Python 3.13, PySide6, sounddevice, numpy, keyboard, pyautogui, pyperclip, zhipuai

---

## 文件结构

```
/home/wurong/workspace/zhipu/
├── zhipu_tray.py              # 入口：托盘 + 主窗口
├── asr_engine.py              # 封装 ASR 核心逻辑
├── ui/
│   ├── __init__.py
│   ├── main_window.py         # 主窗口 UI
│   └── styles.py              # QSS 样式
├── assets/
│   └── icons/                 # 托盘图标资源
├── zhipu.desktop              # 桌面快捷方式
└── requirements.txt
```

---

## Task 1: 创建项目结构和依赖

**Files:**
- Create: `/home/wurong/workspace/zhipu/requirements.txt`
- Create: `/home/wurong/workspace/zhipu/ui/__init__.py`
- Create: `/home/wurong/workspace/zhipu/assets/icons/`

- [ ] **Step 1: 创建 requirements.txt**

```txt
PySide6
sounddevice
numpy
keyboard
pyautogui
pyperclip
zhipuai
PyYAML
```

- [ ] **Step 2: 创建目录结构**

Run: `mkdir -p ui assets/icons`

- [ ] **Step 3: 创建空 ui/__init__.py**

```python
# UI package
```

- [ ] **Step 4: 安装依赖**

Run: `pip install -r requirements.txt`

- [ ] **Step 5: Commit**

```bash
git add requirements.txt ui/__init__.py
git commit -m "feat: add project structure and dependencies"
```

---

## Task 2: 创建托盘图标资源

**Files:**
- Create: `/home/wurong/workspace/zhipu/assets/icons/mic_idle.svg`
- Create: `/home/wurong/workspace/zhipu/assets/icons/mic_recording.svg`

- [ ] **Step 1: 创建静态麦克风图标 (mic_idle.svg)**

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="#888888">
  <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm-1 1.93c-3.94-.49-7-3.85-7-7.93h2c0 3.03 2.47 5.5 5.5 5.5S17 10.03 17 7h2c0 4.08-3.06 7.44-7 7.93V19h3v2H9v-2h3v-3.07z"/>
</svg>
```

- [ ] **Step 2: 创建录音图标 (mic_recording.svg)**

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="#E53935">
  <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm-1 1.93c-3.94-.49-7-3.85-7-7.93h2c0 3.03 2.47 5.5 5.5 5.5S17 10.03 17 7h2c0 4.08-3.06 7.44-7 7.93V19h3v2H9v-2h3v-3.07z"/>
</svg>
```

- [ ] **Step 3: Commit**

```bash
git add assets/icons/mic_idle.svg assets/icons/mic_recording.svg
git commit -m "feat: add tray icons"
```

---

## Task 3: 实现 ASREngine 类

**Files:**
- Create: `/home/wurong/workspace/zhipu/asr_engine.py`

- [ ] **Step 1: 编写 ASREngine 类**

```python
#!/usr/bin/env python3
"""
ASR Engine - 封装 asr_cli.py 的核心逻辑
"""

import io
import json
import signal
import wave
from enum import Enum
from typing import Callable, Optional

import numpy as np
import sounddevice as sd
from pynput import keyboard

from zhipuai import ZhipuAI
import yaml


SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = 'int16'


class ASRState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    RECORDING = "recording"
    PROCESSING = "processing"


class ASREngine:
    def __init__(
        self,
        api_key: str,
        config_path: str = "config.yaml",
        debug: bool = False,
        state_callback: Optional[Callable[[ASRState], None]] = None,
        result_callback: Optional[Callable[[str], None]] = None,
    ):
        self.api_key = api_key
        if not self.api_key:
            raise ValueError("API key not provided")

        self.client = ZhipuAI(api_key=self.api_key)
        self.debug = debug
        self.config = self._load_config(config_path)
        self.hotwords = self.config.get("hotwords", [])
        self.prompt = self.config.get("prompt", "")

        self.state = ASRState.IDLE
        self._state_callback = state_callback
        self._result_callback = result_callback

        self._is_recording = False
        self._recording_frames: list[np.ndarray] = []
        self._recording_lock = None  # Initialized in start()
        self._running = False
        self._recording_done_event = None
        self._listener = None

        signal.signal(signal.SIGINT, self._signal_handler)

    def _load_config(self, config_path: str) -> dict:
        import os
        if not os.path.exists(config_path):
            return {}
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _signal_handler(self, _signum, _frame):
        self.stop()

    def set_state(self, state: ASRState):
        self.state = state
        if self._state_callback:
            self._state_callback(state)

    def _create_wav_bytes(self, audio_data: np.ndarray) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_data.tobytes())
        buffer.seek(0)
        return buffer.read()

    def _on_rctrl_press(self, key):
        if key == keyboard.Key.ctrl_r and not self._is_recording:
            self._is_recording = True
            self._recording_frames = []
            self.set_state(ASRState.RECORDING)
            self._start_recording_thread()

    def _on_rctrl_release(self, key):
        if key == keyboard.Key.ctrl_r and self._is_recording:
            self._is_recording = False
            self.set_state(ASRState.PROCESSING)

    def _recording_thread_target(self):
        import threading
        self._recording_lock = threading.Lock()
        stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE)
        with stream:
            while self._is_recording and self._running:
                frames, _ = stream.read(int(SAMPLE_RATE * 0.1))
                with self._recording_lock:
                    self._recording_frames.append(frames.copy())

    def _start_recording_thread(self):
        import threading
        t = threading.Thread(target=self._recording_thread_target, daemon=True)
        t.start()

    def _get_recorded_audio(self) -> np.ndarray:
        import threading
        if self._recording_lock is None:
            return np.array([], dtype=DTYPE)
        with self._recording_lock:
            if not self._recording_frames:
                return np.array([], dtype=DTYPE)
            return np.concatenate(self._recording_frames)

    def _transcribe(self, wav_bytes: bytes) -> str:
        kwargs = {
            "file": ("audio.wav", wav_bytes, "audio/wav"),
            "model": "GLM-ASR-2512",
            "stream": True
        }
        extra_body = {}
        if self.prompt:
            extra_body["prompt"] = self.prompt
        if self.hotwords:
            extra_body["hotwords"] = json.dumps(self.hotwords)
        if extra_body:
            kwargs["extra_body"] = extra_body

        response = self.client.audio.transcriptions.create(**kwargs)

        full_text = ""
        for chunk in response:
            chunk_type = getattr(chunk, 'type', None)
            if chunk_type == 'transcript.text_delta':
                delta = getattr(chunk, 'delta', None)
                if delta:
                    full_text += delta
            elif chunk_type == 'transcript.text.done':
                text = getattr(chunk, 'text', None)
                if text:
                    full_text = text
        return full_text

    def _type_text(self, text: str):
        if not text:
            return
        try:
            import pyperclip
            import pyautogui
            pyperclip.copy(text)
            pyautogui.hotkey('ctrl', 'shift', 'v')
        except Exception as e:
            print(f"Type error: {e}")

    def start(self):
        """启动引擎，开始监听"""
        import threading
        self._running = True
        self._recording_done_event = threading.Event()
        self._listener = keyboard.Listener(
            on_press=self._on_rctrl_press,
            on_release=self._on_rctrl_release
        )
        self._listener.start()
        self.set_state(ASRState.LISTENING)

    def stop(self):
        self._running = False
        if self._listener:
            self._listener.stop()

    def process_recording_and_type(self):
        """处理录音并输入文字"""
        import time
        time.sleep(0.1)  # Wait for recording to flush
        audio_data = self._get_recorded_audio()
        if len(audio_data) == 0:
            self.set_state(ASRState.LISTENING)
            return

        wav_bytes = self._create_wav_bytes(audio_data)
        text = self._transcribe(wav_bytes)

        if text:
            self._type_text(text)
            if self._result_callback:
                self._result_callback(text)
        else:
            print("No speech detected")

        self.set_state(ASRState.LISTENING)
```

- [ ] **Step 2: 验证语法**

Run: `python3 -m py_compile asr_engine.py && echo "Syntax OK"`
Expected: Syntax OK

- [ ] **Step 3: Commit**

```bash
git add asr_engine.py
git commit -m "feat: add ASREngine class"
```

---

## Task 4: 实现主窗口 UI

**Files:**
- Create: `/home/wurong/workspace/zhipu/ui/styles.py`
- Create: `/home/wurong/workspace/zhipu/ui/main_window.py`

- [ ] **Step 1: 创建 styles.py**

```python
WINDOW_STYLE = """
QMainWindow {
    background-color: #2b2b2b;
}
QLabel {
    color: #e0e0e0;
    font-size: 14px;
}
QLineEdit {
    background-color: #3c3c3c;
    color: #e0e0e0;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 4px;
}
QPushButton {
    background-color: #0d47a1;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 6px 16px;
}
QPushButton:hover {
    background-color: #1565c0;
}
QTextEdit {
    background-color: #1e1e1e;
    color: #9e9e9e;
    border: 1px solid #333;
    font-family: monospace;
}
#status_label {
    font-size: 16px;
    font-weight: bold;
}
"""
```

- [ ] **Step 2: 创建 main_window.py**

```python
#!/usr/bin/env python3
"""主窗口 UI"""

from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor

from .styles import WINDOW_STYLE


class MainWindow(QMainWindow):
    def __init__(self, on_save_api_key=None):
        super().__init__()
        self.on_save_api_key = on_save_api_key
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Zhipu 语音输入")
        self.setMinimumSize(400, 300)
        self.setStyleSheet(WINDOW_STYLE)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # 状态标签
        self.status_label = QLabel("● 监听中")
        self.status_label.setObjectName("status_label")
        layout.addWidget(self.status_label)

        # 快捷键说明
        hotkey_label = QLabel("快捷键: 右 Ctrl 按住录音，松开识别")
        layout.addWidget(hotkey_label)

        # API Key 设置
        api_layout = QHBoxLayout()
        api_layout.addWidget(QLabel("API Key:"))
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("输入 API Key")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        api_layout.addWidget(self.api_key_input)

        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._on_save)
        api_layout.addWidget(save_btn)
        layout.addLayout(api_layout)

        # 日志区域
        log_label = QLabel("日志:")
        layout.addWidget(log_label)
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(150)
        layout.addWidget(self.log_area)

        self.update_status("listening")

    def update_status(self, status: str):
        colors = {
            "listening": "#4caf50",
            "recording": "#f44336",
            "processing": "#ff9800",
            "idle": "#9e9e9e",
        }
        texts = {
            "listening": "● 监听中",
            "recording": "● 录音中",
            "processing": "● 识别中",
            "idle": "○ 空闲",
        }
        color = colors.get(status, "#9e9e9e")
        text = texts.get(status, status)
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: bold;")

    def append_log(self, msg: str):
        self.log_area.append(msg)

    def _on_save(self):
        if self.on_save_api_key:
            key = self.api_key_input.text().strip()
            if key:
                self.on_save_api_key(key)
                self.append_log(f"[保存] API Key 已更新")
```

- [ ] **Step 3: 验证语法**

Run: `python3 -m py_compile ui/styles.py ui/main_window.py && echo "Syntax OK"`
Expected: Syntax OK

- [ ] **Step 4: Commit**

```bash
git add ui/styles.py ui/main_window.py
git commit -m "feat: add main window UI"
```

---

## Task 5: 实现系统托盘

**Files:**
- Create: `/home/wurong/workspace/zhipu/zhipu_tray.py`

- [ ] **Step 1: 编写托盘主程序**

```python
#!/usr/bin/env python3
"""
Zhipu Tray - 系统托盘 + 主窗口
Usage: python zhipu_tray.py --api-key YOUR_KEY
"""

import os
import sys
import argparse
from pathlib import Path

from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction, QPainter, QPixmap, QColor
from PySide6.QtCore import QTimer, QRect, QPropertyAnimation, QByteArray, Property, Qt
from PySide6.QtCore import QTimer

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent))

from asr_engine import ASREngine, ASRState
from ui.main_window import MainWindow


class AnimatedIcon(QIcon):
    """支持脉冲动画的图标"""
    def __init__(self, idle_path: str, recording_path: str):
        super().__init__()
        self.idle_pixmap = QPixmap(idle_path)
        self.recording_pixmap = QPixmap(recording_path)
        self._animation_progress = 0.0
        self._is_animating = False

    def _generate_pulse_pixmap(self, progress: float) -> QPixmap:
        """生成脉冲动画帧"""
        size = self.recording_pixmap.size()
        pixmap = self.recording_pixmap.copy()
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        # 脉冲效果 - 缩放透明度
        alpha = int(128 * (1.0 - progress))
        painter.fillRect(pixmap.rect(), QColor(255, 0, 0, alpha))
        painter.end()
        return pixmap

    def get_current_pixmap(self) -> QPixmap:
        if self._is_animating:
            return self._generate_pulse_pixmap(self._animation_progress)
        return self.idle_pixmap


def parse_args():
    parser = argparse.ArgumentParser(description="ZhipuAI ASR Tray")
    parser.add_argument("--api-key", "-k", type=str, help="ZhipuAI API key")
    parser.add_argument("--config", "-c", type=str, default="config.yaml", help="Config YAML path")
    return parser.parse_args()


class ZhipuTray:
    def __init__(self, api_key: str, config_path: str = "config.yaml"):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        # 加载图标
        base_dir = Path(__file__).parent
        idle_icon_path = base_dir / "assets" / "icons" / "mic_idle.svg"
        recording_icon_path = base_dir / "assets" / "icons" / "mic_recording.svg"

        self.animated_icon = AnimatedIcon(
            str(idle_icon_path),
            str(recording_icon_path)
        )

        # 创建主窗口
        self.main_window = MainWindow(on_save_api_key=self._on_save_api_key)

        # 创建系统托盘
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(self.animated_icon.idle_pixmap)
        self.tray.setToolTip("Zhipu 语音输入")
        self.tray.activated.connect(self._on_tray_activated)
        self._create_tray_menu()

        # ASR 引擎
        self.engine = ASREngine(
            api_key=api_key,
            config_path=config_path,
            state_callback=self._on_asr_state,
            result_callback=self._on_asr_result,
        )

        # 动画定时器
        self._animation_timer = QTimer()
        self._animation_timer.timeout.connect(self._update_animation)
        self._animation_progress = 0.0

        # 显示主窗口
        self.main_window.show()

    def _create_tray_menu(self):
        menu = QMenu()

        show_action = QAction("显示主窗口", self.app)
        show_action.triggered.connect(self.main_window.show)
        menu.addAction(show_action)

        menu.addSeparator()

        quit_action = QAction("退出", self.app)
        quit_action.triggered.connect(self.quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.main_window.show()

    def _on_asr_state(self, state: ASRState):
        state_map = {
            ASRState.LISTENING: "listening",
            ASRState.RECORDING: "recording",
            ASRState.PROCESSING: "processing",
            ASRState.IDLE: "idle",
        }
        status = state_map.get(state, "idle")

        self.main_window.update_status(status)
        self.main_window.append_log(f"[状态] {status}")

        if state == ASRState.RECORDING:
            self._start_animation()
            self.tray.setIcon(self.animated_icon.recording_pixmap)
        elif state == ASRState.PROCESSING:
            self._stop_animation()
            self.tray.setIcon(self.animated_icon.idle_pixmap)
        elif state == ASRState.LISTENING:
            self._stop_animation()
            self.tray.setIcon(self.animated_icon.idle_pixmap)

    def _on_asr_result(self, text: str):
        self.main_window.append_log(f"[识别] {text}")

    def _on_save_api_key(self, key: str):
        # 保存到环境变量或文件
        os.environ["ZHIPUAI_API_KEY"] = key

    def _start_animation(self):
        self._animation_progress = 0.0
        self.animated_icon._is_animating = True
        self.animated_icon._animation_progress = 0.0
        self._animation_timer.start(50)

    def _stop_animation(self):
        self._animation_timer.stop()
        self.animated_icon._is_animating = False

    def _update_animation(self):
        self._animation_progress = (self._animation_progress + 0.1) % 1.0
        self.animated_icon._animation_progress = self._animation_progress
        # 动态更新托盘图标
        self.tray.setIcon(self.animated_icon.get_current_pixmap())

    def run(self):
        self.engine.start()
        self.tray.show()
        sys.exit(self.app.exec())

    def quit(self):
        self.engine.stop()
        self.app.quit()


def main():
    args = parse_args()
    api_key = args.api_key or os.environ.get("ZHIPUAI_API_KEY")
    if not api_key:
        print("Error: API key not provided. Use --api-key or set ZHIPUAI_API_KEY")
        sys.exit(1)

    tray = ZhipuTray(api_key, config_path=args.config)
    tray.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 验证语法**

Run: `python3 -m py_compile zhipu_tray.py && echo "Syntax OK"`
Expected: Syntax OK

- [ ] **Step 3: Commit**

```bash
git add zhipu_tray.py
git commit -m "feat: add system tray application"
```

---

## Task 6: 创建桌面快捷方式

**Files:**
- Create: `/home/wurong/workspace/zhipu/zhipu.desktop`

- [ ] **Step 1: 创建 .desktop 文件**

```desktop
[Desktop Entry]
Version=1.0
Type=Application
Name=Zhipu 语音输入
Comment=Zhipu AI 语音输入法托盘应用
Exec=python3 /home/wurong/workspace/zhipu/zhipu_tray.py
Icon=/home/wurong/workspace/zhipu/assets/icons/mic_idle.svg
Terminal=false
Categories=Utility;VoiceInput;
StartupNotify=false
X-GNOME-Autostart-enabled=false
```

- [ ] **Step 2: 设置执行权限并复制到 ~/.local/share/applications/**

Run: `chmod +x zhipu.desktop && cp zhipu.desktop ~/.local/share/applications/`

- [ ] **Step 3: Commit**

```bash
git add zhipu.desktop
git commit -m "feat: add desktop entry file"
```

---

## Task 7: 端到端测试

- [ ] **Step 1: 验证所有文件存在**

Run: `ls -la zhipu_tray.py asr_engine.py ui/styles.py ui/main_window.py assets/icons/`
Expected: 所有文件存在

- [ ] **Step 2: 测试导入**

Run: `python3 -c "from asr_engine import ASREngine, ASRState; print('ASREngine OK')"`
Expected: ASREngine OK

- [ ] **Step 3: 测试 GUI 启动（headless 验证）**

Run: `timeout 3 python3 -c "from zhipu_tray import ZhipuTray; print('Tray import OK')" 2>&1 || true`
Expected: Tray import OK 或超时（正常，因为需要显示）

---

## 验证检查清单

- [ ] requirements.txt 包含所有依赖
- [ ] asr_engine.py 封装了 asr_cli.py 的核心逻辑
- [ ] 主窗口显示状态、API Key 设置、日志
- [ ] 托盘图标在录音时有动画
- [ ] 右键菜单包含显示主窗口和退出
- [ ] .desktop 文件可以创建桌面快捷方式
- [ ] 所有代码语法正确
