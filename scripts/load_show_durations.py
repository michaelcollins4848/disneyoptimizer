"""
Loads show_durations.json into the shows table.
Same pattern as load_ride_durations.py.

Usage:
    python scripts/load_show_durations.py
"""
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.models import Show
from db.session import get_session

DURATIONS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "show_durations.json"
)


def normalize(name: str) -> str:
    return "".join(c.lower() for c in name if c.isalnum() or c.isspace()).strip()


def load():
    with open(DURATIONS_PATH) as f:
        raw = json.load(f)

    default  = raw.pop("_default", {"duration": 20, "buffer": 10})
    raw.pop("_note", None)

    lookup = {normalize(k): v for k, v in raw.items()}

    session = get_session()
    try:
        shows     = session.query(Show).all()
        matched   = 0
        unmatched = []

        for show in shows:
            norm = normalize(show.name)

            found = None
            if norm in lookup:
                found = lookup[norm]
            else:
                for curated_name, vals in lookup.items():
                    if curated_name in norm or norm in curated_name:
                        found = vals
                        break

            if found:
                show.duration_minutes = found["duration"]
                show.buffer_minutes   = found["buffer"]
                matched += 1
            else:
                show.duration_minutes = default["duration"]
                show.buffer_minutes   = default["buffer"]
                unmatched.append(show.name)

        session.commit()
        print(f"Matched {matched}/{len(shows)} shows to curated durations.")

        if unmatched:
            print(f"\n{len(unmatched)} shows used defaults — add these to show_durations.json:")
            for name in unmatched:
                print(f"  - {name}")

    except Exception as e:
        session.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    load()
