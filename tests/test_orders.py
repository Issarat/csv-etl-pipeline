import pandas as pd
import pytest

from src.configuration import get_dataset_config
from src.transform import transform_orders


def order_frame():
    row = {column: None for column in get_dataset_config("orders").required_columns}
    row.update(order_id="a", customer_id="b", order_status=" CREATED ",
               order_purchase_timestamp="2020-01-01 10:00:00")
    return pd.DataFrame([row])


def test_optional_dates_allow_null_and_blanks_and_convert_valid_values():
    df = order_frame()
    df["order_approved_at"] = "  "
    df["order_delivered_carrier_date"] = "2020-01-02 12:00:00"
    original = df.copy(deep=True)
    clean, rejected = transform_orders(df)
    assert len(clean) == 1 and rejected.empty
    assert clean.order_status.iloc[0] == "created"
    for column in get_dataset_config("orders").date_columns:
        assert pd.api.types.is_datetime64_any_dtype(clean[column])
    assert pd.isna(clean.order_approved_at.iloc[0])
    assert clean.order_delivered_carrier_date.iloc[0] == pd.Timestamp("2020-01-02 12:00:00")
    pd.testing.assert_frame_equal(df, original)


@pytest.mark.parametrize("column, reason", [
    ("order_purchase_timestamp", "invalid_purchase_date"),
    ("order_delivered_customer_date", "invalid_delivery_date"),
    ("order_approved_at", "invalid_order_approved_at"),
    ("order_delivered_carrier_date", "invalid_order_delivered_carrier_date"),
    ("order_estimated_delivery_date", "invalid_order_estimated_delivery_date"),
])
def test_supplied_invalid_dates_are_rejected_with_original_value(column, reason):
    df = order_frame()
    df[column] = "not-a-date"
    clean, rejected = transform_orders(df)
    assert clean.empty
    assert rejected.rejection_reason.tolist() == [reason]
    assert rejected[f"raw_{column}"].tolist() == ["not-a-date"]


def test_purchase_date_still_required():
    df = order_frame()
    df["order_purchase_timestamp"] = " "
    clean, rejected = transform_orders(df)
    assert clean.empty
    assert rejected.rejection_reason.tolist() == ["missing_purchase_date"]
