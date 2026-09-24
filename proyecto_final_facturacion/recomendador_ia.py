# ==============================================================================
#  [IA-4 / IA-5]  RECOMENDADOR  ·  Lógica difusa + neurona que aprende de las personas
# ------------------------------------------------------------------------------
#  IA-4       : riesgo_difuso(): conjuntos bajo/medio/alto y centroide (lógica difusa, no aprende).
#  IA-5       : NeuronaAprobacion: neurona sigmoide que aprende de aprobar/rechazar propuestas.
#  Se usa en  : web_app.py  ->  pantalla "Recomendar" y decisión humana.
#  Buscar     : Ctrl+F  [IA-  para ver todas las IA del proyecto.
# ==============================================================================

"""Recomendador explicable para corregir alertas de facturación.

Combina reglas expertas, riesgo difuso y una neurona de una capa creada sin
bibliotecas de aprendizaje automático. La neurona aprende únicamente de las
decisiones humanas registradas en la aplicación.
"""

from __future__ import annotations

import json
import math
import os
import threading
from pathlib import Path
from typing import Any

from config import CARPETA_RESULTADOS, TASA_IVA_ESPERADA
from generar_datos import calcular_importes


RUTA_MODELO = CARPETA_RESULTADOS / "neurona_aprobacion.json"
_CANDADO_NEURONA = threading.Lock()
SEVERIDAD_BASE = {
    "monto_atipico": 0.90,
    "impuesto_incorrecto": 0.80,
    "factura_duplicada": 0.75,
    "inconsistencia_aritmetica": 0.70,
    "descuento_atipico": 0.65,
    "operacion_nocturna": 0.55,
}


def _numero(valor: object, defecto: float = 0.0) -> float:
    try:
        return float(valor) if valor is not None else defecto
    except (TypeError, ValueError):
        return defecto


def _limitar(valor: float, minimo: float = 0.0, maximo: float = 1.0) -> float:
    return max(minimo, min(maximo, valor))


# [IA-5] NEURONA DE APROBACIÓN: p = sigmoide(b + W·X). Aprende con cada decisión humana.
class NeuronaAprobacion:
    """Una neurona logística que estima si una sugerencia será aprobada.

    Cada peso representa la importancia aprendida de una característica. El
    ajuste se hace con descenso del gradiente después de cada decisión humana.
    """

    def __init__(self, pesos: list[float] | None = None, sesgo: float = 0.0,
                 ejemplos: int = 0) -> None:
        self.pesos = pesos or [0.0, 0.0, 0.0, 0.0, 0.0]
        self.sesgo = sesgo
        self.ejemplos = ejemplos

    @staticmethod
    def _sigmoide(valor: float) -> float:
        valor = max(-60.0, min(60.0, valor))
        return 1 / (1 + math.exp(-valor))

    def predecir(self, caracteristicas: list[float]) -> float:
        suma = self.sesgo + sum(
            peso * valor for peso, valor in zip(self.pesos, caracteristicas)
        )
        return self._sigmoide(suma)

    def aprender(self, caracteristicas: list[float], aprobada: bool,
                 tasa: float = 0.12) -> float:
        """Ajusta pesos: error = decisión humana - predicción de la neurona."""
        prediccion = self.predecir(caracteristicas)
        # [IA-5] APRENDIZAJE: error = lo que decidió la persona - lo que predijo la neurona.
        error = (1.0 if aprobada else 0.0) - prediccion
        for indice, valor in enumerate(caracteristicas):
            self.pesos[indice] += tasa * error * valor
        self.sesgo += tasa * error
        self.ejemplos += 1
        return self.predecir(caracteristicas)

    @classmethod
    def cargar(cls) -> "NeuronaAprobacion":
        if not RUTA_MODELO.exists():
            return cls()
        try:
            datos = json.loads(RUTA_MODELO.read_text(encoding="utf-8"))
            return cls(datos["pesos"], datos["sesgo"], datos.get("ejemplos", 0))
        except (OSError, ValueError, KeyError):
            return cls()

    def guardar(self) -> None:
        RUTA_MODELO.parent.mkdir(parents=True, exist_ok=True)
        # Se escribe en un archivo temporal y se reemplaza de una vez: si el proceso
        # se interrumpe a mitad de la escritura, el modelo anterior queda intacto.
        temporal = RUTA_MODELO.with_suffix(".tmp")
        temporal.write_text(
            json.dumps(
                {"pesos": self.pesos, "sesgo": self.sesgo, "ejemplos": self.ejemplos},
                indent=2,
            ),
            encoding="utf-8",
        )
        os.replace(temporal, RUTA_MODELO)


def caracteristicas_alerta(factura: dict[str, Any]) -> list[float]:
    """Convierte una alerta en cinco entradas normalizadas para la neurona."""
    tipo = tipo_anomalia_para_recomendacion(factura)
    total = max(_numero(factura.get("total")), 1.0)
    subtotal = _numero(factura.get("subtotal"))
    impuesto = _numero(factura.get("impuesto_valor"))
    esperado = subtotal * (1 + _numero(factura.get("tasa_iva")))
    diferencia = abs(total - esperado) / total
    return [
        SEVERIDAD_BASE.get(tipo, 0.50),
        _limitar(abs(_numero(factura.get("tasa_iva")) - TASA_IVA_ESPERADA) / TASA_IVA_ESPERADA),
        _limitar(_numero(factura.get("descuento_pct"))),
        _limitar(diferencia),
        _limitar(abs(_numero(factura.get("puntaje_ia")))),
    ]


# [IA-4] LÓGICA DIFUSA: severidad -> pertenencia a bajo/medio/alto -> centroide (0 a 100).
def riesgo_difuso(factura: dict[str, Any]) -> dict[str, float]:
    """Aplica lógica difusa y centroide, como en los talleres 3 a 5."""
    caracteristicas = caracteristicas_alerta(factura)
    severidad = max(caracteristicas[0], caracteristicas[1], caracteristicas[3], caracteristicas[4])
    bajo = _limitar(1 - (severidad * 2))
    medio = _limitar(1 - abs((severidad - 0.50) / 0.50))
    alto = _limitar((severidad - 0.35) / 0.65)
    denominador = bajo + medio + alto
    centroide = (20 * bajo + 55 * medio + 90 * alto) / denominador if denominador else 50.0
    return {
        "bajo": round(bajo, 3), "medio": round(medio, 3), "alto": round(alto, 3),
        "porcentaje": round(centroide, 1),
    }


def observacion_especifica(factura: dict[str, Any]) -> dict[str, str]:
    """Indica al analista qué dato de la factura debe comprobar.

    Una alerta de IA no permite inventar un valor correcto. Por eso, cuando no
    hay una regla determinista para recalcularlo, se identifica el campo y el
    soporte que la persona debe validar en vez de proponer un cambio arbitrario.
    """
    tipo = tipo_anomalia_para_recomendacion(factura)
    subtotal = _numero(factura.get("subtotal"))
    impuesto = _numero(factura.get("impuesto_valor"))
    total = _numero(factura.get("total"))
    tasa_iva = _numero(factura.get("tasa_iva"))

    if tipo == "monto_atipico":
        cantidad = _numero(factura.get("cantidad"))
        precio = _numero(factura.get("precio_unitario"))
        return {
            "campo": "Precio unitario",
            "detalle": (
                f"Verifique el precio unitario de ${precio:,.2f} para {cantidad:g} unidad(es). "
                f"Con esos datos, el total facturado es ${total:,.2f}."
            ),
            "accion": "Compare el precio con la cotización, orden de compra o tarifa pactada; si es incorrecto, corrija el precio unitario y recalcule los importes.",
        }
    if tipo == "impuesto_incorrecto":
        impuesto_esperado = round(subtotal * TASA_IVA_ESPERADA, 2)
        return {
            "campo": "Tasa e importe de IVA",
            "detalle": f"La factura usa IVA de {tasa_iva * 100:.1f}% (${impuesto:,.2f}); para este prototipo se espera 19.0% (${impuesto_esperado:,.2f}).",
            "accion": "Corrija la tasa de IVA al 19.0% y actualice el impuesto y el total propuestos.",
        }
    if tipo == "inconsistencia_aritmetica":
        subtotal_esperado, impuesto_esperado, total_esperado = calcular_importes(
            _numero(factura.get("cantidad")), _numero(factura.get("precio_unitario")),
            _numero(factura.get("descuento_pct")), tasa_iva,
        )
        # Si la tarifa declarada es la esperada, pero el IVA no resulta de la
        # base gravable registrada, se explica ese error puntual.  No se debe
        # confundir con un precio alterado: la comparación usa el subtotal que
        # aparece en la propia factura como base gravable.
        impuesto_desde_base = round(subtotal * tasa_iva, 2)
        if (
            abs(tasa_iva - TASA_IVA_ESPERADA) <= 0.0001
            and abs(impuesto - impuesto_desde_base) > 1.00
        ):
            return {
                "campo": "Importe de IVA",
                "detalle": (
                    f"La tasa de IVA indicada es 19.0 %, pero el importe reportado no "
                    f"coincide con la base gravable. IVA esperado: ${impuesto_desde_base:,.2f}; "
                    f"IVA informado: ${impuesto:,.2f}."
                ),
                "accion": "Verifique la base gravable y corrija el importe de IVA; después actualice el total de la factura.",
            }
        return {
            "campo": "Subtotal, impuesto o total",
            "detalle": f"Valores registrados: subtotal ${subtotal:,.2f}, impuesto ${impuesto:,.2f}, total ${total:,.2f}. Valores calculados: ${subtotal_esperado:,.2f}, ${impuesto_esperado:,.2f} y ${total_esperado:,.2f}.",
            "accion": "Conserve los datos comerciales validados y reemplace los importes que no coincidan con el cálculo.",
        }
    if tipo == "factura_duplicada":
        return {
            "campo": "Número de factura",
            "detalle": f"El identificador {factura.get('factura_id', '')} ya aparece en el conjunto de facturas analizado.",
            "accion": "Compare proveedor, fecha, total y soporte con el registro previo antes de contabilizar o anular uno de los documentos.",
        }
    if tipo == "descuento_atipico":
        descuento = _numero(factura.get("descuento_pct"))
        return {
            "campo": "Descuento",
            "detalle": f"La factura contiene un descuento de {descuento * 100:.1f}% sobre el valor comercial.",
            "accion": "Solicite la autorización del descuento y corrija el porcentaje solo si el soporte no lo justifica.",
        }
    if tipo == "operacion_nocturna":
        hora = factura.get("hora", "no registrada")
        return {
            "campo": "Hora de registro",
            "detalle": f"La factura fue registrada a las {hora}:00, fuera del horario configurado de 07:00 a 19:00.",
            "accion": "Verifique la autorización y el comprobante de registro; ajuste la hora únicamente si fue digitada erróneamente.",
        }
    return {
        "campo": "Soporte de la factura",
        "detalle": f"El modelo detectó un patrón inusual en una factura por ${total:,.2f}, pero no hay una regla que permita señalar un único campo incorrecto.",
        "accion": "Contraste los datos con la orden de compra y deje en la observación el campo corregido o la justificación de la validación.",
    }


def tipo_anomalia_para_recomendacion(factura: dict[str, Any]) -> str:
    """Relaciona el motivo de una factura cargada con una recomendacion concreta."""
    tipo = str(factura.get("tipo_anomalia", ""))
    if tipo and tipo != "archivo_cargado":
        return tipo
    motivo = str(factura.get("motivo_alerta", "")).lower()
    if "impuesto" in motivo or "iva" in motivo:
        return "impuesto_incorrecto"
    if "aritm" in motivo:
        return "inconsistencia_aritmetica"
    if "duplic" in motivo:
        return "factura_duplicada"
    if "horario" in motivo or "nocturna" in motivo:
        return "operacion_nocturna"
    if "descuento" in motivo:
        return "descuento_atipico"
    return "monto_atipico"


def generar_recomendacion(factura: dict[str, Any]) -> dict[str, Any]:
    """Genera una propuesta segura; no altera por sí misma la factura original."""
    tipo = tipo_anomalia_para_recomendacion(factura)
    riesgo = riesgo_difuso(factura)
    caracteristicas = caracteristicas_alerta(factura)
    probabilidad = NeuronaAprobacion.cargar().predecir(caracteristicas)
    propuesta: dict[str, Any] = {
        "campos_sugeridos": {}, "automatica": False,
        "observacion_especifica": observacion_especifica(factura),
    }

    if tipo == "impuesto_incorrecto":
        subtotal = _numero(factura.get("subtotal"))
        impuesto = round(subtotal * TASA_IVA_ESPERADA, 2)
        propuesta.update({
            "accion": "Corregir IVA al 19% y recalcular el total",
            "explicacion": "La tasa de IVA no corresponde a la tasa esperada del 19%.",
            "campos_sugeridos": {"tasa_iva": TASA_IVA_ESPERADA, "impuesto_valor": impuesto,
                                  "total": round(subtotal + impuesto, 2)},
            "automatica": True,
        })
    elif tipo == "inconsistencia_aritmetica":
        subtotal, impuesto, total = calcular_importes(
            _numero(factura.get("cantidad")), _numero(factura.get("precio_unitario")),
            _numero(factura.get("descuento_pct")), _numero(factura.get("tasa_iva")),
        )
        propuesta.update({
            "accion": "Recalcular subtotal, IVA y total",
            "explicacion": "Los importes no coinciden con cantidad, precio, descuento e IVA.",
            "campos_sugeridos": {"subtotal": subtotal, "impuesto_valor": impuesto, "total": total},
            "automatica": True,
        })
    elif tipo == "factura_duplicada":
        propuesta.update({
            "accion": "Suspender contabilización hasta verificar el duplicado",
            "explicacion": "Se detectó un identificador de factura repetido. No es seguro eliminarla automáticamente.",
        })
    elif tipo == "descuento_atipico":
        propuesta.update({
            "accion": "Solicitar soporte y validar el descuento",
            "explicacion": "El descuento supera el comportamiento habitual; requiere autorización humana.",
        })
    elif tipo == "operacion_nocturna":
        propuesta.update({
            "accion": "Verificar autorización de operación fuera de horario",
            "explicacion": "La factura fue registrada fuera del horario de operación configurado.",
        })
    else:
        propuesta.update({
            "accion": "Revisión humana del monto atípico",
            "explicacion": "El valor se aleja del patrón esperado; no se debe modificar automáticamente.",
        })

    certeza_regla = 0.96 if propuesta["automatica"] else 0.60
    propuesta.update({
        "riesgo_difuso": riesgo,
        "probabilidad_aprobacion": round(probabilidad * 100, 1),
        "confianza_sugerencia": round(((certeza_regla + probabilidad) / 2) * 100, 1),
        "caracteristicas": [round(valor, 4) for valor in caracteristicas],
    })
    return propuesta


def aprender_de_decision(contexto: dict[str, Any], decision: str) -> float | None:
    """Entrena la neurona solo cuando el humano aprueba o rechaza una propuesta."""
    if decision not in {"aprobada", "rechazada"}:
        return None
    caracteristicas = [float(valor) for valor in contexto.get("caracteristicas", [])]
    if len(caracteristicas) != 5:
        return None
    # Varias personas pueden decidir a la vez: el bloqueo evita que dos aprendizajes
    # se pisen (cargar -> aprender -> guardar debe ocurrir completo, de uno en uno).
    with _CANDADO_NEURONA:
        neurona = NeuronaAprobacion.cargar()
        nueva_probabilidad = neurona.aprender(caracteristicas, decision == "aprobada")
        neurona.guardar()
    return nueva_probabilidad
