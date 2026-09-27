# Wszystkie kontrole lokalne. Pomija te, dla ktorych brakuje narzedzi, i mowi o tym wprost.
# UWAGA: tylko ASCII. Windows PowerShell 5.1 czyta pliki .ps1 bez BOM jako ANSI, a bajt 0x94
# z wielobajtowych znakow UTF-8 (np. myslnika) jest tam cudzyslowem i rozwala parser.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$failed = @()

function Step($name, $block) {
    Write-Host ""
    Write-Host "=== $name ===" -ForegroundColor Cyan
    try {
        & $block
        if ($LASTEXITCODE -ne 0) { $script:failed += $name }
    } catch {
        $script:failed += $name
        Write-Host $_ -ForegroundColor Red
    }
}

function Missing($tool, $name, $why) {
    if (Get-Command $tool -ErrorAction SilentlyContinue) { return $false }
    Write-Host ""
    Write-Host "=== $name - POMINIETE ===" -ForegroundColor Yellow
    Write-Host "brak '$tool': $why"
    return $true
}

Step "detektory (pytest)" { Set-Location "$root\src\python"; python -m pytest tests -q --ignore=tests/integration }
Step "bramka jakosci (eval)" { Set-Location $root; python eval/run_eval.py --check eval/baseline.json }

if (-not (Missing "docker" "testy integracyjne Pythona" "zainstaluj Docker Desktop (wymaga WSL2)")) {
    Step "testy integracyjne" { Set-Location "$root\src\python"; python -m pytest tests/integration -q }
}

Step "front: testy jednostkowe" { Set-Location "$root\web"; npm test }
Step "front: kontrola typow i budowa" { Set-Location "$root\web"; npm run build }
Step "front: testy w przegladarce" { Set-Location "$root\web"; npx playwright test }

$sdks = if (Get-Command dotnet -ErrorAction SilentlyContinue) { dotnet --list-sdks 2>$null } else { $null }
if ($sdks) {
    Step "C# (dotnet test)" { Set-Location "$root\src\dotnet"; dotnet test }
} else {
    Write-Host ""
    Write-Host "=== testy C# - POMINIETE ===" -ForegroundColor Yellow
    Write-Host "brak .NET SDK: winget install -e --id Microsoft.DotNet.SDK.10"
}

Set-Location $root
Write-Host ""
if ($failed.Count -eq 0) {
    Write-Host "WSZYSTKO ZIELONE" -ForegroundColor Green
} else {
    Write-Host ("OBLALY: " + ($failed -join ", ")) -ForegroundColor Red
    exit 1
}
