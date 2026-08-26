# 🧭 Optimal Ship Routing (Nautilus)

Optimal ship routing over the **seas around India** using classical
pathfinding (Dijkstra + weather-aware A\*) plus a **lightweight ML speed
model**, over real geospatial + wave data — exactly as described in the
project synopsis.

- **100% free / offline** — no paid APIs, no cloud, no subscriptions.
- **Laptop-safe** — the giant raw datasets are shrunk **once** to tiny
  files; nothing else ever loads them. Routing takes ~1 second; the ML
  model trains in a couple of seconds.
- **Machine-learning decision layer** — a scikit-learn model predicts the
  vessel's attainable speed from the sea state; the A\* uses that as its
  travel-time cost (matches the synopsis's "ML-based decision techniques").

---

## What it does

1. **Shrinks** the raw data (one time):
   - `GEBCO_2024_sub_ice_topo.nc` (7.4 GB) → `bathymetry.npz` (~0.8 MB)
   - `data_stream-wave_stepType-instant.nc` (4.1 GB) → `weather.npz` (~0.03 MB)
   It also writes a **normalized weather CSV** (`weather_grid.csv`) and
   builds two scenarios: **typical** (time-mean) and **rough** (simulated
   storm, 95th-percentile waves).
2. **Builds a navigable ocean grid**: deep water only, excluding land,
   shoals, and anything within **22 km of the coast**. A KD-tree snaps
   any port to the nearest safe sea cell.
3. **Trains an ML speed model** (`src/ml_model.py`): a scikit-learn
   RandomForest predicts attainable ship speed from wave height,
   direction, period and the chosen vessel's parameters.
4. **Routes** between Indian ports with two algorithms:
   - **Dijkstra** — shortest safe distance (traditional baseline)
   - **Weather-aware A\*** — cost = distance ÷ ML-predicted speed, so it
     optimizes for calmer, faster, safer water (proposed system)
5. **Evaluates** proposed vs traditional (`src/evaluate.py`) on the
   synopsis's metrics: computational efficiency, route optimality, safety
   compliance, adaptability.
6. **Nautilus web UI** — pick a **vessel**, ports, and weather scenario;
   compare routes on an interactive map with a wave-height overlay and
   **per-point weather tooltips**.

---

## Setup (one time)

Everything is already installed on this machine. On a fresh machine:

```bash
pip install -r requirements.txt
```

## Run

**Step 1 — shrink the raw data (only needed once):**

```bash
python -m src.preprocess
```

**Step 2 — launch the Nautilus web app.** There are two front-ends:

### A) Polished Google Maps app (recommended)

```bash
python server.py
```

Then open **http://localhost:8000**. Pick a vessel, origin & destination,
a weather scenario (**Typical / Rough / Live**), and click **Find optimal
route**. Features: satellite/road Google Maps, animated route, live wave
overlay, clickable weather tooltips, side-by-side metric cards.

> **Google Maps key setup (one time).** Your key lives in the local,
> git-ignored `web_config.py`. In Google Cloud Console → your key:
> set **Application restrictions → Websites** and add
> `http://localhost:8000/*` and `http://127.0.0.1:8000/*`, then
> **API restrictions → restrict to "Maps JavaScript API"**. If the map
> ever shows a *RefererNotAllowed* error, temporarily set restrictions to
> **None** while developing. **Never commit or share `web_config.py`.**

### B) Simple Streamlit app (no API key needed)

```bash
streamlit run app.py
```

Open http://localhost:8501. Uses free open-source maps (no Google key).

**Optional — run the full pipeline + evaluation (for report numbers):**

```bash
python run_all.py
```

This trains the ML model (if needed) and prints/saves the proposed-vs-
traditional evaluation table to `data/processed/evaluation.csv`.

**Retrain the ML model on its own:**

```bash
python -m src.ml_model
```

---

## 💾 Reclaim ~11.5 GB of storage (recommended)

After Step 1 succeeds, the two big `.nc` files are **no longer needed**
to run the project. You can move them to an external drive or delete
them (GEBCO is always free to re-download). The project then lives in
under ~1 MB of processed data.

```
data/processed/bathymetry.npz   # ~0.8 MB
data/processed/weather.npz      # ~0.03 MB
data/processed/grid.npz         # built on first run
```

---

## Project layout

```
config.py            # region, resolution, safety + cost settings (edit here)
web_config.py        # PRIVATE: Google Maps key + port (git-ignored)
run_all.py           # headless end-to-end runner (+ evaluation)
server.py            # Flask backend + API for the Google Maps web app
web/                 # polished front-end (index.html, style.css, app.js)
app.py               # simple Streamlit UI (Google-key-free alternative)
src/
  preprocess.py      # Step 1: shrink GEBCO + waves; write weather CSV + scenarios
  grid.py            # navigable mask, coast exclusion, KD-tree
  weather.py         # wave field -> routing grid + analytic cost multiplier
  ml_model.py        # scikit-learn speed model (ML decision layer)
  vessel.py          # vessel types + parameters
  routing.py         # Dijkstra + weather-aware A* (ML-cost aware)
  evaluate.py        # proposed-vs-traditional metrics
  live_weather.py    # real-time waves via free Open-Meteo Marine API
  geo.py             # great-circle distance / bearing helpers
  ports.py           # Indian ports (+ common foreign approaches)
data/processed/      # small cached outputs (npz, csv, joblib)
```

## Tuning

Open `config.py`:

- `GRID_RES` — bigger = faster/lighter, smaller = finer routes.
- `LAT_MIN/MAX`, `LON_MIN/MAX` — change the region.
- `COAST_BUFFER_KM`, `MIN_DEPTH_M` — safety constraints.
- `W_WAVE_HEIGHT`, `W_HEAD_SEAS`, `W_PERIOD` — how strongly weather bends
  the A\* route. Increase them and the A\* route visibly avoids rough seas.

## Future scope

- Swap the time-averaged / scenario weather for a **live** feed (the free
  Open-Meteo Marine API, no key) or a specific forecast timestamp.
- Extend the region for global voyages by widening the bounding box in
  `config.py` and re-running `python -m src.preprocess`.
- Train the ML speed model on **real AIS speed logs** instead of the
  synthesized speed-loss dataset, for site-specific accuracy.
