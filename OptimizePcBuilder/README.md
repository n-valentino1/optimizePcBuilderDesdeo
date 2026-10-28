# optimizePCBuilder

This project contains the custom Python logic for a PC-builder optimization workflow that was made for a 2026 summer reserach experience at Ohio Northern University

The project is designed to work with the official DESDEO framework and its browser-based GUI. The GUI is provided by the official DESDEO project, not by custom JavaScript or TypeScript code in this repository.

## Project layout

- `main.py` - the only Python file in this repo; it contains the PC-builder logic and the DESDEO integration helpers
- `data/` - CSV files for motherboard, RAM, CPU, GPU, and SSD data
- `requirements.txt` - Python dependencies for this project

## One-click startup

This repo keeps only one startup file so it stays clean and easy to use:

- `start_everything.ps1` - starts the custom project, the DESDEO backend, and the official DESDEO browser GUI in one go

Run it from PowerShell:

```powershell
cd "C:\Users\25val\OneDrive\Desktop\optimizePCBuilder.worktrees\custom-gui-setup-desdeo-project"
.\start_everything.ps1
```

If PowerShell blocks the script, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\start_everything.ps1
```

## Recommended setup

Keep the official DESDEO repository in a sibling folder next to this project, for example:

- `C:/projects/DESDEO`
- `C:/projects/optimizePCBuilder`

This keeps your GitHub repo focused on your own project while still using the official DESDEO browser GUI.

## Install Python dependencies

```powershell
cd C:\projects\optimizePCBuilder
py -m venv .venv
. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Install DESDEO locally

```powershell
cd C:\projects
git clone https://github.com/industrial-optimization-group/DESDEO.git
cd DESDEO
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

## Create the DESDEO database (first run only)

`start_everything.ps1` does this automatically when `DESDEO\desdeo\api\test.db` is missing. To do it by hand:

```powershell
cd C:\projects\DESDEO\desdeo\api
. ..\..\.venv\Scripts\Activate.ps1
python db_init_pc_builder.py
python add_representative_for_pc_builder.py
```

The PC builder problem reads its CSVs from `OptimizePcBuilder\data` next to the DESDEO folder. If your CSVs live somewhere else, set `PC_BUILDER_DATA_DIR` to that folder first. The database always lives at `DESDEO\desdeo\api\test.db`, no matter which folder you start the API from.

## Start the DESDEO API

```powershell
cd C:\projects\DESDEO
. .\.venv\Scripts\Activate.ps1
uvicorn --app-dir=./desdeo/api/ app:app --reload
```

## Start the official DESDEO browser GUI

```powershell
cd C:\projects\DESDEO\webui
npm install
npm run dev -- --open
```

Then open:

```text
http://localhost:5173
```

## Running this project

```powershell
cd C:\projects\optimizePCBuilder
. .\.venv\Scripts\Activate.ps1
python main.py
```

## Notes

- If the PC-builder problem already exists in the local DESDEO database, you do not need to register it again.
- This repo is intentionally Python-only.
- The browser UI comes from the official DESDEO project, not from custom front-end code in this repo.