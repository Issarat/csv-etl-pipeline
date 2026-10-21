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

#regeion set up constanst
TRANSFORMERS = {
    "orders": transform_orders,
    "order_items": transform_order_items,
    "customers": transform_customers,
}

DATA_LIST = ("customers","orders", "order_items")

TABLE_NAMES_MAPPING = {
    "customers": "customers",
    "orders": "orders",
    "order_items": "order_items",
}

CONFLICT_COLUMNS = {
    "customers": ("customer_id",),
    "orders": ("order_id",),
    "order_items": (
        "order_id",
        "order_item_id",
    ),
}
#endregeion 

def export_csv(df: pd.DataFrame, file_path: Path) -> None:
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(file_path, index=False)


def run_dataset(dataset: str) -> None:
    if dataset not in TRANSFORMERS:
        raise ValueError(f"No transformer configured for: {dataset}")

    logger = get_logger(dataset_name=dataset, log_type="pipeline")
    try:
        logger.info("Start pipeline: %s", dataset)
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
        export_csv(clean_df, paths["clean"])
        export_csv(rejected_df, paths["rejected"])

        logger.info("Saved clean: %s", paths["clean"])
        logger.info("Saved rejected: %s", paths["rejected"])

        # Load เข้า PostgreSQL
        table_name = TABLE_NAMES_MAPPING[dataset]
        
        upsert_dataframe(
            df=clean_df,
            table_name=table_name,
            conflict_columns=CONFLICT_COLUMNS[dataset],
        )

        logger.info(
            "Completed pipeline: %s",
            dataset,
        )
        logger.info("Completed pipeline: %s", dataset)
    except Exception:
        logger.exception("Failed pipeline: %s", dataset)
        raise


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
        create_table()

        # ต้องทำตามลำดับ Foreign Key
        for dataset in DATA_LIST:
            run_dataset(dataset)

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
