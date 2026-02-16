-- ============================================================================
-- TABLA: telegram_users
-- Persistir usuarios de Telegram para broadcast confiable.
-- Redis sigue como caché rápida; esta tabla es la fuente de verdad.
-- ============================================================================

CREATE TABLE IF NOT EXISTS telegram_users (
    id              SERIAL PRIMARY KEY,
    chat_id         BIGINT UNIQUE NOT NULL,
    username        VARCHAR(128),
    nombre          VARCHAR(255),
    activo          BOOLEAN DEFAULT TRUE,
    creado_en       TIMESTAMP DEFAULT NOW(),
    ultima_interaccion TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tg_users_chat_id ON telegram_users(chat_id);
CREATE INDEX IF NOT EXISTS idx_tg_users_activo  ON telegram_users(activo);

-- ============================================================================
-- TABLA: alert_recipients
-- Lista unificada de destinatarios para alertas y reportes diarios.
-- ============================================================================

CREATE TABLE IF NOT EXISTS alert_recipients (
    id              SERIAL PRIMARY KEY,
    nombre          VARCHAR(255) NOT NULL,
    correo          VARCHAR(255) UNIQUE,
    rol             VARCHAR(128),
    canal_telegram  BOOLEAN DEFAULT FALSE,
    canal_email     BOOLEAN DEFAULT TRUE,
    recibir_alertas BOOLEAN DEFAULT TRUE,   -- alertas cada 30 min
    recibir_diario  BOOLEAN DEFAULT TRUE,   -- informe 7 AM
    activo          BOOLEAN DEFAULT TRUE,
    creado_en       TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recipients_activo ON alert_recipients(activo);

-- ============================================================================
-- Datos iniciales (Viceministro — placeholder, ajustar correo real)
-- ============================================================================

INSERT INTO alert_recipients (nombre, correo, rol, canal_telegram, canal_email,
                              recibir_alertas, recibir_diario, activo)
VALUES
    ('Viceministro de Energía', 'vjpaternina@minenergia.gov.co',
     'Viceministro', FALSE, TRUE, TRUE, TRUE, TRUE)
ON CONFLICT (correo) DO NOTHING;
