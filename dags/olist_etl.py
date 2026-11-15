from datetime import timedelta

import pendulum
from airflow.sdk import DAG
from airflow.providers.docker.operators.docker import DockerOperator
from docker.types import Mount


with DAG(
    dag_id="olist_etl",
    description="Run the existing Olist ETL image",
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Bangkok"),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["olist", "etl"],
) as dag:
    run_pipeline = DockerOperator(
        task_id="run_pipeline",
        image="csv-etl-pipeline:local",
        command=["python", "-m", "src.pipeline"],
        docker_url="unix://var/run/docker.sock",
        api_version="auto",
        network_mode="csv-etl-network",
        environment={"DATABASE_URL": "{{ var.value.etl_database_url }}"},
        mounts=[
            Mount(source="{{ var.value.etl_host_project_dir }}/data", target="/app/data", type="bind"),
            Mount(source="{{ var.value.etl_host_project_dir }}/logs", target="/app/logs", type="bind"),
        ],
        mount_tmp_dir=False,
        force_pull=False,
        auto_remove="success",
        do_xcom_push=False,
    )
