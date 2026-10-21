import logging

import pandas as pd

from src.logger import get_logger
from src.configuration import get_dataset_paths
from src.extract import extract_csv

"""
DATA_LIST = [
    "orders",
    "order_items",
    "customers",
]
"""

DATA_LIST = [
    "products",
    "order_payments",
    "order_reviews",
    "product_categories",
    "geolocation",
    "sellers"
]

def profile_data(
    df: pd.DataFrame,
    logger: logging.Logger,
    dataset_name: str,
) -> None:
    logger.info(
        "\n%s\nDATA PROFILING REPORT: %s\n%s",
        "=" * 65,
        dataset_name,
        "=" * 65,
    )

    logger.info("Total Rows     : %s", f"{len(df):,}")
    logger.info("Total Columns  : %s", len(df.columns))
    logger.info(
        "Duplicate Rows : %s",
        f"{df.duplicated().sum():,}",
    )
    logger.info(
        "Memory Usage   : %.2f MB",
        df.memory_usage(deep=True).sum() / 1024**2,
    )

    profile = pd.DataFrame({
        "Column": df.columns,
        "Type": df.dtypes.astype(str).values,
        "Non-Null": df.notna().sum().values,
        "Null": df.isna().sum().values,
        "Null %": (
            df.isna().mean().values * 100
        ).round(2),
        "Unique": df.nunique(dropna=True).values,
    })

    logger.info(
        "\n%s\nCOLUMN PROFILE\n%s\n%s",
        "-" * 65,
        "-" * 65,
        profile.to_string(index=False),
    )

    # รายงานเฉพาะ orders
    if dataset_name == "orders":
        if "order_status" in df.columns:
            logger.info(
                "\n%s\nORDER STATUS DISTRIBUTION\n%s\n%s",
                "-" * 65,
                "-" * 65,
                df["order_status"]
                .value_counts(dropna=False)
                .to_string(),
            )
        else:
            logger.warning(
                "Skipped status distribution: "
                "column 'order_status' is missing"
            )


def main() -> None:
    failed_datasets = []

    for dataset in DATA_LIST:
        logger = get_logger(
            dataset_name=dataset,
            log_type="profiling",
        )

        try:
            logger.info("Start profiling: %s", dataset)

            csv_paths = get_dataset_paths(dataset)

            df = extract_csv(str(csv_paths["raw"]))

            profile_data(
                df=df,
                logger=logger,
                dataset_name=dataset,
            )

            logger.info("Completed profiling: %s", dataset)

        except Exception:
            logger.exception("Failed profiling: %s", dataset)
            failed_datasets.append(dataset)

    if failed_datasets:
        raise RuntimeError(
            "Profiling failed for: "
            + ", ".join(failed_datasets)
        )

if __name__ == "__main__":
    main()