from pathlib import Path
from collections.abc import Mapping
import pandas as pd

def extract_csv(
    file_path: str,
    dtype: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(
            f"Dataset not found: {file_path}"
        )

    df = pd.read_csv(path, dtype=dtype)

    print(f"Extracted {len(df)} rows")

    return df
