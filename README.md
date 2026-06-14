# AI PyPSA Skill / AI PyPSA 技能

AI PyPSA Skill is an auditable PyPSA-based workflow for 8760-hour electricity dispatch studies.
AI PyPSA 技能用于执行可审计的 8760 小时 PyPSA 电力调度研究。

It supports these inputs and calculations. / 它支持以下输入和计算：

- 8760-hour load, solar, and wind profiles / 8760 小时负荷、光伏和风电曲线
- grid import limits / 电网进口限制
- storage power, capacity, efficiency, and SOC limits / 储能功率、容量、效率和 SOC 限制
- backup generation / 备用电源
- Scope 1 and Scope 2 emission factors / 范围一和范围二排放因子
- dispatch, curtailment, grid import, SOC, unserved energy, backup generation, and green temporal matching diagnostics / 调度、弃电、电网进口、SOC、缺电量、备用电源发电和绿电时序匹配诊断

## Quick Start / 快速开始

Create a Python virtual environment, install dependencies, then run the demo.
创建 Python 虚拟环境、安装依赖，然后运行 demo。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r scripts\requirements-pypsa.txt
.\.venv\Scripts\python.exe scripts\readiness_check.py
.\.venv\Scripts\python.exe scripts\run_dispatch.py --demo --output outputs\demo_8760
```

Run acceptance checks. / 运行验收检查：

```powershell
.\.venv\Scripts\python.exe scripts\run_acceptance.py
```

Expected public artifacts. / 预期公开产物：

- `dispatch_result.json`
- `timeseries.csv`
- `mismatch_summary.md`
- `figures/`
- `calculation_log.md`

## Output Diagnostics / 输出诊断

The demo and user-data runs report these key indicators. / demo 和用户数据运行会报告以下关键指标：

- renewable curtailment / 可再生能源弃电量
- grid import / 电网进口电量
- storage SOC / 储能 SOC
- unserved energy / 缺电量
- backup generation / 备用电源发电量
- Scope 1 and Scope 2 activity data / 范围一和范围二活动数据
- green temporal matching rate / 绿电时序匹配率
- night gray-power dependence / 夜间灰电依赖
- storage insufficiency / 储能不足

## License / 许可证

This project is released under the GNU Affero General Public License v3.0 only (`AGPL-3.0-only`). See `LICENSE`.
本项目仅按 GNU Affero General Public License v3.0（`AGPL-3.0-only`）发布。详见 `LICENSE`。
