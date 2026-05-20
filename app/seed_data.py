"""
Script para cargar datos iniciales desde los archivos Excel al PostgreSQL.
Uso: python -m app.seed_data
"""
import asyncio
import sys
import os
from datetime import datetime, timezone

# Agregar el directorio raiz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import xlrd
from sqlalchemy import select
from app.database import engine, async_session, Base
from app.models import Activo, GrupoHomogeneo, Dependencia


# Mapeo de hojas del Excel a grupos homogeneos
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

# Hojas a procesar (excluir TOTALES y ACTIVOS COMPLETOS para evitar duplicados)
SHEETS_TO_PROCESS = [
    "SOFTWARE", "LICENCIAS", "MUEBLES Y ENSERES",
    "EQUIPO Y MÁQUINA DE OFICINA", "otros muebles y enseres ",
    "EQUIPO DE COMUNICACIÓN", "EQUIPO DE COMPUTACIÓN",
    "EQUIPO DE RESTAURANTE", "SEGUROS",
    "muebles y enseres y eq, de ofi", "NSNR",
]


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


async def crear_grupos():
    """Crea los grupos homogeneos base."""
    grupos_unicos = {}
    for info in SHEET_GRUPO_MAP.values():
        if info["codigo"] not in grupos_unicos:
            grupos_unicos[info["codigo"]] = info["nombre"]

    async with async_session() as db:
        for codigo, nombre in grupos_unicos.items():
            existing = await db.execute(
                select(GrupoHomogeneo).where(GrupoHomogeneo.codigo == codigo)
            )
            if not existing.scalar_one_or_none():
                db.add(GrupoHomogeneo(codigo=codigo, nombre=nombre))
        await db.commit()
    print(f"  -> {len(grupos_unicos)} grupos homogéneos creados")


async def crear_dependencias():
    """Crea dependencias base."""
    deps = [
        "Secretaría General",
        "Presidencia",
        "Mesa Directiva",
        "Oficina Jurídica",
        "Control Interno",
        "Oficina Financiera",
        "Contabilidad",
        "Bienes/Almacén",
        "Sistemas",
        "Archivo",
        "Cafetería",
        "Plenaria",
        "Comisiones",
        "Sin asignar",
    ]
    async with async_session() as db:
        for nombre in deps:
            existing = await db.execute(
                select(Dependencia).where(Dependencia.nombre == nombre)
            )
            if not existing.scalar_one_or_none():
                db.add(Dependencia(nombre=nombre))
        await db.commit()
    print(f"  -> {len(deps)} dependencias creadas")


async def cargar_activos_desde_excel(filepath: str):
    """Carga activos desde el archivo Anexo A."""
    wb = xlrd.open_workbook(filepath)
    total_cargados = 0
    codigos_vistos = set()

    async with async_session() as db:
        # Cargar mapa de grupos
        grupos_result = await db.execute(select(GrupoHomogeneo))
        grupos_map = {g.codigo: g.id for g in grupos_result.scalars().all()}

        for sheet_name in SHEETS_TO_PROCESS:
            if sheet_name not in wb.sheet_names():
                print(f"  [SKIP] Hoja '{sheet_name}' no encontrada")
                continue

            ws = wb.sheet_by_name(sheet_name)
            grupo_info = SHEET_GRUPO_MAP.get(sheet_name)
            grupo_id = grupos_map.get(grupo_info["codigo"]) if grupo_info else None

            # Determinar las columnas del header
            if ws.nrows < 2:
                continue

            headers = [str(ws.cell_value(0, c)).strip().upper() for c in range(ws.ncols)]

            # Mapeo de columnas (posicion en el header)
            col_map = {}
            for i, h in enumerate(headers):
                if "CODIGO" == h or h == "CÓDIGO":
                    col_map["codigo"] = i
                elif "ALTERNO" in h:
                    col_map["codigo_alterno"] = i
                elif "NOMBRE" in h or "ACTIVO" in h and "ESTADO" not in h and "CLASE" not in h and "CTA" not in h:
                    if "nombre" not in col_map:
                        col_map["nombre"] = i
                elif h == "TIPO":
                    col_map["tipo"] = i
                elif "ESTADO" in h and "ACTIVO" in h:
                    col_map["estado_activo"] = i
                elif "CENTRO" in h:
                    col_map["centro_costos"] = i
                elif "PROVEEDOR" in h:
                    col_map["proveedor"] = i
                elif h == "METODO" or h == "MÉTODO":
                    col_map["metodo"] = i
                elif h == "COSTO HISTORICO" or h == "COSTO HISTÓRICO":
                    col_map["costo_historico"] = i
                elif "FECHA INICIO LOCAL" in h or h == "FECHA INICIO LOCAL":
                    col_map["fecha_inicio"] = i
                elif "FECHA FIN LOCAL" in h or h == "FECHA FIN LOCAL":
                    col_map["fecha_fin"] = i
                elif h == "VIDA UTIL LOCAL" or h == "VIDA ÚTIL LOCAL":
                    col_map["vida_util"] = i
                elif h == "VALOR SALVAMENTO" and "NIIF" not in h:
                    col_map["valor_salvamento"] = i
                elif h == "COSTO HISTORICO NIIF" or h == "COSTO HISTÓRICO NIIF":
                    col_map["costo_niif"] = i
                elif "VALORACION" in h or "VALORACIÓN" in h:
                    col_map["valoracion_esfa"] = i
                elif h == "CTA ACTIVO":
                    col_map["cuenta_activo"] = i
                elif h == "PARTIDA LOCAL":
                    col_map["partida_local"] = i
                elif h == "CONTRA PARTIDA LOCAL":
                    col_map["contra_partida"] = i
                elif h == "MODELO":
                    col_map["modelo"] = i
                elif h == "UBICACION" or h == "UBICACIÓN":
                    col_map["ubicacion"] = i

            # Si nombre no se mapeo, usar columna 2 (NOMBRE DEL ACTIVO)
            if "nombre" not in col_map:
                for i, h in enumerate(headers):
                    if "NOMBRE DEL ACTIVO" in h:
                        col_map["nombre"] = i
                        break
                if "nombre" not in col_map and ws.ncols > 2:
                    col_map["nombre"] = 2

            cargados_hoja = 0
            for row_idx in range(1, ws.nrows):
                codigo_val = safe_str(ws.cell_value(row_idx, col_map.get("codigo", 0)))
                nombre_val = safe_str(ws.cell_value(row_idx, col_map.get("nombre", 2)))

                if not codigo_val or not nombre_val:
                    continue

                # Evitar duplicados
                clave = f"{codigo_val}"
                if clave in codigos_vistos:
                    continue
                codigos_vistos.add(clave)

                # Verificar que no exista en DB
                existing = await db.execute(
                    select(Activo).where(Activo.codigo == codigo_val)
                )
                if existing.scalar_one_or_none():
                    continue

                activo = Activo(
                    codigo=codigo_val,
                    codigo_alterno=safe_str(ws.cell_value(row_idx, col_map["codigo_alterno"])) if "codigo_alterno" in col_map else None,
                    nombre=nombre_val,
                    tipo=safe_str(ws.cell_value(row_idx, col_map["tipo"])) if "tipo" in col_map else None,
                    estado_activo=safe_str(ws.cell_value(row_idx, 0)) if sheet_name == "ACTIVOS COMPLETOS" else "ACTIVO",
                    centro_costos=safe_str(ws.cell_value(row_idx, col_map["centro_costos"])) if "centro_costos" in col_map else None,
                    proveedor=safe_str(ws.cell_value(row_idx, col_map["proveedor"])) if "proveedor" in col_map else None,
                    metodo_depreciacion=safe_str(ws.cell_value(row_idx, col_map["metodo"])) if "metodo" in col_map else None,
                    costo_historico=safe_float(ws.cell_value(row_idx, col_map["costo_historico"])) if "costo_historico" in col_map else None,
                    fecha_inicio=excel_date_to_datetime(ws.cell_value(row_idx, col_map["fecha_inicio"]), wb.datemode) if "fecha_inicio" in col_map else None,
                    fecha_fin=excel_date_to_datetime(ws.cell_value(row_idx, col_map["fecha_fin"]), wb.datemode) if "fecha_fin" in col_map else None,
                    vida_util_meses=safe_int(ws.cell_value(row_idx, col_map["vida_util"])) if "vida_util" in col_map else None,
                    valor_salvamento=safe_float(ws.cell_value(row_idx, col_map["valor_salvamento"])) if "valor_salvamento" in col_map else None,
                    costo_historico_niif=safe_float(ws.cell_value(row_idx, col_map["costo_niif"])) if "costo_niif" in col_map else None,
                    valoracion_esfa=safe_float(ws.cell_value(row_idx, col_map["valoracion_esfa"])) if "valoracion_esfa" in col_map else None,
                    cuenta_activo=safe_str(ws.cell_value(row_idx, col_map["cuenta_activo"])) if "cuenta_activo" in col_map else None,
                    partida_local=safe_str(ws.cell_value(row_idx, col_map["partida_local"])) if "partida_local" in col_map else None,
                    contra_partida_local=safe_str(ws.cell_value(row_idx, col_map["contra_partida"])) if "contra_partida" in col_map else None,
                    modelo=safe_str(ws.cell_value(row_idx, col_map["modelo"])) if "modelo" in col_map else None,
                    ubicacion=safe_str(ws.cell_value(row_idx, col_map["ubicacion"])) if "ubicacion" in col_map else None,
                    grupo_homogeneo_id=grupo_id,
                )
                db.add(activo)
                cargados_hoja += 1

            await db.commit()
            total_cargados += cargados_hoja
            print(f"  [{sheet_name}] -> {cargados_hoja} activos cargados")

    return total_cargados


async def main():
    print("=" * 60)
    print("CARGA INICIAL DE DATOS - INVENTARIO ASAMBLEA DE CALDAS")
    print("=" * 60)

    # Crear tablas
    print("\n1. Creando tablas...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("  -> Tablas creadas")

    # Crear grupos homogeneos
    print("\n2. Creando grupos homogéneos...")
    await crear_grupos()

    # Crear dependencias
    print("\n3. Creando dependencias...")
    await crear_dependencias()

    # Cargar activos
    print("\n4. Cargando activos desde Anexo A...")
    filepath = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "Anexo A. ACTIVOS 2026.xls"
    )

    if not os.path.exists(filepath):
        print(f"  ERROR: Archivo no encontrado: {filepath}")
        print("  Asegúrate de que el archivo 'Anexo A. ACTIVOS 2026.xls' esté en el directorio raíz del proyecto.")
        return

    total = await cargar_activos_desde_excel(filepath)

    print(f"\n{'=' * 60}")
    print(f"TOTAL DE ACTIVOS CARGADOS: {total}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
