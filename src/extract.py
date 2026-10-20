from pathlib import Path
import pandas as pd

def extract_csv(file_path: str) -> pd.DataFrame:
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(
            f"Dataset not found: {file_path}"
        )

    df = pd.read_csv(path)

    print(f"Extracted {len(df)} rows")

    return df
