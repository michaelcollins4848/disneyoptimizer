
#DAG runs every 10 minutes while the park is open
#Tasks:
  #1. check_park_open = skip the run if park is closed
  #2. fetch_wait_times = hit themeparks.wiki and store snapshots
  #3. validate_data = sanity check the rows just inserted
  #4. alert_on_anomaly = fires only if validation flags an issue
import sys
import os

#allow Airflow can find modules
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from datetime import datetime, timezone, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.empty import EmptyOperator

default_args = {
    "owner": "michael",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "email_on_failure": False,
}

#check whether park is open or not
def check_park_open(**context) -> str:
    import requests
    from datetime import datetime
    import pytz
    from db.session import get_session
    from db.models import Park

    session = get_session()
    try:
        park = session.query(Park).first()
        if not park:
            return "skip_closed"

        url  = f"https://api.themeparks.wiki/v1/entity/{park.id}/schedule"
        resp = requests.get(url, timeout=10)
        data = resp.json()

        park_tz   = pytz.timezone("America/Los_Angeles")
        now_local = datetime.now(park_tz)
        today_str = now_local.strftime("%Y-%m-%d")

        schedule = data.get("schedule", [])
        today_entry = next(
            (s for s in schedule
             if s.get("date") == today_str and s.get("type") == "OPERATING"),
            None
        )

        if not today_entry:
            print("No operating schedule found for today — skipping.")
            return "skip_closed"

        open_time  = datetime.fromisoformat(today_entry["openingTime"]).astimezone(park_tz)
        close_time = datetime.fromisoformat(today_entry["closingTime"]).astimezone(park_tz)

        if open_time <= now_local <= close_time:
            print(f"Park is open: {open_time.strftime('%I:%M%p')} – {close_time.strftime('%I:%M%p')}")
            return "fetch_wait_times"
        else:
            print(f"Park is closed right now. Opens {open_time.strftime('%I:%M%p')}.")
            return "skip_closed"

    finally:
        session.close()

#pulls wait times and sends pushes to xcom
def do_fetch_wait_times(**context):
    from fetcher.fetch_wait_times import fetch_and_store
    count = fetch_and_store()
    context["ti"].xcom_push(key="snapshot_count", value=count)

#pulls snapshot from xcom and checks if low snapshots (send alert)
def do_validate_data(**context) -> str:
    count = context["ti"].xcom_pull(key="snapshot_count", task_ids="fetch_wait_times")
    print(f"Validating: {count} snapshots inserted.")

    if count is None or count < 5:
        print(f"WARNING: Only {count} snapshots — possible API issue.")
        return "alert_on_anomaly"

    return "validation_passed"

#sends alert if too few snapshots
def do_alert(**context):
    count = context["ti"].xcom_pull(key="snapshot_count", task_ids="fetch_wait_times")
    print(f"ALERT: Anomaly detected — only {count} snapshots inserted. Check API.")


with DAG(
    dag_id="wait_time_ingestion",
    default_args=default_args,
    schedule_interval="*/10 * * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["disney", "ingestion"],
) as dag:

    check_open = BranchPythonOperator(
        task_id="check_park_open",
        python_callable=check_park_open,
    )

    skip_closed = EmptyOperator(task_id="skip_closed")

    fetch = PythonOperator(
        task_id="fetch_wait_times",
        python_callable=do_fetch_wait_times,
    )

    validate = BranchPythonOperator(
        task_id="validate_data",
        python_callable=do_validate_data,
    )

    validation_passed = EmptyOperator(task_id="validation_passed")

    alert = PythonOperator(
        task_id="alert_on_anomaly",
        python_callable=do_alert,
    )

    check_open >> [fetch, skip_closed]
    fetch >> validate
    validate >> [validation_passed, alert]
