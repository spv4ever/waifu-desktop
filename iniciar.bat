@echo off
setlocal

echo ==========================================
echo   WAIFU DESKTOP - START
echo ==========================================

REM Cambiar al directorio del proyecto
cd /d "%~dp0"

REM Comprobar entorno virtual
if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] Entorno virtual no encontrado.
    echo Crea el entorno con:
    echo   python -m venv .venv
    pause
    exit /b 1
)

REM Activar entorno virtual
call .venv\Scripts\activate.bat

REM Comprobar dependencias básicas
python -c "import PySide6" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Dependencias no instaladas.
    echo Ejecuta:
    echo   pip install -r requirements.txt
    pause
    exit /b 1
)

echo Entorno virtual activado.
echo Lanzando Waifu Desktop...
echo.

REM Arrancar la UI
python -m app.runner.run_ui

echo.
echo Waifu Desktop cerrado.
pause
