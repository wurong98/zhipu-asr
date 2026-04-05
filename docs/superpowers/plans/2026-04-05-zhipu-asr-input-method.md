# Zhipu ASR 输入法实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 ASR CLI 改造为按住右Ctrl语音输入法

**Architecture:** 主进程监听按键事件，按住时在独立线程录音，松开后主线程执行 ASR 识别并用 pyautogui 自动打字

**Tech Stack:** Python 3, sounddevice, keyboard, pyautogui, zhipuai SDK

---

## 文件结构

```
/home/wurong/workspace/zhipu/
├── asr_cli.py              # 重构：添加按键监听和打字逻辑
├── requirements.txt        # 新增 keyboard, pyautogui
└── docs/superpowers/plans/2026-04-05-zhipu-asr-input-method.md  # 本计划
```

---

## Task 1: 更新依赖

**Files:**
- Modify: `/home/wurong/workspace/zhipu/requirements.txt`

- [ ] **Step 1: 更新 requirements.txt**

```txt
sounddevice
numpy
keyboard
pyautogui
```

- [ ] **Step 2: 安装依赖**

Run: `pip install -r requirements.txt`

- [ ] **Step 3: 验证导入**

Run: `python3 -c "import keyboard, pyautogui; print('Dependencies OK')"`
Expected: Dependencies OK

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "feat: add keyboard and pyautogui dependencies"
```

---

## Task 2: 重构 asr_cli.py — 基础结构

**Files:**
- Modify: `/home/wurong/workspace/zhipu/asr_cli.py`（完整重写）

- [ ] **Step 1: 编写完整实现**

```python
#!/usr/bin/env python3
"""
ZhipuAI ASR Input Method - Voice input via RightCtrl
Usage: python asr_cli.py --api-key YOUR_KEY
       or: ZHIPUAI_API_KEY=xxx python asr_cli.py
"""

import io
import signal
import sys
import wave
import os
import argparse
import threading
import time

import numpy as np
import sounddevice as sd
import keyboard
import pyautogui

from zhipuai import ZhipuAI


# Configuration
SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = 'int16'
RCTRL_KEY = 'right ctrl'


def parse_args():
    parser = argparse.ArgumentParser(description="ZhipuAI ASR Input Method")
    parser.add_argument("--api-key", "-k", type=str, help="ZhipuAI API key")
    parser.add_argument("--debug", "-d", action="store_true", help="Enable debug output")
    return parser.parse_args()


class ASRInputMethod:
    def __init__(self, api_key: str, debug: bool = False):
        self.api_key = api_key
        if not self.api_key:
            raise ValueError("API key not provided. Use --api-key or set ZHIPUAI_API_KEY")

        self.client = ZhipuAI(api_key=self.api_key)
        self.debug = debug

        self.is_recording = False
        self.recording_frames: list[np.ndarray] = []
        self.recording_lock = threading.Lock()
        self.audio_buffer = []  # Will hold recorded audio chunks

        self.running = True

        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, _signum, _frame):
        print("\n\nExiting...")
        self.running = False
        sys.exit(0)

    def _create_wav_bytes(self, audio_data: np.ndarray) -> bytes:
        """Convert numpy audio array to WAV bytes."""
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_data.tobytes())
        buffer.seek(0)
        return buffer.read()

    def _on_rctrl_press(self, event):
        """Called when RightCtrl is pressed."""
        if event.name == RCTRL_KEY and not self.is_recording:
            self.is_recording = True
            self.recording_frames = []
            print("\nRecording... (release RCtrl to send)", flush=True)
            self._start_recording_thread()

    def _on_rctrl_release(self, event):
        """Called when RightCtrl is released."""
        if event.name == RCTRL_KEY and self.is_recording:
            self.is_recording = False
            print("\nProcessing...", flush=True)
            # Transcription runs in main thread after recording stops

    def _recording_thread_target(self):
        """Records audio in a loop while is_recording is True."""
        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE
        )
        with stream:
            while self.is_recording and self.running:
                frames, _ = stream.read(int(SAMPLE_RATE * 0.1))  # Read 100ms chunks
                with self.recording_lock:
                    self.recording_frames.append(frames.copy())

    def _start_recording_thread(self):
        self.recording_thread = threading.Thread(
            target=self._recording_thread_target,
            daemon=True
        )
        self.recording_thread.start()

    def _get_recorded_audio(self) -> np.ndarray:
        """Get all recorded frames as a single numpy array."""
        with self.recording_lock:
            if not self.recording_frames:
                return np.array([], dtype=DTYPE)
            return np.concatenate(self.recording_frames)

    def _transcribe(self, wav_bytes: bytes) -> str:
        """Send audio to ASR and return transcription."""
        if self.debug:
            print(f"[DEBUG] Request: wav_bytes={len(wav_bytes)} bytes")

        response = self.client.audio.transcriptions.create(
            file=("audio.wav", wav_bytes, "audio/wav"),
            model="GLM-ASR-2512",
            stream=True
        )

        full_text = ""
        for chunk in response:
            if self.debug:
                print(f"[DEBUG] Chunk: {chunk}")
            if hasattr(chunk, 'choices') and chunk.choices:
                delta = chunk.choices[0].delta
                if hasattr(delta, 'content') and delta.content:
                    full_text += delta.content
        return full_text

    def _type_text(self, text: str):
        """Type text into the focused window."""
        if not text:
            print("No text to type")
            return
        try:
            pyautogui.typewrite(text, interval=0.01)
            print(f"Typed: {text}")
        except Exception as e:
            print(f"Error: {e}")

    def run(self):
        """Main loop: listen for RCtrl key events."""
        print("ZhipuAI ASR Input Method")
        print(f"Sample rate: {SAMPLE_RATE}Hz, Channels: {CHANNELS}")
        print(f"Press and hold RightCtrl to record, release to input")
        print("Press 'q' to quit")
        print("-" * 50)

        # Register key hooks
        keyboard.on_press(self._on_rctrl_press)
        keyboard.on_release(self._on_rctrl_release)

        # Status display loop
        last_status_time = 0
        while self.running:
            time.sleep(0.05)  # Sleep to prevent busy loop

            # Check if recording just stopped - process transcription in main thread
            # This is signaled by is_recording becoming False
            if hasattr(self, '_processing') and self._processing:
                continue

            # Handle q to quit
            if keyboard.is_pressed('q'):
                self.running = False
                break

        keyboard.unhook_all()

    def process_recording_and_type(self):
        """Called after RCtrl is released to process and type."""
        self._processing = True
        try:
            audio_data = self._get_recorded_audio()
            if len(audio_data) == 0:
                print("No audio recorded")
                return

            if self.debug:
                print(f"[DEBUG] Recorded {len(audio_data)} samples")

            wav_bytes = self._create_wav_bytes(audio_data)
            text = self._transcribe(wav_bytes)
            if text:
                self._type_text(text)
            else:
                print("No speech detected")
        finally:
            self._processing = False


def main():
    args = parse_args()
    api_key = args.api_key or os.environ.get("ZHIPUAI_API_KEY")
    try:
        im = ASRInputMethod(api_key, debug=args.debug)
        im.run()
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 基本语法检查**

Run: `python3 -m py_compile asr_cli.py && echo "Syntax OK"`
Expected: Syntax OK

- [ ] **Step 3: 验证 --help 输出**

Run: `python3 asr_cli.py --help`
Expected: help message showing --api-key and --debug options

- [ ] **Step 4: Commit**

```bash
git add asr_cli.py
git commit -m "feat: refactor ASR CLI to voice input method with RCtrl"
```

---

## Task 3: 修复录音/识别流程 — 打通按下/松开的完整流程

**Files:**
- Modify: `/home/wurong/workspace/zhipu/asr_cli.py`

当前实现中，`_on_rctrl_release` 设置 `is_recording = False` 后没有触发识别流程。需要修复这个逻辑。

- [ ] **Step 1: 修改 asr_cli.py — 使用 shared flag + 主循环轮询**

删除 `_processing` 复杂逻辑，改用事件驱动：

```python
import queue

class ASRInputMethod:
    def __init__(self, api_key: str, debug: bool = False):
        # ... existing init ...
        self.recording_done_event = threading.Event()
        self.recording_lock = threading.Lock()
        self.recording_frames = []
        self.is_recording = False
        self.running = True
        # ...
```

在 `_on_rctrl_release` 中：

```python
def _on_rctrl_release(self, event):
    """Called when RightCtrl is released."""
    if event.name == RCTRL_KEY and self.is_recording:
        self.is_recording = False
        self.recording_done_event.set()  # Signal main thread
```

在 `run()` 主循环中：

```python
def run(self):
    # ... setup ...
    while self.running:
        time.sleep(0.05)
        if keyboard.is_pressed('q'):
            self.running = False
            break

        # Check if recording just finished
        if self.recording_done_event.is_set():
            self.recording_done_event.clear()
            self.process_recording_and_type()
            print("Listening... (press RCtrl to input)", flush=True)

    keyboard.unhook_all()

def process_recording_and_type(self):
    """Process recorded audio and type result."""
    audio_data = self._get_recorded_audio()
    if len(audio_data) == 0:
        print("No audio recorded")
        return

    wav_bytes = self._create_wav_bytes(audio_data)
    text = self._transcribe(wav_bytes)
    if text:
        self._type_text(text)
    else:
        print("No speech detected")
```

- [ ] **Step 2: 验证语法**

Run: `python3 -m py_compile asr_cli.py && echo "Syntax OK"`

- [ ] **Step 3: Commit**

```bash
git add asr_cli.py
git commit -m "fix: connect recording done event to transcription flow"
```

---

## Task 4: 调试模式优化

**Files:**
- Modify: `/home/wurong/workspace/zhipu/asr_cli.py`

- [ ] **Step 1: 添加 debug 模式下更详细的日志**

在 `_recording_thread_target` 中，当 `self.debug` 时打印每次读取的 chunk 信息。

在 `process_and_type` 开始时打印 `[DEBUG] Processing X samples`。

- [ ] **Step 2: Commit**

```bash
git add asr_cli.py
git commit -m "debug: add debug output for recording and transcription"
```

---

## Task 5: 端到端手动测试

- [ ] **Step 1: 安装依赖并测试**

Run: `pip install -r requirements.txt`

- [ ] **Step 2: 在文本编辑器中启动**

Run: `ZHIPUAI_API_KEY=your_key python3 asr_cli.py`

- [ ] **Step 3: 验证**
1. 终端显示 "Listening..."
2. 按住右Ctrl → 显示 "Recording..."
3. 说话后松开右Ctrl → 显示 "Processing..."
4. 文字自动输入到文本编辑器中
5. 如果没有焦点窗口 → 显示 "Error: focused window not available"

---

## 验证检查清单

- [ ] `python3 asr_cli.py --help` 正常显示帮助
- [ ] 按住右Ctrl开始录音，松开停止录音
- [ ] 松开后在主线程完成 ASR 调用
- [ ] 识别结果通过 pyautogui.typewrite 输入到焦点窗口
- [ ] 无焦点窗口时打印错误信息
- [ ] `q` 键或 `Ctrl+C` 正常退出
- [ ] debug 模式下有详细日志
