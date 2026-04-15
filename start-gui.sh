#!/bin/bash
# 后台启动（不占用终端）
cd "$(dirname "$0")"

LOG_FILE="$HOME/.local/share/zhipu-asr/zhipu-asr.log"
mkdir -p "$(dirname "$LOG_FILE")"

# 优先使用 conda zhipu-asr 环境
if command -v conda &>/dev/null; then
    PYTHON=$(conda run -n zhipu-asr which python 2>/dev/null)
    if [[ -z "$PYTHON" ]]; then
        echo "❌ 未找到 conda 环境 zhipu-asr，请先安装："
        echo ""
        echo "    conda create -n zhipu-asr python=3.10"
        echo "    conda activate zhipu-asr"
        echo "    pip install -r requirements.txt"
        echo ""
        exit 1
    fi
else
    PYTHON=python
fi

nohup "$PYTHON" zhipu-asr.py "$@" > "$LOG_FILE" 2>&1 &
PID=$!

# 等待一秒，检查进程是否存活
sleep 1
if ! kill -0 "$PID" 2>/dev/null; then
    echo "❌ 启动失败，查看日志：$LOG_FILE"
    tail -20 "$LOG_FILE"
    exit 1
fi

echo "✅ 已启动（PID $PID），日志：$LOG_FILE"
