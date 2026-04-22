#!/usr/bin/env python3
"""
ASR Engine - 封装 asr_cli.py 的核心逻辑
"""

import io
import json
import signal
import sys
import subprocess
import wave
import threading
import time
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
MAX_RECORDING_DURATION = 30  # 最大录音时长（秒）


class ASRState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    RECORDING = "recording"
    PROCESSING = "processing"


class ASREngine:
    def __init__(
        self,
        api_key: str,
        config_path: str = None,
        debug: bool = False,
        state_callback: Optional[Callable[[ASRState], None]] = None,
        result_callback: Optional[Callable[[str], None]] = None,
    ):
        import os
        if config_path is None:
            config_path = os.path.expanduser("~/.config/zhipu/config.yaml")

        self._config_path = config_path

        # 先尝试从配置文件加载，如果文件存在且有 api_key，就使用它
        saved_config = self._load_config(config_path)

        # 优先使用传入的 api_key，其次使用保存的
        self.api_key = api_key or saved_config.get("api_key", "")

        self.client = ZhipuAI(api_key=self.api_key) if self.api_key else None
        self.debug = debug
        self.hotwords = saved_config.get("hotwords", [])
        self.prompt = saved_config.get("prompt", "")

        self.state = ASRState.IDLE
        self._state_callback = state_callback
        self._result_callback = result_callback

        self._is_recording = False
        self._recording_frames: list[np.ndarray] = []
        self._recording_lock = None
        self._running = False
        self._recording_done_event = None
        self._listener = None
        self._target_window = None  # 录音前记录目标窗口

        signal.signal(signal.SIGINT, self._signal_handler)

    # 终端窗口检测逻辑，可被单元测试
    TERMINAL_INDICATORS = ['terminal', 'konsole', 'xterm', 'gnome-terminal',
                          'alacritty', 'tilix', 'terminator', 'kitty', 'putty',
                          'rxvt', 'urxvt', 'xfce4-terminal', 'mate-terminal']

    # VSCode 等编辑器内嵌终端的检测
    TERMINAL_IN_WINDOW_NAME = ['terminal', 'bash', 'zsh', 'powershell', 'cmd', 'python']

    def _is_terminal_window(self, window_name: str, window_class: str) -> bool:
        """检测窗口是否是终端（支持前缀匹配）"""
        window_name_lower = window_name.lower()
        window_class_lower = window_class.lower()

        for ind in self.TERMINAL_INDICATORS:
            # 支持子串匹配和前缀匹配
            if ind in window_class_lower or ind in window_name_lower:
                return True
            # 处理 gnome-terminal-server 这类带后缀的情况
            if window_name_lower.startswith(ind) or window_class_lower.startswith(ind):
                return True

        # VSCode/编辑器内嵌终端：窗口类是 code/edit 等，但窗口名包含终端关键词
        if 'code' in window_class_lower or 'code' in window_name_lower:
            for term in self.TERMINAL_IN_WINDOW_NAME:
                if term in window_name_lower:
                    return True

        return False

    def _load_config(self, config_path: str) -> dict:
        import os
        if not os.path.exists(config_path):
            return {}
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def update_config(self, api_key: str = None, hotwords: list = None, prompt: str = None):
        """更新配置并保存到文件"""
        if api_key is not None:
            self.api_key = api_key
            self.client = ZhipuAI(api_key=self.api_key)
        if hotwords is not None:
            self.hotwords = hotwords
        if prompt is not None:
            self.prompt = prompt

        # 保存到配置文件
        import os
        config_path = os.path.expanduser("~/.config/zhipu/config.yaml")
        os.makedirs(os.path.dirname(config_path), exist_ok=True)

        config = {
            "api_key": self.api_key,
            "hotwords": self.hotwords,
            "prompt": self.prompt,
        }
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True)

    @staticmethod
    def load_saved_config() -> dict:
        """加载保存的配置"""
        import os
        config_path = os.path.expanduser("~/.config/zhipu/config.yaml")
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

    def _save_debug_wav(self, wav_bytes: bytes):
        """debug 模式下保存 WAV 文件"""
        import os
        from datetime import datetime
        log_dir = os.path.expanduser("~/.local/share/zhipu-asr/debug")
        os.makedirs(log_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(log_dir, f"{ts}.wav")
        with open(path, "wb") as f:
            f.write(wav_bytes)
        print(f"[debug] WAV saved: {path} ({len(wav_bytes)} bytes)")

    def _get_target_window(self) -> Optional[int]:
        """获取当前活动窗口 ID"""
        try:
            result = subprocess.run(
                ['xdotool', 'getactivewindow'],
                capture_output=True, text=True, check=True
            )
            return int(result.stdout.strip())
        except Exception:
            return None

    def _on_rctrl_press(self, key):
        if key == keyboard.Key.ctrl_r and not self._is_recording:
            # 记录目标窗口（粘贴时需要切回）
            self._target_window = self._get_target_window()
            print(f"[DEBUG] Recording started, target_window: {self._target_window}", file=sys.__stdout__, flush=True)
            self._is_recording = True
            self._recording_frames = []
            self._recording_start_time = time.time()  # 记录开始时间
            self.set_state(ASRState.RECORDING)
            self._start_recording_thread()

    def _on_rctrl_release(self, key):
        if key == keyboard.Key.ctrl_r and self._is_recording:
            self._is_recording = False
            self.set_state(ASRState.PROCESSING)

    def _find_valid_input_device(self):
        # On Linux, sounddevice often fails to see PulseAudio default devices
        # because it tries to lock ALSA hw devices exclusively.
        if sys.platform.startswith('linux'):
            try:
                # We'll use a special string to indicate 'arecord' fallback
                # if the arecord command is available
                subprocess.run(['which', 'arecord'], capture_output=True, check=True)
                print("[Audio] Using system default via 'arecord' fallback for Linux", file=sys.__stdout__, flush=True)
                return "arecord"
            except Exception:
                pass
            
        try:
            # First try the default device
            sd.check_input_settings(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE)
            print(f"[Audio] Using default input device", file=sys.__stdout__, flush=True)
            return None # None means use default
        except Exception:
            pass
        
        # If default fails, search for a working input device
        devices = sd.query_devices()
        for i, device in enumerate(devices):
            if device['max_input_channels'] > 0:
                try:
                    sd.check_input_settings(device=i, samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE)
                    print(f"[Audio] Selected input device {i}: {device['name']}", file=sys.__stdout__, flush=True)
                    print(f"        Info: {device}", file=sys.__stdout__, flush=True)
                    return i
                except Exception:
                    continue
        print("[Audio] Warning: No valid input device found for 16kHz, falling back to default", file=sys.__stdout__, flush=True)
        return None

    def _recording_thread_target(self):
        self._recording_lock = threading.Lock()
        
        device_id = self._find_valid_input_device()
        
        if device_id == "arecord":
            # Use arecord as a subprocess
            cmd = [
                'arecord',
                '-f', 'S16_LE',
                '-c', str(CHANNELS),
                '-r', str(SAMPLE_RATE),
                '-t', 'raw',
                '-q'  # quiet mode
            ]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                # 0.1 seconds * 16000 samples/sec * 2 bytes/sample (int16) * 1 channel
                chunk_bytes = int(SAMPLE_RATE * 0.1 * 2 * CHANNELS)
                while self._is_recording and self._running:
                    elapsed = time.time() - self._recording_start_time
                    if elapsed >= MAX_RECORDING_DURATION:
                        print(f"[警告] 录音已达 {MAX_RECORDING_DURATION}s 上限，自动停止")
                        self._is_recording = False
                        self.set_state(ASRState.PROCESSING)
                        break

                    data = process.stdout.read(chunk_bytes)
                    if not data:
                        break
                    
                    # Convert to numpy array with the shape expected by sounddevice (frames, channels)
                    frames = np.frombuffer(data, dtype=np.int16).reshape(-1, CHANNELS)
                    with self._recording_lock:
                        self._recording_frames.append(frames.copy())
            finally:
                process.terminate()
                process.wait()
        else:
            stream = sd.InputStream(device=device_id, samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE)
            
            with stream:
                while self._is_recording and self._running:
                    # 检查录音时长
                    elapsed = time.time() - self._recording_start_time
                    if elapsed >= MAX_RECORDING_DURATION:
                        print(f"[警告] 录音已达 {MAX_RECORDING_DURATION}s 上限，自动停止")
                        self._is_recording = False
                        self.set_state(ASRState.PROCESSING)
                        break

                    frames, _ = stream.read(int(SAMPLE_RATE * 0.1))
                    with self._recording_lock:
                        self._recording_frames.append(frames.copy())

    def _start_recording_thread(self):
        t = threading.Thread(target=self._recording_thread_target, daemon=True)
        t.start()

    def _get_recorded_audio(self) -> np.ndarray:
        if self._recording_lock is None:
            return np.array([], dtype=DTYPE)
        with self._recording_lock:
            if not self._recording_frames:
                return np.array([], dtype=DTYPE)
            return np.concatenate(self._recording_frames)

    def _transcribe(self, wav_bytes: bytes) -> str:
        if not self.client:
            raise ValueError("API key 未设置，请在设置界面填写 API Key")
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
            import re
            def debug_log(msg):
                print(msg, file=sys.__stdout__, flush=True)

            # 自动检测窗口类型，选择正确的粘贴方式
            use_typeInstead = False
            if self._target_window:
                try:
                    name_result = subprocess.run(
                        ['xdotool', 'getwindowname', str(self._target_window)],
                        capture_output=True, text=True, check=False
                    )
                    window_name = name_result.stdout.lower().strip() if name_result.returncode == 0 else ""

                    class_result = subprocess.run(
                        ['xprop', '-id', str(self._target_window), 'WM_CLASS'],
                        capture_output=True, text=True, check=False
                    )
                    raw_class = class_result.stdout.strip() if class_result.returncode == 0 else ""
                    match = re.search(r'"([^"]+)"', raw_class)
                    window_class = match.group(1).lower() if match else raw_class.lower()

                    is_terminal = self._is_terminal_window(window_name, window_class)

                    # 终端和VSCode都使用 xdotool type 直接输入文本（更可靠）
                    if is_terminal or 'code' in window_class:
                        use_typeInstead = True

                    debug_log(f"[DEBUG] window_name: '{window_name}'")
                    debug_log(f"[DEBUG] window_class: '{window_class}', raw: '{raw_class}'")
                    debug_log(f"[DEBUG] is_terminal: {is_terminal}")
                    debug_log(f"[DEBUG] use_typeInstead: {use_typeInstead}")
                except Exception as e:
                    debug_log(f"[DEBUG] Exception: {e}")

            # 切回目标窗口并等待焦点稳定
            if self._target_window:
                subprocess.run(
                    ['xdotool', 'windowfocus', str(self._target_window)],
                    check=False
                )
                time.sleep(0.15)

            # 释放残留修饰符
            subprocess.run(['xdotool', 'keyup', 'ctrl', 'shift', 'alt'], check=False)

            if use_typeInstead:
                # GNOME Terminal: 使用 xdotool type 直接输入文本（避免 Ctrl+Shift+V 问题）
                subprocess.run(
                    ['xdotool', 'type', '--clearmodifiers', '--', text],
                    check=False
                )
            else:
                # 其他程序: 使用剪贴板粘贴
                from PySide6.QtWidgets import QApplication
                from PySide6.QtGui import QGuiApplication
                app = QApplication.instance()
                if app is None:
                    app = QApplication([])
                clipboard = QGuiApplication.clipboard()

                paste_key = "ctrl+v"
                if self._target_window:
                    try:
                        name_result = subprocess.run(
                            ['xdotool', 'getwindowname', str(self._target_window)],
                            capture_output=True, text=True, check=False
                        )
                        window_name = name_result.stdout.lower().strip() if name_result.returncode == 0 else ""

                        class_result = subprocess.run(
                            ['xprop', '-id', str(self._target_window), 'WM_CLASS'],
                            capture_output=True, text=True, check=False
                        )
                        raw_class = class_result.stdout.strip() if class_result.returncode == 0 else ""
                        match = re.search(r'"([^"]+)"', raw_class)
                        window_class = match.group(1).lower() if match else raw_class.lower()

                        if self._is_terminal_window(window_name, window_class):
                            paste_key = "ctrl+shift+v"
                    except:
                        pass

                clipboard.setText(text)
                time.sleep(0.05)
                subprocess.run(["xdotool", "key", paste_key], check=True)
        except Exception as e:
            print(f"Type error: {e}")

    def start(self):
        """启动引擎，开始监听"""
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
        time.sleep(0.1)  # Wait for recording to flush
        audio_data = self._get_recorded_audio()
        if len(audio_data) == 0:
            self.set_state(ASRState.LISTENING)
            return

        wav_bytes = self._create_wav_bytes(audio_data)

        if self.debug:
            self._save_debug_wav(wav_bytes)

        text = self._transcribe(wav_bytes)

        if text:
            self._type_text(text)
            if self._result_callback:
                self._result_callback(text)
        else:
            print("No speech detected")

        self.set_state(ASRState.LISTENING)
