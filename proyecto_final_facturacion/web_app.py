"""Servidor web local de FactuGuard IA.

Flask muestra la interfaz en el navegador, mientras que los módulos existentes
conservan la lógica de IA, seguridad y PostgreSQL.
"""

from __future__ import annotations

import hmac
import io
import logging
import os
import re
import secrets
import time
import zipfile
from collections import Counter
from datetime import timedelta
from functools import wraps
from logging.handlers import RotatingFileHandler
from xml.etree import ElementTree as ET

import pandas as pd
from dotenv import load_dotenv
from psycopg.errors import UniqueViolation
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for

from base_datos import (
    actualizar_estado_factura_cargada, aplicar_ajuste_recomendado, aplicar_ajuste_recomendado_cargado,
    autenticar_usuario, conectar, guardar_carga_archivo, guardar_recomendacion_cargada,
    eliminar_carga_archivo, eliminar_factura_cargada,
    limpiar_facturas_manuales,
    limpiar_experimentos_sinteticos,
    obtener_alertas, obtener_alertas_cargadas, obtener_alertas_de_carga, obtener_facturas_de_carga,
    obtener_metricas_revision_usuario, obtener_resumen_cargas_usuario,
    obtener_alerta_sintetica, obtener_factura_cargada, obtener_factura_sintetica,
    obtener_factura_sintetica_por_alerta,
    obtener_recomendacion, obtener_recomendacion_cargada, obtener_ultimo_experimento,
    guardar_recomendacion, registrar_decision_recomendacion,
    registrar_decision_recomendacion_cargada,
)
from config import (
    CARPETA_REGISTROS, ES_PRODUCCION, MAX_ARCHIVO_MB, MAX_FILAS_ARCHIVO, POLITICA_IA, RUTA_ENV,
)
from recomendador_ia import (
    aprender_de_decision, generar_recomendacion, observacion_especifica,
    tipo_anomalia_para_recomendacion,
)
from servicio import (
    ModeloNoDisponible, analizar_factura_manual, analizar_facturas_cargadas, ejecutar_experimento,
    informacion_modelo, leer_csv_facturas,
)


load_dotenv(RUTA_ENV)
app = Flask(__name__)
# La llave real se genera durante configurar_postgres.py y no se publica en Git.
_llave_secreta = os.getenv("FLASK_SECRET_KEY")
if not _llave_secreta:
    if ES_PRODUCCION:
        raise RuntimeError("Define FLASK_SECRET_KEY en el archivo .env antes de iniciar en producción.")
    _llave_secreta = secrets.token_urlsafe(32)
if ES_PRODUCCION and (len(_llave_secreta) < 24 or _llave_secreta.startswith("SE_GENERA")):
    raise RuntimeError("FLASK_SECRET_KEY es demasiado corta o es el texto de ejemplo; genera una nueva.")
app.config["SECRET_KEY"] = _llave_secreta
app.config["MAX_CONTENT_LENGTH"] = MAX_ARCHIVO_MB * 1024 * 1024  # Tamaño máximo de un archivo cargado.
# La sesión se cierra sola tras 8 horas y la cookie no es legible desde JavaScript.
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Con HTTPS la cookie viaja solo cifrada. Si aún no hay HTTPS, poner COOKIE_SEGURA=0 en .env.
app.config["SESSION_COOKIE_SECURE"] = ES_PRODUCCION and os.getenv("COOKIE_SEGURA", "1") != "0"
if os.getenv("CONFIAR_PROXY") == "1":
    # Detrás de un proxy inverso (nginx, IIS, Caddy) se respeta la IP y el protocolo reales.
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Registro de eventos para auditoría y soporte: logs/factuguard.log (rota automáticamente).
CARPETA_REGISTROS.mkdir(parents=True, exist_ok=True)
_manejador = RotatingFileHandler(
    CARPETA_REGISTROS / "factuguard.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
)
_manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
app.logger.addHandler(_manejador)
app.logger.setLevel(logging.INFO)


def error_seguro(error: Exception) -> str:
    """Texto de un error apto para mostrar al usuario.

    Los mensajes de validación (ValueError) y de modelo no disponible se muestran
    tal cual. Cualquier otro error (por ejemplo de la base de datos) se registra y,
    en producción, se reemplaza por una referencia para no revelar datos internos.
    """
    if isinstance(error, (ValueError, ModeloNoDisponible)):
        return str(error)
    referencia = secrets.token_hex(3).upper()
    app.logger.error("Error interno (ref. %s)", referencia, exc_info=error)
    if ES_PRODUCCION:
        return f"Error interno. Informa al administrador con la referencia {referencia}."
    return str(error)


@app.errorhandler(413)
def archivo_demasiado_grande(error):
    """Devuelve un mensaje útil cuando el navegador supera el límite permitido."""
    flash(f"El archivo supera el límite de {MAX_ARCHIVO_MB} MB.", "danger")
    return redirect(url_for("cargar_facturas"))


@app.errorhandler(403)
def sin_permiso(error):
    flash("Tu rol no tiene permiso para esta acción. Pide ayuda a un administrador.", "warning")
    return redirect(url_for("dashboard") if "usuario" in session else url_for("login"))


@app.errorhandler(400)
def solicitud_invalida(error):
    flash("El formulario expiró o no es válido. Recarga la página e inténtalo de nuevo.", "warning")
    return redirect(url_for("dashboard") if "usuario" in session else url_for("login"))


def token_csrf() -> str:
    """Token secreto por sesión; cada formulario POST debe devolverlo (protección CSRF)."""
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = token_csrf


@app.before_request
def verificar_csrf():
    """Rechaza cualquier POST que no traiga el token de la sesión (evita acciones forzadas desde otros sitios)."""
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        enviado = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
        esperado = session.get("csrf", "")
        if not esperado or not hmac.compare_digest(str(enviado), str(esperado)):
            app.logger.warning("POST rechazado por token CSRF inválido: %s desde %s", request.path, request.remote_addr)
            abort(400)


@app.after_request
def cabeceras_de_seguridad(respuesta):
    respuesta.headers.setdefault("X-Content-Type-Options", "nosniff")
    respuesta.headers.setdefault("X-Frame-Options", "DENY")
    respuesta.headers.setdefault("Referrer-Policy", "same-origin")
    return respuesta


@app.context_processor
def contexto_global():
    """Datos que todas las páginas pueden mostrar: modelo activo y límites de carga."""
    return {
        "modelo_activo": informacion_modelo(), "limite_mb": MAX_ARCHIVO_MB,
        "limite_filas": MAX_FILAS_ARCHIVO, "politica_ia": POLITICA_IA,
    }


# Bloqueo temporal de fuerza bruta: 5 intentos fallidos por usuario y equipo cada 15 minutos.
_INTENTOS_LOGIN: dict[str, list[float]] = {}
_MAX_INTENTOS_LOGIN = 5
_VENTANA_LOGIN = 15 * 60


def _clave_login(usuario: str) -> str:
    return f"{request.remote_addr}|{usuario.strip().lower()}"


def _login_bloqueado(clave: str) -> bool:
    ahora = time.time()
    recientes = [momento for momento in _INTENTOS_LOGIN.get(clave, []) if ahora - momento < _VENTANA_LOGIN]
    _INTENTOS_LOGIN[clave] = recientes
    if len(_INTENTOS_LOGIN) > 10_000:  # evita que el diccionario crezca sin límite
        _INTENTOS_LOGIN.clear()
    return len(recientes) >= _MAX_INTENTOS_LOGIN


def requiere_inicio_sesion(vista):
    """Evita que alguien visite las páginas privadas sin autenticarse."""
    @wraps(vista)
    def protegida(*args, **kwargs):
        if "usuario" not in session:
            flash("Inicia sesión para acceder al dashboard.", "warning")
            return redirect(url_for("login"))
        return vista(*args, **kwargs)
    return protegida


def requiere_rol(*roles: str):
    """Restringe una vista a ciertos roles (se usa debajo de requiere_inicio_sesion)."""
    def decorador(vista):
        @wraps(vista)
        def protegida(*args, **kwargs):
            if session.get("usuario", {}).get("rol") not in roles:
                abort(403)
            return vista(*args, **kwargs)
        return protegida
    return decorador


ETIQUETAS_TIPO = {
    "monto_atipico": "Monto atípico",
    "impuesto_incorrecto": "Impuesto incorrecto",
    "factura_duplicada": "Factura duplicada",
    "inconsistencia_aritmetica": "Inconsistencia aritmética",
    "descuento_atipico": "Descuento atípico",
    "operacion_nocturna": "Operación nocturna",
}


@app.template_filter("etiqueta_tipo")
def etiqueta_tipo(tipo: object) -> str:
    """Muestra el tipo de anomalía con tildes: operacion_nocturna -> Operación nocturna."""
    texto = str(tipo)
    return ETIQUETAS_TIPO.get(texto, texto.replace("_", " ").capitalize())


def datos_graficos(alertas: list[dict[str, object]]) -> tuple[list[str], list[int], list[str], list[int]]:
    """Convierte alertas de PostgreSQL en listas simples para Chart.js."""
    por_tipo = Counter(etiqueta_tipo(alerta["tipo_anomalia"]) for alerta in alertas)
    por_origen = Counter(str(alerta["origen"]).replace("_", " + ").upper() for alerta in alertas)
    return list(por_tipo.keys()), list(por_tipo.values()), list(por_origen.keys()), list(por_origen.values())


def valores_iniciales_simulador() -> dict[str, str]:
    """Entrega una factura normal precargada para iniciar la demostración manual."""
    return {
        "factura_id": "MAN-001", "cliente_sintetico": "CLIENTE-DEMO", "categoria": "Soporte",
        "nit_emisor": "900000000", "cufe": "", "tipo_documento": "Factura electronica",
        "validacion_dian": "No verificada por FactuGuard",
        "fecha": "2026-09-11", "hora": "10", "cantidad": "2", "precio_unitario": "150000",
        "descuento_pct": "0", "tasa_iva": "19", "subtotal": "300000",
        "impuesto_valor": "57000", "total": "357000",
    }


def leer_factura_manual(formulario) -> dict[str, object]:
    """Valida y convierte campos del formulario a los tipos usados por el modelo."""
    valores = valores_iniciales_simulador()
    for campo in valores:
        valores[campo] = formulario.get(campo, valores[campo]).strip()
    if not valores["factura_id"]:
        raise ValueError("Escribe un identificador para la factura.")
    if not valores["cliente_sintetico"]:
        raise ValueError("Escribe un código de cliente anónimo.")
    if not valores["fecha"]:
        raise ValueError("Selecciona una fecha válida.")
    try:
        hora = int(valores["hora"])
        cantidad = float(valores["cantidad"])
        precio = float(valores["precio_unitario"])
        descuento = float(valores["descuento_pct"])
        tasa_iva = float(valores["tasa_iva"])
        subtotal = float(valores["subtotal"])
        impuesto = float(valores["impuesto_valor"])
        total = float(valores["total"])
    except ValueError as error:
        raise ValueError("Completa todos los valores numéricos con números válidos.") from error
    if not 0 <= hora <= 23 or cantidad <= 0 or precio < 0:
        raise ValueError("La hora debe estar entre 0 y 23; cantidad y precio deben ser válidos.")
    if not 0 <= descuento <= 100 or not 0 <= tasa_iva <= 100:
        raise ValueError("El descuento y el IVA se escriben como porcentajes entre 0 y 100.")
    if subtotal < 0 or impuesto < 0 or total < 0:
        raise ValueError("Subtotal, impuesto y total no pueden ser negativos.")
    return {
        "factura_id": valores["factura_id"].upper(),
        "cliente_sintetico": valores["cliente_sintetico"].upper(),
        "nit_emisor": valores["nit_emisor"].upper() or "NO-REPORTADO",
        "cufe": valores["cufe"].upper(), "tipo_documento": valores["tipo_documento"],
        "validacion_dian": valores["validacion_dian"],
        "categoria": valores["categoria"], "fecha": valores["fecha"], "hora": hora,
        "cantidad": cantidad, "precio_unitario": precio, "descuento_pct": descuento / 100,
        "tasa_iva": tasa_iva / 100, "subtotal": subtotal, "impuesto_valor": impuesto,
        "total": total, "es_anomalia": False, "tipo_anomalia": "manual",
    }


def _numero_pdf(valor: str) -> float:
    """Convierte importes como $1.234.567,89 o $1,234,567.89 a número."""
    coincidencia = re.search(r"\d[\d.,]*", valor)
    texto = coincidencia.group() if coincidencia else ""
    if not texto:
        raise ValueError("El PDF contiene un importe vacío.")
    if "," in texto and "." in texto:
        separador_decimal = "," if texto.rfind(",") > texto.rfind(".") else "."
        separador_miles = "." if separador_decimal == "," else ","
        texto = texto.replace(separador_miles, "").replace(separador_decimal, ".")
    elif "," in texto:
        partes = texto.split(",")
        texto = texto.replace(",", ".") if len(partes[-1]) <= 2 else texto.replace(",", "")
    elif texto.count(".") > 1:
        partes = texto.split(".")
        texto = "".join(partes[:-1]) + "." + partes[-1] if len(partes[-1]) <= 2 else "".join(partes)
    return float(texto)


def _buscar_en_pdf(texto: str, etiquetas: str, obligatorio: bool = True) -> str | None:
    """Busca el valor situado después de una etiqueta habitual de factura."""
    patron = rf"(?:{etiquetas})\s*(?:[:#-]|COP|\$)*\s*([A-Za-z0-9][A-Za-z0-9.,/\- ]{{0,70}})"
    coincidencia = re.search(patron, texto, flags=re.IGNORECASE)
    if coincidencia:
        return coincidencia.group(1).strip()
    if obligatorio:
        raise ValueError(f"No se encontró '{etiquetas}' en el PDF.")
    return None


def _extraer_detalle_tabular_pdf(texto: str) -> dict[str, str] | None:
    """Lee una fila de detalle cuando los encabezados del PDF son gráficos.

    Algunos emisores dibujan los encabezados (Cantidad, Precio unitario,
    Subtotal...) como una imagen. El texto seleccionable conserva la fila de
    valores, pero no sus nombres; por eso buscar solo ``Cantidad:`` da como
    resultado el valor por defecto 1. Esta expresión identifica el orden de
    columnas común: referencia, descripción, cantidad, unidad, precio, IVA,
    valor IVA y subtotal.
    """
    patron = re.compile(
        r"^\s*\d{6,}\s+\d+\.\s+"
        r"(?P<descripcion>.+?)\s+"
        r"(?P<cantidad>\d+(?:[.,]\d+)?)\s+"
        r"(?P<unidad>[A-Z0-9.\-]+)\s+"
        r"(?P<precio>\$?\s*\d[\d.,]*)\s+"
        r"IVA\s*(?P<tasa>\d+(?:[.,]\d+)?)\s*%?\s+"
        r"(?P<impuesto>\$?\s*\d[\d.,]*)\s+"
        r"(?P<subtotal>\$?\s*\d[\d.,]*)\s*$",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    coincidencia = patron.search(texto)
    return coincidencia.groupdict() if coincidencia else None


def _extraer_detalles_tabulares_pdf(texto: str) -> list[dict[str, str]]:
    """Obtiene todas las líneas completas de una tabla de productos en un PDF."""
    patron = re.compile(
        r"^\s*\d{6,}\s+\d+\.\s+"
        r"(?P<descripcion>.+?)\s+"
        r"(?P<cantidad>\d+(?:[.,]\d+)?)\s+"
        r"(?P<unidad>[A-Z0-9.\-]+)\s+"
        r"(?P<precio>\$?\s*\d[\d.,]*)\s+"
        r"IVA\s*(?P<tasa>\d+(?:[.,]\d+)?)\s*%?\s+"
        r"(?P<impuesto>\$?\s*\d[\d.,]*)\s+"
        r"(?P<subtotal>\$?\s*\d[\d.,]*)\s*$",
        flags=re.IGNORECASE | re.MULTILINE,
    )
    return [coincidencia.groupdict() for coincidencia in patron.finditer(texto)]


def leer_factura_pdf(archivo) -> pd.DataFrame:
    """Extrae una factura digital de un PDF con campos etiquetados en español.

    No aplica OCR: si el documento es una imagen escaneada sin texto, la persona
    debe usar la prueba manual o convertirlo primero con OCR.
    """
    try:
        from pypdf import PdfReader
        lector = PdfReader(archivo)
        # Conservamos los saltos de línea: una fila de productos se interpreta
        # mejor como tabla que como un único párrafo.
        texto_por_lineas = "\n".join(pagina.extract_text() or "" for pagina in lector.pages)
    except Exception as error:
        raise ValueError("No fue posible leer el PDF. Verifica que no esté dañado o protegido.") from error
    texto = re.sub(r"\s+", " ", texto_por_lineas)
    caracteres_legibles = sum(caracter.isalnum() for caracter in texto)
    if len(texto.strip()) < 30 or caracteres_legibles / max(len(texto), 1) < 0.35:
        raise ValueError("El PDF no contiene texto seleccionable. Si es escaneado, usa OCR o la prueba manual.")

    def valor_numerico(etiquetas: str, obligatorio: bool = True) -> str | None:
        patron = rf"(?<![A-Za-z])(?:{etiquetas})\b(?:[:#-]|COP|\$|\s)*(\d[\d.,]*)"
        coincidencia = re.search(patron, texto, flags=re.IGNORECASE)
        if coincidencia:
            return coincidencia.group(1)
        if obligatorio:
            raise ValueError(f"No se encontró el valor de '{etiquetas}' en el PDF.")
        return None

    identificador_encontrado = re.search(
        r"factura(?:\s+(?:n[úu]mero|no\.?))?\s*[:#-]?\s*([A-Z0-9]+(?:-[A-Z0-9]+)+)",
        texto, flags=re.IGNORECASE,
    )
    if not identificador_encontrado:
        # Formato habitual en representaciones gráficas DIAN: el consecutivo
        # aparece después de "Factura electrónica de venta". El punto cubre
        # además el carácter de reemplazo que algunos PDF usan para la tilde.
        identificador_encontrado = re.search(
            r"\bfactura\s+electr.?nica(?:\s+de\s+venta)?\s*"
            r"([A-Z]{1,5}\d{4,})\b",
            texto, flags=re.IGNORECASE,
        )
    if not identificador_encontrado:
        # Algunos proveedores imprimen el consecutivo inmediatamente antes de
        # la leyenda "Factura electrónica", sin la etiqueta en la misma línea.
        identificador_encontrado = re.search(
            r"\b([A-Z]{1,5}\d{6,})\s*(?=FACTURA\s+ELECTR[ÓO]NICA)",
            texto, flags=re.IGNORECASE,
        )
    if not identificador_encontrado:
        # Algunos comprobantes de venta solo imprimen un consecutivo numérico
        # junto a la fecha y la hora, sin el rótulo "Factura".
        identificador_encontrado = re.search(
            r"\b(\d{4,10})\s+(?=\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s+(?:[01]?\d|2[0-3]):\d{2})",
            texto,
        )
    if not identificador_encontrado:
        raise ValueError("No se encontró el número de factura en el PDF.")
    identificador = identificador_encontrado.group(1)
    fecha_encontrada = re.search(
        r"fecha(?:\s+(?:de\s+)?emisi[oó]n)?\s*[:#-]?\s*(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        texto, flags=re.IGNORECASE,
    )
    if not fecha_encontrada:
        # La misma disposición usada por algunos comercios para el consecutivo
        # deja la fecha inmediatamente a su derecha, sin escribir "Fecha".
        fecha_encontrada = re.search(
            rf"{re.escape(identificador)}\s+(\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}}|\d{{4}}-\d{{2}}-\d{{2}})",
            texto,
        )
    if not fecha_encontrada:
        # Algunos generadores sustituyen la vocal acentuada por � al extraer
        # texto. Aceptamos cualquier carácter entre "emisi" y "n".
        fecha_encontrada = re.search(
            r"fecha(?:\s+(?:de\s+)?emisi.n)?\s*[:#-]?\s*"
            r"(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            texto, flags=re.IGNORECASE,
        )
    if not fecha_encontrada:
        raise ValueError("No se encontró una fecha válida en el PDF.")
    fecha_valor = pd.to_datetime(fecha_encontrada.group(1), dayfirst=True, errors="coerce")
    if pd.isna(fecha_valor):
        raise ValueError("La fecha del PDF no es válida.")

    detalles_tabulares = _extraer_detalles_tabulares_pdf(texto_por_lineas)
    detalle_tabular = detalles_tabulares[0] if detalles_tabulares else None
    cantidad_texto = detalle_tabular["cantidad"] if detalle_tabular else valor_numerico(r"cantidad", obligatorio=False)
    cantidad = _numero_pdf(cantidad_texto) if cantidad_texto else 1.0
    precio_texto = (
        detalle_tabular["precio"] if detalle_tabular
        else valor_numerico(r"precio\s*(?:unitario|por\s*unidad)", obligatorio=False)
    )
    subtotal_texto = (
        detalle_tabular["subtotal"] if detalle_tabular
        else valor_numerico(r"subtotal|total\s+bruto|base\s+gravable", obligatorio=False)
    )
    impuesto_texto = (
        detalle_tabular["impuesto"] if detalle_tabular
        else valor_numerico(r"impuesto\s*(?:valor|total)?", obligatorio=False)
    )
    total_texto = valor_numerico(r"total\s+(?:a\s+pagar|factura)|valor\s+total", obligatorio=False)
    descuento_texto = valor_numerico(r"descuento", obligatorio=False)
    iva_porcentaje = (
        re.match(r"(\d+(?:[.,]\d+)?)", detalle_tabular["tasa"])
        if detalle_tabular else
        re.search(r"iva\s*(?:\(|:)?\s*(\d+(?:[.,]\d+)?)\s*%", texto, flags=re.IGNORECASE)
    )

    # Algunos comprobantes de caja no incluyen encabezados como "Subtotal" o
    # "Total a pagar" en la capa de texto del PDF. En cambio, dejan la línea
    # de producto con el patrón: valor-base IVA porcentaje valor-IVA. Es
    # información suficiente para analizar la factura: el total se deriva de
    # base + IVA y las reglas del sistema decidirán si esos valores son válidos.
    detalle_con_iva = re.search(
        r"(\d[\d.,]*)\s+IVA\s+(\d+(?:[.,]\d+)?)\s+(\d[\d.,]*)",
        texto, flags=re.IGNORECASE,
    )
    if detalle_con_iva:
        base_detalle, tasa_detalle, impuesto_detalle = detalle_con_iva.groups()
        subtotal_texto = subtotal_texto or base_detalle
        impuesto_texto = impuesto_texto or impuesto_detalle
        if not iva_porcentaje:
            iva_porcentaje = re.match(r"(\d+(?:[.,]\d+)?)", tasa_detalle)

    # En comprobantes de caja el encabezado de los tres totales se imprime en
    # una fila y los tres importes en la siguiente. pypdf los deja seguidos:
    # "TOTAL BRUTO ... TOTAL A PAGAR $subtotal $iva $total". Si se leyera solo
    # el primer número después de "total a pagar" se confundiría el subtotal
    # con el total real.
    resumen_totales = re.search(
        r"total\s+bruto.*?total\s+a\s+pagar\s+\$?\s*(\d[\d.,]*)\s+"
        r"\$?\s*(\d[\d.,]*)\s+\$?\s*(\d[\d.,]*)",
        texto, flags=re.IGNORECASE,
    )
    if resumen_totales:
        subtotal_texto, impuesto_texto, total_texto = resumen_totales.groups()

    if not subtotal_texto:
        # En algunos PDFs el valor queda antes del rótulo por el orden visual
        # de extracción del documento (ej.: "$226.807,00 TOTAL BRUTO").
        subtotal_invertido = re.search(
            r"\$?\s*(\d[\d.,]*)\s*(?=TOTAL\s+BRUTO)", texto, flags=re.IGNORECASE
        )
        subtotal_texto = subtotal_invertido.group(1) if subtotal_invertido else None
    if not subtotal_texto:
        raise ValueError(
            "No se encontró el subtotal en el PDF. Debe incluir subtotal/total bruto "
            "o una línea de detalle con valor, IVA y valor de IVA."
        )
    subtotal = _numero_pdf(subtotal_texto)
    impuesto = _numero_pdf(impuesto_texto) if impuesto_texto else 0.0
    if detalles_tabulares:
        # El detector opera a nivel de factura: consolida las cantidades de
        # todas las líneas y usa un precio promedio que preserva el subtotal.
        cantidad = sum(_numero_pdf(linea["cantidad"]) for linea in detalles_tabulares)
    # Si el PDF no muestra el total con una etiqueta reconocible, lo
    # reconstruimos desde los dos importes presentes. Esto evita rechazar una
    # factura potencialmente errónea antes de que el motor pueda señalarla.
    # En algunos PDF el total está dibujado y no llega a la capa de texto. Si
    # pudimos leer una fila tabular, su valor junto al IVA permite reconstruir
    # el total visible sin reemplazar el subtotal impreso (que puede ser justo
    # el dato inconsistente que debe detectar FactuGuard).
    base_para_total = _numero_pdf(detalle_tabular["precio"]) if detalle_tabular and len(detalles_tabulares) == 1 else subtotal
    total = _numero_pdf(total_texto) if total_texto else round(base_para_total + impuesto, 2)
    descuento = _numero_pdf(descuento_texto) if descuento_texto else 0.0
    tasa_iva = _numero_pdf(iva_porcentaje.group(1)) if iva_porcentaje else round((impuesto / subtotal) * 100, 2)
    precio = round(subtotal / cantidad, 2) if detalles_tabulares else (
        _numero_pdf(precio_texto) if precio_texto else round(subtotal / cantidad, 2)
    )
    hora_texto = valor_numerico(r"hora", obligatorio=False)
    hora_despues_fecha = re.search(
        rf"{re.escape(fecha_encontrada.group(1))}\s+([01]?\d|2[0-3]):\d{{2}}",
        texto,
    )
    hora = (
        int(_numero_pdf(hora_texto)) if hora_texto else
        int(hora_despues_fecha.group(1)) if hora_despues_fecha else 12
    )

    cliente_encontrado = re.search(
        # "cliente" solo se interpreta como campo si viene seguido por dos
        # puntos o guion. Así no se toma texto de políticas como "el cliente
        # cuenta con..." por el nombre del comprador.
        r"\b(?:cliente\s*[:\-]|facturado\s+a\s*[:\-]?|señor(?:es)?\s*[:\-]?)\s*"
        r"([A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑa-záéíóúüñ .,&-]+?)"
        r"(?=\s+(?:\d{5,}|nit\b|o\.\s*compra|factura\b)|$)",
        texto, flags=re.IGNORECASE,
    )
    cliente = cliente_encontrado.group(1).strip(" .,-") if cliente_encontrado else "CLIENTE-PDF"

    # Estos identificadores ayudan a evitar duplicados entre proveedores distintos.
    # Si el PDF no los trae con texto claro, se conservan como no reportados.
    nit_encontrado = re.search(r"\bnit\s*[:#-]?\s*([0-9][0-9.\-]{6,})", texto, flags=re.IGNORECASE)
    cufe_encontrado = re.search(r"\bcufe\s*[:#-]?\s*([A-F0-9]{32,})", texto, flags=re.IGNORECASE)

    # Formato habitual de facturas de venta: referencia, descripción y luego
    # cantidades/valores. Si no se reconoce, se conserva una descripción neutra.
    descripcion_encontrada = re.search(
        r"\b\d{6,}\s+\d+\.\s+(.+?)(?=\s+\d+\s+\d+\s+\d+\s+[\d,.]+(?:\s+IVA)?)",
        texto, flags=re.IGNORECASE,
    )
    descripcion = (
        detalle_tabular["descripcion"].strip(" .,-") if detalle_tabular else
        descripcion_encontrada.group(1).strip(" .,-")
        if descripcion_encontrada else "Producto o servicio del PDF"
    )
    descripciones_sueltas = re.findall(
        r"^\s*\d{6,}\s+\d+\.\s+(.+?)\s+\d+(?:[.,]\d+)?\s*$",
        texto_por_lineas, flags=re.MULTILINE,
    )
    if descripciones_sueltas:
        descripcion = descripciones_sueltas[0].strip(" .,-")
    detalle_lineas = [{
        "descripcion": linea["descripcion"].strip(" .,-"),
        "cantidad": _numero_pdf(linea["cantidad"]), "precio_unitario": _numero_pdf(linea["precio"]),
        "iva_pct": _numero_pdf(linea["tasa"]), "impuesto_valor": _numero_pdf(linea["impuesto"]),
        "subtotal": _numero_pdf(linea["subtotal"]),
    } for linea in detalles_tabulares]
    if not detalle_lineas:
        detalle_lineas = [{
            "descripcion": descripcion, "cantidad": cantidad, "precio_unitario": precio,
            "descuento_pct": descuento, "iva_pct": tasa_iva,
            "impuesto_valor": impuesto, "subtotal": subtotal,
        }]
    descripcion_detallada = "\n".join(
        dict.fromkeys([linea["descripcion"] for linea in detalle_lineas] + descripciones_sueltas)
    )

    return pd.DataFrame([{
        "factura_id": identificador.upper(),
        "cliente_sintetico": cliente[:80],
        "nit_emisor": nit_encontrado.group(1).replace(".", "") if nit_encontrado else "NO-REPORTADO",
        "cufe": cufe_encontrado.group(1).upper() if cufe_encontrado else "",
        "tipo_documento": "Factura electronica PDF",
        "validacion_dian": "No verificada por FactuGuard",
        "categoria": descripcion[:80], "descripcion_detallada": descripcion_detallada,
        "detalle_lineas": detalle_lineas,
        "fecha": fecha_valor.strftime("%Y-%m-%d"), "hora": hora,
        "cantidad": cantidad, "precio_unitario": precio, "descuento_pct": descuento,
        "tasa_iva": tasa_iva, "subtotal": subtotal, "impuesto_valor": impuesto, "total": total,
    }])


FORMATOS_FACTURA = {".csv", ".xlsx", ".pdf", ".xml"}


def _etiqueta_xml(elemento) -> str:
    """Devuelve el nombre local de una etiqueta XML, sin su espacio de nombres."""
    return elemento.tag.rsplit("}", 1)[-1]


def leer_factura_xml(contenido: bytes) -> pd.DataFrame:
    """Lee una factura electrónica XML (UBL/DIAN) y consolida sus líneas.

    El XML es la fuente más precisa para cantidad, precio, IVA y totales. No se
    guarda el XML original: solo los datos mínimos que requiere el análisis.
    """
    try:
        raiz = ET.fromstring(contenido)
    except ET.ParseError as error:
        raise ValueError("El XML no es una factura electrónica válida o está dañado.") from error

    def directo(nombre: str) -> str | None:
        for hijo in raiz:
            if _etiqueta_xml(hijo) == nombre and (hijo.text or "").strip():
                return (hijo.text or "").strip()
        return None

    def buscar(elemento, *nombres: str) -> str | None:
        for hijo in elemento.iter():
            if _etiqueta_xml(hijo) in nombres and (hijo.text or "").strip():
                return (hijo.text or "").strip()
        return None

    def importe(valor: str | None, campo: str) -> float:
        if not valor:
            raise ValueError(f"El XML no contiene '{campo}'.")
        return _numero_pdf(valor)

    identificador = directo("ID")
    fecha = directo("IssueDate")
    if not identificador or not fecha:
        raise ValueError("El XML debe contener el número y la fecha de emisión de la factura.")
    fecha_valor = pd.to_datetime(fecha, errors="coerce")
    if pd.isna(fecha_valor):
        raise ValueError("La fecha de emisión del XML no es válida.")

    lineas = [elemento for elemento in raiz.iter() if _etiqueta_xml(elemento) == "InvoiceLine"]
    if not lineas:
        raise ValueError("El XML no contiene líneas de factura para extraer cantidades y precios.")
    detalle_lineas = []
    for linea in lineas:
        cantidad_linea = importe(buscar(linea, "InvoicedQuantity"), "cantidad")
        subtotal_linea = importe(buscar(linea, "LineExtensionAmount"), "subtotal de línea")
        descripcion_linea = buscar(linea, "Description", "Name") or "Sin descripción"
        precio_linea = _numero_pdf(buscar(linea, "PriceAmount") or str(subtotal_linea / cantidad_linea))
        detalle_lineas.append({
            "referencia": buscar(linea, "SellersItemIdentification", "ID") or "",
            "descripcion": descripcion_linea, "cantidad": cantidad_linea,
            "precio_unitario": precio_linea,
            "descuento_pct": _numero_pdf(buscar(linea, "MultiplierFactorNumeric") or "0") * 100,
            "iva_pct": _numero_pdf(buscar(linea, "Percent") or "0"),
            "impuesto_valor": _numero_pdf(buscar(linea, "TaxAmount") or "0"),
            "subtotal": subtotal_linea,
        })
    cantidad = sum(linea["cantidad"] for linea in detalle_lineas)
    subtotal_lineas = sum(linea["subtotal"] for linea in detalle_lineas)
    descripciones = [str(linea["descripcion"]) for linea in detalle_lineas]
    descripcion_detallada = " | ".join(descripciones)
    categoria = descripcion_detallada[:80] or "Productos del XML"

    total_legal = next(
        (elemento for elemento in raiz.iter() if _etiqueta_xml(elemento) == "LegalMonetaryTotal"), raiz
    )
    subtotal = _numero_pdf(buscar(total_legal, "TaxExclusiveAmount") or str(subtotal_lineas))
    total = importe(buscar(total_legal, "PayableAmount", "TaxInclusiveAmount"), "total a pagar")
    impuesto = _numero_pdf(buscar(raiz, "TaxAmount") or "0")
    tasa_iva = _numero_pdf(buscar(raiz, "Percent") or "0")

    comprador = next(
        (elemento for elemento in raiz.iter() if _etiqueta_xml(elemento) == "AccountingCustomerParty"), raiz
    )
    emisor = next(
        (elemento for elemento in raiz.iter() if _etiqueta_xml(elemento) == "AccountingSupplierParty"), raiz
    )
    cliente = buscar(comprador, "RegistrationName", "Name", "CompanyID") or "CLIENTE-XML"
    nit = buscar(emisor, "CompanyID") or "NO-REPORTADO"
    cufe = directo("UUID") or ""
    descuento = _numero_pdf(buscar(raiz, "MultiplierFactorNumeric") or "0")
    if 0 < descuento <= 1:
        descuento *= 100

    return pd.DataFrame([{
        "factura_id": identificador.upper(), "cliente_sintetico": cliente[:80],
        "nit_emisor": re.sub(r"[^0-9A-Za-z-]", "", nit).upper(), "cufe": cufe.upper(),
        "tipo_documento": "Factura electrónica XML", "validacion_dian": "Datos extraídos del XML",
        "categoria": categoria, "descripcion_detallada": descripcion_detallada,
        "detalle_lineas": detalle_lineas, "fecha": fecha_valor.strftime("%Y-%m-%d"), "hora": 12,
        "cantidad": cantidad, "precio_unitario": round(subtotal / cantidad, 2),
        "descuento_pct": descuento, "tasa_iva": tasa_iva, "subtotal": subtotal,
        "impuesto_valor": impuesto, "total": total,
    }])


def _leer_un_archivo_facturas(nombre: str, contenido: bytes) -> pd.DataFrame:
    """Despacha un archivo de factura ya leído, también cuando viene dentro de un ZIP."""
    extension = os.path.splitext(nombre)[1].lower()
    archivo = io.BytesIO(contenido)
    if extension == ".csv":
        return leer_csv_facturas(contenido)
    if extension == ".xlsx":
        return pd.read_excel(archivo)
    if extension == ".pdf":
        return leer_factura_pdf(archivo)
    if extension == ".xml":
        return leer_factura_xml(contenido)
    raise ValueError("Formato no admitido. Usa CSV, Excel (.xlsx), PDF, XML DIAN o un ZIP con esos archivos.")


def leer_lote_facturas(archivo, nombre_archivo: str) -> tuple[pd.DataFrame, int]:
    """Lee una factura o un ZIP de facturas sin extraer archivos al disco."""
    extension = os.path.splitext(nombre_archivo)[1].lower()
    if extension != ".zip":
        return _leer_un_archivo_facturas(nombre_archivo, archivo.read()), 1

    try:
        paquete = zipfile.ZipFile(archivo)
    except zipfile.BadZipFile as error:
        raise ValueError("El archivo .zip está dañado o no es un ZIP válido.") from error
    with paquete:
        miembros = [miembro for miembro in paquete.infolist() if not miembro.is_dir()]
        facturas = [miembro for miembro in miembros if os.path.splitext(miembro.filename)[1].lower() in FORMATOS_FACTURA]
        if not facturas:
            raise ValueError("El ZIP no contiene CSV, Excel (.xlsx), PDF o XML de factura.")
        if len(facturas) > MAX_FILAS_ARCHIVO:
            raise ValueError(f"El ZIP supera el máximo de {MAX_FILAS_ARCHIVO:,} archivos de factura.")
        if any(miembro.flag_bits & 0x1 for miembro in facturas):
            raise ValueError("El ZIP contiene archivos protegidos con contraseña; descomprímelos antes de cargar.")
        limite_descomprimido = MAX_ARCHIVO_MB * 1024 * 1024
        if sum(miembro.file_size for miembro in facturas) > limite_descomprimido:
            raise ValueError(f"El contenido descomprimido supera el límite de {MAX_ARCHIVO_MB} MB.")
        tablas = [_leer_un_archivo_facturas(miembro.filename, paquete.read(miembro)) for miembro in facturas]

    resultado = pd.concat(tablas, ignore_index=True)
    if len(resultado) > MAX_FILAS_ARCHIVO:
        raise ValueError(f"El lote contiene más de {MAX_FILAS_ARCHIVO:,} facturas.")
    # Un ZIP puede traer el PDF y el XML de la misma factura. Conservamos una
    # sola fila por documento (el XML queda al final si el archivo se ordenó así)
    # para no convertir una copia digital en una alerta de duplicado.
    cufe = resultado.get("cufe", pd.Series("", index=resultado.index)).fillna("").astype(str).str.strip()
    nit = resultado.get("nit_emisor", pd.Series("NO-REPORTADO", index=resultado.index)).fillna("NO-REPORTADO").astype(str)
    identidad = cufe.where(cufe != "", nit + "|" + resultado["factura_id"].astype(str) + "|" + resultado["fecha"].astype(str))
    resultado = resultado.loc[~identidad.duplicated(keep="last")].reset_index(drop=True)
    return resultado, len(facturas)


@app.route("/")
def inicio():
    return redirect(url_for("dashboard") if "usuario" in session else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    """Valida al usuario con hash scrypt almacenado en PostgreSQL."""
    if "usuario" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        nombre = request.form.get("usuario", "")
        clave = _clave_login(nombre)
        if _login_bloqueado(clave):
            app.logger.warning("Login bloqueado por intentos repetidos: %s", clave)
            flash("Demasiados intentos fallidos. Espera 15 minutos e inténtalo de nuevo.", "danger")
            return render_template("login.html")
        try:
            usuario = autenticar_usuario(nombre, request.form.get("contrasena", ""))
        except Exception as error:
            flash(f"No fue posible conectar con PostgreSQL: {error_seguro(error)}", "danger")
            return render_template("login.html")
        if not usuario:
            _INTENTOS_LOGIN.setdefault(clave, []).append(time.time())
            app.logger.warning("Login fallido para '%s' desde %s", nombre.strip().lower(), request.remote_addr)
            flash("Usuario o contraseña incorrectos.", "danger")
        else:
            _INTENTOS_LOGIN.pop(clave, None)
            session.clear()  # nueva sesión y nuevo token CSRF tras autenticarse
            session.permanent = True
            session["usuario"] = usuario
            app.logger.info("Login correcto: %s (%s)", usuario["nombre_usuario"], usuario["rol"])
            return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/salud")
def salud():
    """Comprobación para monitoreo: responde 200 si la aplicación y la base de datos funcionan."""
    try:
        with conectar() as conexion:
            conexion.execute("SELECT 1")
        base_datos = True
    except Exception as error:
        app.logger.error("Comprobación de salud fallida", exc_info=error)
        base_datos = False
    return jsonify(estado="ok" if base_datos else "degradado", base_datos=base_datos), (200 if base_datos else 503)


@app.post("/cerrar-sesion")
def cerrar_sesion():
    session.clear()
    flash("Sesión cerrada correctamente.", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
@requiere_inicio_sesion
def dashboard():
    """Consulta el último experimento y muestra indicadores, gráficos y alertas."""
    try:
        experimento = obtener_ultimo_experimento()
        alertas = obtener_alertas(100)
        resumen_cargas = obtener_resumen_cargas_usuario(int(session["usuario"]["id"]))
        metricas_revision = obtener_metricas_revision_usuario(int(session["usuario"]["id"]))
    except Exception as error:
        flash(f"No fue posible consultar PostgreSQL: {error_seguro(error)}", "danger")
        experimento, alertas = None, []
        resumen_cargas = {"total": 0, "con_alerta": 0, "sin_alerta": 0, "pendientes": 0}
        metricas_revision = {"alertas": 0, "revisadas": 0, "descartadas": 0, "decisiones": 0, "porcentaje_descartadas": 0.0}
    tipos, valores_tipos, origenes, valores_origenes = datos_graficos(alertas)
    return render_template(
        "dashboard.html", experimento=experimento, alertas=alertas,
        tipos=tipos, valores_tipos=valores_tipos, origenes=origenes,
        resumen_cargas=resumen_cargas, metricas_revision=metricas_revision,
        valores_origenes=valores_origenes,
    )


@app.post("/ejecutar")
@requiere_inicio_sesion
@requiere_rol("administrador")
def ejecutar():
    """Ejecuta el motor híbrido y persiste su resultado en PostgreSQL local."""
    try:
        _, metricas, _ = ejecutar_experimento(guardar_en_postgres=True)
        flash(f"Experimento guardado. Puntaje F1: {float(metricas['f1']) * 100:.1f}%.", "success")
    except Exception as error:
        flash(f"No fue posible ejecutar el experimento: {error_seguro(error)}", "danger")
    return redirect(url_for("dashboard"))


@app.route("/recomendacion/<int:alerta_id>")
@requiere_inicio_sesion
def recomendacion(alerta_id: int):
    """Muestra una propuesta explicable para una alerta sintética."""
    factura = obtener_alerta_sintetica(alerta_id)
    if not factura:
        abort(404)
    propuesta_guardada = obtener_recomendacion(alerta_id)
    if not propuesta_guardada:
        propuesta = generar_recomendacion(factura)
        recomendacion_id = guardar_recomendacion(alerta_id, propuesta)
        propuesta_guardada = obtener_recomendacion(alerta_id)
        propuesta_guardada["id"] = recomendacion_id
    # Se calcula al abrir la vista para que recomendaciones guardadas antes de
    # esta mejora también muestren qué dato concreto debe revisar el analista.
    return render_template(
        "recomendacion.html", factura=factura, recomendacion=propuesta_guardada,
        observacion=observacion_especifica(factura),
    )


@app.post("/recomendacion/<int:alerta_id>/decision")
@requiere_inicio_sesion
def decidir_recomendacion(alerta_id: int):
    """Guarda la aprobación humana y entrena la neurona con esa respuesta."""
    decision = request.form.get("decision", "")
    propuesta = obtener_recomendacion(alerta_id)
    if not propuesta:
        flash("Primero abre la recomendación para generar una propuesta.", "warning")
        return redirect(url_for("recomendacion", alerta_id=alerta_id))
    if propuesta["decision_usuario"]:
        # Doble clic, segunda pestaña o botón "atrás": la decisión ya quedó guardada.
        flash(f"Esta recomendación ya tenía una decisión registrada ({propuesta['decision_usuario']}). No se modificó.", "info")
        return redirect(url_for("recomendacion", alerta_id=alerta_id))
    try:
        comentario = request.form.get("comentario", "").strip()
        recomendacion = propuesta["recomendacion"]
        aplicar_ajuste = decision == "aplicar"
        if aplicar_ajuste:
            if not recomendacion.get("automatica"):
                raise ValueError("Esta alerta requiere validación humana y no tiene un ajuste automático seguro.")
            resultado_ajuste = aplicar_ajuste_recomendado(
                alerta_id, recomendacion.get("campos_sugeridos", {})
            )
            decision = "aprobada"
        else:
            resultado_ajuste = None
        correccion_final = {
            "comentario": comentario, "propuesta": recomendacion,
            "resultado_ajuste": resultado_ajuste,
        }
        contexto = registrar_decision_recomendacion(
            int(propuesta["id"]), decision, correccion_final, int(session["usuario"]["id"])
        )
        nueva_probabilidad = aprender_de_decision(contexto, decision)
        mensaje = (
            "Ajuste recomendado aplicado y decisión registrada para auditoría."
            if aplicar_ajuste else f"Decisión '{decision}' registrada para auditoría."
        )
        if nueva_probabilidad is not None:
            mensaje += f" FactuGuard IA actualizó su aprendizaje ({nueva_probabilidad * 100:.1f}% para un caso similar)."
        flash(mensaje, "success")
    except Exception as error:
        flash(f"No fue posible registrar la decisión: {error_seguro(error)}", "danger")
    return redirect(url_for("recomendacion", alerta_id=alerta_id))


@app.route("/recomendacion-cargada/<int:factura_id>")
@requiere_inicio_sesion
def recomendacion_cargada(factura_id: int):
    """Genera una recomendacion para una alerta creada manualmente o desde archivo."""
    factura = obtener_factura_cargada(factura_id)
    if not factura:
        abort(404)
    if not factura["alerta_hibrida"]:
        flash("Esta factura no tiene una novedad que requiera recomendacion.", "warning")
        return redirect(url_for("factura_cargada", factura_id=factura_id))
    factura["tipo_anomalia"] = tipo_anomalia_para_recomendacion(factura)
    propuesta_guardada = obtener_recomendacion_cargada(factura_id)
    if not propuesta_guardada:
        propuesta = generar_recomendacion(factura)
        recomendacion_id = guardar_recomendacion_cargada(factura_id, propuesta)
        propuesta_guardada = obtener_recomendacion_cargada(factura_id)
        propuesta_guardada["id"] = recomendacion_id
    return render_template(
        "recomendacion.html", factura=factura, recomendacion=propuesta_guardada,
        observacion=observacion_especifica(factura), recomendacion_cargada=True,
    )


@app.post("/recomendacion-cargada/<int:factura_id>/decision")
@requiere_inicio_sesion
def decidir_recomendacion_cargada(factura_id: int):
    """Registra la decision humana de una recomendacion de factura cargada."""
    decision = request.form.get("decision", "")
    propuesta = obtener_recomendacion_cargada(factura_id)
    if not propuesta:
        flash("Primero abre la recomendación para generar una propuesta.", "warning")
        return redirect(url_for("recomendacion_cargada", factura_id=factura_id))
    if propuesta["decision_usuario"]:
        # Doble clic, segunda pestaña o botón "atrás": la decisión ya quedó guardada.
        flash(f"Esta recomendación ya tenía una decisión registrada ({propuesta['decision_usuario']}). No se modificó.", "info")
        return redirect(url_for("recomendacion_cargada", factura_id=factura_id))
    try:
        comentario = request.form.get("comentario", "").strip()
        recomendacion = propuesta["recomendacion"]
        aplicar_ajuste = decision == "aplicar"
        if aplicar_ajuste:
            if not recomendacion.get("automatica"):
                raise ValueError("Esta alerta requiere validacion humana y no tiene un ajuste automatico seguro.")
            resultado_ajuste = aplicar_ajuste_recomendado_cargado(
                factura_id, recomendacion.get("campos_sugeridos", {})
            )
            decision = "aprobada"
        else:
            resultado_ajuste = None
        contexto = registrar_decision_recomendacion_cargada(
            int(propuesta["id"]), decision,
            {"comentario": comentario, "propuesta": recomendacion, "resultado_ajuste": resultado_ajuste},
            int(session["usuario"]["id"]),
        )
        nueva_probabilidad = aprender_de_decision(contexto, decision)
        mensaje = "Ajuste recomendado aplicado y decision registrada para auditoria." if aplicar_ajuste else (
            f"Decision '{decision}' registrada para auditoria."
        )
        if nueva_probabilidad is not None:
            mensaje += f" FactuGuard IA actualizo su aprendizaje ({nueva_probabilidad * 100:.1f}% para un caso similar)."
        flash(mensaje, "success")
    except Exception as error:
        flash(f"No fue posible registrar la decision: {error_seguro(error)}", "danger")
    return redirect(url_for("recomendacion_cargada", factura_id=factura_id))


@app.post("/regenerar-datos")
@requiere_inicio_sesion
@requiere_rol("administrador")
def regenerar_datos():
    """Limpia solo los experimentos sintéticos y crea un conjunto completamente nuevo."""
    try:
        eliminados = limpiar_experimentos_sinteticos()
        semilla = secrets.randbelow(2_147_483_647)
        _, metricas, _ = ejecutar_experimento(guardar_en_postgres=True, semilla=semilla)
        flash(
            f"Se eliminaron {eliminados} experimentos sintéticos y se generaron datos nuevos. "
            f"Puntaje F1: {float(metricas['f1']) * 100:.1f}%.",
            "success",
        )
    except Exception as error:
        flash(f"No fue posible regenerar los datos: {error_seguro(error)}", "danger")
    return redirect(url_for("dashboard"))


@app.route("/simulador", methods=["GET", "POST"])
@requiere_inicio_sesion
def simulador():
    """Permite demostrar el motor híbrido con una factura creada a mano."""
    valores = valores_iniciales_simulador()
    resultado = None
    umbral = None
    if request.method == "POST":
        valores.update({campo: request.form.get(campo, "") for campo in valores})
        try:
            factura = leer_factura_manual(request.form)
            resultado, umbral = analizar_factura_manual(factura)
            # La prueba manual queda registrada igual que una carga de archivo.
            # Así, cualquier alerta generada aparece en la bandeja de revisión.
            guardar_carga_archivo(
                pd.DataFrame([resultado]), "Prueba manual", int(session["usuario"]["id"])
            )
            if bool(resultado["alerta_hibrida"]):
                flash("Factura manual guardada en Revisión humana porque requiere validación.", "warning")
            else:
                flash("Factura manual analizada y guardada. No requiere revisión.", "success")
        except Exception as error:
            flash(f"No fue posible analizar la factura: {error_seguro(error)}", "danger")
    return render_template("simulador.html", valores=valores, resultado=resultado, umbral=umbral)


@app.post("/limpiar-pruebas-manuales")
@requiere_inicio_sesion
def limpiar_pruebas_manuales():
    """Borra solo las facturas creadas por el formulario de prueba manual."""
    try:
        eliminadas = limpiar_facturas_manuales(int(session["usuario"]["id"]))
        flash(f"Se eliminaron {eliminadas} carga(s) de Prueba manual.", "success")
    except Exception as error:
        flash(f"No fue posible limpiar las pruebas manuales: {error_seguro(error)}", "danger")
    return redirect(url_for("simulador"))


@app.post("/cargas/<int:carga_id>/eliminar")
@requiere_inicio_sesion
def eliminar_carga(carga_id: int):
    """Elimina una carga de prueba que pertenece a la persona conectada."""
    try:
        eliminada = eliminar_carga_archivo(carga_id, int(session["usuario"]["id"]))
        if eliminada:
            flash("La carga y sus facturas asociadas se eliminaron.", "success")
        else:
            flash("No se encontró esa carga o no tienes permiso para eliminarla.", "warning")
    except Exception as error:
        flash(f"No fue posible eliminar la carga: {error_seguro(error)}", "danger")
    return redirect(url_for("cargar_facturas"))


@app.post("/facturas-cargadas/<int:factura_id>/eliminar")
@requiere_inicio_sesion
def eliminar_factura_importada(factura_id: int):
    """Elimina una factura propia; el administrador puede eliminar cualquiera."""
    try:
        usuario = session["usuario"]
        eliminada = eliminar_factura_cargada(
            factura_id, int(usuario["id"]), es_administrador=usuario["rol"] == "administrador"
        )
        if eliminada:
            app.logger.info(
                "Factura cargada %s eliminada por %s", factura_id, usuario["nombre_usuario"],
            )
            flash("La factura cargada se eliminó correctamente.", "success")
        else:
            flash("La factura no existe o no tienes permiso para eliminarla.", "warning")
    except Exception as error:
        flash(f"No fue posible eliminar la factura: {error_seguro(error)}", "danger")
    destino = "alertas" if request.form.get("origen") == "alertas" else "revision_cargas"
    return redirect(url_for(destino))


@app.route("/cargar-facturas", methods=["GET", "POST"])
@requiere_inicio_sesion
def cargar_facturas():
    """Analiza un CSV o Excel en memoria, sin conservar el archivo del usuario."""
    resumen = None
    alertas_archivo: list[dict[str, object]] = []
    facturas_archivo: list[dict[str, object]] = []
    nombre_archivo = None
    if request.method == "POST":
        archivo = request.files.get("archivo")
        if not archivo or not archivo.filename:
            flash("Selecciona un archivo CSV, Excel o PDF antes de analizar.", "warning")
        else:
            nombre_archivo = archivo.filename
            extension = nombre_archivo.rsplit(".", 1)[-1].lower() if "." in nombre_archivo else ""
            try:
                if extension not in {"csv", "xlsx", "pdf", "xml", "zip"}:
                    raise ValueError("Formato no admitido. Usa CSV, Excel (.xlsx), PDF, XML DIAN o ZIP.")
                tabla, archivos_procesados = leer_lote_facturas(archivo, nombre_archivo)
                resultado, umbral = analizar_facturas_cargadas(tabla)
                alertas = resultado.loc[resultado["alerta_hibrida"]]
                carga_id = guardar_carga_archivo(
                    resultado, nombre_archivo, int(session["usuario"]["id"])
                )
                resumen = {
                    "registros": len(resultado), "alertas": len(alertas), "reglas": int(resultado["alerta_reglas"].sum()),
                    "ia": int(resultado["alerta_ia"].sum()), "umbral": umbral, "carga_id": carga_id,
                }
                app.logger.info(
                    "Carga '%s' por %s: %s facturas de %s archivo(s), %s alertas",
                    nombre_archivo, session["usuario"]["nombre_usuario"], len(resultado),
                    archivos_procesados, len(alertas),
                )
                alertas_archivo = obtener_alertas_de_carga(carga_id)
                facturas_archivo = obtener_facturas_de_carga(carga_id)
            except UniqueViolation:
                # PostgreSQL rechaza dos filas con el mismo NIT, número y fecha (o CUFE).
                flash(
                    "El archivo contiene facturas repetidas (mismo NIT, número y fecha, o mismo CUFE). "
                    "Deja una sola fila por documento y vuelve a cargarlo.", "warning",
                )
            except Exception as error:
                flash(f"No fue posible analizar el archivo: {error_seguro(error)}", "danger")
    return render_template(
        "cargar_facturas.html", resumen=resumen, alertas=alertas_archivo,
        facturas=facturas_archivo, nombre_archivo=nombre_archivo,
    )


@app.route("/revision-cargas")
@requiere_inicio_sesion
def revision_cargas():
    """Presenta la cola de facturas importadas que requieren decisión humana."""
    try:
        alertas = obtener_alertas_cargadas()
    except Exception as error:
        flash(f"No fue posible consultar las facturas cargadas: {error_seguro(error)}", "danger")
        alertas = []
    return render_template(
        "revision_cargas.html", alertas=alertas,
        es_administrador=session["usuario"]["rol"] == "administrador",
    )


@app.route("/factura-cargada/<int:factura_id>", methods=["GET", "POST"])
@requiere_inicio_sesion
def factura_cargada(factura_id: int):
    """Muestra todos los datos de una factura cargada y registra la revisión humana."""
    if request.method == "POST":
        try:
            actualizar_estado_factura_cargada(factura_id, request.form.get("estado", "pendiente"))
            flash("Decisión de revisión guardada.", "success")
        except Exception as error:
            flash(f"No fue posible guardar la revisión: {error_seguro(error)}", "danger")
        return redirect(url_for("factura_cargada", factura_id=factura_id))
    factura = obtener_factura_cargada(factura_id)
    if not factura:
        abort(404)
    usuario = session["usuario"]
    puede_eliminar = (
        usuario["rol"] == "administrador" or factura.get("usuario_id") == int(usuario["id"])
    )
    return render_template(
        "factura.html", factura=factura, es_cargada=True, puede_eliminar=puede_eliminar,
    )


@app.route("/factura-sintetica/<numero_factura>")
@requiere_inicio_sesion
def factura_sintetica(numero_factura: str):
    """Muestra una factura del experimento como documento de demostración."""
    alerta_id = request.args.get("alerta_id", type=int)
    factura = (
        obtener_factura_sintetica_por_alerta(alerta_id)
        if alerta_id is not None else obtener_factura_sintetica(numero_factura)
    )
    if factura and str(factura["factura_id"]) != numero_factura:
        abort(404)
    if not factura:
        abort(404)
    return render_template("factura.html", factura=factura, es_cargada=False)


@app.route("/alertas")
@requiere_inicio_sesion
def alertas():
    """Muestra la bandeja completa para revisión y filtrado en el navegador."""
    try:
        lista_alertas = obtener_alertas(500)
        alertas_cargadas = obtener_alertas_cargadas(500)
    except Exception as error:
        flash(f"No fue posible consultar alertas: {error_seguro(error)}", "danger")
        lista_alertas = []
        alertas_cargadas = []
    return render_template(
        "alertas.html", alertas=lista_alertas, alertas_cargadas=alertas_cargadas
    )


if __name__ == "__main__":
    import threading
    import webbrowser

    direccion = "http://127.0.0.1:5000"
    print(f"FactuGuard IA se está iniciando en {direccion}")
    print("Deja esta ventana abierta mientras uses la aplicación; ciérrala (Ctrl+C) para detenerla.")
    # Abre el navegador cuando el servidor ya está escuchando.
    threading.Timer(1.5, lambda: webbrowser.open(direccion)).start()
    try:
        # Solo se expone en el computador propio; no publica el sistema en internet.
        app.run(host="127.0.0.1", port=5000, debug=False)
    except OSError as error:
        raise SystemExit(f"No se pudo iniciar en el puerto 5000 (¿ya hay otra ventana abierta?): {error}")
