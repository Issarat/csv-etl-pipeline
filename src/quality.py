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