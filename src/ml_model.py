"""
Lightweight ML decision layer (PDF: "machine learning-based decision
techniques").

A small scikit-learn RandomForest predicts the ATTAINABLE ship speed for
a given sea state and vessel. The weather-aware A* then uses that
prediction as its cost (cost = distance / predicted speed), so routing
adapts to how the actual vessel is slowed by waves.

Training data: real per-ship speed-loss logs are not public, so we
synthesize a dataset from an empirical added-resistance / speed-loss
relation (added resistance grows ~ with wave height squared and is worst
in head seas). The model learns that relation and generalizes smoothly.
Training takes a couple of seconds; the saved model is a few hundred KB.
"""
import numpy as np
import joblib
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score

import config as C
from src import geo, vessel as V

# Feature order MUST stay identical for train and predict.
FEATURES = ["swh", "rel_angle_deg", "mwp", "service_speed_kn", "wave_sensitivity"]

_OFF = [(-1, -1), (-1, 0), (-1, 1),
        (0, -1),           (0, 1),
        (1, -1),  (1, 0),  (1, 1)]


# ----------------------------------------------------------------------
# Physics-inspired label generator (the "ground truth" we learn from)
# ----------------------------------------------------------------------
def _attainable_speed(swh, rel_angle_deg, mwp, service_kn, sensitivity):
    """Empirical speed a vessel can actually hold in a given sea state."""
    # Head-sea factor: 1 straight into the waves, 0 following seas.
    hf = (1.0 + np.cos(np.deg2rad(rel_angle_deg))) / 2.0
    # Short periods (<8 s) are choppier -> a bit more loss.
    period_pen = np.clip((8.0 - mwp) / 8.0, 0.0, 1.0)
    # Added-resistance style loss: grows with swh^2, worse in head seas.
    loss = sensitivity * (0.045 * swh**2 * hf
                          + 0.015 * swh
                          + 0.05 * period_pen)
    loss = np.clip(loss, 0.0, 0.75)
    return service_kn * (1.0 - loss)


def _make_dataset(n=20000, seed=42):
    rng = np.random.default_rng(seed)
    swh = rng.uniform(0.0, 8.0, n)                 # m
    rel = rng.uniform(0.0, 180.0, n)               # deg (0 = head seas)
    mwp = rng.uniform(3.0, 15.0, n)                # s
    vs = list(V.VESSELS.values())
    pick = rng.integers(0, len(vs), n)
    service = np.array([vs[i].service_speed_kn for i in pick])
    sens = np.array([vs[i].wave_sensitivity for i in pick])

    y = _attainable_speed(swh, rel, mwp, service, sens)
    y = y + rng.normal(0.0, 0.15, n)               # measurement noise
    X = np.column_stack([swh, rel, mwp, service, sens])
    return X, y


# ----------------------------------------------------------------------
# Train / load
# ----------------------------------------------------------------------
def train(save=True, verbose=True):
    X, y = _make_dataset()
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=0)
    model = RandomForestRegressor(
        n_estimators=60, max_depth=12, min_samples_leaf=5,
        n_jobs=-1, random_state=0)
    model.fit(Xtr, ytr)
    if verbose:
        pred = model.predict(Xte)
        print(f"[ml] trained on {len(Xtr):,} samples | "
              f"MAE={mean_absolute_error(yte, pred):.3f} kn | "
              f"R2={r2_score(yte, pred):.3f}")
    if save:
        joblib.dump(model, C.ML_MODEL_FILE)
        if verbose:
            kb = C.ML_MODEL_FILE.stat().st_size / 1e3
            print(f"[ml] saved {C.ML_MODEL_FILE.name} ({kb:.0f} KB)")
    return model


def load(train_if_missing=True):
    if C.ML_MODEL_FILE.exists():
        return joblib.load(C.ML_MODEL_FILE)
    if train_if_missing:
        return train(verbose=False)
    raise FileNotFoundError("No trained speed model. Run: python -m src.ml_model")


def predict_speed(model, swh, rel_angle_deg, mwp, ves):
    """Attainable speed (kn) for arrays of sea-state values + a vessel."""
    swh = np.asarray(swh, float).ravel()
    rel = np.asarray(rel_angle_deg, float).ravel()
    mwp = np.asarray(mwp, float).ravel()
    service = np.full_like(swh, ves.service_speed_kn)
    sens = np.full_like(swh, ves.wave_sensitivity)
    X = np.column_stack([swh, rel, mwp, service, sens])
    return model.predict(X)


# ----------------------------------------------------------------------
# Build the per-cell, per-direction cost multiplier from ML predictions
# ----------------------------------------------------------------------
def build_multiplier_grid(grid, weather, ves, model):
    """mult[r,c,k] = service_speed / predicted_speed  (>=1), clipped.

    Feeding this into the Router turns the A* cost into travel-time,
    driven by the ML speed prediction.
    """
    nlat, nlon = grid.nlat, grid.nlon
    res = C.GRID_RES

    # Heading of each of the 8 moves, per latitude row.
    head_dir = np.zeros((nlat, 8))
    for r in range(nlat):
        la = grid.lats[r]
        for k, (dr, dc) in enumerate(_OFF):
            r2 = min(max(r + dr, 0), nlat - 1)
            la2 = grid.lats[r2] if r2 != r else la + dr * res
            head_dir[r, k] = geo.bearing_deg(la, 0.0, la2, dc * res)

    wave_from = weather.mwd_deg()               # (nlat, nlon)
    swh = weather.swh
    mwp = weather.mwp
    service = ves.service_speed_kn

    mult = np.empty((nlat, nlon, 8), dtype=np.float32)
    for k in range(8):
        heading = head_dir[:, k][:, None]        # (nlat, 1)
        rel = np.abs((heading - wave_from + 180.0) % 360.0 - 180.0)  # 0..180
        speed = predict_speed(model, swh, rel, mwp, ves).reshape(nlat, nlon)
        speed = np.clip(speed, 1.0, service)     # never faster than calm
        mult[:, :, k] = np.clip(service / speed, 1.0, C.MAX_WEATHER_MULT)
    return mult


if __name__ == "__main__":
    train()
