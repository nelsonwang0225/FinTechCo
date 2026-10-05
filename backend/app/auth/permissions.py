"""The role matrix and the ``require(permission)`` dependency.

Every ``/api/*`` route except ping, the development routes and GET/DELETE
``/api/session`` depends on ``require("<permission>")``. The check order is
401 (no valid session), then 403 (role lacks the permission), then the route
runs and answers 404 for ids outside the principal's merchant. Change the
matrix only after asking.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends

from app.auth.session import Principal, current_principal
from app.main import ApiError

ROLES: tuple[str, ...] = ("business_admin", "operations_manager", "finance_manager", "read_only_analyst")

PERMISSIONS: tuple[str, ...] = (
    "overview:read",
    "payments:read",
    "customers:read",
    "disputes:read",
    "payouts:read",
    "notes:write",
    "reports:operational",
    "reports:financial",
    "settings:read",
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "business_admin": frozenset({"overview:read", "payments:read", "customers:read", "disputes:read", "payouts:read", "notes:write",
                                 "reports:operational", "settings:read"}),
    "operations_manager": frozenset({"overview:read", "payments:read", "customers:read", "disputes:read", "notes:write", "reports:operational"}),
    "finance_manager": frozenset({"overview:read", "payments:read", "disputes:read", "payouts:read", "reports:operational", "reports:financial"}),
    "read_only_analyst": frozenset({"overview:read", "payments:read", "customers:read", "disputes:read", "payouts:read"}),
}

ROLE_LABELS: dict[str, str] = {
    "business_admin": "Business admin",
    "operations_manager": "Operations manager",
    "finance_manager": "Finance manager",
    "read_only_analyst": "Read-only analyst",
}


def permissions_for(role: str) -> list[str]:
    granted = ROLE_PERMISSIONS[role]
    return [p for p in PERMISSIONS if p in granted]


def has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS[role]


def require(permission: str) -> Callable[..., Principal]:
    """Dependency factory: 401 without a valid session, 403 without the permission, else the Principal."""
    if permission not in PERMISSIONS:
        raise ValueError(f"unknown permission {permission!r}")

    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if not has_permission(principal.role, permission):
            raise ApiError(403, "forbidden", f"Your role does not include {permission}.")
        return principal

    dependency.permission = permission  # type: ignore[attr-defined]  # read by the route-introspection test
    dependency.__name__ = f"require_{permission.replace(':', '_')}"
    return dependency
