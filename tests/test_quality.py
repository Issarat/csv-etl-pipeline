import pandas as pd
import pytest

from src.quality import validate_customers
from src import pipeline
from unittest.mock import Mock


def test_valid_customers_pass():
    df = pd.DataFrame({
        "customer_id": ["customer-001", "customer-002"],
        "customer_state": ["SP", "RJ"],
    })

    # ข้อมูลถูกต้อง ต้องไม่เกิด exception
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
