
#trains the shared XGBoost wait time prediction model.

import os
import sys
import json
import numpy as np
import xgboost as xgb
from datetime import datetime
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_squared_error

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml.features import load_raw_data, engineer_features, FEATURE_COLS, TARGET

MODELS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'models'
)
PROD_MODEL_PATH = os.path.join(MODELS_DIR, 'production.json')
PROD_META_PATH  = os.path.join(MODELS_DIR, 'production_meta.json')

#minimum rows needed to attempt training at all
MIN_ROWS = 100


def train(force_promote: bool = False) -> float:

    print("=" * 55)
    print("DisneyLine — Wait Time Model Training")
    print("=" * 55)

    print("\n[1/4] Loading data...")
    raw = load_raw_data()

    print("[2/4] Engineering features...")
    df = engineer_features(raw)
    print(f"      {len(df)} rows ready for training.")

    if len(df) < MIN_ROWS:
        print(f"\nNot enough data ({len(df)} rows, need {MIN_ROWS}). Exiting.")
        return float('inf')

    X = df[FEATURE_COLS].astype(float)
    y = df[TARGET].astype(float)

    print("\n[3/4] Cross-validating (TimeSeriesSplit, 5 folds)...")
    tscv       = TimeSeriesSplit(n_splits=5)
    fold_rmses = []

    for fold, (train_idx, val_idx) in enumerate(tscv.split(X)):
        X_train, y_train = X.iloc[train_idx], y.iloc[train_idx]
        X_val,   y_val   = X.iloc[val_idx],   y.iloc[val_idx]

        fold_model = xgb.XGBRegressor(
            n_estimators        = 400,
            learning_rate       = 0.05,
            max_depth           = 6,
            subsample           = 0.8,
            colsample_bytree    = 0.8,
            min_child_weight    = 5,
            early_stopping_rounds = 20,
            eval_metric         = 'rmse',
            verbosity           = 0,
        )
        fold_model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            verbose=False,
        )

        preds = fold_model.predict(X_val)
        rmse  = np.sqrt(mean_squared_error(y_val, preds))
        fold_rmses.append(rmse)
        print(f"      Fold {fold + 1}: RMSE = {rmse:.2f} min")

    avg_rmse = float(np.mean(fold_rmses))
    print(f"\n      Average CV RMSE: {avg_rmse:.2f} min")

    if avg_rmse < 10:
        print("      ✓ Strong predictions (error < 10 min)")
    elif avg_rmse < 20:
        print("      ~ Decent predictions (error 10–20 min)")
    else:
        print("      ✗ High error — need more data before deploying")

    print("\n[4/4] Training final model on full dataset...")
    final_model = xgb.XGBRegressor(
        n_estimators     = 400,
        learning_rate    = 0.05,
        max_depth        = 6,
        subsample        = 0.8,
        colsample_bytree = 0.8,
        min_child_weight = 5,
        verbosity        = 0,
    )
    final_model.fit(X, y)

    os.makedirs(MODELS_DIR, exist_ok=True)
    timestamp  = datetime.now().strftime('%Y%m%d_%H%M%S')
    model_path = os.path.join(MODELS_DIR, f'xgb_{timestamp}.json')
    meta_path  = os.path.join(MODELS_DIR, f'xgb_{timestamp}_meta.json')

    final_model.save_model(model_path)

    meta = {
        'trained_at':   timestamp,
        'n_samples':    len(df),
        'avg_cv_rmse':  round(avg_rmse, 3),
        'fold_rmses':   [round(r, 3) for r in fold_rmses],
        'features':     FEATURE_COLS,
        'n_rides':      int(df['ride_id'].nunique()),
        'date_range': {
            'start': str(df['recorded_at'].min()),
            'end':   str(df['recorded_at'].max()),
        },
    }
    with open(meta_path, 'w') as f:
        json.dump(meta, f, indent=2)

    print(f"\n      Saved: {model_path}")

    should_promote = force_promote

    if not force_promote:
        if not os.path.exists(PROD_META_PATH):
            print("\n      No production model exists yet — promoting automatically.")
            should_promote = True
        else:
            with open(PROD_META_PATH) as f:
                prod_meta = json.load(f)
            prod_rmse = prod_meta.get('avg_cv_rmse', float('inf'))

            if avg_rmse < prod_rmse:
                improvement = prod_rmse - avg_rmse
                print(f"\n      New RMSE ({avg_rmse:.2f}) beats production ({prod_rmse:.2f})")
                print(f"      Improvement: {improvement:.2f} min → promoting.")
                should_promote = True
            else:
                print(f"\n      New RMSE ({avg_rmse:.2f}) does not beat production ({prod_rmse:.2f}).")
                print("      Keeping existing production model.")

    if should_promote:
        final_model.save_model(PROD_MODEL_PATH)
        with open(PROD_META_PATH, 'w') as f:
            json.dump(meta, f, indent=2)
        print("      ✓ Promoted to production.")

    print("\n" + "=" * 55)
    print(f"Training complete. RMSE: {avg_rmse:.2f} min")
    print("=" * 55)
    return avg_rmse


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--force', action='store_true',
                        help='Promote to production even if RMSE does not improve')
    args = parser.parse_args()
    train(force_promote=args.force)
