"""Generación reproducible de facturas sintéticas.

No se usan clientes, facturas ni montos reales. Cada ejecución con la misma
semilla produce los mismos conjuntos de calibración y prueba.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from config import (
    HORA_FIN, HORA_INICIO, RUTA_CALIBRACION, RUTA_PRUEBA, SEMILLA, TASA_IVA_ESPERADA,
    TASAS_IVA_PERMITIDAS,
)


def calcular_importes(cantidad: float, precio_unitario: float,
                      descuento_pct: float, tasa_iva: float) -> tuple[float, float, float]:
    """Calcula subtotal, impuesto y total tal como lo haría una factura."""
    subtotal = round(cantidad * precio_unitario * (1 - descuento_pct), 2)
    impuesto = round(subtotal * tasa_iva, 2)
    total = round(subtotal + impuesto, 2)
    return subtotal, impuesto, total


def crear_factura_normal(rng: np.random.Generator, factura_id: str) -> dict[str, object]:
    """Crea una factura coherente dentro del comportamiento esperado."""
    cantidad = int(rng.integers(1, 11))
    # Valores expresados en pesos colombianos (COP) para que el laboratorio y
    # la factura visual manejen montos coherentes con una pyme simulada.
    precio_unitario = round(float(rng.uniform(35_000, 450_000)), 2)
    descuento_pct = round(float(rng.choice([0, 0.03, 0.05, 0.08, 0.10, 0.15])), 2)
    subtotal, impuesto_valor, total = calcular_importes(
        cantidad, precio_unitario, descuento_pct, TASA_IVA_ESPERADA
    )
    fecha = pd.Timestamp("2026-08-01") + pd.Timedelta(days=int(rng.integers(0, 31)))

    return {
        "factura_id": factura_id,
        "cliente_sintetico": f"CLI-{int(rng.integers(1, 401)):04d}",
        "categoria": str(rng.choice(["Soporte", "Consultoría", "Licencias", "Mantenimiento"])),
        "fecha": fecha.strftime("%Y-%m-%d"),
        "hora": int(rng.integers(HORA_INICIO, HORA_FIN)),
        "cantidad": cantidad,
        "precio_unitario": precio_unitario,
        "descuento_pct": descuento_pct,
        "tasa_iva": TASA_IVA_ESPERADA,
        "subtotal": subtotal,
        "impuesto_valor": impuesto_valor,
        "total": total,
        "es_anomalia": 0,
        "tipo_anomalia": "normal",
    }


def crear_facturas_normales(cantidad: int, prefijo: str,
                            rng: np.random.Generator) -> pd.DataFrame:
    """Construye una tabla de facturas normales con identificadores únicos."""
    filas = [crear_factura_normal(rng, f"{prefijo}-{indice:05d}") for indice in range(1, cantidad + 1)]
    return pd.DataFrame(filas)


def _marcar_anomalia(fila: dict[str, object], tipo: str) -> dict[str, object]:
    fila["es_anomalia"] = 1
    fila["tipo_anomalia"] = tipo
    return fila


def _tarifa_iva_invalida() -> float:
    """Una tarifa que las reglas rechazan, para simular un IVA mal aplicado."""
    return next(tarifa for tarifa in (0.05, 0.08, 0.16, 0.25, 0.27) if tarifa not in TASAS_IVA_PERMITIDAS)


def crear_anomalias(prueba_normal: pd.DataFrame, rng: np.random.Generator,
                    casos_por_tipo: int = 3, base: pd.DataFrame | None = None) -> pd.DataFrame:
    """Inyecta seis tipos de anomalías controladas sobre facturas normales.

    Sin `base` se parte de facturas sintéticas (demostración). Con `base` se
    parte de facturas reales normales de la empresa, para que KNN y el
    perceptrón aprendan qué es una anomalía *en sus propios montos y hábitos*.
    """
    anomalias: list[dict[str, object]] = []
    consecutivo = 1

    def nueva_normal(numero: int) -> dict[str, object]:
        if base is None:
            return crear_factura_normal(rng, f"FAC-A-{numero:05d}")
        fila = base.iloc[int(rng.integers(0, len(base)))].to_dict()
        fila["factura_id"] = f"FAC-A-{numero:05d}"
        fila["es_anomalia"] = 0
        fila["tipo_anomalia"] = "normal"
        return fila

    for _ in range(casos_por_tipo):
        fila = nueva_normal(consecutivo)
        consecutivo += 1
        fila["precio_unitario"] = round(float(fila["precio_unitario"]) * float(rng.uniform(14, 20)), 2)
        fila["subtotal"], fila["impuesto_valor"], fila["total"] = calcular_importes(
            float(fila["cantidad"]), float(fila["precio_unitario"]),
            float(fila["descuento_pct"]), float(fila["tasa_iva"]),
        )
        anomalias.append(_marcar_anomalia(fila, "monto_atipico"))

    for _ in range(casos_por_tipo):
        fila = nueva_normal(consecutivo)
        consecutivo += 1
        fila["tasa_iva"] = _tarifa_iva_invalida()
        fila["subtotal"], fila["impuesto_valor"], fila["total"] = calcular_importes(
            float(fila["cantidad"]), float(fila["precio_unitario"]),
            float(fila["descuento_pct"]), float(fila["tasa_iva"]),
        )
        anomalias.append(_marcar_anomalia(fila, "impuesto_incorrecto"))

    # Se repite un identificador que ya apareció en una factura normal. La regla
    # solo marcará esta segunda aparición, no la factura original.
    for indice in range(casos_por_tipo):
        fila = prueba_normal.iloc[indice].to_dict()
        anomalias.append(_marcar_anomalia(fila, "factura_duplicada"))

    for _ in range(casos_por_tipo):
        fila = nueva_normal(consecutivo)
        consecutivo += 1
        fila["total"] = round(float(fila["total"]) + float(rng.uniform(70, 300)), 2)
        anomalias.append(_marcar_anomalia(fila, "inconsistencia_aritmetica"))

    for _ in range(casos_por_tipo):
        fila = nueva_normal(consecutivo)
        consecutivo += 1
        fila["hora"] = int(rng.integers(0, HORA_INICIO))
        anomalias.append(_marcar_anomalia(fila, "operacion_nocturna"))

    for _ in range(casos_por_tipo):
        fila = nueva_normal(consecutivo)
        consecutivo += 1
        fila["descuento_pct"] = round(float(rng.uniform(0.65, 0.85)), 2)
        fila["subtotal"], fila["impuesto_valor"], fila["total"] = calcular_importes(
            float(fila["cantidad"]), float(fila["precio_unitario"]),
            float(fila["descuento_pct"]), float(fila["tasa_iva"]),
        )
        anomalias.append(_marcar_anomalia(fila, "descuento_atipico"))

    return pd.DataFrame(anomalias)


def generar_conjuntos(semilla: int = SEMILLA, guardar: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Genera calibración normal y 30 facturas de prueba para la demostración.

    Con guardar=False no escribe los CSV: así el simulador y la carga de
    archivos no modifican datos/ en cada petición web.

    La prueba contiene 12 casos normales y 3 casos de cada una de las seis
    anomalías conocidas. Así es pequeña de explicar, pero conserva todos
    los tipos de alerta del proyecto.
    """
    rng = np.random.default_rng(semilla)
    calibracion = crear_facturas_normales(7000, "FAC-C", rng)
    prueba_normal = crear_facturas_normales(12, "FAC-P", rng)
    anomalias = crear_anomalias(prueba_normal, rng)
    prueba = pd.concat([prueba_normal, anomalias], ignore_index=True)

    if guardar:
        RUTA_CALIBRACION.parent.mkdir(parents=True, exist_ok=True)
        calibracion.to_csv(RUTA_CALIBRACION, index=False)
        prueba.to_csv(RUTA_PRUEBA, index=False)
    return calibracion, prueba


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genera datos sintéticos de facturación.")
    parser.parse_args()
    calibracion_generada, prueba_generada = generar_conjuntos()
    print(f"Calibración: {len(calibracion_generada)} facturas en {RUTA_CALIBRACION}")
    print(f"Prueba: {len(prueba_generada)} facturas en {RUTA_PRUEBA}")
