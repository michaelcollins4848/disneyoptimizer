from fastapi import APIRouter
from sqlalchemy import text
from db.session import get_session

router = APIRouter()


@router.get("/shows/today")
def get_todays_showtimes():

    session = get_session()
    try:
        result = session.execute(text("""
            SELECT
                s.id,
                s.name,
                st.start_time
            FROM shows s
            JOIN show_times st ON st.show_id = s.id
            WHERE st.show_date = CURRENT_DATE::text
            ORDER BY s.name ASC, st.start_time ASC
        """))

        rows = result.fetchall()

        grouped = {}
        for show_id, name, start_time in rows:
            if name not in grouped:
                grouped[name] = {"id": show_id, "name": name, "times": []}
            grouped[name]["times"].append(start_time.isoformat())

        shows = sorted(
            grouped.values(),
            key=lambda s: s["times"][0] if s["times"] else ""
        )

        return {"shows": shows}

    finally:
        session.close()
