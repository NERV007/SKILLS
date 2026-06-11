---
name: gate-rdj-reports
description: >-
  Converts 需求导出-Gate-RDJ Excel/CSV exports to CSV and generates Gate-RDJ HTML
  efficiency reports (time and/or iteration dimension). Also covers Gate-AI 项目集、
  产研分站全景、QC 四源台账、Meegle Alpha、RT 合并、以及产研效能全景单页
  RD-Efficiency-Portfolio.html。Triggers on 需求导出-Gate-RDJ xlsx/csv、Gate-RDJ reports、
  gate_rdj_from_xlsx、generate_gate_rdj_from_csv、generate_gate_ai_effort_report、
  generate_chanfeng_station_report、qc_unified_roster_report、generate_rt_merge_report、
  build_meegle_report_html、主站分站效能报告、8bbOlLnNU、按月部门汇总、
  RD-Efficiency-Portfolio、产研效能报告、build_portfolio_single_html、
  portfolio_rd_styles、rdj_delivery_blocks、portfolio_raw_data、portfolio_hour_override、
  工时修正、localStorage、refresh_portfolio_pipeline、verify_portfolio_raw_data、
  有QC参与即算、整单不分摊、按月折叠、需求明细、Story ID、depts_for_qc、role-s-qa，
  or asks to refresh/regenerate these reports.
---

# Gate-RDJ / 多源效能报告工具包

将 Meegle / Gate 导出的 CSV、xlsx 转为可离线打开的 HTML 效能报告；并可将多份已生成报告合并为 **产研效能全景单页**。

**Skill 入口**：本文件（`gate-rdj-reports/SKILL.md`），与 `~/.cursor/skills/gate-rdj-reports`、`.cursor/skills/gate-rdj-reports` 同一内容（项目内为完整版，用户级可为摘要占位）。  
**人类索引**：`gate-rdj-reports/README.md`。

## 本版要点（2026-06）

| 项 | 规则 |
|----|------|
| 部门归属 | **有 QC 参与即算**（`depts[]`），非首 QC |
| 部门 R/T | story 去重 + **整单** Σ研发÷Σ测试（不分摊） |
| 个人 R/T | 仍 `1/n` 均分（P9 / QC 人员明细） |
| 需求明细 | 按月折叠默认收起；列含 **Story ID**、**工时修正** 按钮 |
| 工时修正 | 浏览器 `localStorage` 覆盖主站研发/测试；联动明细、统计条、部门主站 R/T |
| QC 列展示 | `-QC/-qc` → 测试侧；无 qc 后缀 → 开发角色（含 `role-s-qa`），**不调整**系统工时 |
| 统计截至 | `PORTFOLIO_AS_OF = 2026-05-31` |
| 主站 R/T 锚点 | 全量去重约 **2.84**；`1交易-交易组` 筛选约 **284 条 / R/T 2.10** |

详见 `data/RT多人QC口径分析.md`。

## 环境

```bash
export GATE_REPORTS_ROOT="${GATE_REPORTS_ROOT:-$HOME/work/效能-cursor}"
cd "$GATE_REPORTS_ROOT"
# 根目录 scripts/、vendor/ 为符号链接 → gate-rdj-reports/scripts、vendor/
```

Python 3.9+；Gate-RDJ xlsx 转换需 `pandas openpyxl`；Gate-AI 需 `pandas numpy`；PDF 需 Node + Puppeteer（`scripts/html_to_pdf.js`）。

## 目录结构

```
gate-rdj-reports/
├── SKILL.md              ← 本文件（Cursor skill 完整入口）
├── README.md             ← 人类可读索引（含全景脚本表）
├── scripts/
│   ├── refresh_portfolio_pipeline.sh    ← 数据源滞后 · 全链刷新（推荐）
│   ├── build_portfolio_single_html.py   ← 产研效能全景单页（第六节）
│   ├── portfolio_rd_styles.py           ← 全景 CSS（Executive 青蓝系）
│   ├── portfolio_raw_data.py            ← 原始数据 / 需求明细（按月折叠、Story ID）
│   ├── portfolio_hour_override.py       ← 工时修正 Tab + 弹窗 + 部门 R/T 客户端重算
│   ├── portfolio_formula_core.py        ← R/T 公式说明块（多 Tab 共用）
│   ├── portfolio_glossary.py            ← 附录指标表（含工时修正说明）
│   ├── verify_portfolio_raw_data.py     ← 原始数据口径 + HTML 嵌入校验
│   ├── portfolio_data_reconcile.py      ← 总览横向对账
│   ├── portfolio_validate.py            ← 构建前校验（errors 阻断）
│   ├── rdj_delivery_blocks.py           ← 主站交付/四象限扩展块
│   ├── portfolio_ai_alpha.py            ← AI/Alpha 抽取
│   ├── portfolio_rt_merge.py            ← RT 四源总览嵌入
│   ├── portfolio_dept_stats.py          ← 人员编制 Tab（QC 去重）
│   ├── gate_rdj_metrics.py              ← 核心口径（含 corrected_rd）
│   └── …（Gate-RDJ / AI / 分站 / QC / Meegle / RT 等）
├── templates/            ← Gate-RDJ-12 四件套、P9 参考、rt_merge_report.html（见 templates/README.md）
└── vendor/               ← echarts-5.4.3.min.js

仓库根/
├── data/                 ← 快照、Meegle 导出、department_stats、RT多人QC口径分析.md
├── RD-Efficiency-Portfolio.html  ← 第六节产物（页内标题：产研效能报告）
├── scripts → gate-rdj-reports/scripts
├── vendor → gate-rdj-reports/vendor
└── *.csv / *.html        ← 输入 CSV 与单源生成报告
```

## 六条流水线概览

1. **Gate-RDJ 维度报告** — 单源 CSV → 4 份 HTML + 综合入口（**独立 HTML 模板** + 生成脚本替换占位）。
2. **Gate-AI 项目集报告** — 单源 xlsx/csv → 1 份 HTML + 2 份 CSV（**脚本内嵌版式**，对齐 P9 骨架）。
3. **产研分站全景报告** — 全景 xlsx/csv → 1 份 HTML + 根目录 CSV（**脚本内嵌版式**，含 LDT 专块）。
4. **QC 四源聚合台账** — 五路 CSV + `department_stats` → 单份 HTML（RT 合并上游）。
5. **Alpha·Meegle 多项目视图** — Playwright/MCP 导出宽表 CSV → 主站/分站单页 HTML。
6. **产研效能全景单页** — 多份已生成 HTML/CSV **只读抽取** → 单文件多 Tab 全景（**Python 内嵌 HTML + CSS 模块**）。

---

## 一、Gate-RDJ 维度报告

### 输入 / 输出

| 输入 | 路径 |
|------|------|
| xlsx（可选） | `~/Downloads/需求导出-Gate-RDJ (N).xlsx` |
| 时间维 CSV | `需求导出-Gate-RDJ_时间维度.csv` |
| 迭代维 CSV | `需求导出-Gate-RDJ_迭代维度.csv` |

| 输出（每维度 4 份） | 示例 |
|---------------------|------|
| 需求分析完整/精简 | `Gate-RDJ-时间维度-skill-需求分析报告.html` |
| 测试效能汇总 | `Gate-RDJ-时间维度-skill-测试效能汇总报告.html` |
| v4 业务线 | `Gate-RDJ-时间维度-v4-业务线分析报告.html` |

迭代维文件名中 `时间维度` 换为 `迭代维度`。

### 一键命令

```bash
# 新 xlsx → CSV → HTML（两维）
python3 scripts/gate_rdj_from_xlsx.py --xlsx ~/Downloads/需求导出-Gate-RDJ\ \(10\).xlsx --dimension both

# 仅用现有根目录 CSV 重生成（数据源滞后后常用）
python3 scripts/gate_rdj_from_xlsx.py --regenerate --dimension both
# 回退：python3 scripts/generate_gate_rdj_from_csv.py
```

### 模板与脚本

| 项 | 路径 |
|----|------|
| 入口 | `scripts/gate_rdj_from_xlsx.py` |
| 生成核心 | `scripts/generate_gate_rdj_from_csv.py` |
| 指标口径 | `scripts/gate_rdj_metrics.py` |
| v4 patch | `scripts/gate_rdj_v4_patch.py` |
| HTML 模板 | `templates/Gate-RDJ-12-skill-*.html`、`templates/Gate-RDJ-12-v4-业务线分析报告.html` |

### 核心口径（勿随意改）

**修正研发工时 `corrected_rd`**（主站 R/T 分子、原始数据 Tab 研发列）：

```
修正研发 = 技术方案设计与评审估分
         + Σ(各工种开发估分)   # FE/BE/APP/Engine/DATA/WS/WBE/Admin；全空时回退「研发总估分」
         + max(0, 测试估分 − 测试节点估分(去除RD))
```

**测试工时** = `测试总估分(去除RD)`，空则 `QC用例估分 + 测试估分 + 预发测试估分`。

**R/T** = `修正研发 ÷ 测试工时`。

**QC 列拆分（仅展示）**：后缀带 `-QC`/`-qc` → QC 列；后缀不带 `qc` → 开发角色（如 `Change`、`role-s-qa`）。**不调整**系统口径下的研发/测试/R/T（手工修正见第六节「工时修正」）。

**各工种开发估分**（`DEV_ROLE_COLS`）：FE + BE + APP + Engine + DATA + WS + WBE + **Admin开发 估分**；全空回退 `研发总估分`。

**主站去重**：时间维 + 迭代维按 story ID 合并，**条数不可相加**；合并去重后条数见构建日志（当前约 **1924**）。

### 部门归属与部门 R/T（全景 / 四源台账）

| 维度 | 规则 |
|------|------|
| **部门归属** | **有 QC 参与即算**：`depts_for_qc()` 返回全部参与部门；行字段 `depts[]` |
| **部门 R/T** | `_dept_weighted_RT`：story 去重 + **整单** Σ修正研发 ÷ Σ测试 |
| **个人 R/T** | `_person_weighted_RT`：`qc_share_denom = 1/n` |
| **合计 R/T** | 仅累加 `rt != null` 的可算行 |

**横向锚点**（主站 · `1交易-交易组`）：筛选 ≈**284** 条 · 可算 ≈**255** · R/T ≈**2.10**，须与四源部门表 `rt_main` 一致（未手工修正时）。

| 模块 | 文件 |
|------|------|
| 部门列表 | `qc_unified_roster_report.py` → `depts_for_qc`、`dept_display` |
| 部门加权 | `qc_unified_roster_report.py` → `_dept_weighted_RT` |
| 明细筛选 | `portfolio_raw_data.py` → `dept in depts` |
| 部门表展示 | `portfolio_rt_merge.py` ← RT 合并 `var D.dept` |

---

## 二、Gate-AI 项目集报告

```bash
python3 scripts/generate_gate_ai_effort_report.py ~/Downloads/需求导出-Gate-AI项目集\ \(1\).xlsx
```

口径：人头分摊估算人日；R/T = 研发分摊 ÷ 测试分摊（**≠** 主站五阶段 R/T）。全景 Tab **不展示** Gate-AI 估算 R/T。

---

## 三、产研分站全景报告

```bash
python3 scripts/generate_chanfeng_station_report.py
```

分站全景 **不展示** 与主站同套的 R/T / 测试占比。

---

## 四、QC 四源聚合台账

```bash
export MEEGLE_CSV="${MEEGLE_CSV:-data/meegle_view_8bbOlLnNU.csv}"
export MEEGLE_QC_CSV="${MEEGLE_QC_CSV:-data/meegle_page_export.csv}"
PYTHONPATH=scripts python3 scripts/qc_unified_roster_report.py
```

| 产物 | `QC人员名单-主站分站合并需求与RT.html` |

- **部门汇总表**：`dept_mode=True` → 参与即算 + 去重 + 整单
- **人员明细**：仍 1/n 均分
- **关联条数**：部门级 = 去重需求数；人员级可重复

为 **RT 合并报告**（第五节）上游；更新后须重跑 **QC → RT 合并 → 全景**。

---

## 五、Alpha·Meegle 视图

```bash
python3 scripts/build_meegle_report_html.py data/meegle_view_8bbOlLnNU.csv \
  -o Meegle-视图8bbOlLnNU-主站分站-效能报告.html
```

全景 Alpha Tab 同时读 `data/meegle_view_8bbOlLnNU.csv`。

---

## 六、产研效能全景单页（`RD-Efficiency-Portfolio.html`）

八个顶栏 Tab；页内标题 **产研效能报告**；统计截至 **`PORTFOLIO_AS_OF`**（`2026-05-31`）。构建时从源 HTML **抽取**，不重算 R/T（原始数据 Tab 主站行用 `corrected_rd`；**工时修正**为浏览器端覆盖）。

### 数据源滞后 · 一键全链刷新（推荐）

```bash
cd "$GATE_REPORTS_ROOT"
bash gate-rdj-reports/scripts/refresh_portfolio_pipeline.sh
# 或：bash scripts/refresh_portfolio_pipeline.sh（根 scripts 为符号链接时）

PYTHONPATH=gate-rdj-reports/scripts python3 gate-rdj-reports/scripts/verify_portfolio_raw_data.py
```

7 步：Gate-RDJ → 分站 → Gate-AI → Meegle → QC 四源 → RT 合并 → 全景单页。

### 仅合并

```bash
python3 scripts/build_portfolio_single_html.py
PYTHONPATH=scripts python3 scripts/verify_portfolio_raw_data.py
```

### 改什么改哪里

| 需求 | 修改文件 |
|------|----------|
| Tab / 总览 KPI / 主站组合图 | `build_portfolio_single_html.py` |
| Executive 样式 / 按月折叠 CSS | `portfolio_rd_styles.py`（`.dmd-month-*`） |
| 原始数据 / 需求明细 / 按月 JS | `portfolio_raw_data.py` |
| 工时修正 Tab / 弹窗 / 部门表联动 | `portfolio_hour_override.py` |
| R/T 公式说明 / 附录 | `portfolio_formula_core.py`、`portfolio_glossary.py` |
| 口径校验 | `verify_portfolio_raw_data.py` |
| 交付周期 / 四象限 | `rdj_delivery_blocks.py` |
| RT 钻取 / 部门表 | `portfolio_rt_merge.py` |
| 人员编制去重 | `portfolio_dept_stats.py` |
| 横向对账 | `portfolio_data_reconcile.py` |

### 顶栏 Tab

| Tab | 内容 |
|-----|------|
| **总览** | 规模卡、横向对账、RT 四源（部门表 + **需求明细按月折叠**，区块默认展开） |
| **主站** | 时间/迭代维 KPI、组合图、交付效能 |
| **分站** | 执行摘要、分月、业务线、LDT |
| **AI** | Gate-AI KPI/业务线/QC（不展示估算 R/T） |
| **Alpha** | Meegle 摘要 + Top 表 |
| **原始数据** | 见下节 |
| **工时修正** | 主站需求手工覆盖研发/测试（`localStorage`） |
| **人员编制** | `department_stats`（QC 名册已去重） |

### 工时修正 Tab（`portfolio_hour_override.py`）

- **范围**：仅 **主站·Gate-RDJ**；覆盖键 `portfolio_hour_overrides_v1`（`localStorage`，按 Story ID）
- **入口**：顶栏 Tab「工时修正」；总览/原始数据需求明细行的「工时修正」按钮（共用弹窗）
- **行为**：保存后重算单条 R/T；刷新需求明细蓝色统计条、总览 RT 区合计；**客户端重算**部门×四源表「主站 R/T」列及汇总行（`PORTFOLIO_MAIN_ROWS` + `refreshRtDeptTable`）
- **弹窗**：文本输入支持小数；保存后恢复列表滚动位置与月份展开状态
- **不改 CSV / 不重跑 Python**；换浏览器或清缓存后修正丢失

### 原始数据 Tab

- **筛选**：`模块 + 部门` **或** `模块 + 主导业务线`（二选一）
- **部门**：有 QC 参与即算（`depts[]`）
- **默认**：主导业务线 = **RDJ-交易工具**
- **汇总表**：模块 × 部门 × 主导业务线
- **明细表**：Story ID、QC、开发角色、研发/测试/R/T、**工时修正**；按月折叠默认收起；底部 **筛选合计**
- **CSV**：UTF-8 BOM 下载（含 Story ID、开发角色列）

### 需求明细（总览 RT 区）

- 与原始数据同源 `load_raw_records` + 同一套 `PortfolioHourOverrides`
- 筛选：模块 + 部门
- 展示：按月折叠（默认收起）；`<details class="rt-drill-section" open>` 外层默认展开
- 合计 R/T = 可算行 Σ研发 ÷ Σ测试（含手工修正后的显示值）

### 指标与展示规则

| 模块 | R/T | 说明 |
|------|-----|------|
| 主站 Gate-RDJ | ✅ | 修正研发 ÷ 测试工时 |
| 分站 / AI 全景 Tab | ❌ | 仅条数、分月 |
| RT 合并总览 | 四源加权 | 部门：参与即算+去重整单 |
| 需求明细筛选后 | 对齐部门 `rt_main` | 仅可算行 |

### 构建校验

| 脚本 | 时机 |
|------|------|
| `portfolio_validate.py` | 构建前，errors 阻断 |
| `verify_portfolio_raw_data.py` | 构建后建议跑 |

### 故障排查

| 现象 | 处理 |
|------|------|
| 需求明细 R/T ≠ 部门表 | 重跑 QC → RT 合并 → 全景 |
| 部门筛选条数偏少 | 确认 `depts` 参与即算，非首 QC |
| `no var data` | `--regenerate` Gate-RDJ |
| 主站条数 ≠ 1930 | 检查双维 CSV、`dedupe_main_rows` |
| 勿只改生成后 HTML | 改脚本后重跑 `build_portfolio_single_html.py` |
| 工时修正不持久到报告 | 仅 `localStorage`；要固化须改 CSV 或扩展服务端存储 |

---

## RT 四源合并

```bash
python3 scripts/generate_rt_merge_report.py
```

产物：`Gate-RDJ-RT合并分析报告.html`（`var D`）；源含 QC 四源部门表。

---

## department_stats（QC 白名单）

来源：`data/department_stats.html` 或在线 URL。更新后重跑 **QC 四源 → RT 合并 → 全景**。

---

## 可选后续

- PDF：`node scripts/html_to_pdf.js "RD-Efficiency-Portfolio.html"`
- 分析备忘：`data/RT多人QC口径分析.md`、`data/需求导出-Gate-RDJ-*_analysis.md`
