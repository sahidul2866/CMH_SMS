"""Windows-native launcher tests, isolated from the real app and scheduled task.

Run with: python -m unittest discover -s scripts/tests -p 'test_windows*.py' -v
"""
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
import venv

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.name == 'nt', 'Requires Windows cmd.exe and PowerShell')
class WindowsRecoveryTests(unittest.TestCase):
    def setUp(self):
        # Exercise quoting: deployments can contain spaces and apostrophes.
        self.temp = tempfile.TemporaryDirectory(prefix="CMH server's tests ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'scripts').mkdir()
        (self.root / '.setup').mkdir()
        (self.root / '.setup/windows.env.bat').write_text('@echo off\n')
        (self.root / 'backend/.venv/Scripts').mkdir(parents=True)
        (self.root / 'backend/.venv/Scripts/python.exe').touch()
        shutil.copy(ROOT / 'START_CMH_FOREVER_WINDOWS.bat', self.root)
        shutil.copy(ROOT / 'scripts/install_source_autostart.ps1', self.root / 'scripts')

    def scheduler(self, fail_registration=False):
        # Execute the real installer, replacing only OS mutation commands. Never
        # register, enable, stop, or delete the hospital's actual scheduled task.
        wrapper = self.root / 'scheduler_test.ps1'
        wrapper.write_text(r'''
$ErrorActionPreference = 'Stop'
function New-ScheduledTaskAction { @{ arguments = @($args) } }
function New-ScheduledTaskTrigger { @{ arguments = @($args) } }
function New-ScheduledTaskPrincipal { @{ arguments = @($args) } }
function New-ScheduledTaskSettingsSet { @{ arguments = @($args) } }
function Register-ScheduledTask {
    param($TaskName, $Action, $Trigger, $Principal, $Settings, [switch]$Force)
    if ($env:CMH_TEST_FAIL -eq '1') { throw 'Simulated registration failure' }
    @{ name=$TaskName; action=$Action; triggers=$Trigger; principal=$Principal; settings=$Settings } |
        ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'task.json')
    'register' | Add-Content -LiteralPath (Join-Path $PSScriptRoot 'events.txt')
}
function Enable-ScheduledTask { 'enable' | Add-Content -LiteralPath (Join-Path $PSScriptRoot 'events.txt') }
function Start-ScheduledTask { 'start' | Add-Content -LiteralPath (Join-Path $PSScriptRoot 'events.txt') }
& (Join-Path $PSScriptRoot 'scripts\install_source_autostart.ps1')
''')
        return subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                               '-File', str(wrapper)], capture_output=True, text=True,
                              timeout=30, env={**os.environ, 'CMH_TEST_FAIL': str(int(fail_registration))})

    def test_task_has_recovery_triggers_and_prevents_duplicate_instances(self):
        result = self.scheduler()
        self.assertEqual(result.returncode, 0, result.stderr)
        task = json.loads((self.root / 'task.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(task['name'], 'CMH Smart Serial Server')
        settings = task['settings']['arguments']
        self.assertEqual(settings[settings.index('-MultipleInstances') + 1], 'IgnoreNew')
        self.assertIn('-DontStopIfGoingOnBatteries', settings)
        self.assertEqual(settings[settings.index('-ExecutionTimeLimit') + 1]['Ticks'], 0)
        triggers = task['triggers']
        self.assertIn('-AtLogOn', triggers[0]['arguments'])
        watchdog = triggers[1]['arguments']
        self.assertEqual(watchdog[watchdog.index('-RepetitionInterval') + 1]['TotalSeconds'], 60)
        self.assertNotIn('-RepetitionDuration', watchdog)
        action = task['action']['arguments']
        self.assertEqual(action[action.index('-Argument') + 1],
                         f'/d /c ""{self.root / "START_CMH_FOREVER_WINDOWS.bat"}""')
        self.assertEqual(action[action.index('-WorkingDirectory') + 1], str(self.root))
        self.assertEqual((self.root / 'events.txt').read_text().splitlines(), ['register', 'enable', 'start'])

    def test_registration_failure_does_not_enable_or_start_task(self):
        result = self.scheduler(fail_registration=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'events.txt').exists())

    def test_incomplete_installation_does_not_register_task(self):
        (self.root / '.setup/windows.env.bat').unlink()
        result = self.scheduler()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'events.txt').exists())

    def test_supervisor_exits_without_prompt_when_not_installed(self):
        (self.root / '.setup/windows.env.bat').unlink()
        result = subprocess.run(['cmd.exe', '/d', '/c', str(self.root / 'START_CMH_FOREVER_WINDOWS.bat')],
                                input='', capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 1)
        self.assertIn('not been installed', result.stdout)

    def maintenance_stop(self, fail_disable=False):
        # Execute the stop command embedded in the real BAT with mocked OS
        # mutations, ensuring a failed disable cannot proceed to stop the task.
        batch = (ROOT / 'STOP_CMH_WINDOWS.bat').read_text()
        command = re.search(r'^powershell .* -Command "(.*)"$', batch, re.MULTILINE).group(1)
        wrapper = self.root / 'stop_test.ps1'
        wrapper.write_text(r'''
function Disable-ScheduledTask {
    if ($env:CMH_TEST_FAIL -eq '1') { throw 'Simulated access denied' }
    'disable' | Add-Content -LiteralPath (Join-Path $PSScriptRoot 'stop-events.txt')
}
function Stop-ScheduledTask { 'stop' | Add-Content -LiteralPath (Join-Path $PSScriptRoot 'stop-events.txt') }
''' + command)
        return subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(wrapper)],
                              capture_output=True, text=True, timeout=15,
                              env={**os.environ, 'CMH_TEST_FAIL': str(int(fail_disable))})

    def test_maintenance_disables_recovery_before_stopping(self):
        result = self.maintenance_stop()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'stop-events.txt').read_text().splitlines(), ['disable', 'stop'])

    def test_failed_disable_does_not_stop_a_task_that_would_restart(self):
        result = self.maintenance_stop(fail_disable=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'stop-events.txt').exists())

    def test_supervisor_retries_failure_and_clean_exit_with_delay(self):
        # A disposable Python environment executes a fake app, never Uvicorn or
        # PostgreSQL. The actual batch restart loop and its 10-second delay run.
        (self.root / 'backend/.venv/Scripts/python.exe').unlink()
        venv.EnvBuilder(with_pip=False).create(self.root / 'backend/.venv')
        frontend = self.root / 'frontend/dist/cmh-smart-serial/browser'
        frontend.mkdir(parents=True)
        (frontend / 'index.html').touch()
        (self.root / 'scripts/windows_postgres.py').write_text('''
from pathlib import Path
import time
p = Path(__file__).parent / 'attempts.txt'
previous = p.read_text().splitlines() if p.exists() else []
with p.open('a') as f:
    f.write(str(time.monotonic()) + '\\n')
if len(previous) >= 2:
    time.sleep(120)
raise SystemExit(1 if not previous else 0)
''')
        with (self.root / 'server.log').open('w') as output:
            process = subprocess.Popen(['cmd.exe', '/d', '/c', str(self.root / 'START_CMH_FOREVER_WINDOWS.bat')],
                                       stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT)
            try:
                attempts = self.root / 'scripts/attempts.txt'
                deadline = time.monotonic() + 55
                times = []
                while time.monotonic() < deadline:
                    if attempts.exists():
                        times = attempts.read_text().splitlines()
                    if len(times) >= 3 or process.poll() is not None:
                        break
                    time.sleep(0.2)
                self.assertGreaterEqual(len(times), 3, 'Supervisor failed to retry both exits')
                self.assertGreaterEqual(float(times[1]) - float(times[0]), 9.5)
                self.assertGreaterEqual(float(times[2]) - float(times[1]), 9.5)
            finally:
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=15)
                process.wait(timeout=15)


if __name__ == '__main__':
    unittest.main()
