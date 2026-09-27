# Sprawdza, czego brakuje do uruchomienia calego projektu, i pokazuje dokladne komendy.
$ok = $true

function Check($tool, $label, $install, $note = "") {
    $cmd = Get-Command $tool -ErrorAction SilentlyContinue
    if ($cmd) {
        $version = (& $tool --version 2>&1 | Select-Object -First 1)
        Write-Host ("[ jest ] {0,-16} {1}" -f $label, $version) -ForegroundColor Green
    } else {
        Write-Host ("[ BRAK ] {0,-16} {1}" -f $label, $install) -ForegroundColor Yellow
        if ($note) { Write-Host ("          {0}" -f $note) -ForegroundColor DarkGray }
        $script:ok = $false
    }
}

Write-Host "WACHTA - stan srodowiska`n"
Check "git"    "git"        "winget install -e --id Git.Git"
Check "python" "python"     "winget install -e --id Python.Python.3.12"
Check "node"   "node"       "winget install -e --id OpenJS.NodeJS.LTS"
$uvExe = Get-ChildItem "$env:LOCALAPPDATA\Python\*\Scripts\uv.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ((Get-Command uv -ErrorAction SilentlyContinue) -or $uvExe) {
    $where = if ($uvExe -and -not (Get-Command uv -ErrorAction SilentlyContinue)) { "$($uvExe.FullName) - poza PATH, uzywaj 'python -m uv'" } else { (uv --version) }
    Write-Host ("[ jest ] {0,-16} {1}" -f "uv", $where) -ForegroundColor Green
} else {
    Write-Host ("[ BRAK ] {0,-16} {1}" -f "uv", "python -m pip install uv   albo   winget install -e --id astral-sh.uv") -ForegroundColor Yellow
    $ok = $false
}
$sdks = if (Get-Command dotnet -ErrorAction SilentlyContinue) { (dotnet --list-sdks 2>$null) } else { $null }
if ($sdks) {
    Write-Host ("[ jest ] {0,-16} {1}" -f "dotnet SDK", ($sdks | Select-Object -First 1)) -ForegroundColor Green
} else {
    Write-Host ("[ BRAK ] {0,-16} {1}" -f "dotnet SDK", "winget install -e --id Microsoft.DotNet.SDK.10") -ForegroundColor Yellow
    Write-Host "          sam runtime nie wystarczy - sprawdzamy 'dotnet --list-sdks'" -ForegroundColor DarkGray
    $ok = $false
}
Check "docker" "docker"     "winget install -e --id Docker.DockerDesktop" "najpierw WSL2: wsl --install --no-distribution (administrator + restart)"

wsl --status *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ BRAK ] WSL2             wsl --install --no-distribution (PowerShell jako administrator, potem restart)" -ForegroundColor Yellow
    $ok = $false
} else {
    Write-Host "[ jest ] WSL2" -ForegroundColor Green
}

if (-not (Test-Path (Join-Path (Split-Path -Parent $PSScriptRoot) ".env"))) {
    Write-Host "[ BRAK ] .env             cp .env.example .env  (ustaw POSTGRES_PASSWORD; klucze API wg docs/SOURCES.md)" -ForegroundColor Yellow
    $ok = $false
} else {
    Write-Host "[ jest ] .env" -ForegroundColor Green
}

Write-Host ""
if ($ok) {
    Write-Host "Wszystko na miejscu. Uruchomienie: docker compose up -d --build" -ForegroundColor Green
} else {
    Write-Host "Uzupelnij powyzsze, potem: scripts\check.ps1" -ForegroundColor Yellow
}
