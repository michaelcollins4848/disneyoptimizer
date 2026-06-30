
#one-time backfill: fetches lat/lng coordinates for every ride and fills in 
#done once so isn't repeated every 10 min
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import requests
from db.models import Ride
from db.session import get_session

ENTITY_URL = "https://api.themeparks.wiki/v1/entity/{entity_id}"


def backfill():
    session = get_session()
    try:
        rides = session.query(Ride).all()
        print(f"Backfilling location data for {len(rides)} rides...\n")

        updated = 0
        skipped = 0

        for ride in rides:
            try:
                resp = requests.get(ENTITY_URL.format(entity_id=ride.id), timeout=10)
                resp.raise_for_status()
                data = resp.json()

                location = data.get("location")
                if not location:
                    print(f"  SKIP  {ride.name} — no location data returned")
                    skipped += 1
                    continue

                ride.latitude  = location.get("latitude")
                ride.longitude = location.get("longitude")
                updated += 1
                print(f"  OK    {ride.name} — ({ride.latitude}, {ride.longitude})")

            except Exception as e:
                print(f"  ERROR {ride.name} — {e}")
                skipped += 1

            # themeparks.wiki has no documented rate limit, but be a
            # good citizen since we're hitting it 54 times in a row
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
