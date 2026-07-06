"""
One-time backfill: fetches lat/lng coordinates for every show
in the shows table. Same approach as backfill_ride_locations.py.

Usage:
    python fetcher/backfill_show_locations.py
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import requests
from db.models import Show
from db.session import get_session

ENTITY_URL = "https://api.themeparks.wiki/v1/entity/{entity_id}"


def backfill():
    session = get_session()
    try:
        shows = session.query(Show).all()
        print(f"Backfilling location data for {len(shows)} shows...\n")

        updated = 0
        skipped = 0

        for show in shows:
            try:
                resp = requests.get(
                    ENTITY_URL.format(entity_id=show.id), timeout=10
                )
                resp.raise_for_status()
                data     = resp.json()
                location = data.get("location")

                if not location:
                    print(f"  SKIP  {show.name} — no location data")
                    skipped += 1
                    continue

                show.latitude  = location.get("latitude")
                show.longitude = location.get("longitude")
                updated += 1
                print(f"  OK    {show.name} — ({show.latitude}, {show.longitude})")

            except Exception as e:
                print(f"  ERROR {show.name} — {e}")
                skipped += 1

            time.sleep(0.3)

        session.commit()
        print(f"\nDone. {updated} updated, {skipped} skipped.")

    except Exception as e:
        session.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    backfill()
