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

