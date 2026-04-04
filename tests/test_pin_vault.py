from client.app.pin_vault import decrypt_license, encrypt_license


def test_pin_vault_roundtrip() -> None:
    salt, ct = encrypt_license("trial-key-12345678", "4242")
    assert decrypt_license(ct, "4242", salt) == "trial-key-12345678"
