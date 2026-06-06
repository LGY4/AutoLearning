# ╔══════════════════════════════════════════════════════════════╗
# ║  AutoLearning — Windows 服务器部署脚本                       ║
# ║  适用于：腾讯云宝塔 Windows 面板                             ║
# ║  无需 Docker、无需 WSL、无需 PostgreSQL、无需 Redis           ║
# ╚══════════════════════════════════════════════════════════════╝

$ErrorActionPreference = "Stop"
$PROJECT_DIR = "C:\AutoLearning"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  AutoLearning Windows 部署" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# ── 1. 检查 Python ──────────────────────────────────────────────
Write-Host "[1/6] 检查 Python..." -ForegroundColor Yellow
$python = $null
foreach ($p in @("python", "python3", "py")) {
    try {
        $ver = & $p --version 2>&1
        if ($ver -match "Python 3\.(1[0-9]|[2-9][0-9])") {
            $python = $p
            Write-Host "  ✅ $ver" -ForegroundColor Green
            break
        }
    } catch {}
}
if (-not $python) {
    Write-Host "  ❌ 需要 Python 3.10+" -ForegroundColor Red
    Write-Host "  下载安装: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "  安装时勾选 'Add Python to PATH'" -ForegroundColor Yellow
    exit 1
}

# ── 2. 检查 Node.js ─────────────────────────────────────────────
Write-Host "[2/6] 检查 Node.js..." -ForegroundColor Yellow
try {
    $nodeVer = & node --version 2>&1
    Write-Host "  ✅ Node.js $nodeVer" -ForegroundColor Green
} catch {
    Write-Host "  ❌ 需要 Node.js 18+" -ForegroundColor Red
    Write-Host "  下载安装: https://nodejs.org/" -ForegroundColor Yellow
    exit 1
}

# ── 3. 克隆或更新项目 ──────────────────────────────────────────
Write-Host "[3/6] 准备项目代码..." -ForegroundColor Yellow
if (Test-Path "$PROJECT_DIR\.git") {
    Set-Location $PROJECT_DIR
    git pull origin main 2>&1 | Out-Null
    Write-Host "  ✅ 代码已更新" -ForegroundColor Green
} else {
    if (Test-Path $PROJECT_DIR) {
        Write-Host "  ⚠️  目录已存在但不是 git 仓库，将使用现有代码" -ForegroundColor Yellow
    } else {
        git clone https://github.com/LGY4/AutoLearning.git $PROJECT_DIR 2>&1 | Out-Null
        Write-Host "  ✅ 项目已克隆" -ForegroundColor Green
    }
}
Set-Location $PROJECT_DIR

# ── 4. 配置环境变量 ─────────────────────────────────────────────
Write-Host "[4/6] 配置环境变量..." -ForegroundColor Yellow
$envFile = "$PROJECT_DIR\backend\.env"
if (-not (Test-Path $envFile)) {
    Copy-Item "$PROJECT_DIR\.env.example" $envFile
    Write-Host "  ⚠️  请编辑 $envFile 填入 LLM_API_KEY" -ForegroundColor Yellow
    Write-Host "  按回车继续（稍后编辑）..." -ForegroundColor Gray
    Read-Host
} else {
    Write-Host "  ✅ .env 已存在" -ForegroundColor Green
}

# 设置为内存模式（无需 PostgreSQL 和 Redis）
$envContent = Get-Content $envFile -Raw
if ($envContent -notmatch "REPOSITORY_BACKEND=memory") {
    $envContent = $envContent -replace "REPOSITORY_BACKEND=.*", "REPOSITORY_BACKEND=memory"
    $envContent = $envContent -replace "RAG_BACKEND=.*", "RAG_BACKEND=memory"
    Set-Content $envFile $envContent
    Write-Host "  ✅ 已设置为内存模式（无需数据库）" -ForegroundColor Green
}

# ── 5. 安装后端依赖 ─────────────────────────────────────────────
Write-Host "[5/6] 安装后端依赖..." -ForegroundColor Yellow
Set-Location "$PROJECT_DIR\backend"

if (-not (Test-Path ".venv")) {
    & $python -m venv .venv
    Write-Host "  虚拟环境已创建" -ForegroundColor Gray
}

& .\.venv\Scripts\pip.exe install -q -r requirements.txt 2>&1 | Out-Null
Write-Host "  ✅ 后端依赖已安装" -ForegroundColor Green

# ── 6. 安装前端依赖 ─────────────────────────────────────────────
Write-Host "[6/6] 安装前端依赖..." -ForegroundColor Yellow
Set-Location "$PROJECT_DIR\frontend"
npm install --silent 2>&1 | Out-Null
Write-Host "  ✅ 前端依赖已安装" -ForegroundColor Green

# ── 创建启动脚本 ────────────────────────────────────────────────
Write-Host "" -ForegroundColor White
Write-Host "创建启动脚本..." -ForegroundColor Yellow

# 后端启动脚本
$backendScript = @"
@echo off
title AutoLearning Backend
cd /d "$PROJECT_DIR\backend"
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
"@
Set-Content "$PROJECT_DIR\start-backend.bat" $backendScript

# 前端启动脚本
$frontendScript = @"
@echo off
title AutoLearning Frontend
cd /d "$PROJECT_DIR\frontend"
npx vite --host 0.0.0.0 --port 5173
pause
"@
Set-Content "$PROJECT_DIR\start-frontend.bat" $frontendScript

# 一键启动脚本
$startAllScript = @"
@echo off
title AutoLearning - 启动中...
echo ==========================================
echo   AutoLearning 一键启动
echo ==========================================
echo.

echo [1/2] 启动后端...
start "Backend" cmd /c "$PROJECT_DIR\start-backend.bat"
timeout /t 8 /nobreak >nul

echo [2/2] 启动前端...
start "Frontend" cmd /c "$PROJECT_DIR\start-frontend.bat"
timeout /t 5 /nobreak >nul

echo.
echo ==========================================
echo   ✅ 启动完成
echo ==========================================
echo   前端: http://localhost:5173
echo   后端: http://localhost:8000/docs
echo   健康: http://localhost:8000/health
echo.
echo   关闭: 关闭 Backend 和 Frontend 窗口
echo ==========================================
pause
"@
Set-Content "$PROJECT_DIR\start-all.bat" $startAllScript

Write-Host "  ✅ 启动脚本已创建" -ForegroundColor Green

# ── 完成 ─────────────────────────────────────────────────────────
Write-Host "" -ForegroundColor White
Write-Host "==========================================" -ForegroundColor Green
Write-Host "  ✅ 部署完成" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host "" -ForegroundColor White
Write-Host "  项目位置: $PROJECT_DIR" -ForegroundColor White
Write-Host "" -ForegroundColor White
Write-Host "  启动方式（任选一种）:" -ForegroundColor White
Write-Host "    1. 双击 start-all.bat" -ForegroundColor White
Write-Host "    2. 分别双击 start-backend.bat 和 start-frontend.bat" -ForegroundColor White
Write-Host "" -ForegroundColor White
Write-Host "  访问地址:" -ForegroundColor White
Write-Host "    前端: http://localhost:5173" -ForegroundColor Cyan
Write-Host "    后端: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "" -ForegroundColor White
Write-Host "  ⚠️  记得在宝塔防火墙放行端口 5173 和 8000" -ForegroundColor Yellow
Write-Host "  ⚠️  记得在腾讯云安全组放行端口 5173 和 8000" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Cyan
