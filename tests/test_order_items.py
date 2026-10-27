from uuid import UUID

import pandas as pd
import pytest

from src.transform import transform_order_items


def item_frame():
    return pd.DataFrame([{
        "order_id": "00010242fe8c5a6d1ba2dd792cb16214",
        "order_item_id": "1",
        "product_id": "4244733e06e7ecb4970a6e2683c13e61",
        "seller_id": "48436dade18ac8b2bce089ec2a041202",
        "shipping_limit_date": "2017-09-19 09:45:35",
        "price": "0",
        "freight_value": "0",
    }])


def test_normalizes_uuid_references_and_preserves_integer_item_id():
    df = item_frame()
    original = df.copy(deep=True)
    clean, rejected = transform_order_items(df)
    assert rejected.empty
    assert pd.api.types.is_integer_dtype(clean.order_item_id)
    assert clean.order_item_id.tolist() == [1]
    for column in ("order_id", "product_id", "seller_id"):
        assert clean[column].iloc[0] == str(UUID(df[column].iloc[0]))
    pd.testing.assert_frame_equal(df, original)


@pytest.mark.parametrize("column", ["order_id", "product_id", "seller_id"])
def test_invalid_uuid_is_rejected_without_crashing(column):
    df = item_frame()
    df[column] = "not-a-uuid"
    clean, rejected = transform_order_items(df)
    assert clean.empty
    assert rejected.rejection_reason.tolist() == [f"invalid_{column}"]
    assert rejected[f"raw_{column}"].tolist() == ["not-a-uuid"]


@pytest.mark.parametrize("value", ["abc", "0", "-1", "1.5", "inf", "2147483648"])
def test_invalid_integer_item_id_is_rejected(value):
    df = item_frame()
    df["order_item_id"] = value
    clean, rejected = transform_order_items(df)
    assert clean.empty
    assert rejected.rejection_reason.tolist() == ["invalid_order_item_id"]
    assert rejected.raw_order_item_id.tolist() == [value]


@pytest.mark.parametrize("column", ["price", "freight_value"])
@pytest.mark.parametrize("value", ["-0.01", "inf", "-inf", "bad"])
def test_invalid_amount_is_rejected(column, value):
    df = item_frame()
    df[column] = value
    clean, rejected = transform_order_items(df)
    assert clean.empty
    assert rejected.rejection_reason.tolist() == [f"invalid_{column}"]


def test_duplicate_keys_are_detected_after_uuid_and_integer_normalization():
    df = pd.concat([item_frame(), item_frame()], ignore_index=True)
    df.loc[1, "order_id"] = str(UUID(df.loc[0, "order_id"]))
    df.loc[1, "order_item_id"] = "1.0"
    clean, rejected = transform_order_items(df)
    assert clean.empty
    assert rejected.rejection_reason.tolist() == ["duplicate_order_item_key"] * 2
