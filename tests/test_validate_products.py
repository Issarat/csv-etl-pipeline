from unittest.mock import Mock

import pandas as pd
import pytest

from src import validate


@pytest.fixture
def files(tmp_path, monkeypatch):
    paths = {
        "products": {"clean": tmp_path / "products.csv", "validated": tmp_path / "out" / "products.csv"},
        "product_categories": {"clean": tmp_path / "categories.csv", "validated": tmp_path / "out" / "categories.csv"},
    }
    paths["product_categories"]["validated"].parent.mkdir()
    monkeypatch.setattr(validate, "get_dataset_paths", lambda dataset: paths[dataset])
    monkeypatch.setattr(validate, "get_logger", Mock(return_value=Mock()))
    return paths


def test_merge_latest_translations_and_categories_preserves_ids_and_reruns(files):
    category_paths = files["product_categories"]
    pd.DataFrame({
        "product_category_id": [42, 8, 19],
        "product_category_name": ["livros", "brinquedos", "legacy"],
        "product_category_name_english": [None, "toys", "legacy_english"],
    }).to_csv(category_paths["validated"], index=False)
    pd.DataFrame({
        "product_category_name": [" livros ", "brinquedos", "roupas"],
        "product_category_name_english": [" books ", "new_toys", "clothing"],
    }).to_csv(category_paths["clean"], index=False)
    pd.DataFrame({
        "product_id": ["a", "b", "c", "d", "e", "f"],
        "product_category_name": ["books", "new_toys", "clothing", "legacy", "unknown", None],
    }).to_csv(files["products"]["clean"], index=False)
    inputs = {p: p.read_bytes() for p in (category_paths["clean"], files["products"]["clean"])}

    validate.validate_product()
    categories = pd.read_csv(category_paths["validated"]).set_index("product_category_name")
    products = pd.read_csv(files["products"]["validated"])
    assert categories.product_category_id.to_dict() == {
        "livros": 42, "brinquedos": 8, "legacy": 19, "roupas": 43, "unknown": 44,
    }
    assert categories.loc["livros", "product_category_name_english"] == "books"
    assert categories.loc["brinquedos", "product_category_name_english"] == "new_toys"
    assert products.product_category_id.dropna().tolist() == [42, 8, 43, 19, 44]
    assert pd.isna(products.product_category_id.iloc[-1])
    assert "product_category_name" not in products
    before = category_paths["validated"].read_bytes()
    validate.validate_product()
    assert category_paths["validated"].read_bytes() == before
    assert all(p.read_bytes() == content for p, content in inputs.items())


@pytest.mark.parametrize("translation", [None, "  "])
def test_empty_latest_translation_keeps_existing_translation(files, translation):
    pd.DataFrame({"product_category_id": [7], "product_category_name": ["livros"],
                  "product_category_name_english": ["books"]}).to_csv(files["product_categories"]["validated"], index=False)
    pd.DataFrame({"product_category_name": ["livros"],
                  "product_category_name_english": [translation]}).to_csv(files["product_categories"]["clean"], index=False)
    pd.DataFrame({"product_category_name": ["books"]}).to_csv(files["products"]["clean"], index=False)
    validate.validate_product()
    categories = pd.read_csv(files["product_categories"]["validated"])
    assert categories.product_category_id.tolist() == [7]
    assert categories.product_category_name_english.tolist() == ["books"]


def test_first_run_adds_latest_categories_even_when_unused(files):
    files["product_categories"]["clean"].write_text(
        "product_category_name,product_category_name_english\nlivros,books\nroupas,clothing\n", encoding="utf-8",
    )
    files["products"]["clean"].write_text("product_category_name\nbooks\n", encoding="utf-8")
    validate.validate_product()
    assert pd.read_csv(files["product_categories"]["validated"]).product_category_id.tolist() == [1, 2]


def test_ambiguous_latest_translation_does_not_overwrite_outputs(files):
    category_paths = files["product_categories"]
    category_paths["validated"].write_text(
        "product_category_id,product_category_name,product_category_name_english\n7,livros,books\n", encoding="utf-8",
    )
    category_paths["clean"].write_text(
        "product_category_name,product_category_name_english\nlivros,books\nroupas,books\n", encoding="utf-8",
    )
    files["products"]["clean"].write_text("product_category_name\nbooks\n", encoding="utf-8")
    before = category_paths["validated"].read_bytes()
    with pytest.raises(ValueError, match="multiple categories"):
        validate.validate_product()
    assert category_paths["validated"].read_bytes() == before
    assert not files["products"]["validated"].exists()
