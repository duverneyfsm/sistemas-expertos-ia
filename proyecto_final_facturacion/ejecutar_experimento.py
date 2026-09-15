"""Punto de entrada de consola para ejecutar y validar el prototipo."""

from config import RUTA_ALERTAS, RUTA_METRICAS
from servicio import ejecutar_experimento


if __name__ == "__main__":
    _, metricas, _ = ejecutar_experimento()
    print("Experimento completado con datos sintéticos.")
    for nombre, valor in metricas.items():
        print(f"{nombre.replace('_', ' ').capitalize()}: {valor}")
    print(f"Alertas exportadas: {RUTA_ALERTAS}")
    print(f"Métricas exportadas: {RUTA_METRICAS}")
