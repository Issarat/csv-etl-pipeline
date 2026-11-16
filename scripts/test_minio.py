import os
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def main():
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
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError as exc:
        status = exc.response["ResponseMetadata"]["HTTPStatusCode"]

        if status != 404:
            raise

        s3.create_bucket(Bucket=bucket)
        print(f"Created bucket: {bucket}")

    test_dir = PROJECT_ROOT / "data" / "minio_test"
    test_dir.mkdir(parents=True, exist_ok=True)

    source_path = test_dir / "sample.csv"
    downloaded_path = test_dir / "downloaded_sample.csv"

    source_path.write_text(
        "order_id,amount\norder-001,150.00\n",
        encoding="utf-8",
    )

    key = "raw/test/sample.csv"

    s3.upload_file(str(source_path), bucket, key)
    print(f"Uploaded: s3://{bucket}/{key}")

    s3.download_file(bucket, key, str(downloaded_path))
    print(f"Downloaded: {downloaded_path}")

    if source_path.read_bytes() != downloaded_path.read_bytes():
        raise RuntimeError("Downloaded file does not match source")

    print("PASS: Uploaded and downloaded files match")


if __name__ == "__main__":
    main()