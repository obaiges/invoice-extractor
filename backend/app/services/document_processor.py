"""Procesador de documentos: orquesta la cadena completa.

flujo:
1. validar extensión, tamaño y contenido,
2. convertir el documento a imágenes (PDF → PNG, o normalizar imagen),
3. pedir la extracción al proveedor,
4. normalizar la respuesta y construir el `ExtractionResult`.

El procesador no conoce los detalles de la API de Gemini: depende solo de la
interfaz `ExtractionProvider`, así que la lógica de extracción es sustituible
sin tocar el resto de la aplicación.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.errors import (
    DocumentReadError,
    ExtractionError,
    FileTooLargeError,
    UnsupportedFileError,
)
from app.extraction import parser
from app.extraction.base import ExtractionProvider
from app.models.schemas import ExtractionResult, Invoice
from app.services.pdf_converter import image_to_png, pdf_to_images

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS: dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}

# Si la primera extracción deja sin detectar más de la mitad de los campos
# esperados (de los 14 posibles), se reintenta una vez: el modelo devuelve a
# veces respuestas casi vacías y un segundo intento suele recuperarlas.
CRITICAL_MISSING_THRESHOLD = 8


class DocumentProcessor:
    def __init__(
        self,
        provider: ExtractionProvider,
        max_file_size_bytes: int,
        max_image_bytes: int,
    ) -> None:
        self._provider = provider
        self._max_file_size_bytes = max_file_size_bytes
        self._max_image_bytes = max_image_bytes

    def process(self, filename: str, content: bytes) -> ExtractionResult:
        extension = Path(filename).suffix.lower()
        self._validate_file(extension, content)

        try:
            if extension == ".pdf":
                images = pdf_to_images(content, self._max_image_bytes)
            else:
                images = [image_to_png(content)]
        except (DocumentReadError, UnsupportedFileError):
            raise

        if not images:
            raise DocumentReadError(
                "No se pudo extraer ninguna página del documento. Asegúrate de que no está vacío."
            )

        invoice, missing_fields, warnings = self._extract(images)

        if len(missing_fields) >= CRITICAL_MISSING_THRESHOLD:
            logger.warning(
                "Extracción con %d campos faltantes (%d de umbral crítico); reintentando.",
                len(missing_fields), CRITICAL_MISSING_THRESHOLD,
            )
            retry_invoice, retry_missing, retry_warnings = self._extract(images)
            if len(retry_missing) < len(missing_fields):
                invoice, missing_fields, warnings = (
                    retry_invoice, retry_missing, retry_warnings,
                )

        status = "success" if not missing_fields else "partial"

        return ExtractionResult(
            status=status,
            invoice=invoice,
            missing_fields=missing_fields,
            warnings=warnings,
            model_used=getattr(self._provider, "last_model_used", None),
        )

    def _extract(self, images: list[bytes]) -> tuple[Invoice, list[str], list[str]]:
        """Pide la extracción al proveedor y normaliza la respuesta."""
        raw_response = self._provider.extract(images, "image/png")

        payload = parser.extract_json_payload(raw_response)
        if payload is None:
            raise ExtractionError(
                "El modelo devolvió una respuesta que no se pudo interpretar como datos estructurados. "
                "Revisa la calidad del documento e inténtalo de nuevo."
            )

        return parser.build_invoice(payload)

    def _validate_file(self, extension: str, content: bytes) -> None:
        if extension not in ALLOWED_EXTENSIONS:
            raise UnsupportedFileError(
                f"Formato no soportado: '{extension or 'desconocido'}'. "
                "Formatos admitidos: PDF, PNG, JPG, WEBP."
            )
        if len(content) == 0:
            raise DocumentReadError("El archivo está vacío.")
        if len(content) > self._max_file_size_bytes:
            raise FileTooLargeError(
                f"El archivo supera el tamaño máximo permitido "
                f"({self._max_file_size_bytes // (1024 * 1024)} MB)."
            )
