import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = PROJECT_ROOT / "logs"

def get_logger(
    dataset_name: str,
    log_type: str = "profiling"
) -> logging.Logger:

    # 1. Create Log Directory
    log_dir = LOG_PATH / log_type
    log_dir.mkdir(parents=True, exist_ok=True)

    # 2. Get Logger
    logger = logging.getLogger(
        f"{log_type}.{dataset_name}"
    )

    logger.setLevel(logging.INFO)
    logger.propagate = False

    # 3. Prevent Duplicate Handlers
    if not logger.handlers:

        file_handler = logging.FileHandler(
            log_dir / f"{dataset_name}.log",
            encoding="utf-8"
        )

        console_handler = logging.StreamHandler()

        # 4. Set Formatter
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | "
            "%(name)s | %(message)s"
        )

        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        # 5. Register Handlers
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger