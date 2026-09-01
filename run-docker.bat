@echo off
setlocal EnableDelayedExpansion
title InferMesh - full Docker stack
cd /d "%~dp0"

echo(
echo   InferMesh  -  full container stack  (nginx + gateway + Postgres + Redis)
echo   --------------------------------------------------------------------------
echo(

where docker >nul 2>&1 || (echo [X] "docker" is not on PATH - install Docker Desktop & goto :fail)
if not exist "backend\.env" (
  echo [X] backend\.env is missing.  Copy .env.example to backend\.env and add your keys.
  goto :fail
)

docker info >nul 2>&1
if errorlevel 1 (
  echo [..] Launching Docker Desktop...
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

for /f %%h in ('git rev-parse --short HEAD 2^>nul') do set "GIT_SHA=%%h"
if not defined GIT_SHA set "GIT_SHA=dev"

echo [..] Building images and starting the stack  ^(first run takes a few minutes^)...
docker compose --profile full up -d --build || goto :fail

echo [..] Waiting for the backend to become healthy...
:waitbe
set "_be="
for /f "usebackq delims=" %%s in (`docker inspect -f "{{.State.Health.Status}}" infermesh-backend-1 2^>nul`) do set "_be=%%s"
if /i not "!_be!"=="healthy" ( call :sleep 3 & goto waitbe )

echo [..] Seeding demo data if the DB is empty...
set "_rows="
for /f "usebackq delims=" %%r in (`docker compose exec -T postgres psql -U gateway -d gateway -tAc "select count(*) from requests" 2^>nul`) do set "_rows=%%r"
set "_rows=!_rows: =!"
if not defined _rows set "_rows=0"
if "!_rows!"=="0" docker compose --profile seed run --rm seed --rows 100000 --truncate

start "" http://localhost:8080/

echo(
echo   ================================================================
echo    Dashboard : http://localhost:8080   admin@example.com / admin-dev-password
echo    Gateway   : http://localhost:8000
echo(
echo    Everything runs in Docker.  Stop it with:  docker compose --profile full down
echo   ================================================================
echo(
pause
exit /b 0

:sleep
set /a _s=%1+1
ping -n %_s% 127.0.0.1 >nul 2>&1
exit /b 0

:fail
echo(
pause
exit /b 1
