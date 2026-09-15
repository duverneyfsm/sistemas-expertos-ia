"""Rutas y parámetros comunes del prototipo."""

from pathlib import Path

RAIZ_PROYECTO = Path(__file__).resolve().parent
RUTA_ENV = RAIZ_PROYECTO / ".env"
CARPETA_DATOS = RAIZ_PROYECTO / "datos"
CARPETA_RESULTADOS = RAIZ_PROYECTO / "resultados"
RUTA_CALIBRACION = CARPETA_DATOS / "calibracion.csv"
RUTA_PRUEBA = CARPETA_DATOS / "prueba.csv"
RUTA_ALERTAS = CARPETA_RESULTADOS / "alertas.csv"
RUTA_METRICAS = CARPETA_RESULTADOS / "metricas.json"

SEMILLA = 20260824
TASA_IVA_ESPERADA = 0.19
HORA_INICIO = 7
HORA_FIN = 19

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
