"""Rutas y parámetros comunes del prototipo.

Todo lo que una empresa necesita ajustar se lee del archivo .env (ver
.env.example). Si una variable no existe se usa el valor de demostración.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ_PROYECTO = Path(__file__).resolve().parent
RUTA_ENV = RAIZ_PROYECTO / ".env"
load_dotenv(RUTA_ENV)

CARPETA_DATOS = RAIZ_PROYECTO / "datos"
CARPETA_RESULTADOS = RAIZ_PROYECTO / "resultados"
CARPETA_MODELOS = RAIZ_PROYECTO / "modelos"
CARPETA_REGISTROS = RAIZ_PROYECTO / "logs"
RUTA_CALIBRACION = CARPETA_DATOS / "calibracion.csv"
RUTA_PRUEBA = CARPETA_DATOS / "prueba.csv"
RUTA_ALERTAS = CARPETA_RESULTADOS / "alertas.csv"
RUTA_METRICAS = CARPETA_RESULTADOS / "metricas.json"
# Modelo calibrado con las facturas reales de la empresa (lo crea calibrar_empresa.py).
RUTA_MOTOR_EMPRESA = CARPETA_MODELOS / "motor_empresa.joblib"
RUTA_INFO_MOTOR_EMPRESA = CARPETA_MODELOS / "motor_empresa.json"

SEMILLA = 20260824
TASA_IVA_ESPERADA = 0.19
HORA_INICIO = 7
HORA_FIN = 19


def _entero(nombre: str, defecto: int) -> int:
    try:
        return int(os.getenv(nombre, defecto))
    except ValueError:
        return defecto


# --- Entorno -----------------------------------------------------------------
# "produccion" activa los controles estrictos: llave secreta obligatoria,
# cookies seguras y mensajes de error genéricos para el usuario.
ENTORNO = os.getenv("ENTORNO", "desarrollo").strip().lower()
ES_PRODUCCION = ENTORNO == "produccion"

# --- Volumen -----------------------------------------------------------------
MAX_ARCHIVO_MB = _entero("MAX_ARCHIVO_MB", 50)
MAX_FILAS_ARCHIVO = _entero("MAX_FILAS_ARCHIVO", 200_000)
# La calibración necesita suficiente historia para que "normal" tenga significado.
MIN_FACTURAS_CALIBRACION = _entero("MIN_FACTURAS_CALIBRACION", 500)

# --- Reglas y modelos --------------------------------------------------------
# Tarifas de IVA aceptadas, en porcentaje y separadas por coma: "19,5,0".
# Por defecto solo el 19 % (comportamiento de la demostración).
try:
    TASAS_IVA_PERMITIDAS = tuple(
        round(float(valor) / 100, 4) for valor in os.getenv("TASAS_IVA_PERMITIDAS", "19").split(",") if valor.strip()
    ) or (TASA_IVA_ESPERADA,)
except ValueError:
    TASAS_IVA_PERMITIDAS = (TASA_IVA_ESPERADA,)

# Cómo se combinan las tres IA (Isolation Forest, KNN y perceptrón):
#   "mayoria"   -> alerta si al menos 2 de las 3 coinciden (pocas falsas alarmas).
#   "cualquiera" -> alerta si una sola duda (máxima sensibilidad, muchas falsas alarmas).
POLITICA_IA = os.getenv("POLITICA_IA", "mayoria").strip().lower()
if POLITICA_IA not in {"mayoria", "cualquiera"}:
    POLITICA_IA = "mayoria"
VOTOS_MINIMOS_IA = 1 if POLITICA_IA == "cualquiera" else 2
PERCENTIL_ALERTA = min(max(float(os.getenv("PERCENTIL_ALERTA", "0.99")), 0.5), 0.9999)

# Variables numéricas que usará el modelo de aprendizaje automático.
CARACTERISTICAS_MODELO = (
    "cantidad",
    "precio_unitario",
    "descuento_pct",
    "valor_descuento",
    "subtotal",
    "total",
    "hora",
)
