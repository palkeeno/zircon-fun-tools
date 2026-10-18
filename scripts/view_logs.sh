#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "-f" ]]; then
    exec sudo journalctl -u zircon-bot.service -f
fi
exec sudo journalctl -u zircon-bot.service -n 100 --no-pager
