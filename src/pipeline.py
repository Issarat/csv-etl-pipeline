from pathlib import Path
from typing import List, Tuple
import pandas as pd
from uuid import uuid4
from filelock import FileLock, Timeout
from decimal import Decimal
from src.logger import get_logger
from src.configuration import get_dataset_config, get_dataset_paths
from src.extract import extract_csv
from src.validate import (
    replace_with_retry,
    validate_product,
    validate_geolocation,
)
from src.transform import (
    NUMBERIC_COLUMNS,
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
from src.load import create_table, upsert_dataframe, replace_geolocation, read_product_category_mapping,find_missing_reference_ids

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
CHECK_MISSING_DATA = ("orders","order_payments","order_reviews","order_items")
PIPELINE_LOCK_PATH = Path(__file__).resolve().parents[1] / ".pipeline.lock"


def _export_csv(df: pd.DataFrame, file_path: Path) -> None:
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = file_path.with_suffix(file_path.suffix + ".tmp")
    df.to_csv(temporary, index=False)
    replace_with_retry(temporary, file_path)


def _cleaning_dataset(dataset: str) -> pd.DataFrame:
    """Extract, transform, validate, and export a dataset; return clean records."""
    if dataset not in TRANSFORMERS:
        raise ValueError(f"No transformer configured for: {dataset}")

    logger = get_logger(dataset_name=dataset, log_type="pipeline")
    try:
        logger.info("Start cleaning pipeline: %s", dataset)
        paths = get_dataset_paths(dataset)
        config = get_dataset_config(dataset)
        numberic_columns = tuple(
            column
            for column in config.numeric_columns
            if column in NUMBERIC_COLUMNS
        )

        text_columns = (
            config.id_columns
            + config.text_columns
            + config.optional_text_columns
            + numberic_columns
        )
        
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

def _get_data_missing_check(dataset: str) -> List[Tuple[str, str]]:
    match dataset:
        case "orders":
            return [("customers", "customer_id")]
            
        case "order_payments" | "order_reviews":
            return [("orders", "order_id")]
            
        case "order_items":
            return [
                ("orders", "order_id"), 
                ("products", "product_id"), 
                ("sellers", "seller_id")
            ]
        
        case _: 
            return []
        
def _load_dataset(dataset: str, clean_df: pd.DataFrame) -> None:
    """Load already cleaned records into PostgreSQL."""
    logger = get_logger(dataset_name=dataset, log_type="pipeline")
    try:
        logger.info("Start loading dataset: %s", dataset)
        config = get_dataset_config(dataset)
        if dataset == "geolocation":
            replace_geolocation(clean_df)
        else:
            if dataset in CHECK_MISSING_DATA and not clean_df.empty:
                dependencies = _get_data_missing_check(dataset)
                for target_table, foreign_key in dependencies:
                    missing_ids = find_missing_reference_ids(clean_df, table_name=target_table, column_name=foreign_key)
                    if missing_ids:
                        affected_orders = clean_df[foreign_key].isin(missing_ids).sum()
                        examples = sorted(missing_ids)[:5]

                        raise ValueError(
                            f"{dataset}.{foreign_key} references missing {target_table}: "
                            f"{len(missing_ids)} missing IDs, "
                            f"{affected_orders} affected {dataset}. Examples: {examples}"
                        )
                
            upsert_dataframe(
                df=clean_df,
                table_name=dataset,
                conflict_columns=config.key_columns,
            )

        logger.info("Completed pipeline: %s", dataset)
    except Exception:
        logger.exception("Failed pipeline: %s", dataset)
        raise

def valid_decimal_type(dataset: str) -> pd.DataFrame:
    config = get_dataset_config(dataset)
    paths = get_dataset_paths(dataset)

    numberic_columns = tuple(
        column
        for column in config.numeric_columns
        if column in NUMBERIC_COLUMNS
    )

    dtype = {
        column: "string"
        for column in numberic_columns
    }

    if dataset == "geolocation":
        dtype.update({
            "geolocation_id": "Int64",
            "zip_code": "string",
        })
    elif dataset == "products":
        dtype["product_category_name"] = "string"
    
    df = extract_csv(
        str(paths["validated"]),
        dtype=dtype,
    )

    for column in numberic_columns:
        df[column] = df[column].map(
            lambda value: (
                None if pd.isna(value) else Decimal(value)
            )
        )
    return df

def _run_pipeline() -> None:
    pipeline_logger = get_logger(
        dataset_name="main",
        log_type="pipeline",
    )
    def load_with_status(dataset: str, df: pd.DataFrame) -> None:
        pipeline_logger.info(
            "run_id=%s dataset=%s status=LOAD_STARTED rows=%d",
            run_id, dataset, len(df),
        )

        try:
            _load_dataset(dataset, df)
        except Exception:
            pipeline_logger.error(
                "run_id=%s dataset=%s status=LOAD_FAILED",
                run_id, dataset,
            )
            raise

        pipeline_logger.info(
            "run_id=%s dataset=%s status=LOAD_SUCCEEDED",
            run_id, dataset,
        )
    try:
        run_id = uuid4().hex
        pipeline_logger.info("run_id=%s status=STARTED", run_id)

        # สร้างตารางจาก schma.sql
        create_table()

        for dataset in VALIDATE_LIST:
            _cleaning_dataset(dataset)
        validate_product()
        validate_geolocation()

        for dataset in VALIDATE_LIST:
            validated_df = valid_decimal_type(dataset=dataset)

            if dataset == "products":
                names = validated_df["product_category_name"]
                mapping = read_product_category_mapping()
                category_ids = names.map(mapping).astype("Int64")

                missing = names.notna() & category_ids.isna()
                if missing.any():
                    unknown_names = sorted(names[missing].unique())
                    raise ValueError(f"Categories missing in PostgreSQL: {unknown_names}")

                validated_df["product_category_id"] = category_ids
                validated_df = validated_df.drop(columns=["product_category_name"])
            
            load_with_status(dataset, validated_df)

        # ต้องทำตามลำดับ Foreign Key
        order_items_df = None
        for dataset in DATA_LIST:
            clean_df = _cleaning_dataset(dataset)
            if dataset == "order_items":
                order_items_df = clean_df
            else:
                load_with_status(dataset, clean_df)
  
        if order_items_df is not None: 
            load_with_status("order_items", order_items_df)
        
        pipeline_logger.info("run_id=%s status=SUCCEEDED", run_id)
    except Exception:
        pipeline_logger.exception("run_id=%s status=FAILED", run_id)
        raise

def main() -> None:
    lock = FileLock(str(PIPELINE_LOCK_PATH))

    try:
        lock.acquire(timeout=0)
    except Timeout as exc:
        raise RuntimeError(
            "Another pipeline run is already in progress."
        ) from exc

    try:
        _run_pipeline()
    finally:
        lock.release()

if __name__ == "__main__":
    main()
