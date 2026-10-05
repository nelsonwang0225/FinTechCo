"""Human labels for enum values. The API sends value and label together so the frontend never keeps its own copy."""

from __future__ import annotations

CHANNEL_LABELS: dict[str, str] = {"website": "Website", "mobile_app": "Mobile app", "in_store": "In store"}
PAYMENT_STATUS_LABELS: dict[str, str] = {
    "succeeded": "Succeeded",
    "pending": "Pending",
    "failed": "Failed",
    "partially_refunded": "Partially refunded",
    "refunded": "Refunded",
}
ATTEMPT_OUTCOME_LABELS: dict[str, str] = {"succeeded": "Succeeded", "failed": "Failed", "pending": "Pending"}
REFUND_STATUS_LABELS: dict[str, str] = {"pending": "Pending", "succeeded": "Succeeded"}
REFUND_REASON_LABELS: dict[str, str] = {
    "requested_by_customer": "Requested by customer",
    "damaged_in_transit": "Damaged in transit",
    "wrong_item": "Wrong item",
    "duplicate": "Duplicate",
    "price_adjustment": "Price adjustment",
    "returned_in_store": "Returned in store",
}
DISPUTE_STATUS_LABELS: dict[str, str] = {"needs_response": "Needs response", "under_review": "Under review", "won": "Won", "lost": "Lost"}
DISPUTE_REASON_LABELS: dict[str, str] = {
    "fraudulent": "Fraudulent",
    "product_not_received": "Product not received",
    "product_unacceptable": "Product unacceptable",
    "duplicate": "Duplicate",
    "credit_not_processed": "Credit not processed",
}
PAYOUT_STATUS_LABELS: dict[str, str] = {"in_transit": "In transit", "paid": "Paid"}
MOVEMENT_TYPE_LABELS: dict[str, str] = {
    "charge": "Collection",
    "fee": "Fee",
    "refund": "Refund",
    "dispute_reversal": "Dispute reversal",
    "dispute_fee": "Dispute fee",
    "dispute_reinstatement": "Dispute reinstatement",
    "adjustment": "Adjustment",
}
METHOD_TYPE_LABELS: dict[str, str] = {"card": "Card", "wallet": "Wallet"}
CARD_BRAND_LABELS: dict[str, str] = {"visa": "Visa", "mastercard": "Mastercard", "amex": "American Express", "discover": "Discover"}
WALLET_LABELS: dict[str, str] = {"apple_pay": "Apple Pay", "google_pay": "Google Pay"}
ROLE_LABELS: dict[str, str] = {
    "business_admin": "Business admin",
    "operations_manager": "Operations manager",
    "finance_manager": "Finance manager",
    "read_only_analyst": "Read-only analyst",
}


def method_label(method_type: str | None, card_brand: str | None, card_last4: str | None, wallet_type: str | None) -> str | None:
    """'Visa •••• 4242' or 'Apple Pay · Visa •••• 4242'."""
    if method_type is None or card_brand is None or card_last4 is None:
        return None
    card = f"{CARD_BRAND_LABELS.get(card_brand, card_brand)} •••• {card_last4}"
    if method_type == "wallet" and wallet_type:
        return f"{WALLET_LABELS.get(wallet_type, wallet_type)} · {card}"
    return card
