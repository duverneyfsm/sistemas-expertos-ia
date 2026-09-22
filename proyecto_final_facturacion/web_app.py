"""Servidor web local de FactuGuard IA.

Flask muestra la interfaz en el navegador, mientras que los módulos existentes
conservan la lógica de IA, seguridad y PostgreSQL.
"""

from __future__ import annotations

import hmac
import logging
import os
import re
import secrets
import time
from collections import Counter
from datetime import timedelta
from functools import wraps
from logging.handlers import RotatingFileHandler

import pandas as pd
from dotenv import load_dotenv
from psycopg.errors import UniqueViolation
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for

from base_datos import (
    actualizar_estado_factura_cargada, aplicar_ajuste_recomendado, aplicar_ajuste_recomendado_cargado,
    autenticar_usuario, conectar, guardar_carga_archivo, guardar_recomendacion_cargada,
    eliminar_carga_archivo,
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


def leer_factura_pdf(archivo) -> pd.DataFrame:
    """Extrae una factura digital de un PDF con campos etiquetados en español.

    No aplica OCR: si el documento es una imagen escaneada sin texto, la persona
    debe usar la prueba manual o convertirlo primero con OCR.
    """
    try:
        from pypdf import PdfReader
        lector = PdfReader(archivo)
        texto = "\n".join(pagina.extract_text() or "" for pagina in lector.pages)
    except Exception as error:
        raise ValueError("No fue posible leer el PDF. Verifica que no esté dañado o protegido.") from error
    texto = re.sub(r"\s+", " ", texto)
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
        raise ValueError("No se encontró una fecha válida en el PDF.")
    fecha_valor = pd.to_datetime(fecha_encontrada.group(1), dayfirst=True, errors="coerce")
    if pd.isna(fecha_valor):
        raise ValueError("La fecha del PDF no es válida.")

    cantidad_texto = valor_numerico(r"cantidad", obligatorio=False)
    cantidad = _numero_pdf(cantidad_texto) if cantidad_texto else 1.0
    precio_texto = valor_numerico(r"precio\s*(?:unitario|por\s*unidad)", obligatorio=False)
    subtotal_texto = valor_numerico(r"subtotal|total\s+bruto|base\s+gravable", obligatorio=False)
    impuesto_texto = valor_numerico(r"impuesto\s*(?:valor|total)?", obligatorio=False)
    total_texto = valor_numerico(r"total\s+(?:a\s+pagar|factura)|valor\s+total", obligatorio=False)
    descuento_texto = valor_numerico(r"descuento", obligatorio=False)
    iva_porcentaje = re.search(r"iva\s*(?:\(|:)?\s*(\d+(?:[.,]\d+)?)\s*%", texto, flags=re.IGNORECASE)

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
    # Si el PDF no muestra el total con una etiqueta reconocible, lo
    # reconstruimos desde los dos importes presentes. Esto evita rechazar una
    # factura potencialmente errónea antes de que el motor pueda señalarla.
    total = _numero_pdf(total_texto) if total_texto else round(subtotal + impuesto, 2)
    descuento = _numero_pdf(descuento_texto) if descuento_texto else 0.0
    tasa_iva = _numero_pdf(iva_porcentaje.group(1)) if iva_porcentaje else round((impuesto / subtotal) * 100, 2)
    precio = _numero_pdf(precio_texto) if precio_texto else round(subtotal / cantidad, 2)
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
        descripcion_encontrada.group(1).strip(" .,-")
        if descripcion_encontrada else "Producto o servicio del PDF"
    )

    return pd.DataFrame([{
        "factura_id": identificador.upper(),
        "cliente_sintetico": cliente[:80],
        "nit_emisor": nit_encontrado.group(1).replace(".", "") if nit_encontrado else "NO-REPORTADO",
        "cufe": cufe_encontrado.group(1).upper() if cufe_encontrado else "",
        "tipo_documento": "Factura electronica PDF",
        "validacion_dian": "No verificada por FactuGuard",
        "categoria": descripcion[:80],
        "fecha": fecha_valor.strftime("%Y-%m-%d"), "hora": hora,
        "cantidad": cantidad, "precio_unitario": precio, "descuento_pct": descuento,
        "tasa_iva": tasa_iva, "subtotal": subtotal, "impuesto_valor": impuesto, "total": total,
    }])


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
                if extension == "csv":
                    tabla = leer_csv_facturas(archivo.read())
                elif extension == "xlsx":
                    tabla = pd.read_excel(archivo)
                elif extension == "pdf":
                    tabla = leer_factura_pdf(archivo)
                else:
                    raise ValueError("Formato no admitido. Usa un archivo .csv, .xlsx o .pdf.")
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
                    "Carga '%s' por %s: %s facturas, %s alertas",
                    nombre_archivo, session["usuario"]["nombre_usuario"], len(resultado), len(alertas),
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
    return render_template("revision_cargas.html", alertas=alertas)


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
    return render_template("factura.html", factura=factura, es_cargada=True)


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
