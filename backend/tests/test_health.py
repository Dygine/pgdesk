def test_health_is_up(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_health_db_reports_connection(client):
    r = client.get("/health/db")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    assert body["server_version"]


def test_health_full_envelope(client):
    r = client.get("/health/full")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["database"]["connected"] is True


def test_openapi_and_docs_available(client):
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200


def test_request_id_header_present(client):
    r = client.get("/health")
    assert r.headers.get("X-Request-ID")


def test_unknown_path_uses_the_standard_error_envelope(client):
    """Regression: the handlers once passed JSONResponse args positionally,
    which turned every 404 into a 500."""
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    body = r.json()
    assert body["success"] is False
    assert body["code"] == "http_error"
    assert body["errors"] == []


def test_validation_error_envelope(client):
    """
    Uses /auth/login because it is public and actually validates its body.
    /meta/plans used to serve here, but it now requires authentication and
    would answer 401 before any validation ran.
    """
    r = client.post("/api/v1/auth/login", json={"email": "not-an-email"})
    assert r.status_code == 422
    body = r.json()
    assert body["success"] is False
    assert body["errors"], "a validation failure returned no field errors"
    assert all("field" in e and "message" in e for e in body["errors"])


def test_meta_endpoints_require_authentication(client):
    for path in ("/api/v1/meta/plans", "/api/v1/meta/permissions"):
        assert client.get(path).status_code == 401, f"{path} answered anonymously"
