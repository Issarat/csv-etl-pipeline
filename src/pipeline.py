from pathlib import Path

import pandas as pd

from src.logger import get_logger
from src.configuration import get_dataset_config, get_dataset_paths
from src.extract import extract_csv
from src.validate import validate_product, validate_geolocation
from src.transform import (
    transform_orders,
    transform_order_items,
    transform_customers,
    transform_products,
    transform_product_categories,
    transform_geolocation,
    transform_sellers,
    transform_order_payments,
    transform_order_reviews,
)
from src.load import create_table, upsert_dataframe

# Dataset order follows foreign key dependencies.
TRANSFORMERS = {
    "orders": transform_orders,
    "order_items": transform_order_items,
    "customers": transform_customers,
    "products": transform_products,
    "product_categories": transform_product_categories,
    "geolocation": transform_geolocation,
    "sellers": transform_sellers,
    "order_payments": transform_order_payments,
    "order_reviews": transform_order_reviews,
}

DATA_LIST = ("customers", "sellers", "orders", "order_payments", "order_reviews", "order_items")
VALIDATE_LIST = ("product_categories", "products", "geolocation")

def _export_csv(df: pd.DataFrame, file_path: Path) -> None:
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(file_path, index=False)


def _cleaning_dataset(dataset: str) -> pd.DataFrame:
    """Extract, transform, validate, and export a dataset; return clean records."""
    if dataset not in TRANSFORMERS:
        raise ValueError(f"No transformer configured for: {dataset}")

    logger = get_logger(dataset_name=dataset, log_type="pipeline")
    try:
        logger.info("Start cleaning pipeline: %s", dataset)
        paths = get_dataset_paths(dataset)
        config = get_dataset_config(dataset)
        text_columns = config.id_columns + config.text_columns + config.optional_text_columns
        
        # Extract
        df = extract_csv(
            str(paths["raw"]),
            dtype={column: "string" for column in text_columns},
        )
        
        # Transform
        clean_df, rejected_df = TRANSFORMERS[dataset](df)

        input_count = len(df)
        output_count = len(clean_df) + len(rejected_df)
        if input_count != output_count:
            raise ValueError(
                f"Row count mismatch: Input={input_count}, Output={output_count}"
            )

        if "rejection_reason" not in rejected_df.columns:
            raise ValueError("Rejected records must include rejection_reason")
        missing_reason = (
            rejected_df["rejection_reason"]
            .astype("string")
            .fillna("")
            .str.strip()
            .eq("")
        )

        if missing_reason.any():
            raise ValueError("Rejected records contain empty rejection_reason")
        
        # Export CSV
        logger.info(
            "Input: %s | Clean: %s | Rejected: %s",
            input_count, len(clean_df), len(rejected_df),
        )
        for output_name, output_df in (("clean", clean_df), ("rejected", rejected_df)):
            _export_csv(output_df, paths[output_name])
            logger.info("Saved %s: %s", output_name, paths[output_name])

        logger.info("Completed cleaning pipeline: %s", dataset)
        return clean_df
    except Exception:
        logger.exception("Failed cleaning pipeline: %s", dataset)
        raise


def _load_dataset(dataset: str, clean_df: pd.DataFrame) -> None:
    """Load already cleaned records into PostgreSQL."""
    logger = get_logger(dataset_name=dataset, log_type="pipeline")
    try:
        logger.info("Start loading dataset: %s", dataset)
        config = get_dataset_config(dataset)
        upsert_dataframe(
            df=clean_df,
            table_name=dataset,
            conflict_columns=("geolocation_id",) if dataset == "geolocation" else config.key_columns,
        )

        logger.info("Completed pipeline: %s", dataset)
    except Exception:
        logger.exception("Failed pipeline: %s", dataset)
        raise

dev_mode = False

def main() -> None:
    pipeline_logger = get_logger(
        dataset_name="main",
        log_type="pipeline",
    )

    try:
        pipeline_logger.info(
            "Starting ETL pipeline"
        )

        # สร้างตารางจาก schma.sql
        if not dev_mode:
            create_table()

        # ต้องทำตามลำดับ Foreign Key
        order_items_df = None
        for dataset in DATA_LIST:
            clean_df = _cleaning_dataset(dataset)
            if dataset == "order_items":
                order_items_df = clean_df
            elif not dev_mode:
                _load_dataset(dataset, clean_df)

        for dataset in VALIDATE_LIST:
            _cleaning_dataset(dataset)
        validate_product()
        validate_geolocation()

        if not dev_mode:
            for dataset in VALIDATE_LIST:
                validated_path = get_dataset_paths(dataset)["validated"]
                validated_df = extract_csv(
                    str(validated_path),
                    dtype=(
                        {"geolocation_id": "Int64", "zip_code": "string"}
                        if dataset == "geolocation"
                        else {"product_category_id": "Int64"}
                    ),
                )
                _load_dataset(dataset, validated_df)

            if order_items_df is not None:
                _load_dataset("order_items", order_items_df)

        pipeline_logger.info(
            "ETL pipeline completed successfully"
        )

    except Exception:
        pipeline_logger.exception(
            "ETL pipeline failed"
        )
        raise

if __name__ == "__main__":
    main()
