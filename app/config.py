from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # En producción (Render): usa DATABASE_URL_PROD
    # En desarrollo: usa DATABASE_URL
    database_url: str = "postgresql+asyncpg://inventario:inventario_2026@localhost:5432/inventario_asamblea"
    database_url_prod: str = ""

    # Cloudinary
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""

    @property
    def database_url_async(self) -> str:
        """Convierte postgresql:// en postgresql+asyncpg:// y limpia parámetros incompatibles con asyncpg."""
        url = self.database_url_prod or self.database_url
        if not url:
            return ""
            
        # 1. Asegurar prefijo asyncpg
        if url.startswith("postgresql://") and "+asyncpg" not in url:
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        
        # 2. Eliminar parámetros de libpq que asyncpg no entiende
        # asyncpg entiende: timeout, ssl, server_settings
        # Render agrega: sslmode, channel_binding, statement_cache_size, application_name, etc.
        if "?" in url:
            base, query = url.split("?", 1)
            params = query.split("&")
            # Lista de parámetros de libpq que NO son compatibles con asyncpg
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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
