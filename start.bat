@echo off
chcp 65001>nul
set "PYTHONIOENCODING=utf-8"
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "[Console]::InputEncoding=[Text.UTF8Encoding]::UTF8; [Console]::OutputEncoding=[Text.UTF8Encoding]::UTF8; & '%~dp0start.ps1'"
pause
