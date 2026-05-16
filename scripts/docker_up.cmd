@echo off
setlocal
cd /d "%~dp0\..\infra"
docker compose up --build
