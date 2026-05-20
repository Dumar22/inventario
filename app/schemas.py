from pydantic import BaseModel
from typing import Optional
from datetime import datetime


# --- Activo ---
class ActivoBase(BaseModel):
    codigo: str
    codigo_alterno: Optional[str] = None
    placa_serial: Optional[str] = None
    nombre: str
    tipo: Optional[str] = None
    estado_activo: Optional[str] = None
    centro_costos: Optional[str] = None
    proveedor: Optional[str] = None
    costo_historico: Optional[float] = None
    vida_util_meses: Optional[int] = None
    cuenta_activo: Optional[str] = None
    modelo: Optional[str] = None
    ubicacion: Optional[str] = None
    grupo_homogeneo_id: Optional[int] = None
    dependencia_id: Optional[int] = None


class ActivoResponse(ActivoBase):
    id: int
    grupo_nombre: Optional[str] = None

    class Config:
        from_attributes = True


class ActivoSearch(BaseModel):
    id: int
    codigo: str
    codigo_alterno: Optional[str] = None
    nombre: str
    placa_serial: Optional[str] = None
    grupo_nombre: Optional[str] = None
    ubicacion: Optional[str] = None
    costo_historico: Optional[float] = None


# --- Historial Cambio Grupo ---
class HistorialCambioGrupoResponse(BaseModel):
    id: int
    activo_id: int
    grupo_anterior_id: Optional[int]
    grupo_anterior_nombre: Optional[str]
    grupo_nuevo_id: int
    grupo_nuevo_nombre: str
    razon_cambio: Optional[str]
    modificado_por: Optional[str]
    fecha_cambio: datetime

    class Config:
        from_attributes = True


# --- Registro Inventario ---
class RegistroInventarioBase(BaseModel):
    estado_fisico: Optional[str] = None
    existe_fisicamente: Optional[bool] = None
    costo_verificado: Optional[float] = None
    vida_util_verificada: Optional[int] = None
    custodio_responsable: Optional[str] = None
    ubicacion_verificada: Optional[str] = None
    soporte_documental: Optional[str] = None
    accion_requerida: Optional[str] = None
    motivo_accion: Optional[str] = None
    estado_avance: Optional[str] = "No verificado"
    observaciones: Optional[str] = None
    verificado_por: Optional[str] = None


class RegistroInventarioCreate(RegistroInventarioBase):
    activo_id: int


class RegistroInventarioResponse(RegistroInventarioBase):
    id: int
    activo_id: int
    foto_url: Optional[str] = None
    fecha_verificacion: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class RegistroCompleto(BaseModel):
    """Activo + su registro de inventario combinados."""
    activo: ActivoResponse
    registro: Optional[RegistroInventarioResponse] = None
    historial_grupos: list[HistorialCambioGrupoResponse] = []


# --- Catalogos ---
class CatalogosResponse(BaseModel):
    estados_fisicos: list[str]
    estados_avance: list[str]
    acciones: list[str]
    grupos_homogeneos: list[dict]
    dependencias: list[dict]


# --- Dashboard ---
class DashboardStats(BaseModel):
    total_activos: int
    inventariados: int
    pendientes: int
    porcentaje_avance: float
    por_estado_fisico: dict
    por_grupo: dict
    por_estado_avance: dict
