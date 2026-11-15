# Airflow locally with Docker Desktop

This is a local learning setup using Airflow 3.1.8 standalone, its own
PostgreSQL metadata database, and DockerOperator. The ETL database is separate.
Airflow dependencies live in docker/airflow/Dockerfile, not requirements.txt.
The UI binds only to localhost. The Docker socket gives Airflow control of the
local Docker engine; use trusted DAGs only. This is not a production deployment.

## Start (PowerShell, project root)

Ensure Docker Desktop is running with Linux containers. Keep the source CSVs
in data/raw. Create logs if necessary:

```powershell
New-Item -ItemType Directory -Force logs | Out-Null
docker compose build pipeline
docker compose --profile airflow build airflow
docker compose --profile airflow up -d postgres airflow-postgres airflow
docker compose --profile airflow ps
docker compose logs -f airflow
```

Wait for startup; Ctrl+C stops following logs without stopping the service.
Open http://localhost:8080 and log in as admin using the generated password:

```powershell
docker compose exec airflow cat /opt/airflow/simple_auth_manager_passwords.json.generated
```

## Verify Docker, imports and mounts

```powershell
docker compose exec airflow python -c "import docker; c=docker.from_env(); print(c.ping()); print(c.images.get('csv-etl-pipeline:local').id)"
docker compose exec airflow airflow dags list-import-errors
docker compose exec airflow airflow dags list
```

The DAG uses the Linux Docker Desktop host path
/run/desktop/mnt/host/d/csv-etl-pipeline by default for this checkout on D:.
This path must point to the actual host checkout, not /opt/airflow inside the
Airflow container. Check the raw directory before triggering ETL:

```powershell
docker run --rm --mount type=bind,source=/run/desktop/mnt/host/d/csv-etl-pipeline/data,target=/data alpine:3.21 ls /data/raw
```

If that path is unavailable, use the actual daemon-visible directory. Add
ETL_HOST_PROJECT_DIR to .env (see .env.example), then recreate Airflow:

```powershell
docker compose --profile airflow up -d --force-recreate airflow
```

Environment-backed Airflow Variables provide the ETL database URL and host path;
they do not need to be entered in the UI and may not appear in its variable list.

## Run and inspect

Find olist_etl in the UI, unpause it, then Trigger. Inspect the run_pipeline task
logs. The DAG has no schedule, retries twice with five-minute delays, and permits
one active run. Check logs/pipeline/main.log and PostgreSQL after success. ETL
writes real data and commits per table; rerunning uses the existing upsert rules.

CLI alternative (also performs the real ETL):

```powershell
docker compose exec airflow airflow dags unpause olist_etl
docker compose exec airflow airflow dags trigger olist_etl
```

If the UI is missing, inspect docker compose logs --tail 150 airflow. If the task
reports socket permission denied, inspect socket ownership in the container and
configure the matching supplemental group for your Docker installation. If the
image is missing, rebuild pipeline. A mount error requires correcting the host
path. A database connection error requires the csv-etl-network network and a
healthy postgres service. Failed ETL containers remain for diagnosis.

## Stop Airflow, keep data

```powershell
docker compose --profile airflow stop airflow airflow-postgres
```

Do not use down -v unless you intend to delete database and Airflow state volumes.
