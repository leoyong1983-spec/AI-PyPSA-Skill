# Mismatch Summary

## Acceptance Metrics

- Load: 502,695.209 MWh
- Renewable curtailment: 118.896 MWh (0.07%)
- Unserved energy: 3,113.950 MWh (0.62%)
- Grid import: 264,439.715 MWh
- Backup generation: 57,806.379 MWh
- Green temporal matching rate: 35.28%
- Scope 1 activity: 57,806.379 MWh; emissions: 41,620.593 tCO2
- Scope 2 activity: 264,439.715 MWh; emissions: 145,441.843 tCO2

## Diagnostics

- Night grid-import dependence detected: True
- Night grid-import energy: 165,968.525 MWh
- Night grid-import hours: 4745
- Storage insufficiency detected: True
- Storage stress hours: 1813
- Storage SOC range: 8.000 to 80.000 MWh

## Interpretation

- Night gray dependence means grid import occurs when solar availability is near zero.
- Storage insufficiency is flagged when SOC is near its lower bound while grid, backup, or unserved energy is still required.
- Green temporal matching counts renewable dispatch and battery discharge against the same-hour load. For strict certification, storage energy provenance should be tracked separately.
