#!/usr/bin/env python
"""Check whether the local Python environment can run the PyPSA dispatch runner."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from typing import Any


REQUIRED_MODULES = ("pandas", "matplotlib", "pypsa", "highspy", "scipy")


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def module_version(name: str) -> str:
    try:
        module = importlib.import_module(name)
    except Exception as exc:
        return f"import failed: {exc}"
    return str(getattr(module, "__version__", "installed"))


def run_checks() -> dict[str, Any]:
    results: list[CheckResult] = []
    py_ok = sys.version_info >= (3, 10)
    results.append(
        CheckResult(
            "python_version",
            py_ok,
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
    )
    for name in REQUIRED_MODULES:
        found = importlib.util.find_spec(name) is not None
        detail = module_version(name) if found else "missing"
        results.append(CheckResult(name, found, detail))

    missing = [r.name for r in results if not r.ok]
    return {
        "status": "ok" if not missing else "failed",
        "missing": missing,
        "checks": [{"name": r.name, "ok": r.ok, "detail": r.detail} for r in results],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON only.")
    args = parser.parse_args()
    result = run_checks()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"readiness: {result['status']}")
        for check in result["checks"]:
            mark = "OK" if check["ok"] else "FAIL"
            print(f"- {mark} {check['name']}: {check['detail']}")
    return 0 if result["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())

