#!/usr/bin/env python
"""Run SKILL-002A acceptance checks for AI-PyPSA-Skill."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


EXPECTED_FIGURES = {
    "dispatch_stack_first_14d.png",
    "storage_soc_first_14d.png",
    "gray_shortage_duration_curve.png",
}
REQUIRED_SUMMARY_TERMS = ("绿电时序错配", "储能 SOC", "灰电依赖", "缺电/备用电源")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def clean_dir(path: Path, root: Path) -> None:
    resolved = path.resolve()
    if resolved.exists():
        if not is_relative_to(resolved, root.resolve()) or "acceptance" not in resolved.parts:
            raise RuntimeError(f"Refusing to remove unsafe acceptance path: {resolved}")
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def run_cmd(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def load_result(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def count_csv_rows(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


def contains_absolute_path(text: str) -> bool:
    if re.search(r"[A-Za-z]:\\", text):
        return True
    if re.search(r"(^|\s)/(Users|home|mnt|tmp|var|opt|workspace)/", text):
        return True
    return False


def assert_public_artifacts_safe(output_dir: Path) -> None:
    for path in output_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".json", ".md", ".csv", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if contains_absolute_path(text):
            raise AssertionError(f"Public artifact leaks an absolute path: {path}")


def base_config() -> dict[str, Any]:
    return {
        "units": {
            "load": "MW",
            "power": "MW",
            "energy": "MWh",
            "emission_factor": "tCO2/MWh",
        },
        "columns": {
            "timestamp": "timestamp",
            "load_mw": "load_mw",
            "solar_pu": "solar_pu",
            "wind_pu": "wind_pu",
        },
        "capacities": {"solar_mw": 65.0, "wind_mw": 25.0},
        "grid": {
            "import_limit_mw": 35.0,
            "marginal_cost": 100.0,
            "emission_factor_tco2_per_mwh": 0.55,
        },
        "storage": {
            "power_mw": 25.0,
            "energy_mwh": 80.0,
            "efficiency_charge": 0.95,
            "efficiency_discharge": 0.95,
            "soc_min_mwh": 8.0,
            "soc_max_mwh": 80.0,
            "soc_initial_mwh": 40.0,
        },
        "backup_generator": {
            "p_nom_mw": 15.0,
            "marginal_cost": 300.0,
            "emission_factor_tco2_per_mwh": 0.72,
        },
        "penalties": {"unserved_energy_cost": 10000.0, "allow_unserved": True},
        "solver": {"name": "highs", "log_to_console": False},
    }


def check_demo_success(root: Path, runner: Path, output_root: Path) -> None:
    out = output_root / "demo_success"
    clean_dir(out, root)
    proc = run_cmd(root, [sys.executable, str(runner), "--demo", "--output", str(out)])
    if proc.returncode != 0:
        raise AssertionError(f"demo failed: {proc.stderr[-1000:]}")
    result = load_result(out / "dispatch_result.json")
    if result.get("status") != "ok":
        raise AssertionError("dispatch_result.json.status is not ok")
    if count_csv_rows(out / "timeseries.csv") != 8760:
        raise AssertionError("timeseries.csv does not contain 8760 data rows")
    figures = {p.name for p in (out / "figures").glob("*.png")}
    missing_figures = sorted(EXPECTED_FIGURES - figures)
    if missing_figures:
        raise AssertionError(f"missing figures: {missing_figures}")
    summary = (out / "mismatch_summary.md").read_text(encoding="utf-8")
    missing_terms = [term for term in REQUIRED_SUMMARY_TERMS if term not in summary]
    if missing_terms:
        raise AssertionError(f"mismatch_summary.md missing terms: {missing_terms}")
    assert_public_artifacts_safe(out)


def check_failure_class(
    root: Path,
    runner: Path,
    output_root: Path,
    name: str,
    expected_class: str,
    args: list[str],
) -> None:
    out = output_root / name
    clean_dir(out, root)
    proc = run_cmd(root, [sys.executable, str(runner), *args, "--output", str(out)])
    if proc.returncode == 0:
        raise AssertionError(f"{name} unexpectedly succeeded")
    result = load_result(out / "dispatch_result.json")
    failure = result.get("failure") or {}
    if failure.get("class") != expected_class:
        raise AssertionError(f"{name} expected {expected_class}, got {failure}")
    assert_public_artifacts_safe(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="outputs/acceptance", help="Acceptance output directory.")
    parser.add_argument("--json", action="store_true", help="Print JSON result.")
    args = parser.parse_args()

    root = repo_root()
    runner = root / "scripts" / "run_dispatch.py"
    output_root = (root / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)
    clean_dir(output_root, root)

    cases: list[dict[str, Any]] = []

    def record(name: str, fn: Any) -> None:
        try:
            fn()
            cases.append({"name": name, "status": "ok"})
        except Exception as exc:
            cases.append({"name": name, "status": "failed", "message": str(exc)})

    bad_unit_config = output_root / "bad_unit_config.json"
    bad_cfg = base_config()
    bad_cfg["units"]["load"] = "kW"
    write_json(bad_unit_config, bad_cfg)

    missing_solver_config = output_root / "missing_solver_config.json"
    solver_cfg = base_config()
    solver_cfg["solver"]["name"] = "not_a_solver"
    write_json(missing_solver_config, solver_cfg)

    record("demo_success", lambda: check_demo_success(root, runner, output_root))
    record(
        "missing_profile",
        lambda: check_failure_class(
            root,
            runner,
            output_root,
            "missing_profile",
            "missing_profile",
            ["--config", "examples/demo_config.json", "--profiles", "outputs/acceptance/no_such_profile.csv"],
        ),
    )
    record(
        "bad_unit",
        lambda: check_failure_class(
            root,
            runner,
            output_root,
            "bad_unit",
            "bad_unit",
            ["--demo", "--config", str(bad_unit_config.relative_to(root))],
        ),
    )
    record(
        "missing_solver",
        lambda: check_failure_class(
            root,
            runner,
            output_root,
            "missing_solver",
            "missing_solver",
            ["--demo", "--config", str(missing_solver_config.relative_to(root))],
        ),
    )

    result = {
        "status": "ok" if all(case["status"] == "ok" for case in cases) else "failed",
        "cases": cases,
        "output_dir": str(Path(args.output)),
    }
    write_json(output_root / "acceptance_result.json", result)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"acceptance: {result['status']}")
        for case in cases:
            suffix = "" if case["status"] == "ok" else f" - {case['message']}"
            print(f"- {case['status']} {case['name']}{suffix}")
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

