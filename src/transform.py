from collections.abc import Callable
from uuid import NAMESPACE_URL, UUID, uuid5

import pandas as pd

from src.configuration import DatasetConfig, get_dataset_config

# region Data Transformation Functions
Rules = dict[str, pd.Series]
POSTGRES_INTEGER_MAX = 2_147_483_647
RuleBuilder = Callable[
    [pd.DataFrame, dict[str, pd.Series], DatasetConfig],
    Rules,
]


def _get_rules_builder(dataset_name: str) -> RuleBuilder:
    match dataset_name:
        case "orders":
            return _orders_rules
        case _:
            return _required_field_rules


def _get_addition_rules(
    dataset_name: str,
    result: pd.DataFrame,
    raw_values: pd.DataFrame,
    present: dict[str, pd.Series],
    config: DatasetConfig,
    rules: Rules,
) -> Rules:
    match dataset_name:
        case "order_items":
            return _order_items_rules(
                result,
                raw_values,
                present,
                config,
                rules,
            )
        case "order_payments":
            return _order_payments_rules(
                result,
                raw_values,
                present,
                config,
                rules,
            )
        case "order_reviews":
            return _order_reviews_rules(
                result,
                raw_values,
                present,
                config,
                rules,
            )
        case _:
            return rules


def _prepare_data(df: pd.DataFrame, config: DatasetConfig) -> pd.DataFrame:

    #1. เช็คว่ามีคอลัมน์ ที่ set required_columns ว่าครบหรือไม่
    missing = set(config.required_columns) - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    
    #2. ตรวจสอบว่ามีคอลัมน์ reserved อยู่แล้วหรือไม่
    conflicts = config.reserved_columns & set(df.columns)
    if conflicts:
        raise ValueError(f"Reserved columns already exist: {sorted(conflicts)}")

    #3. copy ข้อมูล และ reset index 
    result = df.copy().reset_index(drop=True)
    
    #4. cleaning id_columns และ text_columns เป็น string และ strip whitespace
    for column in config.id_columns + config.text_columns + config.optional_text_columns:
        result[column] = result[column].astype("string").str.strip()

    return result

def _convert_values(
    result: pd.DataFrame,
    config: DatasetConfig,
) -> tuple[pd.DataFrame, dict[str, pd.Series]]:

    #1. get ค่า date_columns และ numeric_columns และ copy ข้อมูลไปเก็บไว้ใน raw_values
    columns = config.date_columns + config.numeric_columns
    raw_values = result.loc[:, list(columns)].copy()

    #2. สร้าง dictionary present เพื่อเก็บข้อมูลว่า column นั้นมีค่าหรือไม่
    present = {}
    for column in columns:
        #3. convert ค่าใน column เป็น string และ strip whitespace check ว่ามีค่าหรือไม่ ถ้ามีค่าก็ convert เป็น datetime หรือ numeric ตาม column type
        text = raw_values[column].astype("string").str.strip()
        present[column] = text.fillna("").ne("")
        values = text.where(present[column])
        converter = (
            pd.to_datetime if column in config.date_columns else pd.to_numeric
        )
        result[column] = converter(values, errors="coerce")

    return raw_values, present

def _orders_rules(
    result: pd.DataFrame,
    present: dict[str, pd.Series],
    config: DatasetConfig,
) -> dict[str, pd.Series]:
    
    # Purchase date is required; other dates may be empty but must parse if given.
    result["order_status"] = (
        result["order_status"].astype("string").str.strip().str.lower()
    )
    
    purchase = "order_purchase_timestamp"
    delivery = "order_delivered_customer_date"

    rules = {
        "missing_order_id": result["order_id"].fillna("").eq(""),
        "missing_customer_id": result["customer_id"].fillna("").eq(""),
        "invalid_status": ~result["order_status"].isin(config.valid_statuses),
        "missing_purchase_date": ~present[purchase],
        "invalid_purchase_date": present[purchase] & result[purchase].isna(),
        "invalid_delivery_date": present[delivery] & result[delivery].isna(),
    }
    for column in config.date_columns:
        if column not in (purchase, delivery):
            rules[f"invalid_{column}"] = present[column] & result[column].isna()
    return rules

def _required_field_rules(
    result: pd.DataFrame,
    present: dict[str, pd.Series],
    config: DatasetConfig,
) -> dict[str, pd.Series]:
    rules = {
        f"missing_{column}": result[column].fillna("").eq("")
        for column in config.id_columns + config.text_columns
    }

    for column in config.date_columns + config.numeric_columns:
        if column not in config.nullable_numeric_columns:
            rules[f"missing_{column}"] = ~present[column]
        rules[f"invalid_{column}"] = present[column] & result[column].isna()

    return rules


def _uuid_rules(
    result: pd.DataFrame,
    raw_values: pd.DataFrame,
    config: DatasetConfig,
    rules: Rules,
) -> Rules:
    for column in config.id_columns:
        raw_values[column] = result[column].copy()
        normalized = []
        for value in result[column]:
            try:
                normalized.append(str(UUID(value)))
            except (ValueError, TypeError, AttributeError):
                normalized.append(pd.NA)

        normalized_values = pd.Series(
            normalized,
            index=result.index,
            dtype="string",
        )
        rules[f"invalid_{column}"] = (
            result[column].fillna("").ne("")
            & normalized_values.isna()
        )
        result[column] = normalized_values

    return rules


def _order_items_rules(
    result: pd.DataFrame,
    _raw_values: pd.DataFrame,
    present: dict[str, pd.Series],
    _config: DatasetConfig,
    rules: Rules,
) -> dict[str, pd.Series]:
    #set floor data base
    for column, minimum in (("order_item_id", 1), ("price", 0), ("freight_value", 0)):
        invalid = result[column].lt(minimum) | result[column].isin([float("inf"), float("-inf")])
        if column == "order_item_id":
            invalid |= result[column].notna() & (
                result[column].mod(1).ne(0)
                | result[column].gt(POSTGRES_INTEGER_MAX)
            )
        rules[f"invalid_{column}"] |= present[column] & invalid

    return rules

def _order_payments_rules(
    result: pd.DataFrame,
    _raw_values: pd.DataFrame,
    present: dict[str, pd.Series],
    config: DatasetConfig,
    rules: Rules,
) -> dict[str, pd.Series]:
    result["payment_type"] = result["payment_type"].astype("string").str.strip().str.lower()
    rules["invalid_payment_type"] = ~result["payment_type"].isin(config.valid_payment_types)

    for column, minimum in (("payment_sequential", 1), ("payment_installments", 0), ("payment_value", 0)):
        invalid = result[column].lt(minimum) | result[column].isin([float("inf"), float("-inf")])
        if column != "payment_value":
            invalid |= result[column].notna() & (
                result[column].mod(1).ne(0)
                | result[column].gt(POSTGRES_INTEGER_MAX)
            )
        rules[f"invalid_{column}"] |= present[column] & invalid

    return rules


def _order_reviews_rules(
    result: pd.DataFrame,
    _raw_values: pd.DataFrame,
    present: dict[str, pd.Series],
    _config: DatasetConfig,
    rules: Rules,
) -> Rules:
    rules["invalid_review_score"] |= (
        present["review_score"]
        & ~result["review_score"].isin([1, 2, 3, 4, 5])
    )

    return rules

def _split_records(
    result: pd.DataFrame,
    raw_values: pd.DataFrame,
    rules: dict[str, pd.Series],
    original_index: pd.Index,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    
    reasons = pd.Series("", index=result.index, dtype="string")

    for reason, mask in rules.items():
        reasons.loc[mask] = reasons.loc[mask] + reason + ";"

    reasons = reasons.str.rstrip(";")
    invalid = reasons.ne("")
    clean_df = result.loc[~invalid].copy()
    rejected_df = result.loc[invalid].copy()
    rejected_df["rejection_reason"] = reasons.loc[invalid]

    for column in raw_values.columns:
        rejected_df[f"raw_{column}"] = raw_values.loc[invalid, column]

    clean_df.index = original_index[~invalid.to_numpy(dtype=bool)]
    rejected_df.index = original_index[invalid.to_numpy(dtype=bool)]

    return clean_df, rejected_df

def _transform_dataset(
    df: pd.DataFrame,
    dataset_name: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    config = get_dataset_config(dataset_name)
    result = _prepare_data(df, config)
    raw_values, present = _convert_values(result, config)
    rule_builder = _get_rules_builder(dataset_name)
    rules = rule_builder(result, present, config)
    rules = _uuid_rules(result, raw_values, config, rules)
    rules = _get_addition_rules(
        dataset_name,
        result,
        raw_values,
        present,
        config,
        rules,
    )

    key_present = pd.Series(True, index=result.index)

    # ตรวจสอบว่ามีค่าใน key_columns ครบหรือไม่ และ เช็คว่ามีค่าใน key_columns ครบหรือไม่
    for column in config.key_columns:
        key_present &= result[column].astype("string").fillna("").ne("")

    # ตรวจสอบ duplicate key และเพิ่ม rejection reason
    if config.key_columns:
        rules[config.duplicate_reason] = (
            key_present
            & result.duplicated(subset=list(config.key_columns), keep=False)
        )
    return _split_records(result, raw_values, rules, df.index.copy())
# endregion

def transform_orders(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Normalize orders; only purchase dates are required, but all dates must parse."""
    return _transform_dataset(df, "orders")


def transform_order_items(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate UUID references, positive integer item IDs, and nonnegative amounts."""
    clean, rejected = _transform_dataset(df, "order_items")
    clean["order_item_id"] = clean["order_item_id"].astype("int64")
    return clean, rejected


def transform_customers(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reject duplicate customer_id; customer_unique_id may repeat."""
    return _transform_dataset(df, "customers")

def transform_products(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Clean products using shared dataset rules; retain category names for validation."""
    return _transform_dataset(df, "products")


def transform_product_categories(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Clean category names before validation assigns IDs; English names may be null."""
    return _transform_dataset(df, "product_categories")


def transform_geolocation(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Preserve ZIP prefixes as strings and allow multiple locations per prefix."""
    return _transform_dataset(df, "geolocation")


def transform_sellers(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Clean the four seller columns while preserving ZIP prefixes as strings."""
    return _transform_dataset(df, "sellers")


def transform_order_reviews(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Clean reviews; comments are optional and scores must be integers from 1 to 5."""
    if "review_id" in df.columns:
        if "order_review_id" in df.columns:
            raise ValueError("Both review_id and order_review_id are present")
        df = df.rename(columns={"review_id": "order_review_id"})
    return _transform_dataset(df, "order_reviews")


def transform_order_payments(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Clean payments and assign stable UUIDs from their natural payment keys."""
    clean, rejected = _transform_dataset(df, "order_payments")
    clean.insert(0, "order_payments_id", pd.array([
        str(uuid5(NAMESPACE_URL, f"olist/order_payments/{UUID(str(order_id))}/{int(sequential)}"))
        for order_id, sequential in zip(clean["order_id"], clean["payment_sequential"])
    ], dtype="string"))
    return clean, rejected
