-- FinTechCo Business schema.
-- Money: integer cents + currency ('USD'). Timestamps (*_at): UTC ISO 8601 'YYYY-MM-DDTHH:MM:SSZ'.
-- Dates (*_date): America/Chicago calendar dates. Every merchant-owned row carries merchant_id and every
-- child -> parent reference is a composite (parent_id, merchant_id) foreign key.

CREATE TABLE merchant (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    legal_name TEXT NOT NULL,
    support_email TEXT NOT NULL,
    industry TEXT NOT NULL,
    payout_schedule TEXT NOT NULL CHECK (payout_schedule IN ('daily', 'weekly_friday', 'weekly_monday')),
    destination_label TEXT NOT NULL,
    destination_last4 TEXT NOT NULL CHECK (length(destination_last4) = 4),
    destination_kind TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE location (
    id TEXT PRIMARY KEY,
    merchant_id TEXT NOT NULL REFERENCES merchant(id),
    name TEXT NOT NULL,
    address_line TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    UNIQUE (id, merchant_id),
    UNIQUE (merchant_id, name)
);

CREATE TABLE app_user (
    id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

CREATE TABLE membership (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES app_user(id),
    merchant_id TEXT NOT NULL REFERENCES merchant(id),
    role TEXT NOT NULL CHECK (role IN ('business_admin', 'operations_manager', 'finance_manager', 'read_only_analyst')),
    created_at TEXT NOT NULL,
    UNIQUE (user_id, merchant_id),
    UNIQUE (id, merchant_id)
);

CREATE TABLE customer (
    id TEXT PRIMARY KEY,
    merchant_id TEXT NOT NULL REFERENCES merchant(id),
    reference TEXT NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (id, merchant_id),
    UNIQUE (merchant_id, email),
    UNIQUE (merchant_id, reference)
);

CREATE TABLE payment (
    id TEXT PRIMARY KEY,
    merchant_id TEXT NOT NULL REFERENCES merchant(id),
    customer_id TEXT,
    location_id TEXT,
    order_reference TEXT NOT NULL,
    description TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    currency TEXT NOT NULL CHECK (currency = 'USD'),
    channel TEXT NOT NULL CHECK (channel IN ('website', 'mobile_app', 'in_store')),
    created_at TEXT NOT NULL,
    UNIQUE (id, merchant_id),
    UNIQUE (merchant_id, order_reference),
    FOREIGN KEY (customer_id, merchant_id) REFERENCES customer(id, merchant_id),
    FOREIGN KEY (location_id, merchant_id) REFERENCES location(id, merchant_id),
    CHECK ((channel = 'in_store') = (location_id IS NOT NULL))
);

CREATE TABLE payment_attempt (
    id TEXT PRIMARY KEY,
    merchant_id TEXT NOT NULL REFERENCES merchant(id),
    payment_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
    method_type TEXT NOT NULL CHECK (method_type IN ('card', 'wallet')),
    card_brand TEXT NOT NULL CHECK (card_brand IN ('visa', 'mastercard', 'amex', 'discover')),
    card_last4 TEXT NOT NULL CHECK (length(card_last4) = 4),
    wallet_type TEXT CHECK (wallet_type IN ('apple_pay', 'google_pay')),
    outcome TEXT NOT NULL CHECK (outcome IN ('succeeded', 'failed', 'pending')),
    failure_code TEXT,
    failure_message TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (id, merchant_id),
    UNIQUE (payment_id, attempt_number),
    FOREIGN KEY (payment_id, merchant_id) REFERENCES payment(id, merchant_id),
    CHECK ((method_type = 'wallet') = (wallet_type IS NOT NULL)),
    CHECK ((outcome = 'failed') = (failure_code IS NOT NULL)),
    CHECK ((outcome = 'failed') = (failure_message IS NOT NULL)),
    CHECK ((outcome = 'pending') = (completed_at IS NULL))
);
-- At most one succeeded attempt per payment.
CREATE UNIQUE INDEX payment_attempt_one_success ON payment_attempt(payment_id) WHERE outcome = 'succeeded';
CREATE INDEX payment_attempt_payment ON payment_attempt(payment_id, attempt_number);
CREATE INDEX payment_attempt_merchant_created ON payment_attempt(merchant_id, created_at);

CREATE TABLE refund (
    id TEXT PRIMARY KEY,
    merchant_id TEXT NOT NULL REFERENCES merchant(id),
    payment_id TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    currency TEXT NOT NULL CHECK (currency = 'USD'),
    reason TEXT NOT NULL CHECK (reason IN ('requested_by_customer', 'damaged_in_transit', 'wrong_item', 'duplicate', 'price_adjustment', 'returned_in_store')),
    status TEXT NOT NULL CHECK (status IN ('pending', 'succeeded')),
    created_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (id, merchant_id),
    FOREIGN KEY (payment_id, merchant_id) REFERENCES payment(id, merchant_id),
    CHECK ((status = 'succeeded') = (completed_at IS NOT NULL))
);
CREATE INDEX refund_payment ON refund(payment_id);
CREATE INDEX refund_merchant_created ON refund(merchant_id, created_at);

CREATE TABLE dispute (
    id TEXT PRIMARY KEY,
    merchant_id TEXT NOT NULL REFERENCES merchant(id),
    payment_id TEXT NOT NULL UNIQUE,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    currency TEXT NOT NULL CHECK (currency = 'USD'),
    reason TEXT NOT NULL CHECK (reason IN ('fraudulent', 'product_not_received', 'product_unacceptable', 'duplicate', 'credit_not_processed')),
    status TEXT NOT NULL CHECK (status IN ('needs_response', 'under_review', 'won', 'lost')),
    opened_at TEXT NOT NULL,
    evidence_due_at TEXT NOT NULL,
    responded_at TEXT,
    resolved_at TEXT,
    UNIQUE (id, merchant_id),
    FOREIGN KEY (payment_id, merchant_id) REFERENCES payment(id, merchant_id),
    CHECK ((status IN ('won', 'lost')) = (resolved_at IS NOT NULL)),
    CHECK (status != 'needs_response' OR responded_at IS NULL),
    CHECK (status != 'under_review' OR responded_at IS NOT NULL)
);
CREATE INDEX dispute_merchant_due ON dispute(merchant_id, evidence_due_at);

CREATE TABLE payout (
    id TEXT PRIMARY KEY,
    merchant_id TEXT NOT NULL REFERENCES merchant(id),
    amount_cents INTEGER NOT NULL,
    currency TEXT NOT NULL CHECK (currency = 'USD'),
    status TEXT NOT NULL CHECK (status IN ('in_transit', 'paid')),
    cutoff_at TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    expected_arrival_date TEXT NOT NULL,
    paid_at TEXT,
    destination_label TEXT NOT NULL,
    destination_last4 TEXT NOT NULL CHECK (length(destination_last4) = 4),
    destination_kind TEXT NOT NULL,
    UNIQUE (id, merchant_id),
    UNIQUE (merchant_id, cutoff_at),
    CHECK ((status = 'paid') = (paid_at IS NOT NULL))
);
CREATE INDEX payout_merchant_cutoff ON payout(merchant_id, cutoff_at);

CREATE TABLE balance_movement (
    id TEXT PRIMARY KEY,
    merchant_id TEXT NOT NULL REFERENCES merchant(id),
    type TEXT NOT NULL CHECK (type IN ('charge', 'fee', 'refund', 'dispute_reversal', 'dispute_fee', 'dispute_reinstatement', 'adjustment')),
    amount_cents INTEGER NOT NULL CHECK (amount_cents != 0),
    currency TEXT NOT NULL CHECK (currency = 'USD'),
    description TEXT NOT NULL,
    posted_at TEXT NOT NULL,
    available_at TEXT NOT NULL,
    payout_id TEXT,
    payment_id TEXT,
    attempt_id TEXT,
    refund_id TEXT,
    dispute_id TEXT,
    UNIQUE (id, merchant_id),
    FOREIGN KEY (payout_id, merchant_id) REFERENCES payout(id, merchant_id),
    FOREIGN KEY (payment_id, merchant_id) REFERENCES payment(id, merchant_id),
    FOREIGN KEY (attempt_id, merchant_id) REFERENCES payment_attempt(id, merchant_id),
    FOREIGN KEY (refund_id, merchant_id) REFERENCES refund(id, merchant_id),
    FOREIGN KEY (dispute_id, merchant_id) REFERENCES dispute(id, merchant_id),
    -- Each movement type carries exactly the source references it must.
    CHECK (
        (type IN ('charge', 'fee') AND payment_id IS NOT NULL AND attempt_id IS NOT NULL AND refund_id IS NULL AND dispute_id IS NULL)
        OR (type = 'refund' AND payment_id IS NOT NULL AND refund_id IS NOT NULL AND attempt_id IS NULL AND dispute_id IS NULL)
        OR (type IN ('dispute_reversal', 'dispute_fee', 'dispute_reinstatement') AND payment_id IS NOT NULL AND dispute_id IS NOT NULL AND attempt_id IS NULL AND refund_id IS NULL)
        OR (type = 'adjustment' AND payment_id IS NULL AND attempt_id IS NULL AND refund_id IS NULL AND dispute_id IS NULL)
    ),
    -- Signs are part of the type.
    CHECK (
        (type IN ('charge', 'dispute_reinstatement') AND amount_cents > 0)
        OR (type IN ('fee', 'refund', 'dispute_reversal', 'dispute_fee') AND amount_cents < 0)
        OR (type = 'adjustment')
    )
);
CREATE INDEX balance_movement_payout ON balance_movement(payout_id);
CREATE INDEX balance_movement_attempt ON balance_movement(attempt_id);
CREATE INDEX balance_movement_payment ON balance_movement(payment_id);
CREATE INDEX balance_movement_merchant_available ON balance_movement(merchant_id, payout_id, available_at);
CREATE INDEX balance_movement_merchant_posted ON balance_movement(merchant_id, type, posted_at);

CREATE TABLE note_event (
    id TEXT PRIMARY KEY,
    merchant_id TEXT NOT NULL REFERENCES merchant(id),
    kind TEXT NOT NULL CHECK (kind IN ('note', 'export')),
    actor_user_id TEXT NOT NULL REFERENCES app_user(id),
    payment_id TEXT,
    dispute_id TEXT,
    payout_id TEXT,
    export_name TEXT,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (id, merchant_id),
    FOREIGN KEY (payment_id, merchant_id) REFERENCES payment(id, merchant_id),
    FOREIGN KEY (dispute_id, merchant_id) REFERENCES dispute(id, merchant_id),
    FOREIGN KEY (payout_id, merchant_id) REFERENCES payout(id, merchant_id),
    CHECK (
        (kind = 'note' AND ((payment_id IS NOT NULL) + (dispute_id IS NOT NULL)) = 1 AND payout_id IS NULL AND export_name IS NULL AND length(trim(body)) > 0)
        OR (kind = 'export' AND export_name IS NOT NULL AND payment_id IS NULL AND dispute_id IS NULL)
    )
);
CREATE INDEX note_event_merchant_created ON note_event(merchant_id, created_at);
CREATE INDEX note_event_payment ON note_event(payment_id);
CREATE INDEX note_event_dispute ON note_event(dispute_id);

CREATE TABLE seed_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX payment_merchant_created ON payment(merchant_id, created_at);
CREATE INDEX payment_merchant_customer ON payment(merchant_id, customer_id);
CREATE INDEX customer_merchant_name ON customer(merchant_id, full_name);

-- payment_summary: the single definition of a payment's derived status and display fields.
-- Every reader (list, detail header, overview, customer pages, register export) selects from it.
CREATE VIEW payment_summary AS
WITH refunded AS (
    SELECT payment_id, SUM(amount_cents) AS refunded_cents
    FROM refund
    WHERE status = 'succeeded'
    GROUP BY payment_id
),
latest AS (
    SELECT payment_id, MAX(attempt_number) AS attempt_number
    FROM payment_attempt
    GROUP BY payment_id
)
SELECT
    p.id,
    p.merchant_id,
    p.customer_id,
    p.location_id,
    p.order_reference,
    p.description,
    p.amount_cents,
    p.currency,
    p.channel,
    p.created_at,
    s.id AS succeeded_attempt_id,
    s.completed_at AS succeeded_at,
    la.id AS latest_attempt_id,
    la.outcome AS latest_outcome,
    la.created_at AS latest_attempt_at,
    COALESCE(s.method_type, la.method_type) AS method_type,
    COALESCE(s.card_brand, la.card_brand) AS card_brand,
    COALESCE(s.card_last4, la.card_last4) AS card_last4,
    COALESCE(s.wallet_type, la.wallet_type) AS wallet_type,
    COALESCE(r.refunded_cents, 0) AS refunded_cents,
    p.amount_cents - COALESCE(r.refunded_cents, 0) AS net_cents,
    CASE
        WHEN s.id IS NOT NULL AND COALESCE(r.refunded_cents, 0) >= p.amount_cents THEN 'refunded'
        WHEN s.id IS NOT NULL AND COALESCE(r.refunded_cents, 0) > 0 THEN 'partially_refunded'
        WHEN s.id IS NOT NULL THEN 'succeeded'
        WHEN la.outcome = 'pending' THEN 'pending'
        ELSE 'failed'
    END AS status,
    (SELECT bm.payout_id FROM balance_movement bm WHERE bm.attempt_id = s.id AND bm.type = 'charge') AS payout_id,
    d.id AS dispute_id,
    d.status AS dispute_status,
    c.full_name AS customer_name,
    c.email AS customer_email,
    c.reference AS customer_reference,
    l.name AS location_name
FROM payment p
LEFT JOIN payment_attempt s ON s.payment_id = p.id AND s.outcome = 'succeeded'
LEFT JOIN latest ON latest.payment_id = p.id
LEFT JOIN payment_attempt la ON la.payment_id = p.id AND la.attempt_number = latest.attempt_number
LEFT JOIN refunded r ON r.payment_id = p.id
LEFT JOIN dispute d ON d.payment_id = p.id
LEFT JOIN customer c ON c.id = p.customer_id
LEFT JOIN location l ON l.id = p.location_id;
