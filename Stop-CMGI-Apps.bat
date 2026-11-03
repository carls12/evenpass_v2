@echo off
rem Beendet die von Start-CMGI-Apps.bat geoeffneten Entwicklungsfenster.
for %%t in ("CMGI EventPass API" "CMGI EventPass UI" "CMGI Portal" "CMGI Sermon API" "CMGI Sermon UI" "CMGI Accounts API") do (
  taskkill /FI "WINDOWTITLE eq %%~t*" /T /F >nul 2>nul && echo %%~t beendet.
)
echo Fertig. Daten bleiben in apps\eventpass\backend und apps\sermon-ai\backend erhalten.
timeout /t 3 >nul
