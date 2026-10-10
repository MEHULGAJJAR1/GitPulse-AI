"""Airflow DAG: orchestrates the GitPulse ELT pipeline.

extract/transform/quality run through the same CLI the in-app scheduler and the API use, so a run
started from Airflow shows up in the same run history, logs and data-quality tables.

Set GITPULSE_HOME to the repository root on the Airflow worker (default /opt/gitpulse).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

GITPULSE_HOME = os.environ.get("GITPULSE_HOME", "/opt/gitpulse")
PYTHON = os.environ.get("GITPULSE_PYTHON", f"{GITPULSE_HOME}/.venv/bin/python")

default_args = {
    "owner": "gitpulse",
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
    "execution_timeout": timedelta(hours=2),
}

with DAG(
    dag_id="gitpulse_elt",
    description="GitHub -> raw JSON -> Postgres -> dbt-style marts -> data quality",
    start_date=datetime(2026, 1, 1),
    schedule="0 */6 * * *",
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["gitpulse", "elt"],
) as dag:
    extract_and_load = BashOperator(
        task_id="extract_and_load",
        bash_command=f"cd {GITPULSE_HOME}/data_pipeline && {PYTHON} -m gitpulse_elt run --trigger airflow",
    )
    transform = BashOperator(
        task_id="transform",
        bash_command=f"cd {GITPULSE_HOME}/data_pipeline && {PYTHON} -m gitpulse_elt transform",
    )
    quality = BashOperator(
        task_id="quality",
        bash_command=f"cd {GITPULSE_HOME}/data_pipeline && {PYTHON} -m gitpulse_elt quality",
    )

    extract_and_load >> transform >> quality
