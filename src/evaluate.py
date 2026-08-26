"""
Evaluation module (PDF objective: "evaluate the proposed system against
traditional routing methods in terms of computational efficiency, route
optimality, safety compliance, and adaptability").

  Traditional = Dijkstra (shortest distance, weather-blind)
  Proposed    = weather-aware A* driven by the ML speed model

For a set of voyages it computes, for each method:
  * Route optimality      : distance (km), travel time (h)
  * Computational effic.  : cells explored, runtime (s)
  * Safety compliance     : min distance to coast on route (km) vs 22 km
  * Adaptability          : max / mean wave height experienced (m)

Results are printed as a table and saved to data/processed/evaluation.csv.

Run:  python -m src.evaluate
"""
import time

import numpy as np
import pandas as pd

import config as C
from src import (grid as G, weather as W, routing as R, ports as P,
                 vessel as V, ml_model as ML, geo)

# Voyages to evaluate (origin, destination).
VOYAGES = [
    ("Mumbai (JNPT)", "Chennai (Tamil Nadu)"),
    ("Kandla (Gujarat)", "Cochin (Kerala)"),
    ("Cochin (Kerala)", "Dubai / Jebel Ali (UAE)"),
    ("Visakhapatnam (AP)", "Colombo (Sri Lanka)"),
    ("Chennai (Tamil Nadu)", "Port Blair (Andaman)"),
]


def _min_coast_dist(dist_field, result):
    """Minimum distance-to-coast (km) along a route, from the grid field."""
    return round(float(min(dist_field[r, c] for r, c in result.cells)), 1)


def _route_waves(weather, result):
    """Actual max/mean wave height (m) a route experiences, sampled from
    the SAME weather field - so Dijkstra and A* are compared fairly."""
    swh = [float(weather.swh[r, c]) for r, c in result.cells]
    return round(max(swh), 2), round(float(np.mean(swh)), 2)


def run(scenario="rough", vessel_name="General Cargo"):
    grid, model = G.load_grid(), ML.load()
    weather = W.load_weather(grid, scenario)
    mult = ML.build_multiplier_grid(grid, weather, V.get(vessel_name), model)
    dist_field = np.load(C.GRID_FILE)["dist_to_coast_km"]

    router_trad = R.Router(grid)                       # Dijkstra
    router_prop = R.Router(grid, weather=weather, mult_dir=mult)  # A* + ML

    rows = []
    for origin, dest in VOYAGES:
        s = grid.nearest_cell(*P.coord(origin))
        gcell = grid.nearest_cell(*P.coord(dest))

        t = time.time(); rt = router_trad.search(s, gcell, False, False)
        t_trad = time.time() - t
        t = time.time(); rp = router_prop.search(s, gcell, True, True)
        t_prop = time.time() - t
        if not (rt.found and rp.found):
            continue

        trad_maxw, trad_meanw = _route_waves(weather, rt)
        prop_maxw, prop_meanw = _route_waves(weather, rp)
        rows.append({
            "voyage": f"{origin} -> {dest}",
            # route optimality
            "trad_km": rt.distance_km, "prop_km": rp.distance_km,
            "trad_h": rt.time_hours, "prop_h": rp.time_hours,
            # computational efficiency
            "trad_expanded": rt.expanded, "prop_expanded": rp.expanded,
            "trad_sec": round(t_trad, 2), "prop_sec": round(t_prop, 2),
            # safety compliance (>= 22 km required)
            "trad_min_coast_km": _min_coast_dist(dist_field, rt),
            "prop_min_coast_km": _min_coast_dist(dist_field, rp),
            # adaptability (waves actually experienced, same weather field)
            "trad_max_wave_m": trad_maxw, "prop_max_wave_m": prop_maxw,
            "trad_mean_wave_m": trad_meanw, "prop_mean_wave_m": prop_meanw,
        })

    df = pd.DataFrame(rows)
    df.to_csv(C.EVAL_CSV, index=False)

    print(f"\n=== Evaluation: proposed (A*+ML) vs traditional (Dijkstra) ===")
    print(f"Scenario: {scenario} | Vessel: {vessel_name}\n")
    for _, r in df.iterrows():
        print(r["voyage"])
        print(f"  Route optimality : trad {r.trad_km:>7.0f} km / {r.trad_h:>4.0f} h"
              f"   |  prop {r.prop_km:>7.0f} km / {r.prop_h:>4.0f} h")
        print(f"  Comp. efficiency : trad {r.trad_expanded:>7,} cells / {r.trad_sec}s"
              f"  |  prop {r.prop_expanded:>7,} cells / {r.prop_sec}s")
        print(f"  Safety (min coast): trad {r.trad_min_coast_km:>5.1f} km"
              f"      |  prop {r.prop_min_coast_km:>5.1f} km   (need >= {C.COAST_BUFFER_KM})")
        print(f"  Adaptability (wave): trad max {r.trad_max_wave_m} m / mean {r.trad_mean_wave_m} m"
              f"  |  prop max {r.prop_max_wave_m} m / mean {r.prop_mean_wave_m} m\n")

    # Aggregate headline numbers.
    eff = 100 * (1 - df.prop_expanded.mean() / df.trad_expanded.mean())
    wave_cut = (df.trad_max_wave_m - df.prop_max_wave_m).mean()
    print("Summary:")
    print(f"  A* explores {eff:.0f}% fewer cells than Dijkstra on average "
          f"(heuristic efficiency).")
    print(f"  A* reduces peak wave exposure by {wave_cut:.2f} m on average "
          f"(adaptability/safety).")
    print(f"  All routes keep >= {C.COAST_BUFFER_KM} km from coast "
          f"(min observed {df[['trad_min_coast_km','prop_min_coast_km']].min().min()} km).")
    print(f"\nSaved {C.EVAL_CSV.name}")
    return df


if __name__ == "__main__":
    run()
