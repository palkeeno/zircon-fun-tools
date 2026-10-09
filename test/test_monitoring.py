import test
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class MonitoringTests(unittest.TestCase):
    def bash(self):
        if os.name == 'nt':
            path = Path('C:/Program Files/Git/bin/bash.exe')
            return str(path) if path.exists() else None
        return shutil.which('bash')

    def test_installer_renders_unit_and_prepares_fonts_without_live_system_calls(self):
        bash = self.bash()
        if not bash:
            self.skipTest('Bash unavailable')
        source = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'bot space%name'
            (root / '.venv/bin').mkdir(parents=True)
            (root / 'scripts').mkdir()
            fake = root / 'fake-bin'
            fake.mkdir()
            for name in ['install_service.sh', 'zircon-bot.service']:
                shutil.copy2(source / 'scripts' / name, root / 'scripts' / name)
            python = str(Path(sys.executable)).replace('\\', '/')
            runner = root / '.venv/bin/python'
            runner.write_text(f'#!/usr/bin/env bash\nexec "{python}" "$@"\n', encoding='utf-8')
            runner.chmod(0o755)
            (root / 'setup_fonts.py').write_text("print('fonts prepared')", encoding='utf-8')
            sudo = fake / 'sudo'
            sudo.write_text('''#!/usr/bin/env bash
if [[ "$1" == install ]]; then cp "$4" rendered.service; else echo "$*" >> calls.log; fi
''', encoding='utf-8')
            sudo.chmod(0o755)
            cron = fake / 'crontab'
            cron.write_text('#!/usr/bin/env bash\nexit 0\n', encoding='utf-8')
            cron.chmod(0o755)
            environment = os.environ.copy()
            environment['PATH'] = str(fake) + os.pathsep + environment['PATH']
            environment['SERVICE_USER'] = environment.get('USER', 'root')
            # Git Bash USER is a Windows name; id without explicit user is authoritative there.
            identifier = fake / 'id'
            identifier.write_text('#!/usr/bin/env bash\necho 1000\n', encoding='utf-8')
            identifier.chmod(0o755)
            prefix = '$(cygpath -u "$1")' if os.name == 'nt' else '$1'
            command = [bash, '-c', f'export PATH="{prefix}:$PATH"; exec bash scripts/install_service.sh', 'fixture', str(fake)]
            result = subprocess.run(command, cwd=root, env=environment, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            unit = (root / 'rendered.service').read_text()
            self.assertNotIn('@PROJECT_DIR@', unit)
            self.assertIn('User=1000', unit)
            self.assertIn('bot space%%name', unit)
            self.assertIn('Restart=on-failure', unit)
            self.assertIn('/.venv/bin/python', unit)
            self.assertIn('systemctl enable --now zircon-bot.service', (root / 'calls.log').read_text())
            self.assertIn(b'fonts prepared', result.stdout)
            # Legacy PID prevents installation and service start.
            (root / 'calls.log').unlink()
            (root / 'bot.pid').write_text('123')
            result = subprocess.run(command, cwd=root, env=environment, capture_output=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / 'calls.log').exists())

    def test_service_restart_limits_and_old_supervisors_disabled(self):
        root = Path(__file__).resolve().parent.parent
        unit = (root / 'scripts/zircon-bot.service').read_text()
        self.assertIn('StartLimitBurst=5', unit.split('[Service]')[0])
        for name in ['watchdog.sh', 'setup_cron.sh']:
            content = (root / 'scripts' / name).read_text()
            self.assertIn('exit 1', content)
            self.assertNotIn('nohup', content)
            self.assertNotIn('crontab -', content)
