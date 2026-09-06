from potluck import crypto
from potluck.config import get_settings


def _with_key(monkeypatch, key: str | None):
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
    monkeypatch.setenv("SECRET_KEY", key or "")


def test_roundtrip(monkeypatch):
    _with_key(monkeypatch, "test-key-not-a-real-secret")
    token = "eyJhbGciOiJI.pretend-access-token"
    assert crypto.decrypt(crypto.encrypt(token)) == token


def test_ciphertext_does_not_contain_the_plaintext(monkeypatch):
    _with_key(monkeypatch, "test-key-not-a-real-secret")
    secret = "swiggy-access-token-value"
    assert secret not in crypto.encrypt(secret)


def test_changing_the_key_breaks_decryption(monkeypatch):
    """Documents the failure mode: rotating SECRET_KEY means re-authorizing."""
    _with_key(monkeypatch, "first-key")
    ciphertext = crypto.encrypt("hello")
    _with_key(monkeypatch, "second-key")
    try:
        crypto.decrypt(ciphertext)
    except crypto.SecretKeyMissing:
        pass
    else:
        raise AssertionError("expected decryption to fail after a key change")
    get_settings.cache_clear()
    crypto._cipher.cache_clear()
