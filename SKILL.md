---
name: ai-pypsa-skill
description: "Build, run, diagnose, and package auditable PyPSA-based 8760-hour dispatch studies from load, renewable profiles, grid import limits, storage constraints, backup generation, and emission factors. Use when Codex needs to automate PyPSA, run an energy dispatch demo, calculate curtailment, grid import, SOC, unserved energy, backup generation, Scope 1/Scope 2 activity data, green temporal matching, or classify PyPSA/solver/profile/unit failures. / 构建、运行、诊断并打包基于 PyPSA 的 8760 小时可审计电力调度计算，适用于负荷、风光曲线、电网进口约束、储能、备用电源和排放因子的自动化建模、运行、诊断和失败分类。"
---

# AI PyPSA Skill / AI PyPSA 技能

Use this skill for auditable electricity dispatch studies and AI-controlled PyPSA workflows.
使用本技能开展可审计的电力调度研究，以及由 AI 控制的 PyPSA 自动化运行流程。

When writing user-facing explanations, use Chinese-English bilingual labels where practical, especially for inputs, diagnostics, outputs, and failure classes.
面向用户输出说明时，应尽量使用中英双语标签，尤其是输入、诊断、输出和失败分类。

## Default Workflow / 默认流程

1. Confirm the study directory and keep all generated outputs inside it. / 确认研究目录，并将所有生成结果限制在该目录内。
2. Use `scripts/run_dispatch.py` as the deterministic execution entrypoint. / 使用 `scripts/run_dispatch.py` 作为确定性执行入口。
3. Check readiness before running a study. / 运行研究前先检查环境就绪状态：

```powershell
.\.venv\Scripts\python.exe scripts\readiness_check.py
```

4. For a quick dispatch run, execute the demo. / 如需快速调度测试，运行 demo：

```powershell
.\.venv\Scripts\python.exe scripts\run_dispatch.py --demo --output outputs\demo_8760
```

If `.venv` is missing, create it with Python 3.10-3.13 and install `scripts/requirements-pypsa.txt`.
如果缺少 `.venv`，使用 Python 3.10-3.13 创建虚拟环境，并安装 `scripts/requirements-pypsa.txt`。

5. For full SKILL-002A acceptance, execute the acceptance runner. / 如需完整 SKILL-002A 验收，运行验收脚本：

```powershell
.\.venv\Scripts\python.exe scripts\run_acceptance.py
```

6. For user data, provide a JSON config and an 8760-row CSV profile file. / 使用用户数据时，提供 JSON 配置文件和 8760 行 CSV 曲线文件：

```powershell
.\.venv\Scripts\python.exe scripts\run_dispatch.py --config path\to\config.json --profiles path\to\profiles.csv --output outputs\case_name
```

7. Inspect `dispatch_result.json` first, then `mismatch_summary.md`, then `calculation_log.md`. / 先检查 `dispatch_result.json`，再检查 `mismatch_summary.md`，最后检查 `calculation_log.md`。
8. Treat a successful run as complete only when these outputs exist. / 只有以下输出齐全时，才将运行视为完成：
   - `dispatch_result.json`
   - `timeseries.csv`
   - `mismatch_summary.md`
   - `figures/`
   - `calculation_log.md`

## Required Inputs / 必需输入

The workflow supports these inputs. / 本流程支持以下输入：

- 8760 hourly load profile / 8760 小时负荷曲线
- 8760 hourly solar and wind availability profiles / 8760 小时光伏和风电可用率曲线
- grid import limit / 电网进口功率上限
- storage power, energy capacity, efficiency components, and SOC limits / 储能功率、容量、效率参数和 SOC 限制
- backup generator capacity and emission factor / 备用电源容量和排放因子
- grid and backup emission factors / 电网和备用电源排放因子

See `references/output_contract.md` before changing input or output schemas.
修改输入或输出 schema 前，先查看 `references/output_contract.md`。

Validate schema changes against `schemas/input_schema.json` and `schemas/output_schema.json`.
schema 变更必须对照 `schemas/input_schema.json` 和 `schemas/output_schema.json` 校验。

## Required Diagnostics / 必需诊断

Always report these diagnostics with bilingual labels where the output is user-facing. / 面向用户输出时，始终用中英双语标签报告以下诊断：

- renewable curtailment / 可再生能源弃电量
- grid import / 电网进口电量
- storage SOC and low-SOC hours / 储能 SOC 和低 SOC 小时数
- unserved energy / 缺电量
- backup generation / 备用电源发电量
- Scope 1 activity and emissions / 范围一活动数据和排放量
- Scope 2 activity and emissions / 范围二活动数据和排放量
- green temporal matching rate / 绿电时序匹配率
- night grid-import dependence / 夜间灰电依赖
- storage insufficiency evidence / 储能不足证据

## Failure Classes / 失败分类

The runner must classify failures as follows. / 运行器必须按以下类型分类失败：

- `missing_dependency`: Python package such as `pypsa`, `pandas`, or `matplotlib` is unavailable. / 缺少 `pypsa`、`pandas`、`matplotlib` 等 Python 包。
- `missing_solver`: HiGHS/highspy or the configured solver is unavailable. / 缺少 HiGHS/highspy 或配置的求解器不可用。
- `infeasible`: PyPSA reports infeasible or infeasible-or-unbounded. / PyPSA 报告不可行或不可行/无界。
- `missing_profile`: profile file is missing, has missing columns, or is not 8760 rows. / 曲线文件缺失、列缺失或不是 8760 行。
- `bad_unit`: invalid units, negative power/energy, profile values outside 0-1 per unit, impossible SOC bounds, or invalid emission factors. / 单位错误、功率/电量为负、可用率不在 0-1 之间、SOC 边界不可能或排放因子无效。
- `runtime_error`: unexpected execution failure. / 非预期运行错误。

## Public Artifacts / 公开产物

`dispatch_result.json`, `timeseries.csv`, `mismatch_summary.md`, `figures/`, and `calculation_log.md` are public artifacts for Trinity evidence.
`dispatch_result.json`、`timeseries.csv`、`mismatch_summary.md`、`figures/` 和 `calculation_log.md` 是 Trinity 证据链公开产物。

They must not contain local absolute paths such as Windows drive paths or user home directories.
这些产物不得包含 Windows 盘符路径、用户主目录等本地绝对路径。

The runner redacts or omits local executable and output paths in public logs.
运行器会在公开日志中脱敏或省略本地解释器路径和输出目录路径。

## Implementation Notes / 实现说明

The bundled runner uses PyPSA with one electric bus, optional battery energy bus, renewable generators, grid import as a bounded generator, backup generation, and a high-penalty unserved-energy generator.
内置运行器使用 PyPSA 建立单电力母线模型，可选电池能量母线，包含可再生能源发电机、作为有界发电机处理的电网进口、备用电源，以及高惩罚成本的缺电发电机。

Storage is represented as `Store` plus charge/discharge `Link` components so SOC min/max limits are enforced directly.
储能使用 `Store` 加充放电 `Link` 表示，以直接约束 SOC 上下限。

For advanced work, extend the same input/output contract before adding these features. / 增加以下高级能力前，必须先扩展同一套输入/输出契约：

- complex capacity optimization / 复杂容量优化
- multi-region grids / 多区域电网
- market price optimization / 市场电价优化
- stochastic scenarios / 随机场景
- hydrogen/ammonia coupling / 氢氨耦合

## License / 许可证

This project is released under the GNU Affero General Public License v3.0 only (`AGPL-3.0-only`). See `LICENSE`.
本项目仅按 GNU Affero General Public License v3.0（`AGPL-3.0-only`）发布。详见 `LICENSE`。
