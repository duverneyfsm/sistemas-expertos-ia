"""Cálculo y exportación de métricas del experimento."""

from __future__ import annotations

import json
import time

import pandas as pd
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score

from config import RUTA_ALERTAS, RUTA_METRICAS


def calcular_metricas(etiquetas_reales: pd.Series, alertas: pd.Series) -> dict[str, float | int]:
    """Obtiene matriz de confusión y métricas entendibles para la entrega."""
    vn, fp, fn, vp = confusion_matrix(etiquetas_reales, alertas, labels=[0, 1]).ravel()
    especificidad = vn / (vn + fp) if (vn + fp) else 0.0
    return {
        "verdaderos_positivos": int(vp),
        "falsos_positivos": int(fp),
        "falsos_negativos": int(fn),
        "verdaderos_negativos": int(vn),
        "precision": round(float(precision_score(etiquetas_reales, alertas, zero_division=0)), 4),
        "exhaustividad": round(float(recall_score(etiquetas_reales, alertas, zero_division=0)), 4),
        "f1": round(float(f1_score(etiquetas_reales, alertas, zero_division=0)), 4),
        "especificidad": round(float(especificidad), 4),
    }


def exportar_resultados(facturas: pd.DataFrame, metricas: dict[str, object],
                        segundos_proceso: float) -> None:
    """Guarda alertas y métricas para que puedan auditarse después."""
    RUTA_ALERTAS.parent.mkdir(parents=True, exist_ok=True)
    facturas.loc[facturas["alerta_hibrida"]].to_csv(RUTA_ALERTAS, index=False)
    contenido = dict(metricas)
    contenido["registros_evaluados"] = int(len(facturas))
    contenido["alertas_hibridas"] = int(facturas["alerta_hibrida"].sum())
    contenido["milisegundos_por_registro"] = round((segundos_proceso / len(facturas)) * 1000, 4)
    contenido["alertas_por_tipo_inyectado"] = {
        str(tipo): int(cantidad)
        for tipo, cantidad in facturas.loc[facturas["alerta_hibrida"]].groupby("tipo_anomalia").size().items()
    }
    RUTA_METRICAS.write_text(json.dumps(contenido, indent=2, ensure_ascii=False), encoding="utf-8")


def medir_ejecucion(funcion):
    """Ejecuta una función y devuelve su resultado junto con su duración."""
    inicio = time.perf_counter()
    resultado = funcion()
    return resultado, time.perf_counter() - inicio
