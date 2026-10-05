"""Pure, deterministic dataset generation.

``build_dataset()`` returns plain dataclasses from one ``random.Random``
instance. No wall clock, no uuid4, no iteration over unordered collections.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.core import money
from app.core.ids import new_id
from app.core.tz import CHICAGO, UTC, chicago_local, to_iso
from app.seed import scenario as S
from app.seed.scenario import LocationSpec, MerchantSpec, WindowOverride


# --------------------------------------------------------------------------- rows


@dataclass
class MerchantRow:
    id: str
    name: str
    slug: str
    legal_name: str
    support_email: str
    industry: str
    payout_schedule: str
    destination_label: str
    destination_last4: str
    destination_kind: str
    created_at: str


@dataclass
class LocationRow:
    id: str
    merchant_id: str
    name: str
    address_line: str
    city: str
    state: str


@dataclass
class UserRow:
    id: str
    full_name: str
    email: str
    title: str
    is_active: int = 1


@dataclass
class MembershipRow:
    id: str
    user_id: str
    merchant_id: str
    role: str
    created_at: str


@dataclass
class CustomerRow:
    id: str
    merchant_id: str
    reference: str
    full_name: str
    email: str
    created_at: str


@dataclass
class PaymentRow:
    id: str
    merchant_id: str
    customer_id: str | None
    location_id: str | None
    order_reference: str
    description: str
    amount_cents: int
    currency: str
    channel: str
    created_at: str


@dataclass
class AttemptRow:
    id: str
    merchant_id: str
    payment_id: str
    attempt_number: int
    method_type: str
    card_brand: str
    card_last4: str
    wallet_type: str | None
    outcome: str
    failure_code: str | None
    failure_message: str | None
    created_at: str
    completed_at: str | None


@dataclass
class RefundRow:
    id: str
    merchant_id: str
    payment_id: str
    amount_cents: int
    currency: str
    reason: str
    status: str
    created_at: str
    completed_at: str | None


@dataclass
class DisputeRow:
    id: str
    merchant_id: str
    payment_id: str
    amount_cents: int
    currency: str
    reason: str
    status: str
    opened_at: str
    evidence_due_at: str
    responded_at: str | None
    resolved_at: str | None


@dataclass
class PayoutRow:
    id: str
    merchant_id: str
    amount_cents: int
    currency: str
    status: str
    cutoff_at: str
    sent_at: str
    expected_arrival_date: str
    paid_at: str | None
    destination_label: str
    destination_last4: str
    destination_kind: str


@dataclass
class MovementRow:
    id: str
    merchant_id: str
    type: str
    amount_cents: int
    currency: str
    description: str
    posted_at: str
    available_at: str
    payout_id: str | None
    payment_id: str | None
    attempt_id: str | None
    refund_id: str | None
    dispute_id: str | None


@dataclass
class NoteEventRow:
    id: str
    merchant_id: str
    kind: str
    actor_user_id: str
    payment_id: str | None
    dispute_id: str | None
    payout_id: str | None
    export_name: str | None
    body: str
    created_at: str


@dataclass
class Dataset:
    merchants: list[MerchantRow] = field(default_factory=list)
    locations: list[LocationRow] = field(default_factory=list)
    users: list[UserRow] = field(default_factory=list)
    memberships: list[MembershipRow] = field(default_factory=list)
    customers: list[CustomerRow] = field(default_factory=list)
    payments: list[PaymentRow] = field(default_factory=list)
    attempts: list[AttemptRow] = field(default_factory=list)
    refunds: list[RefundRow] = field(default_factory=list)
    disputes: list[DisputeRow] = field(default_factory=list)
    payouts: list[PayoutRow] = field(default_factory=list)
    movements: list[MovementRow] = field(default_factory=list)
    note_events: list[NoteEventRow] = field(default_factory=list)
    meta: dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------- helpers


def _weighted(rng: random.Random, weights: dict[str, float]) -> str:
    keys = list(weights.keys())
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def _weighted_pairs(rng: random.Random, pairs: tuple[tuple[str, float], ...]) -> str:
    return rng.choices([p[0] for p in pairs], weights=[p[1] for p in pairs], k=1)[0]


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, int(round(rng.gauss(lam, lam**0.5))))
    limit = pow(2.718281828459045, -lam)
    k, p = 0, 1.0
    while True:
        p *= rng.random()
        if p < limit:
            return k
        k += 1


def _business_day(day: date) -> bool:
    return day.weekday() < 5 and day not in S.HOLIDAYS


def _next_business_day(day: date) -> date:
    cursor = day + timedelta(days=1)
    while not _business_day(cursor):
        cursor += timedelta(days=1)
    return cursor


def _roll_forward(day: date) -> date:
    while not _business_day(day):
        day += timedelta(days=1)
    return day


def _midnight_safe(dt: datetime) -> datetime:
    """Push an instant away from a Chicago midnight by the guard distance."""
    local = dt.astimezone(CHICAGO)
    seconds_into_day = local.hour * 3600 + local.minute * 60 + local.second
    guard = S.MIDNIGHT_GUARD_SECONDS
    if seconds_into_day < guard:
        return dt + timedelta(seconds=guard - seconds_into_day)
    if seconds_into_day > 86400 - guard:
        return dt - timedelta(seconds=seconds_into_day - (86400 - guard))
    return dt


def _describe(items: list[S.CatalogItem]) -> str:
    names = [i.name for i in items]
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{names[0]}, {names[1]} and {len(names) - 2} more item{'s' if len(names) > 3 else ''}"


# --------------------------------------------------------------------------- generator


class Seeder:
    def __init__(self, seed: int = S.RNG_SEED) -> None:
        self.rng = random.Random(seed)
        self.data = Dataset()
        self.merchant_ids: dict[str, str] = {}
        self.location_rows: dict[str, list[tuple[LocationRow, LocationSpec]]] = {}
        self.user_ids: dict[str, str] = {}
        self.pools: dict[str, list[CustomerRow]] = {}
        self.seeded_customer_ids: dict[tuple[str, str], str] = {}
        self.payment_items: dict[str, list[S.CatalogItem]] = {}
        self.attempts_by_payment: dict[str, list[AttemptRow]] = {}
        self.pending_cutoff = S.AS_OF - timedelta(minutes=S.PENDING_WINDOW_MINUTES)

    # -- ids -------------------------------------------------------------------------
    def new(self, kind: str) -> str:
        return new_id(kind, self.rng)

    # -- master data -------------------------------------------------------------------
    def build_master_data(self) -> None:
        created = to_iso(S.WINDOW_START - timedelta(days=400))
        for spec in S.MERCHANTS:
            mid = self.new("merchant")
            self.merchant_ids[spec.slug] = mid
            self.data.merchants.append(
                MerchantRow(mid, spec.name, spec.slug, spec.legal_name, spec.support_email, spec.industry, spec.payout_schedule,
                            spec.destination_label, spec.destination_last4, spec.destination_kind, created)
            )
            rows = []
            for loc in spec.locations:
                row = LocationRow(self.new("location"), mid, loc.name, loc.address_line, loc.city, loc.state)
                self.data.locations.append(row)
                rows.append((row, loc))
            self.location_rows[spec.slug] = rows
        for user in S.USERS:
            uid = self.new("user")
            self.user_ids[user.email] = uid
            self.data.users.append(UserRow(uid, user.full_name, user.email, user.title))
            for slug, role in user.memberships:
                self.data.memberships.append(MembershipRow(self.new("membership"), uid, self.merchant_ids[slug], role, created))

    def build_customers(self) -> None:
        for spec in S.MERCHANTS:
            mid = self.merchant_ids[spec.slug]
            pool: list[CustomerRow] = []
            used_emails: set[str] = set()
            seq = 0

            def add(full_name: str, email: str) -> CustomerRow:
                nonlocal seq
                seq += 1
                days_before = self.rng.randint(5, 540)
                created_at = to_iso(S.WINDOW_START - timedelta(days=days_before, minutes=self.rng.randint(0, 1439)))
                row = CustomerRow(self.new("customer"), mid, f"{spec.customer_prefix}-{seq:04d}", full_name, email, created_at)
                self.data.customers.append(row)
                used_emails.add(email)
                return row

            for full_name, email in spec.seeded_customers:
                row = add(full_name, email)
                self.seeded_customer_ids[(spec.slug, email)] = row.id
            while len(pool) < spec.named_customers:
                first = self.rng.choice(S.FIRST_NAMES)
                last = self.rng.choice(S.LAST_NAMES)
                base = f"{first.lower()}.{last.lower()}"
                email = f"{base}@example.com"
                n = 2
                while email in used_emails:
                    email = f"{base}{n}@example.com"
                    n += 1
                pool.append(add(f"{first} {last}", email))
            self.pools[spec.slug] = pool

    # -- payments --------------------------------------------------------------------
    def _override(self, slug: str, channel: str, at: datetime) -> WindowOverride | None:
        for o in S.WINDOW_OVERRIDES:
            if o.merchant_slug == slug and o.channel == channel and o.start <= at < o.end:
                return o
        return None

    def _open_locations(self, spec: MerchantSpec, slug: str, day: date, hour: int) -> list[LocationRow]:
        out = []
        for row, loc in self.location_rows[slug]:
            if day.weekday() in loc.closed_weekdays or day in loc.closed_days:
                continue
            if not (loc.open_hour <= hour < loc.close_hour):
                continue
            out.append(row)
        return out

    def _pick_customer(self, spec: MerchantSpec) -> str | None:
        if self.rng.random() < spec.guest_share:
            return None
        pool = self.pools[spec.slug]
        index = int(len(pool) * (self.rng.random() ** 1.35))
        return pool[min(index, len(pool) - 1)].id

    def _order(self, spec: MerchantSpec) -> tuple[list[S.CatalogItem], int]:
        n = self.rng.choices(range(1, len(spec.items_per_order) + 1), weights=spec.items_per_order, k=1)[0]
        items = [self.rng.choice(spec.catalog) for _ in range(n)]
        subtotal = sum(i.price_cents for i in items)
        tax = (subtotal * spec.tax_bps + 5000) // 10000
        return items, subtotal + tax

    def _method(self, spec: MerchantSpec, channel: str) -> tuple[str, str, str, str | None]:
        brand = _weighted_pairs(self.rng, S.CARD_BRANDS)
        last4 = f"{self.rng.randint(0, 9999):04d}"
        if self.rng.random() < spec.wallet_share[channel]:
            return "wallet", brand, last4, _weighted_pairs(self.rng, S.WALLET_TYPES)
        return "card", brand, last4, None

    def _new_payment(self, spec: MerchantSpec, channel: str, created: datetime, location_id: str | None,
                     customer_id: str | None = None, items: list[S.CatalogItem] | None = None, amount: int | None = None) -> PaymentRow:
        mid = self.merchant_ids[spec.slug]
        if items is None or amount is None:
            items, amount = self._order(spec)
        if customer_id is None:
            customer_id = self._pick_customer(spec)
        row = PaymentRow(self.new("payment"), mid, customer_id, location_id, "", _describe(items), amount, money.CURRENCY, channel, to_iso(created))
        self.payment_items[row.id] = items
        self.data.payments.append(row)
        return row

    def _attempts_for(self, spec: MerchantSpec, payment: PaymentRow, created: datetime, *, scripted: list[dict] | None = None) -> None:
        """Generate the attempt chain for a payment."""
        mid = payment.merchant_id
        attempts: list[AttemptRow] = []
        online = payment.channel != "in_store"
        if scripted is not None:
            for n, a in enumerate(scripted, start=1):
                attempts.append(AttemptRow(self.new("attempt"), mid, payment.id, n, a["method_type"], a["card_brand"], a["card_last4"],
                                           a.get("wallet_type"), a["outcome"], a.get("failure_code"),
                                           S.DECLINE_CODES[a["failure_code"]] if a.get("failure_code") else None,
                                           to_iso(a["created"]), to_iso(a["completed"]) if a.get("completed") else None))
            self.attempts_by_payment[payment.id] = attempts
            self.data.attempts.extend(attempts)
            return

        at = created
        number = 1
        method = self._method(spec, payment.channel)
        prior_code: str | None = None
        while True:
            override = self._override(spec.slug, payment.channel, at)
            if number == 1:
                failure_share = override.failure_share if override else S.FIRST_ATTEMPT_FAILURE_SHARE[payment.channel]
            else:
                failure_share = override.retry_failure_share if override else S.RETRY_FAILURE_SHARE
            code_weights = override.code_weights if override else S.DECLINE_CODE_WEIGHTS

            pending = online and at >= self.pending_cutoff and self.rng.random() < S.PENDING_SHARE_IN_WINDOW
            if pending:
                attempts.append(AttemptRow(self.new("attempt"), mid, payment.id, number, *method, "pending", None, None, to_iso(at), None))
                break
            duration = timedelta(seconds=self.rng.randint(*S.ATTEMPT_DURATION_SECONDS))
            completed = at + duration
            if self.rng.random() < failure_share:
                code = _weighted(self.rng, code_weights)
                attempts.append(AttemptRow(self.new("attempt"), mid, payment.id, number, *method, "failed", code, S.DECLINE_CODES[code], to_iso(at), to_iso(completed)))
                retry_probability = override.retry_probability if override else S.RETRY_PROBABILITY
                if number >= 2:
                    retry_probability = S.SECOND_RETRY_PROBABILITY
                if number >= 3 or self.rng.random() >= retry_probability:
                    break
                delay_range = override.retry_delay_seconds if override else S.RETRY_DELAY_SECONDS
                next_at = _midnight_safe(completed + timedelta(seconds=self.rng.randint(*delay_range)))
                if next_at > S.AS_OF - timedelta(seconds=30):
                    break
                if code in S.RETRY_SAME_CARD_CODES and self.rng.random() < 0.6:
                    pass  # shopper fixes the entry and retries the same card
                else:
                    method = self._method(spec, payment.channel)
                prior_code = code
                at = next_at
                number += 1
                continue
            attempts.append(AttemptRow(self.new("attempt"), mid, payment.id, number, *method, "succeeded", None, None, to_iso(at), to_iso(completed)))
            break
        del prior_code
        self.attempts_by_payment[payment.id] = attempts
        self.data.attempts.extend(attempts)

    def build_payments(self) -> None:
        day = S.WINDOW_START_DAY
        while day <= S.AS_OF_DAY:
            for spec in S.MERCHANTS:
                weekday = day.weekday()
                for channel, share in spec.channel_share.items():
                    hours = spec.hour_weights[channel]
                    total_weight = sum(hours)
                    daily_expected = spec.daily_payments * share * spec.weekday_weights[channel][weekday]
                    for hour in range(24):
                        if hours[hour] <= 0:
                            continue
                        slot_start = chicago_local(day.year, day.month, day.day, hour)
                        if slot_start >= S.AS_OF:
                            continue
                        override = self._override(spec.slug, channel, slot_start + timedelta(minutes=30))
                        expected = daily_expected * hours[hour] / total_weight * (override.volume_multiplier if override else 1.0)
                        if channel == "in_store":
                            open_locations = self._open_locations(spec, spec.slug, day, hour)
                            if not open_locations:
                                continue
                            expected *= len(open_locations) / max(1, len(spec.locations))
                        else:
                            open_locations = []
                        count = _poisson(self.rng, expected)
                        for _ in range(count):
                            created = _midnight_safe(slot_start + timedelta(seconds=self.rng.randint(0, 3599)))
                            if created >= S.AS_OF - timedelta(seconds=45):
                                continue
                            location_id = self.rng.choice(open_locations).id if channel == "in_store" else None
                            payment = self._new_payment(spec, channel, created, location_id)
                            self._attempts_for(spec, payment, created)
            day += timedelta(days=1)

    def build_scripted_payments(self) -> None:
        """A handful of shopper stories told exactly."""
        spec = S.ALDER_LOOM
        taylor = self.seeded_customer_ids[("alder-loom", "taylor.reed@example.com")]
        avery = self.seeded_customer_ids[("alder-loom", "avery.stone@example.com")]
        morgan = self.seeded_customer_ids[("alder-loom", "morgan.lee@example.com")]
        avery_juniper = self.seeded_customer_ids[("juniper-trail", "avery.stone@example.com")]

        # Taylor Reed: declined, retried on another card, settled, partially refunded, annotated.
        items = [spec.catalog[0], spec.catalog[1]]  # duvet cover + mug set
        subtotal = sum(i.price_cents for i in items)
        amount = subtotal + (subtotal * spec.tax_bps + 5000) // 10000
        created = chicago_local(2026, 9, 22, 14, 11, 37)
        anchor = self._new_payment(spec, "website", created, None, customer_id=taylor, items=items, amount=amount)
        self._attempts_for(spec, anchor, created, scripted=[
            {"method_type": "card", "card_brand": "visa", "card_last4": "4242", "outcome": "failed", "failure_code": "insufficient_funds",
             "created": created, "completed": created + timedelta(seconds=2)},
            {"method_type": "card", "card_brand": "mastercard", "card_last4": "8812", "outcome": "succeeded",
             "created": created + timedelta(minutes=3, seconds=14), "completed": created + timedelta(minutes=3, seconds=16)},
        ])
        self.anchor_payment_id = anchor.id

        def story(customer_id: str, merchant: MerchantSpec, channel: str, when: datetime, items: list[S.CatalogItem] | None = None) -> PaymentRow:
            if items is None:
                items, amount_ = self._order(merchant)
            else:
                sub = sum(i.price_cents for i in items)
                amount_ = sub + (sub * merchant.tax_bps + 5000) // 10000
            location_id = None
            if channel == "in_store":
                location_id = self.location_rows[merchant.slug][0][0].id
            p = self._new_payment(merchant, channel, when, location_id, customer_id=customer_id, items=items, amount=amount_)
            method = self._method(merchant, channel)
            done = when + timedelta(seconds=2)
            self._attempts_for(merchant, p, when, scripted=[
                {"method_type": method[0], "card_brand": method[1], "card_last4": method[2], "wallet_type": method[3], "outcome": "succeeded",
                 "created": when, "completed": done},
            ])
            return p

        story(taylor, spec, "website", chicago_local(2026, 9, 8, 20, 4, 12))
        story(taylor, spec, "in_store", chicago_local(2026, 9, 19, 13, 42, 5))
        story(taylor, spec, "mobile_app", chicago_local(2026, 10, 3, 11, 15, 48))

        self.avery_refund_payment = story(avery, spec, "website", chicago_local(2026, 9, 6, 11, 22, 3), [spec.catalog[3], spec.catalog[10]])
        story(avery, spec, "website", chicago_local(2026, 9, 13, 19, 48, 29))
        story(avery, spec, "in_store", chicago_local(2026, 9, 20, 15, 5, 51))
        story(avery, spec, "mobile_app", chicago_local(2026, 9, 27, 21, 33, 10))
        story(avery, spec, "website", chicago_local(2026, 10, 4, 12, 2, 44))

        self.morgan_dispute_payment = story(morgan, spec, "website", chicago_local(2026, 9, 15, 12, 31, 9), [spec.catalog[17]])
        story(morgan, spec, "website", chicago_local(2026, 9, 25, 18, 7, 2))
        story(morgan, spec, "in_store", chicago_local(2026, 10, 2, 16, 20, 40))

        # The same email at Juniper is a different customer with unrelated activity.
        story(avery_juniper, S.JUNIPER_TRAIL, "website", chicago_local(2026, 9, 12, 9, 40, 15))
        story(avery_juniper, S.JUNIPER_TRAIL, "in_store", chicago_local(2026, 9, 26, 14, 18, 36))

        # Payments still in flight at the clock.
        for slug, channel, when in S.PENDING_PAYMENTS:
            merchant = next(m for m in S.MERCHANTS if m.slug == slug)
            p = self._new_payment(merchant, channel, when, None)
            method = self._method(merchant, channel)
            self._attempts_for(merchant, p, when, scripted=[
                {"method_type": method[0], "card_brand": method[1], "card_last4": method[2], "wallet_type": method[3], "outcome": "pending",
                 "created": when},
            ])

    def finalize_payment_order(self) -> None:
        """Sort payments chronologically and assign order references per merchant."""
        self.data.payments.sort(key=lambda p: (p.created_at, p.id))
        counters: dict[str, int] = {}
        prefix_by_merchant = {self.merchant_ids[s.slug]: s.order_prefix for s in S.MERCHANTS}
        for p in self.data.payments:
            n = counters.get(p.merchant_id, 10000) + 1
            counters[p.merchant_id] = n
            p.order_reference = f"{prefix_by_merchant[p.merchant_id]}-{n}"
        self.data.attempts.sort(key=lambda a: (a.created_at, a.payment_id, a.attempt_number))

    # -- derived records -----------------------------------------------------------------
    def _succeeded(self, payment_id: str) -> AttemptRow | None:
        for a in self.attempts_by_payment.get(payment_id, []):
            if a.outcome == "succeeded":
                return a
        return None

    def build_refunds(self) -> None:
        refunded_ids: set[str] = set()
        by_merchant: dict[str, list[PaymentRow]] = {}
        for p in self.data.payments:
            by_merchant.setdefault(p.merchant_id, []).append(p)
        for spec in S.MERCHANTS:
            mid = self.merchant_ids[spec.slug]
            candidates = []
            for p in by_merchant.get(mid, []):
                s = self._succeeded(p.id)
                if s is None:
                    continue
                completed = datetime.strptime(s.completed_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
                if completed + timedelta(days=1) < S.AS_OF:
                    candidates.append((p, completed))
            forced = [self.avery_refund_payment.id] if spec.slug == "alder-loom" else []
            forced.append(self.anchor_payment_id) if spec.slug == "alder-loom" else None
            target = int(round(len(candidates) * spec.refund_share))
            chosen = [c for c in candidates if c[0].id in forced]
            rest = [c for c in candidates if c[0].id not in forced]
            chosen += self.rng.sample(rest, max(0, target - len(chosen)))
            chosen.sort(key=lambda c: c[1])
            pending_quota = S.PENDING_REFUNDS_PER_MERCHANT[spec.slug]
            # Pending refunds are the most recent ones, created in the last day.
            recent = [c for c in chosen if c[1] + timedelta(hours=26) > S.AS_OF]
            pending_ids = {c[0].id for c in recent[-pending_quota:]} if pending_quota else set()
            if pending_quota and len(pending_ids) < pending_quota:
                # Not enough very recent refunds; promote the latest chosen ones.
                for c in reversed(chosen):
                    if len(pending_ids) >= pending_quota:
                        break
                    pending_ids.add(c[0].id)
            for p, completed in chosen:
                if p.id in refunded_ids:
                    continue
                refunded_ids.add(p.id)
                if p.id == self.anchor_payment_id:
                    created = chicago_local(2026, 9, 26, 10, 5, 21)
                    amount, reason = 4800, "price_adjustment"
                else:
                    if p.id in pending_ids:
                        created = _midnight_safe(S.AS_OF - timedelta(minutes=self.rng.randint(35, 20 * 60)))
                        if created <= completed:
                            created = completed + timedelta(hours=3)
                    else:
                        created = _midnight_safe(completed + timedelta(days=self.rng.randint(*S.REFUND_DELAY_DAYS), minutes=self.rng.randint(0, 1439)))
                    if created >= S.AS_OF - timedelta(minutes=30):
                        created = _midnight_safe(S.AS_OF - timedelta(hours=self.rng.randint(2, 30)))
                        if created <= completed:
                            continue
                    items = self.payment_items[p.id]
                    full = self.rng.random() < S.REFUND_FULL_SHARE or len(items) == 1 and self.rng.random() < 0.5
                    if full:
                        amount = p.amount_cents
                    elif len(items) > 1:
                        item = self.rng.choice(items)
                        amount = item.price_cents + (item.price_cents * spec.tax_bps + 5000) // 10000
                        amount = min(amount, p.amount_cents - 100)
                    else:
                        amount = max(100, (p.amount_cents * self.rng.randint(20, 60) // 100) // 100 * 100)
                    reason = _weighted(self.rng, S.REFUND_REASON_WEIGHTS)
                    if reason == "returned_in_store" and p.channel != "in_store" and self.rng.random() < 0.5:
                        reason = "requested_by_customer"
                pending = p.id in pending_ids
                completed_at = None if pending else to_iso(created + timedelta(minutes=self.rng.randint(2, 12)))
                self.data.refunds.append(RefundRow(self.new("refund"), mid, p.id, amount, money.CURRENCY, reason, "pending" if pending else "succeeded",
                                                   to_iso(created), completed_at))
        self.data.refunds.sort(key=lambda r: (r.created_at, r.id))

    def build_disputes(self) -> None:
        refunded = {r.payment_id for r in self.data.refunds}
        disputed: set[str] = set()
        customers_by_id = {c.id: c for c in self.data.customers}
        for spec in S.DISPUTES:
            mid = self.merchant_ids[spec.merchant_slug]
            opened = _midnight_safe(S.AS_OF - timedelta(days=spec.opened_days_before_as_of) + timedelta(hours=self.rng.randint(-6, 6), minutes=self.rng.randint(0, 59)))
            pool = []
            for p in self.data.payments:
                if p.merchant_id != mid or p.id in refunded or p.id in disputed or p.amount_cents < spec.min_amount_cents:
                    continue
                s = self._succeeded(p.id)
                if s is None or s.completed_at >= to_iso(opened - timedelta(days=2)):
                    continue
                if spec.customer_email:
                    c = customers_by_id.get(p.customer_id or "")
                    if c is None or c.email != spec.customer_email:
                        continue
                pool.append(p)
            if spec.customer_email and self.morgan_dispute_payment.id in {p.id for p in pool}:
                payment = self.morgan_dispute_payment
            else:
                payment = self.rng.choice(pool)
            disputed.add(payment.id)
            due = opened + timedelta(days=spec.due_days_after_open)
            responded = opened + timedelta(days=spec.responded_days_after_open, hours=3) if spec.responded_days_after_open is not None else None
            resolved = opened + timedelta(days=spec.resolved_days_after_open, hours=5) if spec.resolved_days_after_open is not None else None
            self.data.disputes.append(DisputeRow(self.new("dispute"), mid, payment.id, payment.amount_cents, money.CURRENCY, spec.reason, spec.status,
                                                 to_iso(opened), to_iso(due), to_iso(responded) if responded else None, to_iso(resolved) if resolved else None))
        self.data.disputes.sort(key=lambda d: (d.opened_at, d.id))

    def build_movements(self) -> None:
        payments_by_id = {p.id: p for p in self.data.payments}
        delay = timedelta(hours=S.AVAILABILITY_DELAY_HOURS)
        for a in self.data.attempts:
            if a.outcome != "succeeded":
                continue
            p = payments_by_id[a.payment_id]
            posted = datetime.strptime(a.completed_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            available = to_iso(posted + delay)
            self.data.movements.append(MovementRow(self.new("movement"), p.merchant_id, "charge", p.amount_cents, money.CURRENCY,
                                                   f"Payment {p.order_reference}", a.completed_at, available, None, p.id, a.id, None, None))
            fee = money.fee_cents(p.amount_cents, p.channel)
            self.data.movements.append(MovementRow(self.new("movement"), p.merchant_id, "fee", -fee, money.CURRENCY,
                                                   f"Processing fee for {p.order_reference}", a.completed_at, available, None, p.id, a.id, None, None))
        for r in self.data.refunds:
            if r.status != "succeeded":
                continue
            p = payments_by_id[r.payment_id]
            self.data.movements.append(MovementRow(self.new("movement"), p.merchant_id, "refund", -r.amount_cents, money.CURRENCY,
                                                   f"Refund on {p.order_reference}", r.completed_at, r.completed_at, None, p.id, None, r.id, None))
        for d in self.data.disputes:
            p = payments_by_id[d.payment_id]
            self.data.movements.append(MovementRow(self.new("movement"), p.merchant_id, "dispute_reversal", -d.amount_cents, money.CURRENCY,
                                                   f"Dispute reversal on {p.order_reference}", d.opened_at, d.opened_at, None, p.id, None, None, d.id))
            self.data.movements.append(MovementRow(self.new("movement"), p.merchant_id, "dispute_fee", -S.DISPUTE_FEE_CENTS, money.CURRENCY,
                                                   f"Dispute fee on {p.order_reference}", d.opened_at, d.opened_at, None, p.id, None, None, d.id))
            if d.status == "won" and d.resolved_at:
                self.data.movements.append(MovementRow(self.new("movement"), p.merchant_id, "dispute_reinstatement", d.amount_cents, money.CURRENCY,
                                                       f"Dispute won on {p.order_reference}", d.resolved_at, d.resolved_at, None, p.id, None, None, d.id))
        for adj in S.ADJUSTMENTS:
            at = to_iso(chicago_local(adj.day.year, adj.day.month, adj.day.day, adj.hour, 0, 0))
            self.data.movements.append(MovementRow(self.new("movement"), self.merchant_ids[adj.merchant_slug], "adjustment", adj.amount_cents, money.CURRENCY,
                                                   adj.description, at, at, None, None, None, None, None))
        self.data.movements.sort(key=lambda m: (m.posted_at, m.id))

    def _cutoff_days(self, schedule: str) -> list[date]:
        days: list[date] = []
        cursor = S.WINDOW_START_DAY
        while cursor <= S.AS_OF_DAY:
            if schedule == "daily" and _business_day(cursor):
                days.append(cursor)
            elif schedule == "weekly_friday" and cursor.weekday() == 4:
                days.append(_roll_forward(cursor))
            elif schedule == "weekly_monday" and cursor.weekday() == 0:
                days.append(_roll_forward(cursor))
            cursor += timedelta(days=1)
        return sorted({d for d in days if d <= S.AS_OF_DAY})

    def build_payouts(self) -> None:
        for spec in S.MERCHANTS:
            mid = self.merchant_ids[spec.slug]
            movements = [m for m in self.data.movements if m.merchant_id == mid]
            for day in self._cutoff_days(spec.payout_schedule):
                cutoff = chicago_local(day.year, day.month, day.day, 0, 0, 0)
                if cutoff > S.AS_OF:
                    continue
                cutoff_iso = to_iso(cutoff)
                swept = [m for m in movements if m.payout_id is None and m.available_at < cutoff_iso]
                if not swept:
                    continue
                pid = self.new("payout")
                amount = sum(m.amount_cents for m in swept)
                for m in swept:
                    m.payout_id = pid
                sent = cutoff + timedelta(hours=6)
                arrival_day = _next_business_day(day)
                paid_at = chicago_local(arrival_day.year, arrival_day.month, arrival_day.day, 9, 0, 0)
                status = "paid" if paid_at <= S.AS_OF else "in_transit"
                self.data.payouts.append(PayoutRow(pid, mid, amount, money.CURRENCY, status, cutoff_iso, to_iso(sent), arrival_day.isoformat(),
                                                   to_iso(paid_at) if status == "paid" else None,
                                                   spec.destination_label, spec.destination_last4, spec.destination_kind))

    def build_notes(self) -> None:
        payments_by_id = {p.id: p for p in self.data.payments}
        writers = {
            "alder-loom": [self.user_ids["maya.chen@alder-loom.example.com"]] * 3 + [self.user_ids["jordan.ellis@alder-loom.example.com"]],
            "juniper-trail": [self.user_ids["priya.shah@junipertrail.example.com"]],
            "copper-finch": [],
        }
        texts = list(S.NOTE_TEXTS)
        used_texts = 0

        def next_text() -> str:
            nonlocal used_texts
            t = texts[used_texts % len(texts)]
            used_texts += 1
            return t

        # The anchor payment carries a note by Maya shortly after its refund.
        anchor = payments_by_id[self.anchor_payment_id]
        self.data.note_events.append(NoteEventRow(self.new("note_event"), anchor.merchant_id, "note", self.user_ids["maya.chen@alder-loom.example.com"], anchor.id, None, None, None,
                                                  "Customer called about a second charge on the duvet order. The first attempt was declined and never captured; the Mastercard retry settled. Partial refund for the sale price difference issued by Daniel.",
                                                  to_iso(chicago_local(2026, 9, 26, 10, 40, 12))))
        for spec in S.MERCHANTS:
            mid = self.merchant_ids[spec.slug]
            quota = S.SEEDED_PAYMENT_NOTES[spec.slug]
            if not quota or not writers[spec.slug]:
                continue
            pool = [p for p in self.data.payments if p.merchant_id == mid and p.id != self.anchor_payment_id and self._succeeded(p.id) is not None
                    and p.created_at < to_iso(S.AS_OF - timedelta(days=2))]
            for p in self.rng.sample(pool, quota):
                s = self._succeeded(p.id)
                assert s is not None
                base = datetime.strptime(s.completed_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
                at = _midnight_safe(base + timedelta(hours=self.rng.randint(5, 40), minutes=self.rng.randint(0, 59)))
                if at >= S.AS_OF:
                    at = S.AS_OF - timedelta(hours=self.rng.randint(1, 20))
                actor = self.rng.choice(writers[spec.slug])
                self.data.note_events.append(NoteEventRow(self.new("note_event"), mid, "note", actor, p.id, None, None, None, next_text(), to_iso(at)))
        for d in self.data.disputes:
            if d.status != "under_review":
                continue
            slug = next(s.slug for s in S.MERCHANTS if self.merchant_ids[s.slug] == d.merchant_id)
            if not writers[slug]:
                continue
            at = datetime.strptime(d.responded_at or d.opened_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC) - timedelta(hours=20)
            self.data.note_events.append(NoteEventRow(self.new("note_event"), d.merchant_id, "note", writers[slug][0], None, d.id, None, None,
                                                      "Bank asked for the original receipt and delivery confirmation. Submitted carrier tracking and the signed delivery photo before the deadline.",
                                                      to_iso(_midnight_safe(at))))
        self.data.note_events.sort(key=lambda n: (n.created_at, n.id))

    def build_meta(self) -> None:
        self.data.meta = {
            "as_of": to_iso(S.AS_OF),
            "rng_seed": str(S.RNG_SEED),
            "window_start": to_iso(S.WINDOW_START),
            "window_end": to_iso(S.AS_OF),
            "reporting_timezone": "America/Chicago",
            "seed_version": "1",
        }

    def build(self) -> Dataset:
        self.build_master_data()
        self.build_customers()
        self.build_payments()
        self.build_scripted_payments()
        self.finalize_payment_order()
        self.build_refunds()
        self.build_disputes()
        self.build_movements()
        self.build_payouts()
        self.build_notes()
        self.build_meta()
        return self.data


def build_dataset(seed: int = S.RNG_SEED) -> Dataset:
    return Seeder(seed).build()
