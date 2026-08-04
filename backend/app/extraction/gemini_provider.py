"""Proveedor de extracción basado en la API de Gemini (Google AI Studio).

Implementación de `ExtractionProvider` que envía las páginas del documento como
imágenes inline (base64) a un modelo multimodal junto con un prompt estructurado
y `response_schema` para obtener JSON controlado.

Robustez frente a errores de la API:
- **404 (modelo no disponible)**: el modelo ya no existe o la cuenta no puede usarlo
  (Google retira modelos antiguos para cuentas nuevas). Se prueba el siguiente modelo
  de la cadena de reserva.
- **503 (alta demanda)**: sobrecarga temporal de un modelo concreto. Se reintenta y, si
  persiste, se prueba el siguiente modelo.
- **429 (cuota)**: límite de peticiones de la cuenta. Se reintenta brevemente y, si
  persiste, se devuelve un error claro (no se "queman" los modelos de reserva).

Todos los errores se envuelven en `ExtractionError` con un mensaje accionable;
nunca escapan crudos.
"""

from __future__ import annotations

import logging
import time

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

MAX_ATTEMPTS_PER_MODEL = 2
RETRY_DELAY_SECONDS = 1.5


class _ModelUnavailableError(Exception):
    """El modelo pedido no existe o ya no está disponible para la cuenta (404)."""


class _HighDemandError(Exception):
    """El modelo está temporalmente sobrecargado (503)."""


class _RateLimitError(Exception):
    """Se alcanzó el límite de peticiones de la cuenta (429)."""


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
        high_demand: list[str] = []

        for model in candidates:
            for attempt in range(1, MAX_ATTEMPTS_PER_MODEL + 1):
                try:
                    return self._call(model, parts)
                except _ModelUnavailableError as exc:
                    logger.warning(
                        "Modelo %s no disponible para esta clave (%s); probando siguiente.", model, exc
                    )
                    unavailable.append(model)
                    break
                except _HighDemandError as exc:
                    if attempt < MAX_ATTEMPTS_PER_MODEL:
                        logger.warning(
                            "Modelo %s con alta demanda (intento %d/%d); reintentando.",
                            model, attempt, MAX_ATTEMPTS_PER_MODEL,
                        )
                        time.sleep(RETRY_DELAY_SECONDS)
                        continue
                    logger.warning(
                        "Modelo %s sigue con alta demanda tras %d intentos; probando siguiente.",
                        model, MAX_ATTEMPTS_PER_MODEL,
                    )
                    high_demand.append(model)
                    time.sleep(RETRY_DELAY_SECONDS)
                    break
                except _RateLimitError as exc:
                    if attempt < MAX_ATTEMPTS_PER_MODEL:
                        logger.warning(
                            "Cuota de la API alcanzada (intento %d/%d); reintentando.",
                            attempt, MAX_ATTEMPTS_PER_MODEL,
                        )
                        time.sleep(RETRY_DELAY_SECONDS * 2)
                        continue
                    raise ExtractionError(
                        "Se alcanzó la cuota gratuita de la API de Gemini. "
                        "Espera un momento y vuelve a intentar la extracción."
                    ) from exc

        reasons = []
        if unavailable:
            reasons.append(f"modelos no disponibles para esta cuenta ({', '.join(unavailable)})")
        if high_demand:
            reasons.append(f"modelos con alta demanda temporal ({', '.join(high_demand)})")
        raise ExtractionError(
            "No se pudo extraer el documento: " + "; ".join(reasons) + ". "
            "Si fue por alta demanda, reintenta en unos segundos. Si fue por disponibilidad, "
            "comprueba qué modelos admite tu clave en aistudio.google.com y actualiza "
            "GEMINI_MODEL en el fichero .env."
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
            if _is_high_demand(exc):
                raise _HighDemandError(str(exc)) from exc
            if _is_rate_limit(exc):
                raise _RateLimitError(str(exc)) from exc
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
    if getattr(exc, "code", None) == 404:
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


def _is_high_demand(exc: Exception) -> bool:
    """Detecta sobrecarga temporal de un modelo (503 / high demand)."""
    if getattr(exc, "code", None) == 503:
        return True
    lowered = str(exc).lower()
    return "high demand" in lowered or "currently experiencing" in lowered


def _is_rate_limit(exc: Exception) -> bool:
    """Detecta límite de peticiones de la cuenta (429 / quota)."""
    code = getattr(exc, "code", None)
    if code in (429, 500):
        return True
    lowered = str(exc).lower()
    return "quota" in lowered or "rate limit" in lowered or "429" in lowered


def _friendly_api_error(exc: Exception) -> str:
    """Convierte un error del SDK en un mensaje legible y accionable."""
    raw = str(exc)
    lowered = raw.lower()

    if "permission" in lowered or "403" in raw or "api key not valid" in lowered or "invalid api key" in lowered:
        return "la clave de API no es válida o no tiene permisos para este modelo. Revísala en aistudio.google.com."
    if "model" in lowered and "not found" in lowered:
        return "el modelo configurado no existe. Revisa la variable GEMINI_MODEL."
    if "timeout" in lowered or "timed out" in lowered:
        return "la petición superó el tiempo de espera. Reintenta o usa un documento más corto."
    if "400" in raw:
        return f"la petición fue rechazada por la API (400). Detalle: {raw[:300]}"
    return f"{raw[:400]}"
