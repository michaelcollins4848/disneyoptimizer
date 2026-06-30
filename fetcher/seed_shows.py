#seeds all the shows from disneyland and fetches all child entities

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from db.models import Park, Show
from db.session import get_session

CHILDREN_URL = "https://api.themeparks.wiki/v1/entity/{entity_id}/children"


def seed():
    session = get_session()
    try:
        park = session.query(Park).first()
        if not park:
            print("ERROR: No park found. Run fetcher/seed_rides.py first.")
            sys.exit(1)

        print(f"Fetching entertainment entities for {park.name}...")
        resp = requests.get(CHILDREN_URL.format(entity_id=park.id), timeout=10)
        resp.raise_for_status()
        children = resp.json().get("children", [])

        shows = [c for c in children if c.get("entityType") == "SHOW"]
        print(f"Found {len(shows)} shows/entertainment entities")

        inserted = 0
        skipped  = 0
        for show_data in shows:
            show = session.get(Show, show_data["id"])
            if not show:
                show = Show(
                    id=show_data["id"],
                    park_id=park.id,
                    name=show_data["name"],
                )
                session.add(show)
                inserted += 1
            else:
                skipped += 1

        session.commit()
        print(f"\nDone: {inserted} shows inserted, {skipped} already existed.")

    except Exception as e:
        session.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed()
