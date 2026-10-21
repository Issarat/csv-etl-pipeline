import pandas as pd

from src.configuration import DatasetConfig, get_dataset_config

# region Data Transformation Functions
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
    for column in config.id_columns + config.text_columns:
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
    
    # Delivery date is optional. Preserve the existing reason names/order.
    result["order_status"] = (
        result["order_status"].astype("string").str.strip().str.lower()
    )
    
    purchase = "order_purchase_timestamp"
    delivery = "order_delivered_customer_date"

    return {
        "missing_order_id": result["order_id"].fillna("").eq(""),
        "missing_customer_id": result["customer_id"].fillna("").eq(""),
        "invalid_status": ~result["order_status"].isin(config.valid_statuses),
        "missing_purchase_date": ~present[purchase],
        "invalid_purchase_date": present[purchase] & result[purchase].isna(),
        "invalid_delivery_date": present[delivery] & result[delivery].isna(),
    }

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
        rules[f"missing_{column}"] = ~present[column]
        rules[f"invalid_{column}"] = present[column] & result[column].isna()

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
    rule_builder = _orders_rules if dataset_name == "orders" else _required_field_rules
    rules = rule_builder(result, present, config)
    key_present = pd.Series(True, index=result.index)

    # ตรวจสอบว่ามีค่าใน key_columns ครบหรือไม่ และ เช็คว่ามีค่าใน key_columns ครบหรือไม่
    for column in config.key_columns:
        key_present &= result[column].fillna("").ne("")

    # ตรวจสอบ duplicate key และเพิ่ม rejection reason
    if config.key_columns:
        rules[config.duplicate_reason] = (
            key_present
            & result.duplicated(subset=list(config.key_columns), keep=False)
        )
    return _split_records(result, raw_values, rules, df.index.copy())
# endregion

def transform_orders(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Normalize orders; delivery dates may be empty but must parse if given."""
    return _transform_dataset(df, "orders")


def transform_order_items(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reject all occurrences of duplicate (order_id, order_item_id) keys."""
    return _transform_dataset(df, "order_items")


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
