---
name: ai-pypsa-skill
description: Build, run, diagnose, and package auditable PyPSA-based 8760-hour dispatch studies from load, renewable profiles, grid import limits, storage constraints, backup generation, and emission factors. Use when the user asks Codex to automate PyPSA, run an energy dispatch demo, calculate renewable curtailment, grid import, storage SOC, unserved energy, backup generation, Scope 1/Scope 2 activity data, green temporal matching, or classify PyPSA/solver/profile/unit failures.
---

# AI PyPSA Skill

Use this skill for auditable electricity dispatch studies and AI-controlled PyPSA workflows.

## Default Workflow

1. Confirm the study directory and keep all generated outputs inside it.
2. Use `scripts/run_dispatch.py` as the deterministic execution entrypoint.
3. Check readiness before running a study:

```powershell
.\.venv\Scripts\python.exe scripts\readiness_check.py
```

4. For a quick dispatch run, execute:

```powershell
.\.venv\Scripts\python.exe scripts\run_dispatch.py --demo --output outputs\demo_8760
```

If `.venv` is missing, create it with Python 3.10-3.13 and install `scripts/requirements-pypsa.txt`.

5. For full SKILL-002A acceptance, execute:

```powershell
.\.venv\Scripts\python.exe scripts\run_acceptance.py
```

6. For user data, provide a JSON config and an 8760-row CSV profile file:

```powershell
.\.venv\Scripts\python.exe scripts\run_dispatch.py --config path\to\config.json --profiles path\to\profiles.csv --output outputs\case_name
```

7. Inspect `dispatch_result.json` first, then `mismatch_summary.md`, then `calculation_log.md`.
8. Treat a successful run as complete only when these outputs exist:
   - `dispatch_result.json`
   - `timeseries.csv`
   - `mismatch_summary.md`
   - `figures/`
   - `calculation_log.md`

## Required Inputs

The workflow supports:

- 8760 hourly load profile
- 8760 hourly solar and wind availability profiles
- grid import limit
- storage power, energy capacity, round-trip components, and SOC limits
- backup generator capacity and emission factor
- grid and backup emission factors

See `references/output_contract.md` before changing input or output schemas.
Validate schema changes against `schemas/input_schema.json` and `schemas/output_schema.json`.

## Required Diagnostics

Always report:

- renewable curtailment
- grid import
- storage SOC and low-SOC hours
- unserved energy
- backup generation
- Scope 1 activity and emissions
- Scope 2 activity and emissions
- green temporal matching rate
- night grid-import dependence
- storage insufficiency evidence

## Failure Classes

The runner must classify failures as:

- `missing_dependency`: Python package such as `pypsa`, `pandas`, or `matplotlib` is unavailable.
- `missing_solver`: HiGHS/highspy or the configured solver is unavailable.
- `infeasible`: PyPSA reports infeasible or infeasible-or-unbounded.
- `missing_profile`: profile file is missing, has missing columns, or is not 8760 rows.
- `bad_unit`: invalid units, invalid negative power/energy, profile values outside 0-1 per unit, impossible SOC bounds, or invalid emission factors.
- `runtime_error`: unexpected execution failure.

## Public Artifacts

`dispatch_result.json`, `timeseries.csv`, `mismatch_summary.md`, `figures/`, and `calculation_log.md` are public artifacts for Trinity evidence. They must not contain local absolute paths such as Windows drive paths or user home directories. The runner redacts or omits local executable and output paths in public logs.

## Implementation Notes

The bundled runner uses PyPSA with one electric bus, optional battery energy bus, renewable generators, grid import as a bounded generator, backup generation, and a high-penalty unserved-energy generator. Storage is represented as `Store` plus charge/discharge `Link` components so SOC min/max limits are enforced directly.

For advanced work, extend the same input/output contract before adding:

- complex capacity optimization
- multi-region grids
- market price optimization
- stochastic scenarios
- hydrogen/ammonia coupling

## License

This project is released under the GNU Affero General Public License v3.0 only (`AGPL-3.0-only`). See `LICENSE`.
