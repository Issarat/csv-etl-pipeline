import great_expectations as gx
import pandas as pd


def validate_customers(df: pd.DataFrame) -> None:
    context = gx.get_context(mode="ephemeral")

    source = context.data_sources.add_pandas(name="pipeline")
    asset = source.add_dataframe_asset(name="customers")
    batch = asset.add_batch_definition_whole_dataframe("all_rows")

    suite = gx.ExpectationSuite(name="customers_quality")

    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToNotBeNull(
            column="customer_id",
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeUnique(
            column="customer_id",
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToMatchRegex(
            column="customer_state",
            regex=r"^[A-Z]{2}$",
        )
    )

    suite = context.suites.add(suite)

    validation = context.validation_definitions.add(
        gx.ValidationDefinition(
            name="validate_customers",
            data=batch,
            suite=suite,
        )
    )

    result = validation.run(batch_parameters={"dataframe": df})

    if not result.success:
        raise ValueError(
            f"Customers quality check failed: {result.statistics}"
        )

def validate_sellers(df: pd.DataFrame) -> None:
    context = gx.get_context(mode="ephemeral")

    source = context.data_sources.add_pandas(name="pipeline")
    asset = source.add_dataframe_asset(name="sellers")
    batch = asset.add_batch_definition_whole_dataframe("all_rows")

    suite = gx.ExpectationSuite(name="sellers_quality")

    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeUnique(
            column="seller_id",
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToMatchRegex(
            column="seller_zip_code_prefix",
            regex=r"^[0-9]{5}$",
        )
    )

    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToMatchRegex(
            column="seller_state",
            regex=r"^[A-Z]{2}$",
        )
    )

    for column in ("seller_id", "seller_zip_code_prefix", "seller_state"):
        suite.add_expectation(
            gx.expectations.ExpectColumnValuesToNotBeNull(
                column=column,
            )
        )

    suite = context.suites.add(suite)

    validation = context.validation_definitions.add(
        gx.ValidationDefinition(
            name="validate_seller",
            data=batch,
            suite=suite,
        )
    )

    result = validation.run(batch_parameters={"dataframe": df})

    if not result.success:
        raise ValueError(
            f"Sellers quality check failed: {result.statistics}"
        )

def validate_dataset(dataset: str, df: pd.DataFrame) -> None:
    """Validate the final load shape, including mapped product/geo columns."""
    from src.configuration import get_dataset_config
    from src.transform import NUMBERIC_COLUMNS

    config = get_dataset_config(dataset)
    required = list(config.required_columns)
    if dataset == "products":
        required[required.index("product_category_name")] = "product_category_id"
    if dataset == "geolocation":
        required[required.index("geolocation_zip_code_prefix")] = "zip_code"
        required.append("geolocation_id")
    missing = sorted(set(required) - set(df.columns))
    label = dataset.capitalize()
    if missing:
        raise ValueError(f"{label} quality check failed: missing columns {missing}")

    context = gx.get_context(mode="ephemeral")
    source = context.data_sources.add_pandas(name="pipeline")
    asset = source.add_dataframe_asset(name=dataset)
    batch = asset.add_batch_definition_whole_dataframe("all_rows")
    suite = gx.ExpectationSuite(name=f"{dataset}_quality")
    def add(expectation):
        suite.add_expectation(expectation)

    mandatory = set(config.id_columns + config.text_columns + config.key_columns)
    mandatory.update(set(config.numeric_columns) - set(config.nullable_numeric_columns))
    mandatory.update(config.date_columns if dataset != "orders" else ("order_purchase_timestamp",))
    if dataset == "products":
        mandatory.discard("product_category_name")
    if dataset == "geolocation":
        mandatory.discard("geolocation_zip_code_prefix")
        mandatory.update(("zip_code", "geolocation_id"))
    for column in sorted(mandatory):
        add(gx.expectations.ExpectColumnValuesToNotBeNull(column=column))
    keys = config.key_columns if dataset != "geolocation" else ("geolocation_id",)
    if len(keys) == 1:
        add(gx.expectations.ExpectColumnValuesToBeUnique(column=keys[0]))
    elif keys:
        add(gx.expectations.ExpectCompoundColumnsToBeUnique(column_list=list(keys)))
    for column in config.id_columns + config.text_columns:
        if column in df:
            add(gx.expectations.ExpectColumnValuesToNotMatchRegex(column=column, regex=r"^\s*$"))
    for column in required:
        if column.endswith("state"):
            add(gx.expectations.ExpectColumnValuesToMatchRegex(column=column, regex=r"^[A-Z]{2}$"))
        if "zip_code" in column:
            add(gx.expectations.ExpectColumnValuesToMatchRegex(column=column, regex=r"^[0-9]{1,5}$"))
    if config.valid_statuses:
        add(gx.expectations.ExpectColumnValuesToBeInSet(column="order_status", value_set=sorted(config.valid_statuses)))
    if config.valid_payment_types:
        add(gx.expectations.ExpectColumnValuesToBeInSet(column="payment_type", value_set=sorted(config.valid_payment_types)))
    for column in config.numeric_columns:
        minimum, maximum = 0, 2147483647
        if column in NUMBERIC_COLUMNS:
            maximum = 9999999999.99
        elif column == "geolocation_lat":
            minimum, maximum = -90, 90
        elif column == "geolocation_lng":
            minimum, maximum = -180, 180
        elif column == "review_score":
            minimum, maximum = 1, 5
        elif column in ("order_item_id", "payment_sequential"):
            minimum = 1
        add(gx.expectations.ExpectColumnValuesToBeBetween(column=column, min_value=minimum, max_value=maximum))
        if column not in NUMBERIC_COLUMNS and not column.startswith("geolocation_"):
            # Values may be floats after CSV parsing, so check integrality by value.
            values = df[column].dropna()
            if not values.mod(1).eq(0).all():
                raise ValueError(f"{label} quality check failed: {column} must contain integers")
    suite = context.suites.add(suite)
    validation = context.validation_definitions.add(gx.ValidationDefinition(
        name=f"validate_{dataset}", data=batch, suite=suite,
    ))
    result = validation.run(batch_parameters={"dataframe": df})
    if not result.success:
        raise ValueError(f"{label} quality check failed: {result.statistics}")
