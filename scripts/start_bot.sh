#!/bin/bash
# =============================================================================
# Zircon Fun Tools Bot - 起動スクリプト
# =============================================================================
# 使い方: ./scripts/start_bot.sh
# このスクリプトはbotをnohupで起動し、PIDを記録します
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"
PID_FILE="$PROJECT_DIR/bot.pid"

# ログディレクトリを作成
mkdir -p "$LOG_DIR"

# 現在の日時を取得
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/bot_${TIMESTAMP}.log"

# 既存のプロセスを確認
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "Bot is already running (PID: $OLD_PID)"
        echo "Use ./scripts/stop_bot.sh to stop it first."
        exit 1
    else
        echo "Stale PID file found. Removing..."
        rm -f "$PID_FILE"
    fi
fi

# 作業ディレクトリに移動
cd "$PROJECT_DIR"

echo "=================================================="
echo "Zircon Fun Tools Bot - Starting"
echo "=================================================="
echo "Project: $PROJECT_DIR"
echo "Log: $LOG_FILE"
echo ""

# nohupでbotを起動
nohup python3 main.py >> "$LOG_FILE" 2>&1 &
BOT_PID=$!

# PIDを保存
echo $BOT_PID > "$PID_FILE"

# 起動確認（3秒待機）
sleep 3

if ps -p "$BOT_PID" > /dev/null 2>&1; then
    echo "✓ Bot started successfully!"
    echo "  PID: $BOT_PID"
    echo "  Log: $LOG_FILE"
    echo ""
    echo "To stop: ./scripts/stop_bot.sh"
    echo "To check status: ./scripts/check_bot.sh"
    echo "To view logs: tail -f $LOG_FILE"
else
    echo "✗ Bot failed to start!"
    echo "Check logs: $LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi
