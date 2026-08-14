# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

This is **not a software codebase** — it's an engineering data/design workspace for EGAT (Electricity Generating
Authority of Thailand) wave-energy buoy and dam hydrodynamic studies. It contains CAD models, ANSYS
simulation projects, raw simulation output, and a handful of standalone Python scripts used to post-process
that output into plots and Excel reports. There is no build system, package manifest, linter, or test suite.

Directory names are informal and project-specific (e.g. `bouy_files`, `awqa_dam`, `69-CHANA`, `2.9m`) —
they correspond to design iterations, water-depth/site studies, or ANSYS Workbench project names, not a
conventional source layout.

## File types you'll encounter

- **`.scdoc` / `.scdocx`** — ANSYS SpaceClaim 3D CAD models (buoy hull, ballast, top/bottom sections, rods).
- **`.wbpj` / `.agdb`** — ANSYS Workbench project files, paired with a `<name>_files/` companion directory
  containing `session_files/journal*.wbjn` (recorded Workbench macro/journal logs — useful for seeing what
  operations were performed in a session, e.g. `journalN.wbjn`, with `_crashed` suffixes marking sessions
  that didn't finish cleanly).
- **`.dwg` / `.IGS`** — AutoCAD drawings and IGES CAD exchange files (anchors, buildings, structures).
- **`.stl` / `.gcode` / `.3mf`** — 3D-print-ready meshes and sliced printer output for physical scale models.
- **AQWA CSV output** — raw time-series export from ANSYS AQWA hydrodynamic simulations (wave elevation,
  heave, mooring line tension, RX/RY/RZ rotation). These are the inputs to the Python scripts below.
- **`.xlsx`** — post-processed analysis results, typically produced by the scripts in this repo, containing
  a data sheet plus native Excel charts.
- **`.avi` / `.mp4`** — simulation/animation recordings (Workbench or AQWA visualizations).

## AQWA CSV data conventions

Raw AQWA export files use `*Time (s)` and generic `Line A/B/C (...)` column headers; the actual physical
quantity is only identifable from a metadata line above the data table (e.g. `Line A: ... Global Z ...` for
heave, `... Cable Tension ...` for a mooring line). The `graph.py` script parses this metadata to map
columns automatically.

Processed/derived CSVs and folders follow a `{H}m-{T}s-{quantity}.csv` naming convention, where `H` is
significant wave height (m) and `T` is wave period (s), e.g. `0.75m-3.0s-Heave.csv`,
`2.00m-5.0s-Tension.csv`. Study directories are often split into `Max/`, `Min/`, `Mean/` subfolders holding
the same case set for each statistic, sometimes further split by site/station (`pmp`, `snr`, `vrk`,
`template` under `awqa_dam/`).

## Python scripts

There is no `requirements.txt`. Scripts depend on `streamlit`, `pandas`, `matplotlib`, and `xlsxwriter`
(install ad hoc: `pip install streamlit pandas matplotlib xlsxwriter`). Each script is standalone — there's
no shared package or import between them, even though several are near-duplicates of each other evolved for
a specific study folder.

- **`awqa_dam/pmp/graph.py`** (and its launcher `awqa_dam/pmp/start.py`) — the main Streamlit app. Run with
  `streamlit run graph.py` (or `python start.py`, which just shells out to that). Accepts a single raw AQWA
  CSV export, auto-detects Wave/Heave/Tension/RX/RY/RZ columns from the file's metadata header, renders
  interactive plots, and exports a multi-chart `.xlsx` report.
- **`1111111111111111111111111111111111111111111111/csvplot.py`** — earlier variant of the same idea that
  takes three *separate* CSVs (wave, heave, tension) instead of one combined file. Run with
  `streamlit run csvplot.py`.
- **`csv 24032569/create_aqwa_csv.py`** — generates placeholder/skeleton case files for a fixed list of
  (H, T) wave conditions, used to scaffold a station's data folder before real AQWA results are dropped in.
- **`awqa_dam/pmp/Max/python make_excel.py`** and **`awqa_dam/pmp/Min/python make_excel.py`** (the space in
  the filename is intentional/literal) — batch-process a fixed list of per-case result CSVs in the current
  directory, compute Heave/Wave amplitude and RAO (Response Amplitude Operator) ratios after discarding the
  first 50s of transient response, and print a summary table. Run with `python "make_excel.py"` from inside
  the `Max`/`Min` folder.
- **`awqa_dam/pmp/Graph/ratio.py`** (and per-depth copies under `48.62/`, `71.88/`, `95.14/`) — glob-based
  batch analyzer: finds all `*wave*.csv` files in the current directory, groups the matching
  heave/tension/RX/RY/RZ files by case prefix, and skips any case missing one of the 6 expected file types.

When asked to modify one of these scripts, treat it in isolation — don't assume changes should propagate to
its near-duplicates in other folders unless asked, since each was tuned for a specific dataset/site.
