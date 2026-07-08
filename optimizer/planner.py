
#two planning modes:
# option 1. Greedy planner for fast, good enough for most days
# option 2. CP-SAT planner for optimal, better on complex/crowded days

#steps in planning:
#shows anchor the skeleton (fixed start times + buffer)
#rides fill free windows (must-dos first, then want, then optional)
#walk time computed via haversine between every consecutive pair
#machine learning predictions determine the best time slot for each ride
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass, field
from datetime import datetime, date, time, timedelta, timezone
from typing import Optional
from sqlalchemy import text
import pytz

PACIFIC_TZ = pytz.timezone('America/Los_Angeles')

from db.session import get_session
from db.models import Ride, Show, ShowTime
from optimizer.walk_time import walk_time_minutes
from ml.predict import predict_wait, predict_day

PARK_OPEN_HOUR = 8
PARK_CLOSE_HOUR = 24
SLOT_MINUTES = 5
DEFAULT_BUFFER = 10  

PRIORITY_REWARD = {
    'must': None, 
    'want': 10, 
    'optional': 3, 
}



@dataclass
class RideNode:
    ride_id: str
    name: str
    duration_minutes: float
    latitude: Optional[float]
    longitude: Optional[float]
    priority: str 
    predicted_waits:  dict = field(default_factory=dict) 


@dataclass
class ShowNode:
    show_id: str
    name:   str
    duration_minutes: int
    buffer_minutes:   int
    latitude:  Optional[float]
    longitude:  Optional[float]
    showtime:  datetime            
    candidate_times:  list = field(default_factory=list) 


@dataclass
class PlanItem:
    item_type:        str  
    name:             str
    arrive_at:        datetime   
    start_at:         datetime   
    end_at:           datetime 
    predicted_wait:   Optional[int] = None
    duration_minutes: Optional[int] = None
    walk_minutes:     Optional[int] = None
    ride_id:          Optional[str] = None 
    latitude:         Optional[float] = None  
    longitude:        Optional[float] = None



def load_ride(ride_id: str) -> Optional[RideNode]:
    session = get_session()
    try:
        ride = session.query(Ride).filter(Ride.id == ride_id).first()
        if not ride:
            return None
        return RideNode(
            ride_id = ride.id,
            name = ride.name,
            duration_minutes = ride.duration_minutes or 5.0,
            latitude = ride.latitude,
            longitude = ride.longitude,
            priority = 'optional',  
        )
    finally:
        session.close()


def load_show_with_all_times(show_id: str, target_date: date) -> Optional[ShowNode]:
    session = get_session()
    try:
        show = session.query(Show).filter(Show.id == show_id).first()
        if not show:
            return None

        date_str = target_date.isoformat()
        rows = session.query(ShowTime).filter(
            ShowTime.show_id == show_id,
            ShowTime.show_date == date_str,
        ).order_by(ShowTime.start_time).all()

        candidate_times = []
        for row in rows:
            dt = row.start_time
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            candidate_times.append(dt.astimezone(PACIFIC_TZ))

        if not candidate_times:
            return None

        return ShowNode(
            show_id = show.id,
            name = show.name,
            duration_minutes = show.duration_minutes or 20,
            buffer_minutes = show.buffer_minutes   or DEFAULT_BUFFER,
            latitude = show.latitude,
            longitude = show.longitude,
            showtime = candidate_times[0], 
            candidate_times  = candidate_times,
        )
    finally:
        session.close()


def load_show_for_day(show_id: str, target_date: date, showtime_str: str) -> Optional[ShowNode]:
    session = get_session()
    try:
        show = session.query(Show).filter(Show.id == show_id).first()
        if not show:
            return None

        h, m = map(int, showtime_str.split(':'))
        showtime_dt = PACIFIC_TZ.localize(datetime(
            target_date.year, target_date.month, target_date.day, h, m
        ))

        return ShowNode(
            show_id          = show.id,
            name             = show.name,
            duration_minutes = show.duration_minutes or 20,
            buffer_minutes   = show.buffer_minutes   or DEFAULT_BUFFER,
            latitude         = show.latitude,
            longitude        = show.longitude,
            showtime         = showtime_dt,
        )
    finally:
        session.close()



def park_open_dt(target_date: date) -> datetime:
    naive = datetime(target_date.year, target_date.month, target_date.day,
                     PARK_OPEN_HOUR, 0)
    return PACIFIC_TZ.localize(naive)


def park_close_dt(target_date: date, override: Optional[time] = None) -> datetime:
    if override is not None:
        if override.hour < PARK_OPEN_HOUR:
            naive = datetime(target_date.year, target_date.month, target_date.day,
                             23, 59)
        else:
            naive = datetime(target_date.year, target_date.month, target_date.day,
                             override.hour, override.minute)
        return PACIFIC_TZ.localize(naive)

    if PARK_CLOSE_HOUR >= 24:
        naive = datetime(target_date.year, target_date.month, target_date.day,
                         23, 59)
    else:
        naive = datetime(target_date.year, target_date.month, target_date.day,
                         PARK_CLOSE_HOUR, 0)
    return PACIFIC_TZ.localize(naive)


def best_predicted_wait(
    ride: RideNode,
    earliest_start: datetime,
    lookahead_hours: float = 2.0,
) -> tuple[datetime, float]:
    if not ride.predicted_waits:
        return earliest_start, 30.0

    lookahead_end = earliest_start + timedelta(hours=lookahead_hours)
    best_time  = None
    best_wait  = float('inf')
    first_time = None 

    for slot_dt_str, wait in ride.predicted_waits.items():
        slot_dt = datetime.fromisoformat(slot_dt_str)
        if slot_dt.tzinfo is None:
            slot_dt = slot_dt.replace(tzinfo=timezone.utc)

        if slot_dt >= earliest_start:
            if first_time is None or slot_dt < first_time:
                first_time = slot_dt
            if slot_dt <= lookahead_end and wait < best_wait:
                best_wait = wait
                best_time = slot_dt

    if best_time is None:
        best_time = first_time or earliest_start
        best_wait = ride.predicted_waits.get(best_time.isoformat(), 30.0)

    return best_time, best_wait



def greedy_plan(
    rides:        list[RideNode],
    shows:        list[ShowNode],
    target_date:  date,
    arrival_dt:   datetime,
    close_dt:     Optional[datetime] = None,
    current_lat:  float = 33.8121, 
    current_lng:  float = -117.9190,
) -> list[PlanItem]:
    plan: list[PlanItem] = []
    shows_sorted = sorted(shows, key=lambda s: s.showtime)
    windows = []
    cursor  = arrival_dt
    close   = close_dt or park_close_dt(target_date)

    for show in shows_sorted:
        must_arrive = show.showtime - timedelta(minutes=show.buffer_minutes)
        if must_arrive > cursor:
            windows.append(('ride', cursor, must_arrive))
        windows.append(('show', show.showtime, show, must_arrive))
        cursor = show.showtime + timedelta(minutes=show.duration_minutes)

    if cursor < close:
        windows.append(('ride', cursor, close))

    priority_order = {'must': 0, 'want': 1, 'optional': 2}
    remaining = sorted(rides, key=lambda r: priority_order[r.priority])

    for window in windows:
        if window[0] == 'show':
            _, showtime, show, arrive_by = window
            walk_mins = walk_time_minutes(
                current_lat, current_lng,
                show.latitude or current_lat,
                show.longitude or current_lng,
            )
            plan.append(PlanItem(
                item_type        = 'show',
                name             = show.name,
                arrive_at        = arrive_by - timedelta(minutes=walk_mins),
                start_at         = showtime,
                end_at           = showtime + timedelta(minutes=show.duration_minutes),
                duration_minutes = show.duration_minutes,
                walk_minutes     = int(walk_mins),
            ))
            current_lat = show.latitude or current_lat
            current_lng = show.longitude or current_lng
            continue

        _, window_start, window_end = window
        now = window_start

        while remaining and now < window_end:
            best_ride  = None
            best_start = None
            best_wait  = None
            best_cost  = float('inf')

            for ride in remaining:
                walk_mins = walk_time_minutes(
                    current_lat, current_lng,
                    ride.latitude or current_lat,
                    ride.longitude or current_lng,
                )
                earliest   = now + timedelta(minutes=walk_mins)
                start, wait = best_predicted_wait(ride, earliest)
                finish      = start + timedelta(
                    minutes=wait + ride.duration_minutes
                )

                if finish > window_end:
                    if ride.priority != 'must':
                        continue

                priority_bias = {'must': -100, 'want': 0, 'optional': 50}
                cost = walk_mins + wait + priority_bias[ride.priority]

                if cost < best_cost:
                    best_cost  = cost
                    best_ride  = ride
                    best_start = start
                    best_wait  = wait

            if best_ride is None:
                break

            walk_mins = walk_time_minutes(
                current_lat, current_lng,
                best_ride.latitude or current_lat,
                best_ride.longitude or current_lng,
            )

            plan.append(PlanItem(
                item_type        = 'ride',
                name             = best_ride.name,
                arrive_at        = now,
                start_at         = best_start,
                end_at           = best_start + timedelta(
                    minutes=int(best_wait) + best_ride.duration_minutes
                ),
                predicted_wait   = int(best_wait),
                duration_minutes = int(best_ride.duration_minutes),
                walk_minutes     = int(walk_mins),
                ride_id          = best_ride.ride_id,
                latitude         = best_ride.latitude,
                longitude        = best_ride.longitude,
            ))

            now         = plan[-1].end_at
            current_lat = best_ride.latitude or current_lat
            current_lng = best_ride.longitude or current_lng
            remaining.remove(best_ride)

    def sort_key(item: PlanItem) -> datetime:
        dt = item.start_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    return sorted(plan, key=sort_key)



def cpsat_plan(
    rides:       list[RideNode],
    shows:       list[ShowNode],
    target_date: date,
    arrival_dt:  datetime,
    close_dt:    Optional[datetime] = None,
    start_lat:   float = 33.8121,   # default: park entrance
    start_lng:   float = -117.9190,
) -> list[PlanItem]:
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        print("OR-Tools not installed. Falling back to greedy planner.")
        print("Install with: pip install ortools")
        return greedy_plan(rides, shows, target_date, arrival_dt, close_dt=close_dt)

    model  = cp_model.CpModel()
    park_open  = park_open_dt(target_date)
    park_close = close_dt or park_close_dt(target_date)

    def to_slots(dt: datetime) -> int:
        delta = dt - park_open
        return max(0, int(delta.total_seconds() / 60 / SLOT_MINUTES))

    def from_slots(s: int) -> datetime:
        return park_open + timedelta(minutes=s * SLOT_MINUTES)

    total_slots   = to_slots(park_close)
    arrival_slot  = to_slots(arrival_dt)

    print(f"[cpsat] park_open={park_open}, park_close={park_close}")
    print(f"[cpsat] total_slots={total_slots}, arrival_slot={arrival_slot}, "
          f"arrival_dt={arrival_dt}")

    show_choice_vars = [] 
    show_attended_vars = []

    for show in shows:
        times = show.candidate_times or [show.showtime]
        choices = []

        for idx, showtime in enumerate(times):
            arrive_slot = to_slots(showtime - timedelta(minutes=show.buffer_minutes))
            end_slot    = to_slots(showtime + timedelta(minutes=show.duration_minutes))

            if arrive_slot < 0 or end_slot > total_slots or arrive_slot < arrival_slot:
                continue

            present = model.NewBoolVar(f"show_{show.show_id}_{idx}")
            size    = end_slot - arrive_slot
            interval = model.NewOptionalIntervalVar(
                arrive_slot, size, end_slot, present,
                f"show_int_{show.show_id}_{idx}"
            )
            choices.append((showtime, present, interval, arrive_slot, end_slot))

        if choices:
            attended = model.NewBoolVar(f"show_attended_{show.show_id}")
            model.Add(sum(c[1] for c in choices) == attended)
            show_choice_vars.append((show, choices))
            show_attended_vars.append(attended)

    all_intervals = [c[2] for _, choices in show_choice_vars for c in choices]

    ride_vars = []

    for ride in rides:
        visited = model.NewBoolVar(f"visit_{ride.ride_id}")

        if ride.priority == 'must':
            model.Add(visited == 1)

        best_wait    = min(ride.predicted_waits.values(), default=20)
        duration_s   = max(1, int((best_wait + ride.duration_minutes) / SLOT_MINUTES))

        latest_start = total_slots - duration_s

        close_hour = get_ride_close_hour(ride.name)
        if close_hour is not None:
            close_h  = int(close_hour)
            close_m  = int(round((close_hour - close_h) * 60))
            ride_close_dt = PACIFIC_TZ.localize(datetime(
                target_date.year, target_date.month, target_date.day,
                close_h, close_m
            ))
            ride_close_slot = to_slots(ride_close_dt) - duration_s
            latest_start = min(latest_start, ride_close_slot)

        if latest_start < arrival_slot:
            if ride.priority == 'must':
                model.Add(visited == 0)
            else:
                model.Add(visited == 0)
            continue

        start   = model.NewIntVar(arrival_slot, latest_start, f"start_{ride.ride_id}")
        end     = model.NewIntVar(arrival_slot + duration_s, total_slots, f"end_{ride.ride_id}")
        interval = model.NewOptionalIntervalVar(start, duration_s, end, visited,
                                               f"interval_{ride.ride_id}")

        all_intervals.append(interval)
        ride_vars.append((ride, visited, start, end, interval))

    model.AddNoOverlap(all_intervals)


    VISIT_REWARD = {
        'must':     10000,
        'want':     5000,
        'optional': 2000,
    }
    SHOW_REWARD = 20000
    WAIT_WEIGHT = 1

    objective_terms = []

    for ride, visited, start, end, interval in ride_vars:
        avg_wait = int(sum(ride.predicted_waits.values()) / max(len(ride.predicted_waits), 1))
        objective_terms.append(VISIT_REWARD[ride.priority] * visited)
        objective_terms.append(-WAIT_WEIGHT * avg_wait * visited)

    for attended in show_attended_vars:
        objective_terms.append(SHOW_REWARD * attended)


    for ride, visited, start, end, interval in ride_vars:
        penalized_start = model.NewIntVar(0, total_slots, f"pstart_{ride.ride_id}")
        model.Add(penalized_start == start).OnlyEnforceIf(visited)
        model.Add(penalized_start == 0).OnlyEnforceIf(visited.Not())
        objective_terms.append(-penalized_start)

    model.Maximize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0

    status = solver.Solve(model)

    status_name = {
        cp_model.OPTIMAL:    "OPTIMAL",
        cp_model.FEASIBLE:   "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.MODEL_INVALID: "MODEL_INVALID",
        cp_model.UNKNOWN:    "UNKNOWN",
    }.get(status, str(status))
    print(f"[cpsat] solver status: {status_name} "
          f"({len(ride_vars)} ride vars, {len(show_choice_vars)} shows)")

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print("[cpsat] No feasible plan found — falling back to greedy.")
        return greedy_plan(rides, shows, target_date, arrival_dt, close_dt=close_dt)

    items = []

    for show, choices in show_choice_vars:
        for showtime, present, interval, arrive_slot, end_slot in choices:
            if solver.Value(present):
                items.append((PlanItem(
                    item_type        = 'show',
                    name             = show.name,
                    arrive_at        = from_slots(arrive_slot),
                    start_at         = showtime,
                    end_at           = showtime + timedelta(minutes=show.duration_minutes),
                    duration_minutes = show.duration_minutes,
                ), show.latitude, show.longitude))
                break

    for ride, visited, start, end, interval in ride_vars:
        if solver.Value(visited):
            start_dt  = from_slots(solver.Value(start))
            pred_wait = int(sum(ride.predicted_waits.values()) / max(len(ride.predicted_waits), 1))
            items.append((PlanItem(
                item_type        = 'ride',
                name             = ride.name,
                arrive_at        = start_dt,
                start_at         = start_dt,
                end_at           = start_dt + timedelta(minutes=pred_wait + ride.duration_minutes),
                predicted_wait   = pred_wait,
                duration_minutes = int(ride.duration_minutes),
                ride_id          = ride.ride_id,
                latitude         = ride.latitude,
                longitude        = ride.longitude,
            ), ride.latitude, ride.longitude))

    items.sort(key=lambda pair: pair[0].start_at)

    prev_lat, prev_lng = start_lat, start_lng
    final_items = []
    for item, lat, lng in items:
        if lat is not None and lng is not None:
            item.walk_minutes = round(walk_time_minutes(prev_lat, prev_lng, lat, lng))
            prev_lat, prev_lng = lat, lng
        final_items.append(item)

    return final_items



GAP_BREAK_THRESHOLD = 45
BREAK_SUGGESTIONS = [
    "Grab a snack or a churro nearby",
    "Good time for a sit-down meal",
    "Rest your feet and people-watch",
    "Explore the shops around you",
    "Grab a cold drink and relax",
]


def detect_gaps(
    plan_items:      list[PlanItem],
    unused_rides:    list[RideNode],
    target_date:     date,
) -> list[dict]:
    """
    Finds gaps between consecutive plan items and produces a suggestion
    for each. Short gaps → take a break. Long gaps → fill with a ride
    the user hasn't scheduled yet (drawn from their unused optional pool).
    """
    gaps = []
    sorted_items = sorted(plan_items, key=lambda i: i.start_at)
    unused_pool  = list(unused_rides)

    for i in range(len(sorted_items) - 1):
        current = sorted_items[i]
        nxt     = sorted_items[i + 1]

        gap_start = current.end_at
        gap_end   = nxt.start_at
        gap_min   = (gap_end - gap_start).total_seconds() / 60

        if gap_min < 20:
            continue

        if gap_min <= GAP_BREAK_THRESHOLD:
            suggestion = {
                'type':       'break',
                'message':    BREAK_SUGGESTIONS[i % len(BREAK_SUGGESTIONS)],
                'suggested_ride': None,
            }
        else:
            fill_ride = unused_pool.pop(0) if unused_pool else None
            if fill_ride:
                suggestion = {
                    'type':           'fill_ride',
                    'message':        f"Long break — you could fit in {fill_ride.name}",
                    'suggested_ride': fill_ride.name,
                }
            else:
                suggestion = {
                    'type':       'free_time',
                    'message':    "Free time — explore, shop, or catch a nearby show",
                    'suggested_ride': None,
                }

        gaps.append({
            'after':          current.name,
            'before':         nxt.name,
            'gap_minutes':    int(gap_min),
            'start':          gap_start.astimezone(PACIFIC_TZ).isoformat(),
            'end':            gap_end.astimezone(PACIFIC_TZ).isoformat(),
            **suggestion,
        })

    return gaps



FIXED_WAIT_OVERRIDES = {
    "tiki room": 15,
}

EARLY_CLOSE_RIDES = {
    "rise of the resistance": 21.5, 
}


def get_ride_close_hour(ride_name: str) -> Optional[float]:
    """Returns the latest hour (as float, e.g. 21.5 = 9:30pm) a ride can start."""
    lowered = ride_name.lower()
    for key, hour in EARLY_CLOSE_RIDES.items():
        if key in lowered:
            return hour
    return None


def get_fixed_wait(ride_name: str) -> Optional[int]:
    lowered = ride_name.lower()
    for key, wait in FIXED_WAIT_OVERRIDES.items():
        if key in lowered:
            return wait
    return None


def get_live_waits() -> dict:
    session = get_session()
    try:
        result = session.execute(text("""
            SELECT DISTINCT ON (ride_id)
                ride_id, wait_minutes, status, recorded_at
            FROM wait_time_snapshots
            ORDER BY ride_id, recorded_at DESC
        """))
        live = {}
        for ride_id, wait, status, _ in result.fetchall():
            if status == 'OPERATING' and wait is not None:
                live[ride_id] = wait
        return live
    finally:
        session.close()


def blend_live_waits(
    predicted_waits: dict,      # {iso_time: predicted_minutes}
    live_wait:       Optional[int],
    replan_start:    datetime,
    live_hold_minutes: int = 30,
) -> dict:

    if live_wait is None:
        return predicted_waits

    hold_until = replan_start + timedelta(minutes=live_hold_minutes)
    blended = {}

    for iso_time, pred in predicted_waits.items():
        slot_dt = datetime.fromisoformat(iso_time)
        if slot_dt.tzinfo is None:
            slot_dt = slot_dt.replace(tzinfo=timezone.utc)

        if slot_dt <= hold_until:
            blended[iso_time] = live_wait  
        else:
            blended[iso_time] = pred 
    return blended


def build_plan(
    target_date:    date,
    arrival_time:   time,
    departure_time: Optional[time] = None,
    must_rides:     list[str] = None,
    want_rides:     list[str] = None,
    optional_rides: list[str] = None,
    show_events:    list[dict] = None,
    use_cp_sat:     bool = True,
    completed_rides: list[str] = None,  
    start_lat:       Optional[float] = None,
    start_lng:       Optional[float] = None,
    start_time:      Optional[time] = None, 
) -> dict:

    must_rides      = must_rides     or []
    want_rides      = want_rides     or []
    optional_rides  = optional_rides or []
    show_events     = show_events    or []
    completed_rides = set(completed_rides or [])

    effective_start = start_time or arrival_time

    arrival_dt = PACIFIC_TZ.localize(datetime(
        target_date.year, target_date.month, target_date.day,
        effective_start.hour, effective_start.minute,
    ))


    is_replan  = start_time is not None
    live_waits = get_live_waits() if is_replan else {}
    if is_replan:
        print(f"[planner] Re-plan mode: blending {len(live_waits)} live waits")

    all_rides: list[RideNode] = []
    for ride_id, priority in (
        [(r, 'must')     for r in must_rides] +
        [(r, 'want')     for r in want_rides] +
        [(r, 'optional') for r in optional_rides]
    ):
        if ride_id in completed_rides:
            continue

        node = load_ride(ride_id)
        if node:
            node.priority = priority

            fixed = get_fixed_wait(node.name)
            if fixed is not None:

                slot_dt = park_open_dt(target_date)
                close   = park_close_dt(target_date)
                waits   = {}
                while slot_dt <= close:
                    waits[slot_dt.isoformat()] = fixed
                    slot_dt += timedelta(minutes=15)
                node.predicted_waits = waits
            else:
                preds = predict_day(ride_id, target_date)
                node.predicted_waits = {p['time']: p['predicted_wait'] for p in preds}

                if is_replan:
                    node.predicted_waits = blend_live_waits(
                        node.predicted_waits,
                        live_waits.get(ride_id),
                        arrival_dt, 
                    )

            all_rides.append(node)


    all_shows: list[ShowNode] = []
    for se in show_events:
        if se.get('showtime'):
            show = load_show_for_day(se['show_id'], target_date, se['showtime'])
        else:
            show = load_show_with_all_times(se['show_id'], target_date)
        if show:
            all_shows.append(show)
            print(f"[planner] Loaded show '{show.name}' with "
                  f"{len(show.candidate_times)} showtimes")
        else:
            print(f"[planner] WARNING: no showtimes found for show "
                  f"{se['show_id']} on {target_date}")

    print(f"[planner] {target_date}: {len(all_rides)} rides, "
          f"{len(all_shows)} shows, cp_sat={use_cp_sat}")

    close_dt = park_close_dt(target_date, override=departure_time)


    has_start = start_lat is not None and start_lng is not None

    if use_cp_sat:
        cpsat_kwargs = {'start_lat': start_lat, 'start_lng': start_lng} if has_start else {}
        plan_items = cpsat_plan(all_rides, all_shows, target_date, arrival_dt, close_dt,
                                **cpsat_kwargs)
    else:
        greedy_kwargs = {'current_lat': start_lat, 'current_lng': start_lng} if has_start else {}
        plan_items = greedy_plan(all_rides, all_shows, target_date, arrival_dt,
                                 close_dt=close_dt, **greedy_kwargs)

    total_wait  = sum(i.predicted_wait or 0 for i in plan_items if i.item_type == 'ride')
    total_rides = sum(1 for i in plan_items if i.item_type == 'ride')
    must_done   = {r for r in must_rides}
    plan_rides  = {i.name for i in plan_items if i.item_type == 'ride'}
    feasible    = all(
        any(i.name == r_name for i in plan_items)
        for r_name in [load_ride(r).name for r in must_rides if load_ride(r)]
    )

    def to_pacific_iso(dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(PACIFIC_TZ).isoformat()

    scheduled_names = {i.name for i in plan_items if i.item_type == 'ride'}
    unused_rides    = [r for r in all_rides if r.name not in scheduled_names]

    gaps = detect_gaps(plan_items, unused_rides, target_date)

    return {
        'feasible':    feasible,
        'total_wait':  total_wait,
        'total_rides': total_rides,
        'gaps':        gaps,
        'plan': [
            {
                'type':             item.item_type,
                'name':             item.name,
                'arrive_at':        to_pacific_iso(item.arrive_at),
                'start_at':         to_pacific_iso(item.start_at),
                'end_at':           to_pacific_iso(item.end_at),
                'predicted_wait':   item.predicted_wait,
                'duration_minutes': item.duration_minutes,
                'walk_minutes':     item.walk_minutes,
                'ride_id':          item.ride_id,
                'latitude':         item.latitude,
                'longitude':        item.longitude,
            }
            for item in plan_items
        ]
    }
