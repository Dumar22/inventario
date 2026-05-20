from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, case
from sqlalchemy.orm import joinedload
from typing import Optional
from datetime import datetime, timezone
import json
import logging

from app.database import get_db, init_db
from app.config import get_settings
from app.models import Activo, RegistroInventario, GrupoHomogeneo, Dependencia, HistorialCambioGrupo
from app.schemas import (
    ActivoSearch, RegistroInventarioCreate, RegistroInventarioResponse,
    RegistroCompleto, CatalogosResponse, DashboardStats, HistorialCambioGrupoResponse,
)
from app.cloudinary_service import upload_image, delete_image

logger = logging.getLogger(__name__)
app = FastAPI(title="Inventario Asamblea de Caldas", version="1.0.0")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ----- Catalogos estáticos -----
ESTADOS_FISICOS = [
    "En uso", "En bodega", "Deteriorado", "Obsoleto", "No localizado",
    "Perdido/Hurtado", "En mantenimiento", "Dado de baja", "Sin soporte", "No aplica",
]
ESTADOS_AVANCE = [
    "Verificado", "No verificado", "Pendiente soporte",
]
ACCIONES = [
    "No ajustar", "Incorporar a Contabilidad", "Registrar en Bienes",
    "Reclasificar", "Corregir costo", "Corregir vida útil", "Iniciar baja",
]


def _calcular_accion_requerida(activo: Activo, registro: RegistroInventario) -> tuple[Optional[str], Optional[str]]:
    """Calcula automáticamente la acción requerida basada en cambios detectados.
    Retorna (accion, motivo)."""
    acciones = []
    motivos = []

    # Comparar vida útil
    if registro.vida_util_verificada and activo.vida_util_meses:
        if registro.vida_util_verificada != activo.vida_util_meses:
            acciones.append("No ajustar")
            motivos.append(f"Vida útil verificada ({registro.vida_util_verificada} meses) difiere de la registrada ({activo.vida_util_meses} meses)")

    # Comparar costo
    if registro.costo_verificado and activo.costo_historico:
        if abs(registro.costo_verificado - activo.costo_historico) > 0.01:
            acciones.append("Corregir costo")
            motivos.append(f"Costo verificado (${registro.costo_verificado}) difiere del registrado (${activo.costo_historico})")

    # Si no existe físicamente
    if registro.existe_fisicamente is False:
        acciones.append("Iniciar baja")
        motivos.append("El bien no existe físicamente")

    # Si cambió de cuenta
    if registro.ubicacion_verificada and activo.ubicacion:
        if registro.ubicacion_verificada != activo.ubicacion:
            acciones.append("Reclasificar")
            motivos.append(f"Ubicación verificada ({registro.ubicacion_verificada}) difiere de la registrada ({activo.ubicacion})")

    if acciones:
        return acciones[0], " | ".join(motivos)
    return None, None


@app.on_event("startup")
async def startup():
    settings = get_settings()
    db_url = settings.database_url_async
    # Ocultar credenciales en logs
    masked_url = db_url.split("@")[1] if "@" in db_url else "N/A"
    logger.info(f"🚀 App starting with DB: postgresql+asyncpg://...@{masked_url}")
    await init_db()


# Debug endpoint - solo para verificar la conexión
@app.get("/api/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(select(func.now()))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "database": "disconnected", "error": str(e)}
        )


# ===== PAGINAS HTML =====

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


# ===== API ENDPOINTS =====

# --- Catalogos ---
@app.get("/api/catalogos", response_model=CatalogosResponse)
async def get_catalogos(db: AsyncSession = Depends(get_db)):
    try:
        grupos = await db.execute(select(GrupoHomogeneo).order_by(GrupoHomogeneo.nombre))
        dependencias = await db.execute(select(Dependencia).order_by(Dependencia.nombre))
        return CatalogosResponse(
            estados_fisicos=ESTADOS_FISICOS,
            estados_avance=ESTADOS_AVANCE,
            acciones=ACCIONES,
            grupos_homogeneos=[
                {"id": g.id, "codigo": g.codigo, "nombre": g.nombre}
                for g in grupos.scalars().all()
            ],
            dependencias=[
                {"id": d.id, "nombre": d.nombre, "responsable": d.responsable}
                for d in dependencias.scalars().all()
            ],
        )
    except Exception as e:
        logger.error(f"Error en /api/catalogos: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


# --- Busqueda / Autocompletado ---
@app.get("/api/activos/buscar", response_model=list[ActivoSearch])
async def buscar_activos(
    q: str = Query(..., min_length=1, description="Codigo o nombre del activo"),
    limit: int = Query(15, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Busca activos por codigo, codigo_alterno, nombre o placa_serial.
    Usado para el autocompletado al digitar el codigo."""
    term = f"%{q}%"
    stmt = (
        select(Activo)
        .outerjoin(GrupoHomogeneo)
        .where(
            or_(
                Activo.codigo.ilike(term),
                Activo.codigo_alterno.ilike(term),
                Activo.nombre.ilike(term),
                Activo.placa_serial.ilike(term),
            )
        )
        .order_by(
            # Priorizar coincidencia exacta en codigo
            case(
                (Activo.codigo == q, 0),
                (Activo.codigo.ilike(f"{q}%"), 1),
                else_=2,
            ),
            Activo.codigo,
        )
        .limit(limit)
    )
    result = await db.execute(stmt)
    activos = result.scalars().all()

    # Cargar grupo para cada activo
    response = []
    for a in activos:
        grupo_nombre = None
        if a.grupo_homogeneo_id:
            grupo = await db.get(GrupoHomogeneo, a.grupo_homogeneo_id)
            grupo_nombre = grupo.nombre if grupo else None
        response.append(
            ActivoSearch(
                id=a.id,
                codigo=a.codigo,
                codigo_alterno=a.codigo_alterno,
                nombre=a.nombre,
                placa_serial=a.placa_serial,
                grupo_nombre=grupo_nombre,
                ubicacion=a.ubicacion,
                costo_historico=a.costo_historico,
            )
        )
    return response


# --- Detalle completo de un activo + registro ---
@app.get("/api/activos/{activo_id}", response_model=RegistroCompleto)
async def get_activo_completo(activo_id: int, db: AsyncSession = Depends(get_db)):
    activo = await db.get(Activo, activo_id)
    if not activo:
        raise HTTPException(status_code=404, detail="Activo no encontrado")

    grupo_nombre = None
    if activo.grupo_homogeneo_id:
        grupo = await db.get(GrupoHomogeneo, activo.grupo_homogeneo_id)
        grupo_nombre = grupo.nombre if grupo else None

    # Buscar registro inventario
    stmt = select(RegistroInventario).where(RegistroInventario.activo_id == activo_id)
    result = await db.execute(stmt)
    registro = result.scalar_one_or_none()

    # Historial de cambios de grupo
    hist_stmt = select(HistorialCambioGrupo).where(
        HistorialCambioGrupo.activo_id == activo_id
    ).order_by(HistorialCambioGrupo.fecha_cambio.desc())
    hist_result = await db.execute(hist_stmt)
    historial_raw = hist_result.scalars().all()

    historial_grupos = []
    for h in historial_raw:
        grupo_anterior_nombre = None
        if h.grupo_anterior_id:
            g_ant = await db.get(GrupoHomogeneo, h.grupo_anterior_id)
            grupo_anterior_nombre = g_ant.nombre if g_ant else None
        
        g_nuevo = await db.get(GrupoHomogeneo, h.grupo_nuevo_id)
        grupo_nuevo_nombre = g_nuevo.nombre if g_nuevo else None

        historial_grupos.append(HistorialCambioGrupoResponse(
            id=h.id,
            activo_id=h.activo_id,
            grupo_anterior_id=h.grupo_anterior_id,
            grupo_anterior_nombre=grupo_anterior_nombre,
            grupo_nuevo_id=h.grupo_nuevo_id,
            grupo_nuevo_nombre=grupo_nuevo_nombre,
            razon_cambio=h.razon_cambio,
            modificado_por=h.modificado_por,
            fecha_cambio=h.fecha_cambio,
        ))

    from app.schemas import ActivoResponse
    activo_resp = ActivoResponse(
        id=activo.id,
        codigo=activo.codigo,
        codigo_alterno=activo.codigo_alterno,
        placa_serial=activo.placa_serial,
        nombre=activo.nombre,
        tipo=activo.tipo,
        estado_activo=activo.estado_activo,
        centro_costos=activo.centro_costos,
        proveedor=activo.proveedor,
        costo_historico=activo.costo_historico,
        vida_util_meses=activo.vida_util_meses,
        cuenta_activo=activo.cuenta_activo,
        modelo=activo.modelo,
        ubicacion=activo.ubicacion,
        grupo_homogeneo_id=activo.grupo_homogeneo_id,
        dependencia_id=activo.dependencia_id,
        grupo_nombre=grupo_nombre,
    )

    registro_resp = None
    if registro:
        registro_resp = RegistroInventarioResponse.model_validate(registro)

    return RegistroCompleto(activo=activo_resp, registro=registro_resp, historial_grupos=historial_grupos)


# --- Guardar/Actualizar registro de inventario ---
@app.post("/api/registros", response_model=RegistroInventarioResponse)
async def crear_o_actualizar_registro(
    activo_id: int = Form(...),
    estado_fisico: Optional[str] = Form(None),
    existe_fisicamente: Optional[str] = Form(None),
    costo_verificado: Optional[float] = Form(None),
    vida_util_verificada: Optional[int] = Form(None),
    custodio_responsable: Optional[str] = Form(None),
    ubicacion_verificada: Optional[str] = Form(None),
    soporte_documental: Optional[str] = Form(None),
    accion_requerida: Optional[str] = Form(None),
    estado_avance: Optional[str] = Form("No verificado"),
    observaciones: Optional[str] = Form(None),
    verificado_por: Optional[str] = Form(None),
    foto: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
):
    try:
        # Verificar que existe el activo
        activo = await db.get(Activo, activo_id)
        if not activo:
            raise HTTPException(status_code=404, detail="Activo no encontrado")

        # Buscar registro existente
        stmt = select(RegistroInventario).where(RegistroInventario.activo_id == activo_id)
        result = await db.execute(stmt)
        registro = result.scalar_one_or_none()

        # Convertir strings a bool
        def parse_bool(val):
            if val is None or val == "":
                return None
            return val.lower() in ("true", "1", "si", "sí", "yes")

        # Subir foto si viene
        foto_url = None
        foto_public_id = None
        if foto and foto.filename:
            img_result = await upload_image(foto, folder=f"inventario_asamblea/{activo.codigo}")
            foto_url = img_result["url"]
            foto_public_id = img_result["public_id"]

        existe_fisicamente_bool = parse_bool(existe_fisicamente)

        if registro:
            # Actualizar existente
            registro.estado_fisico = estado_fisico or registro.estado_fisico
            registro.existe_fisicamente = existe_fisicamente_bool if existe_fisicamente else registro.existe_fisicamente
            registro.costo_verificado = costo_verificado if costo_verificado is not None else registro.costo_verificado
            registro.vida_util_verificada = vida_util_verificada if vida_util_verificada is not None else registro.vida_util_verificada
            registro.custodio_responsable = custodio_responsable or registro.custodio_responsable
            registro.ubicacion_verificada = ubicacion_verificada or registro.ubicacion_verificada
            registro.soporte_documental = soporte_documental or registro.soporte_documental
            registro.observaciones = observaciones or registro.observaciones
            registro.verificado_por = verificado_por or registro.verificado_por
            registro.fecha_verificacion = datetime.now(timezone.utc).replace(tzinfo=None)
            registro.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

            if foto_url:
                # Borrar foto anterior si existia
                if registro.foto_public_id:
                    delete_image(registro.foto_public_id)
                registro.foto_url = foto_url
                registro.foto_public_id = foto_public_id

            # Calcular acción requerida automática
            accion_auto, motivo_auto = _calcular_accion_requerida(activo, registro)
            if accion_auto:
                registro.accion_requerida = accion_auto
                registro.motivo_accion = motivo_auto
            elif accion_requerida:
                registro.accion_requerida = accion_requerida

            registro.estado_avance = estado_avance or registro.estado_avance
        else:
            # Crear nuevo
            registro = RegistroInventario(
                activo_id=activo_id,
                estado_fisico=estado_fisico,
                existe_fisicamente=existe_fisicamente_bool,
                costo_verificado=costo_verificado,
                vida_util_verificada=vida_util_verificada,
                custodio_responsable=custodio_responsable,
                ubicacion_verificada=ubicacion_verificada,
                foto_url=foto_url,
                foto_public_id=foto_public_id,
                soporte_documental=soporte_documental,
                estado_avance=estado_avance or "No verificado",
                observaciones=observaciones,
                verificado_por=verificado_por,
                fecha_verificacion=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            # Calcular acción requerida automática para nuevo registro
            # NOTA: Los valores iniciales no existirán, así que no habrá diferencias aún
            db.add(registro)

        await db.commit()
        await db.refresh(registro)
        return RegistroInventarioResponse.model_validate(registro)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en /api/registros: {type(e).__name__}: {str(e)}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al guardar registro: {str(e)}")


# --- Dashboard / Estadisticas ---
@app.get("/api/dashboard", response_model=DashboardStats)
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    # Total activos
    total_result = await db.execute(select(func.count(Activo.id)))
    total = total_result.scalar() or 0

    # Inventariados
    inv_result = await db.execute(select(func.count(RegistroInventario.id)))
    inventariados = inv_result.scalar() or 0

    pendientes = total - inventariados
    porcentaje = (inventariados / total * 100) if total > 0 else 0

    # Por estado fisico
    estado_stmt = (
        select(RegistroInventario.estado_fisico, func.count(RegistroInventario.id))
        .where(RegistroInventario.estado_fisico.isnot(None))
        .group_by(RegistroInventario.estado_fisico)
    )
    estado_result = await db.execute(estado_stmt)
    por_estado = {row[0]: row[1] for row in estado_result.all()}

    # Por grupo homogeneo
    grupo_stmt = (
        select(GrupoHomogeneo.nombre, func.count(Activo.id))
        .join(Activo, Activo.grupo_homogeneo_id == GrupoHomogeneo.id)
        .group_by(GrupoHomogeneo.nombre)
    )
    grupo_result = await db.execute(grupo_stmt)
    por_grupo = {row[0]: row[1] for row in grupo_result.all()}

    # Por estado avance
    avance_stmt = (
        select(RegistroInventario.estado_avance, func.count(RegistroInventario.id))
        .where(RegistroInventario.estado_avance.isnot(None))
        .group_by(RegistroInventario.estado_avance)
    )
    avance_result = await db.execute(avance_stmt)
    por_avance = {row[0]: row[1] for row in avance_result.all()}

    return DashboardStats(
        total_activos=total,
        inventariados=inventariados,
        pendientes=pendientes,
        porcentaje_avance=round(porcentaje, 1),
        por_estado_fisico=por_estado,
        por_grupo=por_grupo,
        por_estado_avance=por_avance,
    )


# --- Estadísticas por usuario (verificador) ---
@app.get("/api/dashboard/por-usuario")
async def get_usuarios_estadisticas(db: AsyncSession = Depends(get_db)):
    """Retorna cantidad de registros completados por cada verificador."""
    stmt = (
        select(RegistroInventario.verificado_por, func.count(RegistroInventario.id))
        .where(RegistroInventario.verificado_por.isnot(None))
        .group_by(RegistroInventario.verificado_por)
        .order_by(func.count(RegistroInventario.id).desc())
    )
    result = await db.execute(stmt)
    usuarios = [
        {"verificado_por": row[0], "cantidad": row[1]}
        for row in result.all()
    ]
    return usuarios


# --- Listado paginado ---
@app.get("/api/activos")
async def listar_activos(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=5, le=200),
    grupo: Optional[str] = None,
    estado: Optional[str] = None,
    estado_avance: Optional[str] = None,
    solo_pendientes: bool = False,
    q: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Activo)
        .outerjoin(RegistroInventario)
        .outerjoin(GrupoHomogeneo)
    )

    if grupo:
        stmt = stmt.where(GrupoHomogeneo.codigo == grupo)
    if estado:
        stmt = stmt.where(RegistroInventario.estado_fisico == estado)
    if estado_avance:
        stmt = stmt.where(RegistroInventario.estado_avance == estado_avance)
    if solo_pendientes:
        stmt = stmt.where(RegistroInventario.id.is_(None))
    if q:
        term = f"%{q}%"
        stmt = stmt.where(
            or_(
                Activo.codigo.ilike(term),
                Activo.nombre.ilike(term),
                Activo.codigo_alterno.ilike(term),
            )
        )

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # Paginar
    stmt = stmt.order_by(Activo.codigo).offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    activos = result.scalars().all()

    items = []
    for a in activos:
        grupo_nombre = None
        if a.grupo_homogeneo_id:
            g = await db.get(GrupoHomogeneo, a.grupo_homogeneo_id)
            grupo_nombre = g.nombre if g else None

        # Verificar si tiene registro
        reg_stmt = select(RegistroInventario).where(RegistroInventario.activo_id == a.id)
        reg_result = await db.execute(reg_stmt)
        reg = reg_result.scalar_one_or_none()

        items.append({
            "id": a.id,
            "codigo": a.codigo,
            "codigo_alterno": a.codigo_alterno,
            "nombre": a.nombre,
            "grupo_nombre": grupo_nombre,
            "costo_historico": a.costo_historico,
            "vida_util_meses": a.vida_util_meses,
            "ubicacion": a.ubicacion,
            "inventariado": reg is not None,
            "estado_fisico": reg.estado_fisico if reg else None,
            "estado_avance": reg.estado_avance if reg else None,
            "custodio": reg.custodio_responsable if reg else None,
            "ubicacion_verificada": reg.ubicacion_verificada if reg else None,
            "foto_url": reg.foto_url if reg else None,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": (total + size - 1) // size,
    }


# --- Cambiar grupo (con trazabilidad) ---
@app.patch("/api/activos/{activo_id}/grupo")
async def cambiar_grupo(
    activo_id: int,
    grupo_homogeneo_id: int = Form(...),
    razon_cambio: Optional[str] = Form(None),
    modificado_por: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Cambia el grupo de un activo y registra el historial."""
    try:
        activo = await db.get(Activo, activo_id)
        if not activo:
            raise HTTPException(status_code=404, detail="Activo no encontrado")

        # Verificar que el nuevo grupo existe
        nuevo_grupo = await db.get(GrupoHomogeneo, grupo_homogeneo_id)
        if not nuevo_grupo:
            raise HTTPException(status_code=404, detail="Grupo no encontrado")

        grupo_anterior_id = activo.grupo_homogeneo_id

        # Si es el mismo grupo, retornar error
        if grupo_anterior_id == grupo_homogeneo_id:
            raise HTTPException(status_code=400, detail="El activo ya pertenece a este grupo")

        # Registrar en historial
        historial = HistorialCambioGrupo(
            activo_id=activo_id,
            grupo_anterior_id=grupo_anterior_id,
            grupo_nuevo_id=grupo_homogeneo_id,
            razon_cambio=razon_cambio,
            modificado_por=modificado_por,
            fecha_cambio=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.add(historial)

        # Cambiar el grupo del activo
        activo.grupo_homogeneo_id = grupo_homogeneo_id

        await db.commit()

        # Retornar el grupo anterior y nuevo
        grupo_anterior_nombre = None
        if grupo_anterior_id:
            g_ant = await db.get(GrupoHomogeneo, grupo_anterior_id)
            grupo_anterior_nombre = g_ant.nombre if g_ant else None

        return {
            "exito": True,
            "activo_id": activo_id,
            "grupo_anterior_id": grupo_anterior_id,
            "grupo_anterior_nombre": grupo_anterior_nombre,
            "grupo_nuevo_id": grupo_homogeneo_id,
            "grupo_nuevo_nombre": nuevo_grupo.nombre,
            "razon_cambio": razon_cambio,
            "fecha_cambio": datetime.now(timezone.utc).replace(tzinfo=None),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error en cambiar_grupo: {type(e).__name__}: {str(e)}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al cambiar grupo: {str(e)}")


# --- Obtener historial de cambios de grupo ---
@app.get("/api/activos/{activo_id}/historial-grupo", response_model=list[HistorialCambioGrupoResponse])
async def obtener_historial_grupo(activo_id: int, db: AsyncSession = Depends(get_db)):
    """Obtiene el historial de cambios de grupo para un activo."""
    activo = await db.get(Activo, activo_id)
    if not activo:
        raise HTTPException(status_code=404, detail="Activo no encontrado")

    stmt = select(HistorialCambioGrupo).where(
        HistorialCambioGrupo.activo_id == activo_id
    ).order_by(HistorialCambioGrupo.fecha_cambio.desc())
    result = await db.execute(stmt)
    historial = result.scalars().all()

    response = []
    for h in historial:
        grupo_anterior_nombre = None
        if h.grupo_anterior_id:
            g_ant = await db.get(GrupoHomogeneo, h.grupo_anterior_id)
            grupo_anterior_nombre = g_ant.nombre if g_ant else None

        g_nuevo = await db.get(GrupoHomogeneo, h.grupo_nuevo_id)
        grupo_nuevo_nombre = g_nuevo.nombre if g_nuevo else None

        response.append(HistorialCambioGrupoResponse(
            id=h.id,
            activo_id=h.activo_id,
            grupo_anterior_id=h.grupo_anterior_id,
            grupo_anterior_nombre=grupo_anterior_nombre,
            grupo_nuevo_id=h.grupo_nuevo_id,
            grupo_nuevo_nombre=grupo_nuevo_nombre,
            razon_cambio=h.razon_cambio,
            modificado_por=h.modificado_por,
            fecha_cambio=h.fecha_cambio,
        ))

    return response
