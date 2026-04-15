#!/usr/bin/env python3
"""主窗口 UI"""

from PySide2.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QCheckBox
)
from PySide2.QtCore import Qt

from .styles import WINDOW_STYLE


class MainWindow(QMainWindow):
    def __init__(self, on_settings_change=None):
        super().__init__()
        self.on_settings_change = on_settings_change
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Zhipu 语音输入")
        self.setMinimumSize(450, 400)
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
        layout.addLayout(api_layout)

        # Hotwords 设置
        hotwords_layout = QHBoxLayout()
        hotwords_layout.addWidget(QLabel("Hotwords:"))
        self.hotwords_input = QLineEdit()
        self.hotwords_input.setPlaceholderText('["词1", "词2"] 或留空')
        hotwords_layout.addWidget(self.hotwords_input)
        layout.addLayout(hotwords_layout)

        # Prompt 设置
        prompt_layout = QVBoxLayout()
        prompt_layout.addWidget(QLabel("Prompt:"))
        self.prompt_input = QTextEdit()
        self.prompt_input.setPlaceholderText("提示词（可选）")
        self.prompt_input.setMaximumHeight(60)
        prompt_layout.addWidget(self.prompt_input)
        layout.addLayout(prompt_layout)

        # 启用 hotwords/prompt 复选框
        self.enable_hotwords_cb = QCheckBox("启用 Hotwords")
        self.enable_prompt_cb = QCheckBox("启用 Prompt")
        layout.addWidget(self.enable_hotwords_cb)
        layout.addWidget(self.enable_prompt_cb)

        # 保存按钮
        save_btn = QPushButton("保存设置")
        save_btn.clicked.connect(self._on_save)
        layout.addWidget(save_btn)

        # 日志区域
        log_label = QLabel("日志:")
        layout.addWidget(log_label)
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(120)
        layout.addWidget(self.log_area)

        self.update_status("listening")

    def load_settings(self, api_key: str = "", hotwords: list = None, prompt: str = ""):
        """加载设置到 UI"""
        if api_key:
            self.api_key_input.setText(api_key)
        if hotwords:
            import json
            self.hotwords_input.setText(json.dumps(hotwords, ensure_ascii=False))
        if prompt:
            self.prompt_input.setText(prompt)

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
        if self.on_settings_change:
            api_key = self.api_key_input.text().strip()

            # 解析 hotwords
            hotwords = None
            hotwords_text = self.hotwords_input.text().strip()
            if hotwords_text:
                try:
                    import json
                    hotwords = json.loads(hotwords_text)
                except json.JSONDecodeError:
                    self.append_log("[错误] Hotwords 格式错误，请使用 JSON 数组")
                    return

            # 解析 prompt
            prompt = None
            if self.enable_prompt_cb.isChecked():
                prompt = self.prompt_input.toPlainText().strip()

            # 如果没有启用 hotwords，清空它
            if not self.enable_hotwords_cb.isChecked():
                hotwords = []

            settings = {
                "api_key": api_key,
                "hotwords": hotwords if hotwords is not None else [],
                "prompt": prompt if prompt else "",
            }

            self.on_settings_change(settings)
            self.append_log(f"[保存] 设置已更新")