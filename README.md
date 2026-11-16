# CSV ETL Pipeline

A Docker-based ETL workflow that downloads nine Olist CSV datasets from MinIO, validates and transforms them, loads PostgreSQL, and uploads outputs grouped by run ID.

The Docker quick start below uses Docker Desktop and PowerShell. See the [setup guide](docs/setup.md) for local Python, Airflow, tests, and troubleshooting.

## Docker quick start

### 1. Prepare MinIO and source data

Start Docker Desktop (or Docker Engine with Compose). Place the nine source CSVs in `data/raw/` and run commands from the project root. MinIO is required by the current pipeline: every run downloads raw files from the bucket before processing.

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose -f compose.minio.yml up -d --build minio
docker compose -f compose.minio.yml build minio-test
docker compose -f compose.minio.yml run --rm minio-test
docker compose -f compose.minio.yml run --rm minio-test python scripts/upload_raw.py
```

Wait for MinIO to be ready before running `minio-test`. The test creates the configured bucket if missing and checks an upload/download round trip. The upload script then seeds `raw/` with your source CSVs. MinIO's first build compiles its source and requires network access.

Open the [MinIO console](http://localhost:9001) using `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD` from `.env`. The API is available at `http://localhost:9000`; objects persist in the `minio_data` volume.

### 2. Run the pipeline and PostgreSQL

The base `compose.yaml` supplies `DATABASE_URL` but does not pass S3 settings to the pipeline. Supply them explicitly. The endpoint below reaches MinIO on Docker Desktop from the pipeline container.

```powershell
docker compose config --quiet
docker compose build pipeline
docker compose up -d --wait postgres
docker compose run --rm --env-from-file .env -e S3_ENDPOINT_URL=http://host.docker.internal:9000 -e DATABASE_URL=postgresql+psycopg://etl_user:etl_password@postgres:5432/olist pipeline
$LASTEXITCODE
```

Use a Docker Compose version supporting `run --env-from-file`. On Linux, configure a reachable MinIO endpoint or host gateway instead of assuming `host.docker.internal` exists. Keep the S3 access keys in `.env` aligned with the MinIO credentials.

Check `$LASTEXITCODE` immediately after the run: `0` means success; a nonzero value means failure. `--rm` removes the finished pipeline container. Rebuild with `docker compose build pipeline` after changing code or dependencies.

Verify the latest run and database contents:

```powershell
Get-Content logs/pipeline/main.log -Tail 20
docker compose exec postgres psql -U etl_user -d olist -c "SELECT count(*) FROM orders;"
```

Look for `status=SUCCEEDED` for the latest run ID. Repeat the pipeline command above again with unchanged inputs and compare table counts to check for duplicate growth. Equal counts alone do not verify all stored values.

| Storage | Purpose |
| --- | --- |
| `./data:/app/data` | Source CSVs, generated outputs, geolocation mapping state, and the pipeline lock |
| `./logs:/app/logs` | Logs retained on the host after the pipeline container exits |
| `postgres_data` | PostgreSQL data retained when containers are recreated |

Inside Docker, the pipeline connects to `postgres:5432`. Applications running on the host connect to `localhost:5433`. The bundled credentials in `compose.yaml` are for local development.

Stop the services while retaining database data:

```powershell
docker compose down
```

To check persistence, run `docker compose up -d --wait postgres` again and repeat the count query before rerunning the pipeline. Do not add `-v` to `docker compose down` unless you intend to delete the database volume.


Stop MinIO while retaining its object storage volume:

```powershell
docker compose -f compose.minio.yml down
```

For full configuration and troubleshooting, see [Setup](docs/setup.md).

## Feature status

| Area               | Current implementation                                                                               |
| ------------------ | ---------------------------------------------------------------------------------------------------- |
| Docker             | Pipeline image and PostgreSQL Compose service                                                        |
| Airflow            | Manual DAG with DockerOperator, retries, and one active run; S3 environment wiring remains           |
| Object storage     | Local MinIO via boto3                                                                                |
| Great Expectations | Customers only: non-null and unique `customer_id`, plus two-uppercase-letter `customer_state` format |
| Spark              | Not implemented; transformations currently use Pandas                                                |

## Storage and quality flow

Each run acquires the pipeline lock, downloads the nine configured files from `raw/` in MinIO, then cleans and loads datasets in dependency order. Downloads replace local files via a temporary `.part` file. The bucket and raw objects must already exist.

Before customers are written to PostgreSQL, Great Expectations validates the cleaned DataFrame. A failed expectation raises an error and stops the run. The context is ephemeral; persistent GX reports or Data Docs are not configured. Other datasets use the existing Python/Pandas validation rules.

After each successful dataset load, the pipeline uploads its output files using the same run ID:

| Bucket prefix | Contents |
| --- | --- |
| `raw/` | Source CSVs seeded with `scripts/upload_raw.py` |
| `clean/<run_id>/` | Clean CSVs for each dataset |
| `rejected/<run_id>/` | Rejected CSVs with reasons |
| `validate/<run_id>/` | Validated categories, products, and geolocation CSVs |

Database commits and object uploads are separate operations. An upload failure stops the run but does not undo an already committed table. A failed run can leave partial output prefixes; inspect the final pipeline status before treating a run as complete.

## Pipeline and load keys

Each dataset is extracted from `data/raw/`, cleaned, and split into clean and rejected CSVs. Cleaning checks required fields, formats, ranges, and configured duplicate keys. The pipeline checks that clean plus rejected row counts equal the input row count and that every rejected row has a reason.

The table lists the load order. Categories, products, and geolocation also produce validated CSVs under `data/validate/`.

| Dataset | Load strategy |
| --- | --- |
| `product_categories` | Upsert by `product_category_name`. PostgreSQL assigns IDs to new categories. |
| `products` | Upsert by `product_id`. Resolve canonical category names to existing PostgreSQL IDs. |
| `geolocation` | Replace the entire snapshot in one transaction. |
| `customers` | Upsert by `customer_id`. |
| `sellers` | Upsert by `seller_id`. |
| `orders` | Upsert by `order_id`. |
| `order_payments` | Upsert by `order_id` and `payment_sequential`. Derive a deterministic UUID from that pair. |
| `order_reviews` | Upsert by `order_review_id` and `order_id`. |
| `order_items` | Upsert by `order_id` and `order_item_id` after orders, products, and sellers load. |

Before loading orders, payments, reviews, or items, the pipeline checks that their parent IDs exist in PostgreSQL. Missing references stop the run and the error includes sample IDs.

## Reruns and recovery

- All chunks for a table load share one transaction. If a later table fails, earlier table commits remain visible. Fix the cause and rerun from the beginning.
- Upserts update matching keys and retain rows omitted from later CSVs. Geolocation replaces its contents with the current validated snapshot.
- Keep `data/validate/geolocation_id_mapping.csv` across runs to preserve historical geolocation IDs, including IDs for removed rows. This file is local pipeline state. Back it up alongside the database if IDs must survive a move to a new checkout.
- `data/.pipeline.lock` rejects overlapping runs sharing the same data directory and compatible filesystem locking. Compose mounts this directory into pipeline containers. Separate data directories have separate locks; verify locking behavior when mixing Windows host runs and Linux containers.
- CSVs are replaced atomically one file at a time. If replacement fails on Windows, close the output file in Excel or other applications and rerun.
- Check `logs/pipeline/main.log` for the run ID, final status, and dataset load statuses.

## Project layout

| Path | Purpose |
| --- | --- |
| `src/pipeline.py` | ETL entry point, run lock, and load orchestration |
| `src/configuration.py` | Dataset rules and CSV paths |
| `src/extract.py`, `src/transform.py`, `src/validate.py` | Extraction, cleaning, and mapping |
| `src/quality.py` | Great Expectations customer quality gate |
| `src/storage.py` | MinIO raw downloads and output uploads |
| `scripts/test_minio.py`, `scripts/upload_raw.py` | Bucket connectivity check and raw-file seeding |
| `compose.minio.yml`, `Dockerfile.minio`, `Dockerfile.minio-test` | Local MinIO and storage helper containers |
| `src/load.py`, `sql/schema.sql` | PostgreSQL writes and schema |
| `data/raw/` | Source CSVs, named `olist_<dataset>_dataset.csv` except `product_categories.csv` |
| `data/clean/`, `data/rejected/`, `data/validate/` | Clean, rejected, and validated outputs |
| `dags/olist_etl.py` | Airflow DAG that launches the ETL container |
| `docker/airflow/Dockerfile` | Airflow image and Docker provider dependencies |
| `compose.yaml`, `docs/airflow.md` | Local services and Airflow setup instructions |
| `tests/`, `.github/workflows/ci.yml` | Unit and PostgreSQL integration tests |

See the [ER diagram](docs/er-diagram.md) for relationships.

## Next goals

- Pass S3 configuration into the Airflow ETL container and verify an end-to-end run.
- Extend Great Expectations coverage beyond customers.
- Add a Spark transformation exercise and compare its results with Pandas.
- Add a read-only FastAPI service serving loaded PostgreSQL data, with ETL kept as a separate command.
