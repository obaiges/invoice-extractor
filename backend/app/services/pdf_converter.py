"""Conversión de documentos (PDF/imagen) a imágenes que entienda el modelo.

Rendereiza cada página de un PDF a PNG con PyMuPDF. Esto permite procesar por
igual PDF con capa de texto y PDF escaneados, y evita depender de la Files API
de Gemini (los bytes se envían inline).
"""

from __future__ import annotations

import io

import pymupdf
from PIL import Image

from app.core.errors import DocumentReadError

PDF_RENDER_DPI = 150


def pdf_to_images(content: bytes, max_total_bytes: int) -> list[bytes]:
    """Convierte un PDF en una lista de PNG (uno por página)."""
    try:
        document = pymupdf.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise DocumentReadError(f"No se pudo abrir el PDF: {exc}") from exc

    try:
        if document.needs_pass:
            raise DocumentReadError(
                "El PDF está protegido por contraseña y no se puede leer. "
                "Quita la protección e inténtalo de nuevo."
            )

        images: list[bytes] = []
        total = 0
        for page in document:
            pixmap = page.get_pixmap(dpi=PDF_RENDER_DPI)
            image_bytes = pixmap.tobytes("png")
            images.append(image_bytes)
            total += len(image_bytes)
            if total > max_total_bytes:
                raise DocumentReadError(
                    "Las páginas renderizadas del PDF superan el tamaño máximo "
                    "aceptado por la API. Prueba con un documento con menos "
                    "páginas o de menor resolución."
                )
        return images
    finally:
        document.close()


def image_to_png(content: bytes) -> bytes:
    """Valida una imagen y la normaliza a PNG."""
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.load()
    except Exception as exc:
        raise DocumentReadError("El archivo de imagen no se pudo leer o está corrupto.") from exc

    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()
