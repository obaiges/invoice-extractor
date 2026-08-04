"""Interfaz de proveedor de extracción.

Aisla la fuente de extracción (Gemini, otro LLM, OCR local, ...) del resto de la
aplicación. El pipeline solo conoce esta interfaz: para sustituir el proveedor
basta con implementar `extract()` y devolver un texto que represente la factura
en JSON (los campos exactos los normaliza `app.extraction.parser`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ExtractionProvider(ABC):
    @abstractmethod
    def extract(self, images: list[bytes], mime_type: str) -> str:
        """Extrae la información de la factura a partir de las imágenes del documento.

        Args:
            images: páginas/imágenes del documento codificadas en el formato
                indicado por `mime_type`.
            mime_type: tipo MIME de los bytes (p. ej. "image/png").

        Returns:
            Texto del modelo representando la factura como JSON.

        Raises:
            ExtractionError: si el proveedor no puede producir un resultado.
        """
