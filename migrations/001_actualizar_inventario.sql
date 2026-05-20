-- ============================================================================
-- MIGRATION: Actualización de Inventario v2.0
-- Elimina campos innecesarios y agrega historial de cambios de grupo
-- ============================================================================

-- Tabla de Historial de Cambios de Grupo (nueva)
CREATE TABLE IF NOT EXISTS historial_cambio_grupo (
    id SERIAL PRIMARY KEY,
    activo_id INTEGER NOT NULL REFERENCES activos(id) ON DELETE CASCADE,
    grupo_anterior_id INTEGER REFERENCES grupos_homogeneos(id) ON DELETE SET NULL,
    grupo_nuevo_id INTEGER NOT NULL REFERENCES grupos_homogeneos(id) ON DELETE CASCADE,
    
    razon_cambio VARCHAR(200),
    modificado_por VARCHAR(200),
    fecha_cambio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_hist_activo FOREIGN KEY (activo_id) REFERENCES activos(id),
    CONSTRAINT fk_hist_grupo_anterior FOREIGN KEY (grupo_anterior_id) REFERENCES grupos_homogeneos(id),
    CONSTRAINT fk_hist_grupo_nuevo FOREIGN KEY (grupo_nuevo_id) REFERENCES grupos_homogeneos(id)
);

CREATE INDEX ix_historial_cambio_grupo_activo_id ON historial_cambio_grupo(activo_id);
CREATE INDEX ix_historial_cambio_grupo_fecha ON historial_cambio_grupo(fecha_cambio);

-- Actualizar tabla registros_inventario (eliminar campos innecesarios, agregar nuevos)
ALTER TABLE registros_inventario DROP COLUMN IF EXISTS registro_modulo_bienes;
ALTER TABLE registros_inventario DROP COLUMN IF EXISTS registro_contabilidad;
ALTER TABLE registros_inventario DROP COLUMN IF EXISTS clasificacion_diferencia;
ALTER TABLE registros_inventario DROP COLUMN IF EXISTS resultado_conciliacion;

-- Agregar columnas nuevas si no existen
ALTER TABLE registros_inventario ADD COLUMN IF NOT EXISTS motivo_accion VARCHAR(200);

-- Cambiar default de estado_avance
ALTER TABLE registros_inventario ALTER COLUMN estado_avance SET DEFAULT 'No verificado';

-- ============================================================================
-- FIN MIGRATION
-- ============================================================================
