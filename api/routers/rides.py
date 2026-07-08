from fastapi import APIRouter
from sqlalchemy import text
from db.session import get_session

router = APIRouter()


@router.get("/rides/live")
def get_live_wait_times():

    session = get_session()
    try:
        result = session.execute(text("""
            WITH latest AS (
                SELECT DISTINCT ON (ride_id)
                    ride_id,
                    wait_minutes,
                    status,
                    recorded_at
                FROM wait_time_snapshots
                ORDER BY ride_id, recorded_at DESC
            )
            SELECT
                r.id,
                r.name,
                r.duration_minutes,
                l.wait_minutes,
                l.status,
                l.recorded_at
            FROM rides r
            LEFT JOIN latest l ON l.ride_id = r.id
            WHERE r.is_queueable = TRUE
            ORDER BY l.wait_minutes ASC NULLS LAST, r.name ASC
        """))

        rows = result.fetchall()

        rides = [
            {
                "id":               row[0],
                "name":             row[1],
                "duration_minutes": row[2],
                "wait_minutes":     row[3],
                "status":           row[4],
                "recorded_at":      row[5].isoformat() if row[5] else None,
            }
            for row in rows
        ]

        last_updated = max(
            (r["recorded_at"] for r in rides if r["recorded_at"]),
            default=None,
        )

        return {"rides": rides, "last_updated": last_updated}

    finally:
        session.close()
