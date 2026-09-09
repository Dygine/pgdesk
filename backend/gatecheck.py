"""
Which supporting lookups a narrow role may make.

The route sweep logged two console 403s on /app/staff: a Receptionist holds
staff.view but not roles.view or branches.view, and the page fired those
lookups anyway. This confirms, without a browser, which endpoints each role may
call - and therefore which requests the frontend now skips instead of firing
and failing.
"""
from fastapi.testclient import TestClient

from app.main import app

GATES = {
    "/roles": "roles.view",
    "/branches": "branches.view",
    "/subscription": "dashboard.view",
}

ROLES = [
    ("Receptionist", "reception@sunriselivingpg.com", "demo1234"),
    ("Security", "security@sunriselivingpg.com", "demo1234"),
    ("Accountant", "accounts@sunriselivingpg.com", "demo1234"),
    ("PG Owner", "owner@sunrise.local", "Owner@2024"),
]


def main() -> None:
    client = TestClient(app)
    for label, email, password in ROLES:
        body = client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        ).json()["data"]
        headers = {"Authorization": f"Bearer {body['access_token']}"}
        permissions = set(body["user"]["permissions"])

        codes = {
            path: client.get("/api/v1" + path, headers=headers).status_code
            for path in ["/users", *GATES]
        }
        skipped = [p for p, perm in GATES.items() if perm not in permissions]

        print(f"  {label:13s} status if called: {codes}")
        print(f"                skipped by the UI: {skipped or 'nothing - all allowed'}")


if __name__ == "__main__":
    main()
