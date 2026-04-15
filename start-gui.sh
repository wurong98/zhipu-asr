#!/bin/bash
# 后台启动（不占用终端）
cd "$(dirname "$0")"

# ALSA PulseAudio 插件路径（让 sounddevice 走 PulseAudio，使用系统默认麦克风并显示录音指示）
export ALSA_PLUGIN_DIR=/usr/lib/x86_64-linux-gnu/alsa-lib

LOG_FILE="$HOME/.local/share/zhipu-asr/zhipu-asr.log"
mkdir -p "$(dirname "$LOG_FILE")"

# 调试模式：不后台运行，直接输出到终端
DEBUG_MODE=false
if [[ "$*" == *"--debug"* ]]; then
    DEBUG_MODE=true
    # 将 --debug 转为 --console 给 zhipu-asr.py
    ARGS="${@/--debug/--console}"
else
    ARGS="$@"
fi

# 优先使用 conda zhipu-asr 环境
if command -v conda &>/dev/null; then
    # 用 conda run 直接执行，确保环境正确加载
    if ! conda run -n zhipu-asr python -c "import sys; sys.exit(0)" 2>/dev/null; then
        echo "❌ 未找到 conda 环境 zhipu-asr，请先安装："
        echo ""
        echo "    conda create -n zhipu-asr python=3.10"
        echo "    conda activate zhipu-asr"
        echo "    pip install -r requirements.txt"
        echo ""
        exit 1
    fi

    if $DEBUG_MODE; then
        conda run -n zhipu-asr python zhipu-asr.py $ARGS
    else
        conda run -n zhipu-asr python zhipu-asr.py $ARGS > "$LOG_FILE" 2>&1 &
        PID=$!
        # 等待一秒，检查进程是否存活
        sleep 1
        if ! kill -0 "$PID" 2>/dev/null; then
            echo "❌ 启动失败，查看日志：$LOG_FILE"
            tail -20 "$LOG_FILE"
            exit 1
        fi
        echo "✅ 已启动（PID $PID），日志：$LOG_FILE"
    fi
else
    if $DEBUG_MODE; then
        python zhipu-asr.py $ARGS
    else
        python zhipu-asr.py $ARGS > "$LOG_FILE" 2>&1 &
        PID=$!
        # 等待一秒，检查进程是否存活
        sleep 1
        if ! kill -0 "$PID" 2>/dev/null; then
            echo "❌ 启动失败，查看日志：$LOG_FILE"
            tail -20 "$LOG_FILE"
            exit 1
        fi
        echo "✅ 已启动（PID $PID），日志：$LOG_FILE"
    fi
fi
