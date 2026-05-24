# AI PyPSA Skill

AI PyPSA Skill is an auditable PyPSA-based workflow for 8760-hour electricity dispatch studies.

It supports:

- 8760-hour load, solar, and wind profiles
- grid import limits
- storage power, capacity, efficiency, and SOC limits
- backup generation
- Scope 1 and Scope 2 emission factors
- dispatch, curtailment, grid import, SOC, unserved energy, backup generation, and green temporal matching diagnostics

## Quick Start

Create a Python virtual environment, install dependencies, then run the demo:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r scripts\requirements-pypsa.txt
.\.venv\Scripts\python.exe scripts\readiness_check.py
.\.venv\Scripts\python.exe scripts\run_dispatch.py --demo --output outputs\demo_8760
```

Run acceptance checks:

```powershell
.\.venv\Scripts\python.exe scripts\run_acceptance.py
```

Expected public artifacts:

- `dispatch_result.json`
- `timeseries.csv`
- `mismatch_summary.md`
- `figures/`
- `calculation_log.md`

## License

This project is released under the GNU Affero General Public License v3.0 only (`AGPL-3.0-only`). See `LICENSE`.
