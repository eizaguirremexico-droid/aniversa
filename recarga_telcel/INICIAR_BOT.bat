@echo off
title Bot de recarga Telcel
cd /d "%~dp0"

echo ============================================================
echo   Iniciando el bot de recarga
echo ============================================================
echo.

echo Revisando la libreria requests...
python -m pip install --quiet requests 2>nul
if errorlevel 1 (
    echo.
    echo No se pudo usar 'python'. Probando con 'py'...
    py -m pip install --quiet requests
    echo.
    py bot_telegram.py
    goto fin
)

echo Listo.
echo.
python bot_telegram.py

:fin
echo.
echo ============================================================
echo   El bot se detuvo.
echo ============================================================
pause
