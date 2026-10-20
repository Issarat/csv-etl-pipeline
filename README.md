# CSV ETL Pipeline

A Python project for migrating CSV data into a database using an extract, transform, and load (ETL) pipeline. The repository contains Olist e-commerce CSV datasets and a starter structure for a PostgreSQL pipeline.

## Project status

This project is currently a scaffold. The Python modules, SQL schema file, and test file are empty. Data extraction, transformation, database loading, and automated tests still need to be implemented.

## Planned workflow

1. **Extract:** Read source CSV files from `data/raw/`.
2. **Transform:** Clean and validate records for the target database.
3. **Load:** Insert the transformed records into PostgreSQL.

## Project structure

```text
csv-etl-pipeline/
├── data/
│   ├── raw/                 # Source Olist CSV datasets
│   └── provessed/           # Reserved for processed data (current folder name)
├── sql/
│   └── schma.sql            # Placeholder for the database schema
├── src/
│   ├── __init__.py
│   ├── extract.py           # Extraction placeholder
│   ├── transform.py         # Transformation placeholder
│   ├── load.py              # Database loading placeholder
│   └── pipeline.py          # Pipeline entry point placeholder
├── tests/
│   └── test_transform.py    # Transformation test placeholder
├── .gitignore
├── requirements.txt
└── README.md
```

The folder name `provessed` and filename `schma.sql` reflect their current spelling in the repository.

## Setup

Install Python with `pip`, then run the following commands from the project root.

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### macOS / Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Use the virtual environment's Python executable for subsequent commands, or activate the environment first.

## Dependencies

Dependencies are pinned in `requirements.txt`. The main libraries are:

- **pandas and NumPy:** CSV processing and data transformation.
- **SQLAlchemy and psycopg:** PostgreSQL connectivity and database operations.
- **python-dotenv:** Local environment configuration.
- **pytest:** Automated testing.

## Source data

`data/raw/` contains CSV files for customers, geolocation, orders, order items, payments, reviews, products, sellers, and product category name translations.

Keep original CSV files in `data/raw/`. The `data/provessed/` directory is reserved for generated transformation output.

## Running the pipeline

After implementing the modules, the intended entry point is:

```bash
python -m src.pipeline
```

At present, this command exits without processing data because `src/pipeline.py` is empty. Database connection settings and schema setup are not implemented yet.

## Tests

Once tests are added, run:

```bash
python -m pytest
```

The current test file is empty, so pytest will collect no tests.

## Local configuration

The `.gitignore` excludes virtual environments, Python caches, test and coverage output, build artifacts, logs, and `.env` files. Keep database credentials in local configuration rather than committing them. No environment variable names have been defined by the application yet.
