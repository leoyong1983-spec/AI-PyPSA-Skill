#!/usr/bin/env python
"""Run an auditable 8760-hour PyPSA dispatch study.

The script intentionally keeps the model small and explicit:
- one site electricity bus,
- solar and wind availability profiles,
- bounded grid import,
- optional storage with enforced SOC limits,
- backup generator,
- high-cost unserved-energy slack.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import platform
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECTED_HOURS = 8760
EPS = 1e-6


class DispatchFailure(Exception):
    """Structured failure raised for known validation and execution failures."""

    def __init__(self, failure_class: str, message: str):
        super().__init__(message)
        self.failure_class = failure_class
        self.message = message


def public_path(path: Path | str | None) -> str:
    """Return a path string safe for public artifacts."""
    if path is None:
        return ""
    raw = str(path)
    try:
        p = Path(raw)
        if p.is_absolute():
            return f"<absolute-path:{p.name}>"
    except Exception:
        pass
    return raw


def sanitize_public_text(text: str) -> str:
    """Redact likely local absolute paths from public artifacts."""
    text = re.sub(r"[A-Za-z]:\\[^\s`\"']+", "<absolute-path>", text)
    text = re.sub(r"(?<!:)//[^\s`\"']+", "<absolute-path>", text)
    return text


def public_command(args: argparse.Namespace) -> str:
    parts = ["run_dispatch.py"]
    if args.demo:
        parts.append("--demo")
    if args.config:
        parts.extend(["--config", public_path(args.config)])
    if args.profiles:
        parts.extend(["--profiles", public_path(args.profiles)])
    parts.extend(["--output", public_path(args.output)])
    return " ".join(parts)


@dataclass
class RuntimeModules:
    pd: Any
    plt: Any
    pypsa: Any


def import_runtime_modules() -> RuntimeModules:
    missing = []
    for name in ("pandas", "matplotlib", "pypsa"):
        if importlib.util.find_spec(name) is None:
            missing.append(name)
    if missing:
        raise DispatchFailure(
            "missing_dependency",
            "Missing Python package(s): " + ", ".join(missing),
        )
    if importlib.util.find_spec("highspy") is None:
        raise DispatchFailure("missing_solver", "HiGHS solver package highspy is not installed.")

    import pandas as pd  # type: ignore
    import matplotlib.pyplot as plt  # type: ignore
    import pypsa  # type: ignore

    return RuntimeModules(pd=pd, plt=plt, pypsa=pypsa)


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def default_config() -> dict[str, Any]:
    return {
        "case_name": "demo_8760_dispatch",
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
        "capacities": {
            "solar_mw": 65.0,
            "wind_mw": 25.0,
        },
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
            "standing_loss_per_hour": 0.0,
        },
        "backup_generator": {
            "p_nom_mw": 15.0,
            "marginal_cost": 300.0,
            "emission_factor_tco2_per_mwh": 0.72,
        },
        "penalties": {
            "unserved_energy_cost": 10000.0,
            "allow_unserved": True,
        },
        "diagnostics": {
            "night_solar_pu_threshold": 0.01,
            "gray_import_mw_threshold": 0.1,
            "low_soc_margin_mwh": 0.5,
        },
        "solver": {
            "name": "highs",
            "log_to_console": False,
        },
    }


def load_config(config_path: Path | None, demo: bool) -> dict[str, Any]:
    config = default_config()
    if config_path:
        if not config_path.exists():
            raise DispatchFailure("missing_profile", f"Config file not found: {public_path(config_path)}")
        try:
            with config_path.open("r", encoding="utf-8") as f:
                user_config = json.load(f)
        except json.JSONDecodeError as exc:
            raise DispatchFailure("bad_unit", f"Config JSON is invalid: {exc}") from exc
        config = deep_merge(config, user_config)
    elif not demo:
        raise DispatchFailure("missing_profile", "Provide --config and --profiles, or run with --demo.")
    return config


def make_demo_profiles(pd: Any) -> Any:
    index = pd.date_range("2025-01-01 00:00:00", periods=EXPECTED_HOURS, freq="h")
    rows = []
    for i, ts in enumerate(index):
        hour = ts.hour
        day = ts.dayofyear
        seasonal = 0.5 + 0.5 * math.sin(2 * math.pi * (day - 80) / 365)
        daylight = math.sin(math.pi * (hour - 6) / 12)
        solar_pu = max(0.0, daylight) ** 1.7 * (0.45 + 0.55 * seasonal)

        wind_base = 0.32 + 0.18 * math.sin(2 * math.pi * i / 97)
        wind_synoptic = 0.12 * math.sin(2 * math.pi * i / 311 + 1.7)
        wind_pu = min(0.85, max(0.05, wind_base + wind_synoptic))

        evening_peak = 18.0 * math.exp(-((hour - 20) / 3.2) ** 2)
        morning_peak = 7.0 * math.exp(-((hour - 8) / 3.5) ** 2)
        seasonal_load = 8.0 * math.cos(2 * math.pi * (day - 15) / 365) ** 2
        weekly = 3.0 if ts.weekday() < 5 else -2.0
        load_mw = 46.0 + evening_peak + morning_peak + seasonal_load + weekly

        rows.append(
            {
                "timestamp": ts.isoformat(),
                "load_mw": round(load_mw, 6),
                "solar_pu": round(solar_pu, 6),
                "wind_pu": round(wind_pu, 6),
            }
        )
    return pd.DataFrame(rows)


def load_profiles(pd: Any, profiles_path: Path | None, config: dict[str, Any], demo: bool) -> Any:
    if demo and profiles_path is None:
        return make_demo_profiles(pd)
    if profiles_path is None:
        raise DispatchFailure("missing_profile", "Profile CSV path is required unless --demo is used.")
    if not profiles_path.exists():
        raise DispatchFailure("missing_profile", f"Profile CSV not found: {public_path(profiles_path)}")
    try:
        return pd.read_csv(profiles_path)
    except Exception as exc:
        raise DispatchFailure("missing_profile", f"Could not read profile CSV: {exc}") from exc


def number(value: Any, path: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise DispatchFailure("bad_unit", f"{path} must be numeric, got {value!r}.") from exc
    if math.isnan(result) or math.isinf(result):
        raise DispatchFailure("bad_unit", f"{path} must be finite, got {value!r}.")
    return result


def require_nonnegative(value: Any, path: str) -> float:
    result = number(value, path)
    if result < 0:
        raise DispatchFailure("bad_unit", f"{path} must be non-negative, got {result}.")
    return result


def validate_units(config: dict[str, Any]) -> None:
    expected = {
        "load": "MW",
        "power": "MW",
        "energy": "MWh",
        "emission_factor": "tCO2/MWh",
    }
    units = config.get("units", {})
    for key, expected_value in expected.items():
        actual = units.get(key)
        if actual != expected_value:
            raise DispatchFailure(
                "bad_unit",
                f"Invalid unit for {key}: expected {expected_value}, got {actual!r}.",
            )


def validate_config(config: dict[str, Any]) -> None:
    validate_units(config)
    capacities = config["capacities"]
    grid = config["grid"]
    storage = config["storage"]
    backup = config["backup_generator"]
    penalties = config["penalties"]

    for path, value in (
        ("capacities.solar_mw", capacities.get("solar_mw")),
        ("capacities.wind_mw", capacities.get("wind_mw")),
        ("grid.import_limit_mw", grid.get("import_limit_mw")),
        ("grid.marginal_cost", grid.get("marginal_cost")),
        ("grid.emission_factor_tco2_per_mwh", grid.get("emission_factor_tco2_per_mwh")),
        ("storage.power_mw", storage.get("power_mw")),
        ("storage.energy_mwh", storage.get("energy_mwh")),
        ("storage.soc_min_mwh", storage.get("soc_min_mwh")),
        ("storage.soc_max_mwh", storage.get("soc_max_mwh")),
        ("storage.soc_initial_mwh", storage.get("soc_initial_mwh")),
        ("storage.standing_loss_per_hour", storage.get("standing_loss_per_hour", 0.0)),
        ("backup_generator.p_nom_mw", backup.get("p_nom_mw")),
        ("backup_generator.marginal_cost", backup.get("marginal_cost")),
        (
            "backup_generator.emission_factor_tco2_per_mwh",
            backup.get("emission_factor_tco2_per_mwh"),
        ),
        ("penalties.unserved_energy_cost", penalties.get("unserved_energy_cost")),
    ):
        require_nonnegative(value, path)
    if not isinstance(penalties.get("allow_unserved", True), bool):
        raise DispatchFailure("bad_unit", "penalties.allow_unserved must be boolean.")

    for path in ("storage.efficiency_charge", "storage.efficiency_discharge"):
        value = number(storage.get(path.split(".")[-1]), path)
        if value <= 0 or value > 1:
            raise DispatchFailure("bad_unit", f"{path} must be in (0, 1], got {value}.")

    storage_power = number(storage.get("power_mw"), "storage.power_mw")
    storage_energy = number(storage.get("energy_mwh"), "storage.energy_mwh")
    soc_min = number(storage.get("soc_min_mwh"), "storage.soc_min_mwh")
    soc_max = number(storage.get("soc_max_mwh"), "storage.soc_max_mwh")
    soc_initial = number(storage.get("soc_initial_mwh"), "storage.soc_initial_mwh")
    if storage_power == 0 and storage_energy > 0:
        raise DispatchFailure("bad_unit", "storage.energy_mwh must be 0 when storage.power_mw is 0.")
    if storage_power > 0 and storage_energy <= 0:
        raise DispatchFailure("bad_unit", "storage.energy_mwh must be positive when storage.power_mw is positive.")
    if not (0 <= soc_min <= soc_initial <= soc_max <= storage_energy):
        raise DispatchFailure(
            "bad_unit",
            "Storage SOC limits must satisfy 0 <= soc_min <= soc_initial <= soc_max <= energy_mwh.",
        )


def validate_profiles(pd: Any, df: Any, config: dict[str, Any]) -> Any:
    columns = config["columns"]
    required = [columns["load_mw"], columns["solar_pu"], columns["wind_pu"]]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise DispatchFailure("missing_profile", "Missing profile column(s): " + ", ".join(missing))

    if len(df) != EXPECTED_HOURS:
        raise DispatchFailure(
            "missing_profile",
            f"Profile CSV must contain exactly {EXPECTED_HOURS} rows, got {len(df)}.",
        )

    timestamp_col = columns.get("timestamp")
    if timestamp_col and timestamp_col in df.columns:
        timestamps = pd.to_datetime(df[timestamp_col], errors="coerce")
        if timestamps.isna().any():
            raise DispatchFailure("missing_profile", f"Column {timestamp_col} contains invalid timestamps.")
    else:
        timestamps = pd.date_range("2025-01-01 00:00:00", periods=EXPECTED_HOURS, freq="h")

    out = df.copy()
    out["timestamp"] = timestamps
    for col in required:
        out[col] = pd.to_numeric(out[col], errors="coerce")
        if out[col].isna().any():
            raise DispatchFailure("missing_profile", f"Column {col} contains non-numeric or missing values.")

    load = out[columns["load_mw"]]
    if (load < -EPS).any():
        raise DispatchFailure("bad_unit", "load_mw contains negative values.")
    if load.max() > 100000:
        raise DispatchFailure(
            "bad_unit",
            "load_mw is above 100000 MW; check whether the profile is in kW or W.",
        )

    for profile_name in ("solar_pu", "wind_pu"):
        col = columns[profile_name]
        series = out[col]
        if (series < -EPS).any() or (series > 1 + EPS).any():
            raise DispatchFailure(
                "bad_unit",
                f"{col} must be per unit in [0, 1]. Values look like percent or another unit.",
            )
        out[col] = series.clip(lower=0, upper=1)

    out[columns["load_mw"]] = load.clip(lower=0)
    return out


def add_carriers(network: Any) -> None:
    for carrier in ("AC", "battery", "solar", "wind", "grid", "backup", "unserved"):
        network.add("Carrier", carrier)


def build_network(mods: RuntimeModules, profiles: Any, config: dict[str, Any]) -> Any:
    pd = mods.pd
    pypsa = mods.pypsa
    columns = config["columns"]
    capacities = config["capacities"]
    grid = config["grid"]
    storage = config["storage"]
    backup = config["backup_generator"]
    penalties = config["penalties"]

    n = pypsa.Network()
    snapshots = pd.DatetimeIndex(profiles["timestamp"])
    n.set_snapshots(snapshots)
    n.add("Bus", "site", carrier="AC")
    add_carriers(n)

    load = profiles[columns["load_mw"]].to_numpy()
    solar_pu = profiles[columns["solar_pu"]].to_numpy()
    wind_pu = profiles[columns["wind_pu"]].to_numpy()
    max_load = float(max(load.max(), 1.0))

    n.add("Load", "site_load", bus="site", p_set=load)
    n.add(
        "Generator",
        "solar",
        bus="site",
        carrier="solar",
        p_nom=require_nonnegative(capacities["solar_mw"], "capacities.solar_mw"),
        p_max_pu=solar_pu,
        marginal_cost=0.0,
    )
    n.add(
        "Generator",
        "wind",
        bus="site",
        carrier="wind",
        p_nom=require_nonnegative(capacities["wind_mw"], "capacities.wind_mw"),
        p_max_pu=wind_pu,
        marginal_cost=0.0,
    )
    n.add(
        "Generator",
        "grid_import",
        bus="site",
        carrier="grid",
        p_nom=require_nonnegative(grid["import_limit_mw"], "grid.import_limit_mw"),
        marginal_cost=require_nonnegative(grid["marginal_cost"], "grid.marginal_cost"),
    )
    n.add(
        "Generator",
        "backup_generator",
        bus="site",
        carrier="backup",
        p_nom=require_nonnegative(backup["p_nom_mw"], "backup_generator.p_nom_mw"),
        marginal_cost=require_nonnegative(backup["marginal_cost"], "backup_generator.marginal_cost"),
    )
    if bool(penalties.get("allow_unserved", True)):
        n.add(
            "Generator",
            "unserved_energy",
            bus="site",
            carrier="unserved",
            p_nom=max_load * 2.0,
            marginal_cost=require_nonnegative(
                penalties["unserved_energy_cost"], "penalties.unserved_energy_cost"
            ),
        )

    storage_power = require_nonnegative(storage["power_mw"], "storage.power_mw")
    storage_energy = require_nonnegative(storage["energy_mwh"], "storage.energy_mwh")
    if storage_power > 0 and storage_energy > 0:
        n.add("Bus", "battery", carrier="battery")
        n.add(
            "Link",
            "battery_charge",
            bus0="site",
            bus1="battery",
            carrier="battery",
            p_nom=storage_power,
            efficiency=number(storage["efficiency_charge"], "storage.efficiency_charge"),
            marginal_cost=0.001,
        )
        n.add(
            "Link",
            "battery_discharge",
            bus0="battery",
            bus1="site",
            carrier="battery",
            p_nom=storage_power,
            efficiency=number(storage["efficiency_discharge"], "storage.efficiency_discharge"),
            marginal_cost=0.001,
        )
        n.add(
            "Store",
            "battery_soc",
            bus="battery",
            carrier="battery",
            e_nom=storage_energy,
            e_initial=number(storage["soc_initial_mwh"], "storage.soc_initial_mwh"),
            e_min_pu=number(storage["soc_min_mwh"], "storage.soc_min_mwh") / storage_energy,
            e_max_pu=number(storage["soc_max_mwh"], "storage.soc_max_mwh") / storage_energy,
            e_cyclic=False,
            standing_loss=number(
                storage.get("standing_loss_per_hour", 0.0), "storage.standing_loss_per_hour"
            ),
        )
    return n


def solve_network(network: Any, config: dict[str, Any]) -> tuple[str, str]:
    solver = config.get("solver", {})
    solver_name = solver.get("name", "highs")
    solver_options = {}
    if solver_name == "highs":
        solver_options["log_to_console"] = bool(solver.get("log_to_console", False))
    try:
        status, termination_condition = network.optimize(
            solver_name=solver_name,
            solver_options=solver_options or None,
        )
    except Exception as exc:
        message = str(exc)
        lowered = message.lower()
        if "solver" in lowered and ("not" in lowered or "available" in lowered or "installed" in lowered):
            raise DispatchFailure("missing_solver", message) from exc
        raise
    if termination_condition in ("infeasible", "infeasible_or_unbounded"):
        raise DispatchFailure(
            "infeasible",
            f"Solver status={status}, termination_condition={termination_condition}.",
        )
    if status != "ok" or termination_condition not in ("optimal", "suboptimal"):
        raise DispatchFailure(
            "runtime_error",
            f"Unexpected solver result: status={status}, termination_condition={termination_condition}.",
        )
    return str(status), str(termination_condition)


def get_series(frame: Any, column: str, index: Any, default: float = 0.0) -> Any:
    if frame is None or frame.empty or column not in frame.columns:
        return frame.__class__([default] * len(index), index=index) if frame is not None else None
    return frame[column].astype(float)


def collect_timeseries(mods: RuntimeModules, network: Any, profiles: Any, config: dict[str, Any]) -> Any:
    pd = mods.pd
    columns = config["columns"]
    idx = network.snapshots
    result = pd.DataFrame(index=idx)
    result["timestamp"] = idx.astype(str)
    result["load_mw"] = profiles[columns["load_mw"]].to_numpy()
    result["solar_available_mw"] = (
        profiles[columns["solar_pu"]].to_numpy() * number(config["capacities"]["solar_mw"], "capacities.solar_mw")
    )
    result["wind_available_mw"] = (
        profiles[columns["wind_pu"]].to_numpy() * number(config["capacities"]["wind_mw"], "capacities.wind_mw")
    )

    gen = network.generators_t.p
    result["solar_dispatch_mw"] = gen.get("solar", pd.Series(0.0, index=idx)).astype(float).clip(lower=0)
    result["wind_dispatch_mw"] = gen.get("wind", pd.Series(0.0, index=idx)).astype(float).clip(lower=0)
    result["grid_import_mw"] = gen.get("grid_import", pd.Series(0.0, index=idx)).astype(float).clip(lower=0)
    result["backup_generation_mw"] = (
        gen.get("backup_generator", pd.Series(0.0, index=idx)).astype(float).clip(lower=0)
    )
    result["unserved_energy_mw"] = (
        gen.get("unserved_energy", pd.Series(0.0, index=idx)).astype(float).clip(lower=0)
    )

    if "battery_charge" in network.links.index:
        result["storage_charge_mw"] = (
            network.links_t.p0.get("battery_charge", pd.Series(0.0, index=idx)).astype(float).clip(lower=0)
        )
        result["storage_discharge_mw"] = (
            -network.links_t.p1.get("battery_discharge", pd.Series(0.0, index=idx)).astype(float)
        ).clip(lower=0)
        result["storage_soc_mwh"] = (
            network.stores_t.e.get("battery_soc", pd.Series(0.0, index=idx)).astype(float).clip(lower=0)
        )
    else:
        result["storage_charge_mw"] = 0.0
        result["storage_discharge_mw"] = 0.0
        result["storage_soc_mwh"] = 0.0

    result["solar_curtailment_mw"] = (
        result["solar_available_mw"] - result["solar_dispatch_mw"]
    ).clip(lower=0)
    result["wind_curtailment_mw"] = (
        result["wind_available_mw"] - result["wind_dispatch_mw"]
    ).clip(lower=0)
    result["renewable_dispatch_mw"] = result["solar_dispatch_mw"] + result["wind_dispatch_mw"]
    result["renewable_available_mw"] = result["solar_available_mw"] + result["wind_available_mw"]
    result["renewable_curtailment_mw"] = (
        result["solar_curtailment_mw"] + result["wind_curtailment_mw"]
    )
    result["scope1_activity_mwh"] = result["backup_generation_mw"]
    result["scope2_activity_mwh"] = result["grid_import_mw"]
    result["scope1_tco2"] = (
        result["backup_generation_mw"]
        * number(
            config["backup_generator"]["emission_factor_tco2_per_mwh"],
            "backup_generator.emission_factor_tco2_per_mwh",
        )
    )
    result["scope2_tco2"] = (
        result["grid_import_mw"]
        * number(config["grid"]["emission_factor_tco2_per_mwh"], "grid.emission_factor_tco2_per_mwh")
    )
    result["green_matched_mwh"] = (
        result["load_mw"]
        - result["grid_import_mw"]
        - result["backup_generation_mw"]
        - result["unserved_energy_mw"]
    ).clip(lower=0, upper=result["load_mw"])
    result["residual_gray_or_unserved_mwh"] = (
        result["load_mw"] - result["green_matched_mwh"]
    ).clip(lower=0)
    return result.reset_index(drop=True)


def sum_col(df: Any, column: str) -> float:
    return float(df[column].sum())


def build_summary(timeseries: Any, config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    diagnostics_config = config["diagnostics"]
    solar_threshold = number(
        diagnostics_config["night_solar_pu_threshold"], "diagnostics.night_solar_pu_threshold"
    )
    gray_threshold = number(
        diagnostics_config["gray_import_mw_threshold"], "diagnostics.gray_import_mw_threshold"
    )
    low_soc_margin = number(diagnostics_config["low_soc_margin_mwh"], "diagnostics.low_soc_margin_mwh")
    storage = config["storage"]
    soc_min = number(storage["soc_min_mwh"], "storage.soc_min_mwh")

    load_mwh = sum_col(timeseries, "load_mw")
    curtailment_mwh = sum_col(timeseries, "renewable_curtailment_mw")
    unserved_mwh = sum_col(timeseries, "unserved_energy_mw")
    grid_mwh = sum_col(timeseries, "grid_import_mw")
    backup_mwh = sum_col(timeseries, "backup_generation_mw")
    green_matched_mwh = sum_col(timeseries, "green_matched_mwh")

    night_mask = timeseries["solar_available_mw"] <= (
        number(config["capacities"]["solar_mw"], "capacities.solar_mw") * solar_threshold
    )
    night_gray = timeseries[night_mask & (timeseries["grid_import_mw"] > gray_threshold)].copy()
    low_soc_mask = timeseries["storage_soc_mwh"] <= (soc_min + low_soc_margin + EPS)
    storage_stress = timeseries[
        low_soc_mask
        & (
            (timeseries["grid_import_mw"] > gray_threshold)
            | (timeseries["backup_generation_mw"] > EPS)
            | (timeseries["unserved_energy_mw"] > EPS)
        )
    ].copy()

    summary = {
        "load_mwh": load_mwh,
        "renewable_available_mwh": sum_col(timeseries, "renewable_available_mw"),
        "renewable_dispatch_mwh": sum_col(timeseries, "renewable_dispatch_mw"),
        "renewable_curtailment_mwh": curtailment_mwh,
        "renewable_curtailment_rate": curtailment_mwh
        / max(sum_col(timeseries, "renewable_available_mw"), EPS),
        "grid_import_mwh": grid_mwh,
        "backup_generation_mwh": backup_mwh,
        "unserved_energy_mwh": unserved_mwh,
        "unserved_energy_rate": unserved_mwh / max(load_mwh, EPS),
        "storage_charge_mwh": sum_col(timeseries, "storage_charge_mw"),
        "storage_discharge_mwh": sum_col(timeseries, "storage_discharge_mw"),
        "storage_min_soc_mwh": float(timeseries["storage_soc_mwh"].min()),
        "storage_max_soc_mwh": float(timeseries["storage_soc_mwh"].max()),
        "scope1_activity_mwh": sum_col(timeseries, "scope1_activity_mwh"),
        "scope1_tco2": sum_col(timeseries, "scope1_tco2"),
        "scope2_activity_mwh": sum_col(timeseries, "scope2_activity_mwh"),
        "scope2_tco2": sum_col(timeseries, "scope2_tco2"),
        "green_temporal_matching_mwh": green_matched_mwh,
        "green_temporal_matching_rate": green_matched_mwh / max(load_mwh, EPS),
        "night_grid_import_mwh": float(night_gray["grid_import_mw"].sum()) if len(night_gray) else 0.0,
        "night_grid_import_hours": int(len(night_gray)),
        "storage_stress_hours": int(len(storage_stress)),
    }

    diagnostics = {
        "night_gray_dependence_detected": bool(summary["night_grid_import_mwh"] > EPS),
        "storage_insufficiency_detected": bool(
            summary["storage_stress_hours"] > 0 or summary["unserved_energy_mwh"] > EPS
        ),
        "night_gray_top_hours": top_hours(night_gray, "grid_import_mw", 10),
        "storage_stress_top_hours": top_hours(storage_stress, "unserved_energy_mw", 10),
    }
    return summary, diagnostics


def top_hours(df: Any, sort_column: str, limit: int) -> list[dict[str, Any]]:
    if df is None or len(df) == 0:
        return []
    sorted_df = df.sort_values(sort_column, ascending=False).head(limit)
    rows = []
    for _, row in sorted_df.iterrows():
        rows.append(
            {
                "timestamp": str(row["timestamp"]),
                "load_mw": round(float(row["load_mw"]), 6),
                "grid_import_mw": round(float(row["grid_import_mw"]), 6),
                "backup_generation_mw": round(float(row["backup_generation_mw"]), 6),
                "storage_soc_mwh": round(float(row["storage_soc_mwh"]), 6),
                "unserved_energy_mw": round(float(row["unserved_energy_mw"]), 6),
            }
        )
    return rows


def write_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def fmt(value: float, digits: int = 3) -> str:
    return f"{value:,.{digits}f}"


def write_mismatch_summary(path: Path, summary: dict[str, Any], diagnostics: dict[str, Any]) -> None:
    lines = [
        "# Mismatch Summary",
        "",
        "## Acceptance Metrics",
        "",
        f"- Load: {fmt(summary['load_mwh'])} MWh",
        f"- Renewable curtailment: {fmt(summary['renewable_curtailment_mwh'])} MWh "
        f"({summary['renewable_curtailment_rate']:.2%})",
        f"- Unserved energy: {fmt(summary['unserved_energy_mwh'])} MWh "
        f"({summary['unserved_energy_rate']:.2%})",
        f"- Grid import: {fmt(summary['grid_import_mwh'])} MWh",
        f"- Backup generation: {fmt(summary['backup_generation_mwh'])} MWh",
        f"- Green temporal matching rate: {summary['green_temporal_matching_rate']:.2%}",
        f"- Scope 1 activity: {fmt(summary['scope1_activity_mwh'])} MWh; "
        f"emissions: {fmt(summary['scope1_tco2'])} tCO2",
        f"- Scope 2 activity: {fmt(summary['scope2_activity_mwh'])} MWh; "
        f"emissions: {fmt(summary['scope2_tco2'])} tCO2",
        "",
        "## Trinity Acceptance Notes",
        "",
        f"- 绿电时序错配: residual gray-or-unserved energy is "
        f"{fmt(summary['load_mwh'] - summary['green_temporal_matching_mwh'])} MWh; "
        f"green temporal matching rate is {summary['green_temporal_matching_rate']:.2%}.",
        f"- 储能 SOC: SOC range is {fmt(summary['storage_min_soc_mwh'])} to "
        f"{fmt(summary['storage_max_soc_mwh'])} MWh; storage stress hours are "
        f"{summary['storage_stress_hours']}.",
        f"- 灰电依赖: night grid-import dependence is "
        f"{diagnostics['night_gray_dependence_detected']}; night grid import is "
        f"{fmt(summary['night_grid_import_mwh'])} MWh.",
        f"- 缺电/备用电源: unserved energy is {fmt(summary['unserved_energy_mwh'])} MWh; "
        f"backup generation is {fmt(summary['backup_generation_mwh'])} MWh.",
        "",
        "## Diagnostics",
        "",
        f"- Night grid-import dependence detected: {diagnostics['night_gray_dependence_detected']}",
        f"- Night grid-import energy: {fmt(summary['night_grid_import_mwh'])} MWh",
        f"- Night grid-import hours: {summary['night_grid_import_hours']}",
        f"- Storage insufficiency detected: {diagnostics['storage_insufficiency_detected']}",
        f"- Storage stress hours: {summary['storage_stress_hours']}",
        f"- Storage SOC range: {fmt(summary['storage_min_soc_mwh'])} to "
        f"{fmt(summary['storage_max_soc_mwh'])} MWh",
        "",
        "## Interpretation",
        "",
        "- Night gray dependence means grid import occurs when solar availability is near zero.",
        "- Storage insufficiency is flagged when SOC is near its lower bound while grid, backup, or unserved energy is still required.",
        "- Green temporal matching counts renewable dispatch and battery discharge against the same-hour load. For strict certification, storage energy provenance should be tracked separately.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_log(
    path: Path,
    args: argparse.Namespace,
    config: dict[str, Any],
    status: str,
    termination_condition: str | None,
    failure: dict[str, Any] | None,
    pypsa_version: str | None,
) -> None:
    lines = [
        "# Calculation Log",
        "",
        f"- Run timestamp UTC: {datetime.now(timezone.utc).isoformat()}",
        f"- Command: {public_command(args)}",
        f"- Python: {sys.version.split()[0]} (<redacted executable>)",
        f"- Platform: {platform.platform()}",
        f"- PyPSA version: {pypsa_version or 'unavailable'}",
        f"- Output directory: {public_path(args.output)}",
        f"- Status: {status}",
        "- Public artifact policy: local absolute paths are redacted or omitted.",
    ]
    if termination_condition:
        lines.append(f"- Solver termination condition: {termination_condition}")
    if failure:
        lines.extend(
            [
                f"- Failure class: {failure['class']}",
                f"- Failure message: {sanitize_public_text(failure['message'])}",
            ]
        )
    lines.extend(
        [
            "",
            "## Validation",
            "",
            "- Expected hours: 8760",
            "- Required units: MW, MWh, tCO2/MWh",
            "- Renewable profiles: per unit [0, 1]",
            "- Storage SOC bounds: enforced through PyPSA Store e_min_pu/e_max_pu",
            "",
            "## Effective Config",
            "",
            "```json",
            json.dumps(config, indent=2, ensure_ascii=False),
            "```",
            "",
        ]
    )
    path.write_text(sanitize_public_text("\n".join(lines)), encoding="utf-8")


def make_figures(mods: RuntimeModules, timeseries: Any, figures_dir: Path) -> None:
    plt = mods.plt
    figures_dir.mkdir(parents=True, exist_ok=True)
    sample = timeseries.iloc[: min(len(timeseries), 24 * 14)].copy()
    x = range(len(sample))

    plt.figure(figsize=(14, 6))
    plt.stackplot(
        x,
        sample["solar_dispatch_mw"],
        sample["wind_dispatch_mw"],
        sample["storage_discharge_mw"],
        sample["grid_import_mw"],
        sample["backup_generation_mw"],
        sample["unserved_energy_mw"],
        labels=["solar", "wind", "storage discharge", "grid import", "backup", "unserved"],
    )
    plt.plot(x, sample["load_mw"], color="black", linewidth=1.2, label="load")
    plt.title("Dispatch stack, first 14 days")
    plt.xlabel("Hour")
    plt.ylabel("MW")
    plt.legend(loc="upper right", ncol=3)
    plt.tight_layout()
    plt.savefig(figures_dir / "dispatch_stack_first_14d.png", dpi=150)
    plt.close()

    plt.figure(figsize=(14, 4))
    plt.plot(x, sample["storage_soc_mwh"], color="#1f77b4")
    plt.title("Storage SOC, first 14 days")
    plt.xlabel("Hour")
    plt.ylabel("MWh")
    plt.tight_layout()
    plt.savefig(figures_dir / "storage_soc_first_14d.png", dpi=150)
    plt.close()

    duration = timeseries[["grid_import_mw", "backup_generation_mw", "unserved_energy_mw"]].copy()
    duration = duration.sort_values("grid_import_mw", ascending=False).reset_index(drop=True)
    plt.figure(figsize=(10, 5))
    plt.plot(duration.index, duration["grid_import_mw"], label="grid import")
    plt.plot(duration.index, duration["backup_generation_mw"], label="backup")
    plt.plot(duration.index, duration["unserved_energy_mw"], label="unserved")
    plt.title("Gray and shortage duration curves")
    plt.xlabel("Sorted hour")
    plt.ylabel("MW")
    plt.legend()
    plt.tight_layout()
    plt.savefig(figures_dir / "gray_shortage_duration_curve.png", dpi=150)
    plt.close()


def relative(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def run(args: argparse.Namespace) -> int:
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = output_dir / "figures"
    result_path = output_dir / "dispatch_result.json"
    log_path = output_dir / "calculation_log.md"
    config = default_config()
    pypsa_version = None

    try:
        mods = import_runtime_modules()
        pypsa_version = getattr(mods.pypsa, "__version__", "unknown")
        config = load_config(Path(args.config) if args.config else None, args.demo)
        validate_config(config)
        profiles = load_profiles(
            mods.pd,
            Path(args.profiles) if args.profiles else None,
            config,
            args.demo,
        )
        profiles = validate_profiles(mods.pd, profiles, config)
        network = build_network(mods, profiles, config)
        solver_status, termination_condition = solve_network(network, config)
        timeseries = collect_timeseries(mods, network, profiles, config)
        summary, diagnostics = build_summary(timeseries, config)

        timeseries_path = output_dir / "timeseries.csv"
        summary_path = output_dir / "mismatch_summary.md"
        timeseries.to_csv(timeseries_path, index=False)
        write_mismatch_summary(summary_path, summary, diagnostics)
        make_figures(mods, timeseries, figures_dir)

        result = {
            "status": "ok",
            "failure": None,
            "case_name": config.get("case_name"),
            "solver": {
                "status": solver_status,
                "termination_condition": termination_condition,
                "name": config.get("solver", {}).get("name", "highs"),
            },
            "summary": summary,
            "diagnostics": diagnostics,
            "outputs": {
                "dispatch_result_json": "dispatch_result.json",
                "timeseries_csv": "timeseries.csv",
                "mismatch_summary_md": "mismatch_summary.md",
                "figures_dir": "figures",
                "calculation_log_md": "calculation_log.md",
            },
        }
        write_json(result_path, result)
        write_log(log_path, args, config, "ok", termination_condition, None, pypsa_version)
        return 0
    except DispatchFailure as exc:
        failure = {"class": exc.failure_class, "message": sanitize_public_text(exc.message)}
        write_json(
            result_path,
            {
                "status": "failed",
                "failure": failure,
                "case_name": config.get("case_name"),
                "summary": {},
                "diagnostics": {},
                "outputs": {
                    "dispatch_result_json": "dispatch_result.json",
                    "calculation_log_md": "calculation_log.md",
                },
            },
        )
        write_log(log_path, args, config, "failed", None, failure, pypsa_version)
        print(f"{exc.failure_class}: {exc.message}", file=sys.stderr)
        return 2
    except Exception as exc:
        failure = {
            "class": "runtime_error",
            "message": sanitize_public_text(str(exc)),
            "traceback_redacted": True,
        }
        write_json(
            result_path,
            {
                "status": "failed",
                "failure": failure,
                "case_name": config.get("case_name"),
                "summary": {},
                "diagnostics": {},
                "outputs": {
                    "dispatch_result_json": "dispatch_result.json",
                    "calculation_log_md": "calculation_log.md",
                },
            },
        )
        write_log(log_path, args, config, "failed", None, failure, pypsa_version)
        print(f"runtime_error: {exc}", file=sys.stderr)
        return 3


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Run the built-in 8760-hour demo profiles.")
    parser.add_argument("--config", help="Path to config JSON.")
    parser.add_argument("--profiles", help="Path to 8760-row profile CSV.")
    parser.add_argument("--output", default="outputs/demo_8760", help="Output directory.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
