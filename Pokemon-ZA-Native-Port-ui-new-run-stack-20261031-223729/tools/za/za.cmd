@echo off
setlocal
set "ZA_SCRIPT="
for /f "delims=" %%P in ('wsl -d Ubuntu -- wslpath -a -u "%~dp0za.py"') do set "ZA_SCRIPT=%%P"
if not defined ZA_SCRIPT exit /b 2
wsl -d Ubuntu -- python3 "%ZA_SCRIPT%" %*
exit /b %errorlevel%
