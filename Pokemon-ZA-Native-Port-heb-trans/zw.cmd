@echo off
chcp 65001 >nul
py -3 -I "%~dp0workbench\zw.py" %*
exit /b %errorlevel%
