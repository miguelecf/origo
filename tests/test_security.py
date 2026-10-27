import datetime as dt
import logging

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.clock import now
from app.core.config import Settings, settings
from app.models import LoginAttempt, WebSession
from app.services import guests, security
from app.web.security import COOKIE_NAME, client_ip

PASSWORD = "correct horse battery staple"


def login(client, username="owner", password=PASSWORD, code=""):
    return client.post("/login", data={"username": username, "password": password, "code": code}, follow_redirects=False)


def test_anonymous_and_no_implicit_owner(anonymous_client):
    for path in ("/", "/plata", "/cuerpo", "/dia", "/invitados", "/super", "/deudas"):
        response = anonymous_client.get(path, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"
    assert login(anonymous_client).status_code == 401


def test_generic_failure_and_dummy_hash(anonymous_client, owner, monkeypatch):
    hashes = []
    verify = security.hasher.verify

    def record(self, encoded, password):
        hashes.append(encoded)
        return verify(encoded, password)

    monkeypatch.setattr(type(security.hasher), "verify", record)
    absent = login(anonymous_client, username="absent")
    wrong = login(anonymous_client, password="incorrect")
    assert absent.status_code == wrong.status_code == 401
    assert absent.text == wrong.text
    assert hashes == [security.DUMMY_HASH, owner.password_hash]
    assert owner.password_hash.startswith("$argon2id$")


def test_login_rotation_logout_and_replay(anonymous_client, owner, db):
    assert login(anonymous_client).status_code == 303
    first = anonymous_client.cookies.get(COOKIE_NAME)
    assert login(anonymous_client).status_code == 303
    second = anonymous_client.cookies.get(COOKIE_NAME)
    assert first != second
    assert security.session_identity(db, first) is None
    assert anonymous_client.get("/", follow_redirects=False).status_code == 200
    assert anonymous_client.get("/logout").status_code == 405
    assert anonymous_client.post("/logout", follow_redirects=False).status_code == 303
    anonymous_client.cookies.set(COOKIE_NAME, second)
    assert anonymous_client.get("/", follow_redirects=False).status_code == 303
    assert db.get(WebSession, security.digest(second)) is None


@pytest.mark.parametrize("field,seconds", [("last_seen_at", 1801), ("created_at", 86401)])
def test_session_expiry(client, db, field, seconds):
    token = client.cookies.get(COOKIE_NAME)
    session = db.get(WebSession, security.digest(token))
    setattr(session, field, now() - dt.timedelta(seconds=seconds))
    db.commit()
    assert client.get("/", follow_redirects=False).status_code == 303


def test_password_change_invalidates_sessions(client, db, owner):
    security.set_password(db, owner, "another sufficiently long password")
    assert client.get("/", follow_redirects=False).status_code == 303


def test_persistent_increasing_lockout(anonymous_client, owner, db):
    for _ in range(5):
        assert login(anonymous_client, password="wrong").status_code == 401
    assert login(anonymous_client).status_code == 429
    rows = list(db.scalars(select(LoginAttempt)))
    assert len(rows) == 2
    for row in rows:
        row.blocked_until = now() - dt.timedelta(seconds=1)
    db.commit()
    # Otra instancia usa los mismos contadores en DB.
    fresh = TestClient(anonymous_client.app, base_url=settings.BASE_URL, headers={"Origin": settings.BASE_URL})
    assert login(fresh, password="wrong").status_code == 401
    db.expire_all()
    assert all(row.failures == 6 and row.blocked_until >= now() + dt.timedelta(seconds=58) for row in rows)
    assert login(fresh).status_code == 429


def test_valid_login_is_not_counted_as_failed_ip_attempt(anonymous_client, owner, db):
    for _ in range(4):
        assert login(anonymous_client, password="wrong").status_code == 401
    assert login(anonymous_client).status_code == 303
    ip_key = security.attempt_keys("testclient", "owner")[0]
    row = db.get(LoginAttempt, ip_key)
    assert row.failures == 4 and row.blocked_until is None
    assert login(anonymous_client).status_code == 303
    assert db.get(LoginAttempt, ip_key).failures == 4


def test_rate_limits_per_ip_and_user(db, owner):
    for i in range(5):
        assert security.authenticate(db, "owner", "wrong", "", f"192.0.2.{i}") == (None, False)
    assert security.authenticate(db, "owner", PASSWORD, "", "198.51.100.1") == (None, True)
    for i in range(5):
        assert security.authenticate(db, f"unknown-{i}", "wrong", "", "203.0.113.1") == (None, False)
    assert security.authenticate(db, "new-user", PASSWORD, "", "203.0.113.1") == (None, True)


def test_totp_and_replay(anonymous_client, db, owner):
    secret = pyotp.random_base32()
    security.set_totp(db, owner, secret)
    assert login(anonymous_client, code="💥💥💥").status_code == 401
    assert login(anonymous_client, code=pyotp.TOTP(secret).now()).status_code == 303
    assert login(anonymous_client, code=pyotp.TOTP(secret).now()).status_code == 401
    security.set_totp(db, owner, None)
    assert anonymous_client.get("/", follow_redirects=False).status_code == 303
    assert login(anonymous_client).status_code == 303


def test_csrf(client):
    for method in ("post", "put", "delete", "patch"):
        call = getattr(client, method)
        assert call("/super/casa", headers={"Origin": "https://evil.example"}).status_code == 403
        assert call("/super/casa", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.post("/super/casa", data={"text": "pan"}).status_code == 200
    client.headers.pop("origin")
    assert client.post("/super/casa", data={"text": "leche"}).status_code == 403
    assert client.post("/super/casa", headers={"Referer": settings.BASE_URL + "/super"}, data={"text": "leche"}).status_code == 200
    assert client.post("/super/casa", headers={"Origin": "null", "Referer": settings.BASE_URL}).status_code == 403


def test_super_put(client, db):
    from app.services import lists
    trip = lists.start_trip(db)
    response = client.put(f"/super/compra/{trip.id}", json={"items": [{"name": "pan", "price": "100", "qty": "2"}]})
    assert response.status_code == 200
    assert response.json()["total"] == "200.00"


def test_headers_surface_hosts_and_errors(anonymous_client):
    response = anonymous_client.get("/login")
    for header in ("content-security-policy", "x-frame-options", "x-content-type-options", "referrer-policy", "permissions-policy"):
        assert header in response.headers
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert anonymous_client.get(path).status_code == 404
    assert anonymous_client.get("/login", headers={"Host": "evil.example"}).status_code == 400

    @anonymous_client.app.get("/crash")
    def crash():
        raise RuntimeError("sensitive-password")

    response = anonymous_client.get("/crash")
    assert response.status_code == 500
    assert "sensitive-password" not in response.text
    assert "x-frame-options" in response.headers


def test_https_cookies_and_hsts(monkeypatch, db, owner):
    from app.core.database import get_db
    from app.main import create_app
    monkeypatch.setattr(settings, "BASE_URL", "https://mentor.example.com")
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, base_url=settings.BASE_URL, headers={"Origin": settings.BASE_URL}) as client:
        response = login(client)
        cookie = response.headers["set-cookie"]
        assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
        assert response.headers["strict-transport-security"] == "max-age=31536000"
        assert client.get("/").status_code == 200


@pytest.mark.parametrize("secret", ["", "dev-secret-change-me", "x" * 64, "example-secret-change-me-" * 3])
def test_reject_weak_production_secret(secret):
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(_env_file=None, BASE_URL="https://mentor.example.com", SECRET_KEY=secret)


def test_app_does_not_start_with_weak_https_secret(monkeypatch):
    from app.main import create_app
    monkeypatch.setattr(settings, "BASE_URL", "https://mentor.example.com")
    monkeypatch.setattr(settings, "SECRET_KEY", "dev-secret-change-me")
    with pytest.raises(ValueError, match="SECRET_KEY"):
        create_app()


def test_dev_open_explicit_and_local_only(anonymous_client, monkeypatch):
    with pytest.raises(ValueError, match="MENTOR_DEV_OPEN"):
        Settings(_env_file=None, BASE_URL="https://mentor.example.com", SECRET_KEY="test-only-randomish-1234567890ABCDEF", MENTOR_DEV_OPEN=True)
    with pytest.raises(ValueError, match="MENTOR_DEV_OPEN"):
        Settings(_env_file=None, BASE_URL="http://mentor.example.com", MENTOR_DEV_OPEN=True)
    monkeypatch.setattr(settings, "MENTOR_DEV_OPEN", True)
    assert anonymous_client.get("/").status_code == 200


def test_trusted_proxy_ip():
    def scope(peer):
        return {"client": (peer, 123), "headers": [(b"cf-connecting-ip", b"203.0.113.5"), (b"x-forwarded-for", b"198.51.100.1")]}
    assert client_ip(scope("127.0.0.1")) == "203.0.113.5"
    assert client_ip(scope("198.51.100.9")) == "198.51.100.9"
    assert client_ip(scope("::1")) == "::1"


def test_guest_rotation_revocation_expiry_and_logs(anonymous_client, db, caplog):
    caplog.set_level(logging.INFO, logger="mentor")
    guest, token = guests.create_guest(db, name="Sofi", can_lists=True)
    assert len(token) >= 32 and guest.token_hash != token
    assert anonymous_client.get(f"/g/{token}?token=SECRET&code=CODE&state=STATE", follow_redirects=False).status_code == 303
    old_cookie = anonymous_client.cookies.get(COOKIE_NAME)
    for path in ("/plata", "/cuerpo", "/dia", "/invitados"):
        assert anonymous_client.get(path, follow_redirects=False).headers["location"] == "/super"
    rotated = guests.rotate_token(db, guest.id)
    assert anonymous_client.get("/super", follow_redirects=False).headers["location"] == "/login"
    assert security.session_identity(db, old_cookie) is None
    anonymous_client.get(f"/g/{rotated}")
    guests.revoke(db, guest.id)
    assert anonymous_client.get("/super", follow_redirects=False).headers["location"] == "/login"
    expired, expired_token = guests.create_guest(db, name="Vencido", can_lists=True, expires_at=now() - dt.timedelta(seconds=1))
    assert "ya no funciona" in anonymous_client.get(f"/g/{expired_token}").text
    assert guests.active(db, expired.id) is None
    assert token not in caplog.text and rotated not in caplog.text and expired_token not in caplog.text
    assert all(value not in caplog.text for value in ("SECRET", "CODE", "STATE"))
    assert "/g/***" in caplog.text
    assert "guest_link_rotated" in caplog.text and "guest_link_revoked" in caplog.text


def test_guest_rate_limit(anonymous_client):
    for _ in range(20):
        assert anonymous_client.get("/g/invalid").status_code == 200
    assert anonymous_client.get("/g/invalid").status_code == 429


def test_no_credentials_in_logs(anonymous_client, owner, caplog):
    caplog.set_level(logging.INFO, logger="mentor")
    login(anonymous_client)
    cookie = anonymous_client.cookies.get(COOKIE_NAME)
    anonymous_client.post("/logout", headers={"Authorization": "Bearer SHOULD-NOT-APPEAR"})
    assert PASSWORD not in caplog.text and cookie not in caplog.text and "SHOULD-NOT-APPEAR" not in caplog.text
    assert "login_ok" in caplog.text and "logout" in caplog.text
