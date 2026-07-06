from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import date, time, datetime, timezone
from typing import Optional
import traceback

router = APIRouter()


# ── Request / Response schemas ─────────────────────────────────────────────────

class ShowEventRequest(BaseModel):
    show_id:  str
    showtime: str   # "21:00" format


class PlanRequest(BaseModel):
    date:           str              # "YYYY-MM-DD"
    arrival_time:   str              # "09:00"
    must_rides:     list[str] = []
    want_rides:     list[str] = []
    optional_rides: list[str] = []
    show_events:    list[ShowEventRequest] = []
    use_cp_sat:     bool = True


# ── Endpoint ───────────────────────────────────────────────────────────────────

@router.post("/plans")
def create_plan(req: PlanRequest):
    """
    Generates an optimized day plan for Disneyland.

    Takes the user's ride priority lists and any shows they want to attend,
    and returns an ordered itinerary with predicted wait times and walk times.
    """
    try:
        from optimizer.planner import build_plan

        target_date  = date.fromisoformat(req.date)
        h, m         = map(int, req.arrival_time.split(":"))
        arrival_time = time(h, m)

        show_events = [
            {"show_id": se.show_id, "showtime": se.showtime}
            for se in req.show_events
        ]

        result = build_plan(
            target_date    = target_date,
            arrival_time   = arrival_time,
            must_rides     = req.must_rides,
            want_rides     = req.want_rides,
            optional_rides = req.optional_rides,
            show_events    = show_events,
            use_cp_sat     = req.use_cp_sat,
        )

        return result

    except FileNotFoundError as e:
        raise HTTPException(
            status_code=503,
            detail=str(e)
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Optimizer error: {str(e)}"
        )


@router.get("/plans/rides")
def get_plannable_rides():
    """
    Returns all rides available for planning with their names and IDs.
    Used to populate the ride picker in the frontend.
    """
    from db.session import get_session
    from db.models import Ride

    session = get_session()
    try:
        rides = session.query(Ride).order_by(Ride.name).all()
        return {
            "rides": [
                {
                    "id":               r.id,
                    "name":             r.name,
                    "duration_minutes": r.duration_minutes,
                }
                for r in rides
            ]
        }
    finally:
        session.close()


@router.get("/plans/shows")
def get_plannable_shows():
    """
    Returns all shows with today's scheduled times.
    Used to populate the show picker in the frontend.
    """
    from db.session import get_session
    from db.models import Show, ShowTime
    from sqlalchemy import text

    session = get_session()
    try:
        result = session.execute(text("""
            SELECT
                s.id,
                s.name,
                s.duration_minutes,
                s.buffer_minutes,
                st.start_time
            FROM shows s
            JOIN show_times st ON st.show_id = s.id
            WHERE st.show_date = CURRENT_DATE::text
            ORDER BY s.name ASC, st.start_time ASC
        """))

        rows    = result.fetchall()
        grouped = {}

        for show_id, name, duration, buffer, start_time in rows:
            if show_id not in grouped:
                grouped[show_id] = {
                    "id":               show_id,
                    "name":             name,
                    "duration_minutes": duration,
                    "buffer_minutes":   buffer,
                    "times":            [],
                }
            grouped[show_id]["times"].append({
                "time":     start_time.strftime("%H:%M"),
                "time_iso": start_time.isoformat(),
            })

        return {"shows": list(grouped.values())}

    finally:
        session.close()
