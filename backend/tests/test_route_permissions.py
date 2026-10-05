"""Every route is guarded, every guard matches the role matrix, and every JSON route declares its shape."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.auth.permissions import PERMISSIONS, ROLE_PERMISSIONS, ROLES, has_permission, permissions_for
from tests.conftest import PERSONA_ROLES, PERSONAS, Ids, api_routes, route_permission

# Routes that intentionally do not carry require(): liveness, development personas, and the session itself.
UNGUARDED = {("GET", "/api/ping"), ("GET", "/api/dev/personas"), ("POST", "/api/dev/session"), ("GET", "/api/session"), ("DELETE", "/api/session")}

MATRIX_PERSONAS = ("maya", "daniel", "jordan", "priya", "sam")


def test_role_matrix_is_the_approved_one() -> None:
    assert ROLES == ("business_admin", "operations_manager", "finance_manager", "read_only_analyst")
    assert set(ROLE_PERMISSIONS) == set(ROLES)
    for role, granted in ROLE_PERMISSIONS.items():
        assert granted <= set(PERMISSIONS), role
    table = {
        "overview:read": {"business_admin", "operations_manager", "finance_manager", "read_only_analyst"},
        "payments:read": {"business_admin", "operations_manager", "finance_manager", "read_only_analyst"},
        "customers:read": {"business_admin", "operations_manager", "read_only_analyst"},
        "disputes:read": {"business_admin", "operations_manager", "finance_manager", "read_only_analyst"},
        "payouts:read": {"business_admin", "finance_manager", "read_only_analyst"},
        "notes:write": {"business_admin", "operations_manager"},
        "reports:operational": {"business_admin", "operations_manager", "finance_manager"},
        "reports:financial": {"finance_manager"},
        "settings:read": {"business_admin"},
    }
    for permission, roles in table.items():
        assert {r for r in ROLES if has_permission(r, permission)} == roles, permission
    assert permissions_for("read_only_analyst") == ["overview:read", "payments:read", "customers:read", "disputes:read", "payouts:read"]


def test_every_api_route_is_guarded_or_allowlisted(app: FastAPI) -> None:
    for route in api_routes(app):
        for method in route.methods:
            key = (method, route.path)
            permission = route_permission(route)
            if key in UNGUARDED:
                assert permission is None, key
            else:
                assert permission in PERMISSIONS, f"{key} lacks require(<permission>)"


def test_every_json_route_declares_a_response_model(app: FastAPI) -> None:
    for route in api_routes(app):
        if route.path == "/api/ping" or "DELETE" in route.methods:
            continue
        if route.response_model is None:
            # CSV endpoints stream text and are the documented exception.
            assert not issubclass(route.response_class, JSONResponse), route.path
        else:
            assert getattr(route.response_model, "model_config", {}).get("extra") == "forbid", route.path


def test_every_path_parameter_has_a_sample_id(app: FastAPI, ids: Ids) -> None:
    for route in api_routes(app):
        for name in route.param_convertors:
            assert name in ids.samples["alder-loom"], f"add {name} to the sample ids in conftest"
            assert ids.samples["alder-loom"][name], name


@pytest.mark.parametrize("persona", MATRIX_PERSONAS)
def test_role_times_route_matrix(app: FastAPI, client_as, ids: Ids, persona: str) -> None:
    c = client_as(persona)
    role = PERSONA_ROLES[persona]
    slug = PERSONAS[persona][1]
    checked = 0
    for route in api_routes(app):
        permission = route_permission(route)
        if permission is None:
            continue
        path = route.path
        for name, value in ids.samples[slug].items():
            path = path.replace("{" + name + "}", value)
        for method in route.methods:
            r = c.request(method, path, json={} if method in ("POST", "PUT", "PATCH") else None)
            if has_permission(role, permission):
                assert r.status_code != 403, (persona, method, path, r.text)
            else:
                assert r.status_code == 403, (persona, method, path, r.status_code)
                assert r.json()["error"]["code"] == "forbidden"
            checked += 1
    assert checked > 0
