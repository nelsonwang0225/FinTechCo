"""Sessions: the cookie, who it resolves to, and what a forged request gets."""

from __future__ import annotations

from app.core import clock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import session as session_mod
from app.auth.permissions import ROLE_PERMISSIONS, permissions_for
from app.main import create_app
from tests.conftest import PERSONA_ROLES, PERSONAS, Ids, api_routes, route_permission


def protected_requests(app: FastAPI, ids: Ids) -> list[tuple[str, str]]:
    out = []
    for route in api_routes(app):
        if route_permission(route) is None:
            continue
        path = route.path
        for name, value in ids.samples["alder-loom"].items():
            path = path.replace("{" + name + "}", value)
        for method in route.methods:
            out.append((method, path))
    return out


def test_every_protected_route_is_401_without_a_cookie(client: TestClient, app: FastAPI, ids: Ids) -> None:
    requests = protected_requests(app, ids)
    assert requests, "there should be protected routes"
    for method, path in requests:
        r = client.request(method, path, json={} if method in ("POST", "PUT", "PATCH") else None)
        assert r.status_code == 401, (method, path, r.text)
        assert r.json() == {"error": {"code": "unauthenticated", "message": "Sign in to continue."}}


@pytest.mark.parametrize("cookie", ["", "garbage", "abc.def", "eyJ9.sig", "a.b.c"])
def test_garbage_cookies_are_401(client: TestClient, cookie: str) -> None:
    client.cookies.set(session_mod.COOKIE_NAME, cookie)
    assert client.get("/api/session").status_code == 401


def test_tampered_signature_is_401(client: TestClient, ids: Ids) -> None:
    membership_id = ids.memberships[PERSONAS["maya"]]
    now = int(clock.wall_now().timestamp())
    token = session_mod.encode_token(membership_id, now, now + 3600)
    payload, signature = token.split(".")
    bad = signature[:-1] + ("A" if signature[-1] != "A" else "B")
    client.cookies.set(session_mod.COOKIE_NAME, f"{payload}.{bad}")
    assert client.get("/api/session").status_code == 401


def test_expired_token_is_401(client: TestClient, ids: Ids) -> None:
    membership_id = ids.memberships[PERSONAS["maya"]]
    now = int(clock.wall_now().timestamp())
    client.cookies.set(session_mod.COOKIE_NAME, session_mod.encode_token(membership_id, now - 7200, now - 1))
    assert client.get("/api/session").status_code == 401


def test_valid_token_for_unknown_membership_is_401(client: TestClient) -> None:
    now = int(clock.wall_now().timestamp())
    client.cookies.set(session_mod.COOKIE_NAME, session_mod.encode_token("mem_aaaaaaaaaaaaaa", now, now + 3600))
    assert client.get("/api/session").status_code == 401


def test_cookie_only_carries_a_membership_id(client_as, ids: Ids) -> None:
    c = client_as("maya")
    token = c.cookies.get(session_mod.COOKIE_NAME)
    assert token
    assert session_mod.decode_token(token) == ids.memberships[PERSONAS["maya"]]
    import base64
    import json

    payload = token.split(".")[0]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    assert set(claims) == {"membership_id", "iat", "exp"}
    assert claims["exp"] - claims["iat"] == 12 * 3600


def test_cookie_attributes(client: TestClient, ids: Ids) -> None:
    email, slug = PERSONAS["maya"]
    r = client.post("/api/dev/session", json={"user_id": ids.users[email], "merchant_id": ids.merchants[slug]})
    header = r.headers["set-cookie"]
    assert header.startswith("ftc_session=")
    assert "HttpOnly" in header and "Path=/" in header and "Max-Age=43200" in header
    assert "samesite=lax" in header.lower()


def test_forged_user_merchant_pair_is_refused_without_a_cookie(client: TestClient, ids: Ids) -> None:
    r = client.post("/api/dev/session", json={"user_id": ids.users[PERSONAS["maya"][0]], "merchant_id": ids.merchants["juniper-trail"]})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "no_membership"
    assert "set-cookie" not in r.headers
    assert client.get("/api/session").status_code == 401


def test_unknown_user_or_merchant_is_refused(client: TestClient, ids: Ids) -> None:
    assert client.post("/api/dev/session", json={"user_id": "usr_nobody00000000", "merchant_id": ids.merchants["alder-loom"]}).status_code == 403
    assert client.post("/api/dev/session", json={"user_id": ids.users[PERSONAS["maya"][0]], "merchant_id": "mer_nobody00000000"}).status_code == 403
    r = client.post("/api/dev/session", json={"user_id": ids.users[PERSONAS["maya"][0]]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_analyst_can_sit_at_both_merchants_but_not_juniper(client_as, ids: Ids) -> None:
    alder = client_as("sam").get("/api/session").json()
    copper = client_as("sam_copper").get("/api/session").json()
    assert alder["merchant"]["slug"] == "alder-loom" and copper["merchant"]["slug"] == "copper-finch"
    assert alder["membership_id"] != copper["membership_id"]
    assert alder["user"]["id"] == copper["user"]["id"]
    assert alder["role"] == copper["role"] == "read_only_analyst"
    anon = client_as("anon")
    r = anon.post("/api/dev/session", json={"user_id": ids.users["sam.okafor@example.com"], "merchant_id": ids.merchants["juniper-trail"]})
    assert r.status_code == 403


@pytest.mark.parametrize("persona", sorted(PERSONAS))
def test_session_payload_matches_the_membership(client_as, ids: Ids, persona: str) -> None:
    email, slug = PERSONAS[persona]
    body = client_as(persona).get("/api/session").json()
    assert body["user"]["email"] == email
    assert body["merchant"]["id"] == ids.merchants[slug]
    assert body["membership_id"] == ids.memberships[(email, slug)]
    assert body["role"] == PERSONA_ROLES[persona]
    assert body["permissions"] == permissions_for(PERSONA_ROLES[persona])
    assert set(body["permissions"]) == ROLE_PERMISSIONS[PERSONA_ROLES[persona]]
    assert body["as_of"] == "2026-10-05T14:12:00Z"
    assert body["timezone"] == "America/Chicago"
    assert set(body) == {"membership_id", "user", "merchant", "role", "role_label", "permissions", "as_of", "timezone"}


def test_sign_out_clears_the_cookie(client_as) -> None:
    c = client_as("priya")
    assert c.get("/api/session").status_code == 200
    r = c.delete("/api/session")
    assert r.status_code == 204
    assert 'ftc_session=""' in r.headers["set-cookie"] or "ftc_session=;" in r.headers["set-cookie"]
    assert c.get("/api/session").status_code == 401


def test_personas_list_only_seeded_memberships(client: TestClient, ids: Ids) -> None:
    body = client.get("/api/dev/personas").json()
    seen = {(p["user_id"], g["merchant"]["id"]) for g in body["merchants"] for p in g["personas"]}
    expected = {(ids.users[email], ids.merchants[slug]) for (email, slug) in ids.memberships}
    assert seen == expected
    assert [g["merchant"]["name"] for g in body["merchants"]] == ["Alder & Loom", "Copper Finch Coffee", "Juniper Trail Outfitters"]


def test_production_removes_the_dev_router(db_copy, monkeypatch: pytest.MonkeyPatch, ids: Ids) -> None:
    monkeypatch.setenv("FINTECHCO_ENV", "production")
    prod = create_app(db_copy)
    assert not any(r.path.startswith("/api/dev") for r in api_routes(prod))
    with TestClient(prod) as c:
        assert c.get("/api/dev/personas").status_code == 404
        r = c.post("/api/dev/session", json={"user_id": ids.users[PERSONAS["maya"][0]], "merchant_id": ids.merchants["alder-loom"]})
        assert r.status_code == 404
        assert c.get("/api/ping").status_code == 200
        assert c.get("/api/session").status_code == 401
