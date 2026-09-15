"""Servidor web local de FactuGuard IA.

Flask muestra la interfaz en el navegador, mientras que los módulos existentes
conservan la lógica de IA, seguridad y PostgreSQL.
"""

from __future__ import annotations

import os
import re
import secrets
from collections import Counter
from functools import wraps

import pandas as pd
from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for

from base_datos import (
    actualizar_estado_factura_cargada, aplicar_ajuste_recomendado, aplicar_ajuste_recomendado_cargado,
    autenticar_usuario, guardar_carga_archivo, guardar_recomendacion_cargada,
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
from config import RUTA_ENV
from recomendador_ia import (
    aprender_de_decision, generar_recomendacion, observacion_especifica,
    tipo_anomalia_para_recomendacion,
)
from servicio import analizar_factura_manual, analizar_facturas_cargadas, ejecutar_experimento


load_dotenv(RUTA_ENV)
app = Flask(__name__)
# La llave real se genera durante configurar_postgres.py y no se publica en Git.
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY") or secrets.token_urlsafe(32)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # Archivos de hasta 5 MB.


@app.errorhandler(413)
def archivo_demasiado_grande(error):
    """Devuelve un mensaje &uacute;til cuando el navegador supera el l&iacute;mite permitido."""
    flash("El archivo supera el l&iacute;mite de 5 MB.", "danger")
    return redirect(url_for("cargar_facturas"))


def requiere_inicio_sesion(vista):
    """Evita que alguien visite las páginas privadas sin autenticarse."""
    @wraps(vista)
    def protegida(*args, **kwargs):
        if "usuario" not in session:
            flash("Inicia sesión para acceder al dashboard.", "warning")
            return redirect(url_for("login"))
        return vista(*args, **kwargs)
    return protegida


def datos_graficos(alertas: list[dict[str, object]]) -> tuple[list[str], list[int], list[str], list[int]]:
    """Convierte alertas de PostgreSQL en listas simples para Chart.js."""
    por_tipo = Counter(str(alerta["tipo_anomalia"]).replace("_", " ").title() for alerta in alertas)
    por_origen = Counter(str(alerta["origen"]).replace("_", " + ").upper() for alerta in alertas)
    return list(por_tipo.keys()), list(por_tipo.values()), list(por_origen.keys()), list(por_origen.values())


def valores_iniciales_simulador() -> dict[str, str]:
    """Entrega una factura normal precargada para iniciar la demostraciÃ³n manual."""
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
        raise ValueError("Escribe un c&oacute;digo de cliente an&oacute;nimo.")
    if not valores["fecha"]:
        raise ValueError("Selecciona una fecha v&aacute;lida.")
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
        raise ValueError("Completa todos los valores num&eacute;ricos con n&uacute;meros v&aacute;lidos.") from error
    if not 0 <= hora <= 23 or cantidad <= 0 or precio < 0:
        raise ValueError("La hora debe estar entre 0 y 23; cantidad y precio deben ser v&aacute;lidos.")
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
        raise ValueError("No se encontró el número de factura en el PDF.")
    identificador = identificador_encontrado.group(1)
    fecha_encontrada = re.search(
        r"fecha(?:\s+(?:de\s+)?emisi[oó]n)?\s*[:#-]?\s*(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        texto, flags=re.IGNORECASE,
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

    if not subtotal_texto:
        # En algunos PDFs el valor queda antes del rótulo por el orden visual
        # de extracción del documento (ej.: "$226.807,00 TOTAL BRUTO").
        subtotal_invertido = re.search(
            r"\$?\s*(\d[\d.,]*)\s*(?=TOTAL\s+BRUTO)", texto, flags=re.IGNORECASE
        )
        subtotal_texto = subtotal_invertido.group(1) if subtotal_invertido else None
    if not subtotal_texto:
        raise ValueError("No se encontró el subtotal o total bruto en el PDF.")
    if not total_texto:
        raise ValueError("No se encontró el total a pagar en el PDF.")
    subtotal = _numero_pdf(subtotal_texto)
    total = _numero_pdf(total_texto)
    impuesto = _numero_pdf(impuesto_texto) if impuesto_texto else round(total - subtotal, 2)
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
        r"\b(?:cliente|facturado\s+a|señor(?:es)?)\s*[:\-]?\s*"
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
        try:
            usuario = autenticar_usuario(request.form.get("usuario", ""), request.form.get("contrasena", ""))
        except Exception as error:
            flash(f"No fue posible conectar con PostgreSQL: {error}", "danger")
            return render_template("login.html")
        if not usuario:
            flash("Usuario o contraseña incorrectos.", "danger")
        else:
            session["usuario"] = usuario
            return redirect(url_for("dashboard"))
    return render_template("login.html")


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
        flash(f"No fue posible consultar PostgreSQL: {error}", "danger")
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
def ejecutar():
    """Ejecuta el motor híbrido y persiste su resultado en PostgreSQL local."""
    try:
        _, metricas, _ = ejecutar_experimento(guardar_en_postgres=True)
        flash(f"Experimento guardado. Puntaje F1: {float(metricas['f1']) * 100:.1f}%.", "success")
    except Exception as error:
        flash(f"No fue posible ejecutar el experimento: {error}", "danger")
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
        flash(f"No fue posible registrar la decisión: {error}", "danger")
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
        flash("Primero abre la recomendacion para generar una propuesta.", "warning")
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
        flash(f"No fue posible registrar la decision: {error}", "danger")
    return redirect(url_for("recomendacion_cargada", factura_id=factura_id))


@app.post("/regenerar-datos")
@requiere_inicio_sesion
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
        flash(f"No fue posible regenerar los datos: {error}", "danger")
    return redirect(url_for("dashboard"))


@app.route("/simulador", methods=["GET", "POST"])
@requiere_inicio_sesion
def simulador():
    """Permite demostrar el motor h&iacute;brido con una factura creada a mano."""
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
            flash(f"No fue posible analizar la factura: {error}", "danger")
    return render_template("simulador.html", valores=valores, resultado=resultado, umbral=umbral)


@app.post("/limpiar-pruebas-manuales")
@requiere_inicio_sesion
def limpiar_pruebas_manuales():
    """Borra solo las facturas creadas por el formulario de prueba manual."""
    try:
        eliminadas = limpiar_facturas_manuales(int(session["usuario"]["id"]))
        flash(f"Se eliminaron {eliminadas} carga(s) de Prueba manual.", "success")
    except Exception as error:
        flash(f"No fue posible limpiar las pruebas manuales: {error}", "danger")
    return redirect(url_for("simulador"))


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
                    tabla = pd.read_csv(archivo)
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
                alertas_archivo = obtener_alertas_de_carga(carga_id)
                facturas_archivo = obtener_facturas_de_carga(carga_id)
            except Exception as error:
                flash(f"No fue posible analizar el archivo: {error}", "danger")
    return render_template(
        "cargar_facturas.html", resumen=resumen, alertas=alertas_archivo,
        facturas=facturas_archivo, nombre_archivo=nombre_archivo,
    )


@app.route("/revision-cargas")
@requiere_inicio_sesion
def revision_cargas():
    """Presenta la cola de facturas importadas que requieren decisi&oacute;n humana."""
    try:
        alertas = obtener_alertas_cargadas()
    except Exception as error:
        flash(f"No fue posible consultar las facturas cargadas: {error}", "danger")
        alertas = []
    return render_template("revision_cargas.html", alertas=alertas)


@app.route("/factura-cargada/<int:factura_id>", methods=["GET", "POST"])
@requiere_inicio_sesion
def factura_cargada(factura_id: int):
    """Muestra todos los datos de una factura cargada y registra la revisi&oacute;n humana."""
    if request.method == "POST":
        try:
            actualizar_estado_factura_cargada(factura_id, request.form.get("estado", "pendiente"))
            flash("Decisi&oacute;n de revisi&oacute;n guardada.", "success")
        except Exception as error:
            flash(f"No fue posible guardar la revisi&oacute;n: {error}", "danger")
        return redirect(url_for("factura_cargada", factura_id=factura_id))
    factura = obtener_factura_cargada(factura_id)
    if not factura:
        abort(404)
    return render_template("factura.html", factura=factura, es_cargada=True)


@app.route("/factura-sintetica/<numero_factura>")
@requiere_inicio_sesion
def factura_sintetica(numero_factura: str):
    """Muestra una factura del experimento como documento de demostraci&oacute;n."""
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
        flash(f"No fue posible consultar alertas: {error}", "danger")
        lista_alertas = []
        alertas_cargadas = []
    return render_template(
        "alertas.html", alertas=lista_alertas, alertas_cargadas=alertas_cargadas
    )


if __name__ == "__main__":
    # Solo se expone en el computador propio; no publica el sistema en internet.
    app.run(host="127.0.0.1", port=5000, debug=False)
