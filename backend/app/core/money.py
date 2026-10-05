"""Integer-cent money helpers. No floats anywhere."""

from __future__ import annotations

CURRENCY = "USD"

# Processing fee schedule: basis points plus a fixed cent component.
FEE_SCHEDULE: dict[str, tuple[int, int]] = {
    "website": (290, 30),
    "mobile_app": (290, 30),
    "in_store": (270, 5),
}


def fee_cents(amount_cents: int, channel: str) -> int:
    """Positive fee for a collected amount: bps share rounded half-up, plus the fixed part."""
    if amount_cents <= 0:
        raise ValueError("amount must be positive")
    bps, fixed = FEE_SCHEDULE[channel]
    return (amount_cents * bps + 5000) // 10000 + fixed


def format_usd(cents: int, *, symbol: bool = False) -> str:
    """'1,234.56' or '-48.00' from integer cents, never via floats."""
    sign = "-" if cents < 0 else ""
    dollars, rem = divmod(abs(cents), 100)
    body = f"{dollars:,}.{rem:02d}"
    return f"{sign}{'$' if symbol else ''}{body}"


def parse_usd(text: str) -> int:
    """Parse '1,234.5' / '$12' / '-3.07' into integer cents without floats."""
    raw = text.strip().replace(",", "").replace("$", "")
    if not raw:
        raise ValueError("empty amount")
    negative = raw.startswith("-")
    if negative:
        raw = raw[1:]
    if "." in raw:
        whole, frac = raw.split(".", 1)
        if len(frac) > 2 or not frac.isdigit():
            raise ValueError(f"invalid amount {text!r}")
        frac = (frac + "00")[:2]
    else:
        whole, frac = raw, "00"
    if not whole.isdigit() and whole != "":
        raise ValueError(f"invalid amount {text!r}")
    cents = int(whole or "0") * 100 + int(frac)
    return -cents if negative else cents
