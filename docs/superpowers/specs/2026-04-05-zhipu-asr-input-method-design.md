# Zhipu ASR 输入法 — 设计文档

**日期:** 2026-04-05

**状态:** 已批准

---

## 目标

将现有的智谱AI ASR CLI 改造为 Linux 语音输入法：按住 **右Ctrl** 录音，松开后自动识别并打字到当前焦点窗口。

---

## 交互流程

1. 程序启动 → 显示 "Listening for RCtrl..."
2. 按住 **右Ctrl** → 开始录音，终端显示 "Recording..."
3. 说话中 → 持续录音（无实时显示）
4. 松开 **右Ctrl** → 停止录音 → 发送到 ZhipuAI ASR → 获取识别结果
5. 识别成功 → 用 `pyautogui` 自动打字到当前焦点窗口
6. 打字成功 → 终端显示 "Typed: <text>"
7. 打字失败 → 终端显示 "Error: focused window not available"
8. 按 `q` 或 `Ctrl+C` 退出程序

---

## 架构

```
┌─────────────────────────────────────────────────┐
│  Main Process                                   │
│  ├── keyboard.hook on RCtrl (按下/松开事件)      │
│  ├── 状态显示循环（每秒打印状态）                 │
│  └── 录音线程（RCtrl 按下时启动，松开时停止）     │
│                                                 │
│  松开 RCtrl 后（在主线程执行）:                  │
│  ├── 创建 WAV bytes                             │
│  ├── 调用 ZhipuAI ASR 流式识别                   │
│  └── pyautogui.typewrite(result)                │
└─────────────────────────────────────────────────┘
```

---

## 技术方案

- **按键监听:** `keyboard` 库（Linux 下可靠，支持 `keyboard.is_pressed()` 和 `on_press`/`on_release` 回调）
- **录音:** `sounddevice`（已有），在独立线程中运行
- **按键模拟:** `pyautogui`（跨平台，Linux 需要 X11）
- **ASR 调用:** 复用现有 `_transcribe_stream` 逻辑，模型仍为 `GLM-ASR-2512`

---

## 新增依赖

```
keyboard
pyautogui
```

---

## 文件变更

- `asr_cli.py` — 重构为守护模式，添加按键监听和打字逻辑
- `requirements.txt` — 新增 `keyboard`, `pyautogui`

---

## 错误处理

- 录音时 `sounddevice` 异常 → 打印错误，继续监听
- ASR 调用失败 → 打印错误，显示 "ASR failed"
- 打字失败（无焦点窗口）→ 打印 "Error: focused window not available"

---

## 测试计划

- 单元测试：WAV 转换逻辑
- 集成测试：手动测试完整流程（按住RCtrl → 说话 → 松开 → 验证文字输入）
