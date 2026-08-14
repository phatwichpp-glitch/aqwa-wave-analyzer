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

## Build a standalone Windows .exe

For running on machines without Python installed. Uses [`streamlit-desktop-app`](https://pypi.org/project/streamlit-desktop-app/)
(wraps the app with [pywebview](https://pywebview.flowrl.com/) so it opens as a native window instead of a
browser tab) plus PyInstaller.

```bash
pip install -r requirements.txt pyinstaller streamlit-desktop-app
python build_exe.py
```

Output: `dist/AQWA_Wave_Analyzer.exe` (a single ~100 MB file — everything, including the Python runtime, is
bundled in). Copy that one file to any Windows machine and double-click to run; no install step needed.

**If building from a conda environment**, `build_exe.py` auto-detects and bundles the DLLs
(`libexpat.dll`, `liblzma.dll`, `libbz2.dll`, `ffi.dll`, `sqlite3.dll`) that conda keeps under
`<env>/Library/bin` instead of next to `python.exe` — without this the frozen exe crashes on startup with
`DLL load failed while importing pyexpat` (or lzma/bz2/ctypes/sqlite3). Building from a plain python.org
install shouldn't need this, but if you hit the same error there, locate the missing DLL and add it via
`--add-binary "<path>;."` in `build_exe.py`.

The exe embeds the app as it existed at build time — rebuild and redistribute it after changing `app.py`.
