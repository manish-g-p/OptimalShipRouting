"""
Grid model: turn the small bathymetry slice into a navigable ocean map.

Produces:
  * navigable mask  - True where a ship may sail (deep enough AND far
                      enough from the coast)
  * KD-tree         - maps any (lat, lon) to the nearest navigable cell
Cached to data/processed/grid.npz so it is built only once.

Run standalone to (re)build:  python -m src.grid
"""
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

import config as C

# 8-connectivity structuring element for component labelling.
_CONN8 = np.ones((3, 3), dtype=int)


class Grid:
    def __init__(self, lats, lons, elevation, navigable):
        self.lats = lats                      # 1D, ascending (south->north)
        self.lons = lons                      # 1D, ascending (west->east)
        self.elevation = elevation            # 2D (nlat, nlon), metres
        self.navigable = navigable            # 2D bool
        self.nlat, self.nlon = navigable.shape

        # Restrict port-snapping to the MAIN connected ocean body, so a
        # port can never snap into a small enclosed pocket (which would be
        # unreachable and produce a confusing "no route"). Routing still
        # runs on the full navigable mask; endpoints just always sit in
        # the main basin, so any two ports are guaranteed connected.
        labels, n = ndimage.label(navigable, structure=_CONN8)
        if n > 0:
            sizes = np.bincount(labels.ravel())
            sizes[0] = 0                      # background
            main = int(sizes.argmax())
            snap_mask = labels == main
        else:
            snap_mask = navigable
        self.main_component = snap_mask

        # KD-tree over the main-basin cells. Coordinates stored as
        # (lat, lon) in degrees; lon is scaled by cos(lat) so distances
        # are roughly isotropic.
        rows, cols = np.where(snap_mask)
        self._cells = np.column_stack([rows, cols])
        cell_lat = lats[rows]
        cell_lon = lons[cols]
        self._coslat = np.cos(np.deg2rad(cell_lat.mean()))
        pts = np.column_stack([cell_lat, cell_lon * self._coslat])
        self._tree = cKDTree(pts)

    # -- coordinate <-> cell helpers -----------------------------------
    def nearest_cell(self, lat, lon):
        """Nearest NAVIGABLE (row, col) to a real-world coordinate."""
        _, idx = self._tree.query([lat, lon * self._coslat])
        return tuple(self._cells[idx])

    def cell_latlon(self, row, col):
        return float(self.lats[row]), float(self.lons[col])

    def in_bounds(self, row, col):
        return 0 <= row < self.nlat and 0 <= col < self.nlon


def build_grid():
    """Build the navigable grid from bathymetry.npz and cache it."""
    b = np.load(C.BATHY_FILE)
    lats, lons, elevation = b["lats"], b["lons"], b["elevation"]

    # Deep-enough water: seafloor below -MIN_DEPTH_M (elevation is negative
    # under water). Everything else (land + shoals) is a barrier.
    deep = elevation <= -C.MIN_DEPTH_M
    barrier = ~deep

    # Distance (km) from each cell to the nearest barrier. sampling makes
    # the transform account for real km per cell in lat and lon.
    dlat_km = C.GRID_RES * C.KM_PER_DEG
    dlon_km = C.GRID_RES * C.KM_PER_DEG * float(np.cos(np.deg2rad(lats.mean())))
    dist_km = ndimage.distance_transform_edt(deep, sampling=[dlat_km, dlon_km])

    # Navigable = deep water at least COAST_BUFFER_KM from any barrier.
    navigable = deep & (dist_km >= C.COAST_BUFFER_KM)

    np.savez_compressed(
        C.GRID_FILE,
        lats=lats, lons=lons, elevation=elevation,
        navigable=navigable, dist_to_coast_km=dist_km.astype(np.float32),
    )
    n = int(navigable.sum())
    print(f"[grid] navigable cells: {n} / {navigable.size} "
          f"({100*n/navigable.size:.1f}%)  saved {C.GRID_FILE.name}")
    return Grid(lats, lons, elevation, navigable)


def load_grid():
    """Load the cached grid, building it if needed."""
    if not C.GRID_FILE.exists():
        return build_grid()
    g = np.load(C.GRID_FILE)
    return Grid(g["lats"], g["lons"], g["elevation"], g["navigable"])


if __name__ == "__main__":
    build_grid()
