@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "URL_FACTUGUARD=http://127.0.0.1:5000/login"

echo Iniciando FactuGuard IA. Puede tardar unos segundos en preparar el modelo.

REM Si ya hay un servidor en el puerto 5000, no se inicia una segunda copia.
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if not errorlevel 1 goto abrir_navegador

REM El servidor queda en su propia ventana: no la cierres mientras uses la aplicacion.
start "FactuGuard IA - Servidor" /D "%~dp0" cmd /k py -u web_app.py

REM Espera hasta un minuto a que Flask escuche antes de abrir el navegador.
powershell -NoProfile -Command "$limite=(Get-Date).AddSeconds(60); while((Get-Date) -lt $limite) { $cliente=[System.Net.Sockets.TcpClient]::new(); try { $cliente.Connect('127.0.0.1',5000); $cliente.Dispose(); Start-Process '%URL_FACTUGUARD%'; exit 0 } catch { $cliente.Dispose(); Start-Sleep -Milliseconds 500 } }; exit 1"
if errorlevel 1 (
    echo.
    echo FactuGuard no pudo iniciar en un minuto. Revisa la ventana "FactuGuard IA - Servidor" para ver el error.
    pause
    exit /b 1
)
exit /b 0

:abrir_navegador
echo Ya habia un servidor de FactuGuard ejecutandose. Abriendo el navegador...
start "" "%URL_FACTUGUARD%"
