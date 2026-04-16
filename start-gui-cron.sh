#!/bin/bash
# cron @reboot 启动 zhipu-asr (修复 DISPLAY 和日志)

# 日志文件
LOGFILE="/home/liudf/tools/zhipu-asr/start-gui.log"
echo "=== $(date) 启动 zhipu-asr ===" >> "$LOGFILE"

# 等待用户登录并获取 DISPLAY（最长 60 秒）
for i in {1..60}; do
    # 从 who 获取当前用户的 DISPLAY
    DISPLAY_NUM=$(who | grep "liudf" | grep -oP '\(:\d+\)' | tr -d '()' | head -1)
    
    if [ -n "$DISPLAY_NUM" ]; then
        export DISPLAY="$DISPLAY_NUM"
        echo "找到 DISPLAY=$DISPLAY" >> "$LOGFILE"
        break
    fi
    sleep 1
done

if [ -z "$DISPLAY" ]; then
    echo "错误：60 秒内未检测到用户登录" >> "$LOGFILE"
    exit 1
fi

# 设置 XAUTHORITY
export XAUTHORITY="/run/user/1000/gdm/Xauthority"

# 启动程序
cd /home/liudf/tools/zhipu-asr
nohup python zhipu-asr.py >> "$LOGFILE" 2>&1 &
echo "进程已启动，PID=$!" >> "$LOGFILE"
