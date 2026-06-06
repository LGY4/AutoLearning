$ErrorActionPreference = "Stop"
$PROJECT_DIR = "C:\AutoLearning"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  AutoLearning Windows 部署" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. 检查 Python
Write-Host "[1/6] 检查 Python..." -ForegroundColor Yellow
$python = $null
foreach ($p in @("python", "python3", "py")) {
    try {
        $ver = & $p --version 2>&1
        if ($ver -match "Python 3\.(1[0-9]|[2-9][0-9])") {
            $python = $p
            Write-Host "  OK $ver" -ForegroundColor Green
            break
        }
    } catch {}
}
if (-not $python) {
    Write-Host "  FAIL: 需要 Python 3.10+" -ForegroundColor Red
    Write-Host "  下载: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

# 2. 检查 Node.js
Write-Host "[2/6] 检查 Node.js..." -ForegroundColor Yellow
try {
    $nodeVer = & node --version 2>&1
    Write-Host "  OK Node.js $nodeVer" -ForegroundColor Green
} catch {
    Write-Host "  FAIL: 需要 Node.js 18+" -ForegroundColor Red
    Write-Host "  下载: https://nodejs.org/" -ForegroundColor Yellow
    exit 1
}

# 3. 下载项目代码
Write-Host "[3/6] 准备项目代码..." -ForegroundColor Yellow
if (Test-Path "$PROJECT_DIR\backend\app\main.py") {
    Write-Host "  OK 项目代码已存在" -ForegroundColor Green
} else {
    Write-Host "  下载项目 ZIP..." -ForegroundColor Gray
    $zipUrl = "https://github.com/LGY4/AutoLearning/archive/refs/heads/main.zip"
    $zipFile = "$env:TEMP\autolearning.zip"
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipFile -UseBasicParsing
    Expand-Archive -Path $zipFile -DestinationPath $env:TEMP -Force
    if (Test-Path $PROJECT_DIR) { Remove-Item $PROJECT_DIR -Recurse -Force }
    Move-Item "$env:TEMP\AutoLearning-main" $PROJECT_DIR
    Remove-Item $zipFile -Force
    Write-Host "  OK 项目已下载" -ForegroundColor Green
}
Set-Location $PROJECT_DIR

# 4. 配置环境变量
Write-Host "[4/6] 配置环境变量..." -ForegroundColor Yellow
$envFile = "$PROJECT_DIR\backend\.env"
if (-not (Test-Path $envFile)) {
    Copy-Item "$PROJECT_DIR\.env.example" $envFile
    Write-Host "  请编辑 $envFile 填入 LLM_API_KEY" -ForegroundColor Yellow
    Write-Host "  按回车继续..." -ForegroundColor Gray
    Read-Host
}
# 设置为内存模式
(Get-Content $envFile) -replace "REPOSITORY_BACKEND=.*", "REPOSITORY_BACKEND=memory" -replace "RAG_BACKEND=.*", "RAG_BACKEND=memory" | Set-Content $envFile
Write-Host "  OK 已配置为内存模式" -ForegroundColor Green

# 5. 安装后端依赖
Write-Host "[5/6] 安装后端依赖..." -ForegroundColor Yellow
Set-Location "$PROJECT_DIR\backend"
if (-not (Test-Path ".venv")) {
    & $python -m venv .venv
}
& .\.venv\Scripts\pip.exe install -q -r requirements.txt 2>&1 | Out-Null
Write-Host "  OK 后端依赖已安装" -ForegroundColor Green

# 6. 安装前端依赖
Write-Host "[6/6] 安装前端依赖..." -ForegroundColor Yellow
Set-Location "$PROJECT_DIR\frontend"
npm install --silent 2>&1 | Out-Null
Write-Host "  OK 前端依赖已安装" -ForegroundColor Green

# 创建启动脚本
Write-Host "" -ForegroundColor White
Write-Host "创建启动脚本..." -ForegroundColor Yellow

Set-Content "$PROJECT_DIR\start-backend.bat" "@echo off`r`ntitle AutoLearning Backend`r`ncd /d `"$PROJECT_DIR\backend`"`r`n.\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000`r`npause"

Set-Content "$PROJECT_DIR\start-frontend.bat" "@echo off`r`ntitle AutoLearning Frontend`r`ncd /d `"$PROJECT_DIR\frontend`"`r`nnpx vite --host 0.0.0.0 --port 5173`r`npause"

Set-Content "$PROJECT_DIR\start-all.bat" "@echo off`r`ntitle AutoLearning`r`necho Starting AutoLearning...`r`nstart `"`" cmd /c `"$PROJECT_DIR\start-backend.bat`"`r`ntimeout /t 8 /nobreak >nul`r`nstart `"`" cmd /c `"$PROJECT_DIR\start-frontend.bat`"`r`necho.`r`necho AutoLearning started!`r`necho Frontend: http://localhost:5173`r`necho Backend: http://localhost:8000/docs`r`npause"

Write-Host "  OK 启动脚本已创建" -ForegroundColor Green

# 完成
Write-Host "" -ForegroundColor White
Write-Host "==========================================" -ForegroundColor Green
Write-Host "  部署完成" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host "" -ForegroundColor White
Write-Host "  项目位置: $PROJECT_DIR" -ForegroundColor White
Write-Host "  启动: 双击 start-all.bat" -ForegroundColor White
Write-Host "  前端: http://localhost:5173" -ForegroundColor Cyan
Write-Host "  后端: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "" -ForegroundColor White
Write-Host "  记得放行端口 5173 和 8000" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Cyan
