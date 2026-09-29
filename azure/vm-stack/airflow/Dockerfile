# Airflow for the safety/recovery/maintenance DAGs (§61, §67, §93–98): late-data replay,
# Kafka/CDC health sampling, backfill + reconciliation, maintenance. Pinning apache-airflow
# alongside the providers stops pip from upgrading Airflow itself while resolving dependencies.
FROM apache/airflow:2.10.5-python3.11
RUN pip install --no-cache-dir "apache-airflow==2.10.5" "apache-airflow-providers-databricks>=6.10,<7" \
    "confluent-kafka>=2.3,<3.0"
