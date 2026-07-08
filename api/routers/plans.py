from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import date, time, datetime, timezone
from typing import Optional
import traceback

router = APIRouter()



class ShowEventRequest(BaseModel):
    show_id:str
    showtime: Optional[str] = None 


class PlanRequest(BaseModel):
    date:           str  
    arrival_time:   str    
    departure_time: Optional[str] = None 
    must_rides:     list[str] = []
    want_rides:     list[str] = []
    optional_rides: list[str] = []
    avoid_rides:    list[str] = []  
    show_events:    list[ShowEventRequest] = []
    use_cp_sat:     bool = True
    completed_rides: list[str] = [] 
    start_lat:       Optional[float] = None
    start_lng:       Optional[float] = None
    start_time:      Optional[str] = None 



@router.post("/plans")
def create_plan(req: PlanRequest):
    #generates an optimized day plan for Disneyland, itakes the user's ride priority lists and any shows they want to attend,
    #and returns an ordered itinerary with predicted wait times and walk times

    try:
        from optimizer.planner import build_plan

        target_date = date.fromisoformat(req.date)
        h, m = map(int, req.arrival_time.split(":"))
        arrival_time = time(h, m)

        departure_time = None
        if req.departure_time:
            dh, dm = map(int, req.departure_time.split(":"))
            departure_time = time(dh, dm)

        start_time = None
        if req.start_time:
            sh, sm = map(int, req.start_time.split(":"))
            start_time = time(sh, sm)

        show_events = [
            {"show_id": se.show_id, "showtime": se.showtime}
            for se in req.show_events
        ]
        result = build_plan(
            target_date  = target_date,
            arrival_time  = arrival_time,
            departure_time  = departure_time,
            must_rides  = req.must_rides,
            want_rides  = req.want_rides,
            optional_rides  = req.optional_rides,
            show_events  = show_events,
            use_cp_sat   = req.use_cp_sat,
            completed_rides = req.completed_rides,
            start_lat = req.start_lat,
            start_lng = req.start_lng,
            start_time = start_time,
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
    from db.session import get_session
    from db.models import Ride

    session = get_session()
    try:
        rides = (
            session.query(Ride)
            .filter(Ride.is_queueable == True)
            .order_by(Ride.name)
            .all()
        )
        return {
            "rides": [
                {
                    "id":  r.id,
                    "name": r.name,
                    "duration_minutes": r.duration_minutes,
                }
                for r in rides
            ]
        }
    finally:
        session.close()


@router.get("/plans/shows")
def get_plannable_shows():

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
