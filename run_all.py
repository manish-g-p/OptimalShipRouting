"""
One-shot pipeline runner (no UI): shrink data -> train model -> evaluate.

Handy for generating results for the report without opening the web app.

    python run_all.py
"""
import config as C
from src import ml_model as ML, evaluate as E


def main():
    # Step 1: shrink raw data if not already done.
    if not (C.BATHY_FILE.exists() and C.WEATHER_FILE.exists()):
        from src import preprocess
        preprocess.main()

    # Step 2: train the ML speed model if not already done.
    if not C.ML_MODEL_FILE.exists():
        ML.train()

    # Step 3: evaluate proposed (A*+ML) vs traditional (Dijkstra).
    E.run(scenario="rough", vessel_name="General Cargo")


if __name__ == "__main__":
    main()
