import os
from pathlib import Path

import boto3
from botocore.config import Config


RAW_FILES = (
    "olist_customers_dataset.csv",
    "olist_geolocation_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_orders_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "product_categories.csv",
)


def download_raw_files(raw_dir: Path) -> None:
    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
        region_name=os.environ["S3_REGION"],
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    )

    bucket = os.environ["S3_BUCKET"]
    raw_dir.mkdir(parents=True, exist_ok=True)

    for filename in RAW_FILES:
        key = f"raw/{filename}"
        destination = raw_dir / filename
        temporary = raw_dir / f"{filename}.part"

        try:
            s3.download_file(bucket, key, str(temporary))
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)

        print(f"Downloaded: s3://{bucket}/{key} -> {destination}")

    print(f"PASS: Downloaded {len(RAW_FILES)} raw files")

def upload_clean_file(clean_path: Path, run_id: str) -> str:
    if not clean_path.is_file():
        raise FileNotFoundError(f"Clean file not found: {clean_path}")

    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
        region_name=os.environ["S3_REGION"],
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    )

    bucket = os.environ["S3_BUCKET"]
    key = f"clean/{run_id}/{clean_path.name}"

    s3.upload_file(str(clean_path), bucket, key)
    print(f"Uploaded: {clean_path} -> s3://{bucket}/{key}")

    return key

def upload_reject_file(reject_path: Path, run_id: str) -> str:
    if not reject_path.is_file():
        raise FileNotFoundError(f"Clean file not found: {reject_path}")

    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
        region_name=os.environ["S3_REGION"],
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    )

    bucket = os.environ["S3_BUCKET"]
    key = f"rejected/{run_id}/{reject_path.name}"

    s3.upload_file(str(reject_path), bucket, key)
    print(f"Uploaded: {reject_path} -> s3://{bucket}/{key}")

    return key

def upload_valid_file(valid_path: Path, run_id: str) -> str:
    if not valid_path.is_file():
        raise FileNotFoundError(f"Clean file not found: {valid_path}")

    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
        region_name=os.environ["S3_REGION"],
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    )

    bucket = os.environ["S3_BUCKET"]
    key = f"validate/{run_id}/{valid_path.name}"

    s3.upload_file(str(valid_path), bucket, key)
    print(f"Uploaded: {valid_path} -> s3://{bucket}/{key}")

    return key