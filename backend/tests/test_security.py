"""Password hashing and JWT behaviour."""
import time

from app.core.security import (
    create_access_token, create_refresh_token, decode_token,
    hash_password, needs_rehash, verify_password,
)


def test_hash_is_not_the_plaintext():
    h = hash_password("demo1234")
    assert h != "demo1234"
    assert "demo1234" not in h


def test_hash_uses_argon2id():
    assert hash_password("x").startswith("$argon2id$")


def test_hashing_is_salted():
    assert hash_password("same") != hash_password("same")


def test_verify_accepts_correct_and_rejects_wrong():
    h = hash_password("correct-horse")
    assert verify_password("correct-horse", h) is True
    assert verify_password("wrong", h) is False


def test_verify_survives_a_garbage_hash():
    assert verify_password("anything", "not-a-hash") is False


def test_fresh_hash_does_not_need_rehash():
    assert needs_rehash(hash_password("x")) is False


def test_access_token_round_trip():
    token = create_access_token("user-123", org="org-1")
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "user-123"
    assert payload["org"] == "org-1"


def test_refresh_token_is_not_accepted_as_an_access_token():
    """Token confusion is a real attack; the type claim is checked."""
    refresh = create_refresh_token("user-123")
    assert decode_token(refresh, expected_type="access") is None
    assert decode_token(refresh, expected_type="refresh") is not None


def test_tampered_token_is_rejected():
    token = create_access_token("user-123")
    tampered = token[:-4] + ("aaaa" if not token.endswith("aaaa") else "bbbb")
    assert decode_token(tampered) is None


def test_garbage_token_is_rejected():
    assert decode_token("not.a.token") is None
