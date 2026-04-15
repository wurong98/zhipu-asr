# zhipu-asr

> **目前仅支持 Linux 系统**

Linux 语音输入法——基于智谱 AI GLM-ASR API，按住右 Ctrl 说话，识别结果自动输入到焦点窗口。

## 快速开始

### 1. 安装依赖

```bash
# 使用 conda（推荐）
conda create -n zhipu-asr python=3.10
conda activate zhipu-asr
pip install -r requirements.txt
```

> **注意**：需要系统已安装 `portaudio`（Ubuntu: `apt install libportaudio2`，或通过 conda 安装 `conda install portaudio`）。

### 2. 获取 API Key

前往 [智谱 AI 开放平台](https://open.bigmodel.cn/) 注册并获取 API Key。

### 3. 运行

首次运行会弹出设置界面，填入 API Key 后保存即可。

```bash
./start-gui.sh --api-key YOUR_API_KEY
```

或设置环境变量后直接运行：

```bash
export ZHIPUAI_API_KEY=your_key
./start-gui.sh
```

### 4. 使用

- **按住右 Ctrl** → 开始录音
- **松开右 Ctrl** → 停止录音，识别结果自动输入到焦点窗口

## 命令行选项

- `-k, --api-key` - 智谱 AI API Key
- `--console` - 启用调试模式（控制台输出 + 保存 WAV 文件到 `~/.local/share/zhipu-asr/debug/`）

## 配置

首次运行后，配置保存在 `~/.config/zhipu/config.yaml`。

可用配置项：

```yaml
hotwords:
  - Python
  - Linux

prompt: "用户正在讨论技术问题"
```

## 项目结构

```
zhipu-asr/
├── zhipu-asr.py      # 主入口（系统托盘 + 主窗口）
├── start-gui.sh      # 启动脚本
├── asr_engine.py     # ASR 核心引擎
├── ui/
│   ├── main_window.py # 主窗口 UI
│   └── styles.py      # 样式表
├── assets/
│   └── icons/         # 图标资源
├── config.yaml.example # 配置示例
├── requirements.txt
└── LICENSE            # MIT License
```

## 常见问题

**Q: 录音时系统任务栏不显示录音图标？**
A: 确保已安装 `libportaudio2` 或让 sounddevice 走 PulseAudio 驱动。启动脚本已自动设置 `ALSA_PLUGIN_DIR` 路由到 PulseAudio。

**Q: 提示 "PySide6 Qt platform plugin could not be initialized"？**
A: PySide6 版本过高。推荐使用 `requirements.txt` 中的 `PySide6==6.4.3`，6.5+ 需要 `libxcb-cursor0`（Ubuntu 20.04 不支持）。

**Q: 粘贴功能不工作？**
A: 依赖 `xdotool`（系统已预装），使用 PySide6 QClipboard 替代 pyperclip，无需额外剪贴板工具。

## License

MIT
