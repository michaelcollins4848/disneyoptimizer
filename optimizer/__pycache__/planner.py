"""
DisneyLine Day Optimizer

Two planning modes:
  1. Greedy planner  — fast, good enough for most days
  2. CP-SAT planner  — optimal, better on complex/crowded days

Shows are treated as fixed-time anchors. The plan is built around
them — rides fill the gaps between show commitments.

Architecture:
  - Shows anchor the skeleton (fixed start times + buffer)
  - Rides fill free windows (must-dos first, then want, then optional)
  - Walk time computed via haversine between every consecutive pair
  - ML predictions determine the best time slot for each ride

Usage:
    from optimizer.planner import build_plan

    plan = build_plan(
        date          = date(2026, 7, 5),
        arrival_time  = time(9, 0),
        must_rides    = ['ride_id_1', 'ride_id_2'],
        want_rides    = ['ride_id_3'],
        optional_rides= ['ride_id_4'],
        show_events   = [{'show_id': 'show_id_1', 'showtime': '21:00'}],
        use_cp_sat    = True,
    )
"""
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

# ── Constants ──────────────────────────────────────────────────────────────────
PARK_OPEN_HOUR  = 8
PARK_CLOSE_HOUR = 22
SLOT_MINUTES    = 5     # time discretization for CP-SAT
DEFAULT_BUFFER  = 10    # minutes to arrive before a show

PRIORITY_REWARD = {
    'must':     None,   # hard constraint
    'want':     10,     # high reward
    'optional': 3,      # low reward
}


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class RideNode:
    ride_id:          str
    name:             str
    duration_minutes: float
    latitude:         Optional[float]
    longitude:        Optional[float]
    priority:         str            # 'must' | 'want' | 'optional'
    predicted_waits:  dict = field(default_factory=dict)  # slot_index → minutes


@dataclass
class ShowNode:
    show_id:          str
    name:             str
    duration_minutes: int
    buffer_minutes:   int
    latitude:         Optional[float]
    longitude:        Optional[float]
    showtime:         datetime       # exact scheduled start


@dataclass
class PlanItem:
    item_type:        str            # 'ride' | 'show' | 'walk'
    name:             str
    arrive_at:        datetime       # when to head to this item
    start_at:         datetime       # actual start (show start or queue join)
    end_at:           datetime       # when free to move on
    predicted_wait:   Optional[int] = None
    duration_minutes: Optional[int] = None
    walk_minutes:     Optional[int] = None


# ── DB loaders ─────────────────────────────────────────────────────────────────

def load_ride(ride_id: str) -> Optional[RideNode]:
    session = get_session()
    try:
        ride = session.query(Ride).filter(Ride.id == ride_id).first()
        if not ride:
            return None
        return RideNode(
            ride_id          = ride.id,
            name             = ride.name,
            duration_minutes = ride.duration_minutes or 5.0,
            latitude         = ride.latitude,
            longitude        = ride.longitude,
            priority         = 'optional',   # overwritten by caller
        )
    finally:
        session.close()


def load_show_for_day(show_id: str, target_date: date, showtime_str: str) -> Optional[ShowNode]:
    """
    Loads a show and matches it to the specified showtime string ('21:00').
    """
    session = get_session()
    try:
        show = session.query(Show).filter(Show.id == show_id).first()
        if not show:
            return None

        # Parse showtime as Pacific time
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


# ── Time helpers ───────────────────────────────────────────────────────────────

def park_open_dt(target_date: date) -> datetime:
    naive = datetime(target_date.year, target_date.month, target_date.day,
                     PARK_OPEN_HOUR, 0)
    return PACIFIC_TZ.localize(naive)


def park_close_dt(target_date: date) -> datetime:
    naive = datetime(target_date.year, target_date.month, target_date.day,
                     PARK_CLOSE_HOUR, 0)
    return PACIFIC_TZ.localize(naive)


def best_predicted_wait(
    ride: RideNode,
    earliest_start: datetime,
    lookahead_hours: float = 2.0,
) -> tuple[datetime, float]:
    """
    Find the lowest predicted wait within a 2-hour lookahead window.

    Limiting to a window is critical for the greedy planner — without
    it the planner jumps ahead hours to find an 'ideal' slot, skipping
    the entire morning and leaving no room for other rides. If nothing
    is found in the window, falls back to the first available slot.
    """
    if not ride.predicted_waits:
        return earliest_start, 30.0

    lookahead_end = earliest_start + timedelta(hours=lookahead_hours)
    best_time  = None
    best_wait  = float('inf')
    first_time = None   # fallback: the very first available slot

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


# ── Greedy planner ─────────────────────────────────────────────────────────────

def greedy_plan(
    rides:        list[RideNode],
    shows:        list[ShowNode],
    target_date:  date,
    arrival_dt:   datetime,
    current_lat:  float = 33.8121,   # Disneyland main entrance approx
    current_lng:  float = -117.9190,
) -> list[PlanItem]:
    """
    Greedy planner: fixes shows as anchors, then fills time gaps
    with rides prioritized by must > want > optional.

    Each step picks the ride with the lowest (walk + predicted_wait)
    that fits within the current free window.
    """
    plan: list[PlanItem] = []

    # Sort shows by start time
    shows_sorted = sorted(shows, key=lambda s: s.showtime)

    # Build time windows: [(window_start, window_end), ...]
    # Shows carve out fixed blocks; rides fill the gaps.
    windows = []
    cursor  = arrival_dt
    close   = park_close_dt(target_date)

    for show in shows_sorted:
        must_arrive = show.showtime - timedelta(minutes=show.buffer_minutes)
        if must_arrive > cursor:
            windows.append(('ride', cursor, must_arrive))
        windows.append(('show', show.showtime, show, must_arrive))
        cursor = show.showtime + timedelta(minutes=show.duration_minutes)

    if cursor < close:
        windows.append(('ride', cursor, close))

    # Pool of unvisited rides sorted by priority
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

        # Ride window
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

                # Skip if ride won't finish before window ends
                if finish > window_end:
                    # Still do it if it's a must-do
                    if ride.priority != 'must':
                        continue

                # Lower priority cost (must-dos get preferred first)
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
            ))

            now         = plan[-1].end_at
            current_lat = best_ride.latitude or current_lat
            current_lng = best_ride.longitude or current_lng
            remaining.remove(best_ride)

    # Sort chronologically so shows appear in their correct time position,
    # not at the end where they were appended during window processing.
    def sort_key(item: PlanItem) -> datetime:
        dt = item.start_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    return sorted(plan, key=sort_key)


# ── CP-SAT planner ─────────────────────────────────────────────────────────────

def cpsat_plan(
    rides:       list[RideNode],
    shows:       list[ShowNode],
    target_date: date,
    arrival_dt:  datetime,
) -> list[PlanItem]:
    """
    OR-Tools CP-SAT planner. Produces globally optimal ordering
    within a 10-second solver budget.

    Falls back to greedy if OR-Tools is not installed or times out.
    """
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        print("OR-Tools not installed. Falling back to greedy planner.")
        print("Install with: pip install ortools")
        return greedy_plan(rides, shows, target_date, arrival_dt)

    model  = cp_model.CpModel()
    park_open  = park_open_dt(target_date)
    park_close = park_close_dt(target_date)

    # Convert everything to integer slots (5-minute resolution)
    def to_slots(dt: datetime) -> int:
        delta = dt - park_open
        return max(0, int(delta.total_seconds() / 60 / SLOT_MINUTES))

    def from_slots(s: int) -> datetime:
        return park_open + timedelta(minutes=s * SLOT_MINUTES)

    total_slots   = to_slots(park_close)
    arrival_slot  = to_slots(arrival_dt)

    # ── Show intervals (fixed) ─────────────────────────────────────────
    show_intervals = []
    for show in shows:
        arrive_slot  = to_slots(show.showtime - timedelta(minutes=show.buffer_minutes))
        end_slot     = to_slots(show.showtime + timedelta(minutes=show.duration_minutes))
        size         = end_slot - arrive_slot
        interval     = model.NewFixedSizeIntervalVar(arrive_slot, size, f"show_{show.show_id}")
        show_intervals.append((show, interval, arrive_slot, end_slot))

    # ── Ride variables ─────────────────────────────────────────────────
    ride_vars      = []
    all_intervals  = [iv for _, iv, _, _ in show_intervals]

    for ride in rides:
        visited = model.NewBoolVar(f"visit_{ride.ride_id}")

        if ride.priority == 'must':
            model.Add(visited == 1)

        # Duration in slots (wait + ride time)
        best_wait    = min(ride.predicted_waits.values(), default=20)
        duration_s   = max(1, int((best_wait + ride.duration_minutes) / SLOT_MINUTES))

        start   = model.NewIntVar(arrival_slot, total_slots, f"start_{ride.ride_id}")
        end     = model.NewIntVar(arrival_slot, total_slots, f"end_{ride.ride_id}")
        interval = model.NewOptionalIntervalVar(start, duration_s, end, visited,
                                               f"interval_{ride.ride_id}")

        all_intervals.append(interval)
        ride_vars.append((ride, visited, start, end, interval))

    # ── No-overlap constraint ──────────────────────────────────────────
    model.AddNoOverlap(all_intervals)

    # ── Objective ─────────────────────────────────────────────────────
    # Minimize total wait time for must/want rides
    # Maximize reward for optional rides visited
    wait_cost    = []
    reward_terms = []

    for ride, visited, start, end, interval in ride_vars:
        # Approximate wait cost as average predicted wait
        avg_wait = int(sum(ride.predicted_waits.values()) / max(len(ride.predicted_waits), 1))
        wait_cost.append(avg_wait * visited)

        if ride.priority in ('want', 'optional'):
            reward_terms.append(PRIORITY_REWARD[ride.priority] * visited)

    model.Minimize(sum(wait_cost) - sum(reward_terms))

    # ── Solve ──────────────────────────────────────────────────────────
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 10.0

    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print("CP-SAT could not find a feasible plan. Falling back to greedy.")
        return greedy_plan(rides, shows, target_date, arrival_dt)

    # ── Extract and sort the plan ──────────────────────────────────────
    items = []

    for show, interval, arrive_slot, end_slot in show_intervals:
        items.append(PlanItem(
            item_type        = 'show',
            name             = show.name,
            arrive_at        = from_slots(arrive_slot),
            start_at         = show.showtime,
            end_at           = show.showtime + timedelta(minutes=show.duration_minutes),
            duration_minutes = show.duration_minutes,
        ))

    for ride, visited, start, end, interval in ride_vars:
        if solver.Value(visited):
            start_dt  = from_slots(solver.Value(start))
            pred_wait = int(sum(ride.predicted_waits.values()) / max(len(ride.predicted_waits), 1))
            items.append(PlanItem(
                item_type        = 'ride',
                name             = ride.name,
                arrive_at        = start_dt,
                start_at         = start_dt,
                end_at           = start_dt + timedelta(minutes=pred_wait + ride.duration_minutes),
                predicted_wait   = pred_wait,
                duration_minutes = int(ride.duration_minutes),
            ))

    return sorted(items, key=lambda x: x.start_at)


# ── Public interface ───────────────────────────────────────────────────────────

def build_plan(
    target_date:    date,
    arrival_time:   time,
    must_rides:     list[str] = None,
    want_rides:     list[str] = None,
    optional_rides: list[str] = None,
    show_events:    list[dict] = None,
    use_cp_sat:     bool = True,
) -> dict:
    """
    Main entry point for the optimizer.

    show_events format:
        [{'show_id': '...', 'showtime': '21:00'}, ...]

    Returns a dict with 'plan', 'feasible', 'total_wait', 'total_rides'.
    """
    must_rides     = must_rides     or []
    want_rides     = want_rides     or []
    optional_rides = optional_rides or []
    show_events    = show_events    or []

    # Localize arrival to Pacific — the user means 9am Disneyland time,
    # not 9am UTC (which would be 2am in Anaheim).
    arrival_dt = PACIFIC_TZ.localize(datetime(
        target_date.year, target_date.month, target_date.day,
        arrival_time.hour, arrival_time.minute,
    ))

    # Load and tag rides
    all_rides: list[RideNode] = []
    for ride_id, priority in (
        [(r, 'must')     for r in must_rides] +
        [(r, 'want')     for r in want_rides] +
        [(r, 'optional') for r in optional_rides]
    ):
        node = load_ride(ride_id)
        if node:
            node.priority = priority
            # Precompute ML predictions for the full day
            preds = predict_day(ride_id, target_date)
            node.predicted_waits = {p['time']: p['predicted_wait'] for p in preds}
            all_rides.append(node)

    # Load shows
    all_shows: list[ShowNode] = []
    for se in show_events:
        show = load_show_for_day(se['show_id'], target_date, se['showtime'])
        if show:
            all_shows.append(show)

    # Run planner
    if use_cp_sat:
        plan_items = cpsat_plan(all_rides, all_shows, target_date, arrival_dt)
    else:
        plan_items = greedy_plan(all_rides, all_shows, target_date, arrival_dt)

    # Format output
    total_wait  = sum(i.predicted_wait or 0 for i in plan_items if i.item_type == 'ride')
    total_rides = sum(1 for i in plan_items if i.item_type == 'ride')
    must_done   = {r for r in must_rides}
    plan_rides  = {i.name for i in plan_items if i.item_type == 'ride'}
    feasible    = all(
        any(i.name == r_name for i in plan_items)
        for r_name in [load_ride(r).name for r in must_rides if load_ride(r)]
    )

    def to_pacific_iso(dt: datetime) -> str:
        """Convert any timezone-aware datetime to Pacific for consistent output."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(PACIFIC_TZ).isoformat()

    return {
        'feasible':    feasible,
        'total_wait':  total_wait,
        'total_rides': total_rides,
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
            }
            for item in plan_items
        ]
    }
