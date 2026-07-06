#DAG runs once a day at midnight to collect showtimes instead of 10 min cycles
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import pendulum
from datetime import timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator

LOCAL_TZ = pendulum.timezone("America/Los_Angeles")

default_args = {
    "owner": "michael",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def do_fetch_showtimes(**context):
    from fetcher.fetch_showtimes import fetch_and_store
    count = fetch_and_store()
    print(f"Inserted {count} showtimes.")


with DAG(
    dag_id="showtime_refresh",
    default_args=default_args,
    schedule_interval="15 1 * * *",
    start_date=pendulum.datetime(2025, 1, 1, tz=LOCAL_TZ),
    catchup=False,
    tags=["disney", "shows"],
) as dag:

    fetch_showtimes = PythonOperator(                                                               
        task_id="fetch_showtimes",
        python_callable=do_fetch_showtimes,
    )
