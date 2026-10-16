# Bimmer Diagnostics

Desktop and CLI helper for BMW diagnostics on Windows.

Project focus:
- OBD-II quick checks (DTC read/clear, live data),
- BMW diagnostics via EDIABAS (module jobs, profile scans),
- GUI workflow with vehicle selection, scan screen, and history screen.

## What is implemented

- OBD commands:
	- `scan` (read DTC)
	- `clear --yes` (clear DTC)
	- `live` (stream common PIDs)
	- `--simulate` mode for offline testing
- BMW/EDIABAS commands:
	- `doctor-bmw` (installation/config check)
	- `toggle-bmw-sim on|off` (simulation flag in EDIABAS.INI)
	- `modules-bmw` (list local SGBD modules from ECU/*.prg)
	- `bmw-job` (single ECU job)
	- `scan-bmw` (same job over multiple modules)
	- `profiles-bmw` (list available profiles)
	- `profile-scan-bmw` (profile-based scan)
- Profile system:
	- curated profiles (hand-tuned)
	- auto-generated profiles per vehicle (`auto-quick`, `auto-full`)
- GUI (Tkinter):
	- Start screen (vehicle selection + detect via OBD)
	- Scan screen (vehicle-specific profile scan + single job)
	- History screen (saved reports)
- JSON reports under `reports/` with timestamps.

## Requirements

- Windows
- Python 3.11+
- OBD adapter/cable and drivers
- For BMW deep diagnostics: BMW Standard Tools / EDIABAS installed (for example under `C:\EDIABAS`)

## Setup (venv)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -r requirements.txt
```

Without activation:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Quick start (CLI)

```powershell
.\.venv\Scripts\python.exe -m src.bimmer_diag info
.\.venv\Scripts\python.exe -m src.bimmer_diag scan --port COM3
.\.venv\Scripts\python.exe -m src.bimmer_diag live --port COM3 --pids rpm,speed,coolant_temp
.\.venv\Scripts\python.exe -m src.bimmer_diag clear --port COM3 --yes
```

Offline simulation:

```powershell
.\.venv\Scripts\python.exe -m src.bimmer_diag scan --simulate
.\.venv\Scripts\python.exe -m src.bimmer_diag live --simulate --samples 5
```

## BMW diagnostics usage

Check EDIABAS configuration:

```powershell
.\.venv\Scripts\python.exe -m src.bimmer_diag doctor-bmw
```

List available modules:

```powershell
.\.venv\Scripts\python.exe -m src.bimmer_diag modules-bmw --filter N62
```

Run single ECU job:

```powershell
.\.venv\Scripts\python.exe -m src.bimmer_diag bmw-job --ecu EHC2RR4 --job STATUS_LESEN --json --lang en
```

Run scan over chosen modules:

```powershell
.\.venv\Scripts\python.exe -m src.bimmer_diag scan-bmw --modules EHC2RR4,T_GRTB --job STATUS_LESEN --json
```

List profiles and run profile scan:

```powershell
.\.venv\Scripts\python.exe -m src.bimmer_diag profiles-bmw
.\.venv\Scripts\python.exe -m src.bimmer_diag profile-scan-bmw --profile e60-550i-n62b48 --json --lang en
```

Save report to file:

```powershell
.\.venv\Scripts\python.exe -m src.bimmer_diag profile-scan-bmw --profile e60-550i-n62b48 --out reports\my_report.json
```

## GUI usage

Run GUI:

```powershell
.\.venv\Scripts\python.exe -m src.bimmer_diag.gui
```

Recommended flow:
1. Start screen:
	 - select vehicle manually or click Detect via OBD,
	 - review module groups.
2. Open Scan Screen:
	 - choose profile (curated or auto-generated),
	 - run profile scan or single job.
3. Open History Screen:
	 - filter and load previous JSON reports.

## How vehicle/profile mapping works

- Known vehicles are defined in `vehicle_catalog.py` with grouped modules.
- Curated profiles are defined in `bmw_profiles.py`.
- Service layer automatically adds generated profiles for each vehicle:
	- `...-auto-quick` (one representative module per group)
	- `...-auto-full` (all modules from grouped map)
- Detect via OBD reads VIN:
	- known VIN mapping -> known vehicle entry,
	- unknown BMW VIN -> runtime vehicle entry and generated profiles.

## Important limitations

- OBD-II is universal but limited (mainly emissions/powertrain DTCs).
- BMW deep diagnostics quality depends on EDIABAS/SGBD and correct cable/config.
- For unknown BMW, runtime module set is heuristic and may include modules not physically present in a specific car.
