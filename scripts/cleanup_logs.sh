#!/bin/bash
# =============================================================================
# Zircon Fun Tools Bot - ログクリーンアップスクリプト
# =============================================================================
# 使い方: ./scripts/cleanup_logs.sh [days]
# 
# デフォルトで7日以上前のログファイルを削除します。
# 引数で日数を指定できます: ./scripts/cleanup_logs.sh 14  (14日以上前を削除)
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs"

# 保持日数（デフォルト: 7日）
RETENTION_DAYS="${1:-7}"

# ログ出力関数
log() {
    local TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")
    echo "[$TIMESTAMP] [CLEANUP] $1"
}

log "=========================================="
log "Log cleanup started"
log "Retention: ${RETENTION_DAYS} days"
log "Log directory: $LOG_DIR"
log "=========================================="

# ログディレクトリが存在するか確認
if [ ! -d "$LOG_DIR" ]; then
    log "Log directory does not exist: $LOG_DIR"
    exit 0
fi

# 削除対象ファイルをカウント
DELETED_COUNT=0
DELETED_SIZE=0

# Botログファイル (bot_*.log)
while IFS= read -r -d '' file; do
    if [ -f "$file" ]; then
        FILE_SIZE=$(stat -f%z "$file" 2>/dev/null || stat -c%s "$file" 2>/dev/null || echo 0)
        DELETED_SIZE=$((DELETED_SIZE + FILE_SIZE))
        rm -f "$file"
        log "Deleted: $(basename "$file") (${FILE_SIZE} bytes)"
        DELETED_COUNT=$((DELETED_COUNT + 1))
    fi
done < <(find "$LOG_DIR" -name "bot_*.log" -type f -mtime +${RETENTION_DAYS} -print0 2>/dev/null)

# Cronログファイル (cron.log) - 古い内容を切り詰め
CRON_LOG="$LOG_DIR/cron.log"
if [ -f "$CRON_LOG" ]; then
    CRON_SIZE=$(stat -f%z "$CRON_LOG" 2>/dev/null || stat -c%s "$CRON_LOG" 2>/dev/null || echo 0)
    # 10MB以上なら最新1000行を残して切り詰め
    if [ "$CRON_SIZE" -gt 10485760 ]; then
        tail -1000 "$CRON_LOG" > "$CRON_LOG.tmp"
        mv "$CRON_LOG.tmp" "$CRON_LOG"
        log "Truncated cron.log (was ${CRON_SIZE} bytes)"
    fi
fi

# Watchdogログファイル (watchdog.log) - 古い内容を切り詰め
WATCHDOG_LOG="$LOG_DIR/watchdog.log"
if [ -f "$WATCHDOG_LOG" ]; then
    WD_SIZE=$(stat -f%z "$WATCHDOG_LOG" 2>/dev/null || stat -c%s "$WATCHDOG_LOG" 2>/dev/null || echo 0)
    # 5MB以上なら最新500行を残して切り詰め
    if [ "$WD_SIZE" -gt 5242880 ]; then
        tail -500 "$WATCHDOG_LOG" > "$WATCHDOG_LOG.tmp"
        mv "$WATCHDOG_LOG.tmp" "$WATCHDOG_LOG"
        log "Truncated watchdog.log (was ${WD_SIZE} bytes)"
    fi
fi

# Crashログファイル (crash.log) - 古い内容を切り詰め
CRASH_LOG="$LOG_DIR/crash.log"
if [ -f "$CRASH_LOG" ]; then
    CRASH_SIZE=$(stat -f%z "$CRASH_LOG" 2>/dev/null || stat -c%s "$CRASH_LOG" 2>/dev/null || echo 0)
    # 5MB以上なら最新1000行を残して切り詰め
    if [ "$CRASH_SIZE" -gt 5242880 ]; then
        tail -1000 "$CRASH_LOG" > "$CRASH_LOG.tmp"
        mv "$CRASH_LOG.tmp" "$CRASH_LOG"
        log "Truncated crash.log (was ${CRASH_SIZE} bytes)"
    fi
fi

# 空のログファイルを削除（README.md以外）
while IFS= read -r -d '' file; do
    if [ -f "$file" ] && [ "$(basename "$file")" != "README.md" ]; then
        rm -f "$file"
        log "Deleted empty file: $(basename "$file")"
        DELETED_COUNT=$((DELETED_COUNT + 1))
    fi
done < <(find "$LOG_DIR" -type f -empty -print0 2>/dev/null)

# サマリー
log "=========================================="
log "Cleanup completed"
log "Deleted files: ${DELETED_COUNT}"
log "Freed space: ${DELETED_SIZE} bytes"
log "=========================================="
