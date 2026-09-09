"""Configuration safety - the checks that stop a bad production boot."""
import pytest

from app.core.config import Settings


def test_cors_origins_parse_to_a_list():
    s = Settings(cors_origins="http://a.com, http://b.com ,")
    assert s.cors_origin_list == ["http://a.com", "http://b.com"]


def test_database_url_must_name_the_driver():
    with pytest.raises(ValueError, match="postgresql\\+psycopg"):
        Settings(database_url="postgresql://user:pw@localhost/db")


def test_development_boot_is_permissive():
    Settings(environment="development", debug=True).assert_production_safe()   # no raise


def test_production_rejects_default_secret():
    s = Settings(environment="production", debug=False,
                 secret_key="dev-only-insecure-key-change-me",
                 cors_origins="https://app.example.com")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        s.assert_production_safe()


def test_production_rejects_wildcard_cors():
    s = Settings(environment="production", debug=False,
                 secret_key="x" * 40, cors_origins="*")
    with pytest.raises(RuntimeError, match="CORS"):
        s.assert_production_safe()


def test_production_rejects_debug_true():
    s = Settings(environment="production", debug=True,
                 secret_key="x" * 40, cors_origins="https://app.example.com")
    with pytest.raises(RuntimeError, match="DEBUG"):
        s.assert_production_safe()


def test_valid_production_config_passes():
    """
    Every production-relevant field is stated explicitly.

    Settings still reads .env for anything not passed, and the development .env
    sets REFRESH_COOKIE_SECURE=false so that cookies work over local http. A
    test asserting "a valid production configuration boots" has to supply a
    valid production configuration rather than inherit half of it from a
    developer's machine.
    """
    Settings(environment="production", debug=False, secret_key="x" * 40,
             cors_origins="https://app.example.com",
             refresh_cookie_secure=True,
             expose_refresh_token_in_body=False).assert_production_safe()
