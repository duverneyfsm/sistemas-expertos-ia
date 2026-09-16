-- Esquema local para conservar trazabilidad de los experimentos.
-- Buena practica: cada tabla tiene una PRIMARY KEY que identifica una fila
-- de forma unica. Las FOREIGN KEY conectan las tablas y evitan registros
-- huerfanos. Las restricciones CHECK validan datos basicos sin impedir que
-- FactuGuard guarde una factura anomala para analizarla.

CREATE TABLE IF NOT EXISTS experimentos (
    id BIGSERIAL PRIMARY KEY,
    fecha_ejecucion TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    modelo VARCHAR(80) NOT NULL,
    semilla INTEGER NOT NULL,
    registros_evaluados INTEGER NOT NULL,
    alertas_hibridas INTEGER NOT NULL,
    precision NUMERIC(8, 4) NOT NULL,
    exhaustividad NUMERIC(8, 4) NOT NULL,
    f1 NUMERIC(8, 4) NOT NULL,
    especificidad NUMERIC(8, 4) NOT NULL,
    milisegundos_por_registro NUMERIC(12, 4) NOT NULL,
    CONSTRAINT ck_experimentos_registros CHECK (registros_evaluados >= 0),
    CONSTRAINT ck_experimentos_alertas CHECK (alertas_hibridas BETWEEN 0 AND registros_evaluados),
    CONSTRAINT ck_experimentos_metricas CHECK (
        precision BETWEEN 0 AND 1 AND exhaustividad BETWEEN 0 AND 1
        AND f1 BETWEEN 0 AND 1 AND especificidad BETWEEN 0 AND 1
    ),
    CONSTRAINT ck_experimentos_tiempo CHECK (milisegundos_por_registro >= 0)
);

-- Usuarios de la aplicación. No se guarda ninguna contraseña en texto plano.
CREATE TABLE IF NOT EXISTS usuarios (
    id BIGSERIAL PRIMARY KEY,
    nombre_usuario VARCHAR(50) NOT NULL UNIQUE,
    nombre_completo VARCHAR(120) NOT NULL,
    password_hash VARCHAR(128) NOT NULL,
    password_salt VARCHAR(64) NOT NULL,
    rol VARCHAR(20) NOT NULL DEFAULT 'analista'
        CHECK (rol IN ('administrador', 'analista', 'revisor')),
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS facturas (
    id BIGSERIAL PRIMARY KEY,
    experimento_id BIGINT NOT NULL REFERENCES experimentos(id) ON DELETE CASCADE,
    conjunto VARCHAR(15) NOT NULL CHECK (conjunto IN ('calibracion', 'prueba')),
    indice_origen INTEGER NOT NULL,
    factura_id VARCHAR(40) NOT NULL,
    cliente_sintetico VARCHAR(40) NOT NULL,
    categoria VARCHAR(60) NOT NULL,
    fecha DATE NOT NULL,
    hora SMALLINT NOT NULL CHECK (hora BETWEEN 0 AND 23),
    cantidad INTEGER NOT NULL,
    precio_unitario NUMERIC(14, 2) NOT NULL,
    descuento_pct NUMERIC(6, 4) NOT NULL,
    tasa_iva NUMERIC(6, 4) NOT NULL,
    subtotal NUMERIC(14, 2) NOT NULL,
    impuesto_valor NUMERIC(14, 2) NOT NULL,
    total NUMERIC(14, 2) NOT NULL,
    es_anomalia BOOLEAN NOT NULL DEFAULT FALSE,
    tipo_anomalia VARCHAR(60) NOT NULL,
    alerta_reglas BOOLEAN NOT NULL DEFAULT FALSE,
    alerta_ia BOOLEAN NOT NULL DEFAULT FALSE,
    alerta_hibrida BOOLEAN NOT NULL DEFAULT FALSE,
    puntaje_ia NUMERIC(12, 6),
    -- Evita repetir la misma fila de origen dentro de un experimento.
    CONSTRAINT uq_facturas_origen UNIQUE (experimento_id, conjunto, indice_origen),
    CONSTRAINT ck_facturas_indice CHECK (indice_origen >= 0),
    CONSTRAINT ck_facturas_cantidad CHECK (cantidad > 0),
    CONSTRAINT ck_facturas_valores CHECK (
        precio_unitario >= 0 AND subtotal >= 0 AND impuesto_valor >= 0 AND total >= 0
    ),
    CONSTRAINT ck_facturas_porcentajes CHECK (descuento_pct BETWEEN 0 AND 1 AND tasa_iva BETWEEN 0 AND 1),
    CONSTRAINT ck_facturas_puntaje CHECK (puntaje_ia IS NULL OR puntaje_ia >= 0)
);

CREATE INDEX IF NOT EXISTS idx_facturas_experimento ON facturas(experimento_id);
CREATE INDEX IF NOT EXISTS idx_facturas_alerta ON facturas(experimento_id, alerta_hibrida);

CREATE TABLE IF NOT EXISTS alertas (
    id BIGSERIAL PRIMARY KEY,
    experimento_id BIGINT NOT NULL REFERENCES experimentos(id) ON DELETE CASCADE,
    factura_id VARCHAR(40) NOT NULL,
    tipo_anomalia VARCHAR(60) NOT NULL,
    origen VARCHAR(20) NOT NULL,
    puntaje_ia NUMERIC(12, 6),
    motivo TEXT NOT NULL,
    estado_revision VARCHAR(20) NOT NULL DEFAULT 'pendiente'
        CHECK (estado_revision IN ('pendiente', 'revisada', 'descartada')),
    creada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- Una factura de un experimento produce una sola alerta consolidada.
    CONSTRAINT uq_alertas_factura_experimento UNIQUE (experimento_id, factura_id),
    CONSTRAINT ck_alertas_puntaje CHECK (puntaje_ia IS NULL OR puntaje_ia >= 0)
);

CREATE INDEX IF NOT EXISTS idx_alertas_experimento ON alertas(experimento_id);

-- Propuestas explicables y decisiones humanas. La factura original no se modifica:
-- se conserva la propuesta, la decisión y la corrección final para auditoría.
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
);

-- Cargas reales anonimizadas: se conserva la información tabular necesaria
-- para que una persona pueda revisar una alerta, no el archivo original.
CREATE TABLE IF NOT EXISTS cargas_archivo (
    id BIGSERIAL PRIMARY KEY,
    nombre_archivo VARCHAR(255) NOT NULL,
    usuario_id BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,
    total_facturas INTEGER NOT NULL,
    total_alertas INTEGER NOT NULL,
    creada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_cargas_totales CHECK (total_facturas >= 0 AND total_alertas BETWEEN 0 AND total_facturas)
);

CREATE TABLE IF NOT EXISTS facturas_cargadas (
    id BIGSERIAL PRIMARY KEY,
    carga_id BIGINT NOT NULL REFERENCES cargas_archivo(id) ON DELETE CASCADE,
    indice_origen INTEGER NOT NULL,
    factura_id VARCHAR(80) NOT NULL,
    cliente_sintetico VARCHAR(80) NOT NULL,
    categoria VARCHAR(80) NOT NULL,
    fecha DATE NOT NULL,
    hora SMALLINT NOT NULL CHECK (hora BETWEEN 0 AND 23),
    cantidad NUMERIC(14, 2) NOT NULL,
    precio_unitario NUMERIC(14, 2) NOT NULL,
    descuento_pct NUMERIC(6, 4) NOT NULL,
    tasa_iva NUMERIC(6, 4) NOT NULL,
    subtotal NUMERIC(14, 2) NOT NULL,
    impuesto_valor NUMERIC(14, 2) NOT NULL,
    total NUMERIC(14, 2) NOT NULL,
    -- Estos campos sirven para identificar el documento sin participar en la IA.
    nit_emisor VARCHAR(30) NOT NULL DEFAULT 'NO-REPORTADO',
    cufe VARCHAR(150) NOT NULL DEFAULT '',
    tipo_documento VARCHAR(60) NOT NULL DEFAULT 'Factura electronica',
    validacion_dian VARCHAR(100) NOT NULL DEFAULT 'No verificada por FactuGuard',
    alerta_reglas BOOLEAN NOT NULL DEFAULT FALSE,
    alerta_ia BOOLEAN NOT NULL DEFAULT FALSE,
    alerta_hibrida BOOLEAN NOT NULL DEFAULT FALSE,
    puntaje_ia NUMERIC(12, 6),
    motivo_alerta TEXT NOT NULL,
    prioridad_alerta VARCHAR(10) NOT NULL DEFAULT 'baja'
        CONSTRAINT ck_facturas_cargadas_prioridad CHECK (prioridad_alerta IN ('alta', 'media', 'baja')),
    version_modelo VARCHAR(80) NOT NULL DEFAULT 'FactuGuard IA 1.0',
    estado_revision VARCHAR(20) NOT NULL DEFAULT 'pendiente'
        CHECK (estado_revision IN ('pendiente', 'revisada', 'descartada')),
    revisado_en TIMESTAMPTZ,
    -- Solo se valida el rango; no se obliga subtotal + IVA = total porque
    -- una diferencia aritmetica es precisamente una alerta que se debe guardar.
    CONSTRAINT uq_facturas_cargadas_origen UNIQUE (carga_id, indice_origen),
    CONSTRAINT ck_facturas_cargadas_indice CHECK (indice_origen >= 0),
    CONSTRAINT ck_facturas_cargadas_cantidad CHECK (cantidad > 0),
    CONSTRAINT ck_facturas_cargadas_valores CHECK (
        precio_unitario >= 0 AND subtotal >= 0 AND impuesto_valor >= 0 AND total >= 0
    ),
    CONSTRAINT ck_facturas_cargadas_porcentajes CHECK (
        descuento_pct BETWEEN 0 AND 1 AND tasa_iva BETWEEN 0 AND 1
    ),
    CONSTRAINT ck_facturas_cargadas_puntaje CHECK (puntaje_ia IS NULL OR puntaje_ia >= 0)
);

CREATE INDEX IF NOT EXISTS idx_facturas_cargadas_alerta
    ON facturas_cargadas(carga_id, alerta_hibrida);
-- Indices para las consultas mas comunes de la bandeja de revision.
CREATE INDEX IF NOT EXISTS idx_facturas_cargadas_revision
    ON facturas_cargadas(alerta_hibrida, prioridad_alerta, fecha DESC, hora DESC);
CREATE INDEX IF NOT EXISTS idx_cargas_usuario_fecha
    ON cargas_archivo(usuario_id, creada_en DESC);
-- El CUFE identifica una factura electronica. Si no existe, se usa NIT,
-- numero y fecha; para datos de demostracion se usa cliente, numero y fecha.
CREATE UNIQUE INDEX IF NOT EXISTS uq_facturas_cargadas_cufe
    ON facturas_cargadas(cufe) WHERE cufe <> '';
CREATE UNIQUE INDEX IF NOT EXISTS uq_facturas_cargadas_nit_numero_fecha
    ON facturas_cargadas(nit_emisor, factura_id, fecha)
    WHERE nit_emisor <> 'NO-REPORTADO';
CREATE UNIQUE INDEX IF NOT EXISTS uq_facturas_cargadas_demo_identidad
    ON facturas_cargadas(cliente_sintetico, factura_id, fecha)
    WHERE nit_emisor = 'NO-REPORTADO' AND cufe = '';

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
);
