#!/usr/bin/env python3
"""
Script para cargar datos iniciales desde el Excel al PostgreSQL.
Uso: python3 load_seed_data.py
"""

import asyncio
import sys
import os

# Agregar el directorio raiz al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.seed_data import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
        print("\n✅ Datos cargados exitosamente!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error al cargar datos: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
