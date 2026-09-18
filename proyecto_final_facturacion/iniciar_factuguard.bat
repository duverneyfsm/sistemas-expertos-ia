@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Iniciando FactuGuard IA. Deja esta ventana abierta mientras uses la aplicacion.
py web_app.py
echo.
echo El servidor se detuvo. Si ves un error arriba, revisalo antes de cerrar.
pause
