@echo off
title Bot de recarga Telcel
cd /d "%~dp0"

echo ============================================================
echo   Bot de recarga Telcel
echo ============================================================
echo.

REM Elegir el comando de Python que exista en esta maquina.
set PY=python
%PY% --version >nul 2>&1
if errorlevel 1 set PY=py
%PY% --version >nul 2>&1
if errorlevel 1 (
    echo No encuentro Python. Instalalo desde python.org
    echo y marca "Add Python to PATH" durante la instalacion.
    pause
    exit /b 1
)

echo Usando: %PY%
echo Revisando la libreria requests...
%PY% -m pip install --quiet requests
echo.

REM Si el bot se cae (internet caido, error suelto), volver a
REM levantarlo. Sin esto habria que estar pendiente de la ventana.
:reiniciar
echo [%date% %time%] Arrancando el bot...
%PY% bot_telegram.py

echo.
echo [%date% %time%] El bot se detuvo. Reintentando en 15 segundos...
echo Cierra esta ventana si no quieres que vuelva a arrancar.
timeout /t 15 /nobreak >nul
goto reiniciar
