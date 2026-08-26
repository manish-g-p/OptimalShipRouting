# Optimal Ship Routing System

Nautilus is a weather-aware ship-routing system for the seas surrounding
India. It combines safe-water grid generation, Dijkstra's algorithm,
weather-aware A* routing, and a machine-learning vessel-speed model.

## Features

- Safe routing based on bathymetry, minimum depth, and coast-buffer rules.
- Traditional shortest-distance routing using Dijkstra's algorithm.
- Weather-aware travel-time routing using A* and predicted vessel speed.
- Typical, rough, and live marine-weather scenarios.
- Flask web application with Google Maps visualization.
- Streamlit interface that does not require a Google Maps API key.
- Evaluation of proposed and traditional routes.

## Requirements

Python 3.10 or later is recommended. Install the dependencies with:

```bash
pip install -r requirements.txt
```

## Data Preparation

The raw GEBCO bathymetry and wave NetCDF files are not included in this
repository because of their size. Obtain the required source datasets and
place them in the project root with the filenames expected by `config.py`.
Then run:

```bash
python -m src.preprocess
```

This generates the processed bathymetry, weather, grid, and evaluation
artifacts in `data/processed/`.

## Running the Applications

### Flask and Google Maps interface

Set the API key in the environment. On Windows PowerShell:

```powershell
$env:GOOGLE_MAPS_API_KEY = "your-key"
python server.py
```

Open `http://localhost:8000`. Restrict the Google key to the local
application origin and to the Google Maps JavaScript API. Never store an API
key in source code or commit it to the repository.

### Streamlit interface

```bash
streamlit run app.py
```

Open `http://localhost:8501`.

### Full pipeline and evaluation

```bash
python run_all.py
```

To retrain the speed model independently:

```bash
python -m src.ml_model
```

## Repository Contents

```text
config.py            Application and routing configuration
web_config.py        Environment-based API key configuration
server.py            Flask backend and routing API
app.py               Streamlit interface
run_all.py           End-to-end pipeline and evaluation runner
src/                 Data processing, routing, weather, and model modules
web/                 Front-end files for the Flask application
data/processed/      Generated routing and model artifacts
```

## Configuration

Edit `config.py` to change the geographic bounding box, grid resolution,
minimum water depth, coast buffer, vessel speed, or weather cost weights.

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
