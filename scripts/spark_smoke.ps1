Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location (Join-Path $root "backend")
try {
    .\.venv\Scripts\python.exe -m app.ops.check_spark --call
}
finally {
    Pop-Location
}
