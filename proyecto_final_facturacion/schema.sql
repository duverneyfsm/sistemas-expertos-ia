-- Esquema local para conservar trazabilidad de los experimentos.

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
    milisegundos_por_registro NUMERIC(12, 4) NOT NULL
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
    puntaje_ia NUMERIC(12, 6)
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
    creada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    creada_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    alerta_reglas BOOLEAN NOT NULL DEFAULT FALSE,
    alerta_ia BOOLEAN NOT NULL DEFAULT FALSE,
    alerta_hibrida BOOLEAN NOT NULL DEFAULT FALSE,
    puntaje_ia NUMERIC(12, 6),
    motivo_alerta TEXT NOT NULL,
    estado_revision VARCHAR(20) NOT NULL DEFAULT 'pendiente'
        CHECK (estado_revision IN ('pendiente', 'revisada', 'descartada')),
    revisado_en TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_facturas_cargadas_alerta
    ON facturas_cargadas(carga_id, alerta_hibrida);

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
