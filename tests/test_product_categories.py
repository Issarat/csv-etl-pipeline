from uuid import UUID

import pandas as pd
import pytest

from src.configuration import get_dataset_config
from src.transform import transform_products


PRODUCT_A = "00000000000000000000000000000001"
PRODUCT_B = "00000000000000000000000000000002"
PRODUCT_C = "00000000000000000000000000000003"
PRODUCT_D = "00000000000000000000000000000004"


def product_frame(data):
    frame = pd.DataFrame(data)
    for column in get_dataset_config("products").numeric_columns:
        if column not in frame:
            frame[column] = "1"
    return frame


def test_products_require_all_source_columns():
    products = pd.DataFrame({
        "product_id": ["a"],
        "product_category_name": ["books"],
    })

    with pytest.raises(ValueError, match="Missing columns"):
        transform_products(products)


def test_cleans_products_and_retains_category_names_without_mapping():
    products = product_frame({
        "product_id": [f" {PRODUCT_A} ", PRODUCT_B],
        "product_category_name": ["books", None],
        "product_weight_g": [" 12 ", "5"],
    })
    products.index = [9, 9]
    original = products.copy(deep=True)
    clean, rejected = transform_products(products)
    assert rejected.empty
    assert clean.product_id.tolist() == [
        str(UUID(PRODUCT_A)),
        str(UUID(PRODUCT_B)),
    ]
    assert clean.product_weight_g.tolist() == [12, 5]
    assert clean.product_category_name.iloc[0] == "books"
    assert pd.isna(clean.product_category_name.iloc[1])
    assert "product_category_id" not in clean
    assert clean.index.tolist() == [9, 9]
    pd.testing.assert_frame_equal(products, original)


def test_shared_rules_reject_invalid_missing_and_duplicate_values():
    products = product_frame({
        "product_id": [
            PRODUCT_A,
            PRODUCT_B,
            PRODUCT_C,
            PRODUCT_D,
            str(UUID(PRODUCT_D)).upper(),
            " ",
        ],
        "product_category_name": ["books"] * 6,
        "product_weight_g": ["12", None, "bad", "2", "3", "4"],
    })
    clean, rejected = transform_products(products)
    assert clean.product_id.tolist() == [
        str(UUID(PRODUCT_A)),
        str(UUID(PRODUCT_B)),
    ]
    assert pd.isna(clean.product_weight_g.iloc[1])
    assert rejected.rejection_reason.tolist() == [
        "invalid_product_weight_g",
        "duplicate_product_id", "duplicate_product_id", "missing_product_id",
    ]
    assert rejected.raw_product_weight_g.tolist() == ["bad", "2", "3", "4"]
    assert len(clean) + len(rejected) == len(products)


def test_all_product_numeric_columns_allow_null_and_blank_but_reject_invalid():
    products = product_frame({
        "product_id": [PRODUCT_A, PRODUCT_B, PRODUCT_C],
        "product_category_name": [None] * 3,
    })
    for column in get_dataset_config("products").numeric_columns:
        products[column] = [None, "  ", "invalid"]
    clean, rejected = transform_products(products)
    assert clean.product_id.tolist() == [
        str(UUID(PRODUCT_A)),
        str(UUID(PRODUCT_B)),
    ]
    for column in get_dataset_config("products").numeric_columns:
        assert clean[column].isna().all()
        assert f"invalid_{column}" in rejected.rejection_reason.iloc[0]

@pytest.mark.parametrize(
    "value",
    [-0.001, -1, 9999999999.999, 10000000001, float("inf"), float("-inf")],
)

def test_out_of_range_product_weight_g_is_rejected(value):
    df = product_frame({
        "product_id": [PRODUCT_A],
        "product_category_name": ["books"],
        "product_weight_g": [value],
    })
    clean, rejected = transform_products(df)
    assert clean.empty
    assert rejected["rejection_reason"].tolist() == ["invalid_product_weight_g"]
    assert len(rejected) == 1
    assert rejected["raw_product_weight_g"].tolist() == [value]
    assert len(clean) + len(rejected) == len(df)

@pytest.mark.parametrize(
    "value",
    [0, 9999999999.99],
)
def test_valid_product_weight_g_is_allowed(value):
    df = product_frame({
        "product_id": [PRODUCT_A],
        "product_category_name": ["books"],
        "product_weight_g": [value],
    })
    clean, rejected = transform_products(df)

    assert len(clean) == 1
    assert rejected.empty
    assert len(clean) + len(rejected) == len(df)
    assert clean["product_weight_g"].tolist() == [value]

@pytest.mark.parametrize(
    "value, expected",
    [
        (12.344, 12.34),
        (12.346, 12.35),
    ],
)
def test_product_weight_is_rounded_to_two_decimal_places(value, expected):
    df = product_frame({
        "product_id": [PRODUCT_A],
        "product_category_name": ["books"],
        "product_weight_g": [value],
    })
    original = df.copy(deep=True)
    clean, rejected = transform_products(df)

    assert len(clean) == 1
    assert rejected.empty
    assert len(clean) + len(rejected) == len(df)
    assert clean["product_weight_g"].tolist() == [expected]
    pd.testing.assert_frame_equal(df, original)

@pytest.mark.parametrize(
    "column",
    [
        "product_photos_qty",
        "product_name_lenght",
        "product_description_lenght",
    ],
)
@pytest.mark.parametrize("value", [1.5, 2147483648])    
def test_invalid_product_integer_is_rejected(column, value):
    df = product_frame({
        "product_id": [PRODUCT_A],
        "product_category_name": ["books"],
        column: [value],
    })
    original = df.copy(deep=True)
    clean, rejected = transform_products(df)

    assert clean.empty
    assert len(rejected) == 1
    assert len(clean) + len(rejected) == len(df)
    assert rejected["rejection_reason"].tolist() == [f"invalid_{column}"]
    assert rejected[f"raw_{column}"].tolist() == [value]
    pd.testing.assert_frame_equal(df, original)

@pytest.mark.parametrize(
    "column",
    [
        "product_photos_qty",
        "product_name_lenght",
        "product_description_lenght",
    ],
)
@pytest.mark.parametrize(
    "value",
    [0, 2147483647],
)
def test_valid_product_integer_is_allowed(column, value):
    df = product_frame({
        "product_id": [PRODUCT_A],
        "product_category_name": ["books"],
        column: [value],
    })
    clean, rejected = transform_products(df)

    assert len(clean) == 1
    assert rejected.empty
    assert len(clean) + len(rejected) == len(df)
    assert clean[column].tolist() == [value]