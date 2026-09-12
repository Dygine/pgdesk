"""
All configuration comes from the environment. Nothing that varies between
machines - and nothing secret - is written into the source tree.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # --- application ---
    project_name: str = "PGuru API"
    api_v1_prefix: str = "/api/v1"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = True

    # --- database ---
    database_url: str = Field(
        default="postgresql+psycopg://pgguru:pgguru@localhost:5432/pgguru",
        description="SQLAlchemy URL. Must name the psycopg (v3) driver explicitly.",
    )
    test_database_url: str | None = None
    db_echo: bool = False
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # --- security ---
    secret_key: str = "dev-only-insecure-key-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    #: How long a browser stays signed in. One day, deliberately: a laptop is
    #: shared and left open in a way a phone is not, and the session lives in a
    #: cookie nobody can see or manage. Installed apps do not use this - they
    #: get a permanent session from platform settings; see
    #: AuthService._refresh_window.
    browser_session_hours: int = 24

    # --- refresh session transport ---
    #
    # The refresh token is delivered as an HttpOnly cookie so that a script
    # injected into the page cannot read it. The access token stays in the
    # response body and is held in memory by the client: it is short-lived, and
    # something has to go in the Authorization header.
    #
    # The cookie is scoped to the auth path, so it is not attached to the
    # hundred-odd other API calls the app makes - a token that is never sent is
    # a token that cannot leak from a log or a proxy.
    refresh_cookie_name: str = "pgguru_refresh"
    refresh_cookie_path: str = "/api/v1/auth"
    refresh_cookie_secure: bool = True
    refresh_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    refresh_cookie_domain: str | None = None

    # Returns the refresh token in the JSON body as well as the cookie. Needed
    # by non-browser clients that have no cookie jar; never enable it for a web
    # deployment, since a body value is readable by any script that can hook
    # fetch. Refused outright in production by assert_production_safe.
    expose_refresh_token_in_body: bool = False

    # --- cors ---
    cors_origins: str = "http://localhost:5173"

    # --- area search for people looking for a PG ---
    #
    # Nominatim (OpenStreetMap) by default: free, no key. Its policy wants an
    # identifying User-Agent and at most one request a second, which is why the
    # API proxies and caches rather than letting every phone call it. Point this
    # at a self-hosted or paid Nominatim when traffic grows; set it empty to
    # switch area search off (the text search keeps working).
    geocoder_url: str = "https://nominatim.openstreetmap.org"
    geocoder_user_agent: str = "PGuru/1.0 (PG finder; https://get.dygine.com)"

    # --- development conveniences ---
    demo_password: str = "demo1234"

    @field_validator("database_url")
    @classmethod
    def _require_psycopg(cls, v: str) -> str:
        if v.startswith("postgresql://"):
            # psycopg2 is not a dependency; fail loudly now rather than at first query.
            raise ValueError("DATABASE_URL must name the driver: postgresql+psycopg://...")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def assert_production_safe(self) -> None:
        """Called at startup. Refuses to boot production with development defaults."""
        if not self.is_production:
            return
        problems = []
        if "change-me" in self.secret_key.lower() or len(self.secret_key) < 32:
            problems.append("SECRET_KEY is a default or too short")
        if "*" in self.cors_origin_list:
            problems.append("CORS_ORIGINS must not contain '*'")
        if self.debug:
            problems.append("DEBUG must be false")
        if not self.refresh_cookie_secure:
            problems.append("REFRESH_COOKIE_SECURE must be true")
        if self.refresh_cookie_samesite == "none" and not self.refresh_cookie_secure:
            problems.append("SameSite=None requires REFRESH_COOKIE_SECURE=true")
        if self.expose_refresh_token_in_body:
            problems.append(
                "EXPOSE_REFRESH_TOKEN_IN_BODY must be false - a refresh token in the "
                "response body is readable by injected script")
        if problems:
            raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
