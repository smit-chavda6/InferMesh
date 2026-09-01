@echo off
setlocal EnableDelayedExpansion
title InferMesh - launcher
cd /d "%~dp0"

echo(
echo   InferMesh  -  starting the dev stack
echo   ----------------------------------------------------------------
echo(

rem --- prerequisites ---------------------------------------------------------
where uv     >nul 2>&1 || (echo [X] "uv" is not on PATH     - https://docs.astral.sh/uv/   & goto :fail)
where npm    >nul 2>&1 || (echo [X] "npm" is not on PATH    - install Node 20+             & goto :fail)
where docker >nul 2>&1 || (echo [X] "docker" is not on PATH - install Docker Desktop       & goto :fail)

if not exist "backend\.env" (
  echo [X] backend\.env is missing.  Copy .env.example to backend\.env and add your keys.
  goto :fail
)

rem --- Docker engine -------------------------------------------------------
docker info >nul 2>&1
if errorlevel 1 (
  echo [..] Docker engine not responding - launching Docker Desktop...
  start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" >nul 2>&1
  set /a _tries=0
  :waitdocker
  call :sleep 3
  docker info >nul 2>&1 && goto dockerok
  set /a _tries+=1
  if !_tries! geq 40 ( echo [X] Docker did not start in time. & goto :fail )
  goto waitdocker
)
:dockerok
echo [ok] Docker engine is up.

rem --- infra --------------------------------------------------------------
echo [..] Starting Postgres + Redis...
docker compose up -d postgres redis || goto :fail
:waitpg
set "_pg="
for /f "usebackq delims=" %%s in (`docker inspect -f "{{.State.Health.Status}}" infermesh-postgres-1 2^>nul`) do set "_pg=%%s"
if /i not "!_pg!"=="healthy" ( call :sleep 2 & goto waitpg )
echo [ok] Postgres + Redis healthy.

rem --- backend deps + migrations + seed --------------------------------
echo [..] Syncing backend deps...
pushd backend
call uv sync || (popd & goto :fail)
echo [..] Applying migrations...
call uv run alembic upgrade head || (popd & goto :fail)

set "_rows="
for /f "usebackq delims=" %%r in (`docker compose -f "..\docker-compose.yml" exec -T postgres psql -U gateway -d gateway -tAc "select count(*) from requests" 2^>nul`) do set "_rows=%%r"
set "_rows=!_rows: =!"
if not defined _rows set "_rows=0"
if "!_rows!"=="0" (
  echo [..] Empty database - seeding ~100k demo rows ^(about a minute^)...
  call uv run python -m scripts.seed --truncate
) else (
  echo [ok] Database already has !_rows! rows - skipping seed.
)
popd

rem --- frontend deps --------------------------------------------------
if not exist "frontend\node_modules" (
  echo [..] Installing frontend deps ^(first run only^)...
  pushd frontend & call npm install & popd
)

rem --- launch -------------------------------------------------------------
echo(
echo [..] Opening the gateway and dashboard in new windows...
start "InferMesh backend  :8000" /D "%~dp0backend"  cmd /k "set AUTH_COOKIE_SECURE=false&& uv run uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "InferMesh frontend :5173" /D "%~dp0frontend" cmd /k "npm run dev -- --host 127.0.0.1 --strictPort"

echo [..] Waiting for the dashboard...
set /a _tries=0
:waitui
call :sleep 2
curl -s -o nul -m 2 http://127.0.0.1:5173/ && goto uiok
set /a _tries+=1
if !_tries! geq 40 goto uiok
goto waitui
:uiok

start "" http://127.0.0.1:5173/

echo(
echo   ================================================================
echo    Dashboard : http://127.0.0.1:5173     admin@example.com / admin-dev-password
echo    Gateway   : http://127.0.0.1:8000        Metrics : /metrics
echo(
echo    Two console windows opened - close them to stop the servers.
echo    Postgres/Redis keep running;  run  stop.bat  to shut everything.
echo   ================================================================
echo(
pause
exit /b 0

:sleep
rem stdin-safe sleep: ping loopback (%1 + 1 pings ~= %1 seconds)
set /a _s=%1+1
ping -n %_s% 127.0.0.1 >nul 2>&1
exit /b 0

:fail
echo(
echo   Launch aborted - see the message above.
echo(
pause
exit /b 1
