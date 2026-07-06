#loads all ride duratiosn into respective rides
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.models import Ride
from db.session import get_session

DURATIONS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "ride_durations.json"
)


def normalize(name: str) -> str:
    return "".join(c.lower() for c in name if c.isalnum() or c.isspace()).strip()


def load():
    with open(DURATIONS_PATH) as f:
        raw = json.load(f)

    default_fallback = raw.pop("_default_fallback_minutes", 5)
    raw.pop("_note", None)

    durations = {normalize(name): mins for name, mins in raw.items()}

    session = get_session()
    try:
        rides = session.query(Ride).all()
        matched   = 0
        unmatched = []

        for ride in rides:
            norm_name = normalize(ride.name)

            if norm_name in durations:
                ride.duration_minutes = durations[norm_name]
                matched += 1
                continue

            found = False
            for curated_name, mins in durations.items():
                if curated_name in norm_name or norm_name in curated_name:
                    ride.duration_minutes = mins
                    matched += 1
                    found = True
                    break

            if not found:
                ride.duration_minutes = default_fallback
                unmatched.append(ride.name)

        session.commit()

        print(f"Matched {matched}/{len(rides)} rides to curated durations.")
        print(f"{len(unmatched)} rides fell back to the default ({default_fallback} min):\n")
        for name in unmatched:
            print(f"  - {name}")

        if unmatched:
            print(
                "\nAdd these to data/ride_durations.json with their real "
                "duration, then re-run this script."
            )

    except Exception as e:
        session.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    load()
