@echo off
REM DuoBeiBei local dev launcher (Windows entry point)
REM Bypass PowerShell execution policy and call scripts/dev.ps1; %* forwards args like -Install
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0scripts\dev.ps1" %* || pause
