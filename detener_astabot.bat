@echo off
set "lockfile=astabot.lock"

if exist "%lockfile%" (
    set /p pid=<"%lockfile%"
    echo Found lockfile. Attempting to stop Astabot...
    taskkill /F /PID %pid% >nul 2>&1
    del "%lockfile%"
) 

taskkill /F /IM pythonw.exe /FI "WINDOWTITLE eq Astabot*" >nul 2>&1
echo Astabot detenido.