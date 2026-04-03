from client.app.user_guide_loader import FALLBACK_GUIDES, load_guides


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
