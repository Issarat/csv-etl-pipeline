from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data"

def get_dataset_paths(dataset_name: str):
    return {
        "raw": (
            DATA_PATH / "raw"
            / f"olist_{dataset_name}_dataset.csv"
        ),
        "clean": (
            DATA_PATH / "clean"
            / f"olist_{dataset_name}_clean.csv"
        ),
        "rejected": (
            DATA_PATH / "rejected"
            / f"olist_{dataset_name}_rejected.csv"
        ),
    }

@dataclass(frozen=True)
class DatasetConfig:
    required_columns: tuple[str, ...]
    id_columns: tuple[str, ...] = ()
    text_columns: tuple[str, ...] = ()
    date_columns: tuple[str, ...] = ()
    numeric_columns: tuple[str, ...] = ()
    key_columns: tuple[str, ...] = ()
    duplicate_reason: str = ""
    reserved_columns: frozenset[str] = frozenset()
    valid_statuses: frozenset[str] = frozenset()


_DATASET_CONFIGS = {
    "orders": DatasetConfig(
        required_columns=('order_id', 'customer_id', 'order_status', 'order_purchase_timestamp', 'order_delivered_customer_date'),
        id_columns=('order_id', 'customer_id'),
        date_columns=('order_purchase_timestamp', 'order_delivered_customer_date'),
        reserved_columns=frozenset(('raw_order_delivered_customer_date', 'raw_order_purchase_timestamp', 'rejection_reason')),
        valid_statuses=frozenset(('approved', 'canceled', 'created', 'delivered', 'invoiced', 'processing', 'shipped', 'unavailable')),
        key_columns=('order_id',),
        duplicate_reason='duplicate_order_id',
    ),
    "order_items": DatasetConfig(
        required_columns=('order_id', 'order_item_id', 'product_id', 'seller_id', 'shipping_limit_date', 'price', 'freight_value'),
        id_columns=('order_id', 'order_item_id', 'product_id', 'seller_id'),
        text_columns=(),
        date_columns=('shipping_limit_date',),
        numeric_columns=('price', 'freight_value'),
        key_columns=('order_id', 'order_item_id'),
        duplicate_reason='duplicate_order_item_key',
        reserved_columns=frozenset(('raw_freight_value', 'raw_price', 'raw_shipping_limit_date', 'rejection_reason')),
    ),
    "customers": DatasetConfig(
        required_columns=('customer_id', 'customer_unique_id', 'customer_zip_code_prefix', 'customer_city', 'customer_state'),
        id_columns=('customer_id', 'customer_unique_id'),
        text_columns=('customer_city', 'customer_state'),
        date_columns=(),
        numeric_columns=('customer_zip_code_prefix',),
        key_columns=('customer_id',),
        duplicate_reason='duplicate_customer_id',
        reserved_columns=frozenset(('raw_customer_zip_code_prefix', 'rejection_reason')),
    ),
}


def get_dataset_config(dataset_name: str) -> DatasetConfig:
    try:
        return _DATASET_CONFIGS[dataset_name]
    except KeyError:
        raise ValueError(f"Unsupported dataset: {dataset_name}") from None
