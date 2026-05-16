Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location (Join-Path $root "infra")
try {
    docker compose up --build
}
finally {
    Pop-Location
}
