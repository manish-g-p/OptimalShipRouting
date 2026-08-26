"""
Weather layer: put the coarse wave field onto the fine routing grid and
turn wave conditions into a travel-cost multiplier.

The multiplier is a simple, EXPLAINABLE formula (no black box):
    higher waves            -> costlier
    sailing INTO the waves  -> costlier still (head seas)
    short choppy periods    -> slightly costlier
So the A* naturally prefers calmer water and following/beam seas.
"""
import numpy as np
from scipy.interpolate import RegularGridInterpolator

import config as C


class Weather:
    def __init__(self, swh, mwp, mwd_cos, mwd_sin):
        # All arrays are already resampled onto the routing grid shape.
        self.swh = swh                 # significant wave height (m)
        self.mwp = mwp                 # mean wave period (s)
        self.mwd_cos = mwd_cos         # cos/sin of mean wave direction
        self.mwd_sin = mwd_sin

    def mwd_deg(self):
        return (np.degrees(np.arctan2(self.mwd_sin, self.mwd_cos)) + 360) % 360

    def multiplier(self, row, col, heading_deg):
        """Cost multiplier (>=1) for leaving cell (row,col) on `heading`."""
        h = float(self.swh[row, col])
        p = float(self.mwp[row, col])
        wave_from = np.degrees(np.arctan2(self.mwd_sin[row, col],
                                          self.mwd_cos[row, col]))

        # Head-sea factor: 1 when sailing straight into the waves, 0 when
        # they are behind you.
        theta = np.radians(heading_deg - wave_from)
        head_factor = (1.0 + np.cos(theta)) / 2.0

        # Short periods (<8 s) are choppier and less comfortable.
        period_pen = max(0.0, (8.0 - p)) / 8.0

        m = (1.0
             + C.W_WAVE_HEIGHT * h
             + C.W_HEAD_SEAS * h * head_factor
             + C.W_PERIOD * period_pen)
        return float(min(m, C.MAX_WEATHER_MULT))


def _interp_to_grid(src_lats, src_lons, field, dst_lats, dst_lons, fill=0.0):
    """Bilinear-resample a coarse field onto the fine routing grid."""
    field = np.nan_to_num(field, nan=fill).astype(np.float64)
    # RegularGridInterpolator needs strictly ascending axes.
    if src_lats[0] > src_lats[-1]:
        src_lats, field = src_lats[::-1], field[::-1, :]
    if src_lons[0] > src_lons[-1]:
        src_lons, field = src_lons[::-1], field[:, ::-1]
    interp = RegularGridInterpolator(
        (src_lats, src_lons), field, bounds_error=False, fill_value=fill)
    gy, gx = np.meshgrid(dst_lats, dst_lons, indexing="ij")
    return interp((gy, gx)).astype(np.float32)


def _read_weather_source(scenario="typical"):
    """Return (lats, lons, swh, mwd, mwp) for the wave grid.

    scenario: 'typical' (time-mean) or 'rough' (simulated storm, P95 waves).
    Prefers the normalized CSV (PDF methodology) and falls back to the
    .npz. Both describe the same regular wave grid.
    """
    sc = "rough" if scenario == "rough" else "typical"
    if C.WEATHER_CSV.exists():
        import pandas as pd
        df = pd.read_csv(C.WEATHER_CSV)
        lats = np.sort(df["lat"].unique()).astype(np.float32)
        lons = np.sort(df["lon"].unique()).astype(np.float32)
        piv = lambda col: (df.pivot(index="lat", columns="lon", values=col)
                             .sort_index().sort_index(axis=1).values)
        return lats, lons, piv(f"swh_{sc}"), piv("mwd"), piv(f"mwp_{sc}")

    w = np.load(C.WEATHER_FILE)
    return (w["lats"], w["lons"],
            w[f"swh_{sc}"], w["mwd"], w[f"mwp_{sc}"])


def load_weather(grid, scenario="typical"):
    """Load the weather grid (CSV preferred) and resample it onto `grid`.

    scenario: 'typical' or 'rough' (simulated storm conditions).
    """
    slat, slon, swh_src, mwd_src, mwp_src = _read_weather_source(scenario)
    mwd_rad = np.deg2rad(mwd_src)

    swh = _interp_to_grid(slat, slon, swh_src, grid.lats, grid.lons, fill=0.0)
    mwp = _interp_to_grid(slat, slon, mwp_src, grid.lats, grid.lons, fill=8.0)
    cos = _interp_to_grid(slat, slon, np.cos(mwd_rad), grid.lats, grid.lons)
    sin = _interp_to_grid(slat, slon, np.sin(mwd_rad), grid.lats, grid.lons)
    return Weather(swh, mwp, cos, sin)
