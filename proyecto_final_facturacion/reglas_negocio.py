# ==============================================================================
#  [REGLAS]  REGLAS DE NEGOCIO  ·  Sistema experto (NO aprende)
# ------------------------------------------------------------------------------
#  Qué hace   : comprueba condiciones escritas a mano: IVA, aritmética, duplicados y horario.
#  Salida     : alerta_reglas y motivos_reglas (explicación en texto).
#  Se usa en  : servicio.py  ->  se combina con las IA en alerta_hibrida.
# ==============================================================================

"""Reglas explícitas y explicables para revisar facturas."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from config import HORA_FIN, HORA_INICIO, TASAS_IVA_PERMITIDAS


def aplicar_reglas(facturas: pd.DataFrame,
                   ids_conocidos: Iterable[str] | None = None) -> pd.DataFrame:
    """Marca incumplimientos tributarios, aritméticos, duplicados y de horario."""
    resultado = facturas.copy()
    base_esperada = (resultado["cantidad"] * resultado["precio_unitario"] *
                      (1 - resultado["descuento_pct"])).round(2)
    impuesto_esperado = (base_esperada * resultado["tasa_iva"]).round(2)
    total_esperado = (base_esperada + impuesto_esperado).round(2)

    # La tarifa es válida si coincide con alguna de las permitidas (config.TASAS_IVA_PERMITIDAS).
    tarifa_valida = np.zeros(len(resultado), dtype=bool)
    for tarifa in TASAS_IVA_PERMITIDAS:
        tarifa_valida |= ((resultado["tasa_iva"] - tarifa).abs() <= 0.0001).to_numpy()
    resultado["regla_impuesto"] = ~tarifa_valida
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
    # Con un NIT de emisor reportado, dos proveedores distintos pueden usar el
    # mismo número de factura sin que sea un duplicado: la clave incluye el NIT.
    if "nit_emisor" in resultado.columns:
        clave_documento = resultado["nit_emisor"].astype(str) + "|" + resultado["factura_id"].astype(str)
    else:
        clave_documento = resultado["factura_id"]
    resultado["regla_duplicado"] = clave_documento.duplicated(keep="first")
    if ids_conocidos is not None:
        resultado["regla_duplicado"] |= resultado["factura_id"].isin(set(ids_conocidos))
    resultado["regla_horario"] = (
        (resultado["hora"] < HORA_INICIO) | (resultado["hora"] >= HORA_FIN)
    )

    if len(TASAS_IVA_PERMITIDAS) == 1:
        texto_impuesto = f"Impuesto diferente del {TASAS_IVA_PERMITIDAS[0] * 100:g} %"
    else:
        tarifas = ", ".join(f"{tarifa * 100:g} %" for tarifa in TASAS_IVA_PERMITIDAS)
        texto_impuesto = f"Impuesto fuera de las tarifas permitidas ({tarifas})"
    nombres_reglas = {
        "regla_impuesto": texto_impuesto,
        "regla_aritmetica": "Inconsistencia aritmética",
        "regla_duplicado": "Factura duplicada",
        "regla_horario": "Operación fuera de horario",
    }

    columnas_reglas = list(nombres_reglas)
    resultado["alerta_reglas"] = resultado[columnas_reglas].any(axis=1)
    # Se arma el texto columna por columna (vectorizado): con cientos de miles de
    # facturas, una función por fila sería el cuello de botella.
    motivos = np.full(len(resultado), "", dtype=object)
    for columna, texto in nombres_reglas.items():
        activa = resultado[columna].to_numpy(dtype=bool)
        motivos = np.where(activa, np.where(motivos == "", texto, motivos + "; " + texto), motivos)
    resultado["motivos_reglas"] = np.where(motivos == "", "Sin incumplimientos explícitos", motivos)
    return resultado
