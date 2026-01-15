#!/bin/bash
# =============================================================================
# Zircon Fun Tools Bot - ステータス確認スクリプト
# =============================================================================
# 使い方: ./scripts/check_bot.sh
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_FILE="$PROJECT_DIR/bot.pid"
LOG_DIR="$PROJECT_DIR/logs"

echo "=================================================="
echo "Zircon Fun Tools Bot - Status Check"
echo "=================================================="

# PIDファイル確認
if [ -f "$PID_FILE" ]; then
    BOT_PID=$(cat "$PID_FILE")
    echo "PID File: $PID_FILE"
    echo "Recorded PID: $BOT_PID"
    
    if ps -p "$BOT_PID" > /dev/null 2>&1; then
        echo "Status: ✓ RUNNING"
        echo ""
        echo "Process Info:"
        ps -p "$BOT_PID" -o pid,ppid,%cpu,%mem,etime,cmd --no-headers
        echo ""
        
        # メモリ使用量
        MEM_KB=$(ps -p "$BOT_PID" -o rss --no-headers 2>/dev/null | tr -d ' ')
        if [ -n "$MEM_KB" ]; then
            MEM_MB=$((MEM_KB / 1024))
            echo "Memory Usage: ${MEM_MB} MB"
        fi
    else
        echo "Status: ✗ NOT RUNNING (stale PID file)"
    fi
else
    echo "PID File: Not found"
    
    # プロセスを検索
    PIDS=$(pgrep -f "python3 main.py")
    if [ -n "$PIDS" ]; then
        echo "Status: ⚠ RUNNING (without PID file)"
        echo "Found PIDs: $PIDS"
    else
        echo "Status: ✗ NOT RUNNING"
    fi
fi

# 最新のログファイル
echo ""
echo "=================================================="
echo "Recent Logs"
echo "=================================================="

if [ -d "$LOG_DIR" ]; then
    LATEST_LOG=$(ls -t "$LOG_DIR"/bot_*.log 2>/dev/null | head -1)
    if [ -n "$LATEST_LOG" ]; then
        echo "Latest log: $LATEST_LOG"
        echo ""
        echo "Last 10 lines:"
        echo "--------------------"
        tail -10 "$LATEST_LOG"
    else
        echo "No log files found."
    fi
else
    echo "Log directory not found."
fi

# エラーログの確認
echo ""
echo "=================================================="
echo "Recent Errors (last 24 hours)"
echo "=================================================="

if [ -d "$LOG_DIR" ]; then
    ERROR_COUNT=$(find "$LOG_DIR" -name "*.log" -mtime -1 -exec grep -l "ERROR\|CRITICAL" {} \; 2>/dev/null | wc -l)
    if [ "$ERROR_COUNT" -gt 0 ]; then
        echo "Found $ERROR_COUNT log file(s) with errors."
        echo ""
        echo "Recent errors:"
        find "$LOG_DIR" -name "*.log" -mtime -1 -exec grep -h "ERROR\|CRITICAL" {} \; 2>/dev/null | tail -5
    else
        echo "No errors found in recent logs."
    fi
fi

# 停止ログの確認
if [ -f "$LOG_DIR/shutdown.log" ]; then
    echo ""
    echo "=================================================="
    echo "Recent Shutdowns"
    echo "=================================================="
    tail -5 "$LOG_DIR/shutdown.log"
fi
