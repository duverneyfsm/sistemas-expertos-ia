"""Servidor de producción de FactuGuard IA (Waitress).

`py web_app.py` usa el servidor de desarrollo de Flask, pensado para una sola
persona. Este archivo sirve la misma aplicación con Waitress, que atiende varias
personas a la vez, funciona en Windows y Linux y no muestra pantallas de depuración.

Configuración en el archivo .env (todas opcionales):
    ENTORNO=produccion      activa los controles estrictos (ver DESPLIEGUE_EMPRESA.md)
    SERVIDOR_HOST=127.0.0.1 usa 0.0.0.0 para recibir conexiones de otros equipos
    SERVIDOR_PUERTO=8000
    SERVIDOR_HILOS=8        peticiones que se atienden en paralelo

Uso:
    py servidor_produccion.py
"""

from __future__ import annotations

import os

from waitress import serve

from config import ES_PRODUCCION
from web_app import app

if __name__ == "__main__":
    host = os.getenv("SERVIDOR_HOST", "127.0.0.1")
    puerto = int(os.getenv("SERVIDOR_PUERTO", "8000"))
    hilos = int(os.getenv("SERVIDOR_HILOS", "8"))
    print(f"FactuGuard IA ({'producción' if ES_PRODUCCION else 'desarrollo'}) en http://{host}:{puerto}")
    print("Ctrl+C para detener. Los eventos se registran en logs/factuguard.log")
    # channel_timeout alto: una carga grande puede tardar varios segundos en analizarse.
    serve(app, host=host, port=puerto, threads=hilos, channel_timeout=300, max_request_body_size=app.config["MAX_CONTENT_LENGTH"])
