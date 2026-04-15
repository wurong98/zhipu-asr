#!/usr/bin/env python3
"""
ASR Engine - 封装 asr_cli.py 的核心逻辑
"""

import io
import json
import signal
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

        signal.signal(signal.SIGINT, self._signal_handler)

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
        self._recording_lock = threading.Lock()
        stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE)
        with stream:
            while self._is_recording and self._running:
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
            import pyperclip
            import pyautogui
            pyperclip.copy(text)
            pyautogui.hotkey('ctrl', 'shift', 'v')
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
        text = self._transcribe(wav_bytes)

        if text:
            self._type_text(text)
            if self._result_callback:
                self._result_callback(text)
        else:
            print("No speech detected")

        self.set_state(ASRState.LISTENING)
