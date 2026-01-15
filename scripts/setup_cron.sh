#!/bin/bash
# =============================================================================
# Zircon Fun Tools Bot - Cron設定スクリプト
# =============================================================================
# 使い方: ./scripts/setup_cron.sh
# 
# このスクリプトは5分ごとにbotの状態をチェックし、
# 停止していれば自動で再起動するcronジョブを設定します
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WATCHDOG_SCRIPT="$SCRIPT_DIR/watchdog.sh"

echo "=================================================="
echo "Zircon Fun Tools Bot - Cron Setup"
echo "=================================================="

# スクリプトに実行権限を付与
chmod +x "$SCRIPT_DIR"/*.sh

# 既存のcronジョブを確認
EXISTING_CRON=$(crontab -l 2>/dev/null | grep -F "watchdog.sh")

if [ -n "$EXISTING_CRON" ]; then
    echo "Existing cron job found:"
    echo "$EXISTING_CRON"
    echo ""
    read -p "Replace with new cron job? (y/n): " REPLACE
    if [ "$REPLACE" != "y" ]; then
        echo "Cancelled."
        exit 0
    fi
    # 既存のジョブを削除
    crontab -l 2>/dev/null | grep -v -F "watchdog.sh" | crontab -
fi

# 新しいcronジョブを追加
CRON_JOB="*/5 * * * * $WATCHDOG_SCRIPT --cron >> $PROJECT_DIR/logs/cron.log 2>&1"

(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -

echo ""
echo "✓ Cron job added:"
echo "$CRON_JOB"
echo ""
echo "This will:"
echo "  - Check bot status every 5 minutes"
echo "  - Automatically restart if bot is stopped"
echo "  - Log to: $PROJECT_DIR/logs/cron.log"
echo ""
echo "To view current cron jobs: crontab -l"
echo "To remove cron job: crontab -e"
