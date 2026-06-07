param(
    [string]$ProjectDir = "C:\www\wwwroot\AutoLearning",
    [string]$RepoUrl = "https://github.com/LGY4/AutoLearning.git",
    [string]$PublicOrigin = "http://159.75.71.163",
    [int]$BackendPort = 8000,
    [switch]$UseMemoryBackend,
    [switch]$EnableWorker,
    [switch]$SkipScheduledTask
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host $Message -ForegroundColor Cyan
}

function Find-Command {
    param([string[]]$Names)
    foreach ($name in $Names) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            return $cmd.Source
        }
    }
    return $null
}

function Assert-Command {
    param(
        [string[]]$Names,
        [string]$InstallHint
    )
    $found = Find-Command -Names $Names
    if (-not $found) {
        throw "Missing required command: $($Names -join '/'). $InstallHint"
    }
    return $found
}

function Get-RandomSecret {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    } finally {
        $rng.Dispose()
    }
    return ($bytes | ForEach-Object { $_.ToString("x2") }) -join ""
}

function Set-EnvValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Value
    )

    if (-not (Test-Path $Path)) {
        New-Item -ItemType File -Path $Path -Force | Out-Null
    }

    $lines = Get-Content -Path $Path -Encoding UTF8
    $escapedKey = [regex]::Escape($Key)
    $replacement = "$Key=$Value"
    $matched = $false
    $updated = foreach ($line in $lines) {
        if ($line -match "^$escapedKey=") {
            $matched = $true
            $replacement
        } else {
            $line
        }
    }
    if (-not $matched) {
        $updated += $replacement
    }
    Set-Content -Path $Path -Value $updated -Encoding UTF8
}

function Get-EnvValue {
    param(
        [string]$Path,
        [string]$Key
    )
    if (-not (Test-Path $Path)) {
        return $null
    }
    $escapedKey = [regex]::Escape($Key)
    foreach ($line in Get-Content -Path $Path -Encoding UTF8) {
        if ($line -match "^$escapedKey=(.*)$") {
            return $Matches[1].Trim()
        }
    }
    return $null
}

function Test-PlaceholderValue {
    param([string]$Value)
    return [string]::IsNullOrWhiteSpace($Value) -or
        $Value -eq "sk-your-key-here" -or
        $Value -eq "change-me-to-a-random-string"
}

function Write-RunnerScript {
    param(
        [string]$Path,
        [string]$ProjectDir,
        [string]$Module
    )

    $content = @"
`$ErrorActionPreference = "Stop"
`$ProjectDir = "$ProjectDir"
Set-Location "`$ProjectDir\backend"
& "`$ProjectDir\backend\.venv\Scripts\python.exe" -m $Module
"@
    Set-Content -Path $Path -Value $content -Encoding UTF8
}

function Write-LoopScript {
    param(
        [string]$Path,
        [string]$TargetScript,
        [string]$LogPath
    )

    $content = @"
`$ErrorActionPreference = "Continue"
New-Item -ItemType Directory -Path "$(Split-Path $LogPath -Parent)" -Force | Out-Null
while (`$true) {
    `$started = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path "$LogPath" -Value "`n[`$started] starting $TargetScript" -Encoding UTF8
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$TargetScript" *>> "$LogPath"
    `$code = `$LASTEXITCODE
    `$ended = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path "$LogPath" -Value "[`$ended] exited with code `$code; restarting in 5 seconds" -Encoding UTF8
    Start-Sleep -Seconds 5
}
"@
    Set-Content -Path $Path -Value $content -Encoding UTF8
}

function Register-StartupTask {
    param(
        [string]$TaskName,
        [string]$ScriptPath
    )
    $taskCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""
    schtasks.exe /Create /TN $TaskName /SC ONSTART /RU SYSTEM /RL HIGHEST /TR $taskCommand /F | Out-Null
    schtasks.exe /Run /TN $TaskName | Out-Null
}

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  AutoLearning Baota Windows Deployment" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

Write-Step "[1/8] Checking prerequisites"
$git = Assert-Command -Names @("git.exe", "git") -InstallHint "Install Git for Windows from Baota software store or https://git-scm.com/."
$python = Assert-Command -Names @("python.exe", "python", "py.exe", "py") -InstallHint "Install Python 3.10+ and add it to PATH."
$node = Assert-Command -Names @("node.exe", "node") -InstallHint "Install Node.js 18+."
$npm = Assert-Command -Names @("npm.cmd", "npm") -InstallHint "Install Node.js 18+."

$pythonVersion = & $python --version 2>&1
if ($pythonVersion -notmatch "Python 3\.(1[0-9]|[2-9][0-9])") {
    throw "Python 3.10+ is required. Current: $pythonVersion"
}
$nodeVersion = & $node --version 2>&1
if ($nodeVersion -notmatch "^v(1[8-9]|[2-9][0-9])\.") {
    throw "Node.js 18+ is required. Current: $nodeVersion"
}
Write-Host "  Python: $pythonVersion" -ForegroundColor Green
Write-Host "  Node: $nodeVersion" -ForegroundColor Green

Write-Step "[2/8] Preparing source code"
if (Test-Path "$ProjectDir\.git") {
    Set-Location $ProjectDir
    & $git fetch --prune origin
    & $git checkout main
    & $git pull --ff-only origin main
} else {
    if (Test-Path $ProjectDir) {
        throw "$ProjectDir exists but is not a Git repository. Move it aside or choose another -ProjectDir."
    }
    New-Item -ItemType Directory -Path (Split-Path $ProjectDir -Parent) -Force | Out-Null
    & $git clone $RepoUrl $ProjectDir
    Set-Location $ProjectDir
}

Write-Step "[3/8] Preparing backend environment"
$backendDir = Join-Path $ProjectDir "backend"
$frontendDir = Join-Path $ProjectDir "frontend"
$envFile = Join-Path $backendDir ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $ProjectDir ".env.example") $envFile
}
if (-not (Test-Path (Join-Path $backendDir "alembic.ini"))) {
    Copy-Item (Join-Path $backendDir "alembic.ini.example") (Join-Path $backendDir "alembic.ini")
}

Set-EnvValue -Path $envFile -Key "ENVIRONMENT" -Value "production"
Set-EnvValue -Path $envFile -Key "HOST" -Value "127.0.0.1"
Set-EnvValue -Path $envFile -Key "PORT" -Value "$BackendPort"
Set-EnvValue -Path $envFile -Key "CORS_ORIGINS" -Value $PublicOrigin

$currentSecret = Get-EnvValue -Path $envFile -Key "SECRET_KEY"
if (Test-PlaceholderValue -Value $currentSecret) {
    Set-EnvValue -Path $envFile -Key "SECRET_KEY" -Value (Get-RandomSecret)
}

if ($UseMemoryBackend) {
    Set-EnvValue -Path $envFile -Key "REPOSITORY_BACKEND" -Value "memory"
    Set-EnvValue -Path $envFile -Key "RAG_BACKEND" -Value "memory"
    Set-EnvValue -Path $envFile -Key "EMBEDDING_PROVIDER" -Value "local"
    Set-EnvValue -Path $envFile -Key "EMBEDDING_ALLOW_FALLBACK" -Value "true"
} else {
    Set-EnvValue -Path $envFile -Key "REPOSITORY_BACKEND" -Value "postgres"
    Set-EnvValue -Path $envFile -Key "RAG_BACKEND" -Value "chroma"
}

$llmKey = Get-EnvValue -Path $envFile -Key "LLM_API_KEY"
if (Test-PlaceholderValue -Value $llmKey) {
    Write-Host ""
    Write-Host "Please edit $envFile and set LLM_API_KEY, then run this script again." -ForegroundColor Yellow
    Write-Host "The script has already prepared production defaults and generated SECRET_KEY." -ForegroundColor Yellow
    exit 1
}

Set-Location $backendDir
if (-not (Test-Path ".venv")) {
    & $python -m venv .venv
}
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\pip.exe" install -r requirements.txt

Write-Step "[4/8] Bootstrapping backend data"
& ".\.venv\Scripts\python.exe" -m app.ops.bootstrap

Write-Step "[5/8] Building frontend"
Set-Location $frontendDir
if (Test-Path "package-lock.json") {
    & $npm ci
} else {
    & $npm install
}
& $npm run build

Write-Step "[6/8] Writing runtime scripts"
$runtimeDir = Join-Path $ProjectDir "deploy\runtime"
$logDir = Join-Path $ProjectDir "logs"
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

$apiScript = Join-Path $runtimeDir "start-api.ps1"
$apiLoopScript = Join-Path $runtimeDir "run-api-loop.ps1"
Write-RunnerScript -Path $apiScript -ProjectDir $ProjectDir -Module "app.ops.start_api"
Write-LoopScript -Path $apiLoopScript -TargetScript $apiScript -LogPath (Join-Path $logDir "api.log")

if ($EnableWorker) {
    $workerScript = Join-Path $runtimeDir "start-worker.ps1"
    $workerLoopScript = Join-Path $runtimeDir "run-worker-loop.ps1"
    Write-RunnerScript -Path $workerScript -ProjectDir $ProjectDir -Module "app.ops.start_worker"
    Write-LoopScript -Path $workerLoopScript -TargetScript $workerScript -LogPath (Join-Path $logDir "worker.log")
}

Write-Step "[7/8] Registering startup tasks"
if ($SkipScheduledTask) {
    Write-Host "  Skipped scheduled task registration." -ForegroundColor Yellow
    Write-Host "  Start backend manually: powershell -ExecutionPolicy Bypass -File `"$apiLoopScript`"" -ForegroundColor Yellow
} else {
    Register-StartupTask -TaskName "AutoLearning-API" -ScriptPath $apiLoopScript
    Write-Host "  AutoLearning-API registered and started." -ForegroundColor Green
    if ($EnableWorker) {
        Register-StartupTask -TaskName "AutoLearning-Worker" -ScriptPath $workerLoopScript
        Write-Host "  AutoLearning-Worker registered and started." -ForegroundColor Green
    }
}

Write-Step "[8/8] Health check"
Start-Sleep -Seconds 8
try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/health" -TimeoutSec 5
    Write-Host "  Backend health: $($health.status)" -ForegroundColor Green
} catch {
    Write-Host "  Backend health check failed. Check $logDir\api.log" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Deployment assets are ready." -ForegroundColor Green
Write-Host "Frontend site root: $frontendDir\dist" -ForegroundColor White
Write-Host "Backend local URL: http://127.0.0.1:$BackendPort" -ForegroundColor White
Write-Host "Baota Nginx should proxy /api/ and /static/ to the backend." -ForegroundColor White
Write-Host "Use deploy\baota-nginx-autolearning.conf.example as the site config reference." -ForegroundColor White
Write-Host "==========================================" -ForegroundColor Green
