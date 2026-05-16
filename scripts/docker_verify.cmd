@echo off
setlocal
cd /d "%~dp0\.."
python scripts\verify_runtime.py
