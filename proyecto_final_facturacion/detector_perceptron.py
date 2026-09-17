"""Tercera opinion: un perceptron construido desde cero con NumPy.

El perceptron es la unidad mas sencilla de una red neuronal. Recibe los datos
de una factura, los multiplica por pesos aprendidos, suma un sesgo y aplica una
funcion escalon: 0 significa factura parecida a normal y 1 alerta potencial.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from config import CARACTERISTICAS_MODELO, SEMILLA


class DetectorPerceptron:
    """Clasificador supervisado con una sola neurona artificial.

    No es una red profunda: esta clase implementa exactamente la neurona del
    taller. Sirve como opinion adicional junto a reglas, Isolation Forest y KNN.
    """

    def __init__(self, tasa_aprendizaje: float = 0.08, epocas: int = 80) -> None:
        # Estos valores me ayudan a controlar cuanto cambian los pesos y cuantas
        # veces la neurona revisa los ejemplos para aprender de sus errores.
        self.tasa_aprendizaje = tasa_aprendizaje
        self.epocas = epocas
        # Este escalador me ayuda a que pesos, porcentajes y horas sean comparables.
        self.escalador = StandardScaler()
        self.pesos: np.ndarray | None = None
        self.sesgo = 0.0
        self.entrenado = False

    @staticmethod
    def _caracteristicas(facturas: pd.DataFrame) -> pd.DataFrame:
        """Prepara las siete entradas numericas que recibe la neurona."""
        datos = facturas.copy()
        # Este calculo me ayuda a incluir el descuento en pesos, no solo su porcentaje.
        datos["valor_descuento"] = (
            datos["cantidad"] * datos["precio_unitario"] * datos["descuento_pct"]
        )
        return datos.loc[:, CARACTERISTICAS_MODELO].astype(float)

    @staticmethod
    def funcion_escalon(valor_z: float) -> int:
        """Convierte la suma de la neurona en una salida binaria 0 o 1."""
        # Esta condicion me ayuda a representar la activacion del perceptron.
        return int(valor_z >= 0)

    def entrenar(self, facturas_normales: pd.DataFrame, facturas_anomalas: pd.DataFrame) -> None:
        """Ajusta pesos con ejemplos normales (0) y anomalias conocidas (1)."""
        ejemplos = pd.concat([facturas_normales, facturas_anomalas], ignore_index=True)
        etiquetas = np.array([0] * len(facturas_normales) + [1] * len(facturas_anomalas), dtype=int)
        entradas = self.escalador.fit_transform(self._caracteristicas(ejemplos))

        # Estos pesos iniciales y este sesgo empiezan en cero, como una neurona sin experiencia.
        self.pesos = np.zeros(entradas.shape[1], dtype=float)
        self.sesgo = 0.0
        rng = np.random.default_rng(SEMILLA)

        for _ in range(self.epocas):
            errores = 0
            # Este orden aleatorio me ayuda a que la neurona no memorice el orden de las filas.
            for indice in rng.permutation(len(entradas)):
                entrada = entradas[indice]
                esperada = etiquetas[indice]
                # Z = X.W + b es la combinacion lineal estudiada en la sesion 11.
                valor_z = float(np.dot(entrada, self.pesos) + self.sesgo)
                obtenida = self.funcion_escalon(valor_z)
                error = esperada - obtenida
                if error:
                    # Esta regla me ayuda a mover pesos y sesgo hacia la respuesta correcta.
                    self.pesos += self.tasa_aprendizaje * error * entrada
                    self.sesgo += self.tasa_aprendizaje * error
                    errores += 1
            # Si no hubo errores, la neurona ya separo los ejemplos disponibles.
            if errores == 0:
                break
        self.entrenado = True

    def predecir(self, facturas: pd.DataFrame) -> pd.DataFrame:
        """Anade el margen Z y la alerta binaria del perceptron a cada factura."""
        if not self.entrenado or self.pesos is None:
            raise RuntimeError("El perceptron debe entrenarse antes de predecir.")
        resultado = facturas.copy()
        entradas = self.escalador.transform(self._caracteristicas(resultado))
        # Este producto punto me ayuda a calcular la suma ponderada de cada factura.
        margenes = entradas @ self.pesos + self.sesgo
        resultado["margen_perceptron"] = margenes
        resultado["alerta_perceptron"] = (margenes >= 0).astype(bool)
        return resultado
