import os

import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from uuid import uuid4
from src import load


@pytest.fixture
def postgres_engine():
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is not configured")

    if make_url(database_url).database != "olist_test":
        raise ValueError("Tests must use olist_test")

    engine = create_engine(database_url)

    try:
        yield engine
    finally:
        engine.dispose()


def test_connects_to_test_database(postgres_engine):
    with postgres_engine.connect() as connection:
        database = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

    assert database == "olist_test"


@pytest.fixture
def customer_table(postgres_engine, monkeypatch):
    table_name = f"test_customers_{uuid4().hex}"

    with postgres_engine.begin() as connection:
        connection.execute(text(f"""
            CREATE TABLE "{table_name}" (
                customer_id UUID PRIMARY KEY,
                customer_unique_id UUID NOT NULL,
                customer_zip_code_prefix VARCHAR(5) NOT NULL,
                customer_city TEXT NOT NULL,
                customer_state VARCHAR(2) NOT NULL
            )
        """))

    monkeypatch.setattr(load, "_get_engine", lambda: postgres_engine)

    try:
        yield table_name
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(text(f'DROP TABLE "{table_name}"'))

CUSTOMER_ID = "00000000000000000000000000000021"
CUSTOMER_UNIQUE_ID = "00000000000000000000000000000022"
SELLER_ID = "00000000000000000000000000000023"

def test_customer_upsert_is_idempotent(
    postgres_engine,
    customer_table,
):
    df = pd.DataFrame([{
        "customer_id": CUSTOMER_ID,
        "customer_unique_id": CUSTOMER_UNIQUE_ID,
        "customer_zip_code_prefix": "01001",
        "customer_city": "sao paulo",
        "customer_state": "SP",
    }])

    load.upsert_dataframe(
        df=df,
        table_name=customer_table,
        conflict_columns=("customer_id",),
    )

    load.upsert_dataframe(
        df=df,
        table_name=customer_table,
        conflict_columns=("customer_id",),
    )

    with postgres_engine.connect() as connection:
        row_count = connection.execute(
            text(f'SELECT COUNT(*) FROM "{customer_table}"')
        ).scalar_one()

    assert row_count == 1

    with postgres_engine.connect() as connection:
        row = connection.execute(
            text(f"""
                SELECT customer_zip_code_prefix, customer_city, customer_state
                FROM "{customer_table}"
            """)
        ).one()
    assert tuple(row) == ("01001", "sao paulo", "SP")

def test_customer_upsert_updates_existing_row(
    postgres_engine,
    customer_table,
):
    df = pd.DataFrame([{
            "customer_id": CUSTOMER_ID,
            "customer_unique_id": CUSTOMER_UNIQUE_ID,
            "customer_zip_code_prefix": "01001",
            "customer_city": "campinas",
            "customer_state": "SP",
    }])
    load.upsert_dataframe(
            df=df,
            table_name=customer_table,
            conflict_columns=("customer_id",),
    )
    with postgres_engine.connect() as connection:
            row = connection.execute(
                text(f"""
                    SELECT customer_zip_code_prefix, customer_city, customer_state
                    FROM "{customer_table}"
                """)
            ).one()
    assert tuple(row) == ("01001", "campinas", "SP")

from sqlalchemy.exc import IntegrityError


def test_customer_upsert_rolls_back_when_later_chunk_fails(
    postgres_engine,
    customer_table,
):
    df = pd.DataFrame([
        {
            "customer_id": CUSTOMER_ID,
            "customer_unique_id": CUSTOMER_UNIQUE_ID,
            "customer_zip_code_prefix": "01001",
            "customer_city": "sao paulo",
            "customer_state": "SP",
        },
        {
            "customer_id": "00000000000000000000000000000024",
            "customer_unique_id": "00000000000000000000000000000025",
            "customer_zip_code_prefix": "01002",
            "customer_city": None,
            "customer_state": "SP",
        },
    ])

    with pytest.raises(IntegrityError):
        load.upsert_dataframe(
            df=df,
            table_name=customer_table,
            conflict_columns=("customer_id",),
            chunk_size=1,
        )

    with postgres_engine.connect() as connection:
        row_count = connection.execute(
            text(f'SELECT COUNT(*) FROM "{customer_table}"')
        ).scalar_one()

    assert row_count == 0