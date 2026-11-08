import os
from unittest.mock import Mock
from contextlib import nullcontext

import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from uuid import uuid4
from src import load,pipeline
from sqlalchemy.exc import IntegrityError
from decimal import Decimal
from src.transform import transform_products

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

#region customer
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
            "customer_city": "sao paulo",
            "customer_state": "SP",
    }])
    load.upsert_dataframe(
            df=df,
            table_name=customer_table,
            conflict_columns=("customer_id",),
    )

    df["customer_city"] = "campinas"
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

def test_check_exist_customer_id_finds_missing_id_across_chunks(
    postgres_engine,
    monkeypatch,
):
    customer_a, customer_b, customer_c = (str(uuid4()) for _ in range(3))
    orders = pd.DataFrame({
        "customer_id": [customer_a, customer_b, customer_c],
    })

    with postgres_engine.begin() as connection:
        connection.execute(text("""
            CREATE TEMP TABLE customers (
                customer_id UUID PRIMARY KEY
            ) ON COMMIT DROP
        """))
        connection.execute(
            text("""
                INSERT INTO customers (customer_id)
                VALUES (CAST(:customer_id AS uuid))
            """),
            [
                {"customer_id": customer_a},
                {"customer_id": customer_c},
            ],
        )

        engine = Mock()
        engine.connect.return_value = nullcontext(connection)
        monkeypatch.setattr(load, "_get_engine", lambda: engine)

        missing_ids = load.find_missing_reference_ids(
            orders,
            chunk_size=1,
            table_name="customers",
            column_name="customer_id",
        )
        assert missing_ids == {customer_b}

#endregion

#region products
@pytest.fixture
def product_table(postgres_engine, monkeypatch):
    table_name = f"test_products_{uuid4().hex}"

    with postgres_engine.begin() as connection:
        connection.execute(text(f"""
            CREATE TABLE "{table_name}" (
                product_id UUID PRIMARY KEY,
                product_weight_g NUMERIC(12, 2)
            )
        """))

    monkeypatch.setattr(
        load,
        "_get_engine",
        lambda: postgres_engine,
    )

    try:
        yield table_name
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(
                text(f'DROP TABLE "{table_name}"')
            )

def test_product_weight_rounding_is_preserved_in_postgres(
    postgres_engine,
    product_table,
):
    df = pd.DataFrame([{
            "product_id": "00000000000000000000000000000021",
            "product_category_name": "books",
            "product_weight_g": "1.125",
            "product_length_cm": None,
            "product_height_cm": None,
            "product_width_cm": None,
            "product_name_lenght": None,
            "product_description_lenght": None,
            "product_photos_qty": None,
        }])
    clean, rejected = transform_products(df)

    assert rejected.empty
    assert clean["product_weight_g"].tolist() == [Decimal("1.13")]

    load.upsert_dataframe(
        df=clean[["product_id", "product_weight_g"]],
        table_name=product_table,
        conflict_columns=("product_id",)
    )
    with postgres_engine.connect() as connection:
        weight = connection.execute(
            text(f'''
                SELECT product_weight_g
                FROM "{product_table}"
            ''')
        ).scalar_one()

    assert isinstance(weight, Decimal)
    assert weight == Decimal("1.13")

def test_product_upsert_rolls_back_when_later_chunk_fails(
    postgres_engine,
    product_table,
):
    df = pd.DataFrame([
        {
            "product_id": "00000000000000000000000000000021",
            "product_weight_g": Decimal("1.13"),
        },
        {
            "product_id": None,
            "product_weight_g": Decimal("2.00"),
        },
    ])
    with pytest.raises(IntegrityError):
        load.upsert_dataframe(
            df=df,
            table_name=product_table,
            conflict_columns=("product_id",),
            chunk_size=1,
        )
    with postgres_engine.connect() as connection:
        row_count = connection.execute(
            text(f'SELECT COUNT(*) FROM "{product_table}"')
        ).scalar_one()

    assert row_count == 0

def test_product_upsert_preserves_existing_row_when_later_chunk_fails(
    postgres_engine,
    product_table,
):
    df = pd.DataFrame([
        {
            "product_id": "00000000000000000000000000000021",
            "product_weight_g": Decimal("5.00"),
        }
    ])
    load.upsert_dataframe(
        df=df,
        table_name=product_table,
        conflict_columns=("product_id",)
    )

    df = pd.DataFrame([
        {
            "product_id": "00000000000000000000000000000021",
            "product_weight_g": Decimal("1.13"),
        },
        {
            "product_id": None,
            "product_weight_g": Decimal("2.00"),
        },
    ])
    with pytest.raises(IntegrityError):
        load.upsert_dataframe(
            df=df,
            table_name=product_table,
            conflict_columns=("product_id",),
            chunk_size=1,
        )
    with postgres_engine.connect() as connection:
        row_count = connection.execute(
            text(f'SELECT COUNT(*) FROM "{product_table}"')
        ).scalar_one()
    with postgres_engine.connect() as connection:
        weight = connection.execute(
            text(f'''
                SELECT product_weight_g
                FROM "{product_table}"
            ''')
        ).scalar_one()
    assert row_count == 1
    assert isinstance(weight, Decimal)
    assert weight == Decimal("5.00")
#endregion

#region product_cutomer
def test_main_loads_products_with_existing_postgres_category_id(
    postgres_engine,
    monkeypatch,
    tmp_path,
):
    schema = f"test_category_mapping_{uuid4().hex}"
    product_id = "00000000-0000-0000-0000-000000000021"

    categories_csv = tmp_path / "categories_validated.csv"
    products_csv = tmp_path / "products_validated.csv"

    pd.DataFrame([{
        "product_category_name": "livros",
        "product_category_name_english": "books",
    }]).to_csv(categories_csv, index=False)
    pd.DataFrame([{
        "product_id": product_id,
        "product_category_name": "livros",
        "product_weight_g": "1.13",
        "product_length_cm": None,
        "product_width_cm": None,
        "product_height_cm": None,
    }]).to_csv(products_csv, index=False)

    paths = {
        "product_categories": {"validated": categories_csv},
        "products": {"validated": products_csv},
    }

    with postgres_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    # ทุก connection ของ Pipeline จะใช้ตารางใน schema ของ Test
    scoped_engine = create_engine(
        postgres_engine.url,
        connect_args={"options": f"-c search_path={schema}"},
    )

    try:
        with scoped_engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE product_categories (
                    product_category_id INTEGER
                        GENERATED BY DEFAULT AS IDENTITY (START WITH 100)
                        PRIMARY KEY,
                    product_category_name TEXT NOT NULL UNIQUE,
                    product_category_name_english TEXT
                )
            """))
            connection.execute(text("""
                CREATE TABLE products (
                    product_id UUID PRIMARY KEY,
                    product_category_id INTEGER
                        REFERENCES product_categories (product_category_id),
                    product_weight_g NUMERIC(12, 2),
                    product_length_cm NUMERIC(12, 2),
                    product_width_cm NUMERIC(12, 2),
                    product_height_cm NUMERIC(12, 2)
                )
            """))
            connection.execute(text("""
                INSERT INTO product_categories (
                    product_category_id, product_category_name
                )
                VALUES (1, 'outro'), (42, 'livros')
            """))

        monkeypatch.setattr(load, "_get_engine", lambda: scoped_engine)
        monkeypatch.setattr(load, "get_logger", Mock(return_value=Mock()))
        monkeypatch.setattr(pipeline, "get_logger", Mock(return_value=Mock()))
        monkeypatch.setattr(pipeline, "create_table", Mock())
        monkeypatch.setattr(pipeline, "_cleaning_dataset", Mock())
        monkeypatch.setattr(pipeline, "validate_product", Mock())
        monkeypatch.setattr(pipeline, "validate_geolocation", Mock())
        monkeypatch.setattr(pipeline, "get_dataset_paths", paths.__getitem__)
        monkeypatch.setattr(
            pipeline, "VALIDATE_LIST", ("product_categories", "products")
        )
        monkeypatch.setattr(pipeline, "DATA_LIST", ())

        pipeline.main()

        with scoped_engine.connect() as connection:
            row = connection.execute(
                text("""
                    SELECT p.product_category_id, c.product_category_name
                    FROM products AS p
                    JOIN product_categories AS c
                        ON c.product_category_id = p.product_category_id
                    WHERE p.product_id = :product_id
                """),
                {"product_id": product_id},
            ).one()

        assert tuple(row) == (42, "livros")
    finally:
        scoped_engine.dispose()
        with postgres_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            
def test_pipeline_rerun_recovers_after_order_items_failure(
    postgres_engine,
    monkeypatch,
):
    schema = f"test_rerun_{uuid4().hex}"
    customer_id, seller_id, product_id, order_id = (
        str(uuid4()) for _ in range(4)
    )

    datasets = {
        "customers": pd.DataFrame([{"customer_id": customer_id}]),
        "sellers": pd.DataFrame([{"seller_id": seller_id}]),
        "orders": pd.DataFrame([{
            "order_id": order_id,
            "customer_id": customer_id,
        }]),
        "order_items": pd.DataFrame([{
            "order_id": order_id,
            "order_item_id": 1,
            "product_id": product_id,
            "seller_id": seller_id,
        }]),
    }

    with postgres_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    scoped_engine = create_engine(
        postgres_engine.url,
        connect_args={"options": f"-c search_path={schema}"},
    )

    try:
        with scoped_engine.begin() as connection:
            for ddl in (
                "CREATE TABLE customers (customer_id UUID PRIMARY KEY)",
                "CREATE TABLE sellers (seller_id UUID PRIMARY KEY)",
                "CREATE TABLE products (product_id UUID PRIMARY KEY)",
                """
                CREATE TABLE orders (
                    order_id UUID PRIMARY KEY,
                    customer_id UUID NOT NULL REFERENCES customers(customer_id)
                )
                """,
                """
                CREATE TABLE order_items (
                    order_id UUID NOT NULL REFERENCES orders(order_id),
                    order_item_id INTEGER NOT NULL,
                    product_id UUID NOT NULL REFERENCES products(product_id),
                    seller_id UUID NOT NULL REFERENCES sellers(seller_id),
                    PRIMARY KEY (order_id, order_item_id)
                )
                """,
            ):
                connection.execute(text(ddl))

            connection.execute(
                text("INSERT INTO products VALUES (CAST(:id AS uuid))"),
                {"id": product_id},
            )

        monkeypatch.setattr(load, "_get_engine", lambda: scoped_engine)
        monkeypatch.setattr(load, "get_logger", Mock(return_value=Mock()))
        monkeypatch.setattr(pipeline, "get_logger", Mock(return_value=Mock()))
        monkeypatch.setattr(pipeline, "create_table", Mock())
        monkeypatch.setattr(pipeline, "validate_product", Mock())
        monkeypatch.setattr(pipeline, "validate_geolocation", Mock())
        monkeypatch.setattr(pipeline, "VALIDATE_LIST", ())
        monkeypatch.setattr(pipeline, "DATA_LIST", tuple(datasets))
        monkeypatch.setattr(
            pipeline, "_cleaning_dataset", lambda name: datasets[name].copy()
        )

        original_load_dataset = pipeline._load_dataset

        def fail_on_order_items(dataset, df):
            if dataset == "order_items":
                raise RuntimeError("simulated order_items load failure")
            original_load_dataset(dataset, df)

        with monkeypatch.context() as patch:
            patch.setattr(pipeline, "_load_dataset", fail_on_order_items)
            with pytest.raises(RuntimeError, match="simulated order_items load failure"):
                pipeline.main()

        with scoped_engine.connect() as connection:
            assert connection.execute(text("SELECT COUNT(*) FROM orders")).scalar_one() == 1
            assert connection.execute(text("SELECT COUNT(*) FROM order_items")).scalar_one() == 0

        # รันซ้ำบน schema เดิมหลังคืน loader จริง
        pipeline.main()

        with scoped_engine.connect() as connection:
            assert connection.execute(text("SELECT COUNT(*) FROM orders")).scalar_one() == 1
            item = connection.execute(text("""
                SELECT order_id, order_item_id, product_id, seller_id
                FROM order_items
            """)).one()

        assert (str(item.order_id), item.order_item_id) == (order_id, 1)
        assert str(item.product_id) == product_id
        assert str(item.seller_id) == seller_id
    finally:
        scoped_engine.dispose()
        with postgres_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
#endregion
