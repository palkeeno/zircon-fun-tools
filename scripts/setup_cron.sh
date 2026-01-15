#!/bin/bash
# =============================================================================
# Zircon Fun Tools Bot - Cron設定スクリプト
# =============================================================================
# 使い方: ./scripts/setup_cron.sh
# 
# このスクリプトは以下のcronジョブを設定します:
# 1. 5分ごとにbotの状態をチェックし、停止していれば自動再起動
# 2. 毎日午前3時に7日以上前のログファイルを自動削除
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WATCHDOG_SCRIPT="$SCRIPT_DIR/watchdog.sh"
CLEANUP_SCRIPT="$SCRIPT_DIR/cleanup_logs.sh"

echo "=================================================="
echo "Zircon Fun Tools Bot - Cron Setup"
echo "=================================================="

# スクリプトに実行権限を付与
chmod +x "$SCRIPT_DIR"/*.sh

# 既存のcronジョブを確認
EXISTING_WATCHDOG=$(crontab -l 2>/dev/null | grep -F "watchdog.sh")
EXISTING_CLEANUP=$(crontab -l 2>/dev/null | grep -F "cleanup_logs.sh")

if [ -n "$EXISTING_WATCHDOG" ] || [ -n "$EXISTING_CLEANUP" ]; then
    echo "Existing cron jobs found:"
    [ -n "$EXISTING_WATCHDOG" ] && echo "  Watchdog: $EXISTING_WATCHDOG"
    [ -n "$EXISTING_CLEANUP" ] && echo "  Cleanup: $EXISTING_CLEANUP"
    echo ""
    read -p "Replace with new cron jobs? (y/n): " REPLACE
    if [ "$REPLACE" != "y" ]; then
        echo "Cancelled."
        exit 0
    fi
    # 既存のジョブを削除
    crontab -l 2>/dev/null | grep -v -F "watchdog.sh" | grep -v -F "cleanup_logs.sh" | crontab -
fi

# 新しいcronジョブを追加
WATCHDOG_CRON="*/5 * * * * $WATCHDOG_SCRIPT --cron >> $PROJECT_DIR/logs/cron.log 2>&1"
CLEANUP_CRON="0 3 * * * $CLEANUP_SCRIPT >> $PROJECT_DIR/logs/cron.log 2>&1"

(crontab -l 2>/dev/null; echo "$WATCHDOG_CRON"; echo "$CLEANUP_CRON") | crontab -

echo ""
echo "✓ Cron jobs added:"
echo ""
echo "1. Watchdog (every 5 minutes):"
echo "   $WATCHDOG_CRON"
echo ""
echo "2. Log cleanup (daily at 3:00 AM):"
echo "   $CLEANUP_CRON"
echo ""
echo "This will:"
echo "  - Check bot status every 5 minutes"
echo "  - Automatically restart if bot is stopped"
echo "  - Delete log files older than 7 days at 3:00 AM daily"
echo "  - Log to: $PROJECT_DIR/logs/cron.log"
echo ""
echo "To view current cron jobs: crontab -l"
echo "To remove cron job: crontab -e"
