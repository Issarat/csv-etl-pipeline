import pandas as pd
import pytest
from src import pipeline
from unittest.mock import Mock
from src.quality import (
    validate_customers, 
    validate_sellers
)



def test_valid_customers_pass():
    df = pd.DataFrame({
        "customer_id": ["customer-001", "customer-002"],
        "customer_state": ["SP", "RJ"],
    })

    validate_customers(df)


@pytest.mark.parametrize(
    "customer_ids, states",
    [
        # ID ว่าง
        ([None, "customer-002"], ["SP", "RJ"]),

        # ID ซ้ำ
        (["customer-001", "customer-001"], ["SP", "RJ"]),

        # State ผิดรูปแบบ
        (["customer-001", "customer-002"], ["Sao Paulo", "RJ"]),
    ],
    ids=["null-id", "duplicate-id", "invalid-state"],
)
def test_invalid_customers_fail(customer_ids, states):
    df = pd.DataFrame({
        "customer_id": customer_ids,
        "customer_state": states,
    })

    with pytest.raises(ValueError, match="Customers quality check failed"):
        validate_customers(df)

@pytest.mark.parametrize("valid", [False, True], ids=["blocked", "allowed"])
def test_customer_quality_gates_loading(monkeypatch, valid):
    # Run the real GX validator; replace only logging and database writes.
    upsert = Mock()
    monkeypatch.setattr(pipeline, "upsert_dataframe", upsert)
    monkeypatch.setattr(pipeline, "get_logger", Mock(return_value=Mock()))
    df = pd.DataFrame({
        "customer_id": ["customer-001" if valid else None],
        "customer_state": ["SP"],
    })

    if valid:
        pipeline._load_dataset("customers", df)
        upsert.assert_called_once_with(
            df=df,
            table_name="customers",
            conflict_columns=("customer_id",),
        )
    else:
        with pytest.raises(ValueError, match="Customers quality check failed"):
            pipeline._load_dataset("customers", df)
        upsert.assert_not_called()

def test_valid_sellers_pass():
    df = pd.DataFrame({
        "seller_id": ["customer-001", "customer-002"],
        "seller_zip_code_prefix": ["10101", "01010"],
        "seller_state": ["SP", "RJ"],
    })

    validate_sellers(df)

@pytest.mark.parametrize(
    "seller_id, zipcode,  states",
    [
        # ID ว่าง
        ([None, "customer-002"], ["10101", "01010"], ["SP", "RJ"]),

        # ID ซ้ำ
        (["customer-001", "customer-001"], ["10101", "01010"], ["SP", "RJ"]),

        # Zizcode ว่าง
        (["customer-001", "customer-002"], ["10101", None], ["SP", "RJ"]),

        # Zizcode ผิดรูปแบบ
        (["customer-001", "customer-002"], ["10101", "010101"], ["SP", "RJ"]),

        # State ว่าง
        (["customer-001", "customer-002"], ["10101", "01010"], [None, "RJ"]),

        # State ผิดรูปแบบ
        (["customer-001", "customer-002"], ["10101", "01010"], ["Sao Paulo", "RJ"]),
    ],
    ids=["null-id", "duplicate-id", "null-zip-code", "invalid-zip-code", "null-state", "invalid-state"],
)
def test_invalid_sellers_fail(seller_id, zipcode, states):
    df = pd.DataFrame({
        "seller_id": seller_id,
        "seller_zip_code_prefix": zipcode,
        "seller_state": states
    })

    with pytest.raises(ValueError, match="Sellers quality check failed"):
        validate_sellers(df)


@pytest.mark.parametrize("valid", [False, True], ids=["blocked", "allowed"])
def test_seller_quality_gates_loading(monkeypatch, valid):
    # Run the real GX validator; replace only logging and database writes.
    upsert = Mock()
    monkeypatch.setattr(pipeline, "upsert_dataframe", upsert)
    monkeypatch.setattr(pipeline, "get_logger", Mock(return_value=Mock()))
    df = pd.DataFrame({
        "seller_id": ["customer-001" if valid else None],
        "seller_zip_code_prefix": "10101",
        "seller_state": ["SP"],
    })

    if valid:
        pipeline._load_dataset("sellers", df)
        upsert.assert_called_once_with(
            df=df,
            table_name="sellers",
            conflict_columns=("seller_id",),
        )
    else:
        with pytest.raises(ValueError, match="Sellers quality check failed"):
            pipeline._load_dataset("sellers", df)
        upsert.assert_not_called()


@pytest.mark.parametrize("dataset", ["orders", "order_items", "order_payments", "order_reviews", "products", "product_categories", "geolocation"])
@pytest.mark.parametrize("valid", [True, False], ids=["allowed", "blocked"])
def test_all_dataset_quality_gates(monkeypatch, dataset, valid):
    from src.configuration import get_dataset_config
    from src.transform import NUMBERIC_COLUMNS
    from decimal import Decimal

    config = get_dataset_config(dataset)
    row = {column: "example" for column in config.required_columns}
    for column in config.date_columns:
        row[column] = pd.Timestamp("2026-01-01")
    for column in config.numeric_columns:
        row[column] = Decimal("1.00") if column in NUMBERIC_COLUMNS else 1
    if dataset == "orders":
        row["order_status"] = "delivered"
    if dataset == "order_payments":
        row["payment_type"] = "credit_card"
    if dataset == "products":
        del row["product_category_name"]
        row["product_category_id"] = None  # Nullable category is supported.
    if dataset == "geolocation":
        del row["geolocation_zip_code_prefix"]
        row.update(zip_code="01234", geolocation_id=1, geolocation_state="SP")
    key = config.key_columns[0] if config.key_columns else "geolocation_id"
    if not valid:
        row[key] = None
    df = pd.DataFrame([row])
    upsert, replace = Mock(), Mock()
    monkeypatch.setattr(pipeline, "upsert_dataframe", upsert)
    monkeypatch.setattr(pipeline, "replace_geolocation", replace)
    monkeypatch.setattr(pipeline, "find_missing_reference_ids", Mock(return_value=[]))
    monkeypatch.setattr(pipeline, "get_logger", Mock(return_value=Mock()))
    if valid:
        pipeline._load_dataset(dataset, df)
        (replace if dataset == "geolocation" else upsert).assert_called_once()
    else:
        with pytest.raises(ValueError, match="quality check failed"):
            pipeline._load_dataset(dataset, df)
        upsert.assert_not_called()
        replace.assert_not_called()


@pytest.mark.parametrize("change", ["negative", "fraction", "duplicate", "missing-column", "bad-type"])
def test_payment_quality_rejects_invalid_values(change):
    from src.quality import validate_dataset
    df = pd.DataFrame({
        "order_id": ["order-1", "order-1"],
        "payment_sequential": [1, 2],
        "payment_installments": [0, 1],
        "payment_value": [0, 10],
        "payment_type": ["credit_card", "voucher"],
    })
    if change == "negative":
        df.loc[0, "payment_value"] = -1
    elif change == "fraction":
        df["payment_sequential"] = [1.5, 2]
    elif change == "duplicate":
        df["payment_sequential"] = [1, 1]
    elif change == "missing-column":
        df = df.drop(columns="payment_value")
    else:
        df.loc[0, "payment_type"] = "unknown"
    with pytest.raises(ValueError, match="quality check failed"):
        validate_dataset("order_payments", df)
