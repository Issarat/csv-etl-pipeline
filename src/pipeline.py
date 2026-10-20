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


TRANSFORMERS = {
    "orders": transform_orders,
    "order_items": transform_order_items,
    "customers": transform_customers,
}

DATA_LIST = ("orders", "order_items", "customers")


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
        df = extract_csv(
            str(paths["raw"]),
            dtype={column: "string" for column in text_columns},
        )
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

        logger.info(
            "Input: %s | Clean: %s | Rejected: %s",
            input_count, len(clean_df), len(rejected_df),
        )

        export_csv(clean_df, paths["clean"])
        logger.info("Saved clean: %s", paths["clean"])
        export_csv(rejected_df, paths["rejected"])
        logger.info("Saved rejected: %s", paths["rejected"])
        logger.info("Completed pipeline: %s", dataset)
    except Exception:
        logger.exception("Failed pipeline: %s", dataset)
        raise


def main() -> None:
    for dataset in DATA_LIST:
        run_dataset(dataset)


if __name__ == "__main__":
    main()
