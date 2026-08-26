"""
Nautilus backend - Flask API + static server for the polished web app.

Loads the routing engine ONCE at startup and exposes:
  GET  /                 -> the web app (Google Maps key injected)
  GET  /api/meta         -> ports + vessels
  GET  /api/weather      -> wave heatmap points for a scenario
  POST /api/route        -> compute Dijkstra + weather-aware A* routes

Run:  python server.py   (then open http://localhost:8000)
"""
import io
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
from matplotlib import colormaps, image as mpimg
from flask import (Flask, jsonify, request, send_from_directory, Response,
                   send_file)

import config as C
import web_config as WC
from src import (grid as G, weather as W, routing as R, ports as P,
                 vessel as V, ml_model as ML, live_weather as LW)

WEB = Path(__file__).resolve().parent / "web"
app = Flask(__name__)

# ----------------------------------------------------------------------
# Load heavy objects once, then cache derived fields.
# ----------------------------------------------------------------------
print("[server] loading grid + ML model...")
GRID = G.load_grid()
MODEL = ML.load()
DIST_COAST = np.load(C.GRID_FILE)["dist_to_coast_km"]
_weather_cache = {}
_mult_cache = {}
print("[server] ready.")


def get_weather(scenario):
    if scenario == "live":
        return LW.build_live_weather(GRID)          # module-cached ~5 min
    if scenario not in _weather_cache:
        _weather_cache[scenario] = W.load_weather(GRID, scenario)
    return _weather_cache[scenario]


def get_multiplier(scenario, vessel_name, weather):
    if scenario == "live":                          # live changes -> no cache
        return ML.build_multiplier_grid(GRID, weather, V.get(vessel_name), MODEL)
    key = (scenario, vessel_name)
    if key not in _mult_cache:
        _mult_cache[key] = ML.build_multiplier_grid(
            GRID, weather, V.get(vessel_name), MODEL)
    return _mult_cache[key]


def route_waves(weather, res):
    swh = [float(weather.swh[r, c]) for r, c in res.cells]
    return round(max(swh), 2), round(float(np.mean(swh)), 2)


def waypoints(weather, res, every=12):
    mwd = weather.mwd_deg()
    out = []
    for i in range(0, len(res.cells), every):
        r, c = res.cells[i]
        lat, lon = res.latlon[i]
        out.append({"lat": lat, "lon": lon,
                    "swh": round(float(weather.swh[r, c]), 2),
                    "mwp": round(float(weather.mwp[r, c]), 1),
                    "mwd": round(float(mwd[r, c]))})
    return out


def result_json(weather, res):
    if not res.found:
        return {"found": False}
    mx, mean = route_waves(weather, res)
    min_coast = round(float(min(DIST_COAST[r, c] for r, c in res.cells)), 1)
    return {
        "found": True,
        "path": [[la, lo] for la, lo in res.latlon],
        "distance_km": res.distance_km,
        "time_hours": res.time_hours,
        "max_wave_m": mx,
        "mean_wave_m": mean,
        "min_coast_km": min_coast,
        "expanded": res.expanded,
        "waypoints": waypoints(weather, res),
    }


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------
@app.route("/")
def index():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    html = html.replace("__MAPS_KEY__", WC.GOOGLE_MAPS_API_KEY)
    return Response(html, mimetype="text/html")


@app.route("/<path:fname>")
def static_files(fname):
    return send_from_directory(WEB, fname)


@app.route("/api/meta")
def meta():
    return jsonify({
        "ports": [{"name": n, "lat": P.PORTS[n][0], "lon": P.PORTS[n][1]}
                  for n in P.port_list()],
        "vessels": [{"name": v.name, "speed": v.service_speed_kn,
                     "draft": v.draft_m, "length": v.length_m}
                    for v in V.VESSELS.values()],
        "region": {"lat_min": C.LAT_MIN, "lat_max": C.LAT_MAX,
                   "lon_min": C.LON_MIN, "lon_max": C.LON_MAX},
    })


_TURBO = colormaps["turbo"]


@app.route("/api/weather")
def weather_layer():
    """Return legend max + region bounds for the wave overlay image."""
    scenario = request.args.get("scenario", "typical")
    try:
        w = get_weather(scenario)
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    vmax = max(0.5, float(np.nanpercentile(w.swh, 99)))
    return jsonify({
        "max": round(vmax, 2),
        "bounds": {"north": C.LAT_MAX, "south": C.LAT_MIN,
                   "east": C.LON_MAX, "west": C.LON_MIN},
    })


@app.route("/api/weather_image")
def weather_image():
    """Render the wave field as a semi-transparent PNG (GroundOverlay)."""
    scenario = request.args.get("scenario", "typical")
    try:
        w = get_weather(scenario)
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    swh = w.swh
    vmax = max(0.5, float(np.nanpercentile(swh, 99)))
    t = np.clip(swh / vmax, 0, 1)
    rgba = _TURBO(t)                                  # (nlat, nlon, 4)
    alpha = np.where((swh > 0.05) & GRID.navigable, 0.58, 0.0)

    # Feather the outer cells so the data-box edges fade out smoothly
    # instead of showing a hard rectangle over open ocean.
    ny, nx = swh.shape
    b = 22
    ramp = np.linspace(0.0, 1.0, b)
    fade = np.ones((ny, nx), dtype=np.float32)
    fade[:b, :] *= ramp[:, None];  fade[-b:, :] *= ramp[::-1, None]
    fade[:, :b] *= ramp[None, :];  fade[:, -b:] *= ramp[None, ::-1]
    rgba[..., 3] = alpha * fade
    rgba = np.flipud(rgba)                            # north at top
    buf = io.BytesIO()
    mpimg.imsave(buf, rgba, format="png")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.route("/api/route", methods=["POST"])
def api_route():
    body = request.get_json(force=True)
    origin = body["origin"]
    dest = body["dest"]
    vessel_name = body.get("vessel", V.DEFAULT_VESSEL)
    scenario = body.get("scenario", "typical")
    use_ml = bool(body.get("use_ml", True))
    algos = body.get("algorithms", ["dijkstra", "astar"])

    if origin == dest:
        return jsonify({"error": "Origin and destination are the same."}), 400
    if origin not in P.PORTS or dest not in P.PORTS:
        return jsonify({"error": "Unknown port."}), 400

    try:
        weather = get_weather(scenario)
    except Exception as e:
        return jsonify({"error": f"Live weather unavailable: {e}"}), 502

    start = GRID.nearest_cell(*P.coord(origin))
    goal = GRID.nearest_cell(*P.coord(dest))

    out = {
        "origin": {"name": origin, "lat": GRID.cell_latlon(*start)[0],
                   "lon": GRID.cell_latlon(*start)[1]},
        "dest": {"name": dest, "lat": GRID.cell_latlon(*goal)[0],
                 "lon": GRID.cell_latlon(*goal)[1]},
        "scenario": scenario, "vessel": vessel_name,
    }

    if "dijkstra" in algos:
        rd = R.Router(GRID).search(start, goal, False, False)
        out["dijkstra"] = result_json(weather, rd)
    if "astar" in algos:
        if use_ml:
            mult = get_multiplier(scenario, vessel_name, weather)
            router = R.Router(GRID, weather=weather, mult_dir=mult)
        else:
            router = R.Router(GRID, weather=weather)
        ra = router.search(start, goal, True, True)
        out["astar"] = result_json(weather, ra)

    return jsonify(out)


if __name__ == "__main__":
    print(f"[server] http://localhost:{WC.PORT}")
    app.run(host="127.0.0.1", port=WC.PORT, debug=False, threaded=True)
