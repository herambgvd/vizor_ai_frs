import uuid

from .conftest import API


def test_error_envelope_not_found(client, admin_headers):
    r = client.patch(f"{API}/auth/users/{uuid.uuid4()}", headers=admin_headers, json={"is_active": False})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_unauthorized_envelope(client):
    r = client.get(f"{API}/auth/users")  # no token
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_pagination_envelope(client, admin_headers):
    body = client.get(f"{API}/auth/users", headers=admin_headers).json()
    for key in ("items", "page", "page_size", "total", "pages", "has_next", "has_prev"):
        assert key in body
    assert isinstance(body["items"], list)


def test_request_id_header(client):
    assert "X-Request-ID" in client.get("/health").headers
