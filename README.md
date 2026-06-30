# DisneyLine 🏰

A full-stack Disneyland wait time optimizer that collects live ride data, displays current park conditions, and (coming soon) uses machine learning to predict wait times and build optimal day plans.

Built as a real product with a production-grade data pipeline, a growing time-series database, and a planning algorithm that accounts for ride duration and walking time between attractions.

![Wait Times Tab](https://placehold.co/900x500/080D1A/9B7FE8?text=DisneyLine+Screenshot)

---

## What It Does

**Right now:**
- Polls the [themeparks.wiki](https://api.themeparks.wiki) API every 10 minutes during park hours and stores every ride's wait time in PostgreSQL
- Displays live wait times across three views: shortest waits strip, full ranked list with animated bars, and a card grid with ride durations
- Shows today's entertainment schedule (parades, character shows, fireworks) grouped by show with upcoming/past time highlighting
- Color-codes everything — green under 20 min, amber 20–45, red above 45
- Auto-refreshes every 10 minutes with a live countdown in the header

**Coming once enough data is collected:**
- XGBoost model trained on months of historical snapshots to predict wait times by time of day, day of week, weather, and crowd level
- OR-Tools CP-SAT optimizer that takes a user's priority ride list (must-do / really want / if time allows) and outputs an optimal ordered itinerary
- Live re-planning mid-visit as actual waits deviate from predictions
- Feasibility detection — warns you if your must-do list can't fit in one day

---

## Architecture

```
themeparks.wiki API
        ↓  (every 10 min, Airflow)
  PostgreSQL DB          ←── grows daily
        ↓
  FastAPI backend        ←── serves rides, wait times, showtimes
        ↓
  React frontend         ←── live wait times + showtimes display
```

Future state adds two layers between the DB and the API:

```
  PostgreSQL DB
        ↓
  Airflow (weekly retrain)
        ↓
  XGBoost model  →  wait time forecasts
        ↓
  OR-Tools CP-SAT  →  optimal day itinerary
        ↓
  FastAPI  →  React
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Data collection | Python, Apache Airflow, themeparks.wiki API |
| Database | PostgreSQL |
| ORM | SQLAlchemy |
| Backend | FastAPI, Uvicorn |
| ML (planned) | XGBoost, scikit-learn, pandas |
| Optimizer (planned) | Google OR-Tools CP-SAT |
| Frontend | React, Vite |
| Scheduling | Apache Airflow (4 DAGs) |

---

## Project Structure

```
DisneyLine/
├── api/                        # FastAPI backend
│   ├── main.py                 # App entry point, CORS config
│   └── routers/
│       ├── rides.py            # GET /api/rides/live
│       └── shows.py            # GET /api/shows/today
│
├── dags/                       # Airflow DAGs
│   ├── wait_time_ingestion.py  # Every 10 min — fetches ride waits
│   └── showtime_refresh.py     # Daily midnight PST — fetches show schedule
│
├── data/
│   └── ride_durations.json     # Curated ride durations (manual reference)
│
├── db/
│   ├── models.py               # SQLAlchemy ORM (Park, Ride, WaitTimeSnapshot, Show, ShowTime)
│   └── session.py              # DB connection management
│
├── fetcher/
│   ├── fetch_wait_times.py     # Core ingestion — polls API, inserts snapshots
│   ├── fetch_showtimes.py      # Pulls today's show schedule
│   ├── seed_rides.py           # One-time: discovers and seeds rides from API
│   ├── seed_shows.py           # One-time: discovers and seeds shows from API
│   └── backfill_ride_locations.py  # One-time: fetches lat/lng per ride
│
├── optimizer/                  # (In progress)
│   └── walk_time.py            # Haversine walk time calculator
│
├── scripts/
│   ├── init_db.py              # Creates all tables
│   └── load_ride_durations.py  # Loads curated durations into DB
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx             # Root component, fetch logic, tab state
│   │   ├── App.css             # Global styles — Disney night sky theme
│   │   └── components/
│   │       ├── StarField.jsx   # Animated background
│   │       ├── WaitTimesTab.jsx
│   │       ├── QuickLook.jsx   # Rides under 20 min
│   │       ├── SortedList.jsx  # All rides ranked with animated bars
│   │       ├── RideCard.jsx    # Individual ride card with duration
│   │       ├── ShowtimesTab.jsx
│   │       └── PlanningTab.jsx # WIP placeholder
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
- Apache Airflow 2.10+
- WSL2 (if on Windows)

### 1. Clone and configure

```bash
git clone https://github.com/yourusername/DisneyLine.git
cd DisneyLine

cp .env.example .env
# Fill in your PostgreSQL credentials in .env
```

### 2. Python environment

```bash
python3 -m venv venv
source venv/bin/activate   # Windows WSL: source venv/bin/activate

pip install -r requirements.txt
```

### 3. Database setup

```bash
# Create the database and user (adjust credentials to match your .env)
sudo -u postgres psql -c "CREATE DATABASE disney_optimizer;"
sudo -u postgres psql -c "CREATE USER disney_user WITH PASSWORD 'yourpassword';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE disney_optimizer TO disney_user;"
sudo -u postgres psql -d disney_optimizer -c "GRANT ALL ON SCHEMA public TO disney_user;"

# Add columns not created by init_db (added incrementally during development)
sudo -u postgres psql -d disney_optimizer -c "ALTER TABLE rides ADD COLUMN IF NOT EXISTS duration_minutes INTEGER;"
sudo -u postgres psql -d disney_optimizer -c "ALTER TABLE rides ADD COLUMN IF NOT EXISTS latitude FLOAT;"
sudo -u postgres psql -d disney_optimizer -c "ALTER TABLE rides ADD COLUMN IF NOT EXISTS longitude FLOAT;"

# Create all tables
python scripts/init_db.py
```

### 4. Seed reference data (one-time)

```bash
python fetcher/seed_rides.py          # Discovers all Disneyland rides
python fetcher/seed_shows.py          # Discovers all shows/entertainment
python fetcher/backfill_ride_locations.py  # Fetches lat/lng per ride
python scripts/load_ride_durations.py      # Loads curated ride durations
```

### 5. Frontend

```bash
cd frontend
npm install
cd ..
```

### 6. Start Airflow

```bash
export AIRFLOW_HOME=~/airflow
export PYTHONPATH=/path/to/DisneyLine

airflow standalone   # UI available at http://localhost:8080

# Symlink DAGs
mkdir -p ~/airflow/dags
ln -s $(pwd)/dags/wait_time_ingestion.py ~/airflow/dags/wait_time_ingestion.py
ln -s $(pwd)/dags/showtime_refresh.py ~/airflow/dags/showtime_refresh.py
```

Enable both DAGs in the Airflow UI. `wait_time_ingestion` will start collecting data every 10 minutes during park hours.

### 7. Run the app

```bash
# Terminal 1 — backend
uvicorn api.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend && npm run dev
```

Open `http://localhost:5173`.

---

## Data Collection

The ingestion pipeline polls [themeparks.wiki](https://api.themeparks.wiki) — a free, open, community-maintained API — every 10 minutes. Each run checks the park's official schedule first and skips the fetch if the park is closed. Every snapshot stores the raw wait time alongside pre-computed time features (hour of day, day of week, is_holiday etc.) so the ML training step doesn't have to re-derive them.

After a few months of collection, the dataset will have enough coverage to train per-time-slot wait time predictions with meaningful accuracy.

---

## ML + Optimizer (In Progress)

The planned ML pipeline:

1. **Feature engineering** — rolling averages, weather (temperature/precipitation via Open-Meteo), park crowd signal (aggregate wait across all rides), holiday flags
2. **Model** — shared XGBoost regressor with `ride_id` as a categorical feature; trained on `TimeSeriesSplit` folds to prevent data leakage
3. **Evaluation** — RMSE on most recent held-out week; new model only promoted to production if it beats the current one
4. **Optimizer** — Google OR-Tools CP-SAT solver with:
   - Hard constraints for must-do rides
   - Reward weights for optional rides (three priority tiers)
   - Time-dependent wait costs from ML predictions
   - Walk time between rides via haversine formula
   - Feasibility detection with actionable suggestions

---

## Roadmap

- [x] PostgreSQL schema + data pipeline
- [x] Airflow orchestration (10-min ingestion + daily showtime refresh)
- [x] FastAPI backend
- [x] React frontend — wait times, showtimes, planning placeholder
- [x] Ride duration data
- [x] Walk time calculator
- [ ] XGBoost wait time prediction model
- [ ] Airflow retraining DAG + model promotion logic
- [ ] OR-Tools day planner with priority tiers
- [ ] Live re-planning during park visit
- [ ] Cloud deployment (DigitalOcean / AWS)

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/rides/live` | GET | Latest wait time snapshot for all rides |
| `/api/shows/today` | GET | Today's show schedule grouped by show |
| `/health` | GET | API health check |

---

## Acknowledgements

Live park data provided by [themeparks.wiki](https://themeparks.wiki) — an open-source community project.
