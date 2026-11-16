import os
from pathlib import Path

import boto3
from botocore.config import Config


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
    raw_dir = Path("/app/data/raw")
    files = sorted(raw_dir.glob("*.csv"))

    if not files:
        raise FileNotFoundError(f"No CSV files found in {raw_dir}")

    for path in files:
        key = f"raw/{path.name}"
        s3.upload_file(str(path), bucket, key)
        print(f"Uploaded: {path.name} -> s3://{bucket}/{key}")

    print(f"PASS: Uploaded {len(files)} CSV files")


if __name__ == "__main__":
    main()