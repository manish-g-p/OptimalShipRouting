"""
Central configuration for the Optimal Ship Routing system.

Everything tunable lives here so the rest of the code stays clean.
Edit BBOX / GRID_RES if you ever want a different region or resolution.
"""
from pathlib import Path

# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent

# Raw NetCDF files (the giant ones). These are read ONCE by preprocess.py
# and then never touched again. You can move/delete them after that.
GEBCO_NC = ROOT / "GEBCO_2024_sub_ice_topo.nc"          # 7.4 GB bathymetry
WAVE_NC  = ROOT / "data_stream-wave_stepType-instant.nc"  # 4.1 GB ERA5 waves

# Small processed outputs live here (a few MB total).
PROCESSED = ROOT / "data" / "processed"
PROCESSED.mkdir(parents=True, exist_ok=True)

BATHY_FILE   = PROCESSED / "bathymetry.npz"   # depth grid + lat/lon
WEATHER_FILE = PROCESSED / "weather.npz"      # swh/mwd/mwp on wave grid
WEATHER_CSV  = PROCESSED / "weather_grid.csv" # normalized weather (PDF: CSV)
GRID_FILE    = PROCESSED / "grid.npz"         # navigable mask + costs
ML_MODEL_FILE = PROCESSED / "speed_model.joblib"  # trained speed predictor
EVAL_CSV     = PROCESSED / "evaluation.csv"   # proposed-vs-traditional metrics

# ----------------------------------------------------------------------
# Region of interest: the seas around India (all Indian ports).
# lat 0 -> 27 N, lon 60 -> 100 E covers the Arabian Sea, the Bay of
# Bengal and the approaches used by Indian incoming/outgoing traffic.
# ----------------------------------------------------------------------
LAT_MIN, LAT_MAX = 0.0, 27.0
# West edge is 50E so Oman/UAE ports (Salalah 54E, Dubai 54.9E) and the
# Gulf of Oman are inside the map - otherwise routes to them stop short
# at the boundary, leaving a visible gap.
LON_MIN, LON_MAX = 50.0, 100.0
BBOX = (LON_MIN, LAT_MIN, LON_MAX, LAT_MAX)

# Routing grid resolution in degrees. 0.05 deg is about 5.5 km per cell.
# Bigger number  -> fewer cells -> faster + lighter (safer for laptops).
# Smaller number -> finer routes -> heavier. 0.05 is a good balance.
GRID_RES = 0.05

# ----------------------------------------------------------------------
# Navigability / safety constraints
# ----------------------------------------------------------------------
# A cell counts as open water only if the seafloor is deeper than this
# (elevation more negative than -MIN_DEPTH_M). Keeps ships off shoals.
MIN_DEPTH_M = 10.0

# Exclude any sea cell within this distance of land (synopsis: 22 km).
COAST_BUFFER_KM = 22.0

# ----------------------------------------------------------------------
# Ship / cost-function parameters (used by the weather-aware A*)
# ----------------------------------------------------------------------
SHIP_SPEED_KN = 18.0   # nominal calm-water speed in knots

# How strongly waves penalise a leg. These are simple, explainable
# weights - tune them and the route visibly changes.
W_WAVE_HEIGHT = 0.6    # penalty per metre of significant wave height
W_HEAD_SEAS   = 0.4    # extra penalty for sailing INTO the waves
W_PERIOD      = 0.1    # short, choppy periods are slightly worse

# Cap so a single stormy cell can't make cost explode to infinity.
MAX_WEATHER_MULT = 4.0

KM_PER_DEG = 111.195   # mean km per degree of latitude
