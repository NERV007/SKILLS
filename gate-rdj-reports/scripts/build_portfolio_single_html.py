#!/usr/bin/env python3
"""五份源报告 → 单文件全景 HTML。构建时从源 HTML 抽取数据，不重算 R/T。

规则（用户口径）：
- R/T 仅主站 Gate-RDJ（五阶段实测：修正研发÷测试工时）
- 分站 / AI / Alpha：无 R/T、无测试/排期%、无估分派生占比
- 非主站模块只展示条数、分月/分线分布、交付天、测试分摊绝对值等事实字段
"""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path

from _paths import REPO_ROOT
from portfolio_ai_alpha import (
    ai_biz_table_rows,
    alpha_brief_panels,
    alpha_top_table_rows,
    load_ai_from_html,
    load_alpha_from_csv,
)
from portfolio_rd_styles import RDJ_DASHBOARD_CSS
from portfolio_rt_merge import (
    load_rt_merge_data,
    rt_merge_script_js,
    rt_overview_panel,
)
from portfolio_dept_stats import (
    dept_kpi,
    dept_panel_html,
    load_dept_stats,
)
from portfolio_glossary import portfolio_formula_appendix_html
from portfolio_hour_override import (
    build_hour_override_tab,
    hour_override_shared_js,
)
from portfolio_raw_data import build_demand_detail_overview, build_raw_data_tab
from portfolio_validate import validate_portfolio
from gate_rdj_metrics import dedupe_main_rows
from rdj_delivery_blocks import (
    build_rdj_chart_options,
    extract_rdj_extended,
    parse_delivery_sd,
    rdj_delivery_panel_html,
)

ROOT = REPO_ROOT
ECHARTS = ROOT / "vendor" / "echarts-5.4.3.min.js"
OUT = ROOT / "RD-Efficiency-Portfolio.html"
# 全景报告页眉「统计截至」展示口径（与 department_stats 源文件日期可独立）
PORTFOLIO_AS_OF = "2026-05-31"

C_MAIN, C_BRANCH, C_AI, C_ALPHA, C_DEPT = "#2563eb", "#059669", "#7c3aed", "#ea580c", "#0891b2"
GRID = {"left": "3%", "right": "4%", "bottom": "8%", "top": "16%", "containLabel": True}

# ============ 源文件 ============
SRC = {
    "main_time": ROOT / "Gate-RDJ-时间维度-skill-需求分析报告.html",
    "main_iter": ROOT / "Gate-RDJ-迭代维度-skill-需求分析报告.html",
    "branch": ROOT / "产研分站-全景需求分析报告.html",
    "ai": ROOT / "Gate-AI项目集-测试工时与RT分析报告.html",
    "alpha": ROOT / "Meegle-视图8bbOlLnNU-主站分站-效能报告.html",
    "rt_merge": ROOT / "Gate-RDJ-RT合并分析报告.html",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _var_data(path: Path) -> dict:
    m = re.search(r"var data = (\{.*?\});\s*\n", _read(path), re.S)
    if not m:
        raise ValueError(f"no var data in {path}")
    return json.loads(m.group(1))


def _const_p(path: Path) -> dict:
    m = re.search(r"const P\s*=\s*(\{.*?\});\s*\n", _read(path), re.S)
    if not m:
        raise ValueError(f"no const P in {path}")
    return json.loads(m.group(1))


def _parse_alpha_top(html: str, n: int = 15) -> list[dict]:
    rows = []
    for m in re.finditer(
        r'<tr><td class="rt-num">(\d+)</td><td[^>]*>.*?rel="noopener">(.*?)</a></td>'
        r'<td>(P\d)</td>.*?<td class="rt-num">([\d.]+)</td><td class="rt-num">([\d.]+)</td>',
        html,
        re.S,
    ):
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        rows.append({
            "id": m.group(1),
            "title": title[:48] + ("…" if len(title) > 48 else ""),
            "prio": m.group(3),
            "test_pd": float(m.group(4)),
            "est_pd": float(m.group(5)),
        })
    rows.sort(key=lambda x: -x["test_pd"])
    return rows[:n]


def load_all() -> tuple[dict, dict, dict, dict, dict]:
    dt = _var_data(SRC["main_time"])
    di = _var_data(SRC["main_iter"])
    P = _const_p(SRC["branch"])
    main_time = {
        "label": "完成月 2026-01 ~ 2026-05",
        "kpi": {
            "需求数": sum(x["value"] for x in dt["month_with_chain"]),
            "五阶段工时": round(sum(p["value"] for p in dt["phase_workload"]), 1),
            "测试占比%": round(dt["phase_workload"][3]["pct"], 1),
            "平均R/T": round(dt["avg_rt_ratio"], 2),
            "平均交付周期": round(sum(dt["month_avg_cycle"]) / len(dt["month_avg_cycle"]), 2),
            "Bug数": int(sum(x["value"] for x in dt["bug_by_biz"])),
        },
        "axis": dt["months"],
        "demands": [x["value"] for x in dt["month_with_chain"]],
        "rt": [x["rt_ratio"] for x in dt["monthly_summary"]],
        "test_effort": [x["test_effort"] for x in dt["monthly_summary"]],
        "rd_corrected": [x["rd_corrected"] for x in dt["monthly_summary"]],
        "phase": [(p["name"], p["pct"]) for p in dt["phase_workload"]],
        "priority": dt["by_priority"],
        "req_type": dt["by_req_type"],
        "by_biz": dt["by_biz"][:12],
        "bug_biz": dt["bug_by_biz"][:10],
        "month_chain": dt["month_with_chain"],
        "month_cycle": dt["month_avg_cycle"],
        "insights": [
            f"完成需求 {main_time_kpi_n(dt)} 条；测试工时占比 {dt['phase_workload'][3]['pct']}%（五阶段实测）。",
            f"平均 R/T {dt['avg_rt_ratio']:.2f}（修正研发÷测试）；勿与分站/AI/Alpha 估分口径横比。",
            f"Bug 合计 {int(sum(x['value'] for x in dt['bug_by_biz']))}；Bug 最高业务域：{dt['bug_by_biz'][0]['name']}。",
            f"交付周期（自然日）1→5 月：{', '.join(f'{v:g}' for v in dt['month_avg_cycle'])}。",
        ],
        "ext": extract_rdj_extended(dt, parse_delivery_sd(_read(SRC["main_time"]))),
    }

    main_iter = {
        "label": "迭代 2026-SP1 ~ SP9（已排除 SP10）",
        "kpi": {
            "需求数": sum(x["demands"] for x in di["monthly_summary"]),
            "五阶段工时": round(sum(p["value"] for p in di["phase_workload"]), 1),
            "测试占比%": round(di["phase_workload"][3]["pct"], 1),
            "平均R/T": round(di["avg_rt_ratio"], 2),
            "平均交付周期": round(sum(di["month_avg_cycle"]) / len(di["month_avg_cycle"]), 2),
            "Bug数": int(sum(x["value"] for x in di["bug_by_biz"])),
        },
        "axis": [x["month"].replace("2026-", "") for x in di["monthly_summary"]],
        "demands": [x["demands"] for x in di["monthly_summary"]],
        "rt": [x["rt_ratio"] for x in di["monthly_summary"]],
        "test_effort": [x["test_effort"] for x in di["monthly_summary"]],
        "rd_corrected": [x["rd_corrected"] for x in di["monthly_summary"]],
        "phase": [(p["name"], p["pct"]) for p in di["phase_workload"]],
        "priority": di["by_priority"],
        "req_type": di["by_req_type"],
        "by_biz": di["by_biz"][:12],
        "bug_biz": di["bug_by_biz"][:10],
        "insights": [
            f"迭代维需求 {sum(x['demands'] for x in di['monthly_summary'])} 条（与时间维为同批需求另一切分）。",
            f"SP1 R/T {di['monthly_summary'][0]['rt_ratio']:.2f} 为尖峰，其余 SP 多在 2.2~2.9。",
            f"测试占比 {di['phase_workload'][3]['pct']}%（五阶段实测）。",
        ],
        "ext": extract_rdj_extended(di, parse_delivery_sd(_read(SRC["main_iter"]))),
    }

    line_agg = []
    for r in P.get("line_agg_rows", [])[:12]:
        line_agg.append((
            r["line"],
            r["n"],
            r["sched_sum"],
            r["test_sum"],
            r.get("avg_sched"),
            r.get("avg_test"),
        ))

    br_summary = P.get("summary") or {}
    br_prio = {x["name"]: x["value"] for x in P.get("priority_pie") or []}
    branch = {
        "label": f"创建 {br_summary.get('date_range', '2025-12 ~ 2026-04')}",
        "kpi": {
            "工作项数": P["n"],
            "业务线未填": br_summary.get("missing_line", 0),
            "测试>0条数": br_summary.get("rt_n", 0),
            "P0条数": br_prio.get("P0", 0),
            "P1条数": br_prio.get("P1", 0),
            "P2条数": br_prio.get("P2", 0),
        },
        "month_axis": P["month_bar"]["categories"],
        "month_cnt": P["month_bar"]["values"],
        "month_table": P.get("month_table_rows", []),
        "month_stack": P.get("month_stack", {}),
        "priority": [(x["name"], x["value"]) for x in P["priority_pie"]],
        "line_bar": list(zip(P["line_bar"]["categories"], P["line_bar"]["values"])),
        "line_agg": line_agg,
        "heatmap": P.get("heatmap", {}),
        "creator_bar": list(zip(
            P["creator_bar"]["categories"][:10],
            P["creator_bar"]["values"][:10],
        )),
        "node_pie": [(x["name"], x["value"]) for x in P.get("node_pie", [])],
        "insights": [
            x for x in (P.get("insights") or P.get("closing_bullets") or [])
            if not any(
                k in x
                for k in (
                    "R/T", "测试/排期", "排期/测试", "占排期", "比重约",
                    "近似 R/T", "派生比",
                )
            )
        ] + [
            "本页不展示 R/T 与测试/排期%：无五阶段实测字段，估分缺失时不计算派生比。",
        ],
    }

    ai = load_ai_from_html(SRC["ai"])
    alpha = load_alpha_from_csv()
    return main_time, main_iter, branch, ai, alpha


def main_time_kpi_n(dt: dict) -> int:
    return sum(x["value"] for x in dt["month_with_chain"])


# ============ ECharts ============
def combo_demand_rt(axis, demands, rt, color):
    return {
        "tooltip": {"trigger": "axis"},
        "legend": {"data": ["完成需求数", "R/T"], "top": 4},
        "grid": GRID,
        "xAxis": {"type": "category", "data": axis, "axisLabel": {"fontSize": 11}},
        "yAxis": [
            {"type": "value", "name": "需求数"},
            {"type": "value", "name": "R/T", "splitLine": {"show": False}},
        ],
        "series": [
            {"name": "完成需求数", "type": "bar", "data": demands,
             "itemStyle": {"color": color, "borderRadius": [4, 4, 0, 0]}, "barWidth": "46%"},
            {"name": "R/T", "type": "line", "yAxisIndex": 1, "data": rt, "smooth": True,
             "symbolSize": 7, "lineStyle": {"width": 3, "color": "#f59e0b"},
             "itemStyle": {"color": "#f59e0b"}, "label": {"show": True, "fontSize": 10}},
        ],
    }


def phase_pie(phase, title):
    colors = ["#94a3b8", "#2563eb", "#a5b4fc", "#0ea5e9", "#7dd3fc"]
    return {
        "title": {"text": title, "left": "center", "top": 2,
                  "textStyle": {"fontSize": 12, "color": "#475569"}},
        "tooltip": {"trigger": "item", "formatter": "{b}: {c}%"},
        "legend": {"bottom": 0, "type": "scroll", "textStyle": {"fontSize": 10}},
        "series": [{
            "type": "pie", "radius": ["38%", "62%"], "center": ["50%", "48%"],
            "data": [{"name": n, "value": v, "itemStyle": {"color": colors[i % len(colors)]}}
                     for i, (n, v) in enumerate(phase)],
            "label": {"fontSize": 10, "formatter": "{b}\n{c}%"},
        }],
    }


def test_vs_rd(axis, test, rd):
    return {
        "tooltip": {"trigger": "axis"},
        "legend": {"data": ["测试工时", "修正研发"], "top": 4},
        "grid": GRID,
        "xAxis": {"type": "category", "data": axis, "axisLabel": {"fontSize": 11}},
        "yAxis": {"type": "value", "name": "人天"},
        "series": [
            {"name": "修正研发", "type": "bar", "stack": "t", "data": rd,
             "itemStyle": {"color": "#cbd5e1"}},
            {"name": "测试工时", "type": "bar", "stack": "t", "data": test,
             "itemStyle": {"color": "#0ea5e9"}},
        ],
    }


def pie_chart(pairs, palette=None):
    palette = palette or {"P0": "#dc2626", "P1": "#2563eb", "P2": "#059669", "P3": "#64748b"}
    return {
        "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
        "legend": {"bottom": 0},
        "series": [{
            "type": "pie", "radius": ["40%", "64%"],
            "data": [{"name": n, "value": v,
                      "itemStyle": {"color": palette.get(n, "#888")}}
                     for n, v in pairs],
            "label": {"fontSize": 11, "formatter": "{b} {c}"},
        }],
    }


def hbar(pairs, color, name):
    pairs = list(reversed(pairs))
    return {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "grid": {"left": "3%", "right": "8%", "bottom": "3%", "top": "8%", "containLabel": True},
        "xAxis": {"type": "value"},
        "yAxis": {"type": "category", "data": [p[0] for p in pairs],
                  "axisLabel": {"fontSize": 10}},
        "series": [{"name": name, "type": "bar", "data": [p[1] for p in pairs],
                    "itemStyle": {"color": color, "borderRadius": [0, 4, 4, 0]},
                    "label": {"show": True, "position": "right", "fontSize": 10}}],
    }


def month_stack_chart(ms: dict):
    if not ms or not ms.get("categories"):
        return {"title": {"text": "无数据", "left": "center", "top": "middle"}}
    series = []
    colors = {"P0": "#dc2626", "P1": "#2563eb", "P2": "#059669"}
    for s in ms.get("series", []):
        series.append({
            "name": s["name"], "type": "bar", "stack": "t", "data": s["data"],
            "itemStyle": {"color": colors.get(s["name"], "#94a3b8")},
        })
    return {
        "tooltip": {"trigger": "axis"},
        "legend": {"top": 4},
        "grid": GRID,
        "xAxis": {"type": "category", "data": ms["categories"]},
        "yAxis": {"type": "value", "name": "条数"},
        "series": series,
    }


def heatmap_chart(h: dict):
    if not h or not h.get("data"):
        return {"title": {"text": "无已填业务线样本", "left": "center", "top": "middle"}}
    lines = h.get("lines", [])
    prios = h.get("prios", [])
    data = [[d[1], d[0], d[2]] for d in h["data"]]
    return {
        "tooltip": {"position": "top"},
        "grid": {"left": "12%", "right": "4%", "bottom": "12%", "top": "12%"},
        "xAxis": {"type": "category", "data": prios, "splitArea": {"show": True}},
        "yAxis": {"type": "category", "data": lines, "splitArea": {"show": True}},
        "visualMap": {"min": 0, "max": max(d[2] for d in data) or 1,
                      "calculable": True, "orient": "horizontal", "left": "center", "bottom": 0},
        "series": [{
            "type": "heatmap", "data": data,
            "label": {"show": True, "fontSize": 10},
            "emphasis": {"itemStyle": {"shadowBlur": 6}},
        }],
    }


def month_cnt_chart(axis, cnt, color):
    return {
        "tooltip": {"trigger": "axis"},
        "grid": GRID,
        "xAxis": {"type": "category", "data": axis},
        "yAxis": {"type": "value", "name": "条数"},
        "series": [{"type": "bar", "data": cnt,
                    "itemStyle": {"color": color, "borderRadius": [4, 4, 0, 0]}}],
    }


def ai_est_chart(biz: list):
    """业务线估算人日（与 Gate-AI 源表「估算人日」列一致，非归因堆叠）。"""
    if not biz:
        return {"title": {"text": "无数据", "left": "center"}}
    ordered = sorted(biz, key=lambda x: -x["est"])
    cats = [b["name"] for b in ordered]
    vals = [round(b["est"], 1) for b in ordered]
    bar_grad = {
        "type": "linear", "x": 0, "y": 0, "x2": 1, "y2": 0,
        "colorStops": [
            {"offset": 0, "color": "#c4b5fd"},
            {"offset": 0.5, "color": "#8b5cf6"},
            {"offset": 1, "color": "#5b21b6"},
        ],
    }
    return {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "grid": {"left": 12, "right": 72, "bottom": 24, "top": 8, "containLabel": True},
        "xAxis": {
            "type": "value",
            "name": "估算人日",
            "nameTextStyle": {"color": "#6d28d9", "fontWeight": 600},
            "splitLine": {"lineStyle": {"type": "dashed", "color": "#ede9fe"}},
        },
        "yAxis": {
            "type": "category",
            "data": cats,
            "inverse": True,
            "axisLabel": {"fontSize": 11, "color": "#334155", "width": 120, "overflow": "truncate"},
            "axisLine": {"lineStyle": {"color": "#ddd6fe"}},
        },
        "series": [{
            "name": "估算人日",
            "type": "bar",
            "data": vals,
            "barMaxWidth": 22,
            "itemStyle": {"color": bar_grad, "borderRadius": [0, 6, 6, 0]},
            "label": {
                "show": True,
                "position": "right",
                "fontSize": 11,
                "fontWeight": 700,
                "color": "#5b21b6",
            },
            "emphasis": {"itemStyle": {"color": "#4c1d95"}},
        }],
    }


def ai_biz_cnt_test(biz: list):
    ordered = sorted(biz, key=lambda x: -x["est"])
    cats = [b["name"] for b in ordered]
    demands = [b["demands"] for b in ordered]
    tests = [round(b["test_alloc"], 1) for b in ordered]
    return {
        "tooltip": {"trigger": "axis"},
        "legend": {
            "data": ["需求数", "测试分摊(人日)"],
            "top": 4,
            "textStyle": {"fontSize": 11, "color": "#475569"},
        },
        "grid": {"left": 48, "right": 48, "bottom": 72, "top": 44, "containLabel": True},
        "xAxis": {
            "type": "category",
            "data": cats,
            "axisLabel": {"fontSize": 10, "color": "#475569", "rotate": 32, "interval": 0},
            "axisLine": {"lineStyle": {"color": "#ddd6fe"}},
        },
        "yAxis": [
            {
                "type": "value",
                "name": "需求数",
                "nameTextStyle": {"color": "#7c3aed", "fontWeight": 600},
                "splitLine": {"lineStyle": {"color": "#f5f3ff"}},
            },
            {
                "type": "value",
                "name": "测试分摊(人日)",
                "nameTextStyle": {"color": "#c2410c", "fontWeight": 600},
                "splitLine": {"show": False},
            },
        ],
        "series": [
            {
                "name": "需求数",
                "type": "bar",
                "data": demands,
                "barWidth": "36%",
                "itemStyle": {
                    "color": {
                        "type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
                        "colorStops": [
                            {"offset": 0, "color": "#ddd6fe"},
                            {"offset": 1, "color": "#a78bfa"},
                        ],
                    },
                    "borderRadius": [6, 6, 0, 0],
                },
                "label": {"show": True, "position": "top", "fontSize": 10, "color": "#5b21b6"},
            },
            {
                "name": "测试分摊(人日)",
                "type": "line",
                "yAxisIndex": 1,
                "data": tests,
                "symbol": "circle",
                "symbolSize": 10,
                "lineStyle": {"width": 3, "color": "#ea580c", "shadowColor": "rgba(234,88,12,0.25)", "shadowBlur": 6},
                "itemStyle": {"color": "#ea580c", "borderColor": "#fff", "borderWidth": 2},
                "areaStyle": {"color": "rgba(251,146,60,0.12)"},
                "label": {"show": True, "position": "top", "fontSize": 10, "fontWeight": 600, "color": "#c2410c"},
            },
        ],
    }


def ai_biz_charts_html(ai: dict) -> str:
    """Gate-AI（一）双图区：卡片布局 + 图例说明（图标带汇总数值）。"""
    k = ai.get("kpi") or {}
    est = _fmt_kpi_val(k.get("估算人日Σ"))
    test = _fmt_kpi_val(k.get("测试分摊Σ"))
    dem = _fmt_kpi_val(k.get("参与需求"))
    return f"""
<div class="ai-charts-zone">
  <div class="ai-chart-card ai-chart-est">
    <div class="ai-chart-head">
      <span class="ai-chart-ico" aria-hidden="true">📊</span>
      <div>
        <div class="ai-chart-title">业务线估算人日</div>
        <div class="ai-chart-hint">Σ <b>{est}</b> 人天 · 按业务线降序 · 与源报告（一）表一致</div>
      </div>
    </div>
    {chart("ai_est", 400)}
  </div>
  <div class="ai-chart-card ai-chart-mix">
    <div class="ai-chart-head">
      <span class="ai-chart-ico" aria-hidden="true">📈</span>
      <div>
        <div class="ai-chart-title">需求数 × 测试分摊</div>
        <div class="ai-chart-hint"><b>{dem}</b> 条需求 · 测试分摊 Σ <b>{test}</b> 人天</div>
      </div>
    </div>
    {chart("ai_biz", 400)}
  </div>
</div>"""


def delivery_chart(rows: list):
    cats = [r["name"] for r in rows]
    return {
        "tooltip": {"trigger": "axis"},
        "legend": {"data": ["平均交付天", "中位交付天"], "top": 4},
        "grid": {"left": "3%", "right": "4%", "bottom": "18%", "top": "16%", "containLabel": True},
        "xAxis": {"type": "category", "data": cats, "axisLabel": {"fontSize": 9, "rotate": 28}},
        "yAxis": {"type": "value", "name": "自然日"},
        "series": [
            {"name": "平均交付天", "type": "bar", "data": [r["avg"] for r in rows],
             "itemStyle": {"color": "#a78bfa", "borderRadius": [4, 4, 0, 0]}},
            {"name": "中位交付天", "type": "bar", "data": [r["med"] for r in rows],
             "itemStyle": {"color": "#7c3aed", "borderRadius": [4, 4, 0, 0]}},
        ],
    }


def alpha_rt_bar(split: list) -> dict:
    cats = [s[0].replace("（WEB3/Alpha）", "主站").replace("分站 / 跨线协作", "分站") for s in split]
    rts = [round(s[3], 2) if s[3] is not None else 0 for s in split]
    tests = [s[2] for s in split]
    return {
        "tooltip": {"trigger": "axis"},
        "legend": {"data": ["加权 R/T", "测试节点Σ(pd)"], "top": 4},
        "grid": GRID,
        "xAxis": {"type": "category", "data": cats},
        "yAxis": [
            {"type": "value", "name": "R/T"},
            {"type": "value", "name": "pd", "splitLine": {"show": False}},
        ],
        "series": [
            {"name": "加权 R/T", "type": "bar", "data": rts,
             "itemStyle": {"color": "#7c3aed", "borderRadius": [4, 4, 0, 0]}, "barWidth": "36%"},
            {"name": "测试节点Σ(pd)", "type": "line", "yAxisIndex": 1, "data": tests,
             "smooth": True, "symbolSize": 8, "lineStyle": {"width": 3, "color": "#0ea5e9"}},
        ],
    }


def alpha_test_bar(split: list):
    return {
        "tooltip": {"trigger": "axis"},
        "grid": GRID,
        "xAxis": {"type": "category", "data": [s[0] for s in split]},
        "yAxis": {"type": "value", "name": "测试节点 pd"},
        "series": [{"type": "bar", "data": [s[2] for s in split],
                    "itemStyle": {"color": C_ALPHA, "borderRadius": [4, 4, 0, 0]},
                    "label": {"show": True, "fontSize": 11}}],
    }


def build_options(mt, mi, br, ai, al, ds: dict | None = None, merged_n: int = 0) -> dict:
    opts = {
        "ov_scale": {
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "grid": {"left": "3%", "right": "8%", "bottom": "3%", "top": "10%", "containLabel": True},
            "xAxis": {"type": "value", "name": "需求数"},
            "yAxis": {"type": "category",
                      "data": ["Alpha", "AI", "分站", "主站·去重", "主站·迭代", "主站·时间"],
                      "axisLabel": {"fontSize": 11}},
            "series": [{"type": "bar", "data": [
                {"value": al["kpi"]["需求数"], "itemStyle": {"color": C_ALPHA}},
                {"value": ai["kpi"].get("参与需求", 0), "itemStyle": {"color": C_AI}},
                {"value": br["kpi"]["工作项数"], "itemStyle": {"color": C_BRANCH}},
                {"value": merged_n, "itemStyle": {"color": "#1d4ed8"}},
                {"value": mi["kpi"]["需求数"], "itemStyle": {"color": "#60a5fa"}},
                {"value": mt["kpi"]["需求数"], "itemStyle": {"color": C_MAIN}},
            ], "barWidth": "55%", "itemStyle": {"borderRadius": [0, 4, 4, 0]},
             "label": {"show": True, "position": "right", "fontSize": 12, "fontWeight": "bold", "color": "#0c4a6e"}}],
        },
        "mt_combo": combo_demand_rt(mt["axis"], mt["demands"], mt["rt"], C_MAIN),
        "mt_phase": phase_pie(mt["phase"], "五阶段工时占比"),
        "mt_tvr": test_vs_rd(mt["axis"], mt["test_effort"], mt["rd_corrected"]),
        "mt_prio": pie_chart([(p["name"], p["value"]) for p in mt["priority"]]),
        "mt_req": pie_chart([(p["name"], p["value"]) for p in mt["req_type"]]),
        "mt_biz": hbar([(b["name"], b["value"]) for b in mt["by_biz"]], C_MAIN, "需求数"),
        "mt_bug": hbar([(b["name"], int(b["value"])) for b in mt["bug_biz"]], "#dc2626", "Bug数"),
        "mt_cycle": {
            "tooltip": {"trigger": "axis"},
            "grid": GRID,
            "xAxis": {"type": "category", "data": mt["axis"]},
            "yAxis": {"type": "value", "name": "天"},
            "series": [{"name": "平均交付周期", "type": "line", "data": mt["month_cycle"],
                        "smooth": True, "symbolSize": 8,
                        "lineStyle": {"width": 3, "color": "#0ea5e9"}}],
        },
        "mi_combo": combo_demand_rt(mi["axis"], mi["demands"], mi["rt"], "#60a5fa"),
        "mi_phase": phase_pie(mi["phase"], "五阶段工时占比"),
        "mi_tvr": test_vs_rd(mi["axis"], mi["test_effort"], mi["rd_corrected"]),
        "mi_prio": pie_chart([(p["name"], p["value"]) for p in mi["priority"]]),
        "mi_biz": hbar([(b["name"], b["value"]) for b in mi["by_biz"]], "#60a5fa", "需求数"),
        "br_month": month_cnt_chart(br["month_axis"], br["month_cnt"], C_BRANCH),
        "br_stack": month_stack_chart(br["month_stack"]),
        "br_line": hbar(br["line_bar"][:11], C_BRANCH, "条数"),
        "br_creator": hbar(br["creator_bar"], "#0369a1", "创建条数"),
        "br_node": pie_chart(br["node_pie"], {"需求设计与内审": "#2563eb", "需求排期": "#f59e0b"}),
        "ai_est": ai_est_chart(ai["biz"]),
        "ai_biz": ai_biz_cnt_test(ai["biz"]),
        "ai_deliv": delivery_chart(ai["delivery"]),
        "al_test": alpha_test_bar(al["split"]),
        "al_rt": alpha_rt_bar(al["split"]),
        "al_prio": pie_chart(al["priority"]),
    }
    opts.update(build_rdj_chart_options(mt["ext"], "mt_"))
    opts.update(build_rdj_chart_options(mi["ext"], "mi_"))
    return opts


# KPI 展示：图标 + 是否强调数值
KPI_ICONS: dict[str, str] = {
    "需求数": "📋",
    "工作项数": "📋",
    "参与需求": "📋",
    "五阶段工时": "⏱️",
    "估算人日Σ": "📊",
    "测试分摊Σ": "🧪",
    "测试占比%": "🧪",
    "平均R/T": "⚖️",
    "分摊R/T": "⚖️",
    "加权R/T": "⚖️",
    "平均交付周期": "📅",
    "平均交付天": "📅",
    "中位交付天": "📅",
    "Bug数": "🐛",
    "业务线未填": "🏷️",
    "测试>0条数": "✅",
    "P0条数": "🔴",
    "P1条数": "🟠",
    "P2条数": "🟢",
    "测试节点Σ": "🧪",
    "总估分Σ": "📊",
    "主站条数": "🏠",
    "分站条数": "🌐",
    "命中QC人": "👤",
    "研发分摊Σ": "⚙️",
    "开发总数": "👥",
    "QC人数": "🧪",
    "PD人数": "📌",
    "新分组数": "🗂️",
    "开发测试比": "⚖️",
    "APP-QC": "📱",
}


def _fmt_kpi_val(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        if v == int(v) and abs(v) >= 1000:
            return f"{int(v):,}"
        return f"{v:g}"
    return str(v)


def kpi_cards(kpi: dict, accent: str = "") -> str:
    tiles = []
    for k, v in kpi.items():
        vs = _fmt_kpi_val(v)
        icon = KPI_ICONS.get(k, "📌")
        highlight = accent and any(x in k for x in ("测试", "R/T", "占比", "工时"))
        tile_cls = "kpi-tile" + (" is-highlight" if highlight else "")
        sub = ""
        if k == "分摊R/T":
            sub = '<div class="kpi-tile-foot">研÷测 · Gate-AI</div>'
        elif "R/T" in k and "加权" in k:
            sub = '<div class="kpi-tile-foot">Meegle (Σ总−Σ测)÷Σ测</div>'
        elif k == "测试占比%":
            sub = '<div class="kpi-tile-foot">五阶段实测</div>'
        elif k == "平均R/T":
            sub = '<div class="kpi-tile-foot">修正研发÷测试</div>'
        tiles.append(
            f'<article class="{tile_cls}">'
            f'<div class="kpi-tile-icon" aria-hidden="true">{icon}</div>'
            f'<div class="kpi-tile-body">'
            f'<div class="kpi-tile-label">{escape(k)}</div>'
            f'<div class="kpi-tile-value">{vs}</div>{sub}</div></article>'
        )
    style = f' style="--kpi-accent:{accent}"' if accent else ""
    return f'<div class="kpi-grid"{style}>{"".join(tiles)}</div>'


def ov_module_card(
    title: str,
    accent: str,
    main_val,
    metrics: list[tuple[str, str]],
    icon: str = "📋",
) -> str:
    main_s = _fmt_kpi_val(main_val)
    chips = "".join(
        f'<span class="ov-meta-item"><em>{escape(lbl)}</em><strong>{escape(val)}</strong></span>'
        for lbl, val in metrics
    )
    return f"""
  <article class="ov-tile" style="--ov-accent:{accent}">
    <div class="ov-tile-main">
      <span class="ov-tile-icon" aria-hidden="true">{icon}</span>
      <div class="ov-tile-text">
        <div class="ov-tile-title">{escape(title)}</div>
        <div class="ov-tile-value">{main_s}</div>
      </div>
    </div>
    <div class="ov-tile-meta">{chips}</div>
  </article>"""


def ul(items) -> str:
    return '<ul class="pts">' + "".join(f"<li>{escape(x)}</li>" for x in items) + "</ul>"


def chart(cid: str, h: int = 300) -> str:
    return f'<div class="ec" id="{cid}" data-opt="{cid}" style="height:{h}px"></div>'


def chart_box(title: str, body: str, caption: str = "") -> str:
    cap = f'<p class="chart-caption">{escape(caption)}</p>' if caption else ""
    t = f'<div class="chart-title">{escape(title)}</div>' if title else ""
    return f'<div class="chart-box">{t}{cap}{body}</div>'


def part(title: str, body: str, desc: str = "") -> str:
    d = f'<p class="part-desc">{escape(desc)}</p>' if desc else ""
    return f'<div class="part"><div class="part-title">{escape(title)}</div>{d}{body}</div>'


def section_group(title: str, body: str, desc: str = "", open_panel: bool = True) -> str:
    o = " open" if open_panel else ""
    d = f'<p class="part-desc">{escape(desc)}</p>' if desc else ""
    return (
        f'<details class="section-group panel-section"{o}>'
        f'<summary class="group-title">{escape(title)}</summary>'
        f'<div class="section-group-body">{d}{body}</div></details>'
    )


def panel_intro(items: list[str]) -> str:
    lis = "".join(f"<li>{escape(x)}</li>" for x in items)
    return (
        f'<nav class="panel-intro" aria-label="阅读顺序">'
        f'<div class="panel-intro-label">阅读顺序</div><ol>{lis}</ol></nav>'
    )


def insight_box(title: str, items) -> str:
    return (
        f'<div class="conclusion-box insight-box">'
        f'<div class="conclusion-title">{escape(title)}</div>'
        f'{ul(items)}</div>'
    )


def block_card(title: str, body: str, desc: str = "") -> str:
    d = f'<p class="block-card-desc">{escape(desc)}</p>' if desc else ""
    inner = body
    if 'class="ec"' in body and "chart-box" not in body:
        inner = chart_box("", body)
    elif "<table" in body and "detail-table" not in body and "tbl-wrap" not in body:
        inner = f'<div class="detail-table">{body}</div>'
    return (
        f'<div class="block-card">'
        f'<div class="block-card-title">{escape(title)}</div>{d}{inner}</div>'
    )


def card(title: str, body: str, desc: str = "") -> str:
    inner = body
    if 'class="ec"' in body and "chart-box" not in body:
        inner = chart_box("", body)
    elif ("<table" in body or "tbl-wrap" in body) and "detail-table" not in body:
        if "tbl-wrap" in body:
            inner = body
        else:
            inner = f'<div class="detail-table">{body}</div>'
    return part(title, inner, desc)


def _unwrap_part(fragment: str) -> str:
    m = re.search(
        r'<div class="part"><div class="part-title">[^<]*</div>(.*)</div>\s*$',
        fragment.strip(),
        re.S,
    )
    if not m:
        return fragment
    inner = m.group(1).strip()
    if 'class="ec"' in inner and "chart-box" not in inner:
        inner = chart_box("", inner)
    return inner


def two(a: str, b: str) -> str:
    return f'<div class="chart-row">{_unwrap_part(a)}{_unwrap_part(b)}</div>'


def tbl(headers: list[str], rows: list[list]) -> str:
    th = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = ""
    for row in rows:
        tds = []
        for i, c in enumerate(row):
            if i == 0:
                cls = ' class="l"'
            elif re.match(r"^-?[\d.]+$", str(c)):
                cls = ' class="rt-num"'
            else:
                cls = ""
            tds.append(f"<td{cls}>{escape(str(c))}</td>")
        body += f"<tr>{''.join(tds)}</tr>"
    return (
        f'<div class="tbl-wrap"><table class="data">'
        f"<thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def branch_month_table(br: dict) -> str:
    rows = []
    for r in br.get("month_table", []):
        mom = "—"
        if r.get("mom_pt") is not None:
            mom = f"{r['mom_pt']:+.2f} pt"
        rows.append([
            r["month"], r["n"], f"{r['sched_sum']:g}", f"{r['test_sum']:g}", mom,
        ])
    return tbl(
        ["创建月", "条数", "排期Σ(pd)", "测试估分Σ(pd)", "测试估分环比"],
        rows,
    )


def branch_line_table(br: dict) -> str:
    rows = [
        [l, n, f"{s:g}", f"{t:g}", f"{a:g}" if a is not None else "—",
         f"{b:g}" if b is not None else "—"]
        for l, n, s, t, a, b in br["line_agg"]
    ]
    return tbl(
        ["业务线", "条数", "排期Σ", "测试估分Σ", "均排期/条", "均测试/条"],
        rows,
    )


def ai_biz_table(ai: dict) -> str:
    return tbl(
        ["业务线", "需求", "估算pd", "测试分摊", "测占%"],
        ai_biz_table_rows(ai),
    )


def ai_delivery_table(ai: dict) -> str:
    rows = [
        [d["name"], d["demands"], d["counted"], f"{d['avg']:g}", f"{d['med']:g}"]
        for d in ai.get("delivery", [])
    ]
    return tbl(["所属项目", "需求数", "可计交付", "平均天", "中位天"], rows)


def ai_qc_table(ai: dict) -> str:
    rows = []
    for q in ai.get("qc", [])[:16]:
        rows.append([
            q["name"], q["group"], f"{q['w_dem']:g}", f"{q.get('est', 0):g}",
            f"{q['test']:g}", q.get("test_pct", "—"),
        ])
    return tbl(
        ["QC", "分组", "加权需求", "估算pd", "测试分摊", "测占%"],
        rows,
    )


def alpha_top_table(al: dict) -> str:
    return tbl(
        ["ID", "标题", "优先级", "主/分站", "测试pd", "总估pd", "R/T"],
        alpha_top_table_rows(al),
    )


def calib_table() -> str:
    rows = [
        ["主站 Gate-RDJ", "五阶段实测", "修正研发÷测", "时间/迭代维全量图表"],
        ["分站 · 产研", "排期/测试估分", "—", "条数、分月、分线（无派生比）"],
        ["AI 项目集", "估算×人头分摊", "—", "业务线估算/测试、交付天、QC表"],
        ["Alpha · Meegle", "测试节点+总估分", "(Σ总−Σ测)÷Σ测", "主/分站对照、Meegle R/T"],
    ]
    return tbl(["模块", "数据性质", "R/T 口径", "本页展示"], rows)


def build_panels(
    mt, mi, br, ai, al, rt_data: dict, rt_floor: float, ds: dict | None = None,
    time_gap: int = 0,
) -> tuple[list[tuple[str, str, str]], str, str, str, str]:
    dem_embed, dem_script = build_demand_detail_overview()
    rt_block = rt_overview_panel(rt_data, rt_floor, demand_embed=dem_embed)
    ov_tiles = f"""<div class="ov-grid">
{ov_module_card("主站 · 时间维", C_MAIN, mt['kpi']['需求数'], [
    ("R/T", str(mt['kpi']['平均R/T'])),
    ("测占", f"{mt['kpi']['测试占比%']}%"),
    ("Bug", _fmt_kpi_val(mt['kpi']['Bug数'])),
], "📋")}
{ov_module_card("主站 · 迭代维", "#60a5fa", mi['kpi']['需求数'], [
    ("R/T", str(mi['kpi']['平均R/T'])),
    ("测占", f"{mi['kpi']['测试占比%']}%"),
    ("口径", "SP1~SP9"),
], "🔄")}
{ov_module_card("分站 · 产研", C_BRANCH, br['kpi']['工作项数'], [
    ("未填线", _fmt_kpi_val(br['kpi']['业务线未填'])),
    ("测试>0", _fmt_kpi_val(br['kpi']['测试>0条数'])),
    ("P0/P1", f"{br['kpi']['P0条数']}/{br['kpi']['P1条数']}"),
], "🌐")}
{ov_module_card("AI 项目集", C_AI, ai['kpi'].get('参与需求', '—'), [
    ("估算Σ", _fmt_kpi_val(ai['kpi'].get('估算人日Σ'))),
    ("测试Σ", _fmt_kpi_val(ai['kpi'].get('测试分摊Σ'))),
    ("QC", _fmt_kpi_val(ai['kpi'].get('命中QC人'))),
], "🤖")}
{ov_module_card("Alpha · Meegle", C_ALPHA, al['kpi']['需求数'], [
    ("加权R/T", str(al['kpi']['加权R/T'])),
    ("主站", _fmt_kpi_val(al['kpi']['主站条数'])),
    ("分站", _fmt_kpi_val(al['kpi']['分站条数'])),
], "α")}
</div>"""
    time_gap_note = (
        f"时间维全量 total_demands 比图表 KPI 多 <b>{time_gap}</b> 条（空完成日或轴外月份）。"
        if time_gap else ""
    )
    overview = f"""
<div class="data-note"><b>口径边界</b>：仅主站 Gate-RDJ 在具备五阶段实测时计算 <b>R/T</b>。
分站 / AI <b>不展示 R/T</b>（无五阶段实测或不可算则 —）；Alpha 为 Meegle 视图内加权 R/T。
主站「时间维 / 迭代维」为同一批需求两种切分，条数不可相加；<b>主站·去重</b>（时间+迭代 story ID 合并）= 原始数据 Tab 主站条数。{time_gap_note}</div>
{panel_intro([
    "模块快照：五条业务线规模与核心指标一览",
    "规模与口径：确认各 Tab 数据性质，避免跨模块硬比",
    "R/T 跨源对照：四源加权与洞察（含需求明细）",
    "主站要点：时间维结论收束",
])}
<div class="panel-stack">
{section_group("一、各模块快照", ov_tiles)}
{section_group(
    "二、规模与口径对照",
    two(block_card("各模块需求规模", chart("ov_scale", 320)),
        block_card("四模块口径对照", calib_table())),
    "柱图含主站·去重；时间/迭代/去重三者不可相加。",
)}
{section_group("三、R/T 跨源对照", rt_block, "部门×四源 R/T；含需求明细（模块+部门筛选）。", open_panel=True)}
{insight_box("四、主站时间维要点", mt["insights"])}
</div>
"""

    mt_trend = f"""
  {block_card("月度完成需求 × R/T", chart("mt_combo", 320))}
  {two(block_card("五阶段工时占比", chart("mt_phase", 300)),
       block_card("月度 测试 vs 修正研发（人天）", chart("mt_tvr", 300)))}
  {two(block_card("优先级分布", chart("mt_prio", 280)),
       block_card("需求类型分布", chart("mt_req", 280)))}
  {two(block_card("业务线需求数 Top12", chart("mt_biz", 320)),
       block_card("业务线 Bug 数 Top10", chart("mt_bug", 320)))}
  {two(block_card("月度平均交付周期（自然日）", chart("mt_cycle", 280)),
       block_card("完成月环比", tbl(
           ["月份", "需求数", "环比%"],
           [[x['name'], x['value'],
             "—" if x.get('chain_ratio') is None else f"{x['chain_ratio']:+.1f}%"]
            for x in mt['month_chain']])))}"""
    mi_trend = f"""
  {block_card("迭代完成需求 × R/T", chart("mi_combo", 320))}
  {two(block_card("五阶段工时占比", chart("mi_phase", 300)),
       block_card("迭代 测试 vs 修正研发", chart("mi_tvr", 300)))}
  {two(block_card("优先级分布", chart("mi_prio", 280)),
       block_card("业务线需求数 Top12", chart("mi_biz", 320)))}"""

    main = f"""
<div class="subtabs">
  <button class="subtab active" data-sub="time">时间维度（完成月）</button>
  <button class="subtab" data-sub="iter">迭代维度（所属 SP）</button>
</div>
<div class="subpanel active" data-sub="time">
  <div class="data-note">R/T = 修正研发 ÷ 测试工时（QC+测试+预发）；仅本模块计算。{mt['label']}。</div>
  {kpi_cards(mt['kpi'], C_MAIN)}
  {panel_intro([
    "交付效能：周期 → 全局测占 → 月度指标 → 团队环比 → 四象限",
    "完成趋势：需求/R/T、五阶段结构、业务线与 Bug 分布",
    "关键观察：时间维结论收束",
  ])}
  <div class="panel-stack">
  {rdj_delivery_panel_html("mt_", mt["ext"], C_MAIN)}
  {section_group("二、完成趋势与结构分布", mt_trend)}
  {insight_box("三、关键观察", mt['insights'])}
  </div>
</div>
<div class="subpanel" data-sub="iter">
  <div class="data-note">同一批主站需求按迭代切分。{mi['label']}。</div>
  {kpi_cards(mi['kpi'], "#60a5fa")}
  {panel_intro([
    "交付效能：与完成月同结构，横轴换为所属 SP",
    "迭代趋势：SP 完成量、五阶段与业务线分布",
    "关键观察：迭代维结论收束",
  ])}
  <div class="panel-stack">
  {rdj_delivery_panel_html("mi_", mi["ext"], "#60a5fa")}
  {section_group("二、迭代趋势与结构分布", mi_trend)}
  {insight_box("三、关键观察", mi['insights'])}
  </div>
</div>
"""

    branch = f"""
<div class="data-note"><b>不展示 R/T、测试/排期%</b>：仅有排期/测试估分字段，67.8% 条数测试为 0，缺失不计算派生比。{br['label']}。</div>
{kpi_cards(br['kpi'], C_BRANCH)}
{panel_intro([
    "创建趋势：分月条数与优先级结构",
    "业务线与人力：已填/未填线分布、创建人 Top",
    "排期结构：节点类型、分月事实与业务线聚合",
])}
<div class="panel-stack">
{section_group("一、创建趋势", two(
    block_card("创建月需求条数", chart("br_month", 300)),
    block_card("创建月 × 优先级堆叠", chart("br_stack", 300)),
))}
{section_group("二、业务线与人力", two(
    block_card("业务线分布（含未填）", chart("br_line", 340)),
    block_card("创建人 Top10", chart("br_creator", 300)),
))}
{section_group("三、排期结构", (
    two(block_card("排期节点类型", chart("br_node", 260)),
        block_card("分月事实表（无占比列）", branch_month_table(br)))
    + block_card("已填业务线聚合（仅合计与均值）", branch_line_table(br))
))}
{insight_box("四、关键观察", br['insights'])}
</div>
"""

    ai_kpi = {
        k: v for k, v in ai["kpi"].items()
        if k in (
            "参与需求", "估算人日Σ", "测试分摊Σ", "测试占比%",
            "平均交付天", "中位交付天", "命中QC人",
        )
    }
    ai_panel = f"""
<div class="data-note"><b>Gate-AI 口径</b>：测试/研发为人头分摊（估算×人数比例），<b>非</b> Gate-RDJ 五阶段实测。
<b>本页不展示 AI 分摊 R/T</b>（估分口径不可与主站横比）。{ai['label']}。</div>
{kpi_cards(ai_kpi, C_AI)}
{panel_intro([
    "交付耗时：各项目自然日与平均/中位天",
    "业务线结构：估算人日、测试分摊与测占%",
    "QC 分摊：个人人头口径（勿与 P9 横比）",
])}
<div class="panel-stack">
{section_group("一、各项目交付耗时", (
    block_card("各项目交付明细", ai_delivery_table(ai))
    + block_card("平均/中位交付天", chart("ai_deliv", 360))
))}
{section_group("二、业务线估算与测试", (
    ai_biz_charts_html(ai) + block_card("业务线明细", ai_biz_table(ai))
))}
{section_group("三、QC 个人分摊", ai_qc_table(ai))}
{insight_box("四、关键观察", ai['insights'])}
</div>
"""

    alpha = f"""
<div class="data-note"><b>Meegle 视图口径</b>：测试节点=排期「测试」流程人日；加权 R/T=(Σ总估−Σ测)÷Σ测。
与 Gate-RDJ 修正研发÷测<b>不可硬比绝对值</b>，仅同视图内主站/分站对照。{al['label']}。</div>
{panel_intro([
    "视图摘要：Meegle 已完成需求 KPI 与主/分站拆分",
    "主站 vs 分站：测试节点与加权 R/T 对照",
    "需求结构：优先级与测试节点 Top 需求",
])}
<div class="panel-stack">
{section_group("一、视图摘要", alpha_brief_panels(al) + kpi_cards(al['kpi'], C_ALPHA))}
{section_group("二、主站 vs 分站", two(
    block_card("测试节点人日", chart("al_test", 300)),
    block_card("加权 R/T 对照", chart("al_rt", 300)),
))}
{section_group("三、需求结构与 Top", (
    block_card("优先级分布", chart("al_prio", 280))
    + block_card("测试节点 Top15（含总估与单条 R/T）", alpha_top_table(al))
))}
{insight_box("四、分析摘要", al['insights'])}
</div>
"""

    dept_panel = ""
    if ds:
        dept_panel = dept_panel_html(ds, kpi_cards(dept_kpi(ds), C_DEPT))

    tabs = [
        ("overview", "总览", overview),
        ("main", "主站 Gate-RDJ", main),
        ("branch", "分站 · 产研", branch),
        ("ai", "AI 项目集", ai_panel),
        ("alpha", "Alpha · Meegle", alpha),
    ]
    raw_body, raw_script = build_raw_data_tab()
    tabs.append(("rawdata", "原始数据", raw_body))
    hov_body, hov_script = build_hour_override_tab()
    tabs.append(("houroverride", "工时修正", hov_body))

    if dept_panel:
        tabs.append(("dept", "人员编制", dept_panel))
    override_shared = hour_override_shared_js()
    return tabs, raw_script, dem_script, override_shared, hov_script


def _executive_header_meta(mt: dict, merged_n: int, ds: dict) -> str:
    """页眉关键指标条（面向汇报的一屏抓手）。"""
    kpi = mt.get("kpi") or {}
    rt = kpi.get("平均R/T", "—")
    test_pct = kpi.get("测试占比%", "—")
    demands = kpi.get("需求数", "—")
    as_of = PORTFOLIO_AS_OF
    merged_s = f"{merged_n:,}" if merged_n else "—"
    return f"""
<div class="header-meta" aria-label="关键指标">
  <span class="header-pill"><em>统计截至</em><strong>{escape(str(as_of))}</strong></span>
  <span class="header-pill"><em>主站完成需求</em><strong>{escape(str(demands))}</strong></span>
  <span class="header-pill"><em>主站去重</em><strong>{merged_s}</strong></span>
  <span class="header-pill header-pill--accent"><em>主站 R/T</em><strong>{escape(str(rt))}</strong></span>
  <span class="header-pill"><em>测试占比</em><strong>{escape(str(test_pct))}%</strong></span>
</div>"""


def build_html(
    tabs: list,
    options: dict,
    rt_script: str,
    raw_script: str = "",
    dem_script: str = "",
    override_shared: str = "",
    hov_script: str = "",
    *,
    header_meta: str = "",
) -> str:
    echarts_js = ECHARTS.read_text(encoding="utf-8")
    tab_btns = "".join(
        f'<button type="button" class="nav-tab{" active" if i == 0 else ""}" data-tab="{k}">{escape(t)}</button>'
        for i, (k, t, _) in enumerate(tabs)
    )
    panels = "".join(
        f'<section class="panel{" active" if i == 0 else ""}" data-tab="{k}">{body}</section>'
        for i, (k, _, body) in enumerate(tabs)
    )
    options_json = json.dumps(options, ensure_ascii=False)
    formula_appendix = portfolio_formula_appendix_html()
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta name="theme-color" content="#0369a1"/>
<title>产研效能全景报告</title>
<style>{RDJ_DASHBOARD_CSS}</style>
</head>
<body>
<div class="dashboard">
<header class="header">
<div class="header-top">
  <div class="header-brand">
    <div class="eyebrow">产研效能 · 管理驾驶舱</div>
    <h1>产研效能全景报告</h1>
    <p class="sub">Gate-RDJ 时间/迭代 · 产研分站 · Gate-AI · Meegle · 人员编制 · 五源数据统一口径呈现</p>
  </div>
</div>
{header_meta}
</header>
<nav class="nav-tabs" role="tablist">{tab_btns}</nav>
{panels}
{formula_appendix}
<footer class="footer">
  <div class="footer-main">产研效能全景报告 · 内部管理用途 · 跨模块对比请先阅读附录公式</div>
  <div class="footer-sources">数据来源：Gate-RDJ 时间/迭代维 · 产研分站全景 · Gate-AI 项目集 · Meegle · department_stats</div>
</footer>
</div>
<script>{echarts_js}</script>
<script>
echarts.registerTheme('portfolio', {{
  color: ['#2563eb','#0ea5e9','#7c3aed','#059669','#ea580c','#f59e0b','#ec4899','#6366f1'],
  backgroundColor: 'transparent',
  textStyle: {{ fontFamily: "'PingFang SC','Microsoft YaHei',sans-serif", color: '#334155', fontSize: 12 }},
  title: {{ textStyle: {{ color: '#0369a1', fontWeight: 600, fontSize: 14 }} }},
  legend: {{ textStyle: {{ color: '#4b5563', fontSize: 12 }} }},
  tooltip: {{
    backgroundColor: 'rgba(255,255,255,0.96)',
    borderColor: '#e2e8f0',
    borderWidth: 1,
    textStyle: {{ color: '#334155' }},
    extraCssText: 'box-shadow:0 8px 24px rgba(15,23,42,0.1);border-radius:8px;'
  }},
  categoryAxis: {{
    axisLine: {{ lineStyle: {{ color: '#cbd5e1' }} }},
    axisTick: {{ lineStyle: {{ color: '#cbd5e1' }} }},
    axisLabel: {{ color: '#4b5563', fontSize: 11 }},
    splitLine: {{ lineStyle: {{ color: '#f1f5f9' }} }}
  }},
  valueAxis: {{
    axisLine: {{ show: false }},
    axisTick: {{ show: false }},
    axisLabel: {{ color: '#4b5563', fontSize: 11 }},
    splitLine: {{ lineStyle: {{ color: '#f1f5f9', type: 'dashed' }} }}
  }}
}});
var OPTIONS = {options_json};
function ensure(panel){{
  if(!panel) return;
  panel.querySelectorAll('.ec').forEach(function(el){{
    if(el.offsetParent===null) return;
    if(!el._chart){{
      el._chart = echarts.init(el, 'portfolio', {{ renderer: 'canvas' }});
      var opt = OPTIONS[el.getAttribute('data-opt')];
      if(opt) el._chart.setOption(opt);
    }} else el._chart.resize();
  }});
}}
function activePanel(){{ return document.querySelector('.panel.active'); }}
document.querySelectorAll('.nav-tab').forEach(function(b){{
  b.addEventListener('click', function(){{
    var k=b.getAttribute('data-tab');
    document.querySelectorAll('.nav-tab').forEach(function(x){{x.classList.toggle('active',x===b);}});
    document.querySelectorAll('.panel').forEach(function(p){{p.classList.toggle('active',p.getAttribute('data-tab')===k);}});
    ensure(activePanel());
    if(k==='overview'&&typeof initDemandDetailOverview==='function') initDemandDetailOverview();
    if(k==='rawdata'&&typeof initRawDataTab==='function') initRawDataTab();
    if(k==='houroverride'&&typeof initHourOverrideTab==='function') initHourOverrideTab();
  }});
}});
document.querySelectorAll('.subtab').forEach(function(b){{
  b.addEventListener('click', function(){{
    var k=b.getAttribute('data-sub');
    var scope=b.closest('.panel');
    scope.querySelectorAll('.subtab').forEach(function(x){{x.classList.toggle('active',x===b);}});
    scope.querySelectorAll('.subpanel').forEach(function(p){{p.classList.toggle('active',p.getAttribute('data-sub')===k);}});
    ensure(scope);
  }});
}});
window.addEventListener('resize', function(){{ var ap=activePanel(); if(ap) ensure(ap); }});
{override_shared}
{rt_script}
{dem_script}
{raw_script}
{hov_script}
ensure(activePanel());
if(document.querySelector('.panel[data-tab="overview"].active')&&typeof initDemandDetailOverview==='function') initDemandDetailOverview();
</script>
</body>
</html>
"""


def main():
    dt = _var_data(SRC["main_time"])
    di = _var_data(SRC["main_iter"])
    P = _const_p(SRC["branch"])
    mt, mi, br, ai, al = load_all()
    ds = load_dept_stats()
    ds["as_of"] = PORTFOLIO_AS_OF
    rt_data, rt_floor = load_rt_merge_data(SRC["rt_merge"])
    csv_time = ROOT / "需求导出-Gate-RDJ_时间维度.csv"
    csv_iter = ROOT / "需求导出-Gate-RDJ_迭代维度.csv"
    merged_n = (
        len(dedupe_main_rows([str(csv_iter), str(csv_time)]))
        if csv_time.is_file() and csv_iter.is_file()
        else 0
    )
    time_kpi = int(mt["kpi"]["需求数"])
    time_total = int(dt.get("total_demands") or time_kpi)
    time_gap = time_total - time_kpi
    opts = build_options(mt, mi, br, ai, al, ds, merged_n=merged_n)
    errors, warns = validate_portfolio(mt, mi, br, ai, al, dt, di, P, opts, rt_data=rt_data)
    seen_warn: set[str] = set()
    deduped_warns: list[str] = []
    for w in warns:
        if w not in seen_warn:
            seen_warn.add(w)
            deduped_warns.append(w)
    warns = deduped_warns
    if errors:
        print("  数据校验失败（阻断构建）:")
        for e in errors:
            print(f"    ✗ {e}")
        raise SystemExit(1)
    tabs, raw_script, dem_script, override_shared, hov_script = build_panels(
        mt, mi, br, ai, al, rt_data, rt_floor, ds, time_gap=time_gap
    )
    rt_script = rt_merge_script_js(rt_data, rt_floor)
    header_meta = _executive_header_meta(mt, merged_n, ds)
    OUT.write_text(
        build_html(
            tabs,
            opts,
            rt_script,
            raw_script,
            dem_script,
            override_shared,
            hov_script,
            header_meta=header_meta,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {OUT.name} ({OUT.stat().st_size:,} bytes)")
    print(f"  charts: {len(opts)}  panels: {len(tabs)}")
    rdj_keys = [k for k in opts if k.startswith(("mt_", "mi_")) and k not in (
        "mt_combo", "mt_phase", "mt_tvr", "mt_prio", "mt_req", "mt_biz", "mt_bug", "mt_cycle",
        "mi_combo", "mi_phase", "mi_tvr", "mi_prio", "mi_biz",
    )]
    print(f"  Gate-RDJ 扩展图: {len(rdj_keys)} ({', '.join(sorted(rdj_keys)[:6])}…)")
    if warns:
        print("  校验警告:")
        for w in warns:
            print(f"    ⚠ {w}")
    else:
        print("  数据校验: 全部通过")


if __name__ == "__main__":
    main()
