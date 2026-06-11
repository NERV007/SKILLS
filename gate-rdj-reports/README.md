# gate-rdj-reports

Gate-RDJ / Gate-AI / 产研分站 / QC 四源 / Meegle / **产研效能全景单页** 报告工具包。

| 目录 | 内容 |
|------|------|
| `SKILL.md` | Cursor Agent 操作手册（**skill 入口，与 `~/.cursor/skills/gate-rdj-reports` 符号链接**） |
| `scripts/` | 生成脚本（Python + Node + 刷新链 shell） |
| `templates/` | HTML 源模板（Gate-RDJ-12 四件套、P9 参考、RT 合并） |
| `vendor/` | ECharts 本地静态资源 |

仓库根目录保留 **数据**（`data/`、`*导出*.csv`）与 **产物**（`RD-Efficiency-Portfolio.html` 等）。

```bash
export GATE_REPORTS_ROOT="${GATE_REPORTS_ROOT:-$HOME/work/效能-cursor}"
cd "$GATE_REPORTS_ROOT"
```

## 数据源滞后 · 一键刷新全景

```bash
bash scripts/refresh_portfolio_pipeline.sh
```

按顺序刷新：Gate-RDJ → 分站 → Gate-AI → Meegle → QC 四源 → RT 合并 → **`RD-Efficiency-Portfolio.html`**。  
详见 **`SKILL.md` 第六节**。

## 仅合并全景（上游 HTML/CSV 已就绪）

```bash
python3 scripts/build_portfolio_single_html.py
PYTHONPATH=scripts python3 scripts/verify_portfolio_raw_data.py
```

**本版口径**：部门 = 有 QC 参与即算；部门 R/T = 整单不分摊；需求明细按月收起 + Story ID + 工时修正（`localStorage`）。见 `SKILL.md`、`data/RT多人QC口径分析.md`。

## 全景单页脚本一览

| 脚本 | 作用 |
|------|------|
| `refresh_portfolio_pipeline.sh` | 全链刷新（推荐） |
| `build_portfolio_single_html.py` | 输出 `RD-Efficiency-Portfolio.html`（8 Tab） |
| `portfolio_rd_styles.py` | 全景 CSS（Executive 青蓝系、弹窗、按月折叠） |
| `portfolio_raw_data.py` | 原始数据 / 需求明细（部门参与即算、按月折叠） |
| `portfolio_hour_override.py` | 工时修正 Tab + 弹窗 + 部门 R/T 客户端联动 |
| `portfolio_formula_core.py` | 主站 R/T 公式说明块 |
| `portfolio_glossary.py` | 附录指标表 |
| `verify_portfolio_raw_data.py` | 构建后口径校验（建议跑） |
| `portfolio_data_reconcile.py` | 总览横向对账 |
| `portfolio_validate.py` | 构建前校验（errors 阻断） |
| `rdj_delivery_blocks.py` | 主站交付周期 / 四象限等 |
| `portfolio_rt_merge.py` | RT 四源总览嵌入 |
| `portfolio_ai_alpha.py` | Gate-AI + Meegle 抽取 |
| `portfolio_dept_stats.py` | 人员编制 Tab |
| `gate_rdj_metrics.py` | 指标口径（`corrected_rd`、`split_qc_field_roles`） |

## Gate-RDJ 单源

```bash
python3 scripts/gate_rdj_from_xlsx.py --regenerate --dimension both
```

完整六条流水线见 **`SKILL.md`**。

Cursor skill：`.cursor/skills/gate-rdj-reports` → 本目录（符号链接）。
