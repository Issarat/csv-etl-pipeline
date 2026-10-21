# CSV ETL Pipeline

A Python ETL pipeline for all nine Olist datasets. It cleans CSV data,
exports rejected records, prepares category and geolocation mappings, and
optionally loads PostgreSQL tables with upserts.

## Quick start

Run commands from the project root. Install Python compatible with the pinned
packages in `requirements.txt`.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m src.pipeline
```

On macOS/Linux, create the environment with `python3 -m venv .venv` and use
`.venv/bin/python` instead of `.\.venv\Scripts\python.exe`.

The default `dev_mode = True` in `src/pipeline.py` runs cleaning and validation
without Docker, `.env`, database engine creation, or database connections.
Set it to `False` to create the schema and load PostgreSQL. This setting is
currently a Python variable, not a command-line flag.

## Supported datasets

| Dataset | Cleaning and output behavior | Upsert conflict key |
| --- | --- | --- |
| `customers` | Trim IDs and text; preserve ZIP as string | `customer_id` |
| `sellers` | Retain all four source columns; preserve ZIP as string | `seller_id` |
| `orders` | Normalize status; convert purchase/delivery dates | `order_id` |
| `order_payments` | Normalize payment type; validate amounts/installments; generate UUID | `order_id`, `payment_sequential` |
| `order_reviews` | Rename review ID; validate scores/dates; allow null comments | `order_review_id`, `order_id` |
| `order_items` | Convert dates/numbers; validate composite key | `order_id`, `order_item_id` |
| `product_categories` | Clean canonical names; assign IDs during validation | `product_category_name` |
| `products` | Convert numeric fields; map category names during validation | `product_id` |
| `geolocation` | Preserve ZIP string; convert coordinates; assign IDs during validation | `geolocation_id` |

## Pipeline flow

```text
data/raw/ -> extract -> transform -> data/clean/
                              `-> data/rejected/

customers, sellers, orders, order_payments, order_reviews:
    clean DataFrame -> database

product_categories, products, geolocation:
    clean CSV -> validate -> data/validate/ -> database

order_items:
    clean DataFrame -> retained until parent tables load -> database
```

In development mode, all database steps are skipped. Cleaning checks required
columns, reserved output columns, missing required values, type conversions,
and configured duplicate keys. Duplicate keys reject all occurrences.
Each rejected row has a nonempty `rejection_reason`; converted numeric/date
fields also retain original values in `raw_...` columns. Input row counts must
match clean plus rejected counts.

In database mode, load order is:

```text
customers -> sellers -> orders -> order_payments -> order_reviews
          -> product_categories -> products -> geolocation -> order_items
```

Each table load is transactional. The whole pipeline is not one transaction.
Upserts update supplied non-key columns; they do not remove rows absent from
subsequent input files.
## Files and folders

Paths are configured in `src/configuration.py`.

| Stage | Standard datasets | Product categories |
| --- | --- | --- |
| Raw | `data/raw/olist_<dataset>_dataset.csv` | `data/raw/product_categories.csv` |
| Clean | `data/clean/olist_<dataset>_clean.csv` | `data/clean/product_categories_clean.csv` |
| Rejected | `data/rejected/olist_<dataset>_rejected.csv` | `data/rejected/product_categories_rejected.csv` |
| Validated | `data/validate/olist_<dataset>_validated.csv` | `data/validate/product_categories_validated.csv` |

Only products, product categories, and geolocation currently have a separate
validation stage. Clean inputs are preserved when validated files are written.

```text
csv-etl-pipeline/
|-- compose.yaml
|-- requirements.txt
|-- data/{raw,clean,rejected,validate}/
|-- docs/
|-- logs/{pipeline,validate,load,profiling}/
|-- sql/schma.sql
|-- src/
|   |-- configuration.py   # Paths and dataset rules
|   |-- extract.py         # CSV extraction
|   |-- transform.py       # Shared cleaning and rejection rules
|   |-- validate.py        # Mapping and validated file generation
|   |-- load.py            # Lazy database setup and upserts
|   |-- pipeline.py        # Orchestration
|   |-- profiling.py       # Source data profiling
|   `-- logger.py          # Console and file logs
`-- tests/
```

## PostgreSQL and schema

[ER diagram](docs/er-diagram.md)
Use an accessible PostgreSQL server or the optional PostgreSQL 17 service in
`compose.yaml`. The provided Compose service exposes host port `5433`.

```powershell
docker compose up -d postgres
docker compose ps
```

For this local service, create a project-root `.env`:

```env
DATABASE_URL=postgresql+psycopg://etl_user:etl_password@localhost:5433/olist
```

Set `dev_mode = False`, then run `python -m src.pipeline` using your virtual
environment. Database configuration is read only when database functions run.
To apply the schema separately:

```powershell
.\.venv\Scripts\python.exe -m src.load
```

`sql/schma.sql` defines nine tables. Foreign keys are:

| Child column | Parent column |
| --- | --- |
| `orders.customer_id` | `customers.customer_id` |
| `order_items.order_id` | `orders.order_id` |
| `order_items.product_id` | `products.product_id` |
| `order_items.seller_id` | `sellers.seller_id` |
| `order_payments.order_id` | `orders.order_id` |
| `order_reviews.order_id` | `orders.order_id` |
| `products.product_category_id` | `product_categories.product_category_id` |

Source entity IDs are stored as UUIDs. Category IDs are integers generated by
`GENERATED BY DEFAULT AS IDENTITY`, allowing explicit validated IDs. Canonical
category names are unique and required; English names and product category
references may be null. Geolocation uses an integer primary key and a
non-unique indexed `VARCHAR(5)` ZIP. Seller ZIPs also use `VARCHAR(5)`.
Payment amounts use `NUMERIC(12, 2)`; schema checks enforce payment types,
numeric bounds, order statuses, and review scores.

`CREATE TABLE IF NOT EXISTS` does not generally upgrade existing tables. The
SQL explicitly updates category identity generation, adds missing order-item
product/seller references, and renames an old reviews `review_id` column.
An older payments table still needs a separate migration for its UUID primary
key, unique natural key, and payment-type check. Existing records must satisfy
foreign keys when those constraints are added.

Docker initializes SQL scripts only for a new database volume. Running
`python -m src.load` applies the current script to an existing database, subject
to the migration limits above. Stop containers without deleting data with
`docker compose down`.

## Profiling and tests

```powershell
.\.venv\Scripts\python.exe -m src.profiling
.\.venv\Scripts\python.exe -m pytest -q
```

Profiling has its own dataset list in `src/profiling.py`. Runtime exceptions
are logged with tracebacks and raised. Automated tests currently cover product
cleaning; database integration is not covered by the pytest suite.

## Troubleshooting

- No Docker: keep `dev_mode = True` for cleaning and validation only.
- Connection failure: verify `DATABASE_URL`, PostgreSQL availability, and port.
- Foreign-key failure: confirm referenced records survived cleaning and were
  loaded. Load ordering cannot resolve references to rejected parent rows.
- Ambiguous category: ensure each canonical/English alias identifies one category.
- Import failure: run from the project root using the virtual environment.

Additional documents: [Setup](docs/setup.md) and [ER diagram](docs/er-diagram.md). The
current implementation and `sql/schma.sql` define the behavior described here.
