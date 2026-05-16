@echo off
setlocal
cd /d "%~dp0\..\backend"
.venv\Scripts\python.exe -m app.ops.check_spark --call
