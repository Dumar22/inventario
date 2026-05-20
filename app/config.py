from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    # En producción (Render): usa DATABASE_URL_PROD
    # En desarrollo: usa DATABASE_URL
    database_url: str = "postgresql+asyncpg://inventario:inventario_2026@localhost:5432/inventario_asamblea"

    # Cloudinary
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""

    @property
    def database_url_async(self) -> str:
        """Convierte postgresql:// en postgresql+asyncpg:// y limpia parámetros incompatibles."""
        url = os.getenv("DATABASE_URL_PROD") or os.getenv("DATABASE_URL") or self.database_url
        if not url:
            return ""
            
        # 1. Asegurar prefijo asyncpg
        if url.startswith("postgresql://") and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        
        # 2. Eliminar sslmode si existe (asyncpg no lo soporta como query param)
        if "?" in url:
            base, query = url.split("?", 1)
            params = query.split("&")
            clean_params = [p for p in params if not p.startswith("sslmode=")]
            url = f"{base}?{'&'.join(clean_params)}" if clean_params else base
            
        return url

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
