import json

from client.app.user_guide_loader import FALLBACK_GUIDES, load_guides
from client.app import user_guide_loader


def test_user_guide_loader_has_required_locales() -> None:
    guides = load_guides()
    for locale in ("he", "en", "ar", "ru"):
        assert locale in guides
        assert guides[locale]["full"].strip()


def test_user_guide_loader_uses_locale_fallbacks_shape() -> None:
    for _locale, payload in FALLBACK_GUIDES.items():
        assert payload["label"].strip()
        assert payload["title"].strip()
        assert payload["close_button"].strip()
        assert payload["short_install_title"].strip()
        assert payload["short_use_title"].strip()


def test_user_guide_loader_falls_back_per_locale(monkeypatch, tmp_path) -> None:
    payload = {
        "he": {
            "label": "עברית",
            "title": "he",
            "layout": "rtl",
            "language_label": "שפה",
            "close_button": "סגור",
            "short_install_title": "א",
            "short_use_title": "ב",
            "full_lines": ["ok"],
            "short_install_lines": ["ok"],
            "short_use_lines": ["ok"],
        },
        # malformed locale: empty required lines
        "en": {
            "label": "English",
            "title": "en",
            "layout": "ltr",
            "language_label": "Language",
            "close_button": "Close",
            "short_install_title": "Install",
            "short_use_title": "Use",
            "full_lines": [],
            "short_install_lines": [],
            "short_use_lines": [],
        },
    }
    content_path = tmp_path / "guide.json"
    content_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(user_guide_loader, "CONTENT_PATH", content_path)

    guides = load_guides()
    assert guides["he"]["title"] == "he"
    assert guides["en"]["title"] == FALLBACK_GUIDES["en"]["title"]
    assert guides["ar"]["title"] == FALLBACK_GUIDES["ar"]["title"]
