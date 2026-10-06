"""Router registration. Each module exposes a ``router``; dev routes exist only outside production."""

from __future__ import annotations

from fastapi import FastAPI

from app.core import config


def register_routers(app: FastAPI) -> None:
    # Imported lazily so the app factory can be created before every router exists.
    import importlib

    modules = ["session", "meta", "overview", "payments", "attempts", "payment_health", "payouts", "customers", "disputes", "reports", "settings"]
    if config.is_development():
        modules.insert(0, "dev")
    for name in modules:
        try:
            module = importlib.import_module(f"app.api.{name}")
        except ModuleNotFoundError as exc:
            if exc.name == f"app.api.{name}":
                continue
            raise
        app.include_router(module.router)
