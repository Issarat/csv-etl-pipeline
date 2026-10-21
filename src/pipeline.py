from pathlib import Path

import pandas as pd

from src.logger import get_logger
from src.Configuration import get_dataset_config, get_dataset_paths
from src.extract import extract_csv
from src.transform import (
    transform_orders,
    transform_order_items,
    transform_customers,
)
from src.load import create_table, upsert_dataframe

# Dataset order follows foreign key dependencies.
TRANSFORMERS = {
    "orders": transform_orders,
    "order_items": transform_order_items,
    "customers": transform_customers,
}

DATA_LIST = ("customers", "orders", "order_items")

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
        text_columns = config.id_columns + config.text_columns
        
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


def _migration_dataset(dataset: str, clean_df: pd.DataFrame) -> None:
    """Load already cleaned records into PostgreSQL."""
    logger = get_logger(dataset_name=dataset, log_type="pipeline")
    try:
        logger.info("Start loading dataset: %s", dataset)
        config = get_dataset_config(dataset)
        upsert_dataframe(
            df=clean_df,
            table_name=dataset,
            conflict_columns=config.key_columns,
        )

        logger.info("Completed pipeline: %s", dataset)
    except Exception:
        logger.exception("Failed pipeline: %s", dataset)
        raise

dev_mode = True

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
        for dataset in DATA_LIST:
            clean_df = _cleaning_dataset(dataset)
            if not dev_mode:
                _migration_dataset(dataset, clean_df)

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
