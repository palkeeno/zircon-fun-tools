#!/bin/bash
# =============================================================================
# Zircon Fun Tools Bot - 停止スクリプト
# =============================================================================
# 使い方: ./scripts/stop_bot.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_FILE="$PROJECT_DIR/bot.pid"
LOG_DIR="$PROJECT_DIR/logs"

echo "=================================================="
echo "Zircon Fun Tools Bot - Stopping"
echo "=================================================="

if [ ! -f "$PID_FILE" ]; then
    echo "PID file not found. Bot may not be running."
    
    # プロセスを検索
    PIDS=$(pgrep -f "python3 main.py")
    if [ -n "$PIDS" ]; then
        echo "Found running bot processes: $PIDS"
        echo "Killing processes..."
        pkill -f "python3 main.py"
        echo "✓ Processes killed."
    else
        echo "No bot process found."
    fi
    exit 0
fi

BOT_PID=$(cat "$PID_FILE")

if ps -p "$BOT_PID" > /dev/null 2>&1; then
    echo "Stopping bot (PID: $BOT_PID)..."
    
    # まずSIGTERMを送信
    kill "$BOT_PID" 2>/dev/null
    
    # 10秒待機
    for i in {1..10}; do
        if ! ps -p "$BOT_PID" > /dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    
    # まだ動いていたらSIGKILL
    if ps -p "$BOT_PID" > /dev/null 2>&1; then
        echo "Force killing..."
        kill -9 "$BOT_PID" 2>/dev/null
    fi
    
    # 停止ログを記録
    TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")
    echo "[$TIMESTAMP] Bot stopped by user (PID: $BOT_PID)" >> "$LOG_DIR/shutdown.log"
    
    echo "✓ Bot stopped."
else
    echo "Bot process (PID: $BOT_PID) is not running."
fi

rm -f "$PID_FILE"
echo "✓ PID file removed."
