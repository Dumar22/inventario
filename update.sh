#!/bin/bash
# ============================================================================
# SCRIPT DE ACTUALIZACIÓN - Inventario v2.0
# Ejecuta las migraciones y reinicia la aplicación
# ============================================================================

set -e

echo "🔄 Actualización de Sistema de Inventario v2.0"
echo "================================================"
echo ""

# Activar entorno virtual
echo "1️⃣  Activando entorno virtual..."
source .venv/bin/activate || echo "⚠️  Entorno virtual no encontrado, continuando..."

# Ejecutar migraciones
echo ""
echo "2️⃣  Ejecutando migraciones de base de datos..."
python3 run_migration.py

# Reiniciar aplicación (si está usando systemd o similar)
echo ""
echo "3️⃣  Limpiando cache..."
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true

echo ""
echo "✅ Actualización completada exitosamente!"
echo ""
echo "📝 Próximos pasos:"
echo "   1. Revisar CAMBIOS_V2.md para ver lista completa de cambios"
echo "   2. Reiniciar la aplicación:"
echo "      python3 -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
echo "   3. Visitar http://localhost:8000 para verificar que todo funciona"
echo ""
echo "🧪 Testing recomendado:"
echo "   - Crear un nuevo registro de inventario"
echo "   - Cambiar el grupo de un activo"
echo "   - Consultar el historial de cambios"
echo ""
