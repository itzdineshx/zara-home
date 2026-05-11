from __future__ import annotations

from app.services.language_service import LanguageService


def test_detects_english_text() -> None:
    service = LanguageService()
    result = service.detect("Turn on the lights in living room")

    assert result.code == "en"
    assert result.name == "English"


def test_detects_tamil_script_text() -> None:
    service = LanguageService()
    result = service.detect("வணக்கம் ஜாரா")

    assert result.code == "ta"
    assert result.name == "Tamil"


def test_detects_tamil_transliteration_text() -> None:
    service = LanguageService()
    result = service.detect("vanakkam zara epadi irukka")

    assert result.code == "ta"
    assert result.name == "Tamil"


def test_non_supported_language_falls_back_to_english() -> None:
    service = LanguageService()
    result = service.detect("Hola, como estas?")

    assert result.code == "en"
    assert result.name == "English"
