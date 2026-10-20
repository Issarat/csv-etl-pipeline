import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

load_dotenv()

database_url = os.getenv("DATABASE_URL")

if not database_url:
    raise RuntimeError("ไม่พบ DATABASE_URL ในไฟล์ .env")

engine = create_engine(database_url, pool_pre_ping=True)

try:
    with engine.connect() as connection:
        version = connection.execute(
            text("SELECT version()")
        ).scalar_one()

        database = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

    print("เชื่อมต่อ PostgreSQL สำเร็จ")
    print(f"Database: {database}")
    print(f"Version: {version}")

except SQLAlchemyError as error:
    print("เชื่อมต่อ PostgreSQL ไม่สำเร็จ")
    print(error)