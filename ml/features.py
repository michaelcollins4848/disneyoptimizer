#pulls raw snapshots from PostgreSQL and returns a clean DataFrame ready for XGBoost training or inference
import pandas as pd
import numpy as np
from sqlalchemy import text
from db.session import get_session



FEATURE_COLS = [
    'hour_of_day',
    'day_of_week',
    'month',
    'is_weekend',
    'is_holiday',
    'minutes_since_open', # (hour - 8) * 60, clipped to 0
    'ride_encoded', # target encoding: each ride's mean wait time
    'park_avg_wait', # avg wait across all rides at this timestamp
    'park_pct_operating',  # fraction of rides running (crowd proxy)
    'ride_rolling_avg_7d',  # this ride's rolling avg over past 7 days
    'ride_rolling_avg_30d',  # this ride's rolling avg over past 30 days
]

TARGET = 'wait_minutes'


def load_raw_data() -> pd.DataFrame:

    session = get_session()
    try:
        result = session.execute(text("""
            SELECT
                w.ride_id,
                r.name          AS ride_name,
                w.wait_minutes,
                w.recorded_at,
                w.hour_of_day,
                w.day_of_week,
                w.month,
                w.is_weekend,
                w.is_holiday
            FROM wait_time_snapshots w
            JOIN rides r ON r.id = w.ride_id
            WHERE w.status = 'OPERATING'
              AND w.wait_minutes IS NOT NULL
            ORDER BY w.recorded_at ASC
        """))
        rows = result.fetchall()
        df   = pd.DataFrame(rows, columns=result.keys())
        print(f"Loaded {len(df)} operating snapshots from DB.")
        return df
    finally:
        session.close()


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:

    df = df.copy()
    df['recorded_at'] = pd.to_datetime(df['recorded_at'], utc=True)
    df['is_weekend']  = df['is_weekend'].astype(int)
    df['is_holiday']  = df['is_holiday'].astype(int)
    df = df.sort_values(['ride_id', 'recorded_at']).reset_index(drop=True)

    df['minutes_since_open'] = ((df['hour_of_day'] - 8) * 60).clip(lower=0)


    ride_means       = df.groupby('ride_id')['wait_minutes'].mean()
    df['ride_encoded'] = df['ride_id'].map(ride_means)


    df['time_bin'] = df['recorded_at'].dt.floor('10min')
    crowd = (
        df.groupby('time_bin')
        .agg(
            park_avg_wait      = ('wait_minutes', 'mean'),
            park_pct_operating = ('wait_minutes', lambda x: x.notna().mean()),
        )
        .reset_index()
    )
    df = df.merge(crowd, on='time_bin', how='left')


    df = df.set_index('recorded_at')

    df['ride_rolling_avg_7d'] = (
        df.groupby('ride_id')['wait_minutes']
        .transform(lambda x: x.rolling('7D', min_periods=5).mean())
    )
    df['ride_rolling_avg_30d'] = (
        df.groupby('ride_id')['wait_minutes']
        .transform(lambda x: x.rolling('30D', min_periods=10).mean())
    )

    df = df.reset_index()

    before = len(df)
    df = df.dropna(subset=['ride_rolling_avg_7d', 'ride_rolling_avg_30d'])
    dropped = before - len(df)
    if dropped > 0:
        print(f"Dropped {dropped} rows with insufficient rolling history.")

    keep = FEATURE_COLS + [TARGET, 'ride_id', 'ride_name', 'recorded_at']
    return df[keep].reset_index(drop=True)


def build_ride_encoding_map() -> dict:

    session = get_session()
    try:
        result = session.execute(text("""
            SELECT ride_id, AVG(wait_minutes) AS mean_wait
            FROM wait_time_snapshots
            WHERE status = 'OPERATING' AND wait_minutes IS NOT NULL
            GROUP BY ride_id
        """))
        return {row[0]: float(row[1]) for row in result.fetchall()}
    finally:
        session.close()
