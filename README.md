# DisneyLine 🏰

A full-stack Disneyland wait time optimizer that collects live ride data, predicts wait times with machine learning, and builds an optimal day plan around the rides and shows you care about.

Built as a real product, not a toy — production-grade data pipeline, a growing time-series database, an XGBoost prediction model with automated retraining, and a constraint-solver optimizer that plans your day down to the walking route between rides.

![Wait Times Tab](https://placehold.co/900x500/080D1A/9B7FE8?text=DisneyLine+Screenshot)

---

## What It Does

**Live wait times**
- Polls the [themeparks.wiki](https://api.themeparks.wiki) API every 10 minutes during park hours and stores every ride's wait time in PostgreSQL
- Displays live conditions three ways: a shortest-waits strip, a full ranked list with animated bars, and a card grid with ride durations
- Color-codes waits — green under 20 min, amber 20–45, red above 45
- Auto-refreshes every 10 minutes with a live countdown

**Showtimes**
- Pulls the day's entertainment schedule (parades, fireworks, character shows) and displays them grouped by show with upcoming/past highlighting
- Refreshes daily before park open

**Wait time prediction (ML)**
- Shared XGBoost model trained on all collected snapshots predicts wait times for any ride at any time of day
- Features include time of day, day of week, month, holidays, park-wide crowd signal, and per-ride rolling averages
- Cross-validated with TimeSeriesSplit to prevent data leakage; retrains weekly and only promotes a new model if it beats the current one

**Day optimizer**
- Pick rides as Must / Want / Avoid, choose shows, set your arrival time
- A Google OR-Tools CP-SAT solver builds the optimal itinerary: guarantees must-do rides, packs in as many others as possible, and schedules each ride at its lowest-wait window
- Chooses the best showing time for each selected show automatically
- Computes walking time between stops via a haversine estimate
- Detects gaps and suggests filling them — a snack break for short gaps, a specific unridden attraction for longer ones

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
| Orchestration | Apache Airflow (3 DAGs) |

---

## Project Structure

```
DisneyLine/
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
├── data/
│   ├── ride_durations.json       # curated ride lengths
│   └── show_durations.json       # curated show lengths + arrival buffers
│
├── db/
│   ├── models.py                 # Park, Ride, WaitTimeSnapshot, Show, ShowTime
│   └── session.py
│
├── fetcher/
│   ├── fetch_wait_times.py
│   ├── fetch_showtimes.py
│   ├── seed_rides.py             # one-time ride discovery
│   ├── seed_shows.py             # one-time show discovery
│   ├── backfill_ride_locations.py
│   └── backfill_show_locations.py
│
├── ml/
│   ├── features.py               # feature engineering
│   ├── train.py                  # training + cross-val + promotion
│   └── predict.py                # inference (single + full-day)
│
├── optimizer/
│   ├── planner.py                # greedy + CP-SAT planners
│   └── walk_time.py              # haversine walk-time estimator
│
├── scripts/
│   ├── init_db.py
│   ├── load_ride_durations.py
│   └── load_show_durations.py
│
├── models/                       # trained models (gitignored)
│   └── .gitkeep
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── App.css
│   │   └── components/
│   │       ├── StarField.jsx
│   │       ├── WaitTimesTab.jsx
│   │       ├── QuickLook.jsx
│   │       ├── SortedList.jsx
│   │       ├── RideCard.jsx
│   │       ├── ShowtimesTab.jsx
│   │       ├── PlanningTab.jsx
│   │       └── planning/
│   │           ├── RidePicker.jsx
│   │           ├── ShowPicker.jsx
│   │           ├── PlanLoading.jsx
│   │           └── PlanTimeline.jsx
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
│
├── .env.example
├── requirements.txt
└── README.md
```

---

## Local Setup

### Prerequisites
- Python 3.12
- Node.js 18+
- PostgreSQL 15+
- WSL2 (if on Windows — Airflow doesn't run natively on Windows)

### 1. Clone and configure

```bash
git clone https://github.com/yourusername/DisneyLine.git
cd DisneyLine
cp .env.example .env      # fill in your PostgreSQL credentials
```

### 2. Python environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Database

```bash
sudo -u postgres psql -c "CREATE DATABASE disney_optimizer;"
sudo -u postgres psql -c "CREATE USER disney_user WITH PASSWORD 'yourpassword';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE disney_optimizer TO disney_user;"
sudo -u postgres psql -d disney_optimizer -c "GRANT ALL ON SCHEMA public TO disney_user;"

python scripts/init_db.py
```

### 4. Seed reference data (one-time)

```bash
python fetcher/seed_rides.py
python fetcher/seed_shows.py
python fetcher/backfill_ride_locations.py
python fetcher/backfill_show_locations.py
python scripts/load_ride_durations.py
python scripts/load_show_durations.py
```

### 5. Frontend

```bash
cd frontend && npm install && cd ..
```

### 6. Airflow

```bash
export AIRFLOW_HOME=~/airflow
export PYTHONPATH=/path/to/DisneyLine
airflow standalone       # UI at http://localhost:8080

mkdir -p ~/airflow/dags
ln -s $(pwd)/dags/wait_time_ingestion.py ~/airflow/dags/wait_time_ingestion.py
ln -s $(pwd)/dags/showtime_refresh.py    ~/airflow/dags/showtime_refresh.py
ln -s $(pwd)/dags/model_retraining.py    ~/airflow/dags/model_retraining.py
```

Enable all three DAGs in the UI. `wait_time_ingestion` begins collecting immediately during park hours.

### 7. Train the first model

Once you've collected some data (even a few days works to validate the pipeline):

```bash
python ml/train.py
```

### 8. Run

```bash
# Terminal 1
uvicorn api.main:app --reload --port 8000

# Terminal 2
cd frontend && npm run dev
```

Open `http://localhost:5173`.

---

## How the Optimizer Works

The planner runs in two possible modes:

**Greedy** — walks forward through the day, at each step picking the ride with the lowest predicted wait reachable within a 2-hour window. Fast (<1 sec) and produces solid plans.

**CP-SAT** (default) — Google OR-Tools constraint solver that searches globally. Must-do rides are hard constraints; want/optional rides carry decreasing rewards. The solver maximizes rides visited while using predicted wait as a tiebreaker, and picks the best showtime for each selected show. Runs in a few seconds and typically produces tighter, lower-wait plans than greedy.

Walking time between consecutive stops is estimated with a haversine distance and a path-indirection multiplier, then surfaced in the plan so arrival times account for the walk. Gaps in the day are detected and annotated with suggestions.

---

## Model Performance

The shared XGBoost model is evaluated with 5-fold `TimeSeriesSplit`. Reported metric is average cross-validation RMSE in minutes — lower is better. The model retrains weekly and only replaces the production model if the new RMSE improves on the current one, so a bad training run can never silently degrade predictions.

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/rides/live` | GET | Latest wait time snapshot for all rides |
| `/api/shows/today` | GET | Today's show schedule grouped by show |
| `/api/plans/rides` | GET | All rides available for planning |
| `/api/plans/shows` | GET | All shows with today's showtimes |
| `/api/plans` | POST | Generate an optimized day plan |
| `/health` | GET | API health check |

---

## Roadmap

- [x] PostgreSQL schema + data pipeline
- [x] Airflow orchestration (ingestion, showtimes, retraining)
- [x] FastAPI backend
- [x] React frontend — wait times, showtimes
- [x] Ride + show duration and location data
- [x] XGBoost wait time prediction model with weekly retraining
- [x] OR-Tools CP-SAT optimizer with priority tiers and show scheduling
- [x] Day planner UI with walk times and gap suggestions
- [ ] Live re-planning during the visit as actual waits change
- [ ] Cloud deployment for 24/7 collection
- [ ] Multi-park support (California Adventure)

---

## Acknowledgements

Live park data provided by [themeparks.wiki](https://themeparks.wiki), an open-source community project.
