# CSV ETL Pipeline

A Python ETL pipeline that loads nine Olist datasets into PostgreSQL. It validates CSV records, exports rejected rows with reasons, and loads clean data in foreign-key order.

## Quick start

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
- A project-root `.pipeline.lock` rejects overlapping runs that share the same checkout. Separate checkouts have separate locks.
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
