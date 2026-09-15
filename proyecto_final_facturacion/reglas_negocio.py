"""Reglas explícitas y explicables para revisar facturas."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from config import HORA_FIN, HORA_INICIO, TASA_IVA_ESPERADA


def aplicar_reglas(facturas: pd.DataFrame,
                   ids_conocidos: Iterable[str] | None = None) -> pd.DataFrame:
    """Marca incumplimientos tributarios, aritméticos, duplicados y de horario."""
    resultado = facturas.copy()
    base_esperada = (resultado["cantidad"] * resultado["precio_unitario"] *
                      (1 - resultado["descuento_pct"])).round(2)
    impuesto_esperado = (base_esperada * resultado["tasa_iva"]).round(2)
    total_esperado = (base_esperada + impuesto_esperado).round(2)

    resultado["regla_impuesto"] = (resultado["tasa_iva"] - TASA_IVA_ESPERADA).abs() > 0.0001
    # Las facturas en COP suelen redondear a pesos enteros. Se admite hasta un
    # peso de diferencia para no marcar como error un IVA correctamente redondeado.
    tolerancia_monetaria = 1.00
    resultado["regla_aritmetica"] = (
        (resultado["subtotal"] - base_esperada).abs() > tolerancia_monetaria
    ) | (
        (resultado["impuesto_valor"] - impuesto_esperado).abs() > tolerancia_monetaria
    ) | (
        (resultado["total"] - total_esperado).abs() > tolerancia_monetaria
    )
    resultado["regla_duplicado"] = resultado["factura_id"].duplicated(keep="first")
    if ids_conocidos is not None:
        resultado["regla_duplicado"] |= resultado["factura_id"].isin(set(ids_conocidos))
    resultado["regla_horario"] = (
        (resultado["hora"] < HORA_INICIO) | (resultado["hora"] >= HORA_FIN)
    )

    nombres_reglas = {
        "regla_impuesto": "Impuesto diferente del 19 %",
        "regla_aritmetica": "Inconsistencia aritmética",
        "regla_duplicado": "Factura duplicada",
        "regla_horario": "Operación fuera de horario",
    }

    def explicar(fila: pd.Series) -> str:
        motivos = [texto for columna, texto in nombres_reglas.items() if bool(fila[columna])]
        return "; ".join(motivos) if motivos else "Sin incumplimientos explícitos"

    columnas_reglas = list(nombres_reglas)
    resultado["alerta_reglas"] = resultado[columnas_reglas].any(axis=1)
    resultado["motivos_reglas"] = resultado.apply(explicar, axis=1)
    return resultado
