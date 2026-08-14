# AQWA Wave Analyzer

Streamlit app for analyzing ANSYS AQWA time-series output (wave elevation, heave, mooring line tension,
and RX/RY/RZ rotation). Upload a raw AQWA CSV export and it auto-detects the columns from the file's
metadata header, renders interactive Plotly plots, computes RAO/steady-state statistics, and exports a
multi-chart Excel report.

**Features:**
- Auto-detects columns from AQWA's metadata header (`Line X: ...` description lines)
- Supports multiple mooring lines (each Tension line is kept separate, not overwritten)
- Works with partial data — plots/exports whatever variables are present, doesn't require all 6
- Interactive Plotly charts (zoom/pan/hover) instead of static images
- RAO and steady-state amplitude/statistics summary with an adjustable transient-cutoff slider
- Data-quality panel showing unmatched columns, dropped rows, and NaN counts
- Native Excel charts in the exported `.xlsx`, plus a `Summary_Stats` sheet

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

(or `python start.py`, which does the same thing)

## Deploy on Streamlit Community Cloud

1. Push this repo to GitHub (already done if you're reading this from the deployed app).
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in, and click **New app**.
3. Pick this repo/branch and set the main file path to `app.py`.
4. Deploy.
