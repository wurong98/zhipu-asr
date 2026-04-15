# Zhipu ASR Ubuntu 20.04 适配记录

## 概述

zhipu-asr 项目原本基于较新的 Python 和 PySide6 开发，为在 Ubuntu 20.04 LTS 环境下运行，进行了以下适配修改。

## 环境信息

- 操作系统：Ubuntu 20.04.6 LTS
- Python 版本：3.8.10
- 用户 DISPLAY：`:1`（非默认的 `:0`）
- 输入法框架：fcitx4

## 修改记录

### 1. PySide6 → PySide2 兼容性修改

**问题**：Ubuntu 20.04 仓库中无 PySide6，仅有 PySide2

**修改文件**：`zhipu-asr.py`

**修改内容**：
```python
# 修改前
app.exec()

# 修改后
app.exec_()
```

**原因**：PySide2 的 QApplication 使用 `exec_()` 方法，PySide6 改为 `exec()`。为保持兼容，使用下划线版本。

---

### 2. 输入方式改进：剪贴板 → 直接键盘输入

**问题**：原实现通过剪贴板 + Ctrl+Shift+V 粘贴，导致用户剪贴板内容被覆盖

**修改文件**：`asr_engine.py`

**修改前**：
```python
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
```

**修改后**：
```python
def _type_text(self, text: str):
    if not text:
        print("[警告] 识别结果为空")
        return
    try:
        from pynput.keyboard import Controller
        keyboard = Controller()
        keyboard.type(text)
    except Exception as e:
        # fallback: 用剪贴板
        print(f"[Type失败] {e}，使用剪贴板fallback")
        try:
            import pyperclip
            pyperclip.copy(text)
            print(f"[剪贴板] 已复制: {text}")
        except Exception as e2:
            print(f"[错误] 剪贴板也失败: {e2}")
```

**改进点**：
- 优先使用 pynput 直接模拟键盘输入，不污染剪贴板
- 添加空识别结果警告提示
- pynput 失败时自动 fallback 到剪贴板模式
- 多级异常捕获和详细日志

**参考**：`/home/liudf/tools/axutils/voice_input.py` 的实现模式

---

### 3. 录音时长保护机制

**问题**：无最大时长限制，用户可能忘记松开按键导致长时间录音

**修改文件**：`asr_engine.py`

**添加常量**（第 26 行）：
```python
MAX_RECORDING_DURATION = 30  # 最大录音时长（秒）
```

**修改录音开始处理**（第 135-141 行）：
```python
def _on_rctrl_press(self, key):
    if key == keyboard.Key.ctrl_r and not self._is_recording:
        self._is_recording = True
        self._recording_frames = []
        self._recording_start_time = time.time()  # 新增：记录开始时间
        self.set_state(ASRState.RECORDING)
        self._start_recording_thread()
```

**修改录音线程**（第 147-163 行）：
```python
def _recording_thread_target(self):
    self._recording_lock = threading.Lock()
    stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE)
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
```

**改进点**：
- 每 0.1s 检查录音时长
- 达到 30s 自动停止并转入处理状态
- 打印警告信息提醒用户

**参考**：`/home/liudf/tools/axutils/voice_input.py` 的 `MAX_DURATION` 设计

---

### 4. DISPLAY 环境变量自动配置

**问题**：Ubuntu 20.04 用户会话可能不在默认的 `:0`，需要手动指定 `DISPLAY=:1`

**新建文件**：`start.sh`

**内容**：
```bash
#!/bin/bash
# Zhipu ASR 启动脚本
# 自动设置 DISPLAY 环境变量

# 获取当前用户的 DISPLAY
if [ -z "$DISPLAY" ]; then
    # 尝试从 w 命令获取用户的 DISPLAY
    USER_DISPLAY=$(w -h "$USER" | awk '{print $3}' | grep -E '^:[0-9]' | head -n1)
    if [ -n "$USER_DISPLAY" ]; then
        export DISPLAY="$USER_DISPLAY"
        echo "[INFO] 自动设置 DISPLAY=$DISPLAY"
    else
        # 默认尝试 :1
        export DISPLAY=:1
        echo "[WARN] 未检测到用户 DISPLAY，使用默认值 DISPLAY=:1"
    fi
fi

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 启动应用
cd "$SCRIPT_DIR"
python3 zhipu-asr.py --console "$@"
```

**使用方法**：
```bash
cd ~/tools/zhipu-asr
./start.sh
```

**改进点**：
- 自动检测用户实际 DISPLAY 值（通过 `w` 命令）
- 未检测到时 fallback 到 `:1`
- 支持传递命令行参数（如 `--console`）
- 无需手动设置环境变量

---

## 依赖说明

所有依赖均已在 Ubuntu 20.04 下验证可用：

```bash
pip3 install PySide2 pynput sounddevice pyautogui zhipuai pyperclip pyyaml
```

**关键依赖版本兼容性**：
- PySide2：Ubuntu 20.04 官方支持
- pynput：用于键盘模拟和监听
- sounddevice：音频录制
- zhipuai：智谱 AI SDK

---

## 测试验证

**测试环境**：
- 系统：Ubuntu 20.04.6 LTS
- Python：3.8.10
- DISPLAY：`:1`

**测试项目**：
- [x] 应用启动正常
- [x] 系统托盘图标显示
- [x] 按住 Right Ctrl 录音
- [x] 松开后识别并直接输入文字
- [x] 中文输入正常（pynput 模式）
- [x] 剪贴板内容不受影响
- [x] 空识别结果有警告提示
- [x] 30s 自动停止录音
- [x] start.sh 自动检测 DISPLAY

---

## 已知限制

1. **pynput 中文兼容性**：部分中文字符可能无法通过 pynput 输入，此时会自动 fallback 到剪贴板模式
2. **输入法框架**：在 fcitx4 环境下测试通过，ibus 环境未验证
3. **DISPLAY 检测**：仅支持本地 X11 会话，Wayland 会话可能需要手动设置

---

## 后续改进建议

1. 打包成 AppImage/deb，简化安装流程
2. 添加桌面快捷方式自动创建脚本
3. 支持自定义录音热键（当前固定 Right Ctrl）
4. 添加 systemd 用户服务配置，支持开机自启

---

**修改时间**：2025-04-15  
**修改人**：liudf  
**参考项目**：/home/liudf/tools/axutils/voice_input.py
