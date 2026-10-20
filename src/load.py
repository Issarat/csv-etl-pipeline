import os
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv
from psycopg import ClientCursor
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from src.logger import get_logger

#regein load .env
load_dotenv()

engine = create_engine(
    os.environ["DATABASE_URL"],
    pool_pre_ping=True,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("ไม่พบ DATABASE_URL ในไฟล์ .env")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)
#endregein
def create_table() -> list[str]:
    logger = get_logger(
        dataset_name="create_table",
        log_type="load",
    )

    schema_file = PROJECT_ROOT / "sql" / "schma.sql"

    try:
        if not schema_file.exists():
            raise FileNotFoundError(
                f"ไม่พบไฟล์ schema: {schema_file}"
            )

        schema_sql = schema_file.read_text(encoding="utf-8")

        if not schema_sql.strip():
            raise ValueError("ไฟล์ schma.sql ไม่มีคำสั่ง SQL")

        psycopg_url = DATABASE_URL.replace(
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

if __name__ == "__main__":
    try:
        create_table()
    except Exception:
        raise SystemExit(1)