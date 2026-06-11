"""Gate-RDJ 时间/迭代维：交付周期、测试占比、四象限等扩展块（从 var data 派生，与源报告 JS 同口径）。"""

from __future__ import annotations

import json
import math
import re
from html import escape
from typing import Any

SHORT_PHASES = ["设计评审", "研发", "QC用例", "测试", "预发"]
PHASE_COLORS = ["#0ea5e9", "#38bdf8", "#7dd3fc", "#0369a1", "#0284c7"]
FLOW_STAGES = ["需求阶段", "研发阶段", "测试阶段", "预发测试", "发布上线"]
FLOW_LABELS = ["需求", "研发", "测试", "预发测试", "发布上线"]
FLOW_COLORS = ["#7c3aed", "#0369a1", "#0ea5e9", "#f59e0b", "#10b981"]
EFFORT_COLORS = ["#7c3aed", "#d97706", "#059669", "#ec4899", "#0ea5e9"]
PW_TO_STAGE = {
    "技术方案设计与评审": "需求阶段",
    "研发": "研发阶段",
    "测试": "测试阶段",
    "预发测试": "预发测试",
}


def parse_delivery_sd(html: str) -> dict | None:
    m = re.search(r"var sd = (\{.*?\});", html, re.S)
    if not m:
        return None
    return json.loads(m.group(1))


def _months_and_demands(d: dict) -> tuple[list[str], list[int], list[float | None]]:
    mc = d.get("month_with_chain") or []
    if mc:
        months = [x["name"] for x in mc]
        demands = [int(x["value"]) for x in mc]
        chains = [x.get("chain_ratio") for x in mc]
        return months, demands, chains
    months = list(d.get("months") or [])
    ms = d.get("monthly_summary") or []
    demands = [int(x["demands"]) for x in ms] if ms else [0] * len(months)
    chains = [None] * len(months)
    return months, demands, chains


TEAM_MOM_COLORS = [
    "#2563eb", "#059669", "#ea580c", "#7c3aed", "#dc2626",
    "#0891b2", "#ca8a04", "#be185d", "#4f46e5", "#0d9488",
]


def _mom_chains(vals: list[float]) -> tuple[list[float | None], list[float | None]]:
    rel: list[float | None] = []
    pt: list[float | None] = []
    for i, v in enumerate(vals):
        if i == 0:
            rel.append(None)
            pt.append(None)
            continue
        prev = vals[i - 1]
        pt.append(round(v - prev, 1))
        rel.append(round((v - prev) / prev * 100, 1) if prev > 0 else None)
    return rel, pt


def _heat_month_totals(d: dict, n_months: int) -> tuple[list[float], list[float]]:
    """month_totals, month_test_related (QC+测试+预发)."""
    hmp = d.get("heat_month_phase") or {}
    totals = [0.0] * n_months
    test_rel = [0.0] * n_months
    for item in hmp.get("data") or []:
        if not item or len(item) < 3:
            continue
        mi, pi, v = int(item[0]), int(item[1]), float(item[2])
        if 0 <= mi < n_months:
            totals[mi] += v
            if pi in (2, 3, 4):
                test_rel[mi] += v
    return totals, test_rel


def extract_rdj_extended(d: dict, delivery_sd: dict | None = None) -> dict:
    months, demands, demand_chains = _months_and_demands(d)
    n = len(months)
    month_totals, month_test_work = _heat_month_totals(d, n)
    test_pcts = [
        round(month_test_work[i] / month_totals[i] * 1000) / 10
        if month_totals[i] > 0
        else 0.0
        for i in range(n)
    ]
    avg_test_pct = round(sum(test_pcts) / n, 2) if n else 0.0

    cycles = list(d.get("month_avg_cycle") or [0.0] * n)
    cycles_wd = list(d.get("month_avg_cycle_wd") or [0.0] * n)
    mtt = d.get("month_test_totals") or []
    test_eff = []
    for i in range(n):
        tv = mtt[i]["value"] if i < len(mtt) and isinstance(mtt[i], dict) else (
            mtt[i] if i < len(mtt) else demands[i]
        )
        test_eff.append(
            round(demands[i] / float(tv) * 1000) / 1000 if tv and float(tv) > 0 else 0.0
        )

    pw = d.get("phase_workload") or []
    summary = d.get("duration_score_summary") or {}
    avg_dur = float(summary.get("avg_duration") or 0)
    avg_dur_wd = float(summary.get("avg_duration_wd") or 0)
    total_pct = sum(p.get("pct", 0) for p in pw) or 100.0
    phase_days = [
        round(avg_dur * (p.get("pct", 0) / total_pct), 1) for p in pw
    ]
    total_days = sum(phase_days) or 1.0
    pct_per_phase = [round(d / total_days * 1000) / 10 for d in phase_days]

    biz_list = d.get("biz_list") or []
    top_biz = sorted(biz_list, key=lambda x: -(x.get("demand_count") or 0))[:12]

    # biz_month_phase_3d → 测试相关占比表
    raw3d = d.get("biz_month_phase_3d") or []
    biz_phase: dict[str, dict[int, list[float]]] = {}
    for row in raw3d:
        if len(row) < 3:
            continue
        name, mi, phases = row[0], int(row[1]), list(row[2])
        biz_phase.setdefault(name, {})[mi] = phases

    month_avg_pct: list[list[float]] = []
    for m in range(n):
        row = []
        for p in range(5):
            row.append(
                round(month_test_work[m] / month_totals[m] * 1000) / 10
                if month_totals[m] > 0 and p in (2, 3, 4)
                else 0.0
            )
        # 团队各阶段占比（来自 heat_month_phase）
        hmp = d.get("heat_month_phase") or {}
        phase_vals = [0.0] * 5
        for item in hmp.get("data") or []:
            if item and int(item[0]) == m:
                pi = int(item[1])
                if 0 <= pi < 5:
                    phase_vals[pi] = float(item[2])
        tot = sum(phase_vals) or 1.0
        month_avg_pct.append([round(v / tot * 1000) / 10 for v in phase_vals])

    def _biz_month_test_pcts(name: str) -> list[float]:
        pcts = []
        for m in range(n):
            phases = (biz_phase.get(name) or {}).get(m, [0, 0, 0, 0, 0])
            tot = sum(phases)
            tr = (phases[2] + phases[3] + phases[4]) if len(phases) >= 5 else 0
            pcts.append(round(tr / tot * 1000) / 10 if tot > 0 else 0.0)
        return pcts

    biz_rows_table = []
    for b in top_biz:
        name = b["name"]
        month_pcts = _biz_month_test_pcts(name)
        month_devs = [round(mp - test_pcts[m], 1) for m, mp in enumerate(month_pcts)]
        valid = [p for p in month_pcts if p > 0]
        avg_biz = round(sum(valid) / len(valid), 1) if valid else 0.0
        biz_rows_table.append({
            "name": name,
            "avg_pct": avg_biz,
            "month_pcts": month_pcts,
            "month_devs": month_devs,
        })

    team_mom_rows = []
    for b in biz_list:
        name = b["name"]
        month_pcts = _biz_month_test_pcts(name)
        chains_rel, chains_pt = _mom_chains(month_pcts)
        team_mom_rows.append({
            "name": name,
            "test_total": float(b.get("test_total") or 0),
            "month_pcts": month_pcts,
            "chains_rel": chains_rel,
            "chains_pt": chains_pt,
        })
    team_mom_rows.sort(key=lambda x: -x["test_total"])

    quadrant = []
    for b in biz_list:
        dc = b.get("avg_delivery_cycle_days") or 0
        cnt = b.get("demand_count") or 0
        if dc > 0 and cnt >= 20:
            quadrant.append({
                "name": b["name"],
                "cycle": float(dc),
                "cycle_wd": float(b.get("avg_delivery_cycle_wd") or 0),
                "count": int(cnt),
                "total_score": float(b.get("total_score") or 0),
                "test_total": float(b.get("test_total") or 0),
            })

    quadrant_pc = []
    for q in quadrant:
        if q["test_total"] > 0:
            q2 = dict(q)
            q2["per_test"] = round(q["total_score"] / q["test_total"] * 100) / 100
            quadrant_pc.append(q2)

    return {
        "months": months,
        "demands": demands,
        "demand_chains": demand_chains,
        "month_totals": [round(x) for x in month_totals],
        "month_test_work": [round(x) for x in month_test_work],
        "test_pcts": test_pcts,
        "avg_test_pct": avg_test_pct,
        "cycles": cycles,
        "cycles_wd": cycles_wd,
        "test_eff": test_eff,
        "phase_workload": pw,
        "phase_days": phase_days,
        "pct_per_phase": pct_per_phase,
        "duration_summary": summary,
        "biz_rows_table": biz_rows_table,
        "team_mom_rows": team_mom_rows,
        "month_avg_phase_pct": month_avg_pct,
        "quadrant": quadrant,
        "quadrant_per_capita": quadrant_pc,
        "delivery_sd": delivery_sd or {},
    }


def _act_bar_html(act: float) -> str:
    if act > 80:
        color, bg = "#dc2626", "#fef2f2"
    elif act > 50:
        color, bg = "#d97706", "#fffbeb"
    else:
        color, bg = "#059669", "#f0fdf4"
    w = min(max(act, 0), 100)
    return (
        f'<div class="dc-act-track" style="background:{bg}">'
        f'<div class="dc-act-fill" style="width:{w}%;background:{color}"></div></div>'
        f'<div class="dc-act-lbl" style="color:{color}">活跃度 {act:g}%</div>'
    )


def delivery_cycle_html(ext: dict, accent: str) -> str:
    pw = ext["phase_workload"]
    summary_ds = ext["duration_summary"]
    sd = ext.get("delivery_sd") or {}
    sd_sum = sd.get("summary") or {}
    pw_map = {p["name"]: p for p in pw}
    stage_effort = {st: {"value": 0, "pct": 0} for st in FLOW_STAGES}
    for k, st in PW_TO_STAGE.items():
        if k in pw_map:
            stage_effort[st] = pw_map[k]

    total_days = sum((sd_sum.get(s) or {}).get("avg", 0) for s in FLOW_STAGES) or 1.0
    total_wl = sum(p.get("value", 0) for p in pw)
    total_dem = sum(ext.get("demands") or []) or 1
    avg_hpd = round(total_wl / total_dem, 2)
    cycle_avg = (sd_sum.get("交付周期") or {}).get("avg") or summary_ds.get("avg_duration", "—")
    avg_wd = summary_ds.get("avg_duration_wd", "—")

    flow = (
        '<div class="dc-unified-flow">'
        '<div class="dc-flow-end dc-flow-start">'
        '<div class="dc-end-inner">需求<br/>创建</div></div>'
    )
    for i, st in enumerate(FLOW_STAGES):
        sm = sd_sum.get(st) or {}
        d = sm.get("avg", ext["phase_days"][i] if i < len(ext["phase_days"]) else 0)
        act = sm.get("activity", 0)
        avg_e = sm.get("avg_effort", 0)
        eff = stage_effort.get(st) or {"value": 0, "pct": 0}
        e_val, e_pct = eff.get("value", 0), eff.get("pct", 0)
        pct = round(d / total_days * 100) if total_days else 0
        flow += (
            '<div class="dc-flow-arrow"><svg width="28" height="20" viewBox="0 0 28 20">'
            '<path d="M0 10 L20 10" stroke="#cbd5e1" stroke-width="2" fill="none"/>'
            '<path d="M16 5 L22 10 L16 15" stroke="#cbd5e1" stroke-width="2" fill="none"/>'
            "</svg></div>"
            f'<div class="dc-stage-card" style="border-top-color:{FLOW_COLORS[i]}">'
            f'<div class="dc-stage-title" style="color:{FLOW_COLORS[i]}">{escape(FLOW_LABELS[i])}</div>'
            '<div class="dc-stage-block dc-block-sched">'
            '<div class="dc-block-lbl">📅 工期</div>'
            f'<div class="dc-block-val">{d:g}<span> 天</span></div>'
            f'<div class="dc-block-sub">占比 {pct}%</div></div>'
            '<div class="dc-stage-block dc-block-effort">'
            '<div class="dc-block-lbl">⏱️ 工时</div>'
            f'<div class="dc-block-val dc-val-sm">{avg_e:.2f}<span> 人天</span></div>'
            f'<div class="dc-block-sub">占比 {e_pct}%<span class="dc-total-eff">总{round(e_val):g}</span></div></div>'
            f"{_act_bar_html(float(act))}</div>"
        )
    flow += (
        '<div class="dc-flow-arrow"><svg width="28" height="20" viewBox="0 0 28 20">'
        '<path d="M0 10 L20 10" stroke="#cbd5e1" stroke-width="2" fill="none"/>'
        '<path d="M16 5 L22 10 L16 15" stroke="#cbd5e1" stroke-width="2" fill="none"/>'
        "</svg></div>"
        '<div class="dc-flow-end dc-flow-done">'
        '<div class="dc-end-inner">交付<br/>完成</div></div></div>'
    )

    sched_segs = ""
    for i, st in enumerate(FLOW_STAGES):
        sm = sd_sum.get(st) or {}
        d = sm.get("avg", 0)
        pct = round(d / total_days * 100) if total_days else 0
        w = max(pct, 2)
        sched_segs += (
            f'<div class="dc-seg-bar" style="flex:{w};background:{FLOW_COLORS[i]}" '
            f'title="{escape(FLOW_LABELS[i])} {d:g}天 {pct}%">'
            f"{escape(FLOW_LABELS[i])} {d:g}天 {pct}%</div>"
        )
    effort_segs = ""
    for i, p in enumerate(pw):
        pct = p.get("pct", 0)
        sn = (
            p["name"]
            .replace("技术方案设计与评审", "设计评审")
            .replace("QC用例设计与评审", "QC评审")
            .replace("预发测试", "预发")
        )
        w = max(float(pct), 2)
        effort_segs += (
            f'<div class="dc-seg-bar" style="flex:{w};background:{EFFORT_COLORS[i % 5]}" '
            f'title="{escape(sn)} {pct}%">{escape(sn)} {pct}%</div>'
        )

    short = SHORT_PHASES[: len(pw)]
    rows = ""
    for i, p in enumerate(pw):
        sm = sd_sum.get(FLOW_STAGES[i]) if i < len(FLOW_STAGES) else {}
        d = sm.get("avg", ext["phase_days"][i] if i < len(ext["phase_days"]) else 0)
        avg_ph = round(float(p.get("value", 0)) / total_dem, 2)
        act = sm.get("activity", round(avg_ph / d * 100, 1) if d else 0)
        rows += (
            f"<tr><td class='col-phase'>{escape(short[i])}</td>"
            f"<td>{d:g}</td><td>{ext['pct_per_phase'][i]}%</td>"
            f"<td>{p.get('value', 0):g}</td><td>{avg_ph}</td><td>{act:g}%</td></tr>"
        )

    return f"""
<div class="delivery-cycle-wrap">
  <h4>需求交付周期全流程</h4>
  <div class="dc-kpi-row">
    <div class="dc-kpi-badge dc-kpi-blue">
      <span class="dc-kpi-ico" aria-hidden="true">📅</span>
      <div class="dc-kpi-body">
        <div class="dc-kpi-lbl">平均工期</div>
        <div class="dc-kpi-num">{cycle_avg}<span class="dc-kpi-unit">天</span></div>
        <div class="dc-kpi-sub">{avg_wd} 工作日</div>
      </div>
    </div>
    <div class="dc-kpi-badge dc-kpi-amber">
      <span class="dc-kpi-ico" aria-hidden="true">⏱️</span>
      <div class="dc-kpi-body">
        <div class="dc-kpi-lbl">平均工时/需求</div>
        <div class="dc-kpi-num">{avg_hpd}<span class="dc-kpi-unit">人天</span></div>
        <div class="dc-kpi-sub">总工时 {total_wl:,.0f} 人天</div>
      </div>
    </div>
  </div>
  <div class="dc-caliber-bar">工期 = 各阶段日历天（来自 delivery_sd）；工时 = 五活动估分人天（phase_workload）；活跃度 = 平均工时/需求 ÷ 阶段工期。</div>
  {flow}
  <div class="dc-two-bars">
    <div class="dc-bar-panel dc-panel-sched">
      <div class="dc-bar-panel-title"><span>📅</span> 工期占比（按阶段·日历天）</div>
      <div class="dc-seg-row">{sched_segs}</div>
    </div>
    <div class="dc-bar-panel dc-panel-effort">
      <div class="dc-bar-panel-title"><span>⏱️</span> 工时占比（按活动·估分人天）</div>
      <div class="dc-seg-row">{effort_segs}</div>
    </div>
  </div>
  <div class="dc-phase-tips">
    <table><thead><tr>
      <th class="col-phase">阶段</th><th>工期(天)</th><th>工期占比</th>
      <th>总工时(人天)</th><th>平均工时/需求</th><th class="col-ratio">活跃度(%)</th>
    </tr></thead><tbody>{rows}</tbody></table>
  </div>
</div>"""


def _fmt_mom_cell(val: float | None, kind: str = "rel") -> str:
    if val is None:
        return "<td class='ch'>—</td>"
    if kind == "pt":
        color = "#dc2626" if val > 1 else "#16a34a" if val < -1 else "#64748b"
        return f"<td class='ch' style='color:{color}'>{val:+.1f}pp</td>"
    color = "#dc2626" if val > 10 else "#16a34a" if val < -10 else "#64748b"
    return f"<td class='ch' style='color:{color}'>{val:+.1f}%</td>"


def team_mom_summary_table_html(ext: dict) -> str:
    rows = ext.get("team_mom_rows") or []
    months = ext["months"]
    if not rows or not months:
        return ""
    last_i = len(months) - 1
    prev_i = last_i - 1 if last_i > 0 else None
    last_m = months[last_i]
    prev_m = months[prev_i] if prev_i is not None else "—"
    body = ""
    for r in rows:
        lp = r["month_pcts"][last_i] if last_i < len(r["month_pcts"]) else 0
        pp = r["month_pcts"][prev_i] if prev_i is not None and prev_i < len(r["month_pcts"]) else None
        cr = r["chains_rel"][last_i] if last_i < len(r["chains_rel"]) else None
        cp = r["chains_pt"][last_i] if last_i < len(r["chains_pt"]) else None
        body += (
            f"<tr><td class='l'>{escape(r['name'].replace('RDJ-', ''))}</td>"
            f"<td>{r['test_total']:g}</td>"
            f"<td>{pp if pp is not None else '—'}{'%' if pp is not None else ''}</td>"
            f"<td><b>{lp:g}%</b></td>"
            f"{_fmt_mom_cell(cr, 'rel')}{_fmt_mom_cell(cp, 'pt')}</tr>"
        )
    return (
        f'<div class="detail-table team-mom-summary"><table>'
        f"<thead><tr><th>团队</th><th>测试工时Σ</th><th>{escape(prev_m)}占比</th>"
        f"<th>{escape(last_m)}占比</th><th>环比(相对%)</th><th>环比(pt)</th></tr></thead>"
        f"<tbody>{body}</tbody></table></div>"
    )


def team_mom_pivot_table_html(ext: dict) -> str:
    rows = ext.get("team_mom_rows") or []
    months = ext["months"]
    if not rows or not months:
        return ""
    head = "<th class='sticky-col'>团队</th>"
    head += "".join(f"<th colspan='2'>{escape(m)}</th>" for m in months)
    sub = "<th class='sticky-col'></th>" + "".join("<th>占比</th><th>环比</th>" for _ in months)
    body = ""
    for r in rows:
        cells = f"<td class='l sticky-col'>{escape(r['name'].replace('RDJ-', ''))}</td>"
        for i, mp in enumerate(r["month_pcts"]):
            cr = r["chains_rel"][i] if i < len(r["chains_rel"]) else None
            cells += f"<td>{mp:g}%</td>{_fmt_mom_cell(cr, 'rel')}"
        body += f"<tr>{cells}</tr>"
    global_cells = "<td class='l sticky-col'><b>【全局】</b></td>"
    g_rel, _ = _mom_chains(ext["test_pcts"])
    for i, mp in enumerate(ext["test_pcts"]):
        global_cells += f"<td><b>{mp:g}%</b></td>{_fmt_mom_cell(g_rel[i], 'rel')}"
    return (
        f'<div class="detail-table team-mom-pivot-wrap"><table class="team-mom-pivot">'
        f"<thead><tr>{head}</tr><tr>{sub}</tr></thead>"
        f"<tbody><tr class='tp-global-row'>{global_cells}</tr>{body}</tbody></table></div>"
    )


def chart_team_mom_trend(ext: dict, top_n: int = 8) -> dict:
    rows = ext.get("team_mom_rows") or []
    months = ext["months"]
    series: list[dict] = [{
        "name": "【全局】",
        "type": "line",
        "data": ext["test_pcts"],
        "symbol": "circle",
        "symbolSize": 6,
        "lineStyle": {"type": "dashed", "width": 2, "color": "#64748b"},
        "itemStyle": {"color": "#64748b"},
        "z": 1,
    }]
    for i, r in enumerate(rows[:top_n]):
        color = TEAM_MOM_COLORS[i % len(TEAM_MOM_COLORS)]
        nm = r["name"].replace("RDJ-", "")
        series.append({
            "name": nm,
            "type": "line",
            "data": r["month_pcts"],
            "symbol": "circle",
            "symbolSize": 5,
            "lineStyle": {"width": 2, "color": color},
            "itemStyle": {"color": color},
            "z": 2,
        })
    return {
        "title": {
            "text": "各团队测试相关占比 · 分月趋势",
            "subtext": f"Top{min(top_n, len(rows))} 团队（按全期测试工时）+ 全局虚线",
            "left": "center",
            "top": 4,
            "textStyle": {"fontSize": 13, "color": "#0369a1", "fontWeight": 700},
            "subtextStyle": {"fontSize": 10, "color": "#94a3b8"},
        },
        "tooltip": {"trigger": "axis"},
        "legend": {
            "type": "scroll",
            "bottom": 0,
            "textStyle": {"fontSize": 9},
        },
        "grid": {"left": 48, "right": 24, "top": 56, "bottom": 52},
        "xAxis": {"type": "category", "data": months, "axisLabel": {"fontSize": 10}},
        "yAxis": {
            "type": "value",
            "name": "占比 %",
            "axisLabel": {"fontSize": 10, "formatter": "{value}%"},
        },
        "series": series,
    }


def team_mom_panel_html(prefix: str, ext: dict) -> str:
    p = prefix
    pivot = team_mom_pivot_table_html(ext)
    return f"""
<div class="rdj-box rdj-box-white team-mom-wrap">
  <div class="rdj-box-h">
    <span class="rdj-emoji">📊</span>
    <span class="rdj-box-title">团队内月度环比 · 测试相关占比</span>
    <span class="rdj-box-hint">（QC+测试+预发）÷ 五阶段总工时</span>
  </div>
  <p class="table-caption" style="margin:0 0 12px;">
    各业务线按全期测试工时降序；<b>环比(相对%)</b>=(本期占比−上期占比)÷上期占比；
    <b>环比(pt)</b>=百分点差。上表看 vs 团队偏差，本块看团队自身逐月变化。
  </p>
  {chart(f"{p}team_mom", 360)}
  {team_mom_summary_table_html(ext)}
  <details class="team-mom-details">
    <summary>展开 · 各团队分月透视表（占比 + 环比）</summary>
    {pivot}
  </details>
</div>
"""


def biz_test_pct_table_html(ext: dict) -> str:
    months = ext["months"]
    head = "<th>业务线</th><th>均测占比</th>"
    head += "".join(f"<th colspan='2'>{escape(m)}</th>" for m in months)
    sub = "<th></th><th></th>" + "".join("<th>当月</th><th>vs团队</th>" for _ in months)
    body = ""
    for r in ext["biz_rows_table"]:
        cells = (
            f"<td class='l'>{escape(r['name'].replace('RDJ-',''))}</td>"
            f"<td><b>{r['avg_pct']}%</b></td>"
        )
        for mp, dev in zip(r["month_pcts"], r["month_devs"]):
            dc = "#dc2626" if dev > 2 else "#16a34a" if dev < -2 else "#64748b"
            arr = "↑" if dev > 0 else "↓" if dev < 0 else "→"
            cells += f"<td>{mp}%</td><td style='color:{dc}'>{arr}{dev:+.1f}pp</td>"
        body += f"<tr>{cells}</tr>"
    team_tr = ext["test_pcts"]
    team_cells = "<td class='l'><b>团队测试相关</b></td><td>—</td>"
    team_cells += "".join(f"<td colspan='2'>{v}%</td>" for v in team_tr)
    team_row = f"<tr>{team_cells}</tr>"
    return (
        f'<div class="detail-table biz-pct-wrap"><table class="biz-pct">'
        f"<thead><tr>{head}</tr><tr>{sub}</tr></thead>"
        f"<tbody>{team_row}{body}</tbody></table></div>"
        f'<p class="table-caption">测试相关占比 = (QC+测试+预发)÷五阶段总工时；vs团队为当月偏差(pp)。</p>'
    )


def chart_test_pct_trend(ext: dict) -> dict:
    months, pcts, avg = ext["months"], ext["test_pcts"], ext["avg_test_pct"]
    lo = math.floor(min(pcts) - 2) if pcts else 28
    hi = math.ceil(max(pcts) + 2) if pcts else 42
    labels = []
    for i, v in enumerate(pcts):
        diff = v - avg
        arrow = "↑" if diff > 0 else ("↓" if diff < 0 else "")
        labels.append(f"{v:g}%\n{arrow}")
    return {
        "title": {
            "text": "测试相关工时占比趋势",
            "subtext": "口径：分子=QC+测试+预发，分母=设计评审+研发+QC+测试+预发",
            "left": "center",
            "top": 4,
            "textStyle": {"fontSize": 14, "color": "#b91c1c", "fontWeight": 700},
            "subtextStyle": {"fontSize": 10, "color": "#94a3b8"},
        },
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 50, "right": 30, "top": 52, "bottom": 40},
        "xAxis": {"type": "category", "data": months, "axisLabel": {"fontSize": 11}},
        "yAxis": {
            "type": "value",
            "name": "占比 %",
            "min": lo,
            "max": hi,
            "axisLabel": {"fontSize": 11, "formatter": "{value}%"},
        },
        "series": [{
            "name": "测试工时占比",
            "type": "line",
            "data": pcts,
            "symbol": "circle",
            "symbolSize": 14,
            "lineStyle": {
                "color": "#dc2626",
                "width": 4,
                "shadowColor": "rgba(220,38,38,0.3)",
                "shadowBlur": 8,
            },
            "itemStyle": {"color": "#dc2626", "borderColor": "#fff", "borderWidth": 3},
            "areaStyle": {
                "color": {
                    "type": "linear",
                    "x": 0, "y": 0, "x2": 0, "y2": 1,
                    "colorStops": [
                        {"offset": 0, "color": "rgba(220,38,38,0.25)"},
                        {"offset": 1, "color": "rgba(220,38,38,0.02)"},
                    ],
                },
            },
            "label": {
                "show": True,
                "formatter": labels,
                "fontSize": 12,
                "fontWeight": 700,
                "color": "#b91c1c",
                "backgroundColor": "#fef2f2",
                "padding": [4, 8],
                "borderRadius": 6,
                "position": "top",
            },
            "markLine": {
                "silent": True,
                "symbol": "none",
                "lineStyle": {"color": "#94a3b8", "type": "dashed", "width": 2},
                "label": {
                    "formatter": f"均值 {avg}%",
                    "fontSize": 11,
                    "color": "#64748b",
                    "position": "end",
                },
                "data": [{"yAxis": avg, "name": "均值"}],
            },
            "markArea": {
                "silent": True,
                "itemStyle": {"color": "rgba(16,185,129,0.08)"},
                "data": [[{"yAxis": 30}, {"yAxis": 40}]],
                "label": {
                    "show": True,
                    "formatter": "健康区间\n30%~40%",
                    "position": "insideRight",
                    "fontSize": 10,
                    "color": "#059669",
                },
            },
        }],
    }


def chart_monthly_small(
    title: str, months: list[str], vals: list, color: str, unit: str, chains: list | None = None,
) -> dict:
    chains = chains or [None] * len(vals)
    return {
        "title": {"text": title, "left": "center", "top": 8, "textStyle": {"fontSize": 12, "color": "#0369a1"}},
        "tooltip": {"trigger": "axis"},
        "grid": {"left": "12%", "right": "6%", "bottom": 28, "top": 48},
        "xAxis": {"type": "category", "data": months, "axisLabel": {"fontSize": 10}},
        "yAxis": {"type": "value", "name": unit, "nameTextStyle": {"fontSize": 10}},
        "series": [
            {
                "type": "bar", "data": vals, "barWidth": "42%",
                "itemStyle": {"color": color, "borderRadius": [4, 4, 0, 0]},
                "label": {"show": True, "position": "top", "fontSize": 9},
            },
            {
                "type": "line", "data": vals, "symbolSize": 6,
                "lineStyle": {"color": color, "width": 2, "opacity": 0.5},
                "itemStyle": {"color": color}, "label": {"show": False},
            },
        ],
    }


def _scatter_labeled(
    points: list[dict], xk: str, yk: str, label_color: str = "#0c4a6e",
) -> list[dict]:
    out = []
    for p in points:
        nm = p["name"].replace("RDJ-", "")
        out.append({
            "name": nm,
            "value": [p[xk], p[yk]],
            "label": {
                "show": True,
                "formatter": nm,
                "position": "top",
                "distance": 8,
                "fontSize": 11,
                "fontWeight": 600,
                "color": label_color,
            },
        })
    return out


def chart_quadrant_throughput(points: list[dict]) -> dict:
    if not points:
        return {"title": {"text": "无足够样本", "left": "center", "top": "middle"}}
    avg_x = round(sum(p["cycle"] for p in points) / len(points), 2)
    avg_y = round(sum(p["count"] for p in points) / len(points), 2)
    xs = [p["cycle"] for p in points]
    ys = [p["count"] for p in points]
    x_min = math.floor(min(xs) * 0.85)
    x_max = math.ceil(max(xs) * 1.1)
    y_min = math.floor(min(ys) * 0.7)
    y_max = math.ceil(max(ys) * 1.15)
    return {
        "title": {
            "text": "交付周期 VS 吞吐量",
            "left": "center",
            "top": 6,
            "textStyle": {"fontSize": 16, "fontWeight": 700, "color": "#0c4a6e"},
        },
        "tooltip": {"trigger": "item"},
        "grid": {"left": "8%", "right": "12%", "bottom": 60, "top": 56, "containLabel": True},
        "xAxis": {
            "type": "value",
            "name": "交付周期",
            "min": x_min,
            "max": x_max,
            "nameTextStyle": {"fontSize": 13, "fontWeight": 700, "color": "#1e293b"},
            "splitLine": {"lineStyle": {"type": "dashed", "color": "#e2e8f0"}},
        },
        "yAxis": {
            "type": "value",
            "name": "吞吐量",
            "min": y_min,
            "max": y_max,
            "nameTextStyle": {"fontSize": 13, "fontWeight": 700, "color": "#1e293b"},
            "splitLine": {"lineStyle": {"type": "dashed", "color": "#e2e8f0"}},
        },
        "graphic": [
            {"type": "text", "left": "10%", "top": 58, "style": {"text": "⭐ 高效高产", "fill": "#16a34a", "fontSize": 12, "fontWeight": 600}},
            {"type": "text", "right": "14%", "top": 58, "style": {"text": "⚠️ 高产但周期长", "fill": "#f97316", "fontSize": 12, "fontWeight": 600}},
            {"type": "text", "left": "10%", "bottom": 62, "style": {"text": "📦 周期短产出低", "fill": "#64748b", "fontSize": 12, "fontWeight": 600}},
            {"type": "text", "right": "14%", "bottom": 62, "style": {"text": "🔴 低效低产", "fill": "#dc2626", "fontSize": 12, "fontWeight": 600}},
        ],
        "series": [{
            "type": "scatter",
            "symbolSize": 14,
            "clip": False,
            "data": _scatter_labeled(points, "cycle", "count"),
            "itemStyle": {"color": "#38bdf8", "borderColor": "#0284c7", "borderWidth": 1.5},
            "markLine": {
                "silent": True,
                "animation": False,
                "lineStyle": {"color": "#dc2626", "width": 2, "type": "solid"},
                "label": {"show": True, "fontSize": 11, "fontWeight": 600, "color": "#dc2626"},
                "data": [
                    {"xAxis": avg_x, "label": {"formatter": f"均值 {avg_x}天", "position": "end"}},
                    {"yAxis": avg_y, "label": {"formatter": f"均值 {avg_y}个", "position": "end"}},
                ],
            },
            "markArea": {
                "silent": True,
                "data": [
                    [
                        {"xAxis": x_min, "yAxis": avg_y, "itemStyle": {"color": "rgba(22,163,74,0.06)"}},
                        {"xAxis": avg_x, "yAxis": y_max},
                    ],
                    [
                        {"xAxis": avg_x, "yAxis": avg_y, "itemStyle": {"color": "rgba(249,115,22,0.06)"}},
                        {"xAxis": x_max, "yAxis": y_max},
                    ],
                    [
                        {"xAxis": x_min, "yAxis": y_min, "itemStyle": {"color": "rgba(148,163,184,0.06)"}},
                        {"xAxis": avg_x, "yAxis": avg_y},
                    ],
                    [
                        {"xAxis": avg_x, "yAxis": y_min, "itemStyle": {"color": "rgba(220,38,38,0.06)"}},
                        {"xAxis": x_max, "yAxis": avg_y},
                    ],
                ],
            },
        }],
    }


def chart_quadrant_per_capita(points: list[dict]) -> dict:
    if len(points) < 3:
        return {"title": {"text": "样本不足", "left": "center", "top": "middle"}}
    avg_x = round(sum(p["cycle"] for p in points) / len(points), 3)
    total_score = sum(p.get("total_score", 0) for p in points)
    total_tt = sum(p.get("test_total", 0) for p in points)
    avg_y = round(total_score / total_tt, 2) if total_tt > 0 else 0
    xs = [p["cycle"] for p in points]
    ys = [p["per_test"] for p in points]
    x_min = math.floor(min(xs) * 0.85)
    x_max = math.ceil(max(xs) * 1.1)
    y_max = math.ceil(max(ys) * 1.15 * 100) / 100
    return {
        "title": {
            "text": "交付周期 VS 单位测试支撑的交付量（总估分÷测试工时）",
            "left": "center",
            "top": 6,
            "textStyle": {"fontSize": 16, "fontWeight": 700, "color": "#0c4a6e"},
        },
        "tooltip": {"trigger": "item"},
        "grid": {"left": "8%", "right": "12%", "bottom": 60, "top": 56, "containLabel": True},
        "xAxis": {
            "type": "value",
            "name": "交付周期(天)",
            "min": x_min,
            "max": x_max,
            "nameTextStyle": {"fontSize": 13, "fontWeight": 700, "color": "#1e293b"},
            "splitLine": {"lineStyle": {"type": "dashed", "color": "#e2e8f0"}},
        },
        "yAxis": {
            "type": "value",
            "name": "总估分÷测试工时(估分/人天)",
            "min": 0,
            "max": y_max,
            "nameTextStyle": {"fontSize": 13, "fontWeight": 700, "color": "#1e293b"},
            "splitLine": {"lineStyle": {"type": "dashed", "color": "#e2e8f0"}},
        },
        "graphic": [
            {"type": "text", "left": "10%", "top": 58, "style": {"text": "⭐ 快且高效", "fill": "#7c3aed", "fontSize": 12, "fontWeight": 600}},
            {"type": "text", "right": "14%", "top": 58, "style": {"text": "⚠️ 杠杆高但周期长", "fill": "#f97316", "fontSize": 12, "fontWeight": 600}},
            {"type": "text", "left": "10%", "bottom": 62, "style": {"text": "📦 周期短支撑量低", "fill": "#64748b", "fontSize": 12, "fontWeight": 600}},
            {"type": "text", "right": "14%", "bottom": 62, "style": {"text": "🔴 又慢又费", "fill": "#dc2626", "fontSize": 12, "fontWeight": 600}},
        ],
        "series": [{
            "type": "scatter",
            "symbolSize": 10,
            "clip": False,
            "data": _scatter_labeled(points, "cycle", "per_test", "#4c1d95"),
            "itemStyle": {"color": "#7c3aed", "borderColor": "#5b21b6", "borderWidth": 1},
            "markLine": {
                "silent": True,
                "animation": False,
                "lineStyle": {"color": "#7c3aed", "width": 2, "type": "solid"},
                "label": {"show": True, "fontSize": 11, "fontWeight": 600, "color": "#7c3aed"},
                "data": [
                    {"xAxis": avg_x, "label": {"formatter": f"均值 {avg_x}天", "position": "end"}},
                    {"yAxis": avg_y, "label": {"formatter": f"均值 {avg_y}估分/人天", "position": "end"}},
                ],
            },
            "markArea": {
                "silent": True,
                "data": [
                    [
                        {"xAxis": x_min, "yAxis": avg_y, "itemStyle": {"color": "rgba(124,58,237,0.06)"}},
                        {"xAxis": avg_x, "yAxis": y_max},
                    ],
                    [
                        {"xAxis": avg_x, "yAxis": avg_y, "itemStyle": {"color": "rgba(249,115,22,0.06)"}},
                        {"xAxis": x_max, "yAxis": y_max},
                    ],
                    [
                        {"xAxis": x_min, "yAxis": 0, "itemStyle": {"color": "rgba(148,163,184,0.06)"}},
                        {"xAxis": avg_x, "yAxis": avg_y},
                    ],
                    [
                        {"xAxis": avg_x, "yAxis": 0, "itemStyle": {"color": "rgba(220,38,38,0.06)"}},
                        {"xAxis": x_max, "yAxis": avg_y},
                    ],
                ],
            },
        }],
    }


def quadrant_conclusion_html(ext: dict) -> str:
    pts = ext.get("quadrant") or []
    if not pts:
        return ""
    avg_c = sum(p["cycle"] for p in pts) / len(pts)
    avg_n = sum(p["count"] for p in pts) / len(pts)
    q1, q2, q3, q4 = [], [], [], []
    for p in pts:
        n = p["name"].replace("RDJ-", "")
        fast = p["cycle"] <= avg_c
        high = p["count"] >= avg_n
        if fast and high:
            q1.append(n)
        elif not fast and high:
            q2.append(n)
        elif fast and not high:
            q3.append(n)
        else:
            q4.append(n)
    eff = [
        {
            "n": p["name"].replace("RDJ-", ""),
            "eff": p["per_test"],
        }
        for p in ext.get("quadrant_per_capita") or []
    ]
    eff.sort(key=lambda x: -x["eff"])
    top_eff = "、".join(f"{d['n']}({d['eff']}估分/人天)" for d in eff[:3])
    btm_eff = "、".join(f"{d['n']}({d['eff']}估分/人天)" for d in eff[-3:])
    cy_sorted = sorted(pts, key=lambda x: x["cycle"])
    fast_top = "、".join(f"{d['name'].replace('RDJ-','')}({d['cycle']}天)" for d in cy_sorted[:3])
    slow_top = "、".join(
        f"{d['name'].replace('RDJ-','')}({d['cycle']}天)" for d in reversed(cy_sorted[-3:])
    )
    def cell(title: str, color: str, names: list[str], hint: str) -> str:
        body = "、".join(names) if names else "无"
        return (
            f'<div><span style="color:{color};font-weight:700;">{title}</span>：{escape(body)}<br/>'
            f'<span class="quad-hint">{escape(hint)}</span></div>'
        )
    return f"""
<div class="quadrant-conclusion">
  <div class="quad-concl-title">📊 四象限分析结论</div>
  <p class="quad-concl-sub">基于主图（交付周期 vs 需求总数）与辅助图（交付周期 vs 单位测试支撑的交付量），需求数≥20 的业务线。</p>
  <div class="quad-concl-grid">
    {cell("⭐ 高效高产", "#7c3aed", q1, "周期短 + 吞吐高（主图右上），保持现有节奏。")}
    {cell("⚠️ 高产但周期长", "#f97316", q2, "吞吐高但交付慢（主图右下），需排查流程瓶颈。")}
    {cell("📦 周期短低产", "#64748b", q3, "交付快但量小（主图左上），多属正常。")}
    {cell("🔴 低效低产", "#dc2626", q4, "周期长 + 吞吐低（主图左下），需重点改善。")}
  </div>
  <div class="quad-concl-findings">
    <b>关键发现：</b><br/>
    • <b>交付最快</b>（主图）：{escape(fast_top)}<br/>
    • <b>交付最慢</b>（主图）：{escape(slow_top)}<br/>
    • <b>单位测试支撑的交付量最高</b>（辅助图）：{escape(top_eff)}<br/>
    • <b>单位测试支撑的交付量最低</b>（辅助图）：{escape(btm_eff)}
  </div>
</div>"""


def _fmt_chain_cell(c) -> str:
    if c is None:
        return "—"
    if isinstance(c, (int, float)):
        return f"{c:+.1f}%"
    s = str(c).strip()
    return "—" if not s or s == "None" else s


def monthly_metrics_table_html(ext: dict) -> str:
    months = ext["months"]
    def chain_row(vals):
        chains = []
        for i, v in enumerate(vals):
            if i == 0 or not vals[i - 1]:
                chains.append("—")
            else:
                prev = vals[i - 1]
                chains.append(
                    f"{((v - prev) / abs(prev) * 100):+.1f}%"
                    if prev
                    else "—"
                )
        return chains

    rows_def = [
        ("交付数量", ext["demands"], ext["demand_chains"]),
        ("总工时(人天)", ext["month_totals"], chain_row(ext["month_totals"])),
        ("交付周期(天)", ext["cycles"], chain_row(ext["cycles"])),
        ("测试相关工时", ext["month_test_work"], chain_row(ext["month_test_work"])),
        ("测试效率(个/人天)", ext["test_eff"], chain_row(ext["test_eff"])),
    ]
    body = ""
    for name, vals, chs in rows_def:
        tds = "".join(
            f"<td>{v:g}</td><td class='ch'>{_fmt_chain_cell(c)}</td>"
            if isinstance(v, (int, float))
            else f"<td>{escape(str(v))}</td><td class='ch'>{_fmt_chain_cell(c)}</td>"
            for v, c in zip(vals, chs)
        )
        body += f"<tr><td class='l'>{name}</td>{tds}</tr>"
    hdr = "".join(f"<th colspan='2'>{escape(m)}</th>" for m in months)
    sub = "".join("<th>值</th><th>环比</th>" for _ in months)
    return (
        f'<div class="detail-table monthly-metrics-table"><table>'
        f"<thead><tr><th rowspan='2'>指标</th>{hdr}</tr><tr>{sub}</tr></thead>"
        f"<tbody>{body}</tbody></table></div>"
    )


def build_rdj_chart_options(ext: dict, prefix: str) -> dict[str, Any]:
    """prefix: mt_ or mi_"""
    return {
        f"{prefix}team_mom": chart_team_mom_trend(ext),
        f"{prefix}test_pct": chart_test_pct_trend(ext),
        f"{prefix}deliv_cnt": chart_monthly_small(
            "每月交付数量", ext["months"], ext["demands"], "#0ea5e9", "个", ext["demand_chains"],
        ),
        f"{prefix}deliv_cycle": chart_monthly_small(
            "交付周期(天)", ext["months"], ext["cycles"], "#6366f1", "天",
        ),
        f"{prefix}test_eff": chart_monthly_small(
            "测试效率(需求/测试工时)", ext["months"], ext["test_eff"], "#7c3aed", "",
        ),
        f"{prefix}test_work": chart_monthly_small(
            "测试相关工时(人天)", ext["months"], ext["month_test_work"], "#dc2626", "人天",
        ),
        f"{prefix}quad_tp": chart_quadrant_throughput(ext["quadrant"]),
        f"{prefix}quad_pc": chart_quadrant_per_capita(ext["quadrant_per_capita"]),
    }


_QUAD_CAP_MAIN = (
    "<b>指标意义：</b>横轴 = 平均交付周期（天），纵轴 = 吞吐量（需求总数）。"
    "以两轴均值为分界线划分四象限，用于识别「高效高产」「高产但周期长」「周期短低产」「低效低产」四类业务线。"
)
_QUAD_CAP_AUX = (
    "<b>指标意义：</b>横轴 = 平均交付周期（天），纵轴 = 总估分÷测试工时（估分/人天），"
    "表示单位测试投入所支撑的交付规模。以两轴均值为分界线划分四象限，"
    "用于识别「快且高效」「杠杆高但周期长」等类型，便于跨业务线比较测试杠杆。"
)


def rdj_delivery_panel_html(prefix: str, ext: dict, accent: str) -> str:
    """主站时间/迭代子面板 — 结构与 Gate-RDJ 时间维报告「一、交付效能分析」对齐。"""
    p = prefix
    monthly_charts = "".join(
        f'<div class="monthly-chart-tile">{chart(f"{p}{k}", 320)}</div>'
        for k in ("deliv_cnt", "deliv_cycle", "test_eff", "test_work")
    )
    return f"""
<details open class="section-group rdj-section panel-section">
  <summary class="group-title">一、交付效能分析</summary>
  <div class="section-group-body rdj-delivery-zone">
  <div class="rdj-part">
    <div class="part-title">1.1 交付周期与全局测试占比</div>
    {delivery_cycle_html(ext, accent)}

    <div class="rdj-box rdj-box-red">
      <div class="rdj-box-h">
        <span class="rdj-emoji">📊</span>
        <span class="rdj-box-title rdj-title-red">测试相关工时占比趋势</span>
        <span class="rdj-box-hint">（QC+测试+预发）÷（设计评审+研发+QC+测试+预发）× 100%</span>
      </div>
      {chart(f"{p}test_pct", 340)}
    </div>

    <div class="rdj-box rdj-box-white rdj-monthly-wrap">
      <div class="rdj-box-h">
        <span class="rdj-emoji">📈</span>
        <span class="rdj-box-title">月度交付核心指标</span>
        <span class="rdj-box-hint">交付量 · 周期 · 测试效率 · 测试工时及环比</span>
      </div>
      <div class="monthly-metrics-grid">{monthly_charts}</div>
      {monthly_metrics_table_html(ext)}
    </div>
  </div>

  <div class="rdj-part">
    <div class="part-title">1.2 团队测试占比对比</div>
    <div class="rdj-box rdj-box-cyan">
      <div class="rdj-box-h">
        <span class="rdj-emoji">📋</span>
        <span class="rdj-box-title">各业务线当月实际 vs 各月团队均值</span>
      </div>
      {biz_test_pct_table_html(ext)}
    </div>
    {team_mom_panel_html(p, ext)}
  </div>

  <div class="rdj-part">
    <div class="part-title">1.3 交付效率四象限分析</div>
    <div class="quadrant-info">
      主图反映<b>绝对交付规模</b>（需求总数）。辅助图采用<b>总交付估分÷测试工时</b>（单位测试支撑的交付量），
      弱化需求颗粒度差异，便于跨业务线比较测试投入的杠杆效果。<br/>
      <span class="quadrant-info-sub">统计规则：主图、辅助图仅纳入<strong>需求数≥20</strong>的业务线，避免小样本波动影响象限划分。</span>
    </div>
    <div class="chart-row chart-row-quad">
      <div class="chart-box chart-box-quad">
        {chart(f"{p}quad_tp", 560)}
        <p class="chart-caption quad-cap">{_QUAD_CAP_MAIN}</p>
      </div>
      <div class="chart-box chart-box-quad">
        {chart(f"{p}quad_pc", 560)}
        <p class="chart-caption quad-cap">{_QUAD_CAP_AUX}</p>
      </div>
    </div>
    {quadrant_conclusion_html(ext)}
  </div>
  </div>
</details>
"""


def card_inner(title: str, body: str, desc: str = "", compact: bool = False) -> str:
    cls = "card inner-card" + (" compact" if compact else "")
    d = f'<p class="card-desc">{desc}</p>' if desc else ""
    t = f'<div class="card-t">{escape(title)}</div>' if title else ""
    return f'<div class="{cls}">{t}{d}{body}</div>'


def chart(cid: str, h: int = 300) -> str:
    return f'<div class="ec" id="{cid}" data-opt="{cid}" style="height:{h}px"></div>'


def two(a: str, b: str) -> str:
    return f'<div class="grid2">{a}{b}</div>'


def validate_against_source(d: dict, label: str) -> list[str]:
    """返回校验警告列表（空=全通过）。"""
    warns: list[str] = []
    mc = d.get("month_with_chain") or []
    if mc:
        n = sum(x["value"] for x in mc)
        kpi_n = d.get("total_demands")
        if kpi_n is not None and int(kpi_n) != n:
            warns.append(f"{label}: 需求数 month_with_chain Σ={n} vs total_demands={kpi_n}")
    ms = d.get("monthly_summary") or []
    if ms and d.get("avg_rt_ratio") is not None:
        avg_rt = sum(x["rt_ratio"] for x in ms) / len(ms)
        if abs(avg_rt - float(d["avg_rt_ratio"])) > 0.15:
            warns.append(
                f"{label}: 月均R/T {avg_rt:.2f} vs avg_rt_ratio {d['avg_rt_ratio']}"
            )
    if d.get("month_avg_cycle") and mc:
        if len(d["month_avg_cycle"]) != len(mc):
            warns.append(f"{label}: month_avg_cycle 长度与月份不一致")
    return warns
