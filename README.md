# CSV ETL Pipeline

A Python ETL pipeline that loads nine Olist datasets into PostgreSQL. It validates CSV records, exports rejected rows with reasons, and loads clean data in foreign-key order.

## Quick start

### Docker: run the pipeline and PostgreSQL

Start Docker Desktop (or Docker Engine with Compose) and place the source CSVs in `data/raw/`. Run these commands from the project root. No local Python installation, virtual environment, or `.env` file is required for this option; Compose supplies the database URL.

```powershell
docker compose config --quiet
docker compose build pipeline
docker compose up -d --wait postgres
docker compose run --rm pipeline
$LASTEXITCODE
```

The pipeline waits for PostgreSQL's health check and exits when the ETL job finishes. Check `$LASTEXITCODE` immediately after the run: `0` means success; a nonzero value means failure. `--rm` removes the finished pipeline container. Rebuild with `docker compose build pipeline` after changing code or dependencies.

Verify the latest run and database contents:

```powershell
Get-Content logs/pipeline/main.log -Tail 20
docker compose exec postgres psql -U etl_user -d olist -c "SELECT count(*) FROM orders;"
```

Look for `status=SUCCEEDED` for the latest run ID. Run `docker compose run --rm pipeline` again with unchanged inputs and compare table counts to check for duplicate growth. Equal counts alone do not verify all stored values.

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

From the project root on Windows with Python 3.14 and Docker Compose:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --wait postgres
.\.venv\Scripts\python.exe -m src.pipeline
```

The pipeline requires PostgreSQL. See [Setup](docs/setup.md) for Git Bash, macOS/Linux, database checks, and integration tests.

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
| `src/load.py`, `sql/schema.sql` | PostgreSQL writes and schema |
| `data/raw/` | Source CSVs, named `olist_<dataset>_dataset.csv` except `product_categories.csv` |
| `data/clean/`, `data/rejected/`, `data/validate/` | Clean, rejected, and validated outputs |
| `tests/`, `.github/workflows/ci.yml` | Unit and PostgreSQL integration tests |

See the [ER diagram](docs/er-diagram.md) for relationships.

## Tests and profiling

```powershell
.\.venv\Scripts\python.exe -m pytest -q -rs
.\.venv\Scripts\python.exe -m src.profiling
```

GitHub Actions runs pytest with Python 3.14 and PostgreSQL 17. Integration tests cover repeat upserts, rollback after a later chunk fails, category ID preservation, and rerunning after a pipeline failure. Locally, integration tests are skipped unless `TEST_DATABASE_URL` is set.

## Next goal

Add a read-only FastAPI service that serves data already loaded into PostgreSQL. Keep ETL execution as a separate command.
