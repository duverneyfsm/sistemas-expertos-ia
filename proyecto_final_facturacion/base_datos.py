"""Persistencia local del experimento en PostgreSQL.

La contraseña nunca se escribe en el código: se toma del archivo .env local.
"""

from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg
from dotenv import load_dotenv
from psycopg import sql
from psycopg.rows import dict_row

from config import RAIZ_PROYECTO, RUTA_ENV, SEMILLA
from seguridad import crear_hash_contrasena, verificar_contrasena


def _cargar_configuracion() -> dict[str, str | int]:
    """Lee la configuración local y falla con un mensaje claro si falta la clave."""
    load_dotenv(RUTA_ENV)
    contrasena = os.getenv("DB_PASSWORD", "")
    if not contrasena or contrasena == "CAMBIAR_POR_TU_CONTRASENA_LOCAL":
        raise RuntimeError(
            "Configura DB_PASSWORD en el archivo .env antes de usar PostgreSQL. "
            "Puedes copiar .env.example y escribir tu contraseña local."
        )
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": os.getenv("DB_NAME", "factuguard_ia"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": contrasena,
    }


def conectar(base_administrativa: bool = False) -> psycopg.Connection:
    """Abre una conexión a PostgreSQL local o a la base administrativa postgres."""
    parametros = _cargar_configuracion()
    if base_administrativa:
        load_dotenv(RUTA_ENV)
        parametros["dbname"] = os.getenv("DB_ADMIN_NAME", "postgres")
    return psycopg.connect(**parametros)


def crear_base_de_datos() -> bool:
    """Crea factuguard_ia si aún no existe; devuelve True cuando la crea."""
    parametros = _cargar_configuracion()
    nombre = str(parametros["dbname"])
    with conectar(base_administrativa=True) as conexion:
        conexion.autocommit = True
        existe = conexion.execute("SELECT 1 FROM pg_database WHERE datname = %s", (nombre,)).fetchone()
        if existe:
            return False
        conexion.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nombre)))
        return True


def crear_esquema() -> None:
    """Crea tablas e índices definidos en schema.sql, sin borrar información previa."""
    script = (Path(RAIZ_PROYECTO) / "schema.sql").read_text(encoding="utf-8")
    with conectar() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(script)
            _asegurar_campos_trazabilidad(cursor)
            _asegurar_restricciones_integridad(cursor)


def inicializar_base_de_datos() -> bool:
    """Prepara la base y sus tablas; es seguro ejecutarlo más de una vez."""
    fue_creada = crear_base_de_datos()
    crear_esquema()
    return fue_creada


def _valor_base(valor: Any) -> Any:
    """Convierte valores NumPy/Pandas en tipos que Psycopg puede almacenar."""
    if pd.isna(valor):
        return None
    return valor.item() if hasattr(valor, "item") else valor


def _asegurar_campos_trazabilidad(cursor) -> None:
    """Agrega datos de identificacion a bases ya creadas sin borrar su historial."""
    cursor.execute(
        """
        ALTER TABLE facturas_cargadas
            ADD COLUMN IF NOT EXISTS nit_emisor VARCHAR(30) NOT NULL DEFAULT 'NO-REPORTADO',
            ADD COLUMN IF NOT EXISTS cufe VARCHAR(150) NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS tipo_documento VARCHAR(60) NOT NULL DEFAULT 'Factura electronica',
            ADD COLUMN IF NOT EXISTS validacion_dian VARCHAR(100) NOT NULL DEFAULT 'No verificada por FactuGuard',
            ADD COLUMN IF NOT EXISTS descripcion_detallada TEXT NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS detalle_lineas JSONB NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN IF NOT EXISTS prioridad_alerta VARCHAR(10) NOT NULL DEFAULT 'baja',
            ADD COLUMN IF NOT EXISTS version_modelo VARCHAR(100) NOT NULL DEFAULT 'FactuGuard IA 1.1 (Reglas + Isolation Forest + KNN + Perceptrón)';
        """
    )
    # Esta instruccion me ayuda a que las bases creadas antes de la neurona
    # tambien guarden el nombre actualizado del modelo en las nuevas cargas.
    cursor.execute(
        "ALTER TABLE facturas_cargadas ALTER COLUMN version_modelo "
        "SET DEFAULT 'FactuGuard IA 1.1 (Reglas + Isolation Forest + KNN + Perceptrón)'"
    )
    # Clasifica tambien las alertas que existian antes de agregar esta columna.
    cursor.execute(
        """
        UPDATE facturas_cargadas
        SET prioridad_alerta = CASE
            WHEN lower(motivo_alerta) LIKE '%impuesto%'
              OR lower(motivo_alerta) LIKE '%inconsistencia%'
              OR lower(motivo_alerta) LIKE '%duplic%' THEN 'alta'
            WHEN alerta_hibrida THEN 'media'
            ELSE 'baja'
        END
        WHERE prioridad_alerta = 'baja' AND alerta_hibrida = TRUE
        """
    )


def _agregar_restriccion_si_falta(cursor, tabla: str, nombre: str, definicion: str) -> None:
    """Agrega una regla SQL a una base existente solo cuando aun no esta creada.

    Esto permite mejorar una base de datos ya usada sin borrar las facturas
    ni aplicar la misma restriccion dos veces.
    """
    cursor.execute(
        "SELECT 1 FROM pg_constraint WHERE conrelid = %s::regclass AND conname = %s",
        (tabla, nombre),
    )
    if cursor.fetchone() is None:
        # Los nombres se protegen con sql.Identifier. La definicion es fija en
        # este archivo, nunca llega desde un formulario ni desde un archivo.
        cursor.execute(
            sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} {}").format(
                sql.Identifier(tabla), sql.Identifier(nombre), sql.SQL(definicion)
            )
        )


def _asegurar_restricciones_integridad(cursor) -> None:
    """Actualiza bases antiguas con claves unicas y CHECK de buenas practicas.

    No valida que subtotal + impuesto sea igual al total: esa diferencia puede
    ser una anomalia real que FactuGuard necesita conservar y reportar.
    """
    restricciones = [
        ("experimentos", "ck_experimentos_registros", "CHECK (registros_evaluados >= 0)"),
        ("experimentos", "ck_experimentos_alertas", "CHECK (alertas_hibridas BETWEEN 0 AND registros_evaluados)"),
        ("experimentos", "ck_experimentos_metricas", "CHECK (precision BETWEEN 0 AND 1 AND exhaustividad BETWEEN 0 AND 1 AND f1 BETWEEN 0 AND 1 AND especificidad BETWEEN 0 AND 1)"),
        ("experimentos", "ck_experimentos_tiempo", "CHECK (milisegundos_por_registro >= 0)"),
        ("facturas", "uq_facturas_origen", "UNIQUE (experimento_id, conjunto, indice_origen)"),
        ("facturas", "ck_facturas_indice", "CHECK (indice_origen >= 0)"),
        ("facturas", "ck_facturas_cantidad", "CHECK (cantidad > 0)"),
        ("facturas", "ck_facturas_valores", "CHECK (precio_unitario >= 0 AND subtotal >= 0 AND impuesto_valor >= 0 AND total >= 0)"),
        ("facturas", "ck_facturas_porcentajes", "CHECK (descuento_pct BETWEEN 0 AND 1 AND tasa_iva BETWEEN 0 AND 1)"),
        ("facturas", "ck_facturas_puntaje", "CHECK (puntaje_ia IS NULL OR puntaje_ia >= 0)"),
        ("alertas", "uq_alertas_factura_experimento", "UNIQUE (experimento_id, factura_id)"),
        ("alertas", "ck_alertas_puntaje", "CHECK (puntaje_ia IS NULL OR puntaje_ia >= 0)"),
        ("cargas_archivo", "ck_cargas_totales", "CHECK (total_facturas >= 0 AND total_alertas BETWEEN 0 AND total_facturas)"),
        ("facturas_cargadas", "uq_facturas_cargadas_origen", "UNIQUE (carga_id, indice_origen)"),
        ("facturas_cargadas", "ck_facturas_cargadas_indice", "CHECK (indice_origen >= 0)"),
        ("facturas_cargadas", "ck_facturas_cargadas_cantidad", "CHECK (cantidad > 0)"),
        ("facturas_cargadas", "ck_facturas_cargadas_valores", "CHECK (precio_unitario >= 0 AND subtotal >= 0 AND impuesto_valor >= 0 AND total >= 0)"),
        ("facturas_cargadas", "ck_facturas_cargadas_porcentajes", "CHECK (descuento_pct BETWEEN 0 AND 1 AND tasa_iva BETWEEN 0 AND 1)"),
        ("facturas_cargadas", "ck_facturas_cargadas_puntaje", "CHECK (puntaje_ia IS NULL OR puntaje_ia >= 0)"),
        ("facturas_cargadas", "ck_facturas_cargadas_prioridad", "CHECK (prioridad_alerta IN ('alta', 'media', 'baja'))"),
    ]
    for tabla, nombre, definicion in restricciones:
        _agregar_restriccion_si_falta(cursor, tabla, nombre, definicion)


def _filas_facturas(facturas: pd.DataFrame, experimento_id: int, conjunto: str) -> list[tuple[Any, ...]]:
    """Prepara cada fila del DataFrame para una inserción parametrizada."""
    columnas = [
        "factura_id", "cliente_sintetico", "categoria", "fecha", "hora", "cantidad",
        "precio_unitario", "descuento_pct", "tasa_iva", "subtotal", "impuesto_valor", "total",
        "es_anomalia", "tipo_anomalia", "alerta_reglas", "alerta_ia", "alerta_hibrida", "puntaje_ia",
    ]
    # Pandas representa con frecuencia los booleanos como enteros NumPy (0 y 1).
    # PostgreSQL no convierte automáticamente esos enteros a BOOLEAN, por eso se
    # normalizan aquí antes de enviarlos mediante la consulta parametrizada.
    columnas_booleanas = {"es_anomalia", "alerta_reglas", "alerta_ia", "alerta_hibrida"}
    filas: list[tuple[Any, ...]] = []
    for indice, fila in facturas.iterrows():
        valores = []
        for columna in columnas:
            valor = _valor_base(fila.get(columna, False if columna.startswith("alerta_") else None))
            valores.append(bool(valor) if columna in columnas_booleanas else valor)
        filas.append((experimento_id, conjunto, int(indice), *valores))
    return filas


def guardar_experimento(calibracion: pd.DataFrame, prueba: pd.DataFrame,
                        metricas: dict[str, object], semilla: int = SEMILLA) -> int:
    """Guarda una ejecución completa: métricas, facturas y alertas auditables."""
    with conectar() as conexion:
        with conexion.cursor() as cursor:
            # Si se vuelve a cargar el mismo documento, se reemplaza su versión
            # anterior en lugar de duplicarlo en la bandeja de revisión.
            cursor.execute(
                """
                INSERT INTO experimentos (
                    modelo, semilla, registros_evaluados, alertas_hibridas, precision,
                    exhaustividad, f1, especificidad, milisegundos_por_registro
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (
                    "Reglas de negocio + Isolation Forest + KNN + perceptrón", semilla,
                    len(prueba), int(prueba["alerta_hibrida"].sum()), metricas["precision"],
                    metricas["exhaustividad"], metricas["f1"], metricas["especificidad"],
                    metricas["milisegundos_por_registro"],
                ),
            )
            experimento_id = int(cursor.fetchone()[0])
            insertar_factura = """
                INSERT INTO facturas (
                    experimento_id, conjunto, indice_origen, factura_id, cliente_sintetico, categoria,
                    fecha, hora, cantidad, precio_unitario, descuento_pct, tasa_iva, subtotal,
                    impuesto_valor, total, es_anomalia, tipo_anomalia, alerta_reglas, alerta_ia,
                    alerta_hibrida, puntaje_ia
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.executemany(insertar_factura, _filas_facturas(calibracion, experimento_id, "calibracion"))
            cursor.executemany(insertar_factura, _filas_facturas(prueba, experimento_id, "prueba"))

            alertas = prueba.loc[prueba["alerta_hibrida"]]
            insertar_alerta = """
                INSERT INTO alertas (experimento_id, factura_id, tipo_anomalia, origen, puntaje_ia, motivo)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            filas_alertas = []
            for _, fila in alertas.iterrows():
                origen = "reglas_ia" if fila["alerta_reglas"] and fila["alerta_ia"] else (
                    "reglas" if fila["alerta_reglas"] else "ia"
                )
                filas_alertas.append((
                    experimento_id, fila["factura_id"], fila["tipo_anomalia"], origen,
                    _valor_base(fila["puntaje_ia"]), fila["motivo_alerta"],
                ))
            cursor.executemany(insertar_alerta, filas_alertas)
    return experimento_id


def limpiar_experimentos_sinteticos() -> int:
    """Elimina el historial sintético; las alertas y facturas asociadas se borran en cascada."""
    with conectar() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute("DELETE FROM experimentos")
            return cursor.rowcount


def _asegurar_tabla_recomendaciones(cursor) -> None:
    """Crea la tabla en instalaciones previas sin exigir reinicializar la base."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS recomendaciones_ia (
            id BIGSERIAL PRIMARY KEY,
            alerta_id BIGINT NOT NULL UNIQUE REFERENCES alertas(id) ON DELETE CASCADE,
            recomendacion JSONB NOT NULL,
            contexto_aprendizaje JSONB NOT NULL,
            decision_usuario VARCHAR(20) CHECK (decision_usuario IN ('aprobada', 'rechazada', 'editada')),
            correccion_final JSONB,
            usuario_id BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,
            creada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            decidida_en TIMESTAMPTZ
        )
        """
    )


def _asegurar_tabla_recomendaciones_cargadas(cursor) -> None:
    """Crea el historial de recomendaciones para CSV, Excel, PDF y pruebas manuales."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS recomendaciones_cargadas (
            id BIGSERIAL PRIMARY KEY,
            factura_cargada_id BIGINT NOT NULL UNIQUE
                REFERENCES facturas_cargadas(id) ON DELETE CASCADE,
            recomendacion JSONB NOT NULL,
            contexto_aprendizaje JSONB NOT NULL,
            decision_usuario VARCHAR(20)
                CHECK (decision_usuario IN ('aprobada', 'rechazada', 'editada')),
            correccion_final JSONB,
            usuario_id BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,
            creada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            decidida_en TIMESTAMPTZ
        )
        """
    )


def obtener_alerta_sintetica(alerta_id: int) -> dict[str, object] | None:
    """Obtiene una alerta y los valores de la factura requeridos para recomendar."""
    with conectar() as conexion:
        with conexion.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT a.id AS alerta_id, a.factura_id, a.tipo_anomalia, a.origen,
                       a.puntaje_ia, a.motivo, a.estado_revision,
                       f.cantidad, f.precio_unitario, f.descuento_pct, f.hora, f.tasa_iva,
                       f.subtotal, f.impuesto_valor, f.total
                FROM alertas a
                JOIN LATERAL (
                    SELECT f2.* FROM facturas f2
                    WHERE f2.experimento_id = a.experimento_id AND f2.factura_id = a.factura_id
                    ORDER BY f2.es_anomalia DESC, f2.id DESC LIMIT 1
                ) f ON TRUE
                WHERE a.id = %s
                """,
                (alerta_id,),
            )
            return cursor.fetchone()


def obtener_recomendacion(alerta_id: int) -> dict[str, object] | None:
    """Busca la propuesta existente para no reemplazar una decisión humana."""
    with conectar() as conexion:
        with conexion.cursor(row_factory=dict_row) as cursor:
            _asegurar_tabla_recomendaciones(cursor)
            cursor.execute("SELECT * FROM recomendaciones_ia WHERE alerta_id = %s", (alerta_id,))
            return cursor.fetchone()


def guardar_recomendacion(alerta_id: int, recomendacion: dict[str, object]) -> int:
    """Guarda una propuesta y sus características de aprendizaje auditables."""
    with conectar() as conexion:
        with conexion.cursor() as cursor:
            _asegurar_tabla_recomendaciones(cursor)
            cursor.execute("SELECT id FROM recomendaciones_ia WHERE alerta_id = %s", (alerta_id,))
            existente = cursor.fetchone()
            if existente:
                return int(existente[0])
            contexto = {"caracteristicas": recomendacion.get("caracteristicas", [])}
            cursor.execute(
                """
                INSERT INTO recomendaciones_ia (alerta_id, recomendacion, contexto_aprendizaje)
                VALUES (%s, %s::jsonb, %s::jsonb) RETURNING id
                """,
                (alerta_id, json.dumps(recomendacion, default=str), json.dumps(contexto)),
            )
            return int(cursor.fetchone()[0])


def aplicar_ajuste_recomendado(alerta_id: int,
                               campos_sugeridos: dict[str, object]) -> dict[str, object]:
    """Aplica una propuesta verificable a una factura sintética y conserva el antes.

    Solo admite importes que el recomendador calcula con reglas explícitas;
    nunca utiliza esta función para una alerta que requiera criterio humano.
    """
    campos_permitidos = {"tasa_iva", "subtotal", "impuesto_valor", "total"}
    cambios = {
        campo: valor for campo, valor in campos_sugeridos.items()
        if campo in campos_permitidos and valor is not None
    }
    if not cambios:
        raise ValueError("La propuesta no contiene un ajuste automático aplicable.")

    with conectar() as conexion:
        with conexion.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT f.id, f.tasa_iva, f.subtotal, f.impuesto_valor, f.total
                FROM alertas a
                JOIN LATERAL (
                    SELECT f2.* FROM facturas f2
                    WHERE f2.experimento_id = a.experimento_id
                      AND f2.factura_id = a.factura_id
                    ORDER BY f2.es_anomalia DESC, f2.id DESC
                    LIMIT 1
                ) f ON TRUE
                WHERE a.id = %s
                """,
                (alerta_id,),
            )
            factura = cursor.fetchone()
            if not factura:
                raise ValueError("No se encontró la factura asociada a esta alerta.")

            asignaciones = sql.SQL(", ").join(
                sql.SQL("{} = %s").format(sql.Identifier(campo)) for campo in cambios
            )
            cursor.execute(
                sql.SQL("UPDATE facturas SET {} WHERE id = %s").format(asignaciones),
                (*cambios.values(), factura["id"]),
            )
            antes = {campo: factura[campo] for campo in campos_permitidos}
            return {"antes": antes, "campos_aplicados": cambios}


def registrar_decision_recomendacion(recomendacion_id: int, decision: str,
                                     correccion_final: dict[str, object], usuario_id: int) -> dict[str, object]:
    """Registra una sola decisión humana y devuelve el contexto para entrenar."""
    if decision not in {"aprobada", "rechazada", "editada"}:
        raise ValueError("La decisión de la recomendación no es válida.")
    with conectar() as conexion:
        with conexion.cursor(row_factory=dict_row) as cursor:
            _asegurar_tabla_recomendaciones(cursor)
            cursor.execute(
                """
                UPDATE recomendaciones_ia
                SET decision_usuario = %s, correccion_final = %s::jsonb, usuario_id = %s,
                    decidida_en = CURRENT_TIMESTAMP
                WHERE id = %s AND decision_usuario IS NULL
                RETURNING contexto_aprendizaje
                """,
                (decision, json.dumps(correccion_final, default=str), usuario_id, recomendacion_id),
            )
            contexto = cursor.fetchone()
            if not contexto:
                raise ValueError("Esta recomendación ya fue decidida y no puede modificarse.")
            return contexto["contexto_aprendizaje"]


def obtener_recomendacion_cargada(factura_id_interno: int) -> dict[str, object] | None:
    """Busca una recomendacion ya generada para una factura importada."""
    with conectar() as conexion:
        with conexion.cursor(row_factory=dict_row) as cursor:
            _asegurar_tabla_recomendaciones_cargadas(cursor)
            cursor.execute(
                "SELECT * FROM recomendaciones_cargadas WHERE factura_cargada_id = %s",
                (factura_id_interno,),
            )
            return cursor.fetchone()


def guardar_recomendacion_cargada(factura_id_interno: int,
                                  recomendacion: dict[str, object]) -> int:
    """Conserva la recomendacion de una factura manual o importada."""
    with conectar() as conexion:
        with conexion.cursor() as cursor:
            _asegurar_tabla_recomendaciones_cargadas(cursor)
            cursor.execute(
                "SELECT id FROM recomendaciones_cargadas WHERE factura_cargada_id = %s",
                (factura_id_interno,),
            )
            existente = cursor.fetchone()
            if existente:
                return int(existente[0])
            contexto = {"caracteristicas": recomendacion.get("caracteristicas", [])}
            cursor.execute(
                """
                INSERT INTO recomendaciones_cargadas
                    (factura_cargada_id, recomendacion, contexto_aprendizaje)
                VALUES (%s, %s::jsonb, %s::jsonb) RETURNING id
                """,
                (
                    factura_id_interno, json.dumps(recomendacion, default=str),
                    json.dumps(contexto),
                ),
            )
            return int(cursor.fetchone()[0])


def aplicar_ajuste_recomendado_cargado(factura_id_interno: int,
                                       campos_sugeridos: dict[str, object]) -> dict[str, object]:
    """Aplica a una factura cargada un calculo verificable y conserva el antes."""
    campos_permitidos = {"tasa_iva", "subtotal", "impuesto_valor", "total"}
    cambios = {
        campo: valor for campo, valor in campos_sugeridos.items()
        if campo in campos_permitidos and valor is not None
    }
    if not cambios:
        raise ValueError("La propuesta no contiene un ajuste automatico aplicable.")
    with conectar() as conexion:
        with conexion.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT id, tasa_iva, subtotal, impuesto_valor, total
                FROM facturas_cargadas WHERE id = %s
                """,
                (factura_id_interno,),
            )
            factura = cursor.fetchone()
            if not factura:
                raise ValueError("No se encontro la factura cargada.")
            asignaciones = sql.SQL(", ").join(
                sql.SQL("{} = %s").format(sql.Identifier(campo)) for campo in cambios
            )
            cursor.execute(
                sql.SQL("UPDATE facturas_cargadas SET {} WHERE id = %s").format(asignaciones),
                (*cambios.values(), factura_id_interno),
            )
            antes = {campo: factura[campo] for campo in campos_permitidos}
            return {"antes": antes, "campos_aplicados": cambios}


def registrar_decision_recomendacion_cargada(recomendacion_id: int, decision: str,
                                             correccion_final: dict[str, object],
                                             usuario_id: int) -> dict[str, object]:
    """Guarda la decision de una recomendacion de factura cargada."""
    if decision not in {"aprobada", "rechazada", "editada"}:
        raise ValueError("La decision de la recomendacion no es valida.")
    with conectar() as conexion:
        with conexion.cursor(row_factory=dict_row) as cursor:
            _asegurar_tabla_recomendaciones_cargadas(cursor)
            cursor.execute(
                """
                UPDATE recomendaciones_cargadas
                SET decision_usuario = %s, correccion_final = %s::jsonb, usuario_id = %s,
                    decidida_en = CURRENT_TIMESTAMP
                WHERE id = %s AND decision_usuario IS NULL
                RETURNING contexto_aprendizaje, factura_cargada_id
                """,
                (decision, json.dumps(correccion_final, default=str), usuario_id, recomendacion_id),
            )
            contexto = cursor.fetchone()
            if not contexto:
                raise ValueError("Esta recomendacion ya fue decidida y no puede modificarse.")
            estado = "descartada" if decision == "rechazada" else "revisada"
            cursor.execute(
                """
                UPDATE facturas_cargadas
                SET estado_revision = %s, revisado_en = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (estado, contexto["factura_cargada_id"]),
            )
            return contexto["contexto_aprendizaje"]


def limpiar_facturas_manuales(usuario_id: int) -> int:
    """Elimina solo las facturas creadas en Prueba manual por el usuario actual."""
    with conectar() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM cargas_archivo
                WHERE nombre_archivo = 'Prueba manual' AND usuario_id = %s
                RETURNING id
                """,
                (usuario_id,),
            )
            return len(cursor.fetchall())


def eliminar_carga_archivo(carga_id: int, usuario_id: int) -> bool:
    """Elimina una carga del propietario actual y sus datos asociados en cascada."""
    with conectar() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM cargas_archivo
                WHERE id = %s AND usuario_id = %s
                RETURNING id
                """,
                (carga_id, usuario_id),
            )
            return cursor.fetchone() is not None


def eliminar_factura_cargada(factura_id_interno: int, usuario_id: int,
                             es_administrador: bool = False) -> bool:
    """Elimina una factura importada y sus recomendaciones asociadas.

    La autorización de administrador se valida en la ruta web. Si la factura
    era la última de su carga, también se elimina el contenedor vacío.
    """
    with conectar() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM facturas_cargadas f
                USING cargas_archivo c
                WHERE f.id = %s
                  AND c.id = f.carga_id
                  AND (%s OR c.usuario_id = %s)
                RETURNING f.carga_id
                """,
                (factura_id_interno, es_administrador, usuario_id),
            )
            eliminada = cursor.fetchone()
            if not eliminada:
                return False

            carga_id = int(eliminada[0])
            # La tabla de cargas conserva los totales para el resumen. Se
            # recalculan para que coincidan con las facturas aún conservadas.
            cursor.execute(
                """
                UPDATE cargas_archivo c
                SET total_facturas = conteo.total_facturas,
                    total_alertas = conteo.total_alertas
                FROM (
                    SELECT carga_id, COUNT(*)::integer AS total_facturas,
                           COUNT(*) FILTER (WHERE alerta_hibrida)::integer AS total_alertas
                    FROM facturas_cargadas
                    WHERE carga_id = %s
                    GROUP BY carga_id
                ) conteo
                WHERE c.id = conteo.carga_id
                """,
                (carga_id,),
            )
            cursor.execute(
                """
                DELETE FROM cargas_archivo c
                WHERE c.id = %s
                  AND NOT EXISTS (
                      SELECT 1 FROM facturas_cargadas f WHERE f.carga_id = c.id
                  )
                """,
                (carga_id,),
            )
            return True


def _lista(resultado: pd.DataFrame, columna: str, defecto: Any = None) -> list[Any]:
    """Convierte una columna en lista de tipos nativos de Python (None si falta el dato)."""
    if columna not in resultado.columns:
        return [defecto] * len(resultado)
    serie = resultado[columna].astype(object)
    return serie.where(serie.notna(), None).tolist()


def _detalle_lineas_json(valor: Any, descripcion: Any) -> str:
    """Convierte el detalle de una factura a JSONB seguro para PostgreSQL."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)) or valor == "":
        texto = str(descripcion or "").strip()
        return json.dumps([{"descripcion": texto}] if texto else [], ensure_ascii=False)
    if isinstance(valor, str):
        try:
            json.loads(valor)
            return valor
        except json.JSONDecodeError:
            return json.dumps([{"descripcion": valor}], ensure_ascii=False)
    return json.dumps(valor, default=str, ensure_ascii=False)


def guardar_carga_archivo(resultado: pd.DataFrame, nombre_archivo: str,
                          usuario_id: int | None) -> int:
    """Guarda datos anonimizados y alertas para su revisión humana posterior.

    El archivo original no se almacena: solo las columnas analizadas y el
    resultado explicable de cada factura. Con archivos grandes se trabaja por
    lotes (una consulta para todos los documentos, no una por factura).
    """
    total = len(resultado)
    cufe = [str(valor or "").strip() for valor in _lista(resultado, "cufe", "")]
    nit = [str(valor or "NO-REPORTADO").strip().upper() for valor in _lista(resultado, "nit_emisor", "NO-REPORTADO")]
    numero = _lista(resultado, "factura_id")
    fecha = _lista(resultado, "fecha")
    cliente = _lista(resultado, "cliente_sintetico")
    descripcion_detallada = [str(valor or "") for valor in _lista(resultado, "descripcion_detallada", "")]
    detalle_lineas = [
        _detalle_lineas_json(valor, descripcion)
        for valor, descripcion in zip(_lista(resultado, "detalle_lineas", ""), descripcion_detallada)
    ]

    with conectar() as conexion:
        with conexion.cursor() as cursor:
            _asegurar_campos_trazabilidad(cursor)
            _asegurar_restricciones_integridad(cursor)
            # Reemplaza una carga previa del mismo documento y evita duplicados.
            # CUFE es la identificacion preferida. Si no existe, se usa NIT,
            # numero y fecha; las pruebas sin NIT usan numero, fecha y cliente.
            por_cufe = sorted({c for c in cufe if c})
            if por_cufe:
                cursor.execute("DELETE FROM facturas_cargadas WHERE cufe = ANY(%s)", (por_cufe,))
            con_nit = [i for i in range(total) if not cufe[i] and nit[i] and nit[i] != "NO-REPORTADO"]
            if con_nit:
                cursor.execute(
                    """
                    DELETE FROM facturas_cargadas f
                    USING unnest(%s::text[], %s::date[], %s::text[]) AS x(factura_id, fecha, nit_emisor)
                    WHERE f.factura_id = x.factura_id AND f.fecha = x.fecha AND f.nit_emisor = x.nit_emisor
                    """,
                    ([numero[i] for i in con_nit], [fecha[i] for i in con_nit], [nit[i] for i in con_nit]),
                )
            sin_nit = [i for i in range(total) if not cufe[i] and not (nit[i] and nit[i] != "NO-REPORTADO")]
            if sin_nit:
                cursor.execute(
                    """
                    DELETE FROM facturas_cargadas f
                    USING unnest(%s::text[], %s::date[], %s::text[]) AS x(factura_id, fecha, cliente)
                    WHERE f.factura_id = x.factura_id AND f.fecha = x.fecha AND f.cliente_sintetico = x.cliente
                    """,
                    ([numero[i] for i in sin_nit], [fecha[i] for i in sin_nit], [cliente[i] for i in sin_nit]),
                )
            cursor.execute(
                """
                INSERT INTO cargas_archivo (nombre_archivo, usuario_id, total_facturas, total_alertas)
                VALUES (%s, %s, %s, %s) RETURNING id
                """,
                (nombre_archivo, usuario_id, total, int(resultado["alerta_hibrida"].sum())),
            )
            carga_id = int(cursor.fetchone()[0])
            # COPY carga miles de filas de una sola vez: es varias veces más rápido que INSERT por fila.
            copiar = """
                COPY facturas_cargadas (
                    carga_id, indice_origen, factura_id, cliente_sintetico, categoria, descripcion_detallada,
                    detalle_lineas, fecha, hora,
                    cantidad, precio_unitario, descuento_pct, tasa_iva, subtotal, impuesto_valor,
                    total, alerta_reglas, alerta_ia, alerta_hibrida, puntaje_ia, motivo_alerta,
                    nit_emisor, cufe, tipo_documento, validacion_dian, prioridad_alerta, version_modelo
                ) FROM STDIN
            """
            filas = zip(
                [carga_id] * total, [int(i) for i in resultado.index], numero, cliente,
                _lista(resultado, "categoria"), descripcion_detallada, detalle_lineas, fecha,
                [int(h) for h in _lista(resultado, "hora")],
                _lista(resultado, "cantidad"), _lista(resultado, "precio_unitario"),
                _lista(resultado, "descuento_pct"), _lista(resultado, "tasa_iva"),
                _lista(resultado, "subtotal"), _lista(resultado, "impuesto_valor"),
                _lista(resultado, "total"), [bool(v) for v in _lista(resultado, "alerta_reglas", False)],
                [bool(v) for v in _lista(resultado, "alerta_ia", False)],
                [bool(v) for v in _lista(resultado, "alerta_hibrida", False)],
                _lista(resultado, "puntaje_ia"), _lista(resultado, "motivo_alerta"),
                nit, cufe, _lista(resultado, "tipo_documento", "Factura electronica"),
                _lista(resultado, "validacion_dian", "No verificada por FactuGuard"),
                _lista(resultado, "prioridad_alerta", "baja"),
                ["FactuGuard IA 1.1 (Reglas + Isolation Forest + KNN + Perceptrón)"] * total,
            )
            with cursor.copy(copiar) as copia:
                for fila in filas:
                    copia.write_row(fila)
            # Las cabeceras de cargas que ya no tienen facturas se descartan.
            cursor.execute(
                "DELETE FROM cargas_archivo c WHERE NOT EXISTS "
                "(SELECT 1 FROM facturas_cargadas f WHERE f.carga_id = c.id)"
            )
    return carga_id


def obtener_id_usuario(nombre_usuario: str) -> int | None:
    """Busca el identificador de un usuario activo (para atribuirle cargas por lotes)."""
    with conectar() as conexion:
        fila = conexion.execute(
            "SELECT id FROM usuarios WHERE nombre_usuario = %s AND activo", (nombre_usuario.strip().lower(),)
        ).fetchone()
    return int(fila[0]) if fila else None


def obtener_alertas_cargadas(limite: int = 200) -> list[dict[str, object]]:
    """Lista facturas importadas que necesitan revisión humana."""
    with conectar() as conexion:
        with conexion.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT f.id, f.factura_id, f.cliente_sintetico, f.categoria, f.fecha, f.hora, f.total,
                       f.puntaje_ia, f.motivo_alerta, f.prioridad_alerta, f.estado_revision,
                       c.nombre_archivo, c.creada_en, c.usuario_id
                FROM facturas_cargadas f
                JOIN cargas_archivo c ON c.id = f.carga_id
                WHERE f.alerta_hibrida = TRUE
                ORDER BY CASE f.prioridad_alerta WHEN 'alta' THEN 1 WHEN 'media' THEN 2 ELSE 3 END,
                         f.fecha DESC, f.hora DESC, c.creada_en DESC, f.puntaje_ia DESC NULLS LAST
                LIMIT %s
                """,
                (limite,),
            )
            return list(cursor.fetchall())


def obtener_alertas_de_carga(carga_id: int) -> list[dict[str, object]]:
    """Devuelve las alertas de una carga concreta, incluyendo su identificador interno."""
    with conectar() as conexion:
        with conexion.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT id, factura_id, fecha, hora, motivo_alerta, puntaje_ia, prioridad_alerta, estado_revision
                FROM facturas_cargadas
                WHERE carga_id = %s AND alerta_hibrida = TRUE
                ORDER BY fecha DESC, hora DESC, puntaje_ia DESC NULLS LAST
                LIMIT 100
                """,
                (carga_id,),
            )
            return list(cursor.fetchall())


def obtener_facturas_de_carga(carga_id: int) -> list[dict[str, object]]:
    """Devuelve todas las facturas de una carga, incluso las que no alertan."""
    with conectar() as conexion:
        with conexion.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT id, factura_id, cliente_sintetico, categoria, fecha, hora, total,
                       alerta_hibrida, motivo_alerta, prioridad_alerta, estado_revision
                FROM facturas_cargadas
                WHERE carga_id = %s
                ORDER BY indice_origen
                """,
                (carga_id,),
            )
            return list(cursor.fetchall())


def obtener_facturas_cargadas_sin_alerta(limite: int = 100) -> list[dict[str, object]]:
    """Lista facturas importadas correctas para poder consultarlas después."""
    with conectar() as conexion:
        with conexion.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT f.id, f.factura_id, f.cliente_sintetico, f.categoria, f.fecha, f.hora,
                       f.total, c.nombre_archivo, c.creada_en
                FROM facturas_cargadas f
                JOIN cargas_archivo c ON c.id = f.carga_id
                WHERE f.alerta_hibrida = FALSE
                ORDER BY c.creada_en DESC, f.fecha DESC, f.hora DESC
                LIMIT %s
                """,
                (limite,),
            )
            return list(cursor.fetchall())


def obtener_resumen_cargas_usuario(usuario_id: int) -> dict[str, int]:
    """Cuenta las facturas cargadas por una persona para las tarjetas del resumen.

    Esta funcion separa las facturas correctas de las que necesitan una decision.
    Asi el dashboard no mezcla los resultados de una carga real con las pruebas
    sinteticas del experimento academico.
    """
    with conectar() as conexion:
        with conexion.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                    COUNT(*)::int AS total,
                    COUNT(*) FILTER (WHERE f.alerta_hibrida)::int AS con_alerta,
                    COUNT(*) FILTER (WHERE NOT f.alerta_hibrida)::int AS sin_alerta,
                    COUNT(*) FILTER (
                        WHERE f.alerta_hibrida AND f.estado_revision = 'pendiente'
                    )::int AS pendientes
                FROM facturas_cargadas f
                JOIN cargas_archivo c ON c.id = f.carga_id
                WHERE c.usuario_id = %s
                """,
                (usuario_id,),
            )
            return dict(cursor.fetchone() or {
                "total": 0, "con_alerta": 0, "sin_alerta": 0, "pendientes": 0,
            })


def obtener_metricas_revision_usuario(usuario_id: int) -> dict[str, int]:
    """Resume decisiones humanas para saber si las alertas estan siendo utiles."""
    with conectar() as conexion:
        with conexion.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE f.alerta_hibrida)::int AS alertas,
                    COUNT(*) FILTER (WHERE f.estado_revision = 'revisada')::int AS revisadas,
                    COUNT(*) FILTER (WHERE f.estado_revision = 'descartada')::int AS descartadas
                FROM facturas_cargadas f
                JOIN cargas_archivo c ON c.id = f.carga_id
                WHERE c.usuario_id = %s
                """,
                (usuario_id,),
            )
            metricas = dict(cursor.fetchone() or {"alertas": 0, "revisadas": 0, "descartadas": 0})
            decisiones = metricas["revisadas"] + metricas["descartadas"]
            metricas["decisiones"] = decisiones
            metricas["porcentaje_descartadas"] = round(
                (metricas["descartadas"] / decisiones) * 100, 1
            ) if decisiones else 0.0
            return metricas


def obtener_factura_cargada(factura_id_interno: int) -> dict[str, object] | None:
    """Obtiene todos los campos de una factura importada para su revisión."""
    with conectar() as conexion:
        with conexion.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT f.*, c.nombre_archivo, c.creada_en, c.usuario_id,
                       u.nombre_completo AS cargado_por
                FROM facturas_cargadas f
                JOIN cargas_archivo c ON c.id = f.carga_id
                LEFT JOIN usuarios u ON u.id = c.usuario_id
                WHERE f.id = %s
                """,
                (factura_id_interno,),
            )
            return cursor.fetchone()


def obtener_factura_sintetica(numero_factura: str) -> dict[str, object] | None:
    """Obtiene una factura del último experimento para mostrarla como simulación."""
    with conectar() as conexion:
        with conexion.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT f.*, a.motivo AS motivo_alerta, a.estado_revision, e.fecha_ejecucion
                FROM facturas f
                JOIN experimentos e ON e.id = f.experimento_id
                LEFT JOIN alertas a ON a.experimento_id = f.experimento_id AND a.factura_id = f.factura_id
                WHERE f.factura_id = %s
                ORDER BY e.fecha_ejecucion DESC, f.id DESC
                LIMIT 1
                """,
                (numero_factura,),
            )
            return cursor.fetchone()


def obtener_factura_sintetica_por_alerta(alerta_id: int) -> dict[str, object] | None:
    """Obtiene la versión exacta de la factura asociada a una alerta.

    Los identificadores de prueba se reutilizan entre experimentos; por eso la
    vista posterior a un ajuste debe consultar la alerta y no solo el número.
    """
    with conectar() as conexion:
        with conexion.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT f.*, a.motivo AS motivo_alerta, a.estado_revision, e.fecha_ejecucion
                FROM alertas a
                JOIN experimentos e ON e.id = a.experimento_id
                JOIN LATERAL (
                    SELECT f2.* FROM facturas f2
                    WHERE f2.experimento_id = a.experimento_id
                      AND f2.factura_id = a.factura_id
                    ORDER BY f2.es_anomalia DESC, f2.id DESC
                    LIMIT 1
                ) f ON TRUE
                WHERE a.id = %s
                """,
                (alerta_id,),
            )
            return cursor.fetchone()


def actualizar_estado_factura_cargada(factura_id_interno: int, estado: str) -> None:
    """Registra la decisión humana sin modificar el resultado original de la IA."""
    if estado not in {"pendiente", "revisada", "descartada"}:
        raise ValueError("Estado de revisión no válido.")
    with conectar() as conexion:
        conexion.execute(
            """
            UPDATE facturas_cargadas
            SET estado_revision = %s, revisado_en = CASE WHEN %s = 'pendiente' THEN NULL ELSE CURRENT_TIMESTAMP END
            WHERE id = %s
            """,
            (estado, estado, factura_id_interno),
        )


def obtener_alertas(limite: int = 100) -> list[dict[str, object]]:
    """Consulta alertas recientes para una futura vista histórica del dashboard."""
    with conectar() as conexion:
        with conexion.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT a.id, a.factura_id, a.tipo_anomalia, a.origen, a.puntaje_ia,
                       a.motivo, a.estado_revision, a.creada_en, f.fecha, f.hora
                FROM alertas a
                JOIN LATERAL (
                    SELECT f2.fecha, f2.hora
                    FROM facturas f2
                    WHERE f2.experimento_id = a.experimento_id
                      AND f2.factura_id = a.factura_id
                    ORDER BY f2.es_anomalia DESC, f2.id DESC
                    LIMIT 1
                ) f ON TRUE
                ORDER BY f.fecha DESC, f.hora DESC, a.creada_en DESC
                LIMIT %s
                """,
                (limite,),
            )
            return list(cursor.fetchall())


def obtener_ultimo_experimento() -> dict[str, object] | None:
    """Devuelve las métricas de la última ejecución para el dashboard web."""
    with conectar() as conexion:
        with conexion.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT * FROM experimentos ORDER BY fecha_ejecucion DESC LIMIT 1")
            return cursor.fetchone()


def crear_usuario(nombre_usuario: str, nombre_completo: str, contrasena: str,
                  rol: str = "administrador") -> None:
    """Registra un usuario y almacena únicamente sal + hash de su contraseña."""
    usuario = nombre_usuario.strip().lower()
    if len(usuario) < 3 or not usuario.replace("_", "").isalnum():
        raise ValueError("El usuario debe tener mínimo 3 caracteres y usar letras, números o guion bajo.")
    if not nombre_completo.strip():
        raise ValueError("Escribe el nombre completo del usuario.")
    sal, hash_contrasena = crear_hash_contrasena(contrasena)
    try:
        with conectar() as conexion:
            conexion.execute(
                """
                INSERT INTO usuarios (nombre_usuario, nombre_completo, password_hash, password_salt, rol)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (usuario, nombre_completo.strip(), hash_contrasena, sal, rol),
            )
    except psycopg.errors.UniqueViolation as error:
        raise ValueError("Ese nombre de usuario ya existe.") from error


def autenticar_usuario(nombre_usuario: str, contrasena: str) -> dict[str, object] | None:
    """Comprueba credenciales y devuelve datos públicos del usuario autenticado."""
    with conectar() as conexion:
        with conexion.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT id, nombre_usuario, nombre_completo, password_hash, password_salt, rol, activo
                FROM usuarios WHERE nombre_usuario = %s
                """,
                (nombre_usuario.strip().lower(),),
            )
            usuario = cursor.fetchone()
    if not usuario or not usuario["activo"]:
        return None
    if not verificar_contrasena(contrasena, usuario["password_salt"], usuario["password_hash"]):
        return None
    # Se retiran hash y sal antes de enviar datos a la interfaz.
    usuario.pop("password_hash")
    usuario.pop("password_salt")
    return usuario
