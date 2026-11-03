from unittest.mock import Mock, patch

import pandas as pd
import pytest

from src import load


@pytest.mark.parametrize("chunk_size", [0, -1])
@pytest.mark.parametrize("is_empty", [False, True])
def test_invalid_chunk_size_is_rejected_before_database(
    chunk_size,
    is_empty,
):
    df = pd.DataFrame({
        "order_id": [] if is_empty else ["example"]
    })

    with (
        patch.object(load, "_get_engine") as mock_engine,
        patch.object(load, "get_logger", return_value=Mock()),
    ):
        with pytest.raises(
            ValueError,
            match="chunk_size must be positive",
        ):
            load.upsert_dataframe(
                df=df,
                table_name="orders",
                conflict_columns=("order_id",),
                chunk_size=chunk_size,
            )

        mock_engine.assert_not_called()

@pytest.mark.parametrize("chunk_size", [1, 1000, 2000])
def test_valid_chunk_size_with_empty_dataframe_skips_database(chunk_size):
    df = pd.DataFrame({"order_id": []})

    with (
        patch.object(load, "_get_engine") as mock_engine,
        patch.object(load, "get_logger", return_value=Mock()),
    ):
        load.upsert_dataframe(
            df=df,
            table_name="orders",
            conflict_columns=("order_id",),
            chunk_size=chunk_size,
        )

        mock_engine.assert_not_called()