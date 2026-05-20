from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Text, DateTime, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class GrupoHomogeneo(Base):
    """Grupos: MUE.ENSERES, EQ.OFICINA, EQ.COMPUTACION, etc."""
    __tablename__ = "grupos_homogeneos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    codigo = Column(String(50), unique=True, nullable=False, index=True)
    nombre = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)

    activos = relationship("Activo", back_populates="grupo_homogeneo")
    historial_grupos = relationship("HistorialCambioGrupo", foreign_keys="HistorialCambioGrupo.grupo_anterior_id", back_populates="grupo_anterior")
    historial_grupos_nuevo = relationship("HistorialCambioGrupo", foreign_keys="HistorialCambioGrupo.grupo_nuevo_id", back_populates="grupo_nuevo")


class Dependencia(Base):
    """Ubicaciones/dependencias dentro de la Asamblea."""
    __tablename__ = "dependencias"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nombre = Column(String(200), nullable=False, unique=True)
    responsable = Column(String(200), nullable=True)
    piso = Column(String(50), nullable=True)

    activos = relationship("Activo", back_populates="dependencia")


class Activo(Base):
    """Tabla principal de activos - corresponde al Anexo A + Matriz Inventario."""
    __tablename__ = "activos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    codigo = Column(String(50), nullable=False, index=True)
    codigo_alterno = Column(String(50), nullable=True, index=True)
    placa_serial = Column(String(100), nullable=True, index=True)
    nombre = Column(String(500), nullable=False)
    tipo = Column(String(50), nullable=True)  # FIJO, DIFERIDO, NA
    estado_activo = Column(String(50), nullable=True)  # ACTIVO, INACTIVO
    clase_activo = Column(String(100), nullable=True)
    clasificacion_fiscal = Column(String(100), nullable=True)
    centro_costos = Column(String(50), nullable=True)
    proveedor = Column(String(200), nullable=True)

    # Contabilidad
    metodo_depreciacion = Column(String(50), nullable=True)
    costo_historico = Column(Float, nullable=True)
    fecha_inicio = Column(DateTime, nullable=True)
    fecha_fin = Column(DateTime, nullable=True)
    vida_util_meses = Column(Integer, nullable=True)
    valor_salvamento = Column(Float, nullable=True)

    # NIIF
    costo_historico_niif = Column(Float, nullable=True)
    valoracion_esfa = Column(Float, nullable=True)
    fecha_inicio_niif = Column(DateTime, nullable=True)
    fecha_fin_niif = Column(DateTime, nullable=True)
    vida_util_niif = Column(Integer, nullable=True)
    valor_salvamento_niif = Column(Float, nullable=True)

    # Cuentas contables
    cuenta_activo = Column(String(20), nullable=True)
    partida_local = Column(String(20), nullable=True)
    contra_partida_local = Column(String(20), nullable=True)
    resultado = Column(String(20), nullable=True)
    partida_niif = Column(String(20), nullable=True)
    contra_partida_niif = Column(String(20), nullable=True)

    # Otros
    modelo = Column(String(200), nullable=True)
    ubicacion = Column(String(200), nullable=True)

    # FK
    grupo_homogeneo_id = Column(Integer, ForeignKey("grupos_homogeneos.id"), nullable=True)
    dependencia_id = Column(Integer, ForeignKey("dependencias.id"), nullable=True)

    # Relaciones
    grupo_homogeneo = relationship("GrupoHomogeneo", back_populates="activos")
    dependencia = relationship("Dependencia", back_populates="activos")
    registro_inventario = relationship("RegistroInventario", back_populates="activo", uselist=False)
    historial_grupos = relationship("HistorialCambioGrupo", back_populates="activo")

    __table_args__ = (
        Index("ix_activos_codigo_nombre", "codigo", "nombre"),
    )


class RegistroInventario(Base):
    """Registro del inventario fisico - la 'ficha' que se llena al verificar un bien."""
    __tablename__ = "registros_inventario"

    id = Column(Integer, primary_key=True, autoincrement=True)
    activo_id = Column(Integer, ForeignKey("activos.id"), unique=True, nullable=False)

    # Verificacion fisica
    estado_fisico = Column(String(50), nullable=True)  # Catalogo: En uso, Deteriorado, etc.
    existe_fisicamente = Column(Boolean, nullable=True)

    # Costo y vida util verificados
    costo_verificado = Column(Float, nullable=True)
    vida_util_verificada = Column(Integer, nullable=True)

    # Custodio y ubicacion verificados
    custodio_responsable = Column(String(200), nullable=True)
    ubicacion_verificada = Column(String(200), nullable=True)

    # Soportes
    foto_url = Column(String(500), nullable=True)
    foto_public_id = Column(String(200), nullable=True)  # Cloudinary public_id
    soporte_documental = Column(Text, nullable=True)

    # Conciliacion y acciones automaticas
    accion_requerida = Column(String(100), nullable=True)  # Catalogo: No ajustar, Reclasificar, Incorporar, etc.
    motivo_accion = Column(String(200), nullable=True)  # Por que se generó la acción

    # Estado del registro
    estado_avance = Column(String(50), default="No verificado")  # Verificado, No verificado, Pendiente soporte
    observaciones = Column(Text, nullable=True)

    # Auditoria
    verificado_por = Column(String(200), nullable=True)
    fecha_verificacion = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relacion
    activo = relationship("Activo", back_populates="registro_inventario")


class HistorialCambioGrupo(Base):
    """Historial de cambios de grupo para trazabilidad."""
    __tablename__ = "historial_cambio_grupo"

    id = Column(Integer, primary_key=True, autoincrement=True)
    activo_id = Column(Integer, ForeignKey("activos.id"), nullable=False)
    grupo_anterior_id = Column(Integer, ForeignKey("grupos_homogeneos.id"), nullable=True)
    grupo_nuevo_id = Column(Integer, ForeignKey("grupos_homogeneos.id"), nullable=False)
    
    razon_cambio = Column(String(200), nullable=True)
    modificado_por = Column(String(200), nullable=True)
    fecha_cambio = Column(DateTime, default=_utcnow)

    # Relaciones
    activo = relationship("Activo", back_populates="historial_grupos")
    grupo_anterior = relationship("GrupoHomogeneo", foreign_keys=[grupo_anterior_id], back_populates="historial_grupos")
    grupo_nuevo = relationship("GrupoHomogeneo", foreign_keys=[grupo_nuevo_id], back_populates="historial_grupos_nuevo")
