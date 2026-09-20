"""Analiza un archivo grande de facturas fuera del navegador (proceso por lotes).

La carga web sirve para archivos medianos. Para volúmenes grandes (por ejemplo
el cierre del mes de todo un ERP) se usa este comando, que no depende de los
tiempos de espera de una petición web y guarda el resultado en PostgreSQL para
que el equipo lo revise en "Decisiones humanas".

Uso (en la carpeta del proyecto):
    py analizar_lote.py facturas_octubre.csv
    py analizar_lote.py facturas_octubre.xlsx --usuario duverney --exportar alertas_octubre.csv
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from base_datos import guardar_carga_archivo, obtener_id_usuario
from servicio import analizar_facturas_cargadas, informacion_modelo, leer_tabla_facturas


def main() -> None:
    parser = argparse.ArgumentParser(description="Analiza un archivo grande de facturas.")
    parser.add_argument("archivo", help="CSV o Excel con las columnas de la plantilla")
    parser.add_argument("--usuario", help="nombre de usuario al que se atribuye la carga")
    parser.add_argument("--exportar", help="ruta de un CSV donde guardar solo las alertas")
    argumentos = parser.parse_args()

    usuario_id = None
    if argumentos.usuario:
        usuario_id = obtener_id_usuario(argumentos.usuario)
        if usuario_id is None:
            raise SystemExit(f"No existe el usuario activo '{argumentos.usuario}'.")

    ruta = Path(argumentos.archivo)
    print(f"Modelo activo: {informacion_modelo()['etiqueta']}")
    inicio = time.perf_counter()
    tabla = leer_tabla_facturas(ruta)
    print(f"{len(tabla):,} filas leídas en {time.perf_counter() - inicio:.1f} s".replace(",", "."))

    try:
        resultado, _ = analizar_facturas_cargadas(tabla, limite_filas=None)
    except (ValueError, RuntimeError) as error:
        raise SystemExit(f"No se pudo analizar: {error}") from error
    print(f"Análisis terminado en {time.perf_counter() - inicio:.1f} s")

    carga_id = guardar_carga_archivo(resultado, ruta.name, usuario_id)
    alertas = resultado.loc[resultado["alerta_hibrida"]]
    print(f"Guardado en PostgreSQL (carga #{carga_id}) — total {time.perf_counter() - inicio:.1f} s")
    print()
    print(f"Facturas analizadas : {len(resultado):,}".replace(",", "."))
    print(f"Alertas             : {len(alertas):,} ({len(alertas) / len(resultado) * 100:.2f} %)".replace(",", "."))
    for prioridad, cantidad in alertas["prioridad_alerta"].value_counts().items():
        print(f"  prioridad {prioridad:<6}: {cantidad:,}".replace(",", "."))
    if argumentos.exportar:
        columnas = ["factura_id", "nit_emisor", "fecha", "total", "prioridad_alerta", "motivo_alerta"]
        alertas.loc[:, columnas].to_csv(argumentos.exportar, index=False, encoding="utf-8-sig")
        print(f"Alertas exportadas a {argumentos.exportar}")


if __name__ == "__main__":
    main()
