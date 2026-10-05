"""Seed parameters. Everything here is fictional and synthetic.

The reporting clock (AS_OF) and the 30-day window are constants; moving the
demo date means changing AS_OF and reseeding. Parameter names are plain data
names on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from app.core.tz import chicago_local

RNG_SEED = 20261009

# The reporting clock written to seed_meta.as_of: Monday 2026-10-05 09:12 America/Chicago.
AS_OF: datetime = chicago_local(2026, 10, 5, 9, 12)
# Thirty complete Chicago days before the as-of date, plus the live partial day.
WINDOW_START: datetime = chicago_local(2026, 9, 5, 0, 0)
WINDOW_START_DAY = date(2026, 9, 5)
AS_OF_DAY = date(2026, 10, 5)

HOLIDAYS: frozenset[date] = frozenset({date(2026, 9, 7)})  # Labor Day

# Minimum distance of any attempt from a Chicago midnight, so period totals never straddle a day.
MIDNIGHT_GUARD_SECONDS = 90
# Settlement: collected funds become available two days after posting.
AVAILABILITY_DELAY_HOURS = 48
DISPUTE_FEE_CENTS = 1500


@dataclass(frozen=True)
class LocationSpec:
    name: str
    address_line: str
    city: str
    state: str
    open_hour: int
    close_hour: int
    closed_weekdays: frozenset[int] = frozenset()  # Monday=0
    closed_days: frozenset[date] = frozenset()


@dataclass(frozen=True)
class CatalogItem:
    name: str
    price_cents: int


@dataclass(frozen=True)
class MerchantSpec:
    slug: str
    name: str
    legal_name: str
    support_email: str
    industry: str
    payout_schedule: str
    destination_label: str
    destination_last4: str
    destination_kind: str
    order_prefix: str
    customer_prefix: str
    tax_bps: int
    locations: tuple[LocationSpec, ...]
    catalog: tuple[CatalogItem, ...]
    items_per_order: tuple[int, ...]  # weights for 1..n items
    channel_share: dict[str, float]
    daily_payments: float  # average payments per day across channels
    weekday_weights: dict[str, tuple[float, ...]]  # per channel, Monday..Sunday
    hour_weights: dict[str, tuple[float, ...]]  # per channel, 24 entries
    wallet_share: dict[str, float]  # per channel
    named_customers: int  # size of the repeat-shopper pool
    guest_share: float
    refund_share: float
    seeded_customers: tuple[tuple[str, str], ...] = ()  # (full name, email) always present


def _hours(spec: dict[int, float]) -> tuple[float, ...]:
    return tuple(spec.get(h, 0.0) for h in range(24))


ONLINE_HOURS = _hours(
    {
        0: 0.15, 1: 0.08, 2: 0.05, 3: 0.03, 4: 0.03, 5: 0.06, 6: 0.18, 7: 0.4, 8: 0.65, 9: 0.85, 10: 1.0,
        11: 1.25, 12: 1.3, 13: 1.2, 14: 1.0, 15: 0.95, 16: 0.9, 17: 0.95, 18: 1.05, 19: 1.3, 20: 1.4,
        21: 1.25, 22: 0.8, 23: 0.4,
    }
)
STORE_HOURS = _hours({10: 0.6, 11: 0.9, 12: 1.2, 13: 1.1, 14: 1.0, 15: 1.0, 16: 1.1, 17: 1.2, 18: 1.0, 19: 0.6})
COFFEE_HOURS = _hours({6: 0.5, 7: 1.4, 8: 1.6, 9: 1.2, 10: 0.9, 11: 0.8, 12: 1.0, 13: 0.8, 14: 0.7, 15: 0.6, 16: 0.5, 17: 0.3})
COFFEE_APP_HOURS = _hours({6: 0.6, 7: 1.5, 8: 1.4, 9: 0.8, 10: 0.4, 11: 0.3, 12: 0.6, 13: 0.4, 14: 0.3, 15: 0.3, 16: 0.2})

ALDER_LOOM = MerchantSpec(
    slug="alder-loom",
    name="Alder & Loom",
    legal_name="Alder & Loom Home LLC",
    support_email="support@alder-loom.example.com",
    industry="Homeware retail",
    payout_schedule="daily",
    destination_label="Operating account",
    destination_last4="4821",
    destination_kind="external bank account",
    order_prefix="AL",
    customer_prefix="AL-C",
    tax_bps=1025,
    locations=(
        LocationSpec("Lincoln Park", "2140 N Halsted St", "Chicago", "IL", 10, 20, closed_days=HOLIDAYS),
        LocationSpec("Fulton Market", "815 W Fulton Market", "Chicago", "IL", 10, 20, closed_days=HOLIDAYS),
    ),
    catalog=(
        CatalogItem("Linen duvet cover, oat", 24800),
        CatalogItem("Stoneware mug set of four", 6400),
        CatalogItem("Walnut side table", 89000),
        CatalogItem("Wool throw, charcoal", 15800),
        CatalogItem("Ceramic table lamp", 21500),
        CatalogItem("Oak serving board", 5600),
        CatalogItem("Hand-loomed runner rug", 32000),
        CatalogItem("Brass picture frame", 3800),
        CatalogItem("Cotton percale sheet set", 17900),
        CatalogItem("Glass carafe", 4200),
        CatalogItem("Linen napkins, set of six", 4800),
        CatalogItem("Teak bath mat", 9800),
        CatalogItem("Cast iron dutch oven", 26500),
        CatalogItem("Alpaca pillow cover", 8900),
        CatalogItem("Marble bookends", 7200),
        CatalogItem("Rattan storage basket", 6900),
        CatalogItem("Beeswax taper candles", 2400),
        CatalogItem("Bouclé accent chair", 140000),
        CatalogItem("Dining chair, ash", 42000),
        CatalogItem("Stoneware vase", 5400),
        CatalogItem("Linen apron", 4600),
        CatalogItem("Wool blend area rug", 68000),
        CatalogItem("Copper watering can", 5800),
        CatalogItem("Birch coat rack", 18900),
        CatalogItem("Ceramic planter, large", 7800),
        CatalogItem("Down alternative duvet", 19900),
        CatalogItem("Woven wall hanging", 12800),
        CatalogItem("Oak bedside table", 36000),
        CatalogItem("Linen curtain panel", 9900),
        CatalogItem("Kitchen towel set", 2800),
        CatalogItem("Hand soap trio", 3600),
        CatalogItem("Walnut cutting board", 8400),
        CatalogItem("Felt desk mat", 4400),
        CatalogItem("Terracotta pitcher", 5200),
        CatalogItem("Boucle ottoman", 46000),
        CatalogItem("Linen tablecloth", 11800),
        CatalogItem("Steel shelving unit", 52000),
        CatalogItem("Cedar hangers, set of ten", 3200),
        CatalogItem("Jute doormat", 3400),
        CatalogItem("Quilted coverlet", 22900),
    ),
    items_per_order=(0.55, 0.28, 0.12, 0.05),
    channel_share={"website": 0.50, "mobile_app": 0.30, "in_store": 0.20},
    daily_payments=88.0,
    weekday_weights={
        "website": (1.0, 1.0, 1.05, 1.1, 1.0, 0.85, 0.7),
        "mobile_app": (1.0, 1.0, 1.0, 1.05, 1.05, 0.95, 0.85),
        "in_store": (0.8, 0.8, 0.85, 0.9, 1.1, 1.4, 1.0),
    },
    hour_weights={"website": ONLINE_HOURS, "mobile_app": ONLINE_HOURS, "in_store": STORE_HOURS},
    wallet_share={"website": 0.18, "mobile_app": 0.35, "in_store": 0.12},
    named_customers=640,
    guest_share=0.15,
    refund_share=0.045,
    seeded_customers=(("Avery Stone", "avery.stone@example.com"), ("Morgan Lee", "morgan.lee@example.com"), ("Taylor Reed", "taylor.reed@example.com")),
)

JUNIPER_TRAIL = MerchantSpec(
    slug="juniper-trail",
    name="Juniper Trail Outfitters",
    legal_name="Juniper Trail Outfitters, Inc.",
    support_email="hello@junipertrail.example.com",
    industry="Outdoor gear retail",
    payout_schedule="weekly_friday",
    destination_label="Operating account",
    destination_last4="2210",
    destination_kind="external bank account",
    order_prefix="JT",
    customer_prefix="JT-C",
    tax_bps=885,
    locations=(LocationSpec("Flagship", "1640 Pearl St", "Boulder", "CO", 10, 19, closed_days=HOLIDAYS),),
    catalog=(
        CatalogItem("Trail running shoes", 14500),
        CatalogItem("Down jacket, 800 fill", 28900),
        CatalogItem("Two-person tent", 42000),
        CatalogItem("Merino base layer", 8900),
        CatalogItem("Hydration pack 2L", 9800),
        CatalogItem("Trekking poles, pair", 12900),
        CatalogItem("Headlamp 400 lm", 4900),
        CatalogItem("Sleeping bag 20F", 24900),
        CatalogItem("Rain shell", 19900),
        CatalogItem("Hiking socks, 3 pack", 3600),
        CatalogItem("Climbing harness", 7900),
        CatalogItem("Insulated bottle 32oz", 4200),
        CatalogItem("Daypack 28L", 13900),
        CatalogItem("Camp stove", 8900),
        CatalogItem("Sun hoodie", 6900),
        CatalogItem("Approach shoes", 15900),
        CatalogItem("Trail map set", 2400),
        CatalogItem("Fleece pullover", 9900),
        CatalogItem("Bear canister", 7900),
        CatalogItem("Gaiters", 5900),
        CatalogItem("Expedition duffel 90L", 18900),
        CatalogItem("Chalk bag", 2900),
        CatalogItem("Camp chair", 7900),
        CatalogItem("Ski goggles", 16900),
        CatalogItem("Avalanche beacon", 38900),
    ),
    items_per_order=(0.6, 0.3, 0.1),
    channel_share={"website": 0.65, "in_store": 0.35},
    daily_payments=20.0,
    weekday_weights={
        "website": (1.0, 1.0, 1.0, 1.05, 1.05, 0.9, 0.8),
        "in_store": (0.7, 0.7, 0.75, 0.85, 1.1, 1.5, 1.2),
    },
    hour_weights={"website": ONLINE_HOURS, "in_store": STORE_HOURS},
    wallet_share={"website": 0.2, "in_store": 0.1},
    named_customers=210,
    guest_share=0.2,
    refund_share=0.05,
    seeded_customers=(("Avery Stone", "avery.stone@example.com"),),
)

COPPER_FINCH = MerchantSpec(
    slug="copper-finch",
    name="Copper Finch Coffee",
    legal_name="Copper Finch Coffee Co.",
    support_email="team@copperfinch.example.com",
    industry="Coffee shops",
    payout_schedule="weekly_monday",
    destination_label="Business checking",
    destination_last4="7730",
    destination_kind="external bank account",
    order_prefix="CF",
    customer_prefix="CF-C",
    tax_bps=1025,
    locations=(
        LocationSpec("Logan Square", "2600 N Milwaukee Ave", "Chicago", "IL", 6, 18, closed_days=frozenset({date(2026, 9, 20)}) | HOLIDAYS),
        LocationSpec("Andersonville", "5200 N Clark St", "Chicago", "IL", 6, 18, closed_weekdays=frozenset({6}), closed_days=HOLIDAYS),
    ),
    catalog=(
        CatalogItem("Drip coffee 12oz", 375),
        CatalogItem("Latte 12oz", 525),
        CatalogItem("Cappuccino", 500),
        CatalogItem("Cold brew 16oz", 550),
        CatalogItem("Espresso", 350),
        CatalogItem("Mocha 16oz", 625),
        CatalogItem("Chai latte", 550),
        CatalogItem("Matcha latte", 600),
        CatalogItem("Croissant", 425),
        CatalogItem("Blueberry muffin", 400),
        CatalogItem("Breakfast sandwich", 850),
        CatalogItem("Avocado toast", 950),
        CatalogItem("Granola bowl", 900),
        CatalogItem("Whole bean bag 12oz", 1800),
        CatalogItem("Whole bean bag 2lb", 4200),
        CatalogItem("Ceramic travel mug", 2800),
        CatalogItem("Pour-over kit", 3900),
        CatalogItem("Cookie", 325),
    ),
    items_per_order=(0.5, 0.35, 0.15),
    channel_share={"in_store": 0.94, "mobile_app": 0.04, "website": 0.02},
    daily_payments=30.0,
    weekday_weights={
        "in_store": (1.0, 1.0, 1.0, 1.0, 1.05, 0.8, 0.45),
        "mobile_app": (1.1, 1.1, 1.1, 1.1, 1.0, 0.4, 0.2),
        "website": (1.0, 1.0, 1.0, 1.0, 1.0, 0.6, 0.6),
    },
    hour_weights={"in_store": COFFEE_HOURS, "mobile_app": COFFEE_APP_HOURS, "website": ONLINE_HOURS},
    wallet_share={"in_store": 0.3, "mobile_app": 0.6, "website": 0.2},
    named_customers=290,
    guest_share=0.25,
    refund_share=0.012,
)

MERCHANTS: tuple[MerchantSpec, ...] = (ALDER_LOOM, JUNIPER_TRAIL, COPPER_FINCH)


@dataclass(frozen=True)
class UserSpec:
    full_name: str
    email: str
    title: str
    memberships: tuple[tuple[str, str], ...]  # (merchant slug, role)


USERS: tuple[UserSpec, ...] = (
    UserSpec("Maya Chen", "maya.chen@alder-loom.example.com", "Operations Manager", (("alder-loom", "operations_manager"),)),
    UserSpec("Daniel Brooks", "daniel.brooks@alder-loom.example.com", "Finance Manager", (("alder-loom", "finance_manager"),)),
    UserSpec("Jordan Ellis", "jordan.ellis@alder-loom.example.com", "Business Administrator", (("alder-loom", "business_admin"),)),
    UserSpec("Priya Shah", "priya.shah@junipertrail.example.com", "Operations Manager", (("juniper-trail", "operations_manager"),)),
    UserSpec("Sam Okafor", "sam.okafor@example.com", "Analyst", (("alder-loom", "read_only_analyst"), ("copper-finch", "read_only_analyst"))),
)

FIRST_NAMES: tuple[str, ...] = (
    "Avery", "Morgan", "Taylor", "Jordan", "Riley", "Casey", "Quinn", "Rowan", "Emerson", "Hayden",
    "Elena", "Marcus", "Priyanka", "Noah", "Sofia", "Liam", "Isabel", "Owen", "Grace", "Mateo",
    "Hannah", "Caleb", "Nadia", "Elijah", "Leah", "Theo", "Amara", "Julian", "Clara", "Felix",
    "Maren", "Dev", "Ingrid", "Tomas", "Yara", "Lucas", "Imani", "Henry", "Zoe", "Arjun",
    "Beatriz", "Samuel", "Nora", "Idris", "Celeste", "Victor", "Lena", "Omar", "Ruth", "Adrian",
    "Wren", "Bennett", "Thea", "Miles", "Paloma", "Jonah", "Freya", "Ezra", "Simone", "Kai",
)
LAST_NAMES: tuple[str, ...] = (
    "Stone", "Lee", "Reed", "Alvarez", "Nakamura", "Okafor", "Lindqvist", "Patel", "Brennan", "Castillo",
    "Hughes", "Moreau", "Kowalski", "Haddad", "Fischer", "Mbeki", "Delgado", "Novak", "Ferreira", "Walsh",
    "Ibrahim", "Sato", "Jensen", "Varga", "Oduya", "Marino", "Chandra", "Kim", "Bauer", "Quintero",
    "Sullivan", "Petrov", "Nair", "Lambert", "Osei", "Romero", "Takahashi", "Weber", "Holm", "Adeyemi",
    "Garza", "Novotny", "Mensah", "Doyle", "Rahman", "Serrano", "Vance", "Byrne", "Larsen", "Achebe",
    "Whitaker", "Ortega", "Blum", "Nwosu", "Pierce", "Kaur", "Tanaka", "Abbott", "Rios", "Hale",
)
STREETS: tuple[str, ...] = ("Maple", "Harbor", "Cedar", "Willow", "Juniper", "Birch", "Elm", "Prairie", "Ridge", "Lake")

CARD_BRANDS: tuple[tuple[str, float], ...] = (("visa", 0.50), ("mastercard", 0.32), ("amex", 0.13), ("discover", 0.05))
WALLET_TYPES: tuple[tuple[str, float], ...] = (("apple_pay", 0.65), ("google_pay", 0.35))

# Human labels for recorded failure codes.
DECLINE_CODES: dict[str, str] = {
    "insufficient_funds": "Insufficient funds",
    "do_not_honor": "Do not honor",
    "incorrect_cvc": "Incorrect security code",
    "expired_card": "Expired card",
    "authentication_failed": "Authentication failed",
    "card_velocity_exceeded": "Card velocity exceeded",
    "fraud_suspected": "Suspected fraud",
    "issuer_unavailable": "Issuer unavailable",
    "processing_error": "Processing error",
    "lost_or_stolen": "Card reported lost or stolen",
    "incorrect_number": "Incorrect card number",
}
DECLINE_CODE_WEIGHTS: dict[str, float] = {
    "insufficient_funds": 0.30,
    "do_not_honor": 0.22,
    "incorrect_cvc": 0.12,
    "expired_card": 0.09,
    "authentication_failed": 0.08,
    "card_velocity_exceeded": 0.05,
    "fraud_suspected": 0.04,
    "processing_error": 0.04,
    "lost_or_stolen": 0.02,
    "issuer_unavailable": 0.02,
    "incorrect_number": 0.02,
}
# Codes where a shopper plausibly retries with the same card after fixing the entry.
RETRY_SAME_CARD_CODES: frozenset[str] = frozenset({"incorrect_cvc", "expired_card", "incorrect_number", "authentication_failed", "issuer_unavailable", "processing_error"})

# First-attempt outcome parameters per channel.
FIRST_ATTEMPT_FAILURE_SHARE: dict[str, float] = {"website": 0.075, "mobile_app": 0.075, "in_store": 0.078}
RETRY_PROBABILITY = 0.70
RETRY_FAILURE_SHARE = 0.15
SECOND_RETRY_PROBABILITY = 0.30
RETRY_DELAY_SECONDS = (60, 1800)
ATTEMPT_DURATION_SECONDS = (1, 4)

# Live-looking activity just before the clock: online attempts that have not completed yet.
PENDING_WINDOW_MINUTES = 40
PENDING_SHARE_IN_WINDOW = 0.35
# Online payments still in flight at the clock, told exactly so the live state is always visible.
PENDING_PAYMENTS: tuple[tuple[str, str, datetime], ...] = (
    ("alder-loom", "website", chicago_local(2026, 10, 5, 9, 4, 21)),
    ("alder-loom", "mobile_app", chicago_local(2026, 10, 5, 8, 49, 7)),
    ("juniper-trail", "website", chicago_local(2026, 10, 5, 8, 57, 33)),
)


@dataclass(frozen=True)
class WindowOverride:
    """Parameter override for one merchant channel between two instants."""

    merchant_slug: str
    channel: str
    start: datetime
    end: datetime
    failure_share: float
    code_weights: dict[str, float]
    volume_multiplier: float = 1.0
    retry_probability: float = RETRY_PROBABILITY
    retry_failure_share: float = RETRY_FAILURE_SHARE
    retry_delay_seconds: tuple[int, int] = RETRY_DELAY_SECONDS


WINDOW_OVERRIDES: tuple[WindowOverride, ...] = (
    WindowOverride(
        merchant_slug="alder-loom",
        channel="mobile_app",
        start=chicago_local(2026, 10, 1, 15, 0),
        end=chicago_local(2026, 10, 2, 11, 0),
        failure_share=0.84,
        code_weights={"issuer_unavailable": 0.86, "processing_error": 0.06, "insufficient_funds": 0.04, "do_not_honor": 0.04},
        volume_multiplier=1.8,
        retry_probability=0.85,
        retry_failure_share=0.10,
        retry_delay_seconds=(240, 3300),
    ),
    # Labor Day week runs quieter online for the homeware retailer.
    WindowOverride(
        merchant_slug="alder-loom",
        channel="website",
        start=chicago_local(2026, 9, 7, 0, 0),
        end=chicago_local(2026, 9, 10, 0, 0),
        failure_share=FIRST_ATTEMPT_FAILURE_SHARE["website"],
        code_weights=DECLINE_CODE_WEIGHTS,
        volume_multiplier=0.75,
    ),
)

REFUND_REASON_WEIGHTS: dict[str, float] = {
    "requested_by_customer": 0.38,
    "damaged_in_transit": 0.16,
    "wrong_item": 0.14,
    "price_adjustment": 0.14,
    "returned_in_store": 0.12,
    "duplicate": 0.06,
}
REFUND_FULL_SHARE = 0.70
REFUND_DELAY_DAYS = (1, 12)
PENDING_REFUNDS_PER_MERCHANT: dict[str, int] = {"alder-loom": 2, "juniper-trail": 1, "copper-finch": 0}


@dataclass(frozen=True)
class DisputeSpec:
    merchant_slug: str
    status: str
    reason: str
    opened_days_before_as_of: int
    due_days_after_open: int
    responded_days_after_open: int | None = None
    resolved_days_after_open: int | None = None
    min_amount_cents: int = 4000
    customer_email: str | None = None


DISPUTES: tuple[DisputeSpec, ...] = (
    DisputeSpec("alder-loom", "needs_response", "product_not_received", 12, 14, customer_email="morgan.lee@example.com"),
    DisputeSpec("alder-loom", "needs_response", "fraudulent", 5, 14),
    DisputeSpec("alder-loom", "under_review", "product_unacceptable", 18, 14, responded_days_after_open=6),
    DisputeSpec("alder-loom", "won", "duplicate", 26, 10, responded_days_after_open=3, resolved_days_after_open=17),
    DisputeSpec("alder-loom", "lost", "credit_not_processed", 24, 10, resolved_days_after_open=14),
    DisputeSpec("juniper-trail", "needs_response", "product_not_received", 10, 14),
    DisputeSpec("juniper-trail", "under_review", "fraudulent", 16, 14, responded_days_after_open=5),
    DisputeSpec("copper-finch", "lost", "fraudulent", 22, 10, resolved_days_after_open=12, min_amount_cents=1500),
)


@dataclass(frozen=True)
class AdjustmentSpec:
    merchant_slug: str
    amount_cents: int
    description: str
    day: date
    hour: int


ADJUSTMENTS: tuple[AdjustmentSpec, ...] = (
    AdjustmentSpec("alder-loom", 1250, "Fee correction for September 9 settlement", date(2026, 9, 11), 7),
    AdjustmentSpec("alder-loom", -3000, "Chargeback handling adjustment", date(2026, 9, 24), 7),
    AdjustmentSpec("juniper-trail", 850, "Fee correction for September 18 settlement", date(2026, 9, 22), 7),
    AdjustmentSpec("copper-finch", 420, "Fee correction for September 14 settlement", date(2026, 9, 16), 7),
)

# Internal investigation notes seeded so timelines and the activity feed are not empty.
NOTE_TEXTS: tuple[str, ...] = (
    "Customer emailed about a duplicate charge. Confirmed a single capture; the first attempt was declined and never settled. Replied with the receipt.",
    "Shopper reports the order arrived with a cracked lid. Refund of the damaged item approved by store lead; remainder of the order kept.",
    "Verified shipping address against the order before releasing the replacement. No further action.",
    "Bank asked for the original receipt and delivery confirmation. Gathering carrier tracking before the deadline.",
    "Customer confirmed the second card is theirs; the first was an old card still saved in the app.",
    "Price adjustment honored after the item went on sale two days later. Partial refund issued by Daniel.",
    "Two attempts on the same order within three minutes; second one settled. Nothing to reconcile.",
    "Spoke with the Fulton Market team: the in-store return was processed against the original payment.",
    "Order flagged by the customer as not received. Carrier shows delivered to the front desk; shared the photo.",
    "Reviewed with finance: fee on this payment matches the in-store schedule.",
    "Customer asked whether a refund had posted. Pending at the processor; told them to allow two business days.",
    "Flagship reports the shopper picked up in person after the online order; no shipping charge to refund.",
)

# Rough target for seeded notes (payments) and dispute notes.
SEEDED_PAYMENT_NOTES: dict[str, int] = {"alder-loom": 7, "juniper-trail": 2, "copper-finch": 1}
