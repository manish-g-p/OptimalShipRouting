"""
Nautilus - web interface for the Optimal Ship Routing system.

Pick a vessel, an origin and a destination Indian port, a weather
scenario, and see the safe optimized route on an interactive map with a
wave overlay and per-point weather tooltips.

Routing:
  * Dijkstra          - shortest safe distance (traditional baseline)
  * Weather-aware A*  - ML speed model drives the cost (proposed system)

Run:  streamlit run app.py
"""
import numpy as np
import streamlit as st
import folium
from streamlit_folium import st_folium

import config as C
from src import (grid as G, weather as W, routing as R, ports as P,
                 vessel as V, ml_model as ML)

st.set_page_config(page_title="Nautilus - Ship Routing", page_icon="🧭",
                   layout="wide")


# ----------------------------------------------------------------------
# Cached loaders (each heavy object is built once and reused).
# ----------------------------------------------------------------------
@st.cache_resource(show_spinner="Loading ocean grid + ML model...")
def load_core():
    return G.load_grid(), ML.load()


@st.cache_resource(show_spinner="Loading weather scenario...")
def get_weather(scenario):
    grid, _ = load_core()
    return W.load_weather(grid, scenario)


@st.cache_resource(show_spinner="Building ML speed-cost surface...")
def get_multiplier(scenario, vessel_name):
    grid, model = load_core()
    w = get_weather(scenario)
    return ML.build_multiplier_grid(grid, w, V.get(vessel_name), model)


# ----------------------------------------------------------------------
# Map helpers
# ----------------------------------------------------------------------
def swh_overlay(grid, weather):
    swh = weather.swh
    vmax = max(0.5, float(np.nanpercentile(swh, 99)))
    t = np.clip(swh / vmax, 0, 1)
    rgba = np.zeros((*swh.shape, 4), dtype=np.float32)
    rgba[..., 0] = t
    rgba[..., 1] = 0.25
    rgba[..., 2] = 1.0 - t
    rgba[..., 3] = np.where(swh > 0.05, 0.40, 0.0)
    rgba = np.flipud(rgba)
    bounds = [[float(grid.lats.min()), float(grid.lons.min())],
              [float(grid.lats.max()), float(grid.lons.max())]]
    return folium.raster_layers.ImageOverlay(
        image=rgba, bounds=bounds, opacity=1.0, name="Wave height (overlay)")


def route_max_wave(weather, result):
    """Actual peak wave height (m) along a route, from the weather field.
    Needed because the Dijkstra router carries no weather of its own."""
    if not (result and result.found):
        return 0.0
    return round(max(float(weather.swh[r, c]) for r, c in result.cells), 2)


def draw_route(fmap, result, color, label):
    if result and result.found:
        folium.PolyLine(
            result.latlon, color=color, weight=4, opacity=0.9,
            tooltip=f"{label}: {result.distance_km} km, {result.time_hours} h",
        ).add_to(fmap)


def draw_weather_tooltips(fmap, result, weather, every=12):
    """Clickable markers along the route showing local wave conditions."""
    if not (result and result.found):
        return
    mwd = weather.mwd_deg()
    layer = folium.FeatureGroup(name="Weather tooltips")
    cells = result.cells
    for i in range(0, len(cells), every):
        r, c = cells[i]
        lat, lon = result.latlon[i]
        h = float(weather.swh[r, c])
        p = float(weather.mwp[r, c])
        d = float(mwd[r, c])
        popup = folium.Popup(
            f"<b>Wave conditions</b><br>Height: {h:.2f} m<br>"
            f"Period: {p:.1f} s<br>From: {d:.0f}°", max_width=200)
        color = "green" if h < 1.5 else "orange" if h < 3 else "red"
        folium.CircleMarker(
            [lat, lon], radius=4, color=color, fill=True, fill_opacity=0.9,
            popup=popup, tooltip=f"{h:.1f} m").add_to(layer)
    layer.add_to(fmap)


# ----------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------
st.title("🧭 Nautilus — Optimal Ship Routing")
st.caption("Pathfinding + geospatial constraints + ML over the seas around "
           "India (GEBCO bathymetry + ERA5 waves). 100% offline, no paid APIs.")

grid, model = load_core()
names = P.port_list()

with st.sidebar:
    st.header("Vessel")
    vessel_name = st.selectbox("Vessel type", V.vessel_list(),
                               index=V.vessel_list().index(V.DEFAULT_VESSEL))
    ves = V.get(vessel_name)
    st.caption(f"Service speed {ves.service_speed_kn} kn · "
               f"draft {ves.draft_m} m · length {ves.length_m} m")

    st.header("Voyage")
    origin = st.selectbox("Origin port", names,
                          index=names.index("Cochin (Kerala)"))
    dest = st.selectbox("Destination port", names,
                        index=names.index("Dubai / Jebel Ali (UAE)"))

    st.header("Weather scenario")
    scenario = st.radio("Sea state", ["typical", "rough"],
                        format_func=lambda s: "Typical (average)"
                        if s == "typical" else "Rough (simulated storm)")

    st.header("Algorithm")
    show_dijkstra = st.checkbox("Dijkstra (traditional, shortest)", value=True)
    show_astar = st.checkbox("Weather-aware A* (proposed)", value=True)
    use_ml = st.checkbox("Use ML speed model for A* cost", value=True)
    show_waves = st.checkbox("Wave overlay", value=True)
    show_tips = st.checkbox("Weather tooltips on route", value=True)
    go = st.button("🚢 Find route", type="primary", use_container_width=True)

if origin == dest:
    st.warning("Origin and destination are the same. Pick two different ports.")
    st.stop()

weather = get_weather(scenario)

center = [float(grid.lats.mean()), float(grid.lons.mean())]
fmap = folium.Map(location=center, zoom_start=5, tiles="CartoDB positron",
                  control_scale=True)
if show_waves:
    swh_overlay(grid, weather).add_to(fmap)

results = {}
if go:
    start = grid.nearest_cell(*P.coord(origin))
    goal = grid.nearest_cell(*P.coord(dest))

    if show_dijkstra:
        results["Dijkstra"] = R.Router(grid).search(start, goal, False, False)
    if show_astar:
        if use_ml:
            mult = get_multiplier(scenario, vessel_name)
            router_a = R.Router(grid, weather=weather, mult_dir=mult)
        else:
            router_a = R.Router(grid, weather=weather)
        results["A*"] = router_a.search(start, goal, True, True)

    draw_route(fmap, results.get("Dijkstra"), "#1f77b4", "Dijkstra")
    draw_route(fmap, results.get("A*"), "#d62728", "A* (weather-aware)")
    if show_tips and "A*" in results:
        draw_weather_tooltips(fmap, results["A*"], weather)
    elif show_tips and "Dijkstra" in results:
        draw_weather_tooltips(fmap, results["Dijkstra"], weather)

    olat, olon = grid.cell_latlon(*start)
    dlat, dlon = grid.cell_latlon(*goal)
    folium.Marker([olat, olon], tooltip=f"Origin: {origin}",
                  icon=folium.Icon(color="green", icon="play")).add_to(fmap)
    folium.Marker([dlat, dlon], tooltip=f"Destination: {dest}",
                  icon=folium.Icon(color="red", icon="stop")).add_to(fmap)
    fmap.fit_bounds([[olat, olon], [dlat, dlon]])

folium.LayerControl().add_to(fmap)

col_map, col_info = st.columns([3, 1])
with col_map:
    st_folium(fmap, width=None, height=600, returned_objects=[])

with col_info:
    st.subheader("Results")
    if not results:
        st.info("Set options and click **Find route**.")
    max_wave = {}
    for name, res in results.items():
        tag = "proposed" if name == "A*" else "traditional"
        if not res.found:
            st.error(f"{name}: no safe route found.")
            continue
        mw = route_max_wave(weather, res)      # measured on same weather
        max_wave[name] = mw
        st.markdown(f"**{name}** · _{tag}_")
        st.metric("Distance", f"{res.distance_km:,.0f} km")
        st.metric("Est. time", f"{res.time_hours:,.0f} h "
                                f"({res.time_hours/24:.1f} days)")
        st.metric("Max wave on route", f"{mw} m")
        st.caption(f"cells explored: {res.expanded:,}")
        st.divider()

    if all(k in results for k in ("Dijkstra", "A*")) \
            and results["Dijkstra"].found and results["A*"].found:
        dd = results["A*"].distance_km - results["Dijkstra"].distance_km
        wd = max_wave["Dijkstra"] - max_wave["A*"]
        if abs(dd) < 1 and abs(wd) < 0.05:
            st.caption("For this vessel and sea state, the ML cost finds the "
                       "shortest route is already the safest.")
        else:
            st.caption(f"A* trades {dd:+.0f} km to cut peak waves by "
                       f"{wd:+.2f} m — calmer, safer water.")

st.caption(f"Vessel: {vessel_name} · Scenario: {scenario} · "
           f"Region lat {C.LAT_MIN}-{C.LAT_MAX}N lon {C.LON_MIN}-{C.LON_MAX}E · "
           f"grid {grid.nlat}×{grid.nlon} @ {C.GRID_RES}° · "
           f"coast buffer {C.COAST_BUFFER_KM} km")
