from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data"
SPECIAL_DATASETS = "product_categories"

def get_dataset_paths(dataset_name: str) -> dict[str, Path]:
    is_special = dataset_name == SPECIAL_DATASETS
    file_stem = dataset_name if is_special else f"olist_{dataset_name}"
    raw_filename = f"{file_stem}.csv" if is_special else f"{file_stem}_dataset.csv"

    return {
        "raw": DATA_PATH / "raw" / raw_filename,
        "clean": DATA_PATH / "clean" / f"{file_stem}_clean.csv",
        "rejected": DATA_PATH / "rejected" / f"{file_stem}_rejected.csv",
        "validated": DATA_PATH / "validate" / f"{file_stem}_validated.csv",
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
    valid_payment_types: frozenset[str] = frozenset()


_DATASET_CONFIGS = {
    "order_payments": DatasetConfig(
        required_columns=('order_id', 'payment_sequential', 'payment_type', 'payment_installments', 'payment_value'),
        id_columns=('order_id',),
        text_columns=('payment_type',),
        valid_payment_types=frozenset({'credit_card', 'boleto', 'voucher', 'debit_card', 'not_defined'}),
        numeric_columns=('payment_sequential', 'payment_installments', 'payment_value'),
        key_columns=('order_id', 'payment_sequential'),
        duplicate_reason='duplicate_order_payment_key',
        reserved_columns=frozenset({'order_payments_id', 'rejection_reason', 'raw_payment_sequential', 'raw_payment_installments', 'raw_payment_value'}),
    ),
    "sellers": DatasetConfig(
        required_columns=('seller_id', 'seller_zip_code_prefix', 'seller_city', 'seller_state'),
        id_columns=('seller_id',),
        text_columns=('seller_zip_code_prefix', 'seller_city', 'seller_state'),
        key_columns=('seller_id',),
        duplicate_reason='duplicate_seller_id',
        reserved_columns=frozenset({'rejection_reason'}),
    ),
    "geolocation": DatasetConfig(
        required_columns=('geolocation_zip_code_prefix', 'geolocation_lat', 'geolocation_lng', 'geolocation_city', 'geolocation_state'),
        text_columns=('geolocation_zip_code_prefix', 'geolocation_city', 'geolocation_state'),
        numeric_columns=('geolocation_lat', 'geolocation_lng'),
        reserved_columns=frozenset({'rejection_reason', 'raw_geolocation_lat', 'raw_geolocation_lng'}),
    ),
    "product_categories": DatasetConfig(
        required_columns=('product_category_name', 'product_category_name_english'),
        text_columns=('product_category_name',),
        key_columns=('product_category_name',),
        duplicate_reason='duplicate_product_category_name',
        reserved_columns=frozenset({'rejection_reason'}),
    ),
    "products": DatasetConfig(
        required_columns=('product_id', 'product_category_name', 'product_weight_g', 'product_length_cm', 'product_height_cm', 'product_width_cm', 'product_name_lenght', 'product_description_lenght', 'product_photos_qty'),
        id_columns=('product_id',),
        key_columns=('product_id',),
        numeric_columns=('product_weight_g', 'product_length_cm', 'product_height_cm', 'product_width_cm', 'product_name_lenght', 'product_description_lenght', 'product_photos_qty'),
        duplicate_reason='duplicate_product_id',
        reserved_columns=frozenset({'product_category_id', 'rejection_reason', 'raw_product_category_name', 'raw_product_weight_g', 'raw_product_length_cm', 'raw_product_height_cm', 'raw_product_width_cm', 'raw_product_name_lenght', 'raw_product_description_lenght', 'raw_product_photos_qty'}),
    ),
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
        text_columns=('customer_city', 'customer_state','customer_zip_code_prefix'),
        date_columns=(),
        numeric_columns=(),
        key_columns=('customer_id',),
        duplicate_reason='duplicate_customer_id',
        reserved_columns=frozenset({'rejection_reason'}),
    ),
}


def get_dataset_config(dataset_name: str) -> DatasetConfig:
    try:
        return _DATASET_CONFIGS[dataset_name]
    except KeyError:
        raise ValueError(f"Unsupported dataset: {dataset_name}") from None
