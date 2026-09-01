@echo off
title InferMesh - stop
cd /d "%~dp0"

echo(
echo   Stopping InferMesh...
echo(

rem dev-mode server windows
taskkill /F /FI "WINDOWTITLE eq InferMesh backend*"  >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq InferMesh frontend*" >nul 2>&1
rem anything still bound to the dev ports
for %%p in (8000 5173) do (
  for /f "tokens=5" %%a in ('netstat -ano ^| findstr /r /c:":%%p .*LISTENING"') do taskkill /F /PID %%a >nul 2>&1
)

echo [..] Stopping containers ^(data volumes are kept^)...
docker compose --profile full --profile seed stop >nul 2>&1
docker compose stop >nul 2>&1

echo(
echo   Done.  Postgres/Redis data volumes are preserved.
echo   ( "docker compose down -v" also deletes the data. )
echo(
pause
