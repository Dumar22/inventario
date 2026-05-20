#!/usr/bin/env python3
"""
Script para cargar datos directamente a Neon BD.
Uso: python3 load_to_neon.py "postgresql://user:pass@host/db"

Lee TODOS los campos del Excel (Anexo A. ACTIVOS 2026.xls):
- Datos básicos: código, nombre, tipo, proveedor
- Contabilidad: costo histórico, vida útil, fechas, valor salvamento
- NIIF: costo NIIF, valoración ESFA, vida útil NIIF
- Cuentas contables: cuenta activo, partida local, contra partida, etc.
- Otros: modelo, ubicación

Si un activo ya existe (por código), se ACTUALIZA con los datos del Excel.
"""

import asyncio
import sys
import os
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, text
from sqlalchemy.orm import DeclarativeBase
import xlrd

# Importar modelos
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.models import Activo, GrupoHomogeneo, Dependencia, HistorialCambioGrupo

# Mapeo de hojas a grupos homogéneos
SHEET_GRUPO_MAP = {
    "SOFTWARE": {"codigo": "POL-SW-LIC", "nombre": "Software"},
    "LICENCIAS": {"codigo": "POL-SW-LIC", "nombre": "Licencias"},
    "MUEBLES Y ENSERES": {"codigo": "MUE.ENSERES", "nombre": "Muebles y Enseres"},
    "EQUIPO Y MÁQUINA DE OFICINA": {"codigo": "EQ.OFICINA", "nombre": "Equipo y Máquina de Oficina"},
    "otros muebles y enseres ": {"codigo": "MUE.ENSERES", "nombre": "Otros Muebles y Enseres"},
    "EQUIPO DE COMUNICACIÓN": {"codigo": "EQ.COMUNICACIÓN", "nombre": "Equipo de Comunicación"},
    "EQUIPO DE COMPUTACIÓN": {"codigo": "EQ.COMPUTACIÓN", "nombre": "Equipo de Computación"},
    "EQUIPO DE RESTAURANTE": {"codigo": "EQ.RESTAURANTE", "nombre": "Equipo de Restaurante"},
    "SEGUROS": {"codigo": "POL-SW-LIC", "nombre": "Seguros/Pólizas"},
    "muebles y enseres y eq, de ofi": {"codigo": "MUE.ENSERES", "nombre": "Muebles, Enseres y Eq. Oficina"},
    "NSNR": {"codigo": "NSNR", "nombre": "No Clasificado"},
}

SHEETS_TO_PROCESS = [
    "SOFTWARE", "LICENCIAS", "MUEBLES Y ENSERES",
    "EQUIPO Y MÁQUINA DE OFICINA", "otros muebles y enseres ",
    "EQUIPO DE COMUNICACIÓN", "EQUIPO DE COMPUTACIÓN",
    "EQUIPO DE RESTAURANTE", "SEGUROS",
    "muebles y enseres y eq, de ofi", "NSNR",
]

# Mapeo de headers del Excel → nombres normalizados para col_map
HEADER_ALIASES = {
    "CODIGO": "codigo",
    "CÓDIGO": "codigo",
    "CODIGO ALTERNO": "codigo_alterno",
    "CÓDIGO ALTERNO": "codigo_alterno",
    "NOMBRE DEL ACTIVO": "nombre",
    "TIPO": "tipo",
    "ESTADO DEL ACTIVO": "estado_activo",
    "CLASE DE ACTIVO": "clase_activo",
    "CLASIFICACION FISCAL": "clasificacion_fiscal",
    "CENTRO DE COSTOS": "centro_costos",
    "PROVEEDOR": "proveedor",
    "METODO": "metodo_depreciacion",
    "COSTO HISTORICO": "costo_historico",
    "FECHA INICIO LOCAL": "fecha_inicio",
    "FECHA FIN LOCAL": "fecha_fin",
    "VIDA UTIL LOCAL": "vida_util_meses",
    "VALOR SALVAMENTO": "valor_salvamento",
    "COSTO HISTORICO NIIF": "costo_historico_niif",
    "VALORACION ESFA": "valoracion_esfa",
    "FECHA INICIO NIIF": "fecha_inicio_niif",
    "FECHA FIN NIIF": "fecha_fin_niif",
    "VIDA UTIL NIIF": "vida_util_niif",
    "VALOR SALVAMENTO NIIF": "valor_salvamento_niif",
    "CTA ACTIVO": "cuenta_activo",
    "PARTIDA LOCAL": "partida_local",
    "CONTRA PARTIDA LOCAL": "contra_partida_local",
    "RESULTADO": "resultado",
    "PARTIDA NIIF": "partida_niif",
    "CONTRA PARTIDA NIIF": "contra_partida_niif",
    "MODELO": "modelo",
    "UBICACION": "ubicacion",
}


def sanitize_db_url(url: str) -> str:
    """Convierte postgresql:// a postgresql+asyncpg:// y limpia parámetros."""
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    if "?" in url:
        base, query = url.split("?", 1)
        params = query.split("&")
        libpq_only_params = {
            "sslmode", "channel_binding", "statement_cache_size", 
            "application_name", "keepalives", "keepalives_idle",
            "options", "replication", "fallback_application_name"
        }
        clean_params = [
            p for p in params 
            if not any(p.startswith(f"{param}=") for param in libpq_only_params)
        ]
        url = f"{base}?{'&'.join(clean_params)}" if clean_params else base
    
    return url


def excel_date_to_datetime(excel_date, datemode=0):
    """Convierte fecha serial de Excel a datetime."""
    if not excel_date or excel_date == "":
        return None
    try:
        if isinstance(excel_date, (int, float)) and excel_date > 0:
            return datetime(*xlrd.xldate_as_tuple(excel_date, datemode))
    except Exception:
        pass
    return None


def safe_float(val):
    """Convierte valor a float de forma segura."""
    if val is None or val == "" or val == "NA":
        return None
    try:
        f = float(val)
        return f if f != 0 else None  # 0 en contabilidad usualmente es "sin dato"
    except (ValueError, TypeError):
        return None


def safe_float_include_zero(val):
    """Convierte valor a float incluyendo 0."""
    if val is None or val == "" or val == "NA":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def safe_int(val):
    """Convierte valor a int de forma segura."""
    if val is None or val == "" or val == "NA":
        return None
    try:
        i = int(float(val))
        return i if i > 0 else None
    except (ValueError, TypeError):
        return None


def safe_str(val):
    """Convierte valor a string de forma segura."""
    if val is None or val == "":
        return None
    s = str(val).strip()
    if s in ("NA", "N/A", "nan", "None", "0", "0.0"):
        return None
    return s if s else None


def safe_str_keep_zero(val):
    """Convierte valor a string de forma segura, manteniendo '0' como dato válido."""
    if val is None or val == "":
        return None
    s = str(val).strip()
    if s in ("NA", "N/A", "nan", "None"):
        return None
    return s if s else None


def safe_cuenta(val):
    """Convierte una cuenta contable a string limpio (sin decimales)."""
    if val is None or val == "":
        return None
    try:
        # Las cuentas vienen como float (16700201.0) → queremos "16700201"
        return str(int(float(val)))
    except (ValueError, TypeError):
        s = str(val).strip()
        return s if s and s not in ("NA", "nan", "None") else None


def build_col_map(ws):
    """Construye un mapeo dinámico de nombre normalizado → índice de columna."""
    headers = [str(ws.cell_value(0, c)).strip().upper() for c in range(ws.ncols)]
    col_map = {}
    for i, h in enumerate(headers):
        if h in HEADER_ALIASES:
            col_map[HEADER_ALIASES[h]] = i
    return col_map


def extract_activo_data(ws, row_idx, col_map, datemode=0):
    """Extrae TODOS los campos de una fila del Excel y retorna un dict."""

    def cell(field):
        idx = col_map.get(field)
        if idx is None:
            return None
        return ws.cell_value(row_idx, idx)

    data = {
        "codigo": safe_str(cell("codigo")),
        "codigo_alterno": safe_str(cell("codigo_alterno")),
        "nombre": safe_str_keep_zero(cell("nombre")),
        "tipo": safe_str(cell("tipo")),
        "estado_activo": safe_str(cell("estado_activo")) or "ACTIVO",
        "clase_activo": safe_str(cell("clase_activo")),
        "clasificacion_fiscal": safe_str(cell("clasificacion_fiscal")),
        "centro_costos": safe_str(cell("centro_costos")),
        "proveedor": safe_str(cell("proveedor")),
        "metodo_depreciacion": safe_str(cell("metodo_depreciacion")),
        "costo_historico": safe_float_include_zero(cell("costo_historico")),
        "fecha_inicio": excel_date_to_datetime(cell("fecha_inicio"), datemode),
        "fecha_fin": excel_date_to_datetime(cell("fecha_fin"), datemode),
        "vida_util_meses": safe_int(cell("vida_util_meses")),
        "valor_salvamento": safe_float_include_zero(cell("valor_salvamento")),
        "costo_historico_niif": safe_float_include_zero(cell("costo_historico_niif")),
        "valoracion_esfa": safe_float_include_zero(cell("valoracion_esfa")),
        "fecha_inicio_niif": excel_date_to_datetime(cell("fecha_inicio_niif"), datemode),
        "fecha_fin_niif": excel_date_to_datetime(cell("fecha_fin_niif"), datemode),
        "vida_util_niif": safe_int(cell("vida_util_niif")),
        "valor_salvamento_niif": safe_float_include_zero(cell("valor_salvamento_niif")),
        "cuenta_activo": safe_cuenta(cell("cuenta_activo")),
        "partida_local": safe_cuenta(cell("partida_local")),
        "contra_partida_local": safe_cuenta(cell("contra_partida_local")),
        "resultado": safe_cuenta(cell("resultado")),
        "partida_niif": safe_cuenta(cell("partida_niif")),
        "contra_partida_niif": safe_cuenta(cell("contra_partida_niif")),
        "modelo": safe_str(cell("modelo")),
        "ubicacion": safe_str(cell("ubicacion")),
    }
    return data


async def crear_grupos(db_session):
    """Crea los grupos homogeneos base."""
    grupos_unicos = {}
    for info in SHEET_GRUPO_MAP.values():
        if info["codigo"] not in grupos_unicos:
            grupos_unicos[info["codigo"]] = info["nombre"]

    for codigo, nombre in grupos_unicos.items():
        existing = await db_session.execute(
            select(GrupoHomogeneo).where(GrupoHomogeneo.codigo == codigo)
        )
        if not existing.scalar_one_or_none():
            db_session.add(GrupoHomogeneo(codigo=codigo, nombre=nombre))
    
    await db_session.commit()
    print(f"  ✅ {len(grupos_unicos)} grupos homogéneos creados/verificados")


async def crear_dependencias(db_session):
    """Crea dependencias base."""
    deps = [
        "Secretaría General", "Presidencia", "Mesa Directiva", "Oficina Jurídica",
        "Control Interno", "Oficina Financiera", "Contabilidad", "Bienes/Almacén",
        "Sistemas", "Archivo", "Cafetería", "Plenaria", "Comisiones", "Sin asignar",
    ]
    for nombre in deps:
        existing = await db_session.execute(
            select(Dependencia).where(Dependencia.nombre == nombre)
        )
        if not existing.scalar_one_or_none():
            db_session.add(Dependencia(nombre=nombre))
    
    await db_session.commit()
    print(f"  ✅ {len(deps)} dependencias creadas/verificadas")


async def cargar_activos_desde_excel(db_session, filepath: str):
    """Carga activos desde el Excel usando TODAS las hojas por grupo."""
    wb = xlrd.open_workbook(filepath)
    datemode = wb.datemode
    total_insertados = 0
    total_actualizados = 0
    codigos_vistos = set()

    # Cargar mapa de grupos
    grupos_result = await db_session.execute(select(GrupoHomogeneo))
    grupos_map = {g.codigo: g.id for g in grupos_result.scalars().all()}

    for sheet_name in SHEETS_TO_PROCESS:
        if sheet_name not in wb.sheet_names():
            print(f"  [SKIP] Hoja '{sheet_name}' no encontrada")
            continue

        ws = wb.sheet_by_name(sheet_name)
        grupo_info = SHEET_GRUPO_MAP.get(sheet_name)
        grupo_id = grupos_map.get(grupo_info["codigo"]) if grupo_info else None

        if ws.nrows < 2:
            continue

        col_map = build_col_map(ws)
        
        if "nombre" not in col_map:
            print(f"  [SKIP] Hoja '{sheet_name}' — no se encontró columna NOMBRE DEL ACTIVO")
            continue

        insertados_hoja = 0
        actualizados_hoja = 0
        
        for row_idx in range(1, ws.nrows):
            data = extract_activo_data(ws, row_idx, col_map, datemode)
            
            if not data["codigo"] or not data["nombre"]:
                continue

            if data["codigo"] in codigos_vistos:
                continue
            codigos_vistos.add(data["codigo"])

            # Buscar si ya existe
            existing_result = await db_session.execute(
                select(Activo).where(Activo.codigo == data["codigo"])
            )
            existing = existing_result.scalar_one_or_none()

            if existing:
                # UPDATE: actualizar campos que estén vacíos o todos los campos contables
                existing.codigo_alterno = data["codigo_alterno"] or existing.codigo_alterno
                existing.nombre = data["nombre"] or existing.nombre
                existing.tipo = data["tipo"] or existing.tipo
                existing.estado_activo = data["estado_activo"] or existing.estado_activo
                existing.clase_activo = data["clase_activo"] or existing.clase_activo
                existing.clasificacion_fiscal = data["clasificacion_fiscal"] or existing.clasificacion_fiscal
                existing.centro_costos = data["centro_costos"] or existing.centro_costos
                existing.proveedor = data["proveedor"] or existing.proveedor
                existing.metodo_depreciacion = data["metodo_depreciacion"] or existing.metodo_depreciacion
                existing.costo_historico = data["costo_historico"] if data["costo_historico"] is not None else existing.costo_historico
                existing.fecha_inicio = data["fecha_inicio"] or existing.fecha_inicio
                existing.fecha_fin = data["fecha_fin"] or existing.fecha_fin
                existing.vida_util_meses = data["vida_util_meses"] if data["vida_util_meses"] is not None else existing.vida_util_meses
                existing.valor_salvamento = data["valor_salvamento"] if data["valor_salvamento"] is not None else existing.valor_salvamento
                existing.costo_historico_niif = data["costo_historico_niif"] if data["costo_historico_niif"] is not None else existing.costo_historico_niif
                existing.valoracion_esfa = data["valoracion_esfa"] if data["valoracion_esfa"] is not None else existing.valoracion_esfa
                existing.fecha_inicio_niif = data["fecha_inicio_niif"] or existing.fecha_inicio_niif
                existing.fecha_fin_niif = data["fecha_fin_niif"] or existing.fecha_fin_niif
                existing.vida_util_niif = data["vida_util_niif"] if data["vida_util_niif"] is not None else existing.vida_util_niif
                existing.valor_salvamento_niif = data["valor_salvamento_niif"] if data["valor_salvamento_niif"] is not None else existing.valor_salvamento_niif
                existing.cuenta_activo = data["cuenta_activo"] or existing.cuenta_activo
                existing.partida_local = data["partida_local"] or existing.partida_local
                existing.contra_partida_local = data["contra_partida_local"] or existing.contra_partida_local
                existing.resultado = data["resultado"] or existing.resultado
                existing.partida_niif = data["partida_niif"] or existing.partida_niif
                existing.contra_partida_niif = data["contra_partida_niif"] or existing.contra_partida_niif
                existing.modelo = data["modelo"] or existing.modelo
                existing.ubicacion = data["ubicacion"] or existing.ubicacion
                # No sobreescribir grupo si ya tiene uno asignado
                if not existing.grupo_homogeneo_id and grupo_id:
                    existing.grupo_homogeneo_id = grupo_id
                actualizados_hoja += 1
            else:
                # INSERT: crear nuevo activo con todos los campos
                activo = Activo(
                    codigo=data["codigo"],
                    codigo_alterno=data["codigo_alterno"],
                    nombre=data["nombre"],
                    tipo=data["tipo"],
                    estado_activo=data["estado_activo"],
                    clase_activo=data["clase_activo"],
                    clasificacion_fiscal=data["clasificacion_fiscal"],
                    centro_costos=data["centro_costos"],
                    proveedor=data["proveedor"],
                    metodo_depreciacion=data["metodo_depreciacion"],
                    costo_historico=data["costo_historico"],
                    fecha_inicio=data["fecha_inicio"],
                    fecha_fin=data["fecha_fin"],
                    vida_util_meses=data["vida_util_meses"],
                    valor_salvamento=data["valor_salvamento"],
                    costo_historico_niif=data["costo_historico_niif"],
                    valoracion_esfa=data["valoracion_esfa"],
                    fecha_inicio_niif=data["fecha_inicio_niif"],
                    fecha_fin_niif=data["fecha_fin_niif"],
                    vida_util_niif=data["vida_util_niif"],
                    valor_salvamento_niif=data["valor_salvamento_niif"],
                    cuenta_activo=data["cuenta_activo"],
                    partida_local=data["partida_local"],
                    contra_partida_local=data["contra_partida_local"],
                    resultado=data["resultado"],
                    partida_niif=data["partida_niif"],
                    contra_partida_niif=data["contra_partida_niif"],
                    modelo=data["modelo"],
                    ubicacion=data["ubicacion"],
                    grupo_homogeneo_id=grupo_id,
                )
                db_session.add(activo)
                insertados_hoja += 1

        await db_session.commit()
        total_insertados += insertados_hoja
        total_actualizados += actualizados_hoja
        print(f"  [{sheet_name}] ✅ {insertados_hoja} nuevos, 🔄 {actualizados_hoja} actualizados")

    return total_insertados, total_actualizados


async def main():
    # Intentar obtener URL de env var (para Render) o de argumentos (para uso local)
    neon_url = os.getenv("DATABASE_URL_PROD") or (sys.argv[1] if len(sys.argv) > 1 else None)
    
    if not neon_url:
        print("❌ Error: Proporciona URL o define DATABASE_URL_PROD")
        print("   Uso: python3 load_to_neon.py 'postgresql://user:pass@host/db'")
        print("   O: export DATABASE_URL_PROD='...' && python3 load_to_neon.py")
        sys.exit(1)
    
    clean_url = sanitize_db_url(neon_url)
    
    print("=" * 70)
    print("CARGA DE DATOS A NEON BD")
    print("=" * 70)
    print(f"\n🔗 Conectando a Neon...")
    
    engine = create_async_engine(clean_url, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    try:
        async with async_session() as db:
            print("\n1️⃣  Creando grupos homogéneos...")
            await crear_grupos(db)
            
            print("\n2️⃣  Creando dependencias...")
            await crear_dependencias(db)
            
            print("\n3️⃣  Cargando/actualizando activos desde Excel...")
            filepath = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "Anexo A. ACTIVOS 2026.xls"
            )
            
            if not os.path.exists(filepath):
                print(f"❌ Archivo no encontrado: {filepath}")
                return
            
            insertados, actualizados = await cargar_activos_desde_excel(db, filepath)
            
            print(f"\n{'=' * 70}")
            print(f"✅ NUEVOS INSERTADOS: {insertados}")
            print(f"🔄 EXISTENTES ACTUALIZADOS: {actualizados}")
            print(f"{'=' * 70}\n")
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
