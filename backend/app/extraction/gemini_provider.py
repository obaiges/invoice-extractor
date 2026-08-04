"""Proveedor de extracción basado en la API de Gemini (Google AI Studio).

Implementación de `ExtractionProvider` que envía las páginas del documento como
imágenes inline (base64) a un modelo multimodal junto con un prompt estructurado
y `response_schema` para obtener JSON controlado.

Incluye una cadena de modelos de reserva: si el modelo configurado deja de estar
disponible para la cuenta (p. ej. Google retira modelos antiguos para cuentas
nuevas con un 404), se reintenta automáticamente con modelos más recientes.

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

# Modelos de reserva, en orden de preferencia, usados si el modelo configurado
# en GEMINI_MODEL deja de estar disponible para la clave de API.
MODEL_FALLBACKS: tuple[str, ...] = (
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
)


class _ModelUnavailableError(Exception):
    """El modelo pedido no existe o ya no está disponible para la cuenta."""


class GeminiProvider(ExtractionProvider):
    def __init__(self, api_key: str, model: str, temperature: float = 0.0) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._temperature = temperature

    def extract(self, images: list[bytes], mime_type: str) -> str:
        parts: list[types.Part] = [types.Part(text=EXTRACTION_PROMPT)]
        for image in images:
            parts.append(types.Part(inline_data=types.Blob(mime_type=mime_type, data=image)))

        candidates = [self._model, *(m for m in MODEL_FALLBACKS if m != self._model)]
        unavailable: list[str] = []

        for model in candidates:
            try:
                return self._call(model, parts)
            except _ModelUnavailableError as exc:
                logger.warning("Modelo %s no disponible para esta clave (%s); probando siguiente.", model, exc)
                unavailable.append(model)

        raise ExtractionError(
            "Ninguno de los modelos de Gemini configurados está disponible para esta clave de API "
            f"({', '.join(unavailable)}). Entra en aistudio.google.com, comprueba qué modelos "
            "admiten tu clave y actualiza GEMINI_MODEL en el fichero .env."
        )

    def _call(self, model: str, parts: list[types.Part]) -> str:
        try:
            response = self._client.models.generate_content(
                model=model,
                contents=[types.Content(parts=parts)],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=INVOICE_SCHEMA,
                    temperature=self._temperature,
                ),
            )
        except Exception as exc:
            if _is_model_unavailable(exc):
                raise _ModelUnavailableError(str(exc)) from exc
            message = _friendly_api_error(exc)
            raise ExtractionError(f"Error al comunicarse con la API de Gemini ({model}): {message}") from exc

        if response.prompt_feedback and response.prompt_feedback.block_reason:
            raise ExtractionError(
                "La petición fue bloqueada por la API de Gemini "
                f"(razón: {response.prompt_feedback.block_reason.name})."
            )

        text = response.text
        if not text:
            raise ExtractionError("La API de Gemini no devolvió contenido para este documento.")

        return text


def _is_model_unavailable(exc: Exception) -> bool:
    """Detecta si el error significa que el modelo no está disponible (404)."""
    code = getattr(exc, "code", None)
    if code == 404:
        return True
    lowered = str(exc).lower()
    return any(
        marker in lowered
        for marker in (
            "not found",
            "no longer available",
            "not available to new users",
            "does not exist",
        )
    )


def _friendly_api_error(exc: Exception) -> str:
    """Convierte un error del SDK en un mensaje legible y accionable."""
    raw = str(exc)
    lowered = raw.lower()

    if "quota" in lowered or "429" in raw:
        return "se alcanzó la cuota gratuita de peticiones. Espera un momento y reintenta."
    if "permission" in lowered or "403" in raw or "api key not valid" in lowered or "invalid api key" in lowered:
        return "la clave de API no es válida o no tiene permisos para este modelo. Revísala en aistudio.google.com."
    if "model" in lowered and "not found" in lowered:
        return "el modelo configurado no existe. Revisa la variable GEMINI_MODEL."
    if "timeout" in lowered or "timed out" in lowered:
        return "la petición superó el tiempo de espera. Reintenta o usa un documento más corto."
    if "400" in raw:
        return f"la petición fue rechazada por la API (400). Detalle: {raw[:300]}"
    return f"{raw[:400]}"
