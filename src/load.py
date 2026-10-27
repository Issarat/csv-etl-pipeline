import os
from pathlib import Path
from functools import lru_cache

import pandas as pd
import psycopg
from dotenv import load_dotenv
from psycopg import ClientCursor
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import MetaData, Table

from src.logger import get_logger

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _get_database_url() -> str:
    load_dotenv(PROJECT_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("ไม่พบ DATABASE_URL ในไฟล์ .env")
    return database_url


@lru_cache(maxsize=1)
def _get_engine():
    return create_engine(_get_database_url(), pool_pre_ping=True)


def create_table() -> list[str]:
    logger = get_logger(
        dataset_name="create_table",
        log_type="load",
    )

    schema_file = PROJECT_ROOT / "sql" / "schema.sql"

    try:
        if not schema_file.exists():
            raise FileNotFoundError(
                f"ไม่พบไฟล์ schema: {schema_file}"
            )

        schema_sql = schema_file.read_text(encoding="utf-8")

        if not schema_sql.strip():
            raise ValueError("ไฟล์ schma.sql ไม่มีคำสั่ง SQL")

        psycopg_url = _get_database_url().replace(
            "postgresql+psycopg://",
            "postgresql://",
            1,
        )

        # หาก SQL มีปัญหา transaction จะ rollback ให้อัตโนมัติ
        with psycopg.connect(
            psycopg_url,
            cursor_factory=ClientCursor,
        ) as connection:
            connection.execute(schema_sql)

            rows = connection.execute(
                """
                SELECT schemaname, tablename
                FROM pg_catalog.pg_tables
                WHERE schemaname NOT IN (
                    'pg_catalog',
                    'information_schema'
                )
                ORDER BY schemaname, tablename;
                """
            ).fetchall()

        table_names = [
            f"{schema_name}.{table_name}"
            for schema_name, table_name in rows
        ]

        logger.info("สร้าง database schema สำเร็จ")
        logger.info(
            "\n%s\nDATABASE TABLES\n%s",
            "=" * 65,
            "=" * 65,
        )

        for table_name in table_names:
            logger.info("- %s", table_name)

        return table_names

    except FileNotFoundError:
        logger.exception("ไม่พบไฟล์ schema")
        raise

    except (psycopg.Error, OSError, ValueError):
        logger.exception("สร้าง database schema ไม่สำเร็จ")
        raise

def load_dataframe(
    df: pd.DataFrame,
    table_name: str,
    if_exists: str = "append",
) -> None:
    logger = get_logger(
        dataset_name=table_name,
        log_type="load",
    )

    try:
        if df.empty:
            logger.warning(
                "ไม่ได้โหลดข้อมูล: DataFrame ของ %s ไม่มีข้อมูล",
                table_name,
            )
            return

        # หากโหลดไม่สำเร็จ transaction จะ rollback
        with _get_engine().begin() as connection:
            df.to_sql(
                name=table_name,
                con=connection,
                if_exists=if_exists,
                index=False,
                chunksize=1000,
                method="multi",
            )

        logger.info(
            "Loaded %s rows into %s",
            f"{len(df):,}",
            table_name,
        )

    except SQLAlchemyError:
        logger.exception(
            "Database error while loading table %s",
            table_name,
        )
        raise

    except (ValueError, TypeError):
        logger.exception(
            "Invalid data while loading table %s",
            table_name,
        )
        raise

def replace_geolocation(df: pd.DataFrame, chunk_size: int = 1000) -> None:
    """Replace the current geolocation snapshot atomically, including empty input."""
    expected = {"geolocation_id", "zip_code", "geolocation_lat", "geolocation_lng", "geolocation_city", "geolocation_state"}
    if set(df.columns) != expected:
        raise ValueError("Geolocation snapshot columns do not match the schema")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    logger = get_logger(dataset_name="geolocation", log_type="load")
    try:
        with _get_engine().begin() as connection:
            table = Table("geolocation", MetaData(), autoload_with=connection)
            connection.execute(table.delete())
            for start in range(0, len(df), chunk_size):
                chunk = df.iloc[start:start + chunk_size]
                records = chunk.astype(object).where(pd.notna(chunk), None).to_dict(orient="records")
                connection.execute(table.insert(), records)
        logger.info("Replaced geolocation with %s rows", len(df))
    except Exception:
        logger.exception("Failed to replace geolocation")
        raise


def upsert_dataframe(
    df: pd.DataFrame,
    table_name: str,
    conflict_columns: tuple[str, ...],
    chunk_size: int = 1000,
) -> None:
    logger = get_logger(
        dataset_name=table_name,
        log_type="load",
    )

    try:
        if df.empty:
            logger.warning(
                "ไม่ได้โหลดข้อมูล: %s ไม่มีข้อมูล",
                table_name,
            )
            return

        missing_columns = (
            set(conflict_columns) - set(df.columns)
        )

        if missing_columns:
            raise ValueError(
                "Missing conflict columns: "
                f"{sorted(missing_columns)}"
            )

        with _get_engine().begin() as connection:
            metadata = MetaData()

            table = Table(
                table_name,
                metadata,
                autoload_with=connection,
            )

            for start in range(0, len(df), chunk_size):
                chunk = df.iloc[start:start + chunk_size]

                records = (
                    chunk.astype(object)
                    .where(pd.notna(chunk), None)
                    .to_dict(orient="records")
                )

                statement = insert(table).values(records)

                update_values = {
                    column:
                    statement.excluded[column]
                    for column in df.columns
                    if column not in conflict_columns
                }

                if update_values:
                    statement = (
                        statement.on_conflict_do_update(
                            index_elements=list(
                                conflict_columns
                            ),
                            set_=update_values,
                        )
                    )
                else:
                    statement = (
                        statement.on_conflict_do_nothing(
                            index_elements=list(
                                conflict_columns
                            )
                        )
                    )

                connection.execute(statement)

        logger.info(
            "Upserted %s rows into %s",
            f"{len(df):,}",
            table_name,
        )

    except (SQLAlchemyError, ValueError):
        logger.exception(
            "Upsert failed for table %s",
            table_name,
        )
        raise

if __name__ == "__main__":
    try:
        create_table()
    except Exception:
        raise SystemExit(1)
