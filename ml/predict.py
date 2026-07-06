
#loads the production XGBoost model and exposes a clean predict()
# Single prediction: wait = predict_wait(ride_id='abc123', target_dt=datetime(2026, 7, 4, 14, 0))
# Full day of predictions for a ride (all 15-min slots): schedule = predict_day(ride_id='abc123', date=date(2026, 7, 4))

import os
import sys
import json
import numpy as np
import pandas as pd
import xgboost as xgb
import holidays
from datetime import datetime, date, timedelta, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml.features import FEATURE_COLS, build_ride_encoding_map

MODELS_DIR      = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'models'
)
PROD_MODEL_PATH = os.path.join(MODELS_DIR, 'production.json')
PROD_META_PATH  = os.path.join(MODELS_DIR, 'production_meta.json')
US_HOLIDAYS     = holidays.US()

_model = None
_ride_means  = None


def _load_model():
    global _model
    if _model is None:
        if not os.path.exists(PROD_MODEL_PATH):
            raise FileNotFoundError(
                "No production model found. Run: python ml/train.py"
            )
        _model = xgb.XGBRegressor()
        _model.load_model(PROD_MODEL_PATH)
    return _model


def _load_ride_means() -> dict:
    global _ride_means
    if _ride_means is None:
        _ride_means = build_ride_encoding_map()
    return _ride_means


def _build_feature_row(
    ride_id:             str,
    target_dt:           datetime,
    park_avg_wait:       float = 25.0,
    park_pct_operating:  float = 0.85,
    ride_rolling_avg_7d: float | None = None,
    ride_rolling_avg_30d: float | None = None,
) -> pd.DataFrame:

    ride_means  = _load_ride_means()
    ride_encoded = ride_means.get(ride_id, float(np.mean(list(ride_means.values()))))

    # Use rolling mean as a fallback if not supplied
    rolling_fallback = ride_encoded
    if ride_rolling_avg_7d  is None: ride_rolling_avg_7d  = rolling_fallback
    if ride_rolling_avg_30d is None: ride_rolling_avg_30d = rolling_fallback

    row = {
        'hour_of_day':          target_dt.hour,
        'day_of_week':          target_dt.weekday(),
        'month':                target_dt.month,
        'is_weekend':           int(target_dt.weekday() >= 5),
        'is_holiday':           int(target_dt.date() in US_HOLIDAYS),
        'minutes_since_open':   max((target_dt.hour - 8) * 60, 0),
        'ride_encoded':         ride_encoded,
        'park_avg_wait':        park_avg_wait,
        'park_pct_operating':   park_pct_operating,
        'ride_rolling_avg_7d':  ride_rolling_avg_7d,
        'ride_rolling_avg_30d': ride_rolling_avg_30d,
    }
    return pd.DataFrame([row])[FEATURE_COLS]


def predict_wait(
    ride_id:   str,
    target_dt: datetime,
    **kwargs,
) -> float:

    model    = _load_model()
    features = _build_feature_row(ride_id, target_dt, **kwargs)
    pred     = model.predict(features.astype(float))[0]
    return float(max(pred, 0.0))


def predict_day(
    ride_id:    str,
    target_date: date,
    open_hour:   int = 8,
    close_hour:  int = 22,
    interval_minutes: int = 15,
) -> list[dict]:

    model  = _load_model()
    slots  = []
    rows   = []
    dt     = datetime(target_date.year, target_date.month, target_date.day,
                      open_hour, 0, tzinfo=timezone.utc)
    close  = datetime(target_date.year, target_date.month, target_date.day,
                      close_hour, 0, tzinfo=timezone.utc)

    while dt <= close:
        rows.append(_build_feature_row(ride_id, dt).iloc[0])
        slots.append(dt)
        dt += timedelta(minutes=interval_minutes)

    if not rows:
        return []

    X     = pd.DataFrame(rows)[FEATURE_COLS].astype(float)
    preds = model.predict(X)

    return [
        {
            'time': slot.isoformat(),
            'slot': i,
            'predicted_wait': float(max(p, 0.0)),
        }
        for i, (slot, p) in enumerate(zip(slots, preds))
    ]


def get_model_info() -> dict:
    if not os.path.exists(PROD_META_PATH):
        return {'status': 'no_model'}
    with open(PROD_META_PATH) as f:
        return json.load(f)


if __name__ == '__main__':
    # Quick smoke test
    info = get_model_info()
    if info.get('status') == 'no_model':
        print("No production model yet. Run: python ml/train.py")
    else:
        print(f"Production model trained at: {info['trained_at']}")
        print(f"CV RMSE: {info['avg_cv_rmse']} min")
        print(f"Trained on {info['n_samples']} samples across {info['n_rides']} rides")
