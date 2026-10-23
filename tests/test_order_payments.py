from uuid import UUID

import pandas as pd
import pytest

from src.transform import transform_order_payments


VALID_ORDER = "b81ef226f3fe1789b1e8b2acac839d17"


def payment_frame(order_ids):
    return pd.DataFrame({
        "order_id": order_ids,
        "payment_sequential": [1] * len(order_ids),
        "payment_type": ["credit_card"] * len(order_ids),
        "payment_installments": [1] * len(order_ids),
        "payment_value": [10] * len(order_ids),
    })


def test_bad_uuid_rejected_while_valid_payment_continues():
    df = payment_frame([VALID_ORDER, "not-a-uuid"])
    df.index = [7, 7]
    original = df.copy(deep=True)
    clean, rejected = transform_order_payments(df)
    assert clean.order_id.tolist() == [str(UUID(VALID_ORDER))]
    assert UUID(clean.order_payments_id.iloc[0]).version == 5
    assert rejected.rejection_reason.tolist() == ["invalid_order_id"]
    assert rejected.raw_order_id.tolist() == ["not-a-uuid"]
    assert len(clean) + len(rejected) == len(df)
    assert clean.index.tolist() == rejected.index.tolist() == [7]
    pd.testing.assert_frame_equal(df, original)


@pytest.mark.parametrize("value, reason", [
    ("bad", "invalid_order_id"),
    (None, "missing_order_id"),
    (" ", "missing_order_id"),
])
def test_all_rejected_payments_return_empty_clean_without_crashing(value, reason):
    clean, rejected = transform_order_payments(payment_frame([value]))
    assert clean.empty
    assert "order_payments_id" in clean
    assert rejected.rejection_reason.tolist() == [reason]


def test_uuid_formats_normalize_before_duplicate_detection():
    clean, rejected = transform_order_payments(
        payment_frame([VALID_ORDER.upper(), str(UUID(VALID_ORDER))]),
    )
    assert clean.empty
    assert rejected.rejection_reason.tolist() == ["duplicate_order_payment_key"] * 2


def test_uuid_generation_remains_stable_across_input_formats():
    first, _ = transform_order_payments(payment_frame([VALID_ORDER]))
    second, _ = transform_order_payments(payment_frame([f" {str(UUID(VALID_ORDER)).upper()} "]))
    assert first.order_payments_id.tolist() == second.order_payments_id.tolist()


@pytest.mark.parametrize(
    "column",
    ["payment_sequential", "payment_installments"],
)
def test_payment_integer_overflow_is_rejected(column):
    df = payment_frame([VALID_ORDER])
    df[column] = "2147483648"

    clean, rejected = transform_order_payments(df)

    assert clean.empty
    assert rejected["rejection_reason"].tolist() == [f"invalid_{column}"]


@pytest.mark.parametrize(
    "column",
    ["payment_sequential", "payment_installments"],
)
def test_max_postgres_integer_is_allowed(column):
    df = payment_frame([VALID_ORDER])
    df[column] = "2147483647"

    clean, rejected = transform_order_payments(df)

    assert len(clean) == 1
    assert rejected.empty
    assert clean[column].tolist() == [2147483647]
