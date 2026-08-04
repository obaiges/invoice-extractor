"""Proveedor de extracción basado en la API de Gemini (Google AI Studio).

Implementación de `ExtractionProvider` que envía las páginas del documento como
imágenes inline (base64) a un modelo multimodal junto con un prompt estructurado
y `response_schema` para obtener JSON controlado.

Todos los errores del SDK (red, cuota, bloqueo de contenido, ...) se envuelven
en `ExtractionError` con un mensaje accionable; nunca escapan crudos.
"""

from __future__ import annotations

import logging

from google import genai
from google.genai import types

from app.core.errors import ExtractionError
from app.extraction.base import ExtractionProvider
from app.extraction.prompt import EXTRACTION_PROMPT, INVOICE_SCHEMA

logger = logging.getLogger(__name__)


class GeminiProvider(ExtractionProvider):
    def __init__(self, api_key: str, model: str, temperature: float = 0.0) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._temperature = temperature

    def extract(self, images: list[bytes], mime_type: str) -> str:
        parts: list[types.Part] = [types.Part(text=EXTRACTION_PROMPT)]
        for image in images:
            parts.append(types.Part(inline_data=types.Blob(mime_type=mime_type, data=image)))

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=[types.Content(parts=parts)],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=INVOICE_SCHEMA,
                    temperature=self._temperature,
                ),
            )
        except Exception as exc:
            message = _friendly_api_error(exc)
            raise ExtractionError(f"Error al comunicarse con la API de Gemini: {message}") from exc

        if response.prompt_feedback and response.prompt_feedback.block_reason:
            raise ExtractionError(
                "La petición fue bloqueada por la API de Gemini "
                f"(razón: {response.prompt_feedback.block_reason.name})."
            )

        text = response.text
        if not text:
            raise ExtractionError("La API de Gemini no devolvió contenido para este documento.")

        return text


def _friendly_api_error(exc: Exception) -> str:
    """Convierte un error del SDK en un mensaje legible y accionable."""
    raw = str(exc)
    lowered = raw.lower()

    if "quota" in lowered or "429" in raw:
        return "se alcanzó la cuota gratuita de peticiones. Espera un momento y reintenta."
    if "permission" in lowered or "403" in raw or "api key not valid" in lowered or "invalid api key" in lowered:
        return "la clave de API no es válida o no tiene permisos para este modelo. Revísala en aistudio.google.com."
    if "model" in lowered and "not found" in lowered:
        return f"el modelo configurado no existe. Revisa la variable GEMINI_MODEL."
    if "timeout" in lowered or "timed out" in lowered:
        return "la petición superó el tiempo de espera. Reintenta o usa un documento más corto."
    if "400" in raw:
        return f"la petición fue rechazada por la API (400). Detalle: {raw[:300]}"
    return f"{raw[:400]}"
