from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    # En producción (Render): usa DATABASE_URL_PROD
    # En desarrollo: usa DATABASE_URL
    @property
    def database_url_async(self) -> str:
        """Convierte postgresql:// en postgresql+asyncpg:// para SQLAlchemy asyncio."""
        url = self.database_url
        if url and url.startswith("postgresql://") and "+asyncpg" not in url:
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"
    
    def __init__(self, **data):
        super().__init__(**data)
        # Si DATABASE_URL_PROD está configurada (producción), úsala
        # Si no, usa DATABASE_URL (desarrollo)
        if os.getenv("DATABASE_URL_PROD"):
            self.database_url = os.getenv("DATABASE_URL_PROD")
        elif os.getenv("DATABASE_URL"):
            self.database_url = os.getenv("DATABASE_URL")
        else:
            self.database_url = "postgresql+asyncpg://inventario:inventario_2026@localhost:5432/inventario_asamblea"


@lru_cache
def get_settings() -> Settings:
    return Settings()
