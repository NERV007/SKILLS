# RD-Efficiency-Portfolio 全景单页

产物文件名：**`RD-Efficiency-Portfolio.html`**（页内标题：产研效能报告）。  
**不是**静态 HTML 模板填空生成，而是由 Python **拼装**：从上游单源报告抽取 `var data`，CSS/Tab/图表逻辑内嵌在脚本模块中。

## 生成命令

```bash
export GATE_REPORTS_ROOT="${GATE_REPORTS_ROOT:-$HOME/work/效能-cursor}"
cd "$GATE_REPORTS_ROOT"
python3 gate-rdj-reports/scripts/build_portfolio_single_html.py
# 或：bash gate-rdj-reports/scripts/refresh_portfolio_pipeline.sh  # 全链刷新后自动构建
```

输出默认写入 **`$GATE_REPORTS_ROOT/RD-Efficiency-Portfolio.html`**（业务仓库根，非 skill 包内）。

## 上游输入（`build_portfolio_single_html.py` · `SRC`）

| 键 | 默认路径（相对业务仓库根） |
|----|---------------------------|
| `main_time` | `Gate-RDJ-时间维度-skill-需求分析报告.html` |
| `main_iter` | `Gate-RDJ-迭代维度-skill-需求分析报告.html` |
| `branch` | `产研分站-全景需求分析报告.html` |
| `ai` | `Gate-AI项目集-测试工时与RT分析报告.html` |
| `alpha` | `Meegle-视图8bbOlLnNU-主站分站-效能报告.html` |
| `rt_merge` | `Gate-RDJ-RT合并分析报告.html` |

另读 CSV：`data/meegle_view_8bbOlLnNU.csv`、`需求导出-Gate-RDJ_*.csv`（原始数据 Tab）、`data/department_stats.html`（人员编制）。

## 构建脚本模块（均在 `scripts/`）

| 文件 | 职责 |
|------|------|
| **`build_portfolio_single_html.py`** | 主入口：读上游 HTML、拼 Tab、写 `RD-Efficiency-Portfolio.html` |
| `portfolio_rd_styles.py` | 全景页 CSS（Executive 青蓝系、按月折叠、工时修正弹窗） |
| `portfolio_raw_data.py` | 原始数据 Tab + 总览需求明细（Story ID、按月折叠） |
| `portfolio_hour_override.py` | 工时修正 Tab + 弹窗 + `PORTFOLIO_MAIN_ROWS` + 部门 R/T 客户端重算 |
| `portfolio_formula_core.py` | 主站 R/T 公式说明块 |
| `portfolio_glossary.py` | 附录指标表 HTML |
| `portfolio_rt_merge.py` | RT 四源总览 / 部门×四源表嵌入 |
| `portfolio_dept_stats.py` | 人员编制 Tab |
| `portfolio_ai_alpha.py` | AI / Alpha Tab 数据抽取 |
| `portfolio_data_reconcile.py` | 总览横向对账逻辑 |
| `portfolio_validate.py` | 构建前校验（errors 阻断） |
| `verify_portfolio_raw_data.py` | 构建后口径 + HTML 嵌入校验 |
| `rdj_delivery_blocks.py` | 主站 Tab 交付周期 / 四象限扩展块 |
| `refresh_portfolio_pipeline.sh` | 全链刷新（Gate-RDJ → … → 全景） |
| `_paths.py` | 路径：`gate-rdj-reports/` 为包根，`../` 为业务数据仓库根 |

## 参考静态壳（非生成器）

`RD-Efficiency-Portfolio.shell.html`：早期 **UI 骨架参考**（静态 Tab/样式 demo）。  
现行产物以 `portfolio_rd_styles.py` + `build_portfolio_single_html.py` 为准；改样式优先改 Python 模块后重跑构建。

## 业务仓库推荐布局

```
GATE_REPORTS_ROOT/
├── gate-rdj-reports/          ← 本 skill 包（可从 SKILLS 仓库 clone）
├── data/                      ← Meegle、department_stats 快照等
├── vendor/                    ← 可 symlink 到 gate-rdj-reports/vendor
├── scripts/                   ← 可 symlink 到 gate-rdj-reports/scripts
├── 需求导出-Gate-RDJ_*.csv
├── Gate-RDJ-*.html            ← 上游单源报告
└── RD-Efficiency-Portfolio.html  ← 构建产物
```
