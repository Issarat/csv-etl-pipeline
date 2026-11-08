from unittest.mock import Mock, call 

import pandas as pd
import pytest
from filelock import FileLock

from src import pipeline

def test_main_uses_database_category_id_for_products(monkeypatch):
    categories = pd.DataFrame({
        "product_category_name": ["livros"],
        "product_category_name_english": ["books"],
    })
    products = pd.DataFrame({
        "product_category_name": ["livros"],
        "product_weight_g": ["1.13"],
        "product_length_cm": [None],
        "product_width_cm": [None],
        "product_height_cm": [None],
    })

    monkeypatch.setattr(pipeline, "get_logger", Mock(return_value=Mock()))
    monkeypatch.setattr(pipeline, "create_table", Mock())
    monkeypatch.setattr(pipeline, "_cleaning_dataset", Mock())
    monkeypatch.setattr(pipeline, "validate_product", Mock())
    monkeypatch.setattr(pipeline, "validate_geolocation", Mock())
    monkeypatch.setattr(pipeline, "DATA_LIST", ())
    monkeypatch.setattr(
        pipeline, "VALIDATE_LIST", ("product_categories", "products")
    )
    monkeypatch.setattr(
        pipeline, "extract_csv", Mock(side_effect=[categories, products])
    )
    monkeypatch.setattr(
        pipeline, "read_product_category_mapping", Mock(return_value={"livros": 42})
    )

    load_dataset = Mock()
    monkeypatch.setattr(pipeline, "_load_dataset", load_dataset)

    pipeline.main()
    category_call, product_call = load_dataset.call_args_list
    category_dataset, loaded_categories = category_call.args
    product_dataset, loaded_products = product_call.args

    assert (category_dataset, product_dataset) == ("product_categories", "products")
    assert "product_category_id" not in loaded_categories.columns
    assert loaded_products["product_category_id"].tolist() == [42]

def test_load_orders_stops_before_upsert_when_customer_is_missing(monkeypatch):
    orders = pd.DataFrame({"customer_id": ["A", "B", "B"]})
    check_customers = Mock(return_value={"B"})
    upsert = Mock()

    monkeypatch.setattr(pipeline, "get_logger", Mock(return_value=Mock()))
    monkeypatch.setattr(pipeline, "find_missing_reference_ids", check_customers)
    monkeypatch.setattr(pipeline, "upsert_dataframe", upsert)

    with pytest.raises(ValueError) as error:
        pipeline._load_dataset("orders", orders)

    message = str(error.value)
    assert "orders.customer_id references missing customers" in message
    assert "1 missing IDs, 2 affected orders" in message
    check_customers.assert_called_once_with(
        orders,
        table_name="customers",
        column_name="customer_id",
    )
    upsert.assert_not_called()

def test_load_order_items_stops_before_upsert_when_seller_is_missing(monkeypatch):
    items = pd.DataFrame({
        "order_id": ["order-1"],
        "product_id": ["product-1"],
        "seller_id": ["seller-1"],
    })

    check_references = Mock(side_effect=[set(), set(), {"seller-1"}])
    upsert = Mock()

    monkeypatch.setattr(pipeline, "get_logger", Mock(return_value=Mock()))
    monkeypatch.setattr(pipeline, "find_missing_reference_ids", check_references)
    monkeypatch.setattr(pipeline, "upsert_dataframe", upsert)

    with pytest.raises(
        ValueError,
        match=r"order_items\.seller_id references missing sellers",
    ) as error:
        pipeline._load_dataset("order_items", items)

    assert "1 missing IDs, 1 affected order_items" in str(error.value)
    assert check_references.call_args_list == [
        call(items, table_name="orders", column_name="order_id"),
        call(items, table_name="products", column_name="product_id"),
        call(items, table_name="sellers", column_name="seller_id"),
    ]
    upsert.assert_not_called()

def test_main_rejects_overlapping_run_and_can_run_after_unlock(
    tmp_path, monkeypatch
):
    lock_path = tmp_path / ".pipeline.lock"
    run_pipeline = Mock()

    monkeypatch.setattr(pipeline, "PIPELINE_LOCK_PATH", lock_path)
    monkeypatch.setattr(pipeline, "_run_pipeline", run_pipeline)

    with FileLock(str(lock_path)):
        with pytest.raises(
            RuntimeError, match="Another pipeline run is already in progress"
        ):
            pipeline.main()

        run_pipeline.assert_not_called()

    pipeline.main()
    run_pipeline.assert_called_once_with()