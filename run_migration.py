#!/usr/bin/env python3
"""
Script para ejecutar migraciones SQL en la base de datos.
Uso: python3 run_migration.py
"""

import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from app.config import get_settings
from app.database import init_db

async def run_migrations():
    """Ejecuta las migraciones SQL."""
    settings = get_settings()
    
    print("📦 Ejecutando migraciones...")
    print(f"Base de datos: {settings.database_url}")
    
    engine = create_async_engine(settings.database_url, echo=True)
    
    try:
        # Ejecutar migraciones
        async with engine.begin() as conn:
            # Leer y ejecutar el SQL
            with open("migrations/001_actualizar_inventario.sql", "r") as f:
                sql = f.read()
                # Dividir por ;; para múltiples comandos
                commands = [cmd.strip() for cmd in sql.split(";") if cmd.strip()]
                for cmd in commands:
                    print(f"\n▶️  Ejecutando: {cmd[:60]}...")
                    await conn.execute(cmd)
        
        print("\n✅ Migraciones ejecutadas exitosamente")
        
        # Inicializar DB
        await init_db()
        print("✅ Base de datos inicializada")
        
    except Exception as e:
        print(f"\n❌ Error durante migraciones: {e}")
        sys.exit(1)
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run_migrations())
