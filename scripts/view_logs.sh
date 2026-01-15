#!/bin/bash
# =============================================================================
# Zircon Fun Tools Bot - ログ閲覧スクリプト
# =============================================================================
# 使い方: 
#   ./scripts/view_logs.sh           # 最新のbotログを表示
#   ./scripts/view_logs.sh crash     # クラッシュログを表示
#   ./scripts/view_logs.sh watchdog  # 監視ログを表示
#   ./scripts/view_logs.sh all       # 全てのログファイル一覧
#   ./scripts/view_logs.sh -f        # 最新ログをリアルタイム表示
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"

show_help() {
    echo "Usage: $0 [option]"
    echo ""
    echo "Options:"
    echo "  (none)     Show latest bot log (last 50 lines)"
    echo "  -f         Follow latest bot log in real-time"
    echo "  crash      Show crash log"
    echo "  watchdog   Show watchdog log"
    echo "  shutdown   Show shutdown log"
    echo "  cron       Show cron log"
    echo "  all        List all log files"
    echo "  clean      Clean old logs (older than 7 days)"
    echo ""
}

if [ ! -d "$LOG_DIR" ]; then
    echo "Log directory not found: $LOG_DIR"
    exit 1
fi

case "$1" in
    "")
        LATEST_LOG=$(ls -t "$LOG_DIR"/bot_*.log 2>/dev/null | head -1)
        if [ -n "$LATEST_LOG" ]; then
            echo "=== Latest Bot Log: $LATEST_LOG ==="
            echo ""
            tail -50 "$LATEST_LOG"
        else
            echo "No bot logs found."
        fi
        ;;
    "-f")
        LATEST_LOG=$(ls -t "$LOG_DIR"/bot_*.log 2>/dev/null | head -1)
        if [ -n "$LATEST_LOG" ]; then
            echo "=== Following: $LATEST_LOG ==="
            echo "Press Ctrl+C to stop"
            echo ""
            tail -f "$LATEST_LOG"
        else
            echo "No bot logs found."
        fi
        ;;
    "crash")
        if [ -f "$LOG_DIR/crash.log" ]; then
            echo "=== Crash Log ==="
            cat "$LOG_DIR/crash.log"
        else
            echo "No crash log found."
        fi
        ;;
    "watchdog")
        if [ -f "$LOG_DIR/watchdog.log" ]; then
            echo "=== Watchdog Log ==="
            tail -100 "$LOG_DIR/watchdog.log"
        else
            echo "No watchdog log found."
        fi
        ;;
    "shutdown")
        if [ -f "$LOG_DIR/shutdown.log" ]; then
            echo "=== Shutdown Log ==="
            cat "$LOG_DIR/shutdown.log"
        else
            echo "No shutdown log found."
        fi
        ;;
    "cron")
        if [ -f "$LOG_DIR/cron.log" ]; then
            echo "=== Cron Log ==="
            tail -100 "$LOG_DIR/cron.log"
        else
            echo "No cron log found."
        fi
        ;;
    "all")
        echo "=== All Log Files ==="
        echo ""
        ls -lh "$LOG_DIR"/*.log 2>/dev/null || echo "No log files found."
        echo ""
        echo "Total disk usage:"
        du -sh "$LOG_DIR" 2>/dev/null
        ;;
    "clean")
        echo "Running log cleanup script..."
        "$SCRIPT_DIR/cleanup_logs.sh"
        ;;
    *)
        show_help
        ;;
esac
