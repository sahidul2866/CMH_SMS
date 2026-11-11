"""Run Windows shutdown logic with mocked OS calls; never stop real processes."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'stop_source_server.ps1'


@unittest.skipUnless(os.name == 'nt', 'Requires Windows PowerShell')
class StopSourceServerTests(unittest.TestCase):
    def run_scenario(self, scenario):
        temporary = tempfile.TemporaryDirectory(prefix="CMH updater's tests ")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        shutil.copy(SCRIPT, root / SCRIPT.name)
        wrapper = root / 'mock_os.ps1'
        wrapper.write_text(r'''
$ErrorActionPreference = 'Stop'
$scenario = $env:CMH_STOP_SCENARIO
$project = $PSScriptRoot
$script:live = @{101=$true; 102=$true; 103=$true; 999=$true}
function Log($value) { Add-Content -LiteralPath (Join-Path $project 'events.txt') -Value $value }
function Get-CimInstance {
    @(
        [pscustomobject]@{ProcessId=101; ParentProcessId=1; ExecutablePath='C:\Windows\cmd.exe'; CommandLine=('cmd /c "' + $project + '\START_CMH_FOREVER_WINDOWS.bat"')},
        [pscustomobject]@{ProcessId=102; ParentProcessId=101; ExecutablePath=($project + '\backend\.venv\Scripts\python.exe'); CommandLine='python -m uvicorn app.main:app'},
        [pscustomobject]@{ProcessId=103; ParentProcessId=102; ExecutablePath='C:\Python\python.exe'; CommandLine='helper'}
    )
}
function Get-NetTCPConnection {
    param($State, $LocalPort, $ErrorAction)
    $owner = if ($scenario -eq 'foreign-port') {999} else {102}
    if ($script:live[$owner]) { [pscustomobject]@{OwningProcess=$owner} }
}
function Get-ScheduledTask {
    param($TaskName, $ErrorAction)
    $folder = if ($scenario -eq 'foreign-task') {'C:\AnotherHospital'} else {$project}
    [pscustomobject]@{Actions=@([pscustomobject]@{Arguments=('/c "' + $folder + '\START_CMH_FOREVER_WINDOWS.bat"')})}
}
function Disable-ScheduledTask { param($TaskName); Log 'disable' }
function Stop-ScheduledTask { param($TaskName); Log 'stop-task' }
function Get-Process { param($Id, $ErrorAction); if ($script:live[$Id]) { [pscustomobject]@{Id=$Id} } }
function Stop-Process { param($Id, [switch]$Force, $ErrorAction); Log "stop:$Id"; $script:live[$Id]=$false }
& (Join-Path $project 'stop_source_server.ps1') -ProjectDir $project -Port 8100
exit $LASTEXITCODE
''')
        result = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(wrapper)],
                                env={**os.environ, 'CMH_STOP_SCENARIO': scenario}, capture_output=True, text=True, timeout=30)
        events_path = root / 'events.txt'
        events = events_path.read_text(encoding='utf-8-sig').splitlines() if events_path.exists() else []
        return result, events

    def test_stops_watchdog_launcher_and_children_before_update(self):
        result, events = self.run_scenario('owned')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events[:2], ['disable', 'stop-task'])
        self.assertEqual(set(events[2:]), {'stop:101', 'stop:102', 'stop:103'})
        self.assertLess(events.index('stop:101'), events.index('stop:103'))

    def test_foreign_port_is_untouched(self):
        result, events = self.run_scenario('foreign-port')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(events, [])

    def test_other_project_task_is_untouched(self):
        result, events = self.run_scenario('foreign-task')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(events, [])
