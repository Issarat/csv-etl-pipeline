# CSV ETL Pipeline

A Python ETL pipeline for Olist CSV datasets: `customers`, `orders`,
`order_items`, `product_categories`, `products`, and `geolocation`.

The pipeline extracts CSV files, cleans records, exports rejected rows,
prepares validated datasets, and optionally upserts records into PostgreSQL.

## Setup

Run commands from the project root. Install Python compatible with the
versions pinned in `requirements.txt`.

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m src.pipeline
```

### macOS / Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m src.pipeline
```

## Development mode

`dev_mode = True` in `src/pipeline.py` is the current default. It runs cleaning
and validation without loading `.env`, creating a database engine, creating
tables, or connecting to PostgreSQL. Docker and `DATABASE_URL` are not required
in this mode.

Set `dev_mode = False` to create the schema and load data into PostgreSQL.
This is a Python setting, not a command-line argument or environment variable.

## Data flow

```text
data/raw/ -> extract -> transform -> data/clean/
                              `-> data/rejected/

customers / orders / order_items:
    clean DataFrame -> PostgreSQL (database mode)

product_categories / products / geolocation:
    data/clean/ -> validate -> data/validate/ -> PostgreSQL (database mode)
```

`main()` processes datasets in this order:

1. Clean customers, orders, and order items; load each in database mode.
2. Clean product categories, products, and geolocation.
3. Run `validate_product()` and `validate_geolocation()`.
4. In database mode, read validated CSV files and load categories, products,
   and geolocation in that order.

Cleaning uses shared preparation, type conversion, field validation, and
clean/rejected splitting. Each rejected row includes `rejection_reason`.
Configured date and numeric fields retain their original values in `raw_...`
columns on rejected rows. Clean plus rejected row counts must equal the input.
Current shared rules reject missing configured numeric fields, including those
in products.

## Product validation

`validate_product()` writes both category and product outputs:

- Match product category names against either `product_category_name` or
  `product_category_name_english`, then resolve to the canonical category name.
- Use an existing validated category mapping when available; otherwise start
  from the clean category file and assign integer IDs starting at 1.
- Preserve existing IDs and append unknown category names using IDs above the
  current maximum. New categories have a null English name.
- Replace `product_category_name` in products with nullable integer
  `product_category_id`. Missing category names produce null IDs.
- Reject ambiguous category aliases or invalid category mappings by raising an
  error rather than writing new outputs.

The clean category data is checked for duplicate canonical names before IDs
are assigned. English category names may be null. Validation preserves clean
input files.

## Geolocation validation

ZIP prefixes are read as strings during extraction so leading zeroes such as
`01037` are preserved. Cleaning converts latitude and longitude to numbers and
allows multiple rows with the same ZIP prefix.

`validate_geolocation()`:

1. Reads the clean geolocation CSV with ZIP prefixes as strings.
2. Renames `geolocation_zip_code_prefix` to `zip_code`.
3. Adds integer `geolocation_id` values starting at 1 in file row order.
4. Writes the validated CSV without modifying the clean input.

Geolocation IDs are regenerated from row order on each validation run. They
are not stable identifiers if the input rows are reordered or removed.

## File paths

Paths are defined in `src/configuration.py`.

| Stage | Standard dataset | Product categories |
| --- | --- | --- |
| Raw | `data/raw/olist_<dataset>_dataset.csv` | `data/raw/product_categories.csv` |
| Clean | `data/clean/olist_<dataset>_clean.csv` | `data/clean/product_categories_clean.csv` |
| Rejected | `data/rejected/olist_<dataset>_rejected.csv` | `data/rejected/product_categories_rejected.csv` |
| Validated | `data/validate/olist_<dataset>_validated.csv` | `data/validate/product_categories_validated.csv` |

Products and geolocation produce `olist_products_validated.csv` and
`olist_geolocation_validated.csv` under `data/validate/`.

## PostgreSQL setup

Use an accessible PostgreSQL server, or optionally start the local PostgreSQL
17 service defined in `compose.yaml`:

```powershell
docker compose up -d postgres
docker compose ps
```

The local service exposes host port `5433`. Create `.env` in the project root
using the local development credentials from Compose:

```env
DATABASE_URL=postgresql+psycopg://etl_user:etl_password@localhost:5433/olist
```

Set `dev_mode = False` in `src/pipeline.py`, then run the pipeline as shown
above. Database configuration and engine creation happen only when database
functions are called.

To apply the schema separately:

```powershell
.\.venv\Scripts\python.exe -m src.load
```

The schema is stored in `sql/schma.sql`. It defines six tables:

| Table | Upsert conflict key | Loaded from |
| --- | --- | --- |
| `customers` | `customer_id` | Clean DataFrame |
| `orders` | `order_id` | Clean DataFrame |
| `order_items` | `order_id`, `order_item_id` | Clean DataFrame |
| `product_categories` | `product_category_name` | Validated CSV |
| `products` | `product_id` | Validated CSV |
| `geolocation` | `geolocation_id` | Validated CSV |

Orders reference customers, order items reference orders, and products
reference product categories. Geolocation uses an integer primary key and a
non-unique indexed `zip_code` of type `VARCHAR(5)`.

Category IDs use `GENERATED BY DEFAULT AS IDENTITY`, allowing IDs supplied by
validated files. Category names are unique and required; English names and
product category references may be null.

The loader uses `INSERT ... ON CONFLICT DO UPDATE`. Each table load has its
own transaction; the entire pipeline is not one transaction. Upserts do not
delete database rows absent from later input files.

`CREATE TABLE IF NOT EXISTS` creates missing tables but does not generally
migrate existing table structures. The schema also explicitly sets the category
identity column to `GENERATED BY DEFAULT`. Docker initialization scripts run
only for a new database volume; use `python -m src.load` to apply the schema to
an existing database.

## Project layout

```text
csv-etl-pipeline/
|-- compose.yaml
|-- data/
|   |-- raw/
|   |-- clean/
|   |-- rejected/
|   `-- validate/
|-- logs/
|-- sql/schma.sql
|-- src/
|   |-- configuration.py   # Dataset paths and cleaning rules
|   |-- extract.py         # CSV reading
|   |-- transform.py       # Shared cleaning and row rejection
|   |-- validate.py        # Product/category and geolocation validation
|   |-- load.py            # Lazy database setup and upserts
|   |-- pipeline.py        # Cleaning, validation, and load orchestration
|   |-- profiling.py       # Source data profiling
|   `-- logger.py          # File and console logging
|-- tests/
|-- .gitignore
`-- requirements.txt
```

## Profiling, logs, and tests

```powershell
.\.venv\Scripts\python.exe -m src.profiling
.\.venv\Scripts\python.exe -m pytest -q
```

Profiling uses its own dataset list in `src/profiling.py`; some profiled
sources are not part of the ETL pipeline. Logs are written under
`logs/pipeline/`, `logs/validate/`, `logs/load/`, and `logs/profiling/`.
Exceptions are logged and raised.

Automated tests currently cover product cleaning, including type conversion,
missing fields, duplicate product IDs, and preserving category names for
validation. Database integration tests are not part of the pytest suite.

## Troubleshooting

- **No Docker on this machine:** keep `dev_mode = True` to generate clean,
  rejected, and validated files without a database.
- **Database connection fails:** check `DATABASE_URL`, the server, and the host
  port (`5433` for the provided Compose configuration).
- **Ambiguous category mapping:** ensure each canonical or English alias maps
  to only one category.
- **Import errors:** run from the project root with the virtual environment's
  Python executable.

Stop the local database while retaining its volume:

```powershell
docker compose down
```
