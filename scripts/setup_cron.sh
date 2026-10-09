#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' 'Bot supervision is now systemd only.' 'Stop the old watchdog process and remove the old watchdog cron entry before installing the service.' 'Use scripts/install_service.sh; status: sudo systemctl status zircon-bot.service'
exit 1
