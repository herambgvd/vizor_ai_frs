from .conftest import API


def test_permission_catalog(client, admin_headers):
    r = client.get(f"{API}/auth/permissions", headers=admin_headers)
    assert r.status_code == 200
    assert "Users" in r.json()["groups"]


def test_unknown_permission_rejected(client, admin_headers):
    r = client.post(
        f"{API}/auth/roles",
        headers=admin_headers,
        json={"name": "BadRole", "permissions": ["does.not.exist"]},
    )
    assert r.status_code == 422


def test_custom_role_permission_gating(client, admin_headers):
    # a role with only user.read can list users but not create them
    r = client.post(
        f"{API}/auth/roles",
        headers=admin_headers,
        json={"name": "Auditor", "permissions": ["audit.read", "user.read"]},
    )
    assert r.status_code == 201
    role_id = r.json()["id"]
    client.post(
        f"{API}/auth/users",
        headers=admin_headers,
        json={"email": "aud@example.com", "password": "Aud12345", "role_id": role_id},
    )
    aud = client.post(
        f"{API}/auth/login", json={"email": "aud@example.com", "password": "Aud12345"}
    ).json()
    h = {"Authorization": f"Bearer {aud['access_token']}"}

    assert client.get(f"{API}/auth/users", headers=h).status_code == 200  # user.read granted
    denied = client.post(
        f"{API}/auth/users",
        headers=h,
        json={"email": "x@example.com", "password": "Xxxx1234", "role_id": role_id},
    )
    assert denied.status_code == 403  # no user.manage
    assert "user.manage" in denied.json()["error"]["message"]


def test_api_key_auth(client, admin_headers):
    role_id = client.get(f"{API}/auth/me", headers=admin_headers).json()["role"]["id"]
    r = client.post(
        f"{API}/auth/api-keys", headers=admin_headers, json={"name": "k", "role_id": role_id}
    )
    assert r.status_code == 201
    assert r.json()["key"].startswith("vz_")
