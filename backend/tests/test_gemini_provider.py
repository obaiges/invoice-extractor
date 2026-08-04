"""Tests del proveedor Gemini: fallback de modelos cuando el configurado no está disponible."""

from __future__ import annotations

import pytest

from app.core.errors import ExtractionError
from app.extraction.gemini_provider import GeminiProvider, _is_model_unavailable


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text
        self.prompt_feedback = None


class _FakeClient:
    """Client genai simulado. `error_factory(model)` devuelve la excepción a lanzar o None."""

    def __init__(self, error_factory=None) -> None:
        self.error_factory = error_factory
        self.calls: list[str] = []

    @property
    def models(self) -> "_Models":
        return _Models(self)


class _Models:
    def __init__(self, client: _FakeClient) -> None:
        self._client = client

    def generate_content(self, model: str, contents, config) -> _FakeResponse:
        self._client.calls.append(model)
        error = self._client.error_factory(model) if self._client.error_factory else None
        if error:
            raise error
        return _FakeResponse('{"invoice_number": "OK-FALLBACK"}')


def _unavailable(message: str):
    return lambda model: RuntimeError(f"This model models/{model} {message}")


def test_fallback_when_configured_model_unavailable(monkeypatch):
    fake = _FakeClient(
        error_factory=lambda model: (
            RuntimeError("is no longer available to new users.")
            if model == "gemini-2.5-flash"
            else None
        )
    )
    monkeypatch.setattr("app.extraction.gemini_provider.genai.Client", lambda api_key: fake)

    provider = GeminiProvider(api_key="test", model="gemini-2.5-flash")
    result = provider.extract([b"\x89PNG fake"], "image/png")

    assert result == '{"invoice_number": "OK-FALLBACK"}'
    assert fake.calls[0] == "gemini-2.5-flash"
    assert "gemini-3.6-flash" in fake.calls


def test_no_fallback_on_unrelated_error(monkeypatch):
    fake = _FakeClient(error_factory=lambda model: RuntimeError("quota exceeded, try again"))
    monkeypatch.setattr("app.extraction.gemini_provider.genai.Client", lambda api_key: fake)

    provider = GeminiProvider(api_key="test", model="gemini-2.5-flash")
    with pytest.raises(ExtractionError):
        provider.extract([b"\x89PNG fake"], "image/png")

    assert fake.calls == ["gemini-2.5-flash"]


def test_error_when_all_models_unavailable(monkeypatch):
    fake = _FakeClient(error_factory=_unavailable("is no longer available to new users."))
    monkeypatch.setattr("app.extraction.gemini_provider.genai.Client", lambda api_key: fake)

    provider = GeminiProvider(api_key="test", model="gemini-2.5-flash")
    with pytest.raises(ExtractionError) as excinfo:
        provider.extract([b"\x89PNG fake"], "image/png")

    assert "Ninguno de los modelos" in str(excinfo.value)
    assert "GEMINI_MODEL" in str(excinfo.value)
    assert len(fake.calls) >= 2


class TestIsModelUnavailable:
    def test_404_code(self):
        error = RuntimeError("x")
        error.code = 404
        assert _is_model_unavailable(error)

    def test_message_markers(self):
        assert _is_model_unavailable(RuntimeError("model not found"))
        assert _is_model_unavailable(RuntimeError("is no longer available to new users"))

    def test_other_errors(self):
        assert not _is_model_unavailable(RuntimeError("quota exceeded"))
        assert not _is_model_unavailable(RuntimeError("invalid api key"))
