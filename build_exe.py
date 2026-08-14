"""Build a standalone Windows .exe (no Python required on the target machine).

Usage (from a Python env with streamlit, pandas, plotly, xlsxwriter,
pyinstaller, and streamlit-desktop-app installed):

    python build_exe.py

Output: dist/AQWA_Wave_Analyzer.exe

Notes:
- If your Python environment is a conda env, some stdlib extension modules
  (pyexpat, _lzma, _bz2, _ctypes, _sqlite3) dynamically link to DLLs that live
  under <env>/Library/bin instead of next to python.exe. PyInstaller can't
  find them automatically, which crashes the frozen exe at startup with
  "DLL load failed while importing pyexpat" (or lzma/bz2/ctypes/sqlite3).
  This script detects a conda env and bundles those DLLs explicitly.
- xlsxwriter is loaded dynamically by pandas (via `engine="xlsxwriter"`
  string, not a literal `import xlsxwriter`), so PyInstaller's static
  analysis never sees it. It must be forced in as a hidden import.
"""
import os
import sys

from streamlit_desktop_app.build import build_executable

APP_NAME = "AQWA_Wave_Analyzer"
SCRIPT = os.path.join(os.path.dirname(__file__), "app.py")

pyinstaller_options = [
    "--onefile",
    "--noconfirm",
    "--clean",
    "--hidden-import", "xlsxwriter",
    "--collect-all", "plotly",
]

conda_prefix = sys.prefix
lib_bin = os.path.join(conda_prefix, "Library", "bin")
if os.path.isdir(lib_bin):
    for dll in ("libexpat.dll", "liblzma.dll", "libbz2.dll", "ffi.dll", "sqlite3.dll"):
        dll_path = os.path.join(lib_bin, dll)
        if os.path.isfile(dll_path):
            pyinstaller_options.extend(["--add-binary", f"{dll_path};."])

if __name__ == "__main__":
    print("PyInstaller options:", pyinstaller_options)
    build_executable(
        script_path=SCRIPT,
        name=APP_NAME,
        pyinstaller_options=pyinstaller_options,
    )
