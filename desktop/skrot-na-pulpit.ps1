# Kladzie skrot WACHTA na pulpicie biezacego uzytkownika.
#
# Skrot celuje WPROST w electron.exe, bez posrednika w postaci pliku .cmd, zeby przy starcie nie
# mrugalo okno konsoli. Dziala, bo ELECTRON_RUN_AS_NODE nie jest ustawiona ani dla uzytkownika, ani
# dla systemu - sprawdzone. Gdyby kiedys byla, Electron wystartowalby jako zwykly Node i main.js
# przewrocilby sie na "app is undefined"; wtedy trzeba posrednika, ktory ja czysci.
#
# Uruchomienie:  powershell -ExecutionPolicy Bypass -File desktop\skrot-na-pulpit.ps1

$ErrorActionPreference = 'Stop'

$katalog = Split-Path -Parent $MyInvocation.MyCommand.Path
$electron = Join-Path $katalog 'node_modules\electron\dist\electron.exe'
$ikona = Join-Path $katalog 'ikona.ico'

if (-not (Test-Path $electron)) {
    Write-Error "Brak $electron - uruchom najpierw 'npm install' w katalogu desktop."
}

$pulpit = [Environment]::GetFolderPath('Desktop')
$sciezka = Join-Path $pulpit 'WACHTA.lnk'

$skrot = (New-Object -ComObject WScript.Shell).CreateShortcut($sciezka)
$skrot.TargetPath = $electron
$skrot.Arguments = '.'
$skrot.WorkingDirectory = $katalog
if (Test-Path $ikona) { $skrot.IconLocation = "$ikona,0" }
$skrot.Description = 'WACHTA - obraz sytuacyjny Baltyku z danych publicznych'
$skrot.Save()

Write-Output "Skrot zapisany: $sciezka"
Write-Output 'Okno samo podnosi Dockera i pokazuje, na ktorym kroku stoi.'
