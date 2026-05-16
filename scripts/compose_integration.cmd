@echo off
setlocal
cd /d "%~dp0\.."
python scripts\compose_integration.py
