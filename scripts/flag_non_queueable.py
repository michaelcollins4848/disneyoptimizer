import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from db.session import get_session

ALWAYS_KEEP = [
    "tiki room",
]


def flag():
    session = get_session()
    try:
        result = session.execute(text("""
            SELECT r.id, r.name
            FROM rides r
            LEFT JOIN wait_time_snapshots w ON w.ride_id = r.id
            GROUP BY r.id, r.name
            HAVING COUNT(*) FILTER (
                WHERE w.status = 'OPERATING' AND w.wait_minutes IS NOT NULL
            ) = 0
        """))

        candidates = result.fetchall()

        flagged   = []
        preserved = []

        for ride_id, name in candidates:
            if any(keep in name.lower() for keep in ALWAYS_KEEP):
                preserved.append(name)
                continue
            session.execute(
                text("UPDATE rides SET is_queueable = FALSE WHERE id = :id"),
                {"id": ride_id}
            )
            flagged.append(name)

        session.commit()

        print(f"Flagged {len(flagged)} attractions as non-queueable:")
        for name in sorted(flagged):
            print(f"  - {name}")

        if preserved:
            print(f"\nPreserved (in ALWAYS_KEEP) despite no wait data:")
            for name in sorted(preserved):
                print(f"  - {name}")

    except Exception as e:
        session.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    flag()
