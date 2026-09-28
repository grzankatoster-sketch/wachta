@echo off
REM Jedno klikniecie: podnosi stos, czeka az odpowie, otwiera aplikacje w przegladarce.
REM Plik lezy w korzeniu repozytorium celowo - zeby nie trzeba bylo go szukac.
setlocal
set DOCKER="%ProgramFiles%\Docker\Docker\resources\bin\docker.exe"
set PORT=8083
cd /d "%~dp0"

echo.
echo   WACHTA - uruchamianie
echo.

REM Bez .env baza nie wstanie, a compose tylko ostrzeze i pojdzie dalej - lepiej powiedziec wprost.
if not exist ".env" (
  echo   BRAK PLIKU .env
  echo   Skopiuj .env.example do .env i wpisz haslo do bazy:
  echo       copy .env.example .env
  echo.
  pause
  exit /b 1
)

REM Silnik Dockera potrafi nie odpowiadac mimo dzialajacej aplikacji - sprawdzamy silnik, nie ikone.
%DOCKER% version --format "{{.Server.Version}}" >nul 2>&1
if errorlevel 1 (
  echo   Docker nie odpowiada. Uruchamiam Docker Desktop...
  start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
  echo   Czekam az silnik wstanie ^(do 3 minut^)...
  for /l %%i in (1,1,36) do (
    ping -n 6 127.0.0.1 >nul
    %DOCKER% version --format "{{.Server.Version}}" >nul 2>&1
    if not errorlevel 1 goto silnik_gotowy
  )
  echo   Silnik nie wstal. Otworz Docker Desktop recznie i sprobuj ponownie.
  pause
  exit /b 1
)
:silnik_gotowy

echo   Podnosze uslugi...
%DOCKER% compose up -d
if errorlevel 1 (
  echo   Nie udalo sie podniesc uslug - tresc bledu wyzej.
  pause
  exit /b 1
)

echo   Czekam, az aplikacja odpowie...
for /l %%i in (1,1,30) do (
  ping -n 4 127.0.0.1 >nul
  curl.exe -s -o nul -m 5 "http://localhost:%PORT%/" && goto gotowe
)
echo   Aplikacja nie odpowiedziala. Sprawdz: %DOCKER% compose logs web
pause
exit /b 1

:gotowe
echo.
echo   Gotowe.
echo     aplikacja:  http://localhost:%PORT%
echo     API:        http://localhost:8080/api/aircraft/live
echo.
echo   Zatrzymanie:  docker compose stop
echo   Podglad:      docker compose logs -f detectors
echo.
start "" "http://localhost:%PORT%/"
endlocal
