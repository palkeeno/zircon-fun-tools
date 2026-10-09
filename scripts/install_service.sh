#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_USER="${SERVICE_USER:-${SUDO_USER:-$USER}}"
test -x "$PROJECT_DIR/.venv/bin/python" || { echo 'Create .venv and install requirements first.'; exit 1; }
# A legacy PID or watchdog is a migration prerequisite, never kill a guessed process.
if [[ -f "$PROJECT_DIR/bot.pid" ]]; then
    echo 'A legacy bot.pid exists. Verify and stop the old Bot/watchdog, then remove its stale PID file before installation.'
    exit 1
fi
if crontab -l 2>/dev/null | grep -F "$PROJECT_DIR/scripts/watchdog.sh" >/dev/null; then
    echo 'Remove this project’s old watchdog cron entry before installation.'
    exit 1
fi
"$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/setup_fonts.py" --prepare
UNIT_TEMP="$(mktemp)"
trap 'rm -f "$UNIT_TEMP"' EXIT
SERVICE_UID="$(id -u "$SERVICE_USER")"
"$PROJECT_DIR/.venv/bin/python" - "$SCRIPT_DIR/zircon-bot.service" "$PROJECT_DIR" "$SERVICE_UID" "$UNIT_TEMP" <<'PY'
import pathlib, sys
template, project, user, output = sys.argv[1:]
if '\n' in project or '\r' in project:
    raise ValueError('Unsupported project path')
# WorkingDirectory is a literal path, not a shell-quoted argument list. Interior
# spaces are preserved; only unit specifier '%' needs doubling here.
working_directory = project.replace('%', '%%')
executable_directory = project.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
unit = (pathlib.Path(template).read_text()
        .replace('@WORKING_DIRECTORY@', working_directory)
        .replace('@PROJECT_DIR@', executable_directory)
        .replace('@SERVICE_USER@', user))
pathlib.Path(output).write_text(unit)
PY
sudo install -m 644 "$UNIT_TEMP" /etc/systemd/system/zircon-bot.service
sudo systemctl daemon-reload
sudo systemctl enable zircon-bot.service
sudo systemctl restart zircon-bot.service
