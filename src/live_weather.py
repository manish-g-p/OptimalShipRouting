"""
Live weather via the Open-Meteo Marine API (free, no API key, no card).

Samples current significant wave height / direction / period on a coarse
grid over the region, then interpolates onto the routing grid to build a
Weather object identical in shape to the stored scenarios.

Docs: https://open-meteo.com/en/docs/marine-weather-api
"""
import time

import numpy as np
import requests
from scipy.interpolate import griddata

import config as C
from src.weather import Weather

_MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
_SAMPLE_STEP = 2.0          # degrees between sampled points
_BATCH = 90                 # locations per API request
_TIMEOUT = 20               # seconds

# Small in-memory cache so repeated routes don't refetch every time.
_cache = {"time": 0.0, "weather": None}
_CACHE_TTL = 300            # 5 minutes


def _sample_points():
    lats = np.arange(C.LAT_MIN, C.LAT_MAX + 1e-6, _SAMPLE_STEP)
    lons = np.arange(C.LON_MIN, C.LON_MAX + 1e-6, _SAMPLE_STEP)
    LO, LA = np.meshgrid(lons, lats)
    return LA.ravel(), LO.ravel()


def _fetch(lat_arr, lon_arr):
    """Call Open-Meteo for a batch of locations; return swh, mwd, mwp."""
    params = {
        "latitude": ",".join(f"{v:.3f}" for v in lat_arr),
        "longitude": ",".join(f"{v:.3f}" for v in lon_arr),
        "current": "wave_height,wave_direction,wave_period",
    }
    r = requests.get(_MARINE_URL, params=params, timeout=_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict):          # single-location response
        data = [data]
    swh, mwd, mwp = [], [], []
    for loc in data:
        cur = loc.get("current", {}) if isinstance(loc, dict) else {}
        swh.append(cur.get("wave_height"))
        mwd.append(cur.get("wave_direction"))
        mwp.append(cur.get("wave_period"))
    to = lambda x: np.array([np.nan if v is None else v for v in x], float)
    return to(swh), to(mwd), to(mwp)


def build_live_weather(grid, use_cache=True):
    """Fetch live waves and resample onto `grid`. Raises on network error."""
    if use_cache and _cache["weather"] is not None \
            and time.time() - _cache["time"] < _CACHE_TTL:
        return _cache["weather"]

    lat_pts, lon_pts = _sample_points()
    swh = np.full(lat_pts.shape, np.nan)
    mwd = np.full(lat_pts.shape, np.nan)
    mwp = np.full(lat_pts.shape, np.nan)
    for i in range(0, len(lat_pts), _BATCH):
        sl = slice(i, i + _BATCH)
        swh[sl], mwd[sl], mwp[sl] = _fetch(lat_pts[sl], lon_pts[sl])

    valid = ~np.isnan(swh)
    if valid.sum() < 4:
        raise RuntimeError("Open-Meteo returned no wave data for this region.")

    pts = np.column_stack([lat_pts[valid], lon_pts[valid]])
    GY, GX = np.meshgrid(grid.lats, grid.lons, indexing="ij")
    tgt = (GY, GX)

    def to_grid(vals, fill):
        vals = vals[valid]
        lin = griddata(pts, vals, tgt, method="linear")
        near = griddata(pts, vals, tgt, method="nearest")   # fill edges
        out = np.where(np.isnan(lin), near, lin)
        return np.nan_to_num(out, nan=fill).astype(np.float32)

    swh_g = to_grid(swh, 0.0)
    mwp_g = to_grid(mwp, 8.0)
    rad = np.deg2rad(mwd)
    cos_g = to_grid(np.cos(rad), 1.0)
    sin_g = to_grid(np.sin(rad), 0.0)

    weather = Weather(swh_g, mwp_g, cos_g, sin_g)
    _cache.update(time=time.time(), weather=weather)
    return weather


if __name__ == "__main__":
    from src import grid as G
    g = G.load_grid()
    w = build_live_weather(g)
    print(f"Live weather OK. swh range {w.swh.min():.2f}-{w.swh.max():.2f} m")
