"""Tests del proveedor Gemini: fallback de modelos, reintentos y cuota."""

from __future__ import annotations

import pytest

from app.core.errors import ExtractionError
from app.extraction.gemini_provider import (
    GeminiProvider,
    _is_high_demand,
    _is_model_unavailable,
    _is_rate_limit,
)


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text
        self.prompt_feedback = None


class _FakeClient:
    """Client genai simulado.

    - `error_factory(model)` devuelve la excepción a lanzar para ese modelo o None.
    - `fail_once_for` hace que el primer intento de un modelo falle con alta demanda
      (simula la sobrecarga temporal).
    """

    def __init__(self, error_factory=None, fail_once_for=()) -> None:
        self.error_factory = error_factory
        self.fail_once_for = set(fail_once_for)
        self.calls: list[str] = []

    @property
    def models(self) -> "_Models":
        return _Models(self)


class _Models:
    def __init__(self, client: _FakeClient) -> None:
        self._client = client

    def generate_content(self, model: str, contents, config) -> _FakeResponse:
        self._client.calls.append(model)
        if model in self._client.fail_once_for:
            self._client.fail_once_for.discard(model)
            raise RuntimeError(f"This model models/{model} is currently experiencing high demand.")
        error = self._client.error_factory(model) if self._client.error_factory else None
        if error:
            raise error
        return _FakeResponse('{"invoice_number": "OK"}')


def _unavailable(message: str):
    return lambda model: RuntimeError(f"This model models/{model} {message}")


def _patch_client(monkeypatch, fake: _FakeClient) -> None:
    monkeypatch.setattr("app.extraction.gemini_provider.genai.Client", lambda api_key: fake)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Elimina las esperas de los reintentos para que los tests corran al instante."""
    monkeypatch.setattr("app.extraction.gemini_provider.time.sleep", lambda _seconds: None)


# --- Fallback por modelo no disponible (404) ---


def test_fallback_when_configured_model_unavailable(monkeypatch):
    fake = _FakeClient(
        error_factory=lambda model: (
            RuntimeError("is no longer available to new users.")
            if model == "gemini-2.5-flash"
            else None
        )
    )
    _patch_client(monkeypatch, fake)

    provider = GeminiProvider(api_key="test", model="gemini-2.5-flash")
    result = provider.extract([b"\x89PNG fake"], "image/png")

    assert result == '{"invoice_number": "OK"}'
    assert fake.calls[0] == "gemini-2.5-flash"
    assert "gemini-3.5-flash" in fake.calls


def test_full_flash_preferred_over_lite_fallbacks(monkeypatch):
    fake = _FakeClient(error_factory=_unavailable("is no longer available to new users."))
    _patch_client(monkeypatch, fake)

    provider = GeminiProvider(api_key="test", model="gemini-3.6-flash")
    with pytest.raises(ExtractionError):
        provider.extract([b"\x89PNG fake"], "image/png")

    # Orden de candidatos: configurado, flash completo y solo después los "lite".
    assert fake.calls[0] == "gemini-3.6-flash"
    assert fake.calls[1] == "gemini-3.5-flash"
    lite_index = min(
        fake.calls.index("gemini-3.1-flash-lite"),
        fake.calls.index("gemini-2.5-flash-lite"),
    )
    assert fake.calls.index("gemini-3.5-flash") < lite_index


def test_error_when_all_models_unavailable(monkeypatch):
    fake = _FakeClient(error_factory=_unavailable("is no longer available to new users."))
    _patch_client(monkeypatch, fake)

    provider = GeminiProvider(api_key="test", model="gemini-2.5-flash")
    with pytest.raises(ExtractionError) as excinfo:
        provider.extract([b"\x89PNG fake"], "image/png")

    assert "Ninguno" not in str(excinfo.value)
    assert "no disponibles" in str(excinfo.value)
    assert "GEMINI_MODEL" in str(excinfo.value)
    assert len(fake.calls) >= 2


# --- Alta demanda temporal (503): reintenta y luego prueba otro modelo ---


def test_retry_succeeds_on_transient_high_demand(monkeypatch):
    fake = _FakeClient(fail_once_for={"gemini-3.6-flash"})
    _patch_client(monkeypatch, fake)

    provider = GeminiProvider(api_key="test", model="gemini-3.6-flash")
    result = provider.extract([b"\x89PNG fake"], "image/png")

    assert result == '{"invoice_number": "OK"}'
    # El primer intento falló (503) y el segundo con el mismo modelo triunfó.
    assert fake.calls.count("gemini-3.6-flash") == 2


def test_high_demand_persists_then_falls_back(monkeypatch):
    fake = _FakeClient(
        error_factory=lambda model: (
            RuntimeError("This model is currently experiencing high demand.")
            if model == "gemini-3.6-flash"
            else None
        )
    )
    _patch_client(monkeypatch, fake)

    provider = GeminiProvider(api_key="test", model="gemini-3.6-flash")
    result = provider.extract([b"\x89PNG fake"], "image/png")

    assert result == '{"invoice_number": "OK"}'
    assert "gemini-3.5-flash" in fake.calls


def test_error_when_all_models_high_demand(monkeypatch):
    fake = _FakeClient(error_factory=lambda model: RuntimeError("currently experiencing high demand."))
    _patch_client(monkeypatch, fake)

    provider = GeminiProvider(api_key="test", model="gemini-3.6-flash")
    with pytest.raises(ExtractionError) as excinfo:
        provider.extract([b"\x89PNG fake"], "image/png")

    assert "alta demanda" in str(excinfo.value)
    assert "reintenta en unos segundos" in str(excinfo.value)


# --- Cuota (429): no quema los modelos de reserva ---


def test_rate_limit_raises_clear_error_without_fallback(monkeypatch):
    fake = _FakeClient(error_factory=lambda model: RuntimeError("quota exceeded, 429"))
    _patch_client(monkeypatch, fake)

    provider = GeminiProvider(api_key="test", model="gemini-3.6-flash")
    with pytest.raises(ExtractionError) as excinfo:
        provider.extract([b"\x89PNG fake"], "image/png")

    assert "cuota" in str(excinfo.value).lower()
    # Solo se intentó el modelo configurado (sin consumir los fallbacks).
    assert set(fake.calls) == {"gemini-3.6-flash"}


# --- Registro del modelo usado ---


def test_last_model_used_recorded(monkeypatch):
    fake = _FakeClient()
    _patch_client(monkeypatch, fake)

    provider = GeminiProvider(api_key="test", model="gemini-3.6-flash")
    assert provider.last_model_used is None
    provider.extract([b"\x89PNG fake"], "image/png")

    assert provider.last_model_used == "gemini-3.6-flash"


def test_last_model_used_reflects_fallback(monkeypatch):
    fake = _FakeClient(
        error_factory=lambda model: (
            RuntimeError("This model is currently experiencing high demand.")
            if model == "gemini-3.6-flash"
            else None
        )
    )
    _patch_client(monkeypatch, fake)

    provider = GeminiProvider(api_key="test", model="gemini-3.6-flash")
    provider.extract([b"\x89PNG fake"], "image/png")

    assert provider.last_model_used == "gemini-3.5-flash"


# --- Detección de errores ---


class TestErrorClassification:
    def test_model_unavailable(self):
        error = RuntimeError("x")
        error.code = 404
        assert _is_model_unavailable(error)
        assert _is_model_unavailable(RuntimeError("model not found"))
        assert _is_model_unavailable(RuntimeError("no longer available to new users"))

    def test_high_demand(self):
        error = RuntimeError("x")
        error.code = 503
        assert _is_high_demand(error)
        assert _is_high_demand(RuntimeError("currently experiencing high demand"))

    def test_rate_limit(self):
        error = RuntimeError("x")
        error.code = 429
        assert _is_rate_limit(error)
        assert _is_rate_limit(RuntimeError("quota exceeded"))

    def test_no_cross_matches(self):
        assert not _is_model_unavailable(RuntimeError("quota exceeded"))
        assert not _is_high_demand(RuntimeError("quota exceeded"))
        assert not _is_rate_limit(RuntimeError("not found"))
