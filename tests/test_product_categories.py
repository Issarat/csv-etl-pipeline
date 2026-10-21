import pandas as pd

from src.configuration import get_dataset_config
from src.transform import transform_products


def product_frame(data):
    frame = pd.DataFrame(data)
    for column in get_dataset_config("products").numeric_columns:
        if column not in frame:
            frame[column] = "1"
    return frame


def test_cleans_products_and_retains_category_names_without_mapping():
    products = product_frame({
        "product_id": [" a ", "b"],
        "product_category_name": ["books", None],
        "product_weight_g": [" 12 ", "5"],
    })
    products.index = [9, 9]
    original = products.copy(deep=True)
    clean, rejected = transform_products(products)
    assert rejected.empty
    assert clean.product_id.tolist() == ["a", "b"]
    assert clean.product_weight_g.tolist() == [12, 5]
    assert clean.product_category_name.iloc[0] == "books"
    assert pd.isna(clean.product_category_name.iloc[1])
    assert "product_category_id" not in clean
    assert clean.index.tolist() == [9, 9]
    pd.testing.assert_frame_equal(products, original)


def test_shared_rules_reject_invalid_missing_and_duplicate_values():
    products = product_frame({
        "product_id": ["a", "b", "c", "d", "d", " "],
        "product_category_name": ["books"] * 6,
        "product_weight_g": ["12", None, "bad", "2", "3", "4"],
    })
    clean, rejected = transform_products(products)
    assert clean.product_id.tolist() == ["a", "b"]
    assert pd.isna(clean.product_weight_g.iloc[1])
    assert rejected.rejection_reason.tolist() == [
        "invalid_product_weight_g",
        "duplicate_product_id", "duplicate_product_id", "missing_product_id",
    ]
    assert rejected.raw_product_weight_g.tolist() == ["bad", "2", "3", "4"]
    assert len(clean) + len(rejected) == len(products)


def test_all_product_numeric_columns_allow_null_and_blank_but_reject_invalid():
    products = product_frame({"product_id": ["null", "blank", "bad"], "product_category_name": [None] * 3})
    for column in get_dataset_config("products").numeric_columns:
        products[column] = [None, "  ", "invalid"]
    clean, rejected = transform_products(products)
    assert clean.product_id.tolist() == ["null", "blank"]
    for column in get_dataset_config("products").numeric_columns:
        assert clean[column].isna().all()
        assert f"invalid_{column}" in rejected.rejection_reason.iloc[0]
