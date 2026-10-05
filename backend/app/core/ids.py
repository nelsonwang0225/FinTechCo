"""Prefixed identifiers: ``<prefix>_`` plus 14 lowercase base-32 characters.

Seeded rows draw their ids from the seed's RNG so they are stable across
resets; runtime writes use ``secrets``.
"""

from __future__ import annotations

import random
import secrets

ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"
LENGTH = 14

PREFIXES: dict[str, str] = {
    "merchant": "mer",
    "location": "loc",
    "user": "usr",
    "membership": "mem",
    "customer": "cus",
    "payment": "pay",
    "attempt": "att",
    "refund": "ref",
    "payout": "po",
    "movement": "bm",
    "dispute": "dp",
    "note_event": "evt",
}


def new_id(kind: str, rng: random.Random | None = None) -> str:
    prefix = PREFIXES[kind]
    if rng is None:
        body = "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))
    else:
        body = "".join(rng.choice(ALPHABET) for _ in range(LENGTH))
    return f"{prefix}_{body}"


def looks_like(kind: str, value: str) -> bool:
    prefix = PREFIXES[kind] + "_"
    return value.startswith(prefix) and len(value) == len(prefix) + LENGTH
