# ╔══════════════════════════════════════════════════════════════╗
# ║  AutoLearning — 一键启动脚本 (Windows PowerShell)            ║
# ╚══════════════════════════════════════════════════════════════╝
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  AutoLearning 一键启动" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. 检查 .env
if (-not (Test-Path ".env")) {
    Write-Host "[1/5] 未检测到 .env，从模板创建..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "  ⚠️  请编辑 .env 填入 LLM_API_KEY 后重新运行" -ForegroundColor Yellow
    Write-Host "  文件位置: $PWD\.env"
    exit 1
}
Write-Host "[1/5] .env 已就绪" -ForegroundColor Green

# 2. 检查 Docker
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "❌ 未安装 Docker。请先安装 Docker Desktop" -ForegroundColor Red
    exit 1
}
Write-Host "[2/5] Docker 已就绪" -ForegroundColor Green

# 3. 启动基础设施
Write-Host "[3/5] 启动 PostgreSQL + Redis..." -ForegroundColor Cyan
Set-Location infra
docker compose up -d postgres redis
Write-Host "  等待数据库就绪..."
Start-Sleep -Seconds 5

# 等待 PostgreSQL
for ($i = 0; $i -lt 30; $i++) {
    $ready = docker compose exec -T postgres pg_isready -U autolearning 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✅ PostgreSQL 就绪" -ForegroundColor Green
        break
    }
    Start-Sleep -Seconds 1
}

# 4. 启动后端
Write-Host "[4/5] 启动后端..." -ForegroundColor Cyan
Set-Location ../backend

if (-not (Test-Path ".venv")) {
    python -m venv .venv
    Write-Host "  虚拟环境已创建"
}

& .\.venv\Scripts\Activate.ps1
pip install -q -r requirements.txt

$backendJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    & .\.venv\Scripts\python.exe -m app.ops.start_api
}
Write-Host "  后端 Job ID: $($backendJob.Id)"

# 等待后端就绪
for ($i = 0; $i -lt 60; $i++) {
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 2
        if ($health.status -eq "ok") {
            Write-Host "  ✅ 后端就绪" -ForegroundColor Green
            break
        }
    } catch {}
    Start-Sleep -Seconds 1
}

# 5. 启动前端
Write-Host "[5/5] 启动前端..." -ForegroundColor Cyan
Set-Location ../frontend

if (-not (Test-Path "node_modules")) {
    npm install
    Write-Host "  前端依赖已安装"
}

$frontendJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    & npx vite --port 5173
}
Write-Host "  前端 Job ID: $($frontendJob.Id)"

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "  ✅ AutoLearning 已启动" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host "  前端: http://localhost:5173" -ForegroundColor White
Write-Host "  后端: http://localhost:8000/docs" -ForegroundColor White
Write-Host "  健康: http://localhost:8000/health" -ForegroundColor White
Write-Host ""
Write-Host "  按 Ctrl+C 停止所有服务" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Cyan

# 等待
try {
    Wait-Job -Job $backendJob, $frontendJob
} finally {
    Stop-Job -Job $backendJob, $frontendJob -ErrorAction SilentlyContinue
    Remove-Job -Job $backendJob, $frontendJob -Force -ErrorAction SilentlyContinue
    Set-Location $PSScriptRoot/infra
    docker compose down
}
