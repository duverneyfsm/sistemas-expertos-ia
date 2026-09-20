"""Calibra FactuGuard IA con el histórico de facturas de la empresa.

Los modelos de demostración se entrenan con facturas sintéticas. Para usar el
sistema con facturas reales hay que enseñarle qué es "normal" en ESTA empresa:
montos, descuentos, horarios y hábitos propios.

Uso (en la carpeta del proyecto):
    py calibrar_empresa.py historico_facturas.csv       # o .xlsx
    py calibrar_empresa.py --restablecer                # vuelve al modelo de demostración

El archivo debe tener las mismas columnas de static/plantilla_facturas.csv y
contener facturas ya validadas como correctas (idealmente 6 a 12 meses).
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from config import MIN_FACTURAS_CALIBRACION, RUTA_MOTOR_EMPRESA
from servicio import calibrar_motor_empresa, leer_tabla_facturas, restablecer_motor_demostracion


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibra los modelos con el histórico de la empresa.")
    parser.add_argument("archivo", nargs="?", help="CSV o Excel con facturas normales del histórico")
    parser.add_argument("--restablecer", action="store_true", help="elimina el modelo de la empresa")
    argumentos = parser.parse_args()

    if argumentos.restablecer:
        restablecer_motor_demostracion()
        print("Modelo de la empresa eliminado. Se usará el modelo de demostración.")
        return
    if not argumentos.archivo:
        parser.error("indica el archivo con el histórico, por ejemplo: py calibrar_empresa.py historico.csv")

    ruta = Path(argumentos.archivo)
    inicio = time.perf_counter()
    print(f"Leyendo {ruta.name} ...")
    historico = leer_tabla_facturas(ruta)
    print(f"{len(historico):,} filas leídas. Validando y entrenando (puede tardar unos segundos) ...".replace(",", "."))
    try:
        info = calibrar_motor_empresa(historico)
    except ValueError as error:
        raise SystemExit(f"No se pudo calibrar: {error}") from error
    print()
    print(f"Listo en {time.perf_counter() - inicio:.1f} s")
    print(f"  Facturas normales usadas : {info['facturas']:,}".replace(",", "."))
    print(f"  Excluidas por incumplir reglas (no se usaron para aprender): {info['excluidas_por_reglas']:,}".replace(",", "."))
    print(f"  Modelo guardado en       : {RUTA_MOTOR_EMPRESA}")
    print("Reinicia el servidor para que la aplicación use el nuevo modelo.")
    print(f"(Mínimo exigido: {MIN_FACTURAS_CALIBRACION} facturas normales.)")


if __name__ == "__main__":
    main()
