# Setup

[Back to README](../README.md)

## Requirements

- Python compatible with the versions pinned in `requirements.txt`
- Docker Desktop with Docker Compose

Run all commands from the project root.

## 1. Create the Python environment

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### macOS or Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## 2. Configure the database connection

Create `.env` in the project root:

```env
DATABASE_URL=postgresql+psycopg://etl_user:etl_password@localhost:5433/olist
```

The host port must match the port published in `compose.yaml`.

## 3. Start PostgreSQL

`compose.yaml` runs PostgreSQL 17 and publishes container port `5432` on host
port `5433`.

```powershell
docker compose up -d postgres
docker compose ps
```

The service should become `healthy`, and its port mapping should include:

```text
0.0.0.0:5433->5432/tcp
```

Check database readiness:

```powershell
docker compose exec postgres pg_isready -U etl_user -d olist
```

Open a `psql` session when direct database access is needed:

```powershell
docker compose exec postgres psql -U etl_user -d olist
```

## 4. Create the database schema

The full pipeline creates missing tables automatically. To create or verify the
schema without running the complete pipeline:

```powershell
.\.venv\Scripts\python.exe -m src.load
```

Verify the tables:

```powershell
docker compose exec postgres psql -U etl_user -d olist -c "\dt"
```

`src.load.create_table()` reads `sql/schma.sql`, executes it in PostgreSQL, and
logs the user-created table names. `CREATE TABLE IF NOT EXISTS` creates missing
tables but does not migrate an existing table after its definition changes.

The `sql` directory is also mounted at `/docker-entrypoint-initdb.d`. The
PostgreSQL image runs those scripts only when it creates an empty database
volume. Use `python -m src.load` for an existing volume.

## 5. Run the pipeline

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m src.pipeline
```

macOS or Linux:

```bash
.venv/bin/python -m src.pipeline
```

## Stop PostgreSQL

Stop the container while retaining database data:

```powershell
docker compose down
```

Delete the container and database volume, including all local database data:

```powershell
docker compose down -v
```
