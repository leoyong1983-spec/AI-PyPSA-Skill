# Calculation Log

- Run timestamp UTC: 2026-05-23T23:20:38.770938+00:00
- Command: scripts\run_dispatch.py --demo --output outputs\demo_8760
- Python: 3.13.13 (D:\SKILL\AI-PyPSA-Skill\.venv\Scripts\python.exe)
- Platform: Windows-11-10.0.26200-SP0
- PyPSA version: 1.2.1
- Output directory: D:\SKILL\AI-PyPSA-Skill\outputs\demo_8760
- Status: ok
- Solver termination condition: optimal

## Validation

- Expected hours: 8760
- Required units: MW, MWh, tCO2/MWh
- Renewable profiles: per unit [0, 1]
- Storage SOC bounds: enforced through PyPSA Store e_min_pu/e_max_pu

## Effective Config

```json
{
  "case_name": "demo_8760_dispatch",
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
    "soc_initial_mwh": 40.0,
    "standing_loss_per_hour": 0.0
  },
  "backup_generator": {
    "p_nom_mw": 15.0,
    "marginal_cost": 300.0,
    "emission_factor_tco2_per_mwh": 0.72
  },
  "penalties": {
    "unserved_energy_cost": 10000.0,
    "allow_unserved": true
  },
  "diagnostics": {
    "night_solar_pu_threshold": 0.01,
    "gray_import_mw_threshold": 0.1,
    "low_soc_margin_mwh": 0.5
  },
  "solver": {
    "name": "highs",
    "log_to_console": false
  }
}
```
