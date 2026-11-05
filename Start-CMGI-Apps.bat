@echo off
setlocal EnableExtensions
title CMGI Apps
cd /d "%~dp0"
set "ROOT=%~dp0"
set "API=%ROOT%apps\eventpass\backend"
set "EPUI=%ROOT%apps\eventpass\frontend"
set "PORTAL=%ROOT%apps\portal"
set "SAPI=%ROOT%apps\sermon-ai\backend"
set "SUI=%ROOT%apps\sermon-ai\frontend"
set "AAPI=%ROOT%apps\accounts\backend"
rem Body of Christ (separate repository), if it is cloned next to this folder.
set "BOC=%ROOT%..\bodyofchrist-django"
rem Shared secret between the local apps and the local account service (development only).
set "ACCOUNTS_INTERNAL_KEY=local-dev-internal-key-0123456789"

rem Optional local settings (e.g. real e-mail sending): lines NAME=value in .env next to this file.
rem Empty values are skipped, so the rest of the local defaults stay as they are.
if exist "%ROOT%.env" for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%ROOT%.env") do if not "%%B"=="" set "%%A=%%B"
rem One set of mail settings for all apps (as on the server): account service and Body of Christ use other names.
if defined EVENTPASS_SMTP_PASSWORD if defined EVENTPASS_MAIL_FROM call :mail_settings

rem  Start-CMGI-Apps.bat          -> Entwicklungsmodus (Python + Node, Live-Reload)
rem  Start-CMGI-Apps.bat docker   -> kompletter Stack mit Docker Desktop (wie auf dem Server)
if /i "%~1"=="docker" goto docker

echo.
echo  === CMGI Apps - lokaler Start ===
echo.
where python >nul 2>nul || (echo [Fehler] Python nicht gefunden: https://www.python.org/downloads/ & goto fail)
where npm >nul 2>nul || (echo [Fehler] Node.js nicht gefunden: https://nodejs.org/ & goto fail)

if not exist "%API%\.venv\Scripts\python.exe" (
  echo [1/3] Python-Umgebung wird eingerichtet ...
  python -m venv "%API%\.venv" || goto fail
)
echo [1/3] Python-Pakete pruefen ...
"%API%\.venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r "%API%\requirements.txt" || goto fail
if not exist "%SAPI%\.venv\Scripts\python.exe" python -m venv "%SAPI%\.venv" || goto fail
"%SAPI%\.venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r "%SAPI%\requirements.txt" || goto fail
if not exist "%AAPI%\.venv\Scripts\python.exe" python -m venv "%AAPI%\.venv" || goto fail
"%AAPI%\.venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r "%AAPI%\requirements.txt" || goto fail
if exist "%BOC%\manage.py" call :setup_boc || goto fail

echo [2/3] Node-Pakete pruefen ...
if not exist "%EPUI%\node_modules" (pushd "%EPUI%" & call npm ci --no-audit --no-fund & popd)
if not exist "%PORTAL%\node_modules" (pushd "%PORTAL%" & call npm ci --no-audit --no-fund & popd)
if not exist "%SUI%\node_modules" (pushd "%SUI%" & call npm ci --no-audit --no-fund & popd)

echo [3/3] Dienste starten ...
rem Lokales Konto-System (SQLite). Admin: Benutzer-Umgebungsvariable CMGI_ADMIN_EMAILS mit deiner E-Mail setzen.
call :running 8020 && (echo       Konto-API laeuft bereits auf Port 8020) || start "CMGI Accounts API" /min /D "%AAPI%" cmd /k "set MAIL_OUTBOX=%AAPI%\data\outbox&&.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8020"
if exist "%BOC%\manage.py" (call :running 8030 && (echo       Body of Christ laeuft bereits auf Port 8030) || start "CMGI Body of Christ" /min /D "%BOC%" cmd /k ".venv\Scripts\python.exe manage.py runserver 127.0.0.1:8030")
call :running 8000 && (echo       EventPass-API laeuft bereits auf Port 8000) || start "CMGI EventPass API" /min /D "%API%" cmd /k ".venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000"
call :running 5174 && (echo       EventPass-Oberflaeche laeuft bereits auf Port 5174) || start "CMGI EventPass UI" /min /D "%EPUI%" cmd /k "npm run dev"
call :running 8010 && (echo       Sermon-API laeuft bereits auf Port 8010) || start "CMGI Sermon API" /min /D "%SAPI%" cmd /k ".venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8010"
call :running 5175 && (echo       Sermon-Oberflaeche laeuft bereits auf Port 5175) || start "CMGI Sermon UI" /min /D "%SUI%" cmd /k "npm run dev"
call :running 5173 && (echo       Portal laeuft bereits auf Port 5173) || start "CMGI Portal" /min /D "%PORTAL%" cmd /k "npm run dev"

echo       Warte auf das Portal ...
for /l %%i in (1,1,40) do (
  curl -s -o nul http://localhost:5173/ && goto ready
  timeout /t 1 /nobreak >nul
)
echo [Warnung] Portal antwortet noch nicht - siehe Fenster "CMGI Portal".

:ready
start "" http://localhost:5173/
echo.
echo  Portal:     http://localhost:5173/
echo  Anmelden:   http://localhost:5173/login   (Admin-Konsole: /admin, siehe CMGI_ADMIN_EMAILS)
echo  E-Mails:    http://localhost:5173/api/accounts/dev/outbox   (lokal werden Mails nur gespeichert)
echo  EventPass:  http://localhost:5173/eventpass/
echo  Sermons:    http://localhost:5173/sermon-ai/
if exist "%BOC%\manage.py" echo  Body of Christ: http://localhost:5173/bodyofchrist/
echo  (Fuer Transkription und Berichte: OPENAI_API_KEY und ANTHROPIC_API_KEY als Benutzer-Umgebungsvariablen setzen)
echo  API-Doku:   http://localhost:5173/api/eventpass/docs
echo.
echo  Beenden mit Stop-CMGI-Apps.bat
exit /b 0

:docker
where docker >nul 2>nul || (echo [Fehler] Docker Desktop ist nicht installiert: https://www.docker.com/products/docker-desktop/ & goto fail)
if not exist "%ROOT%.env" (echo [Fehler] .env fehlt. Kopiere .env.example nach .env und setze EVENTPASS_ADMIN_PASSWORD. & goto fail)
docker compose up -d --build || goto fail
start "" http://localhost/
echo Laeuft unter http://localhost/  (Stoppen: docker compose down)
exit /b 0

:running
netstat -ano | findstr /R /C:":%1 .*LISTENING" >nul
exit /b %errorlevel%

:fail
echo.
echo Start abgebrochen.
pause
exit /b 1

:mail_settings
if not defined EVENTPASS_SMTP_PORT set "EVENTPASS_SMTP_PORT=587"
if not defined EVENTPASS_SMTP_SECURITY set "EVENTPASS_SMTP_SECURITY=starttls"
set "SMTP_HOST=%EVENTPASS_SMTP_HOST%"
set "SMTP_PORT=%EVENTPASS_SMTP_PORT%"
set "SMTP_SECURITY=%EVENTPASS_SMTP_SECURITY%"
set "SMTP_USER=%EVENTPASS_SMTP_USER%"
set "SMTP_PASSWORD=%EVENTPASS_SMTP_PASSWORD%"
set "MAIL_FROM=%EVENTPASS_MAIL_FROM%"
if defined CMGI_MAIL_FROM set "MAIL_FROM=%CMGI_MAIL_FROM%"
if defined EVENTPASS_MAIL_REPLY_TO set "MAIL_REPLY_TO=%EVENTPASS_MAIL_REPLY_TO%"
set "EMAIL_HOST=%EVENTPASS_SMTP_HOST%"
set "EMAIL_PORT=%EVENTPASS_SMTP_PORT%"
set "EMAIL_HOST_USER=%EVENTPASS_SMTP_USER%"
set "EMAIL_HOST_PASSWORD=%EVENTPASS_SMTP_PASSWORD%"
set "DEFAULT_FROM_EMAIL=%EVENTPASS_MAIL_FROM%"
echo       E-Mail-Versand: %EVENTPASS_SMTP_HOST% (aus .env)
exit /b 0

:setup_boc
rem Body of Christ locally: SQLite database (no MySQL needed), signed in with the local CMGI account.
echo       Body of Christ wird vorbereitet ...
if not exist "%BOC%\.venv\Scripts\python.exe" python -m venv "%BOC%\.venv" || exit /b 1
"%BOC%\.venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r "%BOC%\requirements.txt" || exit /b 1
if not exist "%BOC%\.env" "%BOC%\.venv\Scripts\python.exe" "%ROOT%infrastructure\local\bodyofchrist_env.py" "%BOC%\.env" || exit /b 1
pushd "%BOC%" & ".venv\Scripts\python.exe" manage.py migrate --noinput -v 0 & popd
exit /b 0
