"""Orquestación del experimento completo de detección híbrida."""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from detector_ia import DetectorAnomalias
from detector_knn import DetectorKNN
from detector_perceptron import DetectorPerceptron
from evaluacion import calcular_metricas, exportar_resultados, medir_ejecucion
from generar_datos import crear_anomalias, generar_conjuntos
from reglas_negocio import aplicar_reglas
from config import (
    CARPETA_MODELOS, ES_PRODUCCION, MAX_FILAS_ARCHIVO, MIN_FACTURAS_CALIBRACION, PERCENTIL_ALERTA,
    POLITICA_IA, RUTA_INFO_MOTOR_EMPRESA, RUTA_MOTOR_EMPRESA, SEMILLA, VOTOS_MINIMOS_IA,
)


COLUMNAS_FACTURA = (
    "factura_id", "cliente_sintetico", "categoria", "fecha", "hora", "cantidad",
    "precio_unitario", "descuento_pct", "tasa_iva", "subtotal", "impuesto_valor", "total",
)

# Estas columnas no participan en el calculo de IA. Sirven para identificar el
# documento, explicar su origen y conservar una trazabilidad util para auditoria.
COLUMNAS_TRAZABILIDAD = (
    "nit_emisor", "cufe", "tipo_documento", "validacion_dian",
)

# No intervienen en el modelo: conservan el detalle comercial para que la
# persona revisora pueda contrastar la alerta con los conceptos reales.
COLUMNAS_DETALLE_FACTURA = (
    "descripcion_detallada", "detalle_lineas",
)


def preparar_ejemplos_supervisados(calibracion: pd.DataFrame, semilla: int = SEMILLA,
                                   datos_reales: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Prepara ejemplos etiquetados que comparten KNN y el perceptron.

    Estos ejemplos no incluyen las facturas de prueba. Asi los dos modelos
    supervisados aprenden con casos separados antes de emitir su opinion.

    Con datos_reales=True (facturas de la empresa) se usan más ejemplos y las
    anomalías se fabrican a partir de esas mismas facturas, no de datos sintéticos.
    """
    # Demostración: pocos ejemplos, rápida y explicable. Empresa: más variedad.
    cuantas_normales, casos_por_tipo = (1000, 100) if datos_reales else (120, 10)
    normales = calibracion.sample(
        n=min(cuantas_normales, len(calibracion)), random_state=semilla
    ).reset_index(drop=True)
    # Creamos ejemplos de cada tipo para ensenar normal (0) y alerta (1).
    generador = np.random.default_rng(semilla + 17)
    anomalias = crear_anomalias(
        normales, generador, casos_por_tipo=casos_por_tipo, base=normales if datos_reales else None
    )
    return normales, anomalias


def entrenar_segunda_opinion_knn(calibracion: pd.DataFrame, semilla: int = SEMILLA,
                                 datos_reales: bool = False) -> DetectorKNN:
    """Prepara KNN: compara cada factura con cinco ejemplos similares."""
    normales, anomalias = preparar_ejemplos_supervisados(calibracion, semilla, datos_reales)
    detector_knn = DetectorKNN(vecinos=5)
    # fit guarda los vecinos normalizados que KNN consultara en cada prediccion.
    detector_knn.entrenar(normales, anomalias)
    return detector_knn


def entrenar_perceptron(calibracion: pd.DataFrame, semilla: int = SEMILLA,
                        datos_reales: bool = False) -> DetectorPerceptron:
    """Prepara una neurona artificial con las mismas entradas de facturacion."""
    normales, anomalias = preparar_ejemplos_supervisados(calibracion, semilla, datos_reales)
    detector_perceptron = DetectorPerceptron()
    # Este entrenamiento ajusta pesos y sesgo segun los errores de clasificacion.
    detector_perceptron.entrenar(normales, anomalias)
    return detector_perceptron


# [IA-COMBINACIÓN] Aquí se juntan las tres IA (Isolation Forest, KNN y perceptrón).
# Política (config.POLITICA_IA): "mayoria" exige que al menos 2 de las 3 coincidan
# (pocas falsas alarmas); "cualquiera" basta con 1 (máxima sensibilidad).
def aplicar_modelos_ia(facturas: pd.DataFrame, detector: DetectorAnomalias,
                       detector_knn: DetectorKNN,
                       detector_perceptron: DetectorPerceptron) -> pd.DataFrame:
    """Ejecuta Isolation Forest, KNN y perceptron como opiniones complementarias."""
    resultado = detector.predecir(facturas)
    # Guardamos el dictamen original antes de combinarlo con la segunda opinion.
    resultado["alerta_isolation"] = resultado["alerta_ia"]
    resultado = detector_knn.predecir(resultado)
    resultado = detector_perceptron.predecir(resultado)
    # Cada modelo aporta un voto; la política decide cuántos votos hacen falta.
    resultado["votos_ia"] = (
        resultado["alerta_isolation"].astype(int) + resultado["alerta_knn"].astype(int)
        + resultado["alerta_perceptron"].astype(int)
    )
    resultado["alerta_ia"] = resultado["votos_ia"] >= VOTOS_MINIMOS_IA
    return resultado


def ejecutar_experimento(guardar_en_postgres: bool = False, semilla: int = SEMILLA) -> tuple[pd.DataFrame, dict[str, object], DetectorAnomalias]:
    """Genera datos, entrena, detecta alertas y guarda resultados auditables."""
    calibracion, prueba = generar_conjuntos(semilla)
    detector = DetectorAnomalias(PERCENTIL_ALERTA)
    detector.entrenar(calibracion)
    detector_knn = entrenar_segunda_opinion_knn(calibracion, semilla)
    detector_perceptron = entrenar_perceptron(calibracion, semilla)

    def detectar() -> pd.DataFrame:
        con_reglas = aplicar_reglas(prueba)
        con_ia = aplicar_modelos_ia(con_reglas, detector, detector_knn, detector_perceptron)
        con_ia["alerta_hibrida"] = con_ia["alerta_reglas"] | con_ia["alerta_ia"]
        con_ia["motivo_alerta"] = explicar_alertas(con_ia)
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


class ModeloNoDisponible(RuntimeError):
    """El modelo de la empresa falta o está dañado; el mensaje es apto para el usuario."""


@dataclass(frozen=True)
class MotorIA:
    """Reglas + tres modelos ya entrenados, listos para predecir."""

    ids_conocidos: frozenset[str]
    detector: DetectorAnomalias
    detector_knn: DetectorKNN
    detector_perceptron: DetectorPerceptron
    info: dict[str, object]


def _info_demostracion() -> dict[str, object]:
    return {
        "tipo": "demostracion", "facturas": 7000,
        "etiqueta": "Modelo de demostración (datos sintéticos)",
        "politica": POLITICA_IA,
    }


def informacion_modelo() -> dict[str, object]:
    """Describe qué modelo está activo, sin cargarlo ni entrenarlo (es barato)."""
    if RUTA_INFO_MOTOR_EMPRESA.exists():
        try:
            info = json.loads(RUTA_INFO_MOTOR_EMPRESA.read_text(encoding="utf-8"))
            info["politica"] = POLITICA_IA
            return info
        except (OSError, ValueError):
            pass
    return _info_demostracion()


@lru_cache(maxsize=1)
def _motor_de_calibracion() -> MotorIA:
    """Devuelve el motor activo y lo conserva en memoria entre peticiones web.

    - Si existe modelos/motor_empresa.joblib (creado con calibrar_empresa.py) se usa el
      modelo calibrado con las facturas reales de la empresa.
    - Si no, se entrena el modelo de demostración con 7.000 facturas sintéticas
      reproducibles. En producción esto se bloquea: analizar facturas reales con un
      modelo sintético daría resultados sin valor.

    Los modelos solo se usan para predecir, así que compartirlos entre peticiones es seguro.
    """
    if RUTA_MOTOR_EMPRESA.exists():
        try:
            guardado = joblib.load(RUTA_MOTOR_EMPRESA)
            return MotorIA(
                frozenset(), guardado["detector"], guardado["knn"], guardado["perceptron"],
                informacion_modelo(),
            )
        except Exception as error:  # archivo dañado o de otra versión de scikit-learn
            raise ModeloNoDisponible(
                "No se pudo cargar el modelo de la empresa (modelos/motor_empresa.joblib). "
                "Vuelve a ejecutar calibrar_empresa.py con el histórico de facturas."
            ) from error
    if ES_PRODUCCION:
        raise ModeloNoDisponible(
            "Falta calibrar el modelo con las facturas de la empresa. Ejecuta: "
            "py calibrar_empresa.py historico.csv"
        )
    calibracion, _ = generar_conjuntos(guardar=False)
    detector = DetectorAnomalias(PERCENTIL_ALERTA)
    detector.entrenar(calibracion)
    return MotorIA(
        frozenset(calibracion["factura_id"]), detector,
        entrenar_segunda_opinion_knn(calibracion), entrenar_perceptron(calibracion),
        _info_demostracion(),
    )


def calibrar_motor_empresa(historico: pd.DataFrame) -> dict[str, object]:
    """Entrena y guarda el modelo con el histórico de facturas NORMALES de la empresa.

    1. Valida el histórico con las mismas reglas de carga.
    2. Excluye las facturas que ya incumplen una regla (IVA, aritmética, duplicado,
       horario) para no enseñarle al modelo que eso es "normal".
    3. Isolation Forest aprende el patrón normal de la empresa; KNN y el perceptrón
       aprenden con ejemplos normales reales y anomalías fabricadas sobre ellos.
    """
    preparadas = preparar_facturas_cargadas(historico, limite_filas=None)
    con_reglas = aplicar_reglas(preparadas)
    normales = preparadas.loc[~con_reglas["alerta_reglas"]].reset_index(drop=True)
    if len(normales) < MIN_FACTURAS_CALIBRACION:
        raise ValueError(
            f"Se necesitan al menos {MIN_FACTURAS_CALIBRACION} facturas normales para calibrar; "
            f"el histórico aporta {len(normales)} tras excluir las que incumplen reglas."
        )
    detector = DetectorAnomalias(PERCENTIL_ALERTA)
    detector.entrenar(normales)
    detector_knn = entrenar_segunda_opinion_knn(normales, datos_reales=True)
    detector_perceptron = entrenar_perceptron(normales, datos_reales=True)

    ahora = datetime.now()
    info = {
        "tipo": "empresa", "facturas": int(len(normales)),
        "excluidas_por_reglas": int(len(preparadas) - len(normales)),
        "fecha": ahora.strftime("%Y-%m-%d %H:%M"),
        "etiqueta": f"Modelo calibrado con {len(normales):,} facturas de la empresa ({ahora:%d/%m/%Y})".replace(",", "."),
    }
    CARPETA_MODELOS.mkdir(parents=True, exist_ok=True)
    joblib.dump({"detector": detector, "knn": detector_knn, "perceptron": detector_perceptron},
                RUTA_MOTOR_EMPRESA)
    RUTA_INFO_MOTOR_EMPRESA.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    _motor_de_calibracion.cache_clear()
    return info


def restablecer_motor_demostracion() -> None:
    """Elimina el modelo de la empresa y vuelve al modelo de demostración."""
    for ruta in (RUTA_MOTOR_EMPRESA, RUTA_INFO_MOTOR_EMPRESA):
        ruta.unlink(missing_ok=True)
    _motor_de_calibracion.cache_clear()


def _finalizar_analisis(con_reglas: pd.DataFrame, motor: MotorIA) -> pd.DataFrame:
    """Aplica las IA y arma alerta híbrida, motivo y prioridad (todo vectorizado)."""
    resultado = aplicar_modelos_ia(con_reglas, motor.detector, motor.detector_knn, motor.detector_perceptron)
    resultado["alerta_hibrida"] = resultado["alerta_reglas"] | resultado["alerta_ia"]
    resultado["motivo_alerta"] = explicar_alertas(resultado)
    resultado["prioridad_alerta"] = clasificar_prioridades(resultado)
    return resultado


def analizar_factura_manual(factura: dict[str, object]) -> tuple[pd.Series, float]:
    """Analiza una factura escrita por el usuario con el mismo motor del experimento.

    Los modelos se conservan en memoria; ninguna factura analizada modifica el aprendizaje.
    """
    motor = _motor_de_calibracion()
    con_reglas = aplicar_reglas(pd.DataFrame([factura]), ids_conocidos=motor.ids_conocidos)
    resultado = _finalizar_analisis(con_reglas, motor)
    return resultado.iloc[0], float(motor.detector.umbral)


def preparar_facturas_cargadas(facturas: pd.DataFrame,
                               limite_filas: int | None = MAX_FILAS_ARCHIVO) -> pd.DataFrame:
    """Valida una tabla CSV/Excel y la adapta al formato interno del detector.

    limite_filas=None desactiva el tope (lo usan la calibración y el proceso por lotes).
    """
    faltantes = [columna for columna in COLUMNAS_FACTURA if columna not in facturas.columns]
    if faltantes:
        raise ValueError("Faltan estas columnas: " + ", ".join(faltantes))
    if facturas.empty:
        raise ValueError("El archivo no contiene facturas.")
    if limite_filas is not None and len(facturas) > limite_filas:
        raise ValueError(f"Por seguridad, carga máximo {limite_filas:,} facturas por archivo.".replace(",", "."))

    resultado = facturas.loc[:, COLUMNAS_FACTURA].copy()
    # La plantilla puede incluir estos datos adicionales. Si no estan presentes,
    # no se bloquea una carga academica: se guarda un valor claro de "no reportado".
    valores_predeterminados = {
        "nit_emisor": "NO-REPORTADO",
        "cufe": "",
        "tipo_documento": "Factura electronica",
        "validacion_dian": "No verificada por FactuGuard",
    }
    for columna in COLUMNAS_TRAZABILIDAD:
        resultado[columna] = (
            facturas[columna].fillna("").astype(str).str.strip()
            if columna in facturas.columns else valores_predeterminados[columna]
        )
        resultado[columna] = resultado[columna].replace("", valores_predeterminados[columna])
    for columna in COLUMNAS_DETALLE_FACTURA:
        resultado[columna] = facturas[columna] if columna in facturas.columns else ""
    for columna in ("factura_id", "cliente_sintetico", "categoria", "fecha"):
        resultado[columna] = resultado[columna].fillna("").astype(str).str.strip()
    if (resultado["factura_id"] == "").any() or (resultado["cliente_sintetico"] == "").any():
        raise ValueError("Cada fila debe tener factura_id y un código de cliente anónimo.")
    fechas = pd.to_datetime(resultado["fecha"], errors="coerce")
    if fechas.isna().any():
        raise ValueError("La columna fecha debe usar fechas válidas, por ejemplo 2026-09-11.")
    resultado["fecha"] = fechas.dt.strftime("%Y-%m-%d")
    resultado["categoria"] = resultado["categoria"].replace("", "Sin categoria")

    columnas_numericas = (
        "hora", "cantidad", "precio_unitario", "descuento_pct", "tasa_iva", "subtotal",
        "impuesto_valor", "total",
    )
    for columna in columnas_numericas:
        resultado[columna] = pd.to_numeric(resultado[columna], errors="coerce")
    if resultado[list(columnas_numericas)].isna().any().any():
        raise ValueError("Las columnas numéricas deben contener solo números; hora usa valores de 0 a 23.")
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


def analizar_facturas_cargadas(facturas: pd.DataFrame,
                              limite_filas: int | None = MAX_FILAS_ARCHIVO) -> tuple[pd.DataFrame, float]:
    """Analiza un lote de facturas importadas sin almacenarlo en PostgreSQL."""
    facturas_preparadas = preparar_facturas_cargadas(facturas, limite_filas)
    motor = _motor_de_calibracion()
    con_reglas = aplicar_reglas(facturas_preparadas, ids_conocidos=motor.ids_conocidos)
    return _finalizar_analisis(con_reglas, motor), float(motor.detector.umbral)


def clasificar_prioridades(resultado: pd.DataFrame) -> pd.Series:
    """Asigna prioridad para que la bandeja muestre primero los riesgos mayores."""
    motivo = resultado["motivo_alerta"].astype(str).str.lower()
    # Impuestos, cálculos o posible duplicación se revisan primero; montos, descuentos
    # y horarios inusuales necesitan revisión pero no bloquean por sí solos.
    critica = motivo.str.contains("impuesto|inconsistencia|duplic", regex=True)
    prioridad = np.where(~resultado["alerta_hibrida"].to_numpy(dtype=bool), "baja",
                         np.where(critica.to_numpy(), "alta", "media"))
    return pd.Series(prioridad, index=resultado.index)


def explicar_alertas(resultado: pd.DataFrame) -> pd.Series:
    """Escribe el motivo de cada alerta (vectorizado: sirve para cientos de miles de filas)."""
    filas = len(resultado)
    hibrida = (resultado["alerta_reglas"] | resultado["alerta_ia"]).to_numpy(dtype=bool)

    def bandera(columna: str) -> np.ndarray:
        if columna not in resultado.columns:
            return np.zeros(filas, dtype=bool)
        return resultado[columna].to_numpy(dtype=bool) & hibrida

    def valores(columna: str) -> np.ndarray:
        if columna not in resultado.columns:
            return np.zeros(filas)
        return resultado[columna].to_numpy(dtype=float)

    motivos_reglas = resultado["motivos_reglas"].to_numpy(dtype=object)
    probabilidad_knn = valores("probabilidad_knn") * 100
    margen = valores("margen_perceptron")

    partes = [
        (bandera("alerta_reglas"), lambda i: str(motivos_reglas[i])),
        (bandera("alerta_isolation"), lambda i: "Patrón inusual detectado por Isolation Forest"),
        (bandera("alerta_knn"),
         lambda i: f"KNN la clasificó como similar a alertas conocidas ({probabilidad_knn[i]:.0f}%)"),
        (bandera("alerta_perceptron"),
         lambda i: f"Perceptrón activó una alerta por suma ponderada (Z={margen[i]:.2f})"),
    ]
    texto = np.full(filas, "", dtype=object)
    for activa, construir in partes:
        # Solo se recorren las filas con alerta, que son una fracción pequeña del lote.
        for i in np.flatnonzero(activa):
            texto[i] = construir(i) if texto[i] == "" else f"{texto[i]}; {construir(i)}"
    return pd.Series(np.where(hibrida & (texto != ""), texto, "Sin alerta"), index=resultado.index)


def leer_csv_facturas(contenido: bytes) -> pd.DataFrame:
    """Lee un CSV exportado desde Excel o un ERP (coma o punto y coma, UTF-8 o Windows-1252)."""
    try:
        texto = contenido.decode("utf-8-sig")
        codificacion = "utf-8-sig"
    except UnicodeDecodeError:
        codificacion = "cp1252"
        texto = contenido.decode(codificacion)
    primeras = "\n".join(texto.splitlines()[:5])
    encabezado = primeras.splitlines()[0] if primeras else ""
    separador = ";" if encabezado.count(";") > encabezado.count(",") else ","
    # Excel en español escribe los decimales con coma cuando separa columnas con ";".
    coma_decimal = separador == ";" and bool(re.search(r"\d,\d", primeras))
    return pd.read_csv(
        io.StringIO(texto), sep=separador, decimal="," if coma_decimal else ".",
        thousands="." if coma_decimal else None,
    )


def leer_tabla_facturas(ruta: Path) -> pd.DataFrame:
    """Lee un archivo de facturas desde disco (.csv o .xlsx) para los procesos por lotes."""
    extension = ruta.suffix.lower()
    if extension == ".csv":
        return leer_csv_facturas(ruta.read_bytes())
    if extension == ".xlsx":
        return pd.read_excel(ruta)
    raise ValueError("Formato no admitido. Usa un archivo .csv o .xlsx.")
