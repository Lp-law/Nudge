import pytest


@pytest.fixture(autouse=True)
def _reset_license_binding_store() -> None:
    from app.services.license_binding_store import reset_license_binding_store_for_tests

    reset_license_binding_store_for_tests()
    yield
