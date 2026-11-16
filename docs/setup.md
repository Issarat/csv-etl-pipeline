# Setup and project guide

A Python ETL pipeline that loads nine Olist datasets into PostgreSQL. It validates CSV records, exports rejected rows with reasons, and loads clean data in foreign-key order. It downloads source CSVs from MinIO (S3-compatible storage), applies a Great Expectations quality gate to customers, and archives outputs by run ID. An Airflow DAG launches the ETL image through DockerOperator; its S3 environment still needs configuring.

[Back to README](../README.md)

Run all commands from the project root.

## Quick start

### Prepare MinIO and source data

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

### Docker: run the pipeline and PostgreSQL

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

### Local Python with PostgreSQL in Docker

Prepare MinIO and seed its bucket as described above. For a Windows host run, keep `S3_ENDPOINT_URL=http://localhost:9000` and the host database URL from `.env`. Then, with Python 3.14 and Docker Compose:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --wait postgres
.\.venv\Scripts\python.exe -m src.pipeline
```

The pipeline requires PostgreSQL. See [Setup](#local-development-and-integration-tests) for Git Bash, macOS/Linux, database checks, and integration tests.

### Airflow: run the pipeline from the web UI

The optional `airflow` Compose profile starts Airflow 3.1.8 in standalone mode with a separate PostgreSQL metadata database. `DockerOperator` launches `csv-etl-pipeline:local` on the same network as the Olist database. Airflow dependencies are installed in its own image; no local Airflow installation is required.

```powershell
New-Item -ItemType Directory -Force logs | Out-Null
docker compose build pipeline
docker compose --profile airflow build airflow
docker compose --profile airflow up -d postgres airflow-postgres airflow
docker compose logs -f airflow
```

After startup, press Ctrl+C to stop following logs. Retrieve the generated password:

```powershell
docker compose exec airflow cat /opt/airflow/simple_auth_manager_passwords.json.generated
```

**Current integration gap:** `dags/olist_etl.py` passes only `DATABASE_URL` to the ETL container. Before triggering the current pipeline, add `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET`, and `S3_REGION` to the DockerOperator environment using your Airflow configuration or secrets. The endpoint must be reachable from the ETL container. The pipeline image does not include `.env`, and Compose's `.env` is not automatically forwarded to DockerOperator containers.

Open [Airflow](http://localhost:8080), log in as `admin`, unpause `olist_etl`, and click **Trigger**. Open the run, select `run_pipeline`, and inspect **Logs**. Triggering runs the real ETL and writes to PostgreSQL.

| DAG setting | Current behavior |
| --- | --- |
| Task | One `run_pipeline` task invokes `python -m src.pipeline` |
| Schedule | Manual only (`schedule=None`) |
| Retry | Two retries, five minutes apart |
| Concurrency | One active DAG run (`max_active_runs=1`) |
| Catchup | Disabled |
| Data and logs | Host directories mounted into the ETL container |

For the current Windows checkout at `D:\csv-etl-pipeline`, the default Docker daemon host path is `/run/desktop/mnt/host/d/csv-etl-pipeline`. For a different checkout or host OS, set `ETL_HOST_PROJECT_DIR` in `.env` to the absolute project path visible to the Docker daemon and recreate the Airflow service. Compose supplies the database URL and host path as environment-backed Airflow Variables.

#### Manual verification

Earlier manual verification recorded two successful Airflow runs with unchanged inputs. These results do not verify the current MinIO-enabled DAG configuration. After the second run, the following database counts matched the processed row counts:

| Table | Verified rows |
| --- | ---: |
| `order_items` | 112,650 |
| `order_payments` | 103,886 |
| `order_reviews` | 99,224 |

Recheck these tables after a rerun:

```powershell
docker compose exec postgres psql -U etl_user -d olist -c "SELECT 'order_items' AS dataset, COUNT(*) FROM order_items UNION ALL SELECT 'order_payments', COUNT(*) FROM order_payments UNION ALL SELECT 'order_reviews', COUNT(*) FROM order_reviews;"
```

These counts are a manual check for duplicate growth in this dataset, not a complete comparison of stored values or all nine tables. Retry recovery and scheduled execution have not yet been manually verified.

Stop Airflow while retaining its state and both databases:

```powershell
docker compose --profile airflow stop airflow airflow-postgres
```

This standalone setup is for local learning. The Docker socket gives Airflow access to the host Docker engine. See [Airflow setup and testing](airflow.md) for import checks, mount diagnostics, and troubleshooting.

## Tests and profiling

```powershell
.\.venv\Scripts\python.exe -m pytest -q -rs
.\.venv\Scripts\python.exe -m src.profiling
```

GitHub Actions runs pytest with Python 3.14 and PostgreSQL 17. Integration tests cover repeat upserts, rollback after a later chunk fails, category ID preservation, and rerunning after a pipeline failure. Locally, integration tests are skipped unless `TEST_DATABASE_URL` is set.

## Local development and integration tests

Run all commands from the project root. Use Python 3.14 to match CI. For the bundled database, start Docker Desktop or a Docker Engine with the Compose plugin. Place the nine source CSVs in `data/raw/`; filenames follow the [project layout](../README.md#project-layout). Prepare MinIO and seed the bucket using the quick-start instructions before running the pipeline locally. Keep `S3_ENDPOINT_URL=http://localhost:9000` in `.env` for host runs.

### 1. Install dependencies and configure PostgreSQL

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --wait postgres
```

macOS or Linux:

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
test -f .env || cp .env.example .env
docker compose up -d --wait postgres
```

Compose runs PostgreSQL 17 on host port `5433`, mapped to container port `5432`. The default `DATABASE_URL` in `.env.example` connects to the local `olist` database. For an existing PostgreSQL server, set `DATABASE_URL` to its connection URL and use that server in place of Compose.

### 2. Run and verify the pipeline

```powershell
.\.venv\Scripts\python.exe -m src.pipeline
Get-Content logs/pipeline/main.log -Tail 20
docker compose exec postgres psql -U etl_user -d olist -c "\dt"
docker compose exec postgres psql -U etl_user -d olist -c "SELECT count(*) FROM orders;"
```

On macOS/Linux, use `.venv/bin/python -m src.pipeline` and `tail -n 20 logs/pipeline/main.log`. Look for `status=SUCCEEDED` with the latest run ID. Inspect `data/rejected/` for rejected rows and `data/validate/` for mapped outputs.

The pipeline applies `sql/schema.sql` before loading. To apply just the schema, run `python -m src.load` with the virtual environment's Python. Compose runs initialization SQL automatically when it creates an empty database volume. For an existing database, review the SQL before running it. Its explicit changes handle selected legacy schemas, and `CREATE TABLE IF NOT EXISTS` leaves other existing table definitions in place.

### 3. Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q -rs
```

For integration tests, create a dedicated database once and set `TEST_DATABASE_URL` in the current shell:

```powershell
docker compose exec postgres createdb -U etl_user olist_test
$env:TEST_DATABASE_URL = 'postgresql+psycopg://etl_user:etl_password@localhost:5433/olist_test'
.\.venv\Scripts\python.exe -m pytest -q -rs
```

In Bash, use `export TEST_DATABASE_URL='postgresql+psycopg://etl_user:etl_password@localhost:5433/olist_test'`. Tests create and drop database objects, so point this variable at the dedicated test database.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Database connection fails | Check `docker compose ps` and confirm that the host port and credentials match `DATABASE_URL`. |
| A referenced ID is missing | Look up the example IDs in the parent dataset and its rejected CSV. After fixing the source or validation issue, rerun the pipeline. |
| Another run is in progress | Wait for the process using this checkout to finish. |
| CSV replacement fails | Close the output CSV in Excel or any other application that has it open, then rerun. |

Use `docker compose down` to stop PostgreSQL and retain the database volume.
