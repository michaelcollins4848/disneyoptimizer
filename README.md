# DisneyLined 🏰

**Live at [disneylined.site](https://disneylined.site)**

A full-stack Disneyland wait time optimizer. It collects live ride data every 10 minutes, predicts future wait times with a machine learning model, and uses a constraint solver to build the optimal route through your day — around the rides you care about and the shows you don't want to miss.

Deployed on AWS, collecting data 24/7.

![DisneyLined](./disneylinedimg)

---

## What It Does

### Live wait times
Polls the [themeparks.wiki](https://api.themeparks.wiki) API every 10 minutes during park hours and stores every ride's wait in PostgreSQL. The front page shows current conditions three ways: a shortest-waits strip, a ranked list with animated bars, and a card grid. Waits are color-coded (green under 20 min, amber 20–45, red above), and the page auto-refreshes with a live countdown.

### Showtimes
Pulls the day's entertainment schedule — parades, fireworks, character shows — and groups them by show with upcoming and past highlighting. Refreshes daily before park open.

### Wait time prediction
A shared XGBoost model trained on every collected snapshot predicts the wait for any ride at any time of day. Features include time of day, day of week, month, holidays, a park-wide crowd signal, per-ride rolling averages, and a target-encoded ride identity. The model is cross-validated with `TimeSeriesSplit` to prevent leakage, retrains weekly, and only replaces the production model if it beats the current one.

### Day optimizer
Mark rides as Must / Want / Avoid, pick your shows, set arrival and departure times. A Google OR-Tools CP-SAT solver then builds your itinerary:

- Guarantees must-do rides, packs in as many others as fit
- Schedules each ride at its lowest predicted wait
- Automatically chooses which *showing* of each show fits your day best
- Computes walking time between every stop
- Detects idle gaps and suggests filling them — a snack break for short gaps, a specific unridden attraction for longer ones

### Live re-planning
Days never go as planned. As you move through the park, tap rides off as you finish them. Hit **Re-plan from here** and the optimizer rebuilds the rest of your day from your actual current location and the real current time — blending *live* wait times for the next 30 minutes with model predictions beyond that. A nowcast that decays into a forecast.

---

## Architecture

```
themeparks.wiki API
        │  every 10 min (Airflow)
        ▼
   PostgreSQL ──────────────── grows continuously
        │
        ├──► Airflow: weekly model retraining
        │         │
        │         ▼
        │    XGBoost model  ──► wait time predictions
        │                             │
        ▼                             ▼
   FastAPI backend ◄──────── OR-Tools CP-SAT optimizer
        │
        ▼
   React frontend (wait times · showtimes · day planner)
```

Deployed on a single AWS Lightsail instance running Nginx as a reverse proxy, with FastAPI and Airflow managed as systemd services and HTTPS via Let's Encrypt.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Data collection | Python, Apache Airflow, themeparks.wiki API |
| Database | PostgreSQL, SQLAlchemy |
| Backend | FastAPI, Uvicorn |
| ML | XGBoost, scikit-learn, pandas |
| Optimizer | Google OR-Tools (CP-SAT) |
| Frontend | React, Vite |
| Deployment | AWS Lightsail, Nginx, systemd, Let's Encrypt |

---

## Engineering Notes

A few of the more interesting problems this project ran into and how they were solved.

### Shared model vs. per-ride models
The obvious approach is one model per ride. But with limited data per ride and new attractions appearing with no history at all, per-ride models are brittle. Instead, one shared XGBoost model trains on all rides at once, distinguishing them through a **target-encoded ride identity** (each ride's historical mean wait) and per-ride rolling averages. This lets general patterns — mornings are quieter, weekends are busier, waits rise when the whole park is crowded — transfer across rides, while each ride keeps its own baseline. A cold-start ride still gets a sensible prediction.

### The optimizer's objective function was wrong before it was right
The first CP-SAT objective minimized total wait time and gave small rewards for visiting rides. The solver did exactly what it was told: it scheduled as *few* rides as possible, since every ride added its wait to the cost while contributing only a small reward. Mathematically optimal, practically useless.

The fix was to invert the framing — reward visiting rides heavily (scaled by priority tier), and demote wait time to a tiebreaker for *ordering*. Later, a compactness penalty was added to discourage large idle gaps, but that introduced a subtler bug: late-evening rides carried such a large "starts late" penalty that the solver dropped them entirely, ending the plan right after the fireworks. Rewards had to be scaled an order of magnitude above the maximum possible penalty so that including a ride is always worthwhile if it physically fits.

**The lesson:** a constraint solver optimizes the objective you write, not the outcome you want. Most of the work is in making those the same thing.

### Debugging INFEASIBLE
At one point CP-SAT reported the model infeasible and silently fell back to the greedy planner. The cause was in the interval variable bounds: each ride's `start` and `end` were both bounded to `[arrival, close]`, but the interval also has a fixed duration, so `end = start + duration`. For any ride whose start approached closing time, no valid `(start, end)` pair could exist — a logical contradiction baked into the variable domains. Capping the latest start at `close - duration` resolved it.

Greedy never hit this because it walks forward through time placing rides rather than declaring interval constraints, which is precisely why it succeeded on inputs where CP-SAT failed.

### Not everything with a queue is a ride
The park API returns walkthroughs, exhibits, meet-and-greets, and theater shows alongside actual rides. These never report a real wait, so the model — starved of signal — regressed their predictions toward the park-wide average, confidently claiming a 23-minute wait for a shooting gallery that always has zero.

Rather than hardcoding a list of exclusions, the fix is data-driven: any attraction that has **never once** reported an operating wait time gets flagged `is_queueable = FALSE` and disappears from the picker, the planner, and the live grid. A small `ALWAYS_KEEP` list preserves genuine exceptions like the Enchanted Tiki Room, which runs on a fixed cycle and gets a hardcoded wait instead of a model prediction.

### Timezones, twice
Two separate bugs, same root cause. First, the planner localized times as UTC while the park runs on Pacific, so a 9am arrival landed at 2am. Second, the frontend sent the plan date via `toISOString()` — which returns UTC — so after 5pm Pacific it requested tomorrow's plan and silently found zero showtimes for every selected show. Both fixed by being explicit: `America/Los_Angeles` everywhere on the backend, and `toLocaleDateString('en-CA', { timeZone })` on the frontend.

---

## Model Performance

The shared XGBoost model is evaluated with 5-fold `TimeSeriesSplit`, reporting average cross-validation RMSE in minutes. Retraining runs weekly and only promotes the new model if its RMSE improves on the current production model, so a bad training run can never silently degrade predictions.

---

## Project Structure

```
DisneyLined/
├── api/                          # FastAPI backend
│   ├── main.py
│   └── routers/
│       ├── rides.py              # GET /api/rides/live
│       ├── shows.py              # GET /api/shows/today
│       └── plans.py              # POST /api/plans + picker endpoints
│
├── dags/                         # Airflow DAGs
│   ├── wait_time_ingestion.py    # every 10 min — ride waits
│   ├── showtime_refresh.py       # daily 8:01am PT — show schedule
│   └── model_retraining.py       # weekly Mon 9am PT — retrain + promote
│
├── data/                         # curated ride/show durations
├── db/                           # SQLAlchemy models + session
├── fetcher/                      # API clients, seeders, backfills
├── ml/                           # feature engineering, training, inference
├── optimizer/
│   ├── planner.py                # greedy + CP-SAT planners, gap detection
│   └── walk_time.py              # haversine walk-time estimator
├── scripts/                      # init_db, data loaders, is_queueable flagging
├── models/                       # trained models (gitignored)
│
└── frontend/
    └── src/components/
        ├── WaitTimesTab.jsx
        ├── ShowtimesTab.jsx
        ├── PlanningTab.jsx
        └── planning/
            ├── RidePicker.jsx
            ├── ShowPicker.jsx
            ├── PlanLoading.jsx
            └── PlanTimeline.jsx
```

---

## Running Locally

### Prerequisites
Python 3.12 · Node.js 18+ · PostgreSQL 15+ · WSL2 if on Windows (Airflow doesn't run natively on Windows)

### Setup

```bash
git clone https://github.com/yourusername/DisneyLined.git
cd DisneyLined
cp .env.example .env          # fill in your PostgreSQL credentials

python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

Create the database:
```bash
sudo -u postgres psql -c "CREATE DATABASE disney_optimizer;"
sudo -u postgres psql -c "CREATE USER disney_user WITH PASSWORD 'yourpassword';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE disney_optimizer TO disney_user;"
sudo -u postgres psql -d disney_optimizer -c "GRANT ALL ON SCHEMA public TO disney_user;"
python scripts/init_db.py
```

Seed reference data (one-time):
```bash
python fetcher/seed_rides.py
python fetcher/seed_shows.py
python fetcher/backfill_ride_locations.py
python fetcher/backfill_show_locations.py
python scripts/load_ride_durations.py
python scripts/load_show_durations.py
python scripts/flag_non_queueable.py
```

Start Airflow and enable the DAGs:
```bash
export AIRFLOW_HOME=~/airflow
export PYTHONPATH=$(pwd)
airflow standalone            # UI at localhost:8080

mkdir -p ~/airflow/dags
ln -s $(pwd)/dags/*.py ~/airflow/dags/
```

Once some data has accumulated, train the first model:
```bash
python ml/train.py
```

Run it:
```bash
uvicorn api.main:app --reload --port 8000     # terminal 1
cd frontend && npm install && npm run dev     # terminal 2
```

Open `http://localhost:5173`.

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/rides/live` | GET | Latest wait time snapshot for all queueable rides |
| `/api/shows/today` | GET | Today's show schedule grouped by show |
| `/api/plans/rides` | GET | Rides available for planning |
| `/api/plans/shows` | GET | Shows with today's showtimes |
| `/api/plans` | POST | Generate (or re-generate) an optimized day plan |
| `/health` | GET | API health check |

---

## Roadmap

- [x] PostgreSQL schema + Airflow data pipeline
- [x] FastAPI backend, React frontend
- [x] XGBoost wait prediction with weekly retraining and model promotion
- [x] OR-Tools CP-SAT optimizer with priority tiers and automatic showtime selection
- [x] Walk-time estimation and gap-filling suggestions
- [x] Live re-planning with blended live/predicted waits
- [x] Deployed to AWS with 24/7 data collection
- [ ] Multi-park support (Disney California Adventure)
- [ ] Walk-time-aware routing inside the solver (currently annotated post-solve)
- [ ] Mobile-first UI pass

---

## Acknowledgements

Live park data provided by [themeparks.wiki](https://themeparks.wiki), an open-source community project. Not affiliated with or endorsed by The Walt Disney Company.
