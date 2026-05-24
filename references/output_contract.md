# Output Contract

This file defines the stable interface for `scripts/run_dispatch.py`.
JSON schemas are stored in `schemas/input_schema.json` and `schemas/output_schema.json`.

## Config JSON

Minimal shape:

```json
{
  "units": {
    "load": "MW",
    "power": "MW",
    "energy": "MWh",
    "emission_factor": "tCO2/MWh"
  },
  "columns": {
    "timestamp": "timestamp",
    "load_mw": "load_mw",
    "solar_pu": "solar_pu",
    "wind_pu": "wind_pu"
  },
  "capacities": {
    "solar_mw": 65.0,
    "wind_mw": 25.0
  },
  "grid": {
    "import_limit_mw": 35.0,
    "marginal_cost": 100.0,
    "emission_factor_tco2_per_mwh": 0.55
  },
  "storage": {
    "power_mw": 25.0,
    "energy_mwh": 80.0,
    "efficiency_charge": 0.95,
    "efficiency_discharge": 0.95,
    "soc_min_mwh": 8.0,
    "soc_max_mwh": 80.0,
    "soc_initial_mwh": 40.0
  },
  "backup_generator": {
    "p_nom_mw": 15.0,
    "marginal_cost": 300.0,
    "emission_factor_tco2_per_mwh": 0.72
  },
  "penalties": {
    "unserved_energy_cost": 10000.0,
    "allow_unserved": true
  }
}
```

## Profiles CSV

Required columns by default:

- `timestamp`
- `load_mw`
- `solar_pu`
- `wind_pu`

The CSV must have exactly 8760 rows. Renewable profile values are per unit, from 0 to 1.

## Outputs

`dispatch_result.json` contains:

- `status`: `ok` or `failed`
- `failure`: null on success, otherwise `{class, message}`
- `summary`: annual MWh, tCO2, matching, curtailment, and diagnostic values
- `diagnostics`: night gray dependence, storage insufficiency, and notable hours
- `outputs`: relative paths to generated artifacts

`timeseries.csv` contains hourly load, renewable availability, dispatch, curtailment, grid import, backup generation, unserved energy, storage charge/discharge/SOC, and hourly Scope 1/Scope 2 values.

`mismatch_summary.md` is the human-readable acceptance summary.

`figures/` contains PNG plots for dispatch, SOC, and mismatch diagnostics.

`calculation_log.md` contains the execution record, environment, validation checks, solver status, and failure classification.
It is a public artifact and must not contain local absolute paths. Local Python executable paths, absolute output directories, and absolute input paths are redacted or omitted.

## Acceptance

Run SKILL-002A acceptance with:

```powershell
.\.venv\Scripts\python.exe scripts\run_acceptance.py
```

Acceptance covers demo success, 8760-row timeseries, required figures, missing profile, bad unit, missing solver, and public artifact path redaction.
