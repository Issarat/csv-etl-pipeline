FROM apache/airflow:3.1.8-python3.12

RUN pip install --no-cache-dir "apache-airflow==3.1.8" apache-airflow-providers-docker \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-3.1.8/constraints-3.12.txt"
