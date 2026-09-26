@echo off
setlocal EnableExtensions
schtasks /Change /TN "CMH Smart Serial Server" /DISABLE >nul 2>&1
schtasks /End /TN "CMH Smart Serial Server" >nul 2>&1
schtasks /Delete /TN "CMH Smart Serial Server" /F >nul 2>&1
echo CMH Smart Serial automatic startup was removed. Application data was not deleted.
pause
