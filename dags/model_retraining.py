
#runs weekly and retrains the XGBoost model on all accumulated wait

import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import pendulum
from datetime import timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.empty import EmptyOperator

LOCAL_TZ = pendulum.timezone("America/Los_Angeles")

default_args = {
    "owner": "michael",
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}

MIN_ROWS_TO_TRAIN = 500   # don't retrain unless we have meaningful data


def check_data_volume(**context) -> str:
    from sqlalchemy import text
    from db.session import get_session

    session = get_session()
    try:
        result = session.execute(text("""
            SELECT COUNT(*) FROM wait_time_snapshots
            WHERE status = 'OPERATING' AND wait_minutes IS NOT NULL
        """))
        count = result.scalar()
        print(f"Found {count} usable snapshots.")

        if count < MIN_ROWS_TO_TRAIN:
            print(f"Fewer than {MIN_ROWS_TO_TRAIN} rows — skipping retrain.")
            return "skip_retrain"
        return "retrain_model"
    finally:
        session.close()


def do_retrain(**context):
    from ml.train import train
    rmse = train()
    context["ti"].xcom_push(key="rmse", value=rmse)
    print(f"Training complete. RMSE: {rmse:.2f} min")


def do_promote_or_alert(**context):
    import json

    rmse = context["ti"].xcom_pull(key="rmse", task_ids="retrain_model")
    print(f"Final RMSE from training: {rmse:.2f} min")

    # Read promotion result from the metadata file written by train.py
    meta_path = os.path.join(PROJECT_ROOT, 'models', 'production_meta.json')
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        print(f"Production model RMSE: {meta.get('avg_cv_rmse')} min")
        print(f"Trained on {meta.get('n_samples')} samples")
    else:
        print("No production meta found.")

    if rmse > 25:
        print(f"ALERT: Model RMSE is high ({rmse:.2f} min). "
              "Consider collecting more data before relying on predictions.")


with DAG(
    dag_id="model_retraining",
    default_args=default_args,
    schedule_interval="0 9 * * 1",   # 9am Pacific every Monday
    start_date=pendulum.datetime(2025, 1, 1, tz=LOCAL_TZ),
    catchup=False,
    tags=["disney", "ml"],
) as dag:

    check_volume = BranchPythonOperator(
        task_id="check_data_volume",
        python_callable=check_data_volume,
    )

    skip = EmptyOperator(task_id="skip_retrain")

    retrain = PythonOperator(
        task_id="retrain_model",
        python_callable=do_retrain,
    )

    promote = PythonOperator(
        task_id="promote_or_alert",
        python_callable=do_promote_or_alert,
    )

    check_volume >> [retrain, skip]
    retrain >> promote
