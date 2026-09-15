"""Orquestación del experimento completo de detección híbrida."""

from __future__ import annotations

import numpy as np
import pandas as pd

from detector_ia import DetectorAnomalias
from detector_knn import DetectorKNN
from evaluacion import calcular_metricas, exportar_resultados, medir_ejecucion
from generar_datos import crear_anomalias, generar_conjuntos
from reglas_negocio import aplicar_reglas
from config import SEMILLA


COLUMNAS_FACTURA = (
    "factura_id", "cliente_sintetico", "categoria", "fecha", "hora", "cantidad",
    "precio_unitario", "descuento_pct", "tasa_iva", "subtotal", "impuesto_valor", "total",
)


def entrenar_segunda_opinion_knn(calibracion: pd.DataFrame, semilla: int = SEMILLA) -> DetectorKNN:
    """Prepara KNN con ejemplos normales y anomalias conocidas separados de la prueba.

    Isolation Forest detecta rarezas sin etiquetas. KNN complementa esa mirada:
    compara una factura con vecinos previamente marcados como normales (0) o
    anomalos (1). No se usan las facturas que se van a evaluar, evitando que el
    modelo vea la respuesta antes de hacer la prediccion.
    """
    # Limitamos los ejemplos para que la demostracion sea rapida y explicable.
    normales = calibracion.sample(n=min(120, len(calibracion)), random_state=semilla).reset_index(drop=True)
    # Creamos 10 ejemplos de cada una de las seis anomalias para ensenar ambas clases a KNN.
    generador = np.random.default_rng(semilla + 17)
    anomalias = crear_anomalias(normales, generador, casos_por_tipo=10)
    detector_knn = DetectorKNN(vecinos=5)
    # fit guarda los vecinos normalizados que KNN consultara en cada prediccion.
    detector_knn.entrenar(normales, anomalias)
    return detector_knn


def aplicar_modelos_ia(facturas: pd.DataFrame, detector: DetectorAnomalias,
                       detector_knn: DetectorKNN) -> pd.DataFrame:
    """Ejecuta Isolation Forest y KNN, conservando una explicacion de cada uno."""
    resultado = detector.predecir(facturas)
    # Guardamos el dictamen original antes de combinarlo con la segunda opinion.
    resultado["alerta_isolation"] = resultado["alerta_ia"]
    resultado = detector_knn.predecir(resultado)
    # La alerta de IA se activa si cualquiera de los dos modelos encuentra riesgo.
    resultado["alerta_ia"] = resultado["alerta_isolation"] | resultado["alerta_knn"]
    return resultado


def ejecutar_experimento(guardar_en_postgres: bool = False, semilla: int = SEMILLA) -> tuple[pd.DataFrame, dict[str, object], DetectorAnomalias]:
    """Genera datos, entrena, detecta alertas y guarda resultados auditables."""
    calibracion, prueba = generar_conjuntos(semilla)
    detector = DetectorAnomalias()
    detector.entrenar(calibracion)
    detector_knn = entrenar_segunda_opinion_knn(calibracion, semilla)

    def detectar() -> pd.DataFrame:
        con_reglas = aplicar_reglas(prueba)
        con_ia = aplicar_modelos_ia(con_reglas, detector, detector_knn)
        con_ia["alerta_hibrida"] = con_ia["alerta_reglas"] | con_ia["alerta_ia"]
        con_ia["motivo_alerta"] = con_ia.apply(_explicar_alerta, axis=1)
        return con_ia

    resultado, duracion = medir_ejecucion(detectar)
    metricas = calcular_metricas(resultado["es_anomalia"], resultado["alerta_hibrida"])
    # La misma medida se guarda en JSON y PostgreSQL para compararla después.
    metricas["milisegundos_por_registro"] = round((duracion / len(resultado)) * 1000, 4)
    exportar_resultados(resultado, metricas, duracion)
    if guardar_en_postgres:
        # La importación se hace aquí para que el modo CSV funcione aunque la
        # persona aún no haya configurado PostgreSQL.
        from base_datos import guardar_experimento
        guardar_experimento(calibracion, resultado, metricas, semilla)
    return resultado, metricas, detector


def analizar_factura_manual(factura: dict[str, object]) -> tuple[pd.Series, float]:
    """Analiza una factura escrita por el usuario con el mismo motor del experimento.

    En cada prueba se calibra el modelo con las 7.000 facturas normales
    reproducibles. AsÃ­ el simulador manual no conserva datos de una prueba
    anterior y permite explicar el resultado con las mismas condiciones.
    """
    calibracion, _ = generar_conjuntos()
    detector = DetectorAnomalias()
    detector.entrenar(calibracion)
    detector_knn = entrenar_segunda_opinion_knn(calibracion)

    factura_manual = pd.DataFrame([factura])
    ids_calibracion = set(calibracion["factura_id"])
    con_reglas = aplicar_reglas(factura_manual, ids_conocidos=ids_calibracion)
    resultado = aplicar_modelos_ia(con_reglas, detector, detector_knn)
    resultado["alerta_hibrida"] = resultado["alerta_reglas"] | resultado["alerta_ia"]
    resultado["motivo_alerta"] = resultado.apply(_explicar_alerta, axis=1)
    return resultado.iloc[0], float(detector.umbral)


def preparar_facturas_cargadas(facturas: pd.DataFrame) -> pd.DataFrame:
    """Valida una tabla CSV/Excel y la adapta al formato interno del detector."""
    faltantes = [columna for columna in COLUMNAS_FACTURA if columna not in facturas.columns]
    if faltantes:
        raise ValueError("Faltan estas columnas: " + ", ".join(faltantes))
    if facturas.empty:
        raise ValueError("El archivo no contiene facturas.")
    if len(facturas) > 5000:
        raise ValueError("Por seguridad, carga m&aacute;ximo 5.000 facturas por archivo.")

    resultado = facturas.loc[:, COLUMNAS_FACTURA].copy()
    for columna in ("factura_id", "cliente_sintetico", "categoria", "fecha"):
        resultado[columna] = resultado[columna].fillna("").astype(str).str.strip()
    if (resultado["factura_id"] == "").any() or (resultado["cliente_sintetico"] == "").any():
        raise ValueError("Cada fila debe tener factura_id y un c&oacute;digo de cliente an&oacute;nimo.")
    fechas = pd.to_datetime(resultado["fecha"], errors="coerce")
    if fechas.isna().any():
        raise ValueError("La columna fecha debe usar fechas v&aacute;lidas, por ejemplo 2026-09-11.")
    resultado["fecha"] = fechas.dt.strftime("%Y-%m-%d")
    resultado["categoria"] = resultado["categoria"].replace("", "Sin categoria")

    columnas_numericas = (
        "hora", "cantidad", "precio_unitario", "descuento_pct", "tasa_iva", "subtotal",
        "impuesto_valor", "total",
    )
    for columna in columnas_numericas:
        resultado[columna] = pd.to_numeric(resultado[columna], errors="coerce")
    if resultado[list(columnas_numericas)].isna().any().any():
        raise ValueError("Las columnas num&eacute;ricas deben contener solo n&uacute;meros; hora usa valores de 0 a 23.")
    if not resultado["hora"].between(0, 23).all() or (resultado["cantidad"] <= 0).any():
        raise ValueError("La hora debe estar entre 0 y 23 y la cantidad debe ser mayor que cero.")
    if (resultado[["precio_unitario", "subtotal", "impuesto_valor", "total"]] < 0).any().any():
        raise ValueError("Los importes monetarios no pueden ser negativos.")
    if not resultado["descuento_pct"].between(0, 100).all() or not resultado["tasa_iva"].between(0, 100).all():
        raise ValueError("Descuento e IVA deben estar entre 0 y 100.")

    # El archivo acepta 19 o 0.19 para IVA. Si llega como porcentaje entero,
    # se transforma a decimal porque las reglas y el modelo usan 0.19.
    for columna in ("descuento_pct", "tasa_iva"):
        resultado[columna] = resultado[columna].where(resultado[columna] <= 1, resultado[columna] / 100)
    resultado["hora"] = resultado["hora"].astype(int)
    resultado["es_anomalia"] = False
    resultado["tipo_anomalia"] = "archivo_cargado"
    return resultado


def analizar_facturas_cargadas(facturas: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """Analiza un lote de facturas importadas sin almacenarlo en PostgreSQL."""
    facturas_preparadas = preparar_facturas_cargadas(facturas)
    calibracion, _ = generar_conjuntos()
    detector = DetectorAnomalias()
    detector.entrenar(calibracion)
    detector_knn = entrenar_segunda_opinion_knn(calibracion)
    con_reglas = aplicar_reglas(facturas_preparadas, ids_conocidos=set(calibracion["factura_id"]))
    resultado = aplicar_modelos_ia(con_reglas, detector, detector_knn)
    resultado["alerta_hibrida"] = resultado["alerta_reglas"] | resultado["alerta_ia"]
    resultado["motivo_alerta"] = resultado.apply(_explicar_alerta, axis=1)
    return resultado, float(detector.umbral)


def _explicar_alerta(fila: pd.Series) -> str:
    motivos: list[str] = []
    if bool(fila["alerta_reglas"]):
        motivos.append(str(fila["motivos_reglas"]))
    if bool(fila.get("alerta_isolation", False)):
        motivos.append("Patrón inusual detectado por Isolation Forest")
    if bool(fila.get("alerta_knn", False)):
        probabilidad = float(fila.get("probabilidad_knn", 0)) * 100
        motivos.append(f"KNN la clasificó como similar a alertas conocidas ({probabilidad:.0f}%)")
    return "; ".join(motivos) if motivos else "Sin alerta"
