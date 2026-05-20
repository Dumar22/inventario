import cloudinary
import cloudinary.uploader
from app.config import get_settings
from fastapi import UploadFile
import io

settings = get_settings()

# Configurar Cloudinary
cloudinary.config(
    cloud_name=settings.cloudinary_cloud_name,
    api_key=settings.cloudinary_api_key,
    api_secret=settings.cloudinary_api_secret,
    secure=True,
)


async def upload_image(file: UploadFile, folder: str = "inventario_asamblea") -> dict:
    """Sube una imagen a Cloudinary y retorna url + public_id."""
    contents = await file.read()
    result = cloudinary.uploader.upload(
        io.BytesIO(contents),
        folder=folder,
        resource_type="image",
        transformation=[
            {"width": 1200, "height": 1200, "crop": "limit"},
            {"quality": "auto:good"},
            {"fetch_format": "auto"},
        ],
    )
    return {
        "url": result["secure_url"],
        "public_id": result["public_id"],
    }


def delete_image(public_id: str) -> bool:
    """Elimina una imagen de Cloudinary."""
    try:
        result = cloudinary.uploader.destroy(public_id)
        return result.get("result") == "ok"
    except Exception:
        return False
