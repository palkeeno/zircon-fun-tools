#!/bin/bash
# =============================================================================
# Zircon Fun Tools Bot - 監視 & 自動再起動スクリプト（Watchdog）
# =============================================================================
# 使い方: 
#   手動実行: ./scripts/watchdog.sh
#   バックグラウンド: nohup ./scripts/watchdog.sh &
#   cron設定: */5 * * * * /path/to/scripts/watchdog.sh --cron
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_FILE="$PROJECT_DIR/bot.pid"
LOG_DIR="$PROJECT_DIR/logs"
WATCHDOG_LOG="$LOG_DIR/watchdog.log"
CRASH_LOG="$LOG_DIR/crash.log"

# ログディレクトリを作成
mkdir -p "$LOG_DIR"

# ログ出力関数
log() {
    local TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")
    echo "[$TIMESTAMP] $1" | tee -a "$WATCHDOG_LOG"
}

log_crash() {
    local TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")
    echo "[$TIMESTAMP] $1" >> "$CRASH_LOG"
}

# Botが実行中かチェック
is_bot_running() {
    if [ -f "$PID_FILE" ]; then
        BOT_PID=$(cat "$PID_FILE")
        if ps -p "$BOT_PID" > /dev/null 2>&1; then
            return 0  # Running
        fi
    fi
    
    # PIDファイルがなくてもプロセスを検索
    pgrep -f "python3 main.py" > /dev/null 2>&1
    return $?
}

# Botを再起動
restart_bot() {
    log "Restarting bot..."
    
    # 既存のプロセスをクリーンアップ
    if [ -f "$PID_FILE" ]; then
        OLD_PID=$(cat "$PID_FILE")
        if ps -p "$OLD_PID" > /dev/null 2>&1; then
            log "Killing old process: $OLD_PID"
            kill "$OLD_PID" 2>/dev/null
            sleep 2
            kill -9 "$OLD_PID" 2>/dev/null
        fi
        rm -f "$PID_FILE"
    fi
    
    # start_bot.shで起動
    "$SCRIPT_DIR/start_bot.sh"
    
    # 起動確認
    sleep 5
    if is_bot_running; then
        log "✓ Bot restarted successfully"
        return 0
    else
        log "✗ Bot restart failed"
        return 1
    fi
}

# クラッシュの原因を記録
log_crash_details() {
    log_crash "=========================================="
    log_crash "Bot crashed at $(date)"
    log_crash "=========================================="
    
    # 最新のログファイルからエラーを抽出
    LATEST_LOG=$(ls -t "$LOG_DIR"/bot_*.log 2>/dev/null | head -1)
    if [ -n "$LATEST_LOG" ]; then
        log_crash "Last 50 lines from $LATEST_LOG:"
        tail -50 "$LATEST_LOG" >> "$CRASH_LOG"
    fi
    
    log_crash ""
}

# メイン処理
main() {
    # --cronオプションで単発チェック
    if [ "$1" == "--cron" ]; then
        if ! is_bot_running; then
            log "Bot is not running (detected by cron check)"
            log_crash_details
            restart_bot
        fi
        exit 0
    fi
    
    # 通常モード: 継続的に監視
    log "=========================================="
    log "Watchdog started"
    log "Project: $PROJECT_DIR"
    log "Check interval: 30 seconds"
    log "=========================================="
    
    # 最初のチェック - botが動いていなければ起動
    if ! is_bot_running; then
        log "Bot is not running. Starting..."
        restart_bot
    else
        log "Bot is already running."
    fi
    
    # 監視ループ
    CONSECUTIVE_FAILURES=0
    MAX_FAILURES=3
    
    while true; do
        sleep 30
        
        if ! is_bot_running; then
            log "⚠ Bot is not running!"
            log_crash_details
            
            CONSECUTIVE_FAILURES=$((CONSECUTIVE_FAILURES + 1))
            
            if [ $CONSECUTIVE_FAILURES -ge $MAX_FAILURES ]; then
                log "✗ Too many consecutive restart failures ($CONSECUTIVE_FAILURES). Waiting 5 minutes..."
                sleep 300
                CONSECUTIVE_FAILURES=0
            fi
            
            restart_bot
            if [ $? -eq 0 ]; then
                CONSECUTIVE_FAILURES=0
            fi
        fi
    done
}

# 実行
main "$@"
