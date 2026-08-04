"""Endpoints de la API.

Las rutas solo delegan: no contienen lógica de extracción. El procesador se
obtiene por inyección de dependencias, lo que permite sustituirlo en los tests.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile

from app.core.config import settings
from app.core.errors import MissingApiKeyError
from app.extraction.gemini_provider import GeminiProvider
from app.models.schemas import ExtractionResult
from app.services.document_processor import DocumentProcessor

router = APIRouter(prefix="/api/v1")


def get_processor() -> DocumentProcessor:
    """Fábrica del procesador. Sin clave configurada, devuelve un error claro."""
    if not settings.gemini_api_key:
        raise MissingApiKeyError(
            "La API de Gemini no está configurada. Crea un fichero `.env` en la raíz "
            "del proyecto con `GEMINI_API_KEY=...` (gratis en https://aistudio.google.com/apikey) "
            "y reinicia el backend."
        )

    provider = GeminiProvider(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        temperature=settings.temperature,
    )
    return DocumentProcessor(
        provider=provider,
        max_file_size_bytes=settings.max_file_size_bytes,
        max_image_bytes=settings.max_image_bytes,
    )


@router.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/documents/extract",
    response_model=ExtractionResult,
    tags=["documents"],
    summary="Extrae los campos de una factura a partir de un PDF o imagen",
)
async def extract_document(
    file: UploadFile = File(..., description="Documento a procesar (PDF, PNG, JPG, WEBP)"),
    processor: DocumentProcessor = Depends(get_processor),
) -> ExtractionResult:
    content = await file.read()
    return processor.process(filename=file.filename or "document", content=content)
