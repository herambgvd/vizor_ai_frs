"""Logout / refresh revocation / change-password / reset — mutating tests use
their own dedicated users so they don't disturb the shared admin."""

from .conftest import API


def _make_user(client, admin_headers, email, password):
    role_id = client.get(f"{API}/auth/me", headers=admin_headers).json()["role"]["id"]
    client.post(
        f"{API}/auth/users",
        headers=admin_headers,
        json={"email": email, "password": password, "role_id": role_id},
    )


def test_logout_revokes_refresh(client):
    tok = client.post(
        f"{API}/auth/login", json={"email": "admin@example.com", "password": "changeme123"}
    ).json()
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    assert client.post(f"{API}/auth/logout", headers=h, json={"refresh_token": tok["refresh_token"]}).status_code == 204
    # the revoked refresh token no longer works
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": tok["refresh_token"]}).status_code == 401


def test_change_password(client, admin_headers):
    _make_user(client, admin_headers, "cp@example.com", "Start1234")
    tok = client.post(f"{API}/auth/login", json={"email": "cp@example.com", "password": "Start1234"}).json()
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    r = client.post(
        f"{API}/auth/change-password",
        headers=h,
        json={"current_password": "Start1234", "new_password": "Changed1234"},
    )
    assert r.status_code == 204
    assert client.post(f"{API}/auth/login", json={"email": "cp@example.com", "password": "Start1234"}).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": "cp@example.com", "password": "Changed1234"}).status_code == 200
    # change-password revoked the old refresh token
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": tok["refresh_token"]}).status_code == 401


def test_forgot_password_no_enumeration(client):
    assert client.post(f"{API}/auth/forgot-password", json={"email": "admin@example.com"}).status_code == 200
    assert client.post(f"{API}/auth/forgot-password", json={"email": "ghost@example.com"}).status_code == 200
