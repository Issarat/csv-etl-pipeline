import pandas as pd
from src.logger import get_logger
from src.configuration import get_dataset_paths


def validate_geolocation() -> None:
    """Rename the ZIP column and assign integer IDs without changing clean input."""
    dataset_name = "geolocation"
    logger = get_logger(dataset_name=dataset_name, log_type="validate")
    paths = get_dataset_paths(dataset_name)
    try:
        logger.info("Starting validation for dataset: %s", dataset_name)
        df = pd.read_csv(paths["clean"], dtype={"geolocation_zip_code_prefix": "string"})
        if "geolocation_zip_code_prefix" not in df.columns:
            raise ValueError("Missing column: geolocation_zip_code_prefix")
        
        if {"zip_code", "geolocation_id"} & set(df.columns):
            raise ValueError("Clean geolocation already contains zip_code or geolocation_id")
        
        df = df.rename(columns={"geolocation_zip_code_prefix": "zip_code"})
        df.insert(0, "geolocation_id", range(1, len(df) + 1))
        paths["validated"].parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(paths["validated"], index=False)
        logger.info("Successfully validated dataset to: %s", paths["validated"])
        
    except Exception:
        logger.exception("Failed to validate dataset: %s", dataset_name)
        raise


def validate_product() -> None:
    """Build validated category and product files together, preserving existing IDs."""
    dataset_name = "products"
    logger = get_logger(dataset_name=dataset_name, log_type="validate")
    logger.info("Starting validation for dataset: %s", dataset_name)

    paths = get_dataset_paths(dataset_name)
    clean_path = paths["clean"]
    validated_path = paths["validated"]
    category_paths = get_dataset_paths("product_categories")
    category_path = category_paths["validated"]

    if not clean_path.exists():
        logger.error("Clean dataset file does not exist: %s", clean_path)
        raise FileNotFoundError(f"Clean dataset file does not exist: {clean_path}")

    try:
        df = pd.read_csv(clean_path)
        logger.info("Loaded clean dataset with %d rows and %d columns.", len(df), len(df.columns))

        name_column = "product_category_name"
        id_column = "product_category_id"
        english_column = "product_category_name_english"
        latest_categories = pd.read_csv(category_paths["clean"])
        for column in (name_column, english_column):
            latest_categories[column] = latest_categories[column].astype("string").str.strip()
        latest_categories[english_column] = latest_categories[english_column].replace("", pd.NA)
        latest_names = latest_categories[name_column]
        if latest_names.fillna("").eq("").any() or latest_names.duplicated().any():
            raise ValueError("Clean categories contain empty or duplicate names")

        if category_path.exists():
            categories = pd.read_csv(category_path)
            for column in (name_column, english_column):
                categories[column] = categories[column].astype("string").str.strip()
            existing_ids = pd.to_numeric(categories[id_column], errors="raise").astype("Int64")
            if existing_ids.isna().any() or existing_ids.duplicated().any():
                raise ValueError("Category mapping contains null or duplicate IDs")
            categories[id_column] = existing_ids
            # Update translations by canonical name without changing existing IDs.
            latest_translations = latest_categories.set_index(name_column)[english_column]
            translations = categories[name_column].map(latest_translations)
            categories[english_column] = translations.combine_first(categories[english_column])
            new_categories = latest_categories.loc[
                ~latest_names.isin(categories[name_column]), [name_column, english_column]
            ].copy()
            next_id = int(existing_ids.max()) + 1 if not existing_ids.empty else 1
            new_categories.insert(0, id_column, pd.array(
                range(next_id, next_id + len(new_categories)), dtype="Int64",
            ))
            categories = pd.concat([categories, new_categories], ignore_index=True)
        else:
            categories = latest_categories.loc[:, [name_column, english_column]].copy()
        names = categories[name_column].astype("string").str.strip()

        if names.fillna("").eq("").any() or names.duplicated().any():
            raise ValueError("Category mapping contains empty or duplicate names")
        categories[name_column] = names

        # Resolve either category name to the canonical name before assigning IDs.
        aliases = pd.concat([
            pd.DataFrame({"alias": names, "canonical": names}),
            pd.DataFrame({
                "alias": categories["product_category_name_english"].astype("string").str.strip(),
                "canonical": names,
            }),
        ], ignore_index=True)

        aliases = aliases.loc[aliases["alias"].fillna("").ne("")].drop_duplicates()

        if aliases["alias"].duplicated().any():
            raise ValueError("Category names or English names match multiple categories")
        
        canonical_mapping = aliases.set_index("alias")["canonical"]
        product_names = df[name_column].astype("string").str.strip()
        canonical_names = product_names.map(canonical_mapping).astype("string")
        unknown = product_names.fillna("").ne("") & canonical_names.isna()
        canonical_names = canonical_names.where(~unknown, product_names)
        df[name_column] = canonical_names

        if id_column not in categories:
            categories.insert(0, id_column, range(1, len(categories) + 1))
        ids = pd.to_numeric(categories[id_column], errors="raise").astype("Int64")

        if ids.isna().any() or ids.duplicated().any():
            raise ValueError("Category mapping contains null or duplicate IDs")
        
        mapping = pd.Series(ids.array, index=names)
        product_ids = canonical_names.map(mapping).astype("Int64")

        if unknown.any():
            new_names = sorted(product_names[unknown].unique())
            next_id = int(ids.max()) + 1 if not ids.empty else 1
            new_categories = pd.DataFrame(
                {
                    id_column: pd.array(
                        range(next_id, next_id + len(new_names)), dtype="Int64",
                    ),
                    name_column: new_names,
                    "product_category_name_english": pd.NA,
                }
            )
            categories = pd.concat([categories, new_categories], ignore_index=True)
            mapping = pd.Series(
                categories[id_column].astype("Int64").array,
                index=categories[name_column].astype("string").str.strip(),
            )
            product_ids = canonical_names.map(mapping).astype("Int64")
        
        df.insert(df.columns.get_loc(name_column), id_column, product_ids)
        df = df.drop(columns=name_column)

        # Ensure the output directory exists
        validated_path.parent.mkdir(parents=True, exist_ok=True)

        category_path.parent.mkdir(parents=True, exist_ok=True)
        categories.to_csv(category_path, index=False)
        logger.info("Saved validated categories to: %s", category_path)
        if unknown.any():
            logger.info("Added %d product categories to: %s", len(new_names), category_path)

        # Save a separate output without overwriting the clean dataset
        df.to_csv(validated_path, index=False)
        logger.info("Successfully validated dataset to: %s", validated_path)

    except Exception as e:
        logger.exception("Failed to validate dataset: %s", e) 
        raise
