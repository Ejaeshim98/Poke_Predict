# Poke_Predict

Machine learning market prediction dashboard for Pokemon cards with a 30-day forecast.

## What this app does

- Ingests card market history from a CSV file.
- Cleans data and optionally removes outliers (IQR by card series and condition).
- Supports `daily` and `weekly` forecast granularity.
- Forecasts up to 30 future periods per card series.
- Produces a top-10 list of **unique cards** (no duplicate variants/conditions dominating the list).
- Exports top-10 CSV and a text summary report.

## Assumed target price

Because no single target was specified, the app uses:

- **Target price = robust market price proxy**
- Defined as the median observed price per resampled period (daily or weekly) after cleaning and optional outlier filtering.

This is a stable default and can be replaced later with true API market/last-sold fields.

## CSV input format

Required columns:

- `date`
- `card_name`
- `set_name`
- `card_number`
- `condition`
- `price`

Optional columns:

- `variant` (examples: First Edition, Shadowless, Unlimited)
- `expansion_code`

## Variant handling

- If `variant` exists, values are normalized (for example first edition/shadowless/unlimited).
- If missing/unknown, a lightweight inference runs from `card_number` pattern.
- Final identity key includes card + set + number + variant + condition.

## Run locally

1. Create and activate a Python environment.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Launch dashboard:
   - `streamlit run app.py`

## Non-technical launch (double-click)

For users who do not use command line:

- Double-click `Launch_PokePredict.bat`
- On first run, it automatically:
  - creates `.venv`
  - installs `requirements.txt`
  - opens the browser to `http://localhost:8501`

Note: Python 3.10+ must be installed on the machine.

## Next recommended upgrades

- Replace CSV upload with TCGplayer API ingestion once approved.
- Add stronger ML models (gradient boosting with lag/seasonality features).
- Add walk-forward backtesting and model promotion for continuous improvement.
