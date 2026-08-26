# Nautilus: Optimal Ship Routing System

Nautilus is a weather-aware ship-routing system for vessels travelling around
India. It combines GEBCO bathymetry, ERA5 wave data, a navigable ocean grid,
Dijkstra's shortest-distance algorithm, weather-aware A* search, and a
machine-learning vessel-speed model.

The project provides two interfaces: a Streamlit application for local use
without a Google Maps API key, and a Flask application with a Google Maps web
interface and JSON API.

## What the system does

1. Extracts the region around India from the large NetCDF source files.
2. Downsamples the data to a practical routing grid.
3. Removes shallow water and cells close to the coast.
4. Builds typical and rough wave scenarios.
5. Trains or loads a vessel-speed model.
6. Compares a traditional Dijkstra route with the proposed weather-aware A*
	route.

The default region is latitude `0` to `27` N and longitude `50` to `100` E.
The default grid resolution is `0.05` degrees, approximately 5.5 km per cell.

## Features

- Safe routing based on bathymetry, minimum depth, and coast-buffer rules.
- Traditional shortest-distance routing using Dijkstra's algorithm.
- Weather-aware travel-time routing using A* and predicted vessel speed.
- Typical, rough, and live marine-weather scenarios.
- Flask web application with Google Maps visualization.
- Streamlit interface that does not require a Google Maps API key.
- Evaluation of proposed and traditional routes.

## Requirements

- Python 3.10 or newer
- Several GB of free disk space for the raw datasets
- Several GB of available memory for one-time weather extraction
- A Google Maps JavaScript API key only for the Flask map interface

Create and activate a virtual environment, then install the dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

On macOS or Linux, activate the environment with:

```bash
source .venv/bin/activate
```

## Datasets

The raw datasets are too large for GitHub and must be downloaded separately.
The project expects these files in the repository root:

| Purpose | Dataset | Required filename | Download |
| --- | --- | --- | --- |
| Bathymetry and depth safety mask | GEBCO 2024 sub-ice-topography NetCDF | `GEBCO_2024_sub_ice_topo.nc` | [Google Drive dataset 1](https://drive.google.com/file/d/1hOWit5p4TubLsOrbWnMeq9poyGdt2p24/view?usp=sharing) |
| Significant wave height, direction, and period | ERA5 wave NetCDF | `data_stream-wave_stepType-instant.nc` | [Google Drive dataset 2](https://drive.google.com/file/d/1uE4uSOUD5Bpslm-KvAuxNOCRaqsiXApH/view?usp=sharing) |

Direct download links:

- Dataset 1: https://drive.google.com/file/d/1hOWit5p4TubLsOrbWnMeq9poyGdt2p24/view?usp=sharing
- Dataset 2: https://drive.google.com/file/d/1uE4uSOUD5Bpslm-KvAuxNOCRaqsiXApH/view?usp=sharing

Place them here after downloading and renaming if necessary:

```text
Optimal ship routing system/
	GEBCO_2024_sub_ice_topo.nc
	data_stream-wave_stepType-instant.nc
```

Run the one-time preprocessing step:

```bash
python -m src.preprocess
```

This extracts only the configured region and creates `bathymetry.npz`,
`weather.npz`, and `weather_grid.csv` in `data/processed/`. The raw files are
not needed by the applications after preprocessing. Keep them if you plan to
change the region or grid resolution. The wave subset is loaded while
scenarios are calculated, so preprocessing can require several GB of memory.

## Running the Applications

### Flask and Google Maps interface

Set the API key in the environment. On Windows PowerShell:

```powershell
$env:GOOGLE_MAPS_API_KEY = "your-key"
python server.py
```

Open `http://localhost:8000`. Restrict the Google key to the local application
origin and to the Google Maps JavaScript API. Never store an API key in source
code or commit it to the repository.

The Flask server exposes:

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/meta` | Available ports, vessels, and region bounds |
| `GET` | `/api/weather?scenario=typical` | Weather overlay metadata |
| `GET` | `/api/weather_image?scenario=rough` | Wave overlay PNG |
| `POST` | `/api/route` | Calculate one or both routes |

Example route request in PowerShell:

```powershell
$body = @{
	origin = "Cochin (Kerala)"
	dest = "Dubai / Jebel Ali (UAE)"
	vessel = "General Cargo"
	scenario = "typical"
	algorithms = @("dijkstra", "astar")
	use_ml = $true
} | ConvertTo-Json

Invoke-RestMethod -Uri http://localhost:8000/api/route `
	-Method Post -ContentType "application/json" -Body $body
```

### Streamlit interface

```bash
streamlit run app.py
```

Open `http://localhost:8501`.

### Full pipeline and evaluation

```bash
python run_all.py
```

The command preprocesses raw data when processed files are missing, trains the
speed model when needed, and evaluates the rough-weather routes. Results are
written to `data/processed/evaluation.csv`.

To retrain the speed model independently:

```bash
python -m src.ml_model
```

The trained model is written to `data/processed/speed_model.joblib`.

## Repository Contents

```text
config.py                 Shared paths and routing parameters
web_config.py             Environment-based Flask settings
server.py                 Flask backend, static server, and JSON API
app.py                    Streamlit interface
run_all.py                End-to-end preprocessing, training, and evaluation
src/preprocess.py         NetCDF extraction and weather aggregation
src/grid.py               Navigable grid construction and loading
src/routing.py            Dijkstra and A* routing
src/weather.py            Processed weather loading
src/live_weather.py       Optional live weather support
src/ml_model.py           Speed-model training and inference
src/evaluate.py           Route comparison and metrics
src/ports.py              Port catalogue and coordinates
src/vessel.py             Vessel profiles
web/                      Flask frontend files
data/processed/           Generated routing and model artifacts
```

## Configuration

Edit `config.py` to change the geographic bounding box, grid resolution,
minimum water depth, coast buffer, vessel speed, or weather cost weights.
Changing the region or grid resolution requires rerunning preprocessing and
rebuilding the processed grid and model artifacts.

Important settings include `LAT_MIN`, `LAT_MAX`, `LON_MIN`, `LON_MAX`,
`GRID_RES`, `MIN_DEPTH_M`, `COAST_BUFFER_KM`, `SHIP_SPEED_KN`,
`W_WAVE_HEIGHT`, `W_HEAD_SEAS`, `W_PERIOD`, and `MAX_WEATHER_MULT`.

## Troubleshooting

**A raw NetCDF file is not found**

Check that the filename and location exactly match `config.py` and that the
download completed successfully.

**The application cannot load the grid or model**

Run `python -m src.preprocess`, then `python -m src.ml_model`, or run
`python run_all.py` to create the generated files.

**The Flask map is blank**

Set `GOOGLE_MAPS_API_KEY` in the same terminal used to start `server.py` and
confirm that the key enables the Google Maps JavaScript API.

**Preprocessing is slow**

This is expected for multi-gigabyte NetCDF files. The raw files are read only
during preprocessing; normal application startup uses `data/processed/`.

## Files Not Uploaded to GitHub

The following local files and directories are intentionally excluded:

- `GEBCO_2024_sub_ice_topo.nc` (approximately 7.4 GB)
- `data_stream-wave_stepType-instant.nc` (approximately 4.1 GB)
- `.claude/` local tooling configuration
- `__pycache__/` and compiled Python files
- `.env` and Streamlit secret files
- PDF and PowerPoint presentation files

The two NetCDF datasets exceed GitHub's 100 MB per-file limit and must be
stored locally or obtained from their respective data providers. The
processed artifacts in `data/processed/` are included to support normal
application use after cloning.

## Future Improvements

- Use forecast timestamps instead of time-averaged weather scenarios.
- Extend the routing region beyond the seas around India.
- Train the speed model with real AIS vessel data.
