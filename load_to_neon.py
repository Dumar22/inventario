#!/usr/bin/env python3
"""
Script para cargar datos directamente a Neon BD.
Uso: python3 load_to_neon.py "postgresql://user:pass@host/db"
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

# Mapeo de hojas
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
        if isinstance(excel_date, float) and excel_date > 0:
            return datetime(*xlrd.xldate_as_tuple(excel_date, datemode))
    except Exception:
        pass
    return None


def safe_float(val):
    """Convierte valor a float de forma segura."""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def safe_int(val):
    """Convierte valor a int de forma segura."""
    if val is None or val == "":
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def safe_str(val):
    """Convierte valor a string de forma segura."""
    if val is None or val == "":
        return None
    s = str(val).strip()
    return s if s else None


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
    """Carga activos desde el Excel."""
    wb = xlrd.open_workbook(filepath)
    total_cargados = 0
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

        headers = [str(ws.cell_value(0, c)).strip().upper() for c in range(ws.ncols)]
        col_map = {}
        
        for i, h in enumerate(headers):
            if "CODIGO" == h or h == "CÓDIGO":
                col_map["codigo"] = i
            elif "ALTERNO" in h:
                col_map["codigo_alterno"] = i
            elif "NOMBRE DEL ACTIVO" in h:
                col_map["nombre"] = i
        
        if "nombre" not in col_map and ws.ncols > 2:
            col_map["nombre"] = 2

        cargados_hoja = 0
        for row_idx in range(1, ws.nrows):
            codigo_val = safe_str(ws.cell_value(row_idx, col_map.get("codigo", 0)))
            nombre_val = safe_str(ws.cell_value(row_idx, col_map.get("nombre", 2)))

            if not codigo_val or not nombre_val:
                continue

            clave = f"{codigo_val}"
            if clave in codigos_vistos:
                continue
            codigos_vistos.add(clave)

            existing = await db_session.execute(
                select(Activo).where(Activo.codigo == codigo_val)
            )
            if existing.scalar_one_or_none():
                continue

            activo = Activo(
                codigo=codigo_val,
                codigo_alterno=safe_str(ws.cell_value(row_idx, col_map["codigo_alterno"])) if "codigo_alterno" in col_map else None,
                nombre=nombre_val,
                tipo=safe_str(ws.cell_value(row_idx, col_map.get("tipo", 3))) if ws.ncols > 3 else None,
                estado_activo="ACTIVO",
                grupo_homogeneo_id=grupo_id,
            )
            db_session.add(activo)
            cargados_hoja += 1

        await db_session.commit()
        total_cargados += cargados_hoja
        print(f"  [{sheet_name}] ✅ {cargados_hoja} activos")

    return total_cargados


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
            
            print("\n3️⃣  Cargando activos desde Excel...")
            filepath = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "Anexo A. ACTIVOS 2026.xls"
            )
            
            if not os.path.exists(filepath):
                print(f"❌ Archivo no encontrado: {filepath}")
                return
            
            total = await cargar_activos_desde_excel(db, filepath)
            
            print(f"\n{'=' * 70}")
            print(f"✅ TOTAL DE ACTIVOS CARGADOS: {total}")
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
