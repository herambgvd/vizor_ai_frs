from .conftest import API


def test_me(client, admin_headers):
    r = client.get(f"{API}/auth/me", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["role"]["name"] == "Administrator"
    assert r.json()["role"]["permissions"] == ["*"]


def test_wrong_password_envelope(client):
    r = client.post(f"{API}/auth/login", json={"email": "admin@example.com", "password": "nope"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "UNAUTHORIZED"


def test_refresh_issues_access(client):
    tok = client.post(
        f"{API}/auth/login", json={"email": "admin@example.com", "password": "changeme123"}
    ).json()
    r = client.post(f"{API}/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert r.status_code == 200 and r.json()["access_token"]


def test_password_policy_rejects_weak(client, admin_headers):
    role_id = client.get(f"{API}/auth/me", headers=admin_headers).json()["role"]["id"]
    r = client.post(
        f"{API}/auth/users",
        headers=admin_headers,
        json={"email": "weak@example.com", "password": "abc", "role_id": role_id},
    )
    assert r.status_code == 422
    assert "at least" in r.json()["error"]["message"]


def test_versioning_old_path_gone(client):
    # unversioned path must 404 now that everything is under /api/v1
    assert client.get("/api/branding").status_code == 404
    assert client.get(f"{API}/branding").status_code == 200  # public
