"""
Routing engine on the navigable grid (8-connected / king moves).

  * dijkstra : shortest SAFE route by pure great-circle distance (baseline)
  * astar    : weather-aware optimal route (distance x wave-cost), with an
               admissible great-circle heuristic so it stays optimal.

Speed: a Router precomputes per-row step distances and per-cell weather
multipliers once, so the search hot loop is just array look-ups. Both
algorithms then finish in a fraction of a second on a laptop.
"""
import heapq
from dataclasses import dataclass, field

import numpy as np

import config as C
from src import geo

# 8-neighbour offsets (row, col)
_OFF = [(-1, -1), (-1, 0), (-1, 1),
        (0, -1),           (0, 1),
        (1, -1),  (1, 0),  (1, 1)]


@dataclass
class RouteResult:
    algorithm: str
    found: bool
    cells: list = field(default_factory=list)      # [(row, col), ...]
    latlon: list = field(default_factory=list)     # [(lat, lon), ...]
    distance_km: float = 0.0
    time_hours: float = 0.0
    max_wave_m: float = 0.0
    mean_wave_m: float = 0.0
    expanded: int = 0                               # cells explored (cost proxy)


class Router:
    """Holds the grid + precomputed costs and runs the searches."""

    def __init__(self, grid, weather=None, mult_dir=None):
        """mult_dir (nlat,nlon,8), if given, overrides the analytic weather
        multiplier - used to plug in the ML speed-based cost."""
        self.grid = grid
        self.weather = weather
        self.nlat, self.nlon = grid.nlat, grid.nlon
        self.nav = grid.navigable.ravel()
        self.lats = grid.lats
        self.lons = grid.lons
        self._coslat0 = float(np.cos(np.deg2rad(grid.lats.mean())))

        # Per-row, per-direction step distance (km). Depends only on the
        # latitude of the FROM row and the (dr, dc) offset, not on longitude.
        res = C.GRID_RES
        self.dist_dir = np.zeros((self.nlat, 8), dtype=np.float64)
        self.head_dir = np.zeros((self.nlat, 8), dtype=np.float64)
        for r in range(self.nlat):
            la = grid.lats[r]
            for k, (dr, dc) in enumerate(_OFF):
                r2 = min(max(r + dr, 0), self.nlat - 1)
                la2 = grid.lats[r2] if r2 != r else la + dr * res
                self.dist_dir[r, k] = geo.haversine_km(la, 0.0, la2, dc * res)
                self.head_dir[r, k] = geo.bearing_deg(la, 0.0, la2, dc * res)

        # Per-cell, per-direction weather multiplier.
        #   * mult_dir passed in  -> ML speed-based cost (preferred)
        #   * else weather given  -> analytic wave multiplier
        if mult_dir is not None:
            self.mult_dir = mult_dir
        elif weather is not None:
            self.mult_dir = self._build_multipliers(weather)
        else:
            self.mult_dir = None

    def _build_multipliers(self, w):
        wave_from = w.mwd_deg()                     # (nlat, nlon)
        period_pen = np.clip((8.0 - w.mwp) / 8.0, 0.0, None)
        base = 1.0 + C.W_WAVE_HEIGHT * w.swh + C.W_PERIOD * period_pen
        mult = np.empty((self.nlat, self.nlon, 8), dtype=np.float32)
        for k in range(8):
            theta = np.deg2rad(self.head_dir[:, k][:, None] - wave_from)
            head_factor = (1.0 + np.cos(theta)) / 2.0
            m = base + C.W_HEAD_SEAS * w.swh * head_factor
            mult[:, :, k] = np.clip(m, 1.0, C.MAX_WEATHER_MULT)
        return mult

    # -- heuristic ------------------------------------------------------
    def _heuristic(self, r, c, glat, glon):
        # Fast equirectangular distance, scaled <1 so it never overestimates
        # the true great-circle remaining cost (keeps A* optimal).
        dlat = (self.lats[r] - glat) * C.KM_PER_DEG
        dlon = (self.lons[c] - glon) * C.KM_PER_DEG * self._coslat0
        return 0.999 * np.hypot(dlat, dlon)

    # -- core search ----------------------------------------------------
    def search(self, start, goal, use_weather, use_heuristic):
        nlon = self.nlon
        nav = self.nav
        dist_dir = self.dist_dir
        mult_dir = self.mult_dir if use_weather else None

        N = self.nlat * nlon
        g_score = np.full(N, np.inf)
        came = np.full(N, -1, dtype=np.int64)
        visited = np.zeros(N, dtype=bool)

        s_idx = start[0] * nlon + start[1]
        g_idx = goal[0] * nlon + goal[1]
        glat, glon = self.lats[goal[0]], self.lons[goal[1]]

        g_score[s_idx] = 0.0
        pq = [(0.0, 0.0, s_idx)]
        expanded = 0

        while pq:
            f, g, idx = heapq.heappop(pq)
            if visited[idx]:
                continue
            visited[idx] = True
            expanded += 1
            if idx == g_idx:
                return self._finalize(came, g_idx, use_weather, expanded)

            r, c = divmod(idx, nlon)
            for k, (dr, dc) in enumerate(_OFF):
                nr, nc = r + dr, c + dc
                if nr < 0 or nr >= self.nlat or nc < 0 or nc >= nlon:
                    continue
                nidx = nr * nlon + nc
                if not nav[nidx] or visited[nidx]:
                    continue
                cost = dist_dir[r, k]
                if mult_dir is not None:
                    cost *= mult_dir[r, c, k]
                ng = g + cost
                if ng < g_score[nidx]:
                    g_score[nidx] = ng
                    came[nidx] = idx
                    h = self._heuristic(nr, nc, glat, glon) if use_heuristic else 0.0
                    heapq.heappush(pq, (ng + h, ng, nidx))

        return RouteResult(algorithm="A*" if use_weather else "Dijkstra",
                           found=False, expanded=expanded)

    def _finalize(self, came, g_idx, use_weather, expanded):
        nlon = self.nlon
        idx = g_idx
        path = []
        while idx != -1:
            path.append(divmod(idx, nlon))
            idx = came[idx]
        path.reverse()

        latlon = [(float(self.lats[r]), float(self.lons[c])) for r, c in path]
        dist = 0.0
        for (la1, lo1), (la2, lo2) in zip(latlon, latlon[1:]):
            dist += float(geo.haversine_km(la1, lo1, la2, lo2))

        if use_weather and self.weather is not None:
            waves = [float(self.weather.swh[r, c]) for r, c in path]
        else:
            waves = [0.0]

        speed_kmh = C.SHIP_SPEED_KN * 1.852
        return RouteResult(
            algorithm="A*" if use_weather else "Dijkstra",
            found=True, cells=path, latlon=latlon,
            distance_km=round(dist, 1),
            time_hours=round(dist / speed_kmh, 1),
            max_wave_m=round(max(waves), 2),
            mean_wave_m=round(float(np.mean(waves)), 2),
            expanded=expanded,
        )


# -- module-level convenience API ---------------------------------------
def dijkstra(grid, start, goal):
    return Router(grid).search(start, goal, use_weather=False, use_heuristic=False)


def astar(grid, weather, start, goal):
    return Router(grid, weather).search(start, goal, use_weather=True, use_heuristic=True)


def route_between(grid, weather, start_latlon, goal_latlon, algorithm="astar"):
    """Snap coordinates to sea cells and run an algorithm."""
    start = grid.nearest_cell(*start_latlon)
    goal = grid.nearest_cell(*goal_latlon)
    if algorithm == "dijkstra":
        return dijkstra(grid, start, goal)
    return astar(grid, weather, start, goal)
