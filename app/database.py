from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings
import logging

logger = logging.getLogger(__name__)
settings = get_settings()

engine = create_async_engine(
    settings.database_url_async, 
    echo=False, 
    pool_size=10, 
    max_overflow=20
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Inicializa la BD: crea tablas desde modelos y ejecuta migraciones SQL."""
    try:
        # 1. Crear todas las tablas desde los modelos
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Tables created from models")
        
        # 2. Ejecutar migraciones SQL
        import os
        migrations_dir = os.path.join(os.path.dirname(__file__), "..", "migrations")
        migration_file = os.path.join(migrations_dir, "001_actualizar_inventario.sql")
        
        if os.path.exists(migration_file):
            logger.info(f"📋 Executing migration: {migration_file}")
            with open(migration_file, "r") as f:
                sql_content = f.read()
            
            async with engine.begin() as conn:
                # Dividir por ; para ejecutar cada comando
                commands = [cmd.strip() for cmd in sql_content.split(";") if cmd.strip() and not cmd.strip().startswith("--")]
                for cmd in commands:
                    try:
                        await conn.execute(cmd)
                        logger.debug(f"✓ {cmd[:60]}...")
                    except Exception as e:
                        # Si es "already exists", no es crítico
                        if "already exists" not in str(e).lower():
                            logger.warning(f"⚠️  {type(e).__name__}: {str(e)[:80]}")
            logger.info("✅ Migrations executed")
        else:
            logger.warning(f"⚠️  Migration file not found: {migration_file}")
            
    except Exception as e:
        logger.error(f"❌ Database initialization error: {type(e).__name__}: {str(e)}")
        raise
