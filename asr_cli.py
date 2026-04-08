#!/usr/bin/env python3
"""
ZhipuAI ASR Input Method - Voice input via RightCtrl
Usage: python asr_cli.py --api-key YOUR_KEY
       or: ZHIPUAI_API_KEY=xxx python asr_cli.py
"""

import io
import json
import signal
import sys
import wave
import os
import argparse
import threading
import time

import numpy as np
import sounddevice as sd
from pynput import keyboard

from zhipuai import ZhipuAI
import yaml


# Configuration
SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = 'int16'


def parse_args():
    parser = argparse.ArgumentParser(description="ZhipuAI ASR Input Method")
    parser.add_argument("--api-key", "-k", type=str, help="ZhipuAI API key")
    parser.add_argument("--debug", "-d", action="store_true", help="Enable debug output")
    parser.add_argument("--config", "-c", type=str, default="config.yaml", help="Config YAML path")
    return parser.parse_args()


def _load_config(config_path: str) -> dict:
    """Load hotwords and prompt from YAML config file."""
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class ASRInputMethod:
    def __init__(self, api_key: str, debug: bool = False, config_path: str = "config.yaml"):
        self.api_key = api_key
        if not self.api_key:
            raise ValueError("API key not provided. Use --api-key or set ZHIPUAI_API_KEY")

        self.client = ZhipuAI(api_key=self.api_key)
        self.debug = debug

        # Load config
        self.config = _load_config(config_path)
        self.hotwords = self.config.get("hotwords", [])
        self.prompt = self.config.get("prompt", "")

        self.is_recording = False
        self.recording_frames: list[np.ndarray] = []
        self.recording_lock = threading.Lock()
        self.audio_buffer = []  # Will hold recorded audio chunks

        self.running = True
        self.recording_done_event = threading.Event()
        self._processing = False
        self._q_pressed = False

        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, _signum, _frame):
        print("\n\nExiting...")
        self.running = False

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

    def _on_rctrl_press(self, key):
        """Called when RightCtrl is pressed."""
        if key == keyboard.Key.ctrl_r and not self.is_recording:
            self.is_recording = True
            self.recording_frames = []
            print("\nRecording... (release RCtrl to send)", flush=True)
            self._start_recording_thread()
        elif key == keyboard.KeyCode.from_char('q'):
            self._q_pressed = True

    def _on_rctrl_release(self, key):
        """Called when RightCtrl is released."""
        if key == keyboard.Key.ctrl_r and self.is_recording:
            self.is_recording = False
            self.recording_done_event.set()
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
                if self.debug:
                    print(f"[DEBUG] Read frames: shape={frames.shape}")
                with self.recording_lock:
                    self.recording_frames.append(frames.copy())

    def _start_recording_thread(self):
        try:
            self.recording_thread = threading.Thread(
                target=self._recording_thread_target,
                daemon=True
            )
            self.recording_thread.start()
        except Exception as e:
            print(f"Error: {e}")
            self.is_recording = False
            self.recording_done_event.set()  # Signal to allow continued operation

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
            if self.debug:
                print(f"[DEBUG] Chunk: {chunk}")
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
        """Type text into the focused window via clipboard + Ctrl+Shift+V."""
        if not text:
            print("No text to type")
            return
        try:
            import pyperclip
            import pyautogui
            pyperclip.copy(text)
            pyautogui.hotkey('ctrl', 'shift', 'v')
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

        # Start pynput keyboard listener
        listener = keyboard.Listener(
            on_press=self._on_rctrl_press,
            on_release=self._on_rctrl_release
        )
        listener.start()

        # Main loop
        while self.running:
            time.sleep(0.05)  # Sleep to prevent busy loop

            # Check if recording just stopped - process transcription in main thread
            if self.recording_done_event.is_set():
                self.recording_done_event.clear()
                self.process_recording_and_type()
                print("Listening... (press RCtrl to input)", flush=True)

            # Handle q to quit
            if self._q_pressed:
                self.running = False
                break

        # Clean up recording thread
        if hasattr(self, 'recording_thread') and self.recording_thread.is_alive():
            self.recording_thread.join(timeout=1.0)

        listener.stop()

    def process_recording_and_type(self):
        """Called after RCtrl is released to process and type."""
        self._processing = True
        try:
            audio_data = self._get_recorded_audio()
            if self.debug:
                print(f"[DEBUG] Processing {len(audio_data)} samples")
            if len(audio_data) == 0:
                print("No audio recorded")
                return

            if self.debug:
                print(f"[DEBUG] Recorded {len(audio_data)} samples")

            wav_bytes = self._create_wav_bytes(audio_data)

            if self.debug:
                import os
                import datetime
                log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "log")
                os.makedirs(log_dir, exist_ok=True)
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                wav_path = os.path.join(log_dir, f"asr_{timestamp}.wav")
                with open(wav_path, "wb") as f:
                    f.write(wav_bytes)
                print(f"[DEBUG] Saved WAV to {wav_path}")

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
        im = ASRInputMethod(api_key, debug=args.debug, config_path=args.config)
        if im.hotwords:
            print(f"Hotwords loaded: {im.hotwords}")
        if im.prompt:
            print(f"Prompt loaded: {im.prompt}")
        im.run()
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()