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
