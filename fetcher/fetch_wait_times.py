#fetches current wait times from themeparks.wiki and inserts a snapshot row for every operating ride
#called by the Airflow DAG every 10 minutes

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import holidays
from datetime import datetime, timezone

from db.models import Ride, WaitTimeSnapshot
from db.session import get_session

LIVE_URL = "https://api.themeparks.wiki/v1/entity/{entity_id}/live"
US_HOLIDAYS = holidays.US()


def get_park_id(session) -> str | None:
    from db.models import Park
    park = session.query(Park).first()
    return park.id if park else None


def build_snapshot(ride_id: str, live_entry: dict, now: datetime) -> WaitTimeSnapshot:
    standby = live_entry.get("queue", {}).get("STANDBY", {})
    wait_mins = standby.get("waitTime")   # None if ride is closed/down
    status = live_entry.get("status", "UNKNOWN")

    return WaitTimeSnapshot(
        ride_id = ride_id,
        wait_minutes = wait_mins,
        status = status,
        recorded_at = now,
        hour_of_day = now.hour,
        day_of_week = now.weekday(),      # 0=Mon, 6=Sun
        month = now.month,
        is_weekend = now.weekday() >= 5,
        is_holiday = now.date() in US_HOLIDAYS,
    )


def fetch_and_store():
    session = get_session()
    try:
        park_id = get_park_id(session)
        if not park_id:
            raise RuntimeError(
                "No park found in DB. Did you run fetcher/seed_rides.py first?"
            )

        url  = LIVE_URL.format(entity_id=park_id)
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        live_data = resp.json().get("liveData", [])

        known_ride_ids = {r.id for r in session.query(Ride).all()}

        now = datetime.now(timezone.utc)
        snapshots = []

        for entry in live_data:
            ride_id = entry.get("id")

            if ride_id not in known_ride_ids:
                continue

            if "queue" not in entry:
                continue

            snapshot = build_snapshot(ride_id, entry, now)
            snapshots.append(snapshot)

        if snapshots:
            session.bulk_save_objects(snapshots)
            session.commit()

        print(f"[{now.isoformat()}] Inserted {len(snapshots)} snapshots.")
        return len(snapshots)

    except Exception as e:
        session.rollback()
        print(f"ERROR in fetch_and_store: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    fetch_and_store()
