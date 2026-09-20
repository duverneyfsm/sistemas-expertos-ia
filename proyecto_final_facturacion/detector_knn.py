# ==============================================================================
#  [IA-2]  KNN (K VECINOS MÁS CERCANOS, K = 5)  ·  Aprendizaje SUPERVISADO
# ------------------------------------------------------------------------------
#  Qué hace   : compara una factura con 5 ejemplos parecidos y vota: normal o alerta.
#  Aprende de : 120 facturas normales + 60 anómalas ya etiquetadas (0 = normal, 1 = alerta).
#  Entradas   : las mismas 7 variables, escaladas con StandardScaler.
#  Salida     : probabilidad_knn (0 a 1) y alerta_knn (True si la mayoría es anómala).
#  Se usa en  : servicio.aplicar_modelos_ia()  ->  alerta_hibrida
#  Buscar     : Ctrl+F  [IA-  para ver todas las IA del proyecto.
# ==============================================================================

"""Segunda opinion supervisada basada en K vecinos mas cercanos (KNN)."""

from __future__ import annotations

import pandas as pd
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import StandardScaler

from config import CARACTERISTICAS_MODELO


class DetectorKNN:
    """Clasifica una factura por similitud con facturas normales y anomalas conocidas.

    KNN no aprende una formula como una red neuronal. Conserva los ejemplos de
    entrenamiento y, al recibir una factura, consulta sus cinco vecinos mas
    cercanos. El escalador es indispensable porque las variables de facturacion
    tienen unidades muy distintas: pesos, porcentajes y horas.
    """

    def __init__(self, vecinos: int = 5) -> None:
        # K impar evita empates entre las clases normal (0) y alerta (1).
        self.vecinos = vecinos
        # StandardScaler convierte cada variable a una escala comparable.
        self.escalador = StandardScaler()
        # weights='distance' da mas influencia a los vecinos realmente cercanos.
        self.modelo = KNeighborsClassifier(n_neighbors=vecinos, weights="distance")
        self.entrenado = False

    @staticmethod
    def _caracteristicas(facturas: pd.DataFrame) -> pd.DataFrame:
        """Prepara las mismas variables numericas usadas por el detector principal."""
        datos = facturas.copy()
        # El valor absoluto del descuento aporta contexto al porcentaje aplicado.
        datos["valor_descuento"] = (
            datos["cantidad"] * datos["precio_unitario"] * datos["descuento_pct"]
        )
        return datos.loc[:, CARACTERISTICAS_MODELO].astype(float)

    def entrenar(self, facturas_normales: pd.DataFrame, facturas_anomalas: pd.DataFrame) -> None:
        """Guarda ejemplos etiquetados: 0 normal y 1 con una anomalia conocida."""
        ejemplos = pd.concat([facturas_normales, facturas_anomalas], ignore_index=True)
        etiquetas = [0] * len(facturas_normales) + [1] * len(facturas_anomalas)
        datos_escalados = self.escalador.fit_transform(self._caracteristicas(ejemplos))
        # [IA-2] KNN no calcula una fórmula: solo guarda los ejemplos etiquetados.
        self.modelo.fit(datos_escalados, etiquetas)
        self.entrenado = True

    def predecir(self, facturas: pd.DataFrame) -> pd.DataFrame:
        """Anade la probabilidad KNN y una alerta cuando la mayoria es anomala."""
        if not self.entrenado:
            raise RuntimeError("El detector KNN debe entrenarse antes de predecir.")
        resultado = facturas.copy()
        datos_escalados = self.escalador.transform(self._caracteristicas(resultado))
        # La columna 1 representa la probabilidad de pertenecer a la clase alerta.
        # [IA-2] Vota entre los 5 vecinos más cercanos (los más próximos pesan más).
        resultado["probabilidad_knn"] = self.modelo.predict_proba(datos_escalados)[:, 1]
        resultado["alerta_knn"] = self.modelo.predict(datos_escalados).astype(bool)
        return resultado
