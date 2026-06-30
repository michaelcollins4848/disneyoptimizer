#fetches scheduled showtimes for every show in the shows table and stores them in show_times
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from datetime import datetime, timezone
from db.models import Park, Show, ShowTime
from db.session import get_session

LIVE_URL = "https://api.themeparks.wiki/v1/entity/{entity_id}/live"


def fetch_and_store():
    session = get_session()
    try:
        park = session.query(Park).first()
        if not park:
            raise RuntimeError("No park in DB. Run fetcher/seed_rides.py first.")

        known_show_ids = {s.id for s in session.query(Show).all()}
        if not known_show_ids:
            raise RuntimeError("No shows in DB. Run fetcher/seed_shows.py first.")

        print(f"Fetching live data for {park.name}...")
        resp = requests.get(LIVE_URL.format(entity_id=park.id), timeout=10)
        resp.raise_for_status()
        live_data = resp.json().get("liveData", [])

        now = datetime.now(timezone.utc)
        inserted = 0
        dates_touched = set()

        for entry in live_data:
            show_id = entry.get("id")
            if show_id not in known_show_ids:
                continue

            showtimes = entry.get("showtimes", [])
            for st in showtimes:
                start_raw = st.get("startTime")
                if not start_raw:
                    continue

                start_dt  = datetime.fromisoformat(start_raw)
                show_date = start_dt.strftime("%Y-%m-%d")
                dates_touched.add((show_id, show_date))

        for show_id, show_date in dates_touched:
            session.query(ShowTime).filter(
                ShowTime.show_id == show_id,
                ShowTime.show_date == show_date,
            ).delete()

        for entry in live_data:
            show_id = entry.get("id")
            if show_id not in known_show_ids:
                continue

            for st in entry.get("showtimes", []):
                start_raw = st.get("startTime")
                if not start_raw:
                    continue

                start_dt  = datetime.fromisoformat(start_raw)
                show_date = start_dt.strftime("%Y-%m-%d")

                session.add(ShowTime(
                    show_id=show_id,
                    show_date=show_date,
                    start_time=start_dt,
                    fetched_at=now,
                ))
                inserted += 1

        session.commit()
        print(f"Done. {inserted} showtimes stored across {len(dates_touched)} show-date pairs.")
        return inserted

    except Exception as e:
        session.rollback()
        print(f"ERROR in fetch_showtimes: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    fetch_and_store()
