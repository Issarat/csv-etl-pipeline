from unittest.mock import Mock

import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from src import load, validate, pipeline


COLUMNS = ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng", "geolocation_city", "geolocation_state"]


def test_ids_survive_reorder_removal_addition_and_return(tmp_path, monkeypatch):
    source = tmp_path / "clean.csv"
    output = tmp_path / "validate" / "geo.csv"
    monkeypatch.setattr(validate, "get_dataset_paths", lambda _: {"clean": source, "validated": output})
    monkeypatch.setattr(validate, "get_logger", Mock(return_value=Mock()))
    a = ["01037", -23.54562128115268, -46.63929204800168, "A", "SP"]
    b = ["01046", -23.6, -46.7, "B", "SP"]
    c = ["01050", -23.7, -46.8, "C", "SP"]
    def run(rows):
        pd.DataFrame(rows, columns=COLUMNS).to_csv(source, index=False)
        before = source.read_bytes()
        validate.validate_geolocation()
        assert source.read_bytes() == before
        return pd.read_csv(output, dtype={"zip_code": "string"}, float_precision="round_trip")
    first = run([a, a, b])
    assert first.geolocation_id.tolist() == [1, 2, 3]
    assert run([b, a, a]).geolocation_id.tolist() == [3, 1, 2]
    assert run([b, c]).geolocation_id.tolist() == [3, 4]
    assert run([a, b, c, a]).geolocation_id.tolist() == [1, 3, 4, 2]
    assert run([]).empty
    assert run([a]).geolocation_id.tolist() == [1]
    assert (output.parent / "geolocation_id_mapping.csv").exists()


def test_bootstrap_from_existing_validated_ids(tmp_path, monkeypatch):
    source = tmp_path / "clean.csv"
    output = tmp_path / "geo.csv"
    pd.DataFrame([["01037", 1.1, 2.2, "A", "SP"]], columns=COLUMNS).to_csv(source, index=False)
    pd.DataFrame({"geolocation_id": [42], "zip_code": ["01037"], "geolocation_lat": [1.1], "geolocation_lng": [2.2], "geolocation_city": ["A"], "geolocation_state": ["SP"]}).to_csv(output, index=False)
    monkeypatch.setattr(validate, "get_dataset_paths", lambda _: {"clean": source, "validated": output})
    monkeypatch.setattr(validate, "get_logger", Mock(return_value=Mock()))
    validate.validate_geolocation()
    assert pd.read_csv(output).geolocation_id.tolist() == [42]


@pytest.fixture
def database(monkeypatch):
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("""CREATE TABLE geolocation (
            geolocation_id INTEGER PRIMARY KEY, zip_code TEXT NOT NULL,
            geolocation_lat REAL NOT NULL, geolocation_lng REAL NOT NULL,
            geolocation_city TEXT NOT NULL, geolocation_state TEXT NOT NULL
        )"""))
    monkeypatch.setattr(load, "_get_engine", lambda: engine)
    monkeypatch.setattr(load, "get_logger", Mock(return_value=Mock()))
    yield engine
    engine.dispose()


def snapshot():
    return pd.DataFrame({
        "geolocation_id": [1, 2], "zip_code": ["01037", "01046"],
        "geolocation_lat": [1.1, 2.2], "geolocation_lng": [3.3, 4.4],
        "geolocation_city": ["A", "B"], "geolocation_state": ["SP", "SP"],
    })


def test_snapshot_replacement_removes_stale_rows_and_clears_empty_input(database):
    df = snapshot()
    load.replace_geolocation(df)
    load.replace_geolocation(df.iloc[1:])
    with database.connect() as connection:
        assert connection.execute(text("SELECT geolocation_id, zip_code FROM geolocation")).all() == [(2, "01046")]
    load.replace_geolocation(df.iloc[:0])
    with database.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM geolocation")).scalar_one() == 0


def test_failed_snapshot_replacement_rolls_back_delete_and_inserts(database):
    df = snapshot()
    load.replace_geolocation(df)
    invalid = df.copy()
    invalid.loc[1, "zip_code"] = None
    with pytest.raises(IntegrityError):
        load.replace_geolocation(invalid, chunk_size=1)
    with database.connect() as connection:
        assert connection.execute(text("SELECT geolocation_id, zip_code FROM geolocation ORDER BY geolocation_id")).all() == [(1, "01037"), (2, "01046")]


def test_pipeline_routes_geolocation_to_snapshot_loader(monkeypatch):
    replace = Mock()
    upsert = Mock()
    monkeypatch.setattr(pipeline, "get_logger", Mock(return_value=Mock()))
    monkeypatch.setattr(pipeline, "replace_geolocation", replace)
    monkeypatch.setattr(pipeline, "upsert_dataframe", upsert)
    df = snapshot()
    pipeline._load_dataset("geolocation", df)
    replace.assert_called_once_with(df)
    upsert.assert_not_called()
