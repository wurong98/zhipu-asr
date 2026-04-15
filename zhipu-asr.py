#!/usr/bin/env python3
"""
Zhipu ASR - Linux 语音输入法
Usage: python zhipu-asr.py --api-key YOUR_KEY
"""

import os
import sys
import argparse
from pathlib import Path

from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction, QPainter, QPixmap, QColor
from PySide6.QtCore import QTimer

# PyInstaller 兼容：获取资源目录
def get_base_dir():
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # PyInstaller 打包后的路径
        return Path(sys._MEIPASS)
    return Path(__file__).parent

# 添加项目根目录到 path
sys.path.insert(0, str(get_base_dir()))

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
        alpha = int(128 * (1.0 - progress))
        painter.fillRect(pixmap.rect(), QColor(255, 0, 0, alpha))
        painter.end()
        return pixmap

    def get_current_pixmap(self) -> QPixmap:
        if self._is_animating:
            return self._generate_pulse_pixmap(self._animation_progress)
        return self.idle_pixmap


def parse_args():
    parser = argparse.ArgumentParser(description="ZhipuAI ASR")
    parser.add_argument("--api-key", "-k", type=str, help="ZhipuAI API key")
    parser.add_argument("--console", action="store_true", default=False,
                        help="显示控制台输出（默认无控制台）")
    return parser.parse_args()


def setup_console(console_mode: bool):
    """配置控制台输出模式"""
    if not console_mode:
        # 静默模式：重定向到 devnull
        sys.stdout = open(os.devnull, 'w')
        sys.stderr = open(os.devnull, 'w')
    else:
        # 恢复标准输出
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__


class ZhipuTray:
    def __init__(self, api_key: str = None):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        # 加载图标
        base_dir = get_base_dir()
        idle_icon_path = base_dir / "assets" / "icons" / "mic_idle.png"
        recording_icon_path = base_dir / "assets" / "icons" / "mic_recording.png"

        self.animated_icon = AnimatedIcon(
            str(idle_icon_path),
            str(recording_icon_path)
        )

        # 加载已保存的配置
        self._saved_config = ASREngine.load_saved_config()

        # 优先使用命令行参数，其次使用保存的配置
        final_api_key = api_key or self._saved_config.get("api_key", "")

        # 创建主窗口
        self.main_window = MainWindow(on_settings_change=self._on_settings_change)

        if not final_api_key:
            self.main_window.append_log("[提示] 请在上方填写 API Key 并点击保存")

        # 加载设置到 UI
        self.main_window.load_settings(
            api_key=final_api_key,
            hotwords=self._saved_config.get("hotwords", []),
            prompt=self._saved_config.get("prompt", "")
        )

        # 创建系统托盘
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(QIcon(self.animated_icon.idle_pixmap))
        self.tray.setToolTip("Zhipu 语音输入")
        self.tray.activated.connect(self._on_tray_activated)
        self._create_tray_menu()

        # ASR 引擎
        self.engine = ASREngine(
            api_key=final_api_key or "",
            state_callback=None,
            result_callback=self._on_asr_result,
        )

        # 状态轮询定时器
        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._poll_engine_state)
        self._poll_timer.start(100)

        # 动画定时器
        self._animation_timer = QTimer()
        self._animation_timer.timeout.connect(self._update_animation)
        self._animation_progress = 0.0

        # 上一次的状态
        self._last_engine_state = None
        self._processing_called = False

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

    def _poll_engine_state(self):
        """主线程轮询引擎状态"""
        state = self.engine.state

        if state == self._last_engine_state:
            return

        self._last_engine_state = state

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
            self.tray.setIcon(QIcon(self.animated_icon.recording_pixmap))
            self._processing_called = False
        elif state == ASRState.PROCESSING:
            self._stop_animation()
            self.tray.setIcon(QIcon(self.animated_icon.idle_pixmap))
            if not self._processing_called:
                self._processing_called = True
                self.engine.process_recording_and_type()
        elif state == ASRState.LISTENING:
            self._stop_animation()
            self.tray.setIcon(QIcon(self.animated_icon.idle_pixmap))

    def _on_asr_result(self, text: str):
        self.main_window.append_log(f"[识别] {text}")

    def _on_settings_change(self, settings: dict):
        """保存设置并更新引擎"""
        self.engine.update_config(
            api_key=settings.get("api_key"),
            hotwords=settings.get("hotwords", []),
            prompt=settings.get("prompt", "")
        )
        self.main_window.append_log("[设置] 已保存，下次录音生效")

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
        self.tray.setIcon(QIcon(self.animated_icon.get_current_pixmap()))

    def run(self):
        self.engine.start()
        self.tray.show()
        sys.exit(self.app.exec())

    def quit(self):
        self.engine.stop()
        self.app.quit()


def main():
    args = parse_args()

    # 控制台模式设置（默认无控制台）
    setup_console(args.console)

    api_key = args.api_key or os.environ.get("ZHIPUAI_API_KEY")
    tray = ZhipuTray(api_key=api_key)
    tray.run()


if __name__ == "__main__":
    main()