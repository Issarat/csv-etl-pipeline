from uuid import UUID

import pandas as pd
import pytest

from src.transform import transform_customers, transform_sellers


CUSTOMER_ID = "00000000000000000000000000000021"
CUSTOMER_UNIQUE_ID = "00000000000000000000000000000022"
SELLER_ID = "00000000000000000000000000000023"


def customer_frame() -> pd.DataFrame:
    return pd.DataFrame([{
        "customer_id": CUSTOMER_ID,
        "customer_unique_id": CUSTOMER_UNIQUE_ID,
        "customer_zip_code_prefix": "01001",
        "customer_city": "sao paulo",
        "customer_state": "SP",
    }])


def seller_frame() -> pd.DataFrame:
    return pd.DataFrame([{
        "seller_id": SELLER_ID,
        "seller_zip_code_prefix": "01001",
        "seller_city": "sao paulo",
        "seller_state": "SP",
    }])


@pytest.mark.parametrize(
    ("transformer", "frame_factory", "expected_ids"),
    [
        (
            transform_customers,
            customer_frame,
            {
                "customer_id": str(UUID(CUSTOMER_ID)),
                "customer_unique_id": str(UUID(CUSTOMER_UNIQUE_ID)),
            },
        ),
        (
            transform_sellers,
            seller_frame,
            {"seller_id": str(UUID(SELLER_ID))},
        ),
    ],
)
def test_uuid_columns_are_normalized(transformer, frame_factory, expected_ids):
    clean, rejected = transformer(frame_factory())

    assert rejected.empty
    for column, expected in expected_ids.items():
        assert clean[column].tolist() == [expected]


@pytest.mark.parametrize(
    ("transformer", "frame_factory", "column"),
    [
        (transform_customers, customer_frame, "customer_id"),
        (transform_customers, customer_frame, "customer_unique_id"),
        (transform_sellers, seller_frame, "seller_id"),
    ],
)
def test_invalid_uuid_is_rejected(transformer, frame_factory, column):
    frame = frame_factory()
    frame[column] = "not-a-uuid"

    clean, rejected = transformer(frame)

    assert clean.empty
    assert rejected["rejection_reason"].tolist() == [f"invalid_{column}"]
    assert rejected[f"raw_{column}"].tolist() == ["not-a-uuid"]
