Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $root
try {
    python .\scripts\verify_runtime.py
}
finally {
    Pop-Location
}
