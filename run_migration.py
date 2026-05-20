#!/usr/bin/env python3
"""
Script para ejecutar migraciones SQL en la base de datos.
Uso: python3 run_migration.py
"""

import asyncio
import sys
import os
from sqlalchemy.ext.asyncio import create_async_engine
from app.config import get_settings
from app.database import Base

async def run_migrations():
    """Ejecuta las migraciones SQL."""
    settings = get_settings()
    
    print("📦 Ejecutando migraciones...")
    masked_url = settings.database_url_async.split("@")[1] if "@" in settings.database_url_async else "N/A"
    print(f"Base de datos: postgresql+asyncpg://...@{masked_url}")
    
    engine = create_async_engine(settings.database_url_async, echo=False)
    
    try:
        # 1. Crear todas las tablas desde los modelos
        print("\n1️⃣  Creando tablas desde modelos...")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("   ✅ Tablas creadas")
        
        # 2. Ejecutar migraciones SQL
        print("\n2️⃣  Ejecutando migraciones SQL...")
        migrations_dir = "migrations"
        migration_file = os.path.join(migrations_dir, "001_actualizar_inventario.sql")
        
        if os.path.exists(migration_file):
            with open(migration_file, "r") as f:
                sql_content = f.read()
            
            async with engine.begin() as conn:
                commands = [cmd.strip() for cmd in sql_content.split(";") if cmd.strip() and not cmd.strip().startswith("--")]
                for cmd in commands:
                    try:
                        await conn.execute(cmd)
                        print(f"   ✓ {cmd[:60]}...")
                    except Exception as e:
                        if "already exists" not in str(e).lower():
                            print(f"   ⚠️  {type(e).__name__}: {str(e)[:80]}")
        else:
            print(f"   ⚠️  Archivo de migración no encontrado: {migration_file}")
        
        print("\n✅ Migraciones completadas exitosamente")
        
    except Exception as e:
        print(f"\n❌ Error durante migraciones: {e}")
        sys.exit(1)
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run_migrations())
