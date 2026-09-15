"""Modelo no supervisado para identificar patrones inusuales."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from config import CARACTERISTICAS_MODELO, SEMILLA


class DetectorAnomalias:
    """Isolation Forest calibrado únicamente con facturas normales."""

    def __init__(self, percentil_alerta: float = 0.99) -> None:
        self.percentil_alerta = percentil_alerta
        self.escalador = StandardScaler()
        self.modelo = IsolationForest(
            n_estimators=100,
            max_samples=256,
            random_state=SEMILLA,
            n_jobs=-1,
        )
        self.umbral: float | None = None

    @staticmethod
    def _caracteristicas(facturas: pd.DataFrame) -> pd.DataFrame:
        # El valor monetario del descuento complementa el porcentaje: así el
        # modelo distingue un descuento muy alto sobre una venta grande de uno
        # habitual sobre una factura de bajo valor.
        datos = facturas.copy()
        datos["valor_descuento"] = (
            datos["cantidad"] * datos["precio_unitario"] * datos["descuento_pct"]
        )
        return datos.loc[:, CARACTERISTICAS_MODELO].astype(float)

    def entrenar(self, facturas_normales: pd.DataFrame) -> None:
        """Ajusta el modelo y fija el umbral con el percentil de calibración."""
        datos = self._caracteristicas(facturas_normales)
        datos_escalados = self.escalador.fit_transform(datos)
        self.modelo.fit(datos_escalados)
        puntajes = -self.modelo.score_samples(datos_escalados)
        self.umbral = float(np.quantile(puntajes, self.percentil_alerta))

    def predecir(self, facturas: pd.DataFrame) -> pd.DataFrame:
        """Añade puntaje de rareza y alerta del modelo a una tabla de facturas."""
        if self.umbral is None:
            raise RuntimeError("El detector debe entrenarse antes de hacer predicciones.")
        resultado = facturas.copy()
        datos_escalados = self.escalador.transform(self._caracteristicas(resultado))
        resultado["puntaje_ia"] = -self.modelo.score_samples(datos_escalados)
        resultado["alerta_ia"] = resultado["puntaje_ia"] >= self.umbral
        return resultado
