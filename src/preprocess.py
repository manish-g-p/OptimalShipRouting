"""
Step 1 - the ONE-TIME data shrink.

Reads the giant GEBCO (7.4 GB) and wave (4.1 GB) NetCDF files *lazily*,
carves out only the seas around India, downsamples, and writes small
.npz files (a few MB) into data/processed/.

Memory safety: files are opened with dask chunking, so data is streamed
in small blocks. The full arrays are never held in RAM at once. After
this runs once you can move or delete the two big .nc files.

Run:  python -m src.preprocess
"""
import time
import numpy as np
import xarray as xr

import config as C


def _log(msg):
    print(f"[preprocess] {msg}", flush=True)


def shrink_bathymetry():
    """GEBCO global elevation -> small India-region depth grid."""
    _log(f"Opening GEBCO (lazy): {C.GEBCO_NC.name}")
    # chunks= makes xarray use dask -> streamed, low memory.
    ds = xr.open_dataset(C.GEBCO_NC, chunks={"lat": 2048, "lon": 2048})

    # Slice to the region (GEBCO lat/lon are ascending, -90..90 / -180..180).
    sub = ds["elevation"].sel(
        lat=slice(C.LAT_MIN, C.LAT_MAX),
        lon=slice(C.LON_MIN, C.LON_MAX),
    )
    _log(f"Region subset shape (full-res): {sub.shape}")

    # Downsample by block-coarsening. We keep the SHALLOWEST point in each
    # block (max elevation) so shoals are never averaged away -> safer.
    native = 1.0 / 240.0                       # GEBCO native res ~0.004167 deg
    factor = max(1, int(round(C.GRID_RES / native)))
    _log(f"Coarsening by factor {factor} (~{C.GRID_RES} deg cells)...")

    coarse = sub.coarsen(lat=factor, lon=factor, boundary="trim").max()

    t0 = time.time()
    elevation = coarse.values.astype(np.float32)   # triggers the streamed read
    lats = coarse["lat"].values.astype(np.float32)
    lons = coarse["lon"].values.astype(np.float32)
    ds.close()
    _log(f"Bathymetry loaded {elevation.shape} in {time.time()-t0:.1f}s")

    np.savez_compressed(C.BATHY_FILE, elevation=elevation, lats=lats, lons=lons)
    mb = C.BATHY_FILE.stat().st_size / 1e6
    _log(f"Saved {C.BATHY_FILE.name} ({mb:.2f} MB)")
    return lats, lons


def shrink_weather():
    """ERA5 waves -> time-averaged swh/mwd/mwp for the India region."""
    _log(f"Opening waves (lazy): {C.WAVE_NC.name}")
    ds = xr.open_dataset(C.WAVE_NC, chunks={"valid_time": 200})

    # Longitude here is 0..359.5, so 60..100 needs no wrap-around handling.
    lat_mask = (ds["latitude"] >= C.LAT_MIN) & (ds["latitude"] <= C.LAT_MAX)
    lon_mask = (ds["longitude"] >= C.LON_MIN) & (ds["longitude"] <= C.LON_MAX)
    sub = ds.isel(
        latitude=np.where(lat_mask.values)[0],
        longitude=np.where(lon_mask.values)[0],
    )
    _log(f"Wave region grid: {sub.sizes['latitude']} x {sub.sizes['longitude']}"
         f" over {sub.sizes['valid_time']} timesteps")

    # The region is small, so load its full time series once (~0.3 GB)
    # and derive two weather SCENARIOS:
    #   * typical : time-mean conditions (calm/average sailing)
    #   * rough   : 95th-percentile wave height + shorter (P10) periods,
    #               i.e. simulated stormy conditions.
    # Direction is the circular (vector) time-mean, shared by both.
    t0 = time.time()
    sub = sub.load()                           # streamed read of the region
    swh = sub["swh"].values.astype(np.float32)  # (time, lat, lon)
    mwp = sub["mwp"].values.astype(np.float32)
    mwd = sub["mwd"].values.astype(np.float32)
    lats = sub["latitude"].values.astype(np.float32)
    lons = sub["longitude"].values.astype(np.float32)
    ds.close()

    swh_typ = np.nanmean(swh, axis=0)
    swh_rough = np.nanpercentile(swh, 95, axis=0)
    mwp_typ = np.nanmean(mwp, axis=0)
    mwp_rough = np.nanpercentile(mwp, 10, axis=0)    # shorter = choppier
    rad = np.deg2rad(mwd)
    mwd_mean = (np.rad2deg(np.arctan2(np.nanmean(np.sin(rad), axis=0),
                                      np.nanmean(np.cos(rad), axis=0))) % 360.0)
    _log(f"Weather scenarios (typical/rough) computed in {time.time()-t0:.1f}s")

    np.savez_compressed(
        C.WEATHER_FILE, lats=lats, lons=lons,
        swh_typical=swh_typ.astype(np.float32),
        swh_rough=swh_rough.astype(np.float32),
        mwp_typical=mwp_typ.astype(np.float32),
        mwp_rough=mwp_rough.astype(np.float32),
        mwd=mwd_mean.astype(np.float32),
        # keep legacy keys so old code still works
        swh=swh_typ.astype(np.float32), mwp=mwp_typ.astype(np.float32),
    )
    mb = C.WEATHER_FILE.stat().st_size / 1e6
    _log(f"Saved {C.WEATHER_FILE.name} ({mb:.2f} MB) | "
         f"typical max swh {np.nanmax(swh_typ):.1f}m, "
         f"rough max swh {np.nanmax(swh_rough):.1f}m")


def export_weather_csv():
    """Write the weather grid to a normalized CSV (PDF methodology:
    'Weather datasets stored in CSV are normalized and mapped to grid
    cells'). One row per weather grid cell."""
    import pandas as pd

    w = np.load(C.WEATHER_FILE)
    lats, lons = w["lats"], w["lons"]
    LO, LA = np.meshgrid(lons, lats)          # (nlat, nlon)

    def norm(a):
        a = np.asarray(a, dtype=np.float64)
        lo, hi = np.nanmin(a), np.nanmax(a)
        return np.zeros_like(a) if hi <= lo else (a - lo) / (hi - lo)

    df = pd.DataFrame({
        "lat": LA.ravel(),
        "lon": LO.ravel(),
        "mwd": w["mwd"].ravel(),                        # wave direction (deg)
        "swh_typical": w["swh_typical"].ravel(),        # wave height (m)
        "swh_rough": w["swh_rough"].ravel(),
        "mwp_typical": w["mwp_typical"].ravel(),        # wave period (s)
        "mwp_rough": w["mwp_rough"].ravel(),
        "swh_typical_norm": norm(w["swh_typical"]).ravel(),   # 0..1
        "swh_rough_norm": norm(w["swh_rough"]).ravel(),
    })
    df.to_csv(C.WEATHER_CSV, index=False)
    _log(f"Saved {C.WEATHER_CSV.name} ({len(df)} grid cells, "
         f"{C.WEATHER_CSV.stat().st_size/1e3:.1f} KB)")


def main():
    _log("=== Step 1: shrinking raw data (one-time) ===")
    shrink_bathymetry()
    shrink_weather()
    export_weather_csv()
    _log("Done. The big .nc files are no longer needed for routing.")


if __name__ == "__main__":
    main()
