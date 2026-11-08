# Setup

[Back to README](../README.md)

Run all commands from the project root. Use Python 3.14 to match CI. For the bundled database, start Docker Desktop or a Docker Engine with the Compose plugin. The expected source CSVs are listed in the README and belong in `data/raw/`.

## 1. Install dependencies and configure PostgreSQL

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --wait postgres
```

On Windows with Git Bash, `bash setup_project.bash` performs these setup steps. Run the pipeline separately after setup.

macOS or Linux:

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
test -f .env || cp .env.example .env
docker compose up -d --wait postgres
```

Compose runs PostgreSQL 17 on host port `5433`, mapped to container port `5432`. The default `DATABASE_URL` in `.env.example` connects to the local `olist` database. For an existing PostgreSQL server, set `DATABASE_URL` to its connection URL and use that server in place of Compose.

## 2. Run and verify the pipeline

```powershell
.\.venv\Scripts\python.exe -m src.pipeline
Get-Content logs/pipeline/main.log -Tail 20
docker compose exec postgres psql -U etl_user -d olist -c "\dt"
docker compose exec postgres psql -U etl_user -d olist -c "SELECT count(*) FROM orders;"
```

On macOS/Linux, use `.venv/bin/python -m src.pipeline` and `tail -n 20 logs/pipeline/main.log`. Look for `status=SUCCEEDED` with the latest run ID. Inspect `data/rejected/` for rejected rows and `data/validate/` for mapped outputs.

The pipeline applies `sql/schema.sql` before loading. To apply just the schema, run `python -m src.load` with the virtual environment's Python. Compose runs initialization SQL automatically when it creates an empty database volume. For an existing database, review the SQL before running it. Its explicit changes handle selected legacy schemas, and `CREATE TABLE IF NOT EXISTS` leaves other existing table definitions in place.

## 3. Run tests

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
