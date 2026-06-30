#seeds all the initial rides from disneyland and fetches all child entities
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from db.models import Park, Ride
from db.session import get_session

DESTINATIONS_URL = "https://api.themeparks.wiki/v1/destinations"
CHILDREN_URL     = "https://api.themeparks.wiki/v1/entity/{entity_id}/children"
DISNEYLAND_SLUG  = "disneylandresort"  # identifies the right destination


def find_disneyland_park(destinations: list) -> dict | None:
    for destination in destinations:
        if destination.get("slug") == DISNEYLAND_SLUG:
            for park in destination.get("parks", []):
                if "disneyland" in park["name"].lower() and "adventure" not in park["name"].lower():
                    return {
                        "destination": destination,
                        "park": park
                    }
    return None


def fetch_rides(park_id: str) -> list:
    resp = requests.get(CHILDREN_URL.format(entity_id=park_id), timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return data.get("children", [])


def seed():
    print("Fetching destinations from themeparks.wiki...")
    resp = requests.get(DESTINATIONS_URL, timeout=10)
    resp.raise_for_status()
    destinations = resp.json().get("destinations", [])

    result = find_disneyland_park(destinations)
    if not result:
        print("ERROR: Could not find Disneyland Resort in destinations.")
        sys.exit(1)

    destination = result["destination"]
    park_data   = result["park"]

    print(f"Found park: {park_data['name']} (ID: {park_data['id']})")

    print("Fetching rides...")
    rides = fetch_rides(park_data["id"])
    print(f"Found {len(rides)} attractions")

    session = get_session()
    try:
        park = session.get(Park, park_data["id"])
        if not park:
            park = Park(
                id=park_data["id"],
                name=park_data["name"],
                timezone=destination.get("timezone", "America/Los_Angeles"),
            )
            session.add(park)
            print(f"  Inserted park: {park.name}")
        else:
            print(f"  Park already exists: {park.name}")

        inserted = 0
        skipped  = 0
        for ride_data in rides:
            if ride_data.get("entityType") not in ("ATTRACTION",):
                continue

            ride = session.get(Ride, ride_data["id"])
            if not ride:
                ride = Ride(
                    id=ride_data["id"],
                    park_id=park_data["id"],
                    name=ride_data["name"],
                    entity_type=ride_data.get("entityType"),
                )
                session.add(ride)
                inserted += 1
            else:
                skipped += 1

        session.commit()
        print(f"\nSeeding complete: {inserted} rides inserted, {skipped} already existed.")

    except Exception as e:
        session.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed()
