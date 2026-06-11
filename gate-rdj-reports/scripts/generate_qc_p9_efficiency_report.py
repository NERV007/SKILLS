#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QC 人员 P9 报告：总分总结构 — 先完整呈现分月/分迭代事实与图表，再拆解团队与个人；
环比给出相对变化率与百分点差；人员按部门(业务线)聚合并对标 **R/T（修正研发÷测试工时）**。

口径与 v4 业务线分析报告对齐：测试工时 = QC用例 + 测试 + 预发；测试占比 = 该工时 / 五阶段总人天
（质量可控前提下占比倾向越低越好）；**R/T** = 修正研发工时 ÷ 测试工时（同报告内「整体 R/T」与附录定义）。

输出：Gate-RDJ-QC人员-P9人效环比与建议报告.html（主对标指标为 R/T 与测试占比；文件名沿用历史产物。）
"""
from __future__ import annotations

import hashlib
import html as html_module
import json
import os
import sys
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from gate_rdj_metrics import (  # noqa: E402
    _month_period_key,
    _parse_dt,
    _pf,
    _sp_label,
    build_data_payload,
    corrected_rd,
    effort_fields,
    five_phase_total,
    is_urgent,
    load_rows,
)
import generate_gate_rdj_from_csv as ggen  # noqa: E402

from _paths import DATA_DIR, REPO_ROOT

ROOT = str(REPO_ROOT)
OUT_HTML = os.path.join(ROOT, "Gate-RDJ-QC人员-P9人效环比与建议报告.html")


def _qc_labels(row: Dict[str, str]) -> List[str]:
    raw = (row.get("QC") or "").strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split("|") if x.strip()]


def _pct(test: float, five: float) -> float:
    return round(test / (five + 1e-6) * 100, 2) if five else 0.0


# 需求分类（互斥）：紧急 > 技术/优化 > 产品 > 合规风控 > 其他；与下文附录口径一致。
DEMAND_BUCKET_ORDER: Tuple[str, ...] = (
    "紧急需求",
    "技术/优化类",
    "产品类",
    "合规风控类",
    "其他",
)


def demand_bucket_exclusive(r: Dict[str, str]) -> str:
    """每条需求归入单一桶，便于分月/分迭代加总与占比解读。"""
    if is_urgent(r):
        return "紧急需求"
    req_t = (r.get("需求类型") or "").strip()
    val_t = (r.get("价值类型") or "").strip()
    if "技术" in req_t or "技术" in val_t or "优化" in val_t:
        return "技术/优化类"
    if "产品" in req_t:
        return "产品类"
    if "合规" in req_t or "风控" in req_t:
        return "合规风控类"
    return "其他"


def aggregate_demand_category_period(
    rows: List[Dict[str, str]],
    periods: List[str],
    period_key: Callable[[Dict[str, str]], Optional[str]],
) -> Dict[str, Dict[str, Dict[str, float]]]:
    """按完成周期 × 互斥需求分类聚合需求数、测试工时、五阶段、Bug。"""
    pset = set(periods)
    out: Dict[str, Dict[str, Dict[str, float]]] = {
        p: {b: {"demands": 0.0, "test": 0.0, "five": 0.0, "bugs": 0.0} for b in DEMAND_BUCKET_ORDER}
        for p in periods
    }
    for r in rows:
        pk = period_key(r)
        if not pk or pk not in pset:
            continue
        b = demand_bucket_exclusive(r)
        if b not in out[pk]:
            continue
        tw = test_work_hours_v4(r)
        five = five_phase_total(r)
        bugs = _pf(r.get("总 bug 数"))
        o = out[pk][b]
        o["demands"] += 1.0
        o["test"] += tw
        o["five"] += five
        o["bugs"] += bugs
    return out


def _rollup_category_window(
    by_period: Dict[str, Dict[str, Dict[str, float]]], periods: List[str]
) -> Dict[str, Dict[str, float]]:
    """窗口内按分类汇总（跨所选 period 列表）。"""
    acc: Dict[str, Dict[str, float]] = {b: {"demands": 0.0, "test": 0.0, "five": 0.0, "bugs": 0.0} for b in DEMAND_BUCKET_ORDER}
    for p in periods:
        per = by_period.get(p) or {}
        for b in DEMAND_BUCKET_ORDER:
            o = per.get(b) or {}
            acc[b]["demands"] += float(o.get("demands", 0))
            acc[b]["test"] += float(o.get("test", 0))
            acc[b]["five"] += float(o.get("five", 0))
            acc[b]["bugs"] += float(o.get("bugs", 0))
    return acc


_CAT_COLORS = {
    "紧急需求": "#dc2626",
    "技术/优化类": "#059669",
    "产品类": "#2563eb",
    "合规风控类": "#d97706",
    "其他": "#94a3b8",
}


def _category_stack_json(cat_m: Dict[str, Dict[str, Dict[str, float]]], months: List[str], month_labels: List[str]) -> str:
    series: List[Dict[str, Any]] = []
    for b in DEMAND_BUCKET_ORDER:
        series.append(
            {
                "name": b,
                "type": "bar",
                "stack": "test",
                "emphasis": {"focus": "series"},
                "data": [round(float(cat_m.get(m, {}).get(b, {}).get("test", 0)), 2) for m in months],
                "itemStyle": {"color": _CAT_COLORS.get(b, "#64748b")},
            }
        )
    return json.dumps({"labels": month_labels, "series": series}, ensure_ascii=False)


# ---------- 价值类型 / 是否紧急 — 独立归档（非上文互斥桶）----------
MAX_VALUE_TYPE_TOP = 10
OTHER_VALUE_TYPE_LABEL = "（其他价值类型）"

_VT_PALETTE = (
    "#2563eb",
    "#059669",
    "#d97706",
    "#7c3aed",
    "#db2777",
    "#0d9488",
    "#ea580c",
    "#4f46e5",
    "#ca8a04",
    "#16a34a",
    "#64748b",
    "#0891b2",
)

_URGENT_ORDER = ("紧急", "非紧急")
_URGENT_COLORS = {"紧急": "#dc2626", "非紧急": "#94a3b8"}


def _norm_value_type_field(r: Dict[str, str]) -> str:
    v = (r.get("价值类型") or "").strip()
    return v if v else "未分类"


def _urgent_binary_label(r: Dict[str, str]) -> str:
    return "紧急" if is_urgent(r) else "非紧急"


def aggregate_dim_bucket_period(
    rows: List[Dict[str, str]],
    periods: List[str],
    period_key: Callable[[Dict[str, str]], Optional[str]],
    bucket_fn: Callable[[Dict[str, str]], str],
) -> Dict[str, Dict[str, Dict[str, float]]]:
    """按完成周期 × 任意桶维度聚合（每条需求计入其桶）。period 全覆盖 periods 列表。"""
    pset = set(periods)
    out: Dict[str, Dict[str, Dict[str, float]]] = {p: {} for p in periods}
    for r in rows:
        pk = period_key(r)
        if not pk or pk not in pset:
            continue
        b = bucket_fn(r)
        if b not in out[pk]:
            out[pk][b] = {"demands": 0.0, "test": 0.0, "five": 0.0, "bugs": 0.0}
        tw = test_work_hours_v4(r)
        five = five_phase_total(r)
        bugs = _pf(r.get("总 bug 数"))
        o = out[pk][b]
        o["demands"] += 1.0
        o["test"] += tw
        o["five"] += five
        o["bugs"] += bugs
    return out


def collapse_value_types_by_test_volume(
    by_period: Dict[str, Dict[str, Dict[str, float]]],
    periods: List[str],
    top_k: int,
) -> Tuple[List[str], Dict[str, Dict[str, Dict[str, float]]]]:
    """按全期测试工时排序保留 TOP_k，其余并入「其他价值类型」。"""
    totals: Dict[str, float] = defaultdict(float)
    for p in periods:
        for vt, o in (by_period.get(p) or {}).items():
            totals[vt] += float(o.get("test", 0))
    if not totals:
        return [], {p: {} for p in periods}
    ranked = sorted(totals.keys(), key=lambda k: (-totals[k], str(k)))
    keep = set(ranked[:top_k])
    need_other = any(vt not in keep for vt in totals)
    ordered: List[str] = list(ranked[:top_k])
    if need_other:
        ordered.append(OTHER_VALUE_TYPE_LABEL)
    collapsed: Dict[str, Dict[str, Dict[str, float]]] = {}
    for p in periods:
        buck: Dict[str, Dict[str, float]] = {lb: {"demands": 0.0, "test": 0.0, "five": 0.0, "bugs": 0.0} for lb in ordered}
        for vt, o in (by_period.get(p) or {}).items():
            tgt = vt if vt in keep else OTHER_VALUE_TYPE_LABEL
            if tgt not in buck:
                buck[tgt] = {"demands": 0.0, "test": 0.0, "five": 0.0, "bugs": 0.0}
            for kk in ("demands", "test", "five", "bugs"):
                buck[tgt][kk] += float(o.get(kk, 0))
        collapsed[p] = {k: dict(v) for k, v in buck.items()}
    return ordered, collapsed


def _rollup_dim_window(
    by_period: Dict[str, Dict[str, Dict[str, float]]],
    periods: List[str],
    ordered_keys: List[str],
) -> Dict[str, Dict[str, float]]:
    acc = {k: {"demands": 0.0, "test": 0.0, "five": 0.0, "bugs": 0.0} for k in ordered_keys}
    for p in periods:
        per = by_period.get(p) or {}
        for k in ordered_keys:
            o = per.get(k) or {}
            for kk in ("demands", "test", "five", "bugs"):
                acc[k][kk] += float(o.get(kk, 0))
    return acc


def _normalize_urgent_period(
    by_period: Dict[str, Dict[str, Dict[str, float]]],
    periods: List[str],
) -> Dict[str, Dict[str, Dict[str, float]]]:
    """每个周期均含「紧急」「非紧急」两行，便于堆叠与透视对齐。"""
    out: Dict[str, Dict[str, Dict[str, float]]] = {}
    for p in periods:
        per = by_period.get(p) or {}
        out[p] = {}
        for lab in _URGENT_ORDER:
            o = per.get(lab)
            if o:
                out[p][lab] = {k: float(o.get(k, 0)) for k in ("demands", "test", "five", "bugs")}
            else:
                out[p][lab] = {"demands": 0.0, "test": 0.0, "five": 0.0, "bugs": 0.0}
    return out


def _dynamic_stack_json(
    ordered_keys: List[str],
    by_period: Dict[str, Dict[str, Dict[str, float]]],
    periods: List[str],
    axis_labels: List[str],
    *,
    stack_id: str,
    colors: Callable[[str, int], str],
) -> str:
    if not ordered_keys:
        return json.dumps({"labels": axis_labels, "series": []}, ensure_ascii=False)
    series: List[Dict[str, Any]] = []
    for i, name in enumerate(ordered_keys):
        series.append(
            {
                "name": name,
                "type": "bar",
                "stack": stack_id,
                "emphasis": {"focus": "series"},
                "data": [
                    round(float(((by_period.get(p) or {}).get(name) or {}).get("test", 0)), 2) for p in periods
                ],
                "itemStyle": {"color": colors(name, i)},
            }
        )
    return json.dumps({"labels": axis_labels, "series": series}, ensure_ascii=False)


def _vt_color(name: str, i: int) -> str:
    return _VT_PALETTE[i % len(_VT_PALETTE)]


def _urg_color(name: str, i: int) -> str:
    return _URGENT_COLORS.get(str(name), _VT_PALETTE[i % len(_VT_PALETTE)])


def _html_dim_global_table(
    roll: Dict[str, Dict[str, float]],
    ordered_keys: List[str],
    total_test: float,
    total_dem: int,
) -> str:
    rows: List[str] = []
    for b in ordered_keys:
        o = roll.get(b) or {}
        dm = int(o.get("demands", 0))
        tt = float(o.get("test", 0))
        fv = float(o.get("five", 0))
        bugs = float(o.get("bugs", 0))
        pct_t = round(tt / (total_test + 1e-6) * 100, 1) if total_test > 1e-6 else 0.0
        pct_d = round(dm / (total_dem + 1e-6) * 100, 1) if total_dem else 0.0
        tp_b = _pct(tt, fv)
        bpd = round(bugs / (dm + 1e-6), 2) if dm else 0.0
        rows.append(
            "<tr>"
            f'<td style="font-weight:600;">{html_module.escape(str(b))}</td>'
            f"<td>{dm}</td><td>{pct_d}%</td>"
            f"<td>{round(tt, 1)}</td><td>{pct_t}%</td>"
            f"<td>{tp_b}%</td><td>{bpd}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _html_dim_month_pivot(
    by_period: Dict[str, Dict[str, Dict[str, float]]],
    periods: List[str],
    ordered_keys: List[str],
) -> str:
    rows: List[str] = []
    for b in ordered_keys:
        cells: List[str] = []
        for m in periods:
            per_m = by_period.get(m, {})
            tt = float((per_m.get(b) or {}).get("test", 0))
            mt = sum(float((per_m.get(bb) or {}).get("test", 0)) for bb in ordered_keys)
            pct = round(tt / (mt + 1e-6) * 100, 1) if mt > 1e-6 else 0.0
            cells.append(
                f"<td>{round(tt, 1)}<br/><span style=\"font-size:10px;color:#94a3b8\">({pct}%)</span></td>"
            )
        rows.append(
            f'<tr><td style="font-weight:600;">{html_module.escape(str(b))}</td>' + "".join(cells) + "</tr>"
        )
    return "\n".join(rows)


def _html_category_global_table(cat_roll: Dict[str, Dict[str, float]], total_test: float, total_dem: int) -> str:
    rows: List[str] = []
    for b in DEMAND_BUCKET_ORDER:
        o = cat_roll.get(b) or {}
        dm = int(o.get("demands", 0))
        tt = float(o.get("test", 0))
        fv = float(o.get("five", 0))
        bugs = float(o.get("bugs", 0))
        pct_t = round(tt / (total_test + 1e-6) * 100, 1) if total_test > 1e-6 else 0.0
        pct_d = round(dm / (total_dem + 1e-6) * 100, 1) if total_dem else 0.0
        tp_b = _pct(tt, fv)
        bpd = round(bugs / (dm + 1e-6), 2) if dm else 0.0
        rows.append(
            "<tr>"
            f'<td style="font-weight:600;">{html_module.escape(b)}</td>'
            f"<td>{dm}</td><td>{pct_d}%</td>"
            f"<td>{round(tt, 1)}</td><td>{pct_t}%</td>"
            f"<td>{tp_b}%</td><td>{bpd}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _html_category_month_pivot(cat_m: Dict[str, Dict[str, Dict[str, float]]], months: List[str]) -> Tuple[str, str]:
    heads = "".join(f"<th>{html_module.escape(m)}</th>" for m in months)
    rows: List[str] = []
    for b in DEMAND_BUCKET_ORDER:
        cells: List[str] = []
        for m in months:
            per_m = cat_m.get(m, {})
            tt = float((per_m.get(b) or {}).get("test", 0))
            mt = sum(float((per_m.get(bb) or {}).get("test", 0)) for bb in DEMAND_BUCKET_ORDER)
            pct = round(tt / (mt + 1e-6) * 100, 1) if mt > 1e-6 else 0.0
            cells.append(f"<td>{round(tt, 1)}<br/><span style=\"font-size:10px;color:#94a3b8\">({pct}%)</span></td>")
        rows.append(
            f'<tr><td style="font-weight:600;">{html_module.escape(b)}</td>' + "".join(cells) + "</tr>"
        )
    return heads, "\n".join(rows)


def _html_category_iter_pivot(cat_i: Dict[str, Dict[str, Dict[str, float]]], iter_keys: List[str]) -> Tuple[str, str]:
    heads = "".join(f"<th>{html_module.escape(s)}</th>" for s in iter_keys)
    rows: List[str] = []
    for b in DEMAND_BUCKET_ORDER:
        cells: List[str] = []
        for s in iter_keys:
            per_s = cat_i.get(s, {})
            dm = int((per_s.get(b) or {}).get("demands", 0))
            cells.append(f"<td>{dm}</td>")
        rows.append(f'<tr><td style="font-weight:600;">{html_module.escape(b)}</td>' + "".join(cells) + "</tr>")
    return heads, "\n".join(rows)


def build_team_test_pct_pivot_html(
    ranked_teams: List[Tuple[str, Any]],
    team_m: Dict[str, Dict[str, Dict[str, float]]],
    team_i: Dict[str, Dict[str, Dict[str, float]]],
    months: List[str],
    month_labels: List[str],
    iter_keys: List[str],
    iter_labels: List[str],
) -> str:
    """各团队 × 完成月 / × 迭代：测试工时占五阶段人天 %（与上方折线图同一口径与团队集合）。"""
    team_names = [t for t, _ in ranked_teams]
    mh = "".join(f"<th>{html_module.escape(ml)}</th>" for ml in month_labels)
    m_rows: List[str] = []
    for team in team_names:
        per = team_m.get(team, {})
        cells = "".join(
            f"<td>{_pct(per.get(m, {}).get('test', 0), per.get(m, {}).get('five', 0)):.1f}%</td>" for m in months
        )
        m_rows.append(
            f'<tr><td style="text-align:left;font-weight:600;">{html_module.escape(team)}</td>{cells}</tr>'
        )
    g_m = "".join(
        f"<td><strong>{_pct(sum(team_m[t].get(m, {}).get('test', 0) for t in team_m), sum(team_m[t].get(m, {}).get('five', 0) for t in team_m)):.1f}%</strong></td>"
        for m in months
    )
    m_rows.append(f'<tr class="tp-global-row"><td style="text-align:left;">【全局】</td>{g_m}</tr>')
    month_block = (
        '<h3 style="margin:18px 0 8px;font-size:14px;color:#334155;font-weight:700;">'
        "数据表 · 各团队测试工时占比 · 分月（%）</h3>"
        '<p class="note" style="margin-bottom:8px;">与上图一致：<strong>测试工时÷五阶段人天</strong>；团队为<strong>全部业务线</strong>（按全期测试工时降序）；末行【全局】为各列全体团队汇总。</p>'
        '<div class="table-wrap team-pivot-wrap"><table class="team-tp-pivot"><thead><tr>'
        f'<th class="sticky-col">团队</th>{mh}</tr></thead><tbody>{"".join(m_rows)}</tbody></table></div>'
    )

    ih = "".join(f"<th>{html_module.escape(il)}</th>" for il in iter_labels)
    i_rows: List[str] = []
    for team in team_names:
        per = team_i.get(team, {})
        cells = "".join(
            f"<td>{_pct(per.get(s, {}).get('test', 0), per.get(s, {}).get('five', 0)):.1f}%</td>" for s in iter_keys
        )
        i_rows.append(
            f'<tr><td style="text-align:left;font-weight:600;">{html_module.escape(team)}</td>{cells}</tr>'
        )
    g_i = "".join(
        f"<td><strong>{_pct(sum(team_i[t].get(s, {}).get('test', 0) for t in team_i), sum(team_i[t].get(s, {}).get('five', 0) for t in team_i)):.1f}%</strong></td>"
        for s in iter_keys
    )
    i_rows.append(f'<tr class="tp-global-row"><td style="text-align:left;">【全局】</td>{g_i}</tr>')
    iter_block = (
        '<h3 style="margin:18px 0 8px;font-size:14px;color:#334155;font-weight:700;">'
        "数据表 · 各团队测试工时占比 · 分迭代（%）</h3>"
        '<p class="note" style="margin-bottom:8px;">横轴与第三节迭代一致；口径同上。</p>'
        '<div class="table-wrap team-pivot-wrap"><table class="team-tp-pivot"><thead><tr>'
        f'<th class="sticky-col">团队</th>{ih}</tr></thead><tbody>{"".join(i_rows)}</tbody></table></div>'
    )
    return month_block + iter_block


# 折线图数据点旁展示数值（与表格口径一致）
_ECHARTS_TP_LINE_LABEL: Dict[str, Any] = {"show": True, "position": "top", "fontSize": 8, "formatter": "{c}%"}


def test_work_hours_v4(r: Dict[str, str]) -> float:
    """与业务线 v4 报告一致：测试相关工时 = QC用例 + 测试 + 预发（不用「测试总估分(去除RD)」作主口径）。"""
    _d, _rd, qc_e, _tnode, te, pr, _tt = effort_fields(r)
    return round(qc_e + te + pr, 4)


def _rt(rc: float, test: float) -> float:
    return round(rc / (test + 1e-6), 2) if test else 0.0


def _mom_rel(cur: float, prev: float) -> Optional[float]:
    if prev <= 1e-6:
        return None
    return round((cur - prev) / prev * 100, 1)


def _fmt_month_axis(ym: str) -> str:
    p = ym.split("-")
    if len(p) == 2 and p[1].isdigit():
        return f"{int(p[1])}月\\n{ym}"
    return ym


def _fmt_sp_axis(sp: str) -> str:
    if "-SP" in sp:
        return sp.replace("-", "\\n", 1)
    return sp


def aggregate_global_period(
    rows: List[Dict[str, str]],
    periods: List[str],
    period_key: Callable[[Dict[str, str]], Optional[str]],
) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {p: {"demands": 0.0, "test": 0.0, "five": 0.0, "bugs": 0.0, "rd_corr": 0.0} for p in periods}
    pset = set(periods)
    for r in rows:
        pk = period_key(r)
        if not pk or pk not in pset:
            continue
        d, rd, qc_e, tnode, te, pr, _tt = effort_fields(r)
        five = five_phase_total(r)
        tw = test_work_hours_v4(r)
        o = out[pk]
        o["demands"] += 1.0
        o["test"] += tw
        o["five"] += five
        o["bugs"] += _pf(r.get("总 bug 数"))
        o["rd_corr"] += corrected_rd(r)
    return out


def aggregate_team_period(
    rows: List[Dict[str, str]],
    periods: List[str],
    period_key: Callable[[Dict[str, str]], Optional[str]],
) -> Dict[str, Dict[str, Dict[str, float]]]:
    out: Dict[str, Dict[str, Dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    pset = set(periods)
    for r in rows:
        team = (r.get("业务线") or "").strip() or "其他"
        pk = period_key(r)
        if not pk or pk not in pset:
            continue
        d, rd, qc_e, tnode, te, pr, _tt = effort_fields(r)
        five = five_phase_total(r)
        bugs = _pf(r.get("总 bug 数"))
        rc = corrected_rd(r)
        tw = test_work_hours_v4(r)
        o = out[team][pk]
        o["demands"] += 1.0
        o["test"] += tw
        o["five"] += five
        o["bugs"] += bugs
        o["rd_corr"] += rc
    return {k: dict(v) for k, v in out.items()}


def aggregate_qc_period(
    rows: List[Dict[str, str]],
    periods: List[str],
    period_key: Callable[[Dict[str, str]], Optional[str]],
) -> Tuple[Dict[str, Dict[str, Dict[str, float]]], Dict[str, str]]:
    pset = set(periods)
    qc_p: Dict[str, Dict[str, Dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    qc_team_w: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        qcs = _qc_labels(r)
        if not qcs:
            continue
        w = 1.0 / len(qcs)
        team = (r.get("业务线") or "").strip() or "其他"
        pk = period_key(r)
        if not pk or pk not in pset:
            continue
        d, rd, qc_e, tnode, te, pr, _tt = effort_fields(r)
        five = five_phase_total(r)
        bugs = _pf(r.get("总 bug 数"))
        rc = corrected_rd(r)
        tw = test_work_hours_v4(r)
        for q in qcs:
            qc_team_w[q][team] += w
            o = qc_p[q][pk]
            o["demands_w"] += w
            o["test"] += tw * w
            o["five"] += five * w
            o["bugs_w"] += bugs * w
            o["rd_corr"] += rc * w
    team_main: Dict[str, str] = {}
    for q, tw in qc_team_w.items():
        team_main[q] = max(tw.items(), key=lambda kv: kv[1])[0] if tw else "其他"
    return {q: dict(per) for q, per in qc_p.items()}, team_main


# 每人收集关联需求条数上限（避免 HTML 过大）；表格内默认仅展示前若干条
MAX_QC_DEMANDS_IN_MODAL = 220
QC_DEMANDS_TABLE_CAP = 55


def build_qc_demand_details(
    rows: List[Dict[str, str]],
    months: List[str],
) -> Dict[str, List[Dict[str, Any]]]:
    """按与时间维个人聚合相同的月份窗口，收集每位 QC 关联的需求行（含链接、分摊测试工时等）。"""
    pset = set(months)
    by_q: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        qcs = _qc_labels(r)
        if not qcs:
            continue
        pk = _month_period_key(r)
        if not pk or pk not in pset:
            continue
        d, rd, qc_e, tnode, te, pr, _tt = effort_fields(r)
        five = five_phase_total(r)
        tw = test_work_hours_v4(r)
        if five <= 0 and tw <= 0:
            continue
        bugs = _pf(r.get("总 bug 数"))
        rc = corrected_rd(r)
        w = 1.0 / len(qcs)
        title = (r.get("名称") or "").strip() or "（未命名）"
        link = (r.get("需求链接") or "").strip()
        done = (r.get("完成日期") or "").strip()
        sp = (r.get("所属迭代") or "").strip()
        team = (r.get("业务线") or "").strip()
        req_type = (r.get("需求类型") or "").strip()
        prio = (r.get("优先级") or "").strip()
        tp_row = _pct(tw, five)
        for q in qcs:
            th = tw * w
            rt_q = round((rc * w) / (th + 1e-6), 2) if th > 1e-6 else 0.0
            by_q[q].append(
                {
                    "t": title[:220],
                    "u": link[:800],
                    "d": done[:40],
                    "s": sp[:100],
                    "tm": team[:160],
                    "m": pk,
                    "tp": tp_row,
                    "th": round(th, 3),
                    "w": round(w, 4),
                    "bg": round(bugs * w, 2),
                    "rt": rt_q,
                    "typ": req_type[:40],
                    "pr": prio[:16],
                }
            )
    out: Dict[str, List[Dict[str, Any]]] = {}
    for q, lst in by_q.items():
        lst.sort(key=lambda x: (-float(x["th"]), str(x.get("d") or ""), str(x.get("t") or "")))
        out[q] = lst[:MAX_QC_DEMANDS_IN_MODAL]
    return out


def dept_qc_expand_row_id(dept: str, q: str) -> str:
    """稳定 id，供按钮 aria-controls / 展开行引用。"""
    raw = f"{dept}\x1f{q}".encode("utf-8")
    return "qc-dem-" + hashlib.sha256(raw).hexdigest()[:18]


def build_qc_demand_panel_html(
    q: str,
    qc_demand_details: Dict[str, List[Dict[str, Any]]],
    *,
    per_qc_cap: int = QC_DEMANDS_TABLE_CAP,
) -> str:
    """整行 colspan 内：关联需求明细表（表头与主表同宽，视觉连贯）。"""
    items = qc_demand_details.get(q, [])[:per_qc_cap]
    n_all = len(qc_demand_details.get(q, ()))
    foot = ""
    if n_all > len(items):
        foot = (
            f'<p class="qc-demand-foot muted" style="margin:6px 0 0;font-size:11px;">'
            f"展示前 {len(items)} 条，共 {n_all} 条（按分摊测试工时降序）</p>"
        )
    elif n_all:
        foot = f'<p class="qc-demand-foot muted" style="margin:6px 0 0;font-size:11px;">共 {n_all} 条</p>'

    if not items:
        body = '<p class="muted" style="margin:0;font-size:12px;">本窗口期内无关联需求行</p>'
    else:
        trs: List[str] = []
        for it in items:
            t = html_module.escape(str(it.get("t") or ""))
            u = (it.get("u") or "").strip()
            title_cell = (
                f'<a href="{html_module.escape(u, quote=True)}" target="_blank" rel="noopener noreferrer" '
                f'style="color:#0369a1;text-decoration:underline;">{t}</a>'
                if u.startswith(("http://", "https://"))
                else t
            )
            trs.append(
                "<tr>"
                f'<td style="text-align:left;white-space:nowrap;">{html_module.escape(str(it.get("m") or "—"))}</td>'
                f'<td style="text-align:left;max-width:280px;">{title_cell}</td>'
                f"<td>{it.get('th', '')}</td>"
                f"<td>{it.get('tp', '')}%</td>"
                f"<td>{it.get('rt', '')}</td>"
                f'<td style="text-align:left;max-width:140px;">{html_module.escape(str(it.get("tm") or ""))}</td>'
                f'<td style="text-align:left;font-size:11px;">{html_module.escape(str(it.get("s") or ""))}</td>'
                "</tr>"
            )
        body = (
            '<div class="qc-demand-table-wrap">'
            "<table class=\"qc-demand-mini\"><thead><tr>"
            "<th>完成月</th><th>需求</th><th>分摊测试</th><th>测试占比%</th>"
            "<th>R/T</th><th>业务线</th><th>迭代</th>"
            "</tr></thead><tbody>"
            + "".join(trs)
            + "</tbody></table></div>"
        )

    return f"{body}{foot}"


def _glossary_html() -> str:
    return (
        '<div class="section glossary">'
        "<h2>七、指标与名词说明</h2>"
        "<p class=\"lead\"><strong>R/T（研发/测试）</strong>为本报告人员对标的主指标：<code>修正研发工时 ÷ 测试工时</code>。"
        "在可比口径下，<strong>R/T 越高</strong>通常表示<strong>单位测试工时对应的修正研发更重</strong>（估分左移、联调/方案偏重或需求类型更「重研发」等，需结合缺陷与发布质量解读，非单一好坏）。"
        "表格与散点中的<strong>相对部门 R/T%</strong>：<code>(本人 R/T − 部门平均 R/T) ÷ 部门平均 R/T</code>；<strong>正值</strong>表示相对部门更偏「重研发/轻测试嵌入」方向。</p>"
        "<ul class=\"glist\">"
        "<li><strong>测试工时（本报告主口径）</strong>：<code>QC测试用例设计与评审 + 测试估分 + 预发测试估分</code>，"
        "与 v4 业务线分析中「QC用例+测试+预发」一致；<strong>不用</strong> CSV「测试总估分(去除RD)」作为该指标分子。</li>"
        "<li><strong>加权需求数</strong>：「QC」字段列 <em>n</em> 人时每人计 <em>1/n</em>；测试工时、五阶段人天、修正研发、Bug 等亦按 <em>1/n</em> 摊到各人。</li>"
        "<li><strong>五阶段总人天</strong>：<code>技术方案设计与评审 + 研发总估分 + QC测试用例 + 测试估分 + 预发测试估分</code>。</li>"
        "<li><strong>测试工时占比%</strong>：<code>测试工时 ÷ 五阶段总人天 × 100%</code>；在缺陷与发布质量可控时，<strong>结构上倾向越低越好</strong>（左移、减少返工与估分膨胀会压低占比）。</li>"
        "<li><strong>R/T（研发/测试）</strong>：<code>修正研发工时 ÷ 测试工时</code>；修正研发定义同 Gate-RDJ 附录；此处分母为上述测试工时。</li>"
        "<li><strong>部门平均 R/T</strong>：部门内各 QC 个人 R/T 的<strong>算术平均</strong>（仅统计测试工时 &gt; 0.05 人天的成员）。</li>"
        "<li><strong>测试占比环比（相对%）</strong>：相邻上一完成月的个人测试占比为分母；上期为 0 时显示「—」。</li>"
        "<li><strong>关联需求</strong>：完成月落在报告月份内且 QC 白名单含该人；第五节部门表中<strong>点击 QC 姓名</strong>在下一整行展开同宽明细表，需求名可点击跳转「需求链接」。</li>"
        "<li><strong>价值类型（补充维度）</strong>：按 CSV <code>价值类型</code> 原文归档，空记「未分类」；全期测试工时 TOP10 单独展示，其余并入「（其他价值类型）」，可与互斥分类表对照解读。</li>"
        "<li><strong>是否紧急需求（补充维度）</strong>：<code>是否紧急需求</code> 满足 <code>is_urgent</code> 记「紧急」，否则「非紧急」；与互斥分类中「紧急需求」桶的判定一致，但此处不与技术/产品等规则竞争优先级。</li>"
        "<li><strong>需求分类（互斥）</strong>：每条需求仅归一类，优先级为 <code>紧急需求</code>（<code>是否紧急需求</code> 含「紧急」且不含「非」）"
        " &gt; <code>技术/优化类</code>（<code>需求类型</code> 含「技术」或 <code>价值类型</code> 含「技术」「优化」）"
        " &gt; <code>产品类</code>（需求类型含「产品」）&gt; <code>合规风控类</code>（需求类型含「合规」或「风控」）&gt; <code>其他</code>。"
        "用于观察「插单/技术债」对测试工时的结构占比；与业务线 v4 价值类型/需求类型视角对齐。</li>"
        "</ul></div>"
    )


def _rollup_qc_totals(qc_period: Dict[str, Dict[str, Dict[str, float]]]) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for q, per in qc_period.items():
        dw = te = fi = bw = rc = 0.0
        for _, o in per.items():
            dw += o.get("demands_w", 0)
            te += o.get("test", 0)
            fi += o.get("five", 0)
            bw += o.get("bugs_w", 0)
            rc += o.get("rd_corr", 0)
        out[q] = {"demands_w": dw, "test": te, "five": fi, "bugs_w": bw, "rd_corr": rc}
    return out


def _rollup_team_totals(team_p: Dict[str, Dict[str, Dict[str, float]]]) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for t, per in team_p.items():
        dm = te = fi = bw = rc = 0.0
        for _, o in per.items():
            dm += o.get("demands", 0)
            te += o.get("test", 0)
            fi += o.get("five", 0)
            bw += o.get("bugs", 0)
            rc += o.get("rd_corr", 0)
        out[t] = {"demands": dm, "test": te, "five": fi, "bugs": bw, "rd_corr": rc}
    return out


def _median(xs: List[float]) -> float:
    ys = sorted(x for x in xs if x == x)
    if not ys:
        return 0.0
    m = len(ys) // 2
    if len(ys) % 2:
        return ys[m]
    return (ys[m - 1] + ys[m]) / 2.0


def build_mom_table_rows(g: Dict[str, Dict[str, float]], keys: List[str]) -> str:
    lines: List[str] = []
    prev_tp: Optional[float] = None
    for k in keys:
        o = g.get(k, {})
        dm = int(o.get("demands", 0))
        tt = float(o.get("test", 0))
        fv = float(o.get("five", 0))
        tp = _pct(tt, fv)
        rel = _mom_rel(tp, prev_tp) if prev_tp is not None else None
        ppt = round(tp - prev_tp, 2) if prev_tp is not None else None
        rel_s = "—" if rel is None else f"{rel:+.1f}%"
        ppt_s = "—" if ppt is None else f"{ppt:+.2f}pt"
        lines.append(
            "<tr>"
            f"<td style=\"font-weight:600;\">{html_module.escape(k)}</td>"
            f"<td>{dm}</td><td>{round(tt, 1)}</td><td>{round(fv, 1)}</td>"
            f"<td>{tp}%</td>"
            f"<td>{'—' if prev_tp is None else f'{prev_tp}%'}</td>"
            f"<td>{rel_s}</td><td>{ppt_s}</td>"
            "</tr>"
        )
        prev_tp = tp
    return "\n".join(lines)


def suggest_team(
    _n: str, tp_last: float, tp_prev: Optional[float], rt_team: float, global_tp: float, global_rt_w: float
) -> str:
    """rt_team 为团队全期加权 R/T；global_rt_w 为全样本修正研发÷总测试工时。"""
    tips: List[str] = []
    if tp_last >= global_tp + 8:
        tips.append("测试占比较高，建议对齐拆批与准入，排查联调/返工对测试嵌入的推高。")
    elif tp_last <= global_tp - 8 and tp_last > 0:
        tips.append("测试占比低于全局；在质量与线上信号未弱化时，有利于端到端成本结构。")
    if tp_prev is not None and tp_last - tp_prev >= 5:
        tips.append("末月测试占比相对上月上升≥5pt，关注集中交付、缺陷返工或估分口径变化。")
    elif tp_prev is not None and tp_prev - tp_last >= 5:
        tips.append("末月测试占比下降≥5pt；若缺陷与发布质量稳定，多为正向结构信号。")
    if rt_team > 0 and global_rt_w > 0 and rt_team > global_rt_w * 1.22:
        tips.append("团队 R/T 高于全局加权水平，关注估分左移、联调成本与需求类型结构。")
    elif rt_team > 0 and global_rt_w > 0 and rt_team < global_rt_w * 0.78:
        tips.append("团队 R/T 明显低于全局，复核测试覆盖与风险是否被低估，或是否存在口径/摊分差异。")
    if not tips:
        tips.append("指标在常见区间，按迭代复盘需求—缺陷—返工链。")
    return "<br/>".join(f"· {html_module.escape(t)}" for t in tips[:4])


def suggest_person(
    _q: str,
    tp: float,
    rt: float,
    bugs_per_dem: float,
    mom_tp: Optional[float],
    team_tp_med: float,
    global_tp: float,
    vs_dept_rt_pct: Optional[float],
) -> str:
    tips: List[str] = []
    if vs_dept_rt_pct is not None:
        if vs_dept_rt_pct >= 18:
            tips.append(
                f"R/T 高于部门均值约 {vs_dept_rt_pct:.0f}%（修正研发相对测试更重），可对齐估分、拆批与需求类型结构。"
            )
        elif vs_dept_rt_pct <= -18:
            tips.append(
                f"R/T 低于部门均值约 {abs(vs_dept_rt_pct):.0f}%（测试嵌入相对更厚或研发摊分偏低），结合缺陷与发布质量复核。"
            )
    if tp >= global_tp + 12:
        tips.append("个人测试占比显著高于全局，核对名下大需求、返工与估分口径。")
    elif tp > 0 and tp <= global_tp - 10:
        tips.append("个人测试占比低于全局；在质量可控前提下多为结构上的有利信号。")
    if mom_tp is not None and abs(mom_tp) >= 8:
        tips.append(f"末月测试占比环比 {mom_tp:+.1f}%（相对上月占比值）。")
    if (vs_dept_rt_pct is None or abs(vs_dept_rt_pct) < 15) and rt >= 3.2:
        tips.append("R/T 绝对值偏高，与研发对齐估分假设与方案评审节奏。")
    if bugs_per_dem >= 4.5:
        tips.append("Bug/需求偏高，可做缺陷归类与准入加固。")
    if len(tips) < 2:
        tips.append("与部门均值对照后波动不大，保持节奏并盯住异常月。")
    return "".join(f"<div class='sline'>· {html_module.escape(t)}</div>" for t in tips[:6])


def _exec_summary_rich(
    *,
    g_m: Dict[str, Dict[str, float]],
    months: List[str],
    g_i: Dict[str, Dict[str, float]],
    iter_keys: List[str],
    qc_tot: Dict[str, Dict[str, float]],
    global_tp: float,
    g_dem: int,
    n_qc: int,
    global_rt_med: float,
    five_sum: float,
    test_sum: float,
    bug_sum: float,
    rd_corr_sum: float,
    cat_roll: Dict[str, Dict[str, float]],
) -> str:
    """P10 式执行摘要：方向、可量化盘面、观察、风险边界、近期节奏——对齐业务线 v4 版式。"""
    tps_m = [(m, _pct(g_m[m]["test"], g_m[m]["five"])) for m in months if m in g_m]
    lo_m = min(tps_m, key=lambda x: x[1])[0] if tps_m else "—"
    hi_m = max(tps_m, key=lambda x: x[1])[0] if tps_m else "—"
    lo_v = _pct(g_m[lo_m]["test"], g_m[lo_m]["five"]) if lo_m in g_m else 0.0
    hi_v = _pct(g_m[hi_m]["test"], g_m[hi_m]["five"]) if hi_m in g_m else 0.0
    tp_span = round(hi_v - lo_v, 2) if tps_m else 0.0
    tps_i = [(s, _pct(g_i[s]["test"], g_i[s]["five"])) for s in iter_keys if s in g_i]
    lo_s = min(tps_i, key=lambda x: x[1])[0] if tps_i else "—"
    hi_s = max(tps_i, key=lambda x: x[1])[0] if tps_i else "—"
    lo_sv = _pct(g_i[lo_s]["test"], g_i[lo_s]["five"]) if lo_s in g_i else 0.0
    hi_sv = _pct(g_i[hi_s]["test"], g_i[hi_s]["five"]) if hi_s in g_i else 0.0

    rt_glob = round(rd_corr_sum / (test_sum + 1e-6), 2) if test_sum > 1e-6 else 0.0
    bpd_glob = round(bug_sum / (g_dem + 1e-6), 2) if g_dem else 0.0

    n_high_rt = 0
    n_high_tp = 0
    for v in qc_tot.values():
        if v.get("test", 0) <= 0.05:
            continue
        rq = _rt(v.get("rd_corr", 0), v.get("test", 0))
        if global_rt_med > 1e-6 and rq > global_rt_med * 1.25:
            n_high_rt += 1
        tpq = _pct(v["test"], v["five"])
        if tpq > global_tp + 8:
            n_high_tp += 1

    net_tp_window = 0.0
    if len(months) >= 2:
        tp_a = _pct(g_m[months[0]]["test"], g_m[months[0]]["five"])
        tp_z = _pct(g_m[months[-1]]["test"], g_m[months[-1]]["five"])
        net_tp_window = round(tp_z - tp_a, 2)

    p2: List[str] = []
    if len(months) >= 2:
        a, b = months[-2], months[-1]
        tpa = _pct(g_m.get(a, {}).get("test", 0), g_m.get(a, {}).get("five", 0))
        tpb = _pct(g_m.get(b, {}).get("test", 0), g_m.get(b, {}).get("five", 0))
        p2.append(
            f"<li><strong>时间维最近两月：</strong>{html_module.escape(a)} <b>{tpa}%</b> → {html_module.escape(b)} <b>{tpb}%</b>"
            f"（<b>{round(tpb - tpa, 2):+}</b> pt）。</li>"
        )
    if len(iter_keys) >= 2:
        a, b = iter_keys[-2], iter_keys[-1]
        tpa = _pct(g_i.get(a, {}).get("test", 0), g_i.get(a, {}).get("five", 0))
        tpb = _pct(g_i.get(b, {}).get("test", 0), g_i.get(b, {}).get("five", 0))
        p2.append(
            f"<li><strong>迭代维最近两期：</strong>{html_module.escape(a)} <b>{tpa}%</b> → {html_module.escape(b)} <b>{tpb}%</b>"
            f"（<b>{round(tpb - tpa, 2):+}</b> pt）。</li>"
        )

    obs: List[str] = []
    if tps_m:
        obs.append(
            f"分月测试占比波动幅度约 <b>{tp_span}</b> pt（最低 {html_module.escape(str(lo_m))} {lo_v}% → 最高 {html_module.escape(str(hi_m))} {hi_v}%），"
            "窗口首末月净变化 "
            f"<b>{net_tp_window:+}</b> pt；用于判断测试嵌入是阶段性冲高还是持续改善/恶化。"
        )
    obs.append(
        f"在册白名单 QC <b>{n_qc}</b> 人中，约 <b>{n_high_rt}</b> 人个人 <strong>R/T</strong> 显著高于全局 R/T 中位（修正研发相对测试更重），"
        f"约 <b>{n_high_tp}</b> 人个人测试占比高于全局均值+8pt；二者交叉可作为下一轮点名复盘优先级。"
    )
    obs.append(
        f"全期口径下整体 R/T 约 <b>{rt_glob}</b>、Bug/需求约 <b>{bpd_glob}</b>；若占比下行但 Bug 上行，优先怀疑返工与估分口径而非单纯「测少了」。"
    )
    if test_sum > 1e-6 and cat_roll:
        urg_t = float((cat_roll.get("紧急需求") or {}).get("test", 0))
        tech_t = float((cat_roll.get("技术/优化类") or {}).get("test", 0))
        prod_t = float((cat_roll.get("产品类") or {}).get("test", 0))
        pu = round(urg_t / test_sum * 100, 1)
        pt = round(tech_t / test_sum * 100, 1)
        pp = round(prod_t / test_sum * 100, 1)
        obs.append(
            f"需求分类（互斥）下，全期测试工时约 <b>{pu}%</b> 落在「紧急」、<b>{pt}%</b> 落在「技术/优化」、<b>{pp}%</b> 落在「产品」；"
            "若<strong>紧急+技优</strong>合计长期偏高，宜与插单节奏、技术债排期及估分压缩<strong>同屏复盘</strong>，避免单看总占比误判。"
        )

    cards = (
        f'<div class="card"><h3>需求总数</h3><div class="value">{int(g_dem)}</div></div>'
        f'<div class="card"><h3>五阶段总工时</h3><div class="value">{round(five_sum, 1)}</div><div class="sub">人天</div></div>'
        f'<div class="card"><h3>测试工时</h3><div class="value test">{round(test_sum, 1)}</div><div class="sub">QC+测+预发</div></div>'
        f'<div class="card"><h3>全局测试占比</h3><div class="value test">{global_tp}%</div><div class="sub">测÷五阶段</div></div>'
        f'<div class="card"><h3>修正研发合计</h3><div class="value">{round(rd_corr_sum, 1)}</div><div class="sub">人天</div></div>'
        f'<div class="card"><h3>R/T中位(QC)</h3><div class="value">{round(global_rt_med, 2)}</div><div class="sub">个人维度中位</div></div>'
        f'<div class="card"><h3>白名单 QC</h3><div class="value">{n_qc}</div><div class="sub">人</div></div>'
        f'<div class="card"><h3>全局 R/T</h3><div class="value">{rt_glob}</div><div class="sub">修正研发÷测试</div></div>'
        f'<div class="card"><h3>Bug/需求</h3><div class="value">{bpd_glob}</div><div class="sub">全期近似</div></div>'
    )

    mom_ul = "<ul class=\"brief-ul\">" + "".join(p2) + "</ul>" if p2 else ""
    obs_parts = [f"<li>{o}</li>" for o in obs]
    obs_ul = "<ul class=\"brief-ul\">" + "".join(obs_parts) + "</ul>"

    return f"""
<div class="section">
  <div class="section-title">执行摘要（战略视角 · 总）</div>
  <div class="summary-cards">{cards}</div>
  <div class="conclusion-box" style="margin-top:14px;">
    <div class="conclusion-title">方向与成功标准</div>
    <p class="brief-p">本报告回答三件事：<strong>①</strong>测试工时在端到端估分中的<strong>结构占比</strong>是否可控（质量与风险可比时，占比<strong>倾向压低</strong>）；<strong>②</strong>个人 <strong>R/T（修正研发÷测试）</strong>是否可对标<strong>部门均值与全局 R/T 中位</strong>；<strong>③</strong>在<strong>互斥需求分类</strong>（紧急 / 技术·优化 / 产品 / 合规 / 其他）下，测试工时<strong>结构</strong>是否被插单与技术债过度挤压。<strong>成功标准</strong>不是单一排名，而是「占比 + R/T + 类型结构」的联合解读——在 Bug/线上信号不恶化的前提下，端到端估分与风险可解释、可复盘。</p>
  </div>
  <div class="grid-2 brief-grid">
    <div class="panel-blue">
      <div class="panel-title">关键观察（数据驱动）</div>
      {obs_ul}
      {mom_ul}
    </div>
    <div class="panel-amber">
      <div class="panel-title">风险、边界与 P9 动作</div>
      <ul class="brief-ul">
        <li><strong>误判风险：</strong>仅看「测试占比低」可能掩盖估分左移不足或缺陷外溢；必须<strong>与 Bug/需求、R/T、紧急需求</strong>同屏解读。</li>
        <li><strong>本报告不做：</strong>因果归责到个人绩效、不替代 Jira/门禁结论、不覆盖未进白名单的需求行。</li>
        <li><strong>建议 P9 收口：</strong>① 对「<strong>高 R/T × 高测试占比</strong>」象限名单做<strong>需求级</strong>复盘模板；② 对占比冲高月份做<strong>发布窗口与（二）需求分类结构</strong>对齐；③ 下一轮固定<strong>同一工时口径</strong>复测环比。</li>
      </ul>
    </div>
  </div>
</div>
"""


def _closing_text(
    global_tp: float,
    global_rt_w: float,
    global_rt_med: float,
    months: List[str],
    iter_keys: List[str],
) -> str:
    return (
        '<div class="section closing"><h2>六、总结（总）</h2>'
        "<p class=\"lead\">基于上述分月、<strong>需求分类结构</strong>与分迭代的<strong>先事实后判断</strong>，建议将「测试占比偏高月份/迭代」与"
        "「<strong>R/T</strong> 显著高于部门或全局中位」的个人做<strong>交叉点名</strong>：对照缺陷、返工、插单/技优占比与估分口径，区分结构性偏高与个案拖尾。"
        f"全期全局测试占比约 <b>{global_tp}%</b>、全局加权 R/T 约 <b>{round(global_rt_w, 2)}</b>、QC 个人 R/T 中位约 <b>{round(global_rt_med, 2)}</b>，可作为内部对标参考（非唯一目标）。"
        f"覆盖月份：{html_module.escape('、'.join(months))}；迭代序列：{html_module.escape(' → '.join(iter_keys))}。</p></div>"
    )


def build_html_p9(
    *,
    label_time: str,
    label_iter: str,
    months: List[str],
    iter_keys: List[str],
    rows_t: List[Dict[str, str]],
    rows_i: List[Dict[str, str]],
    team_m: Dict[str, Dict[str, Dict[str, float]]],
    team_i: Dict[str, Dict[str, Dict[str, float]]],
    qc_m: Dict[str, Dict[str, Dict[str, float]]],
    qc_team: Dict[str, str],
    qc_demand_details: Dict[str, List[Dict[str, Any]]],
) -> str:
    g_m = aggregate_global_period(rows_t, months, _month_period_key)
    g_i = aggregate_global_period(rows_i, iter_keys, _sp_label)

    g_test = sum(o.get("test", 0) for o in g_m.values())
    g_five = sum(o.get("five", 0) for o in g_m.values())
    g_dem = sum(o.get("demands", 0) for o in g_m.values())
    bug_sum = sum(o.get("bugs", 0) for o in g_m.values())
    rd_corr_sum = sum(o.get("rd_corr", 0) for o in g_m.values())
    global_tp = _pct(g_test, g_five)
    global_rt_w = round(rd_corr_sum / (g_test + 1e-6), 4) if g_test > 1e-6 else 0.0

    qc_tot = _rollup_qc_totals(qc_m)
    rts = [_rt(v.get("rd_corr", 0), v.get("test", 0)) for v in qc_tot.values() if v.get("test", 0) > 0.05]
    global_rt_med = round(_median(rts), 4)

    # 部门 = 业务线；部门平均 R/T = 部门内各人 R/T 的算术平均（仅 test>0.05 的成员）
    dept_qcs: Dict[str, List[str]] = defaultdict(list)
    for q, dept in qc_team.items():
        if q in qc_tot:
            dept_qcs[dept].append(q)
    dept_mean_rt: Dict[str, float] = {}
    for dept, qs in dept_qcs.items():
        el = [_rt(qc_tot[q]["rd_corr"], qc_tot[q]["test"]) for q in qs if qc_tot[q]["test"] > 0.05]
        dept_mean_rt[dept] = round(sum(el) / len(el), 4) if el else 0.0
    cat_m = aggregate_demand_category_period(rows_t, months, _month_period_key)
    cat_i = aggregate_demand_category_period(rows_i, iter_keys, _sp_label)
    cat_roll = _rollup_category_window(cat_m, months)
    exec_html = _exec_summary_rich(
        g_m=g_m,
        months=months,
        g_i=g_i,
        iter_keys=iter_keys,
        qc_tot=qc_tot,
        global_tp=global_tp,
        g_dem=int(g_dem),
        n_qc=len(qc_tot),
        global_rt_med=global_rt_med,
        five_sum=g_five,
        test_sum=g_test,
        bug_sum=bug_sum,
        rd_corr_sum=rd_corr_sum,
        cat_roll=cat_roll,
    )
    mom_month_rows = build_mom_table_rows(g_m, months)
    mom_iter_rows = build_mom_table_rows(g_i, iter_keys)

    month_labels = [_fmt_month_axis(m) for m in months]
    iter_labels = [_fmt_sp_axis(s) for s in iter_keys]
    cat_stack_js = _category_stack_json(cat_m, months, month_labels)
    cat_global_rows = _html_category_global_table(cat_roll, g_test, int(g_dem))
    mh, mrows = _html_category_month_pivot(cat_m, months)
    ih, irows = _html_category_iter_pivot(cat_i, iter_keys)

    vt_raw_m = aggregate_dim_bucket_period(rows_t, months, _month_period_key, _norm_value_type_field)
    vt_order_m, vt_m = collapse_value_types_by_test_volume(vt_raw_m, months, MAX_VALUE_TYPE_TOP)
    vt_raw_i = aggregate_dim_bucket_period(rows_i, iter_keys, _sp_label, _norm_value_type_field)
    vt_order_i, vt_i = collapse_value_types_by_test_volume(vt_raw_i, iter_keys, MAX_VALUE_TYPE_TOP)
    urg_raw_m = aggregate_dim_bucket_period(rows_t, months, _month_period_key, _urgent_binary_label)
    urg_raw_i = aggregate_dim_bucket_period(rows_i, iter_keys, _sp_label, _urgent_binary_label)
    urg_m = _normalize_urgent_period(urg_raw_m, months)
    urg_i = _normalize_urgent_period(urg_raw_i, iter_keys)
    vt_roll_m = _rollup_dim_window(vt_m, months, vt_order_m)
    vt_roll_i = _rollup_dim_window(vt_i, iter_keys, vt_order_i)
    urg_roll_m = _rollup_dim_window(urg_m, months, list(_URGENT_ORDER))
    urg_roll_i = _rollup_dim_window(urg_i, iter_keys, list(_URGENT_ORDER))

    vt_stack_month_js = (
        _dynamic_stack_json(vt_order_m, vt_m, months, month_labels, stack_id="vt", colors=_vt_color)
        if vt_order_m
        else json.dumps({"labels": month_labels, "series": []}, ensure_ascii=False)
    )
    vt_stack_iter_js = (
        _dynamic_stack_json(vt_order_i, vt_i, iter_keys, iter_labels, stack_id="vti", colors=_vt_color)
        if vt_order_i
        else json.dumps({"labels": iter_labels, "series": []}, ensure_ascii=False)
    )
    urg_stack_month_js = _dynamic_stack_json(
        list(_URGENT_ORDER), urg_m, months, month_labels, stack_id="urg", colors=_urg_color
    )
    urg_stack_iter_js = _dynamic_stack_json(
        list(_URGENT_ORDER), urg_i, iter_keys, iter_labels, stack_id="urgi", colors=_urg_color
    )

    mh_vt = "".join(f"<th>{html_module.escape(x)}</th>" for x in month_labels)
    ih_vt = "".join(f"<th>{html_module.escape(x)}</th>" for x in iter_labels)
    vt_global_rows = _html_dim_global_table(vt_roll_m, vt_order_m, g_test, int(g_dem)) if vt_order_m else ""
    vt_month_rows = _html_dim_month_pivot(vt_m, months, vt_order_m) if vt_order_m else ""
    vt_iter_rows = _html_dim_month_pivot(vt_i, iter_keys, vt_order_i) if vt_order_i else ""
    urg_global_rows = _html_dim_global_table(urg_roll_m, list(_URGENT_ORDER), g_test, int(g_dem))
    urg_month_rows = _html_dim_month_pivot(urg_m, months, list(_URGENT_ORDER))
    urg_iter_rows = _html_dim_month_pivot(urg_i, iter_keys, list(_URGENT_ORDER))

    colspan_vt_month = len(months) + 1
    colspan_vt_iter = len(iter_keys) + 1
    vt_month_fallback = f'<tr><td colspan="{colspan_vt_month}" class="muted">—</td></tr>'
    vt_iter_fallback = f'<tr><td colspan="{colspan_vt_iter}" class="muted">—</td></tr>'

    category_section_html = f"""
    <div class="section">
      <h2>（二）分 · 需求分类（紧急 / 技术·优化 / 产品 / …）</h2>
      <p class="lead">以下为<strong>互斥分类</strong>：每条需求仅归一类，优先级为 <strong>紧急</strong> &gt; <strong>技术/优化</strong> &gt; <strong>产品</strong> &gt; <strong>合规风控</strong> &gt; <strong>其他</strong>；口径与<strong>第七节附录</strong>一致。堆叠图纵轴为<strong>测试工时</strong>（QC+测试+预发）；分月表中括号内为该类占<strong>当月测试工时</strong>比重。同节下文补充<strong>价值类型</strong>与<strong>是否紧急</strong>两个独立视角（非互斥优先级），可与互斥桶对照阅读。</p>
      <div id="c-cat-month-stack" class="chart compact"></div>
      <p class="note">全期汇总：「占全期测试工时%」= 该类测试工时 ÷ 全期总测试工时；「占全期需求%」= 该类需求条数 ÷ 全期需求条数；「该类测占五阶段%」= 该类测试工时 ÷ 该类五阶段人天。</p>
      <div class="table-wrap">
        <table><thead><tr>
          <th>分类</th><th>需求数</th><th>占全期需求%</th><th>测试工时</th><th>占全期测试工时%</th><th>该类测占五阶段%</th><th>类内Bug/需求</th>
        </tr></thead><tbody>
        {cat_global_rows}
        </tbody></table>
      </div>
      <h3 style="margin:14px 0 8px;font-size:14px;color:#334155;">分月测试工时（按类）</h3>
      <div class="table-wrap">
        <table><thead><tr><th>分类</th>{mh}</tr></thead><tbody>
        {mrows}
        </tbody></table>
      </div>
      <h3 style="margin:14px 0 8px;font-size:14px;color:#334155;">迭代维 · 各 SP 需求数（按类）</h3>
      <div class="table-wrap">
        <table><thead><tr><th>分类</th>{ih}</tr></thead><tbody>
        {irows}
        </tbody></table>
      </div>

      <h3 style="margin:22px 0 10px;font-size:15px;color:#0c4a6e;font-weight:700;border-top:1px dashed #cbd5e1;padding-top:16px;">补充维度 · 按 CSV「价值类型」字段</h3>
      <p class="lead">与上文<strong>互斥分类</strong>不同：每条需求按导出表<strong>价值类型</strong>原样归档（空值记为「未分类」）；全期测试工时 TOP{MAX_VALUE_TYPE_TOP} 的价值类型单独展示，其余合并为<strong>{OTHER_VALUE_TYPE_LABEL}</strong>。堆叠图纵轴仍为<strong>测试工时</strong>（QC+测试+预发）。</p>
      <div class="chart-grid">
        <div id="c-vt-month-stack" class="chart compact"></div>
        <div id="c-vt-iter-stack" class="chart compact"></div>
      </div>
      <p class="note">汇总表口径与互斥分类小节「全期汇总」列一致；分月/分迭代括号内为占<strong>当期该维度合计测试工时</strong>比重。</p>
      <div class="table-wrap">
        <table><thead><tr>
          <th>价值类型</th><th>需求数</th><th>占全期需求%</th><th>测试工时</th><th>占全期测试工时%</th><th>该类测占五阶段%</th><th>类内Bug/需求</th>
        </tr></thead><tbody>
        {vt_global_rows if vt_global_rows else '<tr><td colspan="7" class="muted">无数值类型分布</td></tr>'}
        </tbody></table>
      </div>
      <h4 style="margin:14px 0 8px;font-size:13px;color:#334155;">分月测试工时（按价值类型）</h4>
      <div class="table-wrap">
        <table><thead><tr><th>价值类型</th>{mh_vt}</tr></thead><tbody>
        {vt_month_rows if vt_month_rows else vt_month_fallback}
        </tbody></table>
      </div>
      <h4 style="margin:14px 0 8px;font-size:13px;color:#334155;">分迭代测试工时（按价值类型）</h4>
      <div class="table-wrap">
        <table><thead><tr><th>价值类型</th>{ih_vt}</tr></thead><tbody>
        {vt_iter_rows if vt_iter_rows else vt_iter_fallback}
        </tbody></table>
      </div>

      <h3 style="margin:22px 0 10px;font-size:15px;color:#0c4a6e;font-weight:700;border-top:1px dashed #cbd5e1;padding-top:16px;">补充维度 · 按「是否紧急需求」</h3>
      <p class="lead"><strong>紧急</strong>：<code>是否紧急需求</code> 含「紧急」且不含「非」（与第七节 <code>is_urgent</code> 一致）；其余记为<strong>非紧急</strong>。每条需求仅归入其一。</p>
      <div class="chart-grid">
        <div id="c-urgent-month-stack" class="chart compact"></div>
        <div id="c-urgent-iter-stack" class="chart compact"></div>
      </div>
      <div class="table-wrap">
        <table><thead><tr>
          <th>紧急度</th><th>需求数</th><th>占全期需求%</th><th>测试工时</th><th>占全期测试工时%</th><th>该类测占五阶段%</th><th>类内Bug/需求</th>
        </tr></thead><tbody>
        {urg_global_rows}
        </tbody></table>
      </div>
      <h4 style="margin:14px 0 8px;font-size:13px;color:#334155;">分月测试工时（紧急 / 非紧急）</h4>
      <div class="table-wrap">
        <table><thead><tr><th>紧急度</th>{mh_vt}</tr></thead><tbody>
        {urg_month_rows}
        </tbody></table>
      </div>
      <h4 style="margin:14px 0 8px;font-size:13px;color:#334155;">分迭代测试工时（紧急 / 非紧急）</h4>
      <div class="table-wrap">
        <table><thead><tr><th>紧急度</th>{ih_vt}</tr></thead><tbody>
        {urg_iter_rows}
        </tbody></table>
      </div>
    </div>
"""
    month_dem = [int(g_m[m]["demands"]) for m in months]
    month_test = [round(g_m[m]["test"], 1) for m in months]
    month_tp = [_pct(g_m[m]["test"], g_m[m]["five"]) for m in months]

    iter_dem = [int(g_i[s]["demands"]) for s in iter_keys]
    iter_test = [round(g_i[s]["test"], 1) for s in iter_keys]
    iter_tp = [_pct(g_i[s]["test"], g_i[s]["five"]) for s in iter_keys]

    global_month_js = json.dumps(
        {"labels": month_labels, "demands": month_dem, "tests": month_test, "tps": month_tp, "rawKeys": months},
        ensure_ascii=False,
    )
    global_iter_js = json.dumps(
        {"labels": iter_labels, "demands": iter_dem, "tests": iter_test, "tps": iter_tp, "rawKeys": iter_keys},
        ensure_ascii=False,
    )

    last_m = months[-1] if months else None
    prev_m = months[-2] if len(months) >= 2 else None
    last_s = iter_keys[-1] if iter_keys else None
    prev_s = iter_keys[-2] if len(iter_keys) >= 2 else None

    team_totals = _rollup_team_totals(team_m)
    # 迭代维 CSV 中可能出现时间维窗口未覆盖到的业务线，一并纳入列表
    for t in team_i.keys():
        if t not in team_totals:
            team_totals[t] = {"demands": 0.0, "test": 0.0, "five": 0.0, "bugs": 0.0, "rd_corr": 0.0}
    # 第四节：含全部业务线（团队），按全期测试工时降序
    ranked_teams = sorted(team_totals.items(), key=lambda kv: -kv[1]["test"])
    n_teams_section = len(ranked_teams)
    team_h_bar_px = max(340, min(2000, 20 * n_teams_section + 100))
    team_rows_html: List[str] = []
    trend_series: List[Dict[str, Any]] = []
    for team, _ in ranked_teams:
        per = team_m.get(team, {})
        tot = team_totals[team]
        tp_all = _pct(tot["test"], tot["five"])
        rt_team = _rt(tot["rd_corr"], tot["test"])
        bugs_pd = round(tot["bugs"] / (tot["demands"] + 1e-6), 2)
        tp_last = _pct(per.get(last_m, {}).get("test", 0), per.get(last_m, {}).get("five", 0)) if last_m else 0.0
        tp_prev = (
            _pct(per.get(prev_m, {}).get("test", 0), per.get(prev_m, {}).get("five", 0)) if prev_m else None
        )
        mom_rel = _mom_rel(tp_last, tp_prev) if tp_prev is not None else None
        ppt = round(tp_last - tp_prev, 2) if tp_prev is not None else None
        mom_cell = "—" if mom_rel is None else f"{mom_rel:+.1f}%"
        ppt_cell = "—" if ppt is None else f"{ppt:+.2f}pt"
        sug = suggest_team(team, tp_last, tp_prev, rt_team, global_tp, global_rt_w)
        team_rows_html.append(
            "<tr>"
            f'<td style="text-align:left;font-weight:600;">{html_module.escape(team)}</td>'
            f"<td>{int(tot['demands'])}</td><td>{round(tot['test'], 1)}</td><td>{tp_all}%</td>"
            f"<td>{rt_team}</td><td>{bugs_pd}</td><td>{tp_last}%</td>"
            f"<td>{mom_cell}</td><td>{ppt_cell}</td>"
            f'<td style="text-align:left;font-size:12px;">{sug}</td></tr>'
        )
        trend_series.append(
            {
                "name": team,
                "type": "line",
                "smooth": 0.15,
                "symbolSize": 5,
                "label": _ECHARTS_TP_LINE_LABEL,
                "data": [_pct(per.get(m, {}).get("test", 0), per.get(m, {}).get("five", 0)) for m in months],
            }
        )
    global_line = [_pct(sum(team_m[t].get(m, {}).get("test", 0) for t in team_m), sum(team_m[t].get(m, {}).get("five", 0) for t in team_m)) for m in months]
    trend_series.append(
        {
            "name": "【全局】",
            "type": "line",
            "smooth": 0.15,
            "lineStyle": {"type": "dashed", "width": 2},
            "label": _ECHARTS_TP_LINE_LABEL,
            "data": global_line,
        }
    )

    # 各团队测试工时占比 · 分迭代（与分月折线同一批团队 + 全局虚线）
    iter_trend_series: List[Dict[str, Any]] = []
    for team, _ in ranked_teams:
        per_i = team_i.get(team, {})
        iter_trend_series.append(
            {
                "name": team,
                "type": "line",
                "smooth": 0.15,
                "symbolSize": 5,
                "label": _ECHARTS_TP_LINE_LABEL,
                "data": [
                    _pct(per_i.get(s, {}).get("test", 0), per_i.get(s, {}).get("five", 0))
                    for s in iter_keys
                ],
            }
        )
    global_iter_team_tp = [
        _pct(
            sum(team_i[t].get(s, {}).get("test", 0) for t in team_i),
            sum(team_i[t].get(s, {}).get("five", 0) for t in team_i),
        )
        for s in iter_keys
    ]
    iter_trend_series.append(
        {
            "name": "【全局】",
            "type": "line",
            "smooth": 0.15,
            "lineStyle": {"type": "dashed", "width": 2},
            "label": _ECHARTS_TP_LINE_LABEL,
            "data": global_iter_team_tp,
        }
    )

    team_tp_pivot_html = build_team_test_pct_pivot_html(
        ranked_teams, team_m, team_i, months, month_labels, iter_keys, iter_labels
    )

    iter_mom_rows: List[str] = []
    for team, _ in ranked_teams:
        per = team_i.get(team, {})
        tp_last = _pct(per.get(last_s, {}).get("test", 0), per.get(last_s, {}).get("five", 0)) if last_s else 0.0
        tp_prev = _pct(per.get(prev_s, {}).get("test", 0), per.get(prev_s, {}).get("five", 0)) if prev_s else None
        rel = _mom_rel(tp_last, tp_prev) if tp_prev is not None else None
        ppt = round(tp_last - tp_prev, 2) if tp_prev is not None else None
        iter_mom_rows.append(
            "<tr>"
            f'<td style="text-align:left;">{html_module.escape(team)}</td>'
            f"<td>{html_module.escape(str(last_s or '—'))}</td>"
            f"<td>{tp_last}%</td>"
            f"<td>{'—' if rel is None else f'{rel:+.1f}%'}</td>"
            f"<td>{'—' if ppt is None else f'{ppt:+.2f}pt'}</td>"
            "</tr>"
        )

    team_tp_medians: Dict[str, List[float]] = defaultdict(list)
    for q, tot in qc_tot.items():
        tm = qc_team.get(q, "其他")
        if tot["five"] > 0:
            team_tp_medians[tm].append(_pct(tot["test"], tot["five"]))
    team_tp_med: Dict[str, float] = {t: _median(v) for t, v in team_tp_medians.items()}

    # 按部门聚合的个人表块
    dept_blocks: List[str] = []
    for dept in sorted(dept_qcs.keys(), key=lambda d: -sum(qc_tot[q]["test"] for q in dept_qcs[d])):
        dm_rt = dept_mean_rt.get(dept, 0.0)
        rows_d: List[str] = []
        for q in sorted(dept_qcs[dept], key=lambda x: -qc_tot[x]["test"]):
            tot = qc_tot[q]
            tp = _pct(tot["test"], tot["five"])
            rt = _rt(tot["rd_corr"], tot["test"])
            bpd = round(tot["bugs_w"] / (tot["demands_w"] + 1e-6), 2)
            per = qc_m.get(q, {})
            tp_last = _pct(per.get(last_m, {}).get("test", 0), per.get(last_m, {}).get("five", 0)) if last_m else 0.0
            tp_prev = _pct(per.get(prev_m, {}).get("test", 0), per.get(prev_m, {}).get("five", 0)) if prev_m else None
            mom_rel = _mom_rel(tp_last, tp_prev) if tp_prev is not None else None
            mom_cell = "—" if mom_rel is None else f"{mom_rel:+.1f}%"
            vs_rt = round((rt - dm_rt) / dm_rt * 100, 1) if dm_rt > 1e-6 else None
            vs_cell = "—" if vs_rt is None else f"{vs_rt:+.1f}%"
            sug = suggest_person(
                q, tp, rt, bpd, mom_rel, team_tp_med.get(dept, global_tp), global_tp, vs_rt
            )
            row_id = dept_qc_expand_row_id(dept, q)
            panel = build_qc_demand_panel_html(q, qc_demand_details)
            name_btn = (
                f'<button type="button" class="qc-name-toggle" aria-expanded="false" '
                f'aria-controls="{html_module.escape(row_id, quote=True)}">'
                f"{html_module.escape(q)}</button>"
            )
            rows_d.append(
                '<tr class="qc-summary-row">'
                f'<td class="qc-name-cell" style="text-align:left;vertical-align:middle;">{name_btn}</td>'
                f"<td>{rt}</td><td>{dm_rt}</td><td>{vs_cell}</td>"
                f"<td>{tp}%</td><td>{round(tot['demands_w'], 2)}</td><td>{round(tot['test'], 1)}</td>"
                f"<td>{tp_last}%</td><td>{mom_cell}</td>"
                f'<td style="text-align:left;max-width:380px;">{sug}</td></tr>'
            )
            rows_d.append(
                f'<tr class="qc-demand-expand-row" id="{html_module.escape(row_id, quote=True)}" hidden>'
                '<td colspan="10" class="qc-demand-expand-cell">'
                f'<div class="qc-demand-drawer">{panel}</div></td></tr>'
            )
        nmem = len(dept_qcs[dept])
        dept_blocks.append(
            f'<section class="dept"><h3>{html_module.escape(dept)} <span class="subh">（{nmem} 人 · 部门平均 R/T {dm_rt}）</span></h3>'
            '<div class="table-wrap"><table><thead><tr>'
            "<th>QC</th><th>R/T</th><th>部门R/T均值</th><th>相对部门R/T%</th>"
            "<th>测试占比%</th><th>加权需求</th><th>测试工时</th><th>末月占比%</th><th>占比环比(相对%)</th><th>建议</th>"
            "</tr></thead><tbody>"
            + "\n".join(rows_d)
            + "</tbody></table></div>"
            + "</section>"
        )

    team_names_c = [t for t, _ in ranked_teams]
    team_test_vals = [round(team_totals[t]["test"], 1) for t in team_names_c]
    team_tp_vals = [round(_pct(team_totals[t]["test"], team_totals[t]["five"]), 2) for t in team_names_c]
    iter_chart_teams = [t for t, _ in ranked_teams]
    iter_prev_vals = [
        round(_pct(team_i.get(t, {}).get(prev_s, {}).get("test", 0), team_i.get(t, {}).get(prev_s, {}).get("five", 0)), 2)
        if prev_s
        else 0.0
        for t in iter_chart_teams
    ]
    iter_last_vals = [
        round(_pct(team_i.get(t, {}).get(last_s, {}).get("test", 0), team_i.get(t, {}).get(last_s, {}).get("five", 0)), 2)
        if last_s
        else 0.0
        for t in iter_chart_teams
    ]

    scatter_pts: List[Dict[str, Any]] = []
    for q in sorted(qc_tot.keys(), key=lambda x: -qc_tot[x]["test"])[:55]:
        tot = qc_tot[q]
        dept = qc_team.get(q, "其他")
        dm_rt = dept_mean_rt.get(dept, 0.0)
        rt = _rt(tot["rd_corr"], tot["test"])
        tp_q = round(_pct(tot["test"], tot["five"]), 2)
        vs_rt = round((rt - dm_rt) / dm_rt * 100, 1) if dm_rt > 1e-6 else 0.0
        sz = max(10, min(44, round(float(tot["test"]) ** 0.55 * 4)))
        scatter_pts.append(
            {
                "name": q,
                "value": [round(vs_rt, 1), tp_q],
                "rt": rt,
                "dept": dept,
                "dm": dm_rt,
                "testH": round(tot["test"], 1),
                "symbolSize": sz,
            }
        )
    top_qc = sorted(qc_tot.items(), key=lambda kv: -kv[1]["test"])[:22]
    qc_bar_names = [k for k, _ in top_qc]
    qc_bar_vals = [round(v["test"], 1) for _, v in top_qc]

    months_js = json.dumps(months, ensure_ascii=False)
    trend_js = json.dumps(trend_series, ensure_ascii=False, separators=(",", ":"))
    team_tp_iter_js = json.dumps(
        {"labels": iter_labels, "series": iter_trend_series},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    team_bar_js = json.dumps({"names": team_names_c, "test": team_test_vals, "tp": team_tp_vals}, ensure_ascii=False)
    iter_bar_js = json.dumps(
        {
            "teams": iter_chart_teams,
            "prev": iter_prev_vals,
            "last": iter_last_vals,
            "prevLab": str(prev_s or ""),
            "lastLab": str(last_s or ""),
            "gridBottom": min(140, 44 + len(iter_chart_teams) * 2),
        },
        ensure_ascii=False,
    )
    qc_charts_js = json.dumps({"scatter": scatter_pts, "barNames": qc_bar_names, "barVals": qc_bar_vals}, ensure_ascii=False)
    glossary_html = _glossary_html()

    analysis_m = ""
    if len(months) >= 2:
        hi_m = max(months, key=lambda m: _pct(g_m[m]["test"], g_m[m]["five"]))
        analysis_m = (
            f"分月看，<b>{html_module.escape(hi_m)}</b> 全局<strong>测试工时占比</strong>最高（{_pct(g_m[hi_m]['test'], g_m[hi_m]['five'])}%），"
            "测试在端到端估分中嵌入最深；宜结合该月发布窗口、缺陷与返工做专项复盘（占比在质量可控前提下倾向压低）。"
        )

    analysis_i = ""
    if len(iter_keys) >= 2:
        hi_s = max(iter_keys, key=lambda s: _pct(g_i[s]["test"], g_i[s]["five"]))
        analysis_i = (
            f"分迭代看，<b>{html_module.escape(hi_s)}</b> 全局测试占比最高（{_pct(g_i[hi_s]['test'], g_i[hi_s]['five'])}%），"
            "建议与需求类型、估分与排期结构对照，识别可左移或可拆批环节。"
        )

    closing = _closing_text(global_tp, global_rt_w, global_rt_med, months, iter_keys)

    core = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Gate-RDJ · QC 测试占比与 R/T（总分总）</title>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
  <style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f1f5f9;color:#1e293b;line-height:1.6}}
    .container{{max-width:1400px;margin:0 auto;padding:20px 20px 48px}}
    h1{{text-align:center;color:#0c4a6e;margin-bottom:8px;font-size:24px;font-weight:800}}
    .subtitle{{text-align:center;color:#64748b;font-size:13px;margin:0 0 20px}}
    .toc{{font-size:13px;color:#475569;margin:0 0 18px;padding:14px 16px;background:linear-gradient(135deg,#f8fafc,#f1f5f9);border-radius:14px;border:1px solid #e2e8f0;box-shadow:0 2px 8px rgba(0,0,0,0.06)}}
    .lead{{color:#475569;font-size:13px;line-height:1.75}}
    .section{{background:#fff;padding:16px;border-radius:12px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,0.08)}}
    .section h2{{font-size:15px;font-weight:700;color:#0c4a6e;margin:0 0 12px;padding-bottom:8px;border-bottom:2px solid #e2e8f0}}
    .section.closing h2{{color:#0c4a6e}}
    .section-title{{font-size:15px;font-weight:700;color:#0c4a6e;margin-bottom:12px;padding-bottom:8px;border-bottom:2px solid #e2e8f0}}
    .summary-cards{{display:grid;grid-template-columns:repeat(9,1fr);gap:10px;margin-bottom:20px}}
    @media(max-width:1200px){{.summary-cards{{grid-template-columns:repeat(3,1fr)}}}}
    @media(max-width:600px){{.summary-cards{{grid-template-columns:repeat(2,1fr)}}}}
    .card{{background:#fff;padding:14px 10px;border-radius:10px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.08);border:1px solid #e2e8f0;min-width:0}}
    .card h3{{font-size:11px;color:#64748b;margin-bottom:4px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
    .card .value{{font-size:20px;font-weight:700;color:#0c4a6e}}
    .card .value.test{{color:#0ea5e9}}
    .card .sub{{font-size:11px;color:#94a3b8;margin-top:4px}}
    .conclusion-box{{background:#f0fdf4;border:1px solid #86efac;border-radius:10px;padding:14px;margin-top:12px}}
    .conclusion-title{{font-size:14px;font-weight:700;color:#166534;margin-bottom:8px}}
    .brief-p{{font-size:13px;color:#334155;line-height:1.78;margin:0}}
    .brief-ul{{margin:8px 0 0;padding-left:1.1rem;font-size:13px;color:#334155;line-height:1.75}}
    .brief-ul li{{margin:6px 0}}
    .grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:14px}}
    @media(max-width:900px){{.grid-2{{grid-template-columns:1fr}}}}
    .panel-blue{{background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;padding:14px}}
    .panel-amber{{background:#fffbeb;border:1px solid #fde68a;border-radius:10px;padding:14px}}
    .panel-title{{font-size:14px;font-weight:700;color:#0c4a6e;margin-bottom:8px}}
    .chart{{width:100%;height:420px;margin-top:10px}}
    .chart.compact{{height:360px}}
    .chart-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:10px}}
    @media(max-width:960px){{.chart-grid{{grid-template-columns:1fr}}}}
    .table-wrap{{overflow:auto;margin-top:12px}}
    table{{width:100%;border-collapse:collapse;font-size:12px}}
    th,td{{padding:8px 10px;text-align:center;border-bottom:1px solid #e2e8f0}}
    th:first-child,td:first-child{{text-align:left}}
    th{{background:#f8fafc;font-weight:600;color:#475569}}
    .dept tbody tr.qc-summary-row:hover{{background:#f8fafc}}
    .qc-name-cell{{min-width:120px}}
    button.qc-name-toggle{{background:none;border:none;padding:0;margin:0;font:inherit;cursor:pointer;color:#0369a1;font-weight:600;text-decoration:underline;text-align:left}}
    button.qc-name-toggle:hover{{color:#0c4a6e}}
    button.qc-name-toggle:focus-visible{{outline:2px solid #38bdf8;outline-offset:2px;border-radius:2px}}
    tr.qc-demand-expand-row td.qc-demand-expand-cell{{padding:0 10px 12px;background:#f8fafc;border-bottom:1px solid #e2e8f0;vertical-align:top}}
    .qc-demand-drawer{{padding:10px 12px 12px;border:1px solid #e2e8f0;border-radius:8px;background:#fff;margin:0 2px 2px;box-shadow:0 1px 2px rgba(0,0,0,0.04)}}
    tr.qc-summary-row:has(+ tr.qc-demand-expand-row:not([hidden])) td{{border-bottom:none}}
    tr.qc-summary-row:has(+ tr.qc-demand-expand-row:not([hidden])) .qc-name-toggle{{color:#0c4a6e}}
    .qc-demand-table-wrap{{overflow:auto;max-height:min(360px,55vh)}}
    table.qc-demand-mini{{width:100%;font-size:11px;border-collapse:collapse;margin:0}}
    table.qc-demand-mini th,table.qc-demand-mini td{{padding:6px 8px;border-bottom:1px solid #e2e8f0;text-align:center}}
    table.qc-demand-mini th:first-child,table.qc-demand-mini td:first-child{{text-align:left}}
    table.qc-demand-mini th:nth-child(2),table.qc-demand-mini td:nth-child(2){{text-align:left}}
    table.qc-demand-mini th:nth-child(6),table.qc-demand-mini td:nth-child(6){{text-align:left}}
    table.qc-demand-mini th:nth-child(7),table.qc-demand-mini td:nth-child(7){{text-align:left}}
    table.qc-demand-mini th{{background:#f1f5f9;color:#475569;font-weight:600}}
    table.qc-demand-mini tr:last-child td{{border-bottom:none}}
    .tag{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:6px;background:#e0f2fe;color:#0369a1;margin-right:6px}}
    .dept{{margin-top:18px;padding-top:14px;border-top:1px dashed #cbd5e1}}
    .dept h3{{margin:0 0 8px;font-size:15px;color:#0c4a6e}}
    .subh{{font-weight:400;color:#64748b;font-size:12px}}
    .sline{{font-size:12px;color:#334155;line-height:1.55;margin:2px 0}}
    .note{{font-size:11px;color:#64748b;margin-top:8px;padding:8px;background:#f8fafc;border-radius:6px}}
    .muted{{color:#94a3b8;font-size:12px}}
    ul.glist{{margin:0;padding-left:1.15rem;color:#334155;font-size:13px;line-height:1.75}}
    ul.glist li{{margin:8px 0}}
    .section.glossary h2{{color:#0f766e}}
    .table-wrap.team-pivot-wrap{{overflow:auto;margin-top:4px;max-width:100%;border:1px solid #e2e8f0;border-radius:10px;background:#fff}}
    table.team-tp-pivot{{width:max-content;min-width:100%;font-size:11px;border-collapse:separate;border-spacing:0}}
    table.team-tp-pivot th,table.team-tp-pivot td{{padding:6px 10px;text-align:center;border-bottom:1px solid #e8eef4;white-space:nowrap}}
    table.team-tp-pivot thead th{{background:#f1f5f9;font-weight:600;color:#475569;position:sticky;top:0;z-index:3}}
    table.team-tp-pivot th.sticky-col,table.team-tp-pivot td:first-child{{text-align:left;position:sticky;left:0;z-index:2;background:#fff;box-shadow:4px 0 8px -4px rgba(15,23,42,0.12)}}
    table.team-tp-pivot thead th.sticky-col{{z-index:4;background:#f1f5f9}}
    table.team-tp-pivot .tp-global-row td:first-child{{background:#eff6ff;font-weight:700}}
    table.team-tp-pivot .tp-global-row td:not(:first-child){{background:#f8fafc}}
  </style>
</head>
<body>
  <div class="container">
    <h1>QC 测试占比与 R/T 环比（总分总）</h1>
    <p class="subtitle">{html_module.escape(label_time)} · 迭代 <code>{html_module.escape(label_iter)}</code></p>
    <p class="lead"><span class="tag">总</span>先读结论与结构；<span class="tag">分</span>看分月、分迭代事实与环比，再拆团队与个人；<span class="tag">总</span>末段收束行动。</p>
    {exec_html}
    <div class="toc"><b>结构：</b>（一）时间维 · 图表 + 环比 → （二）需求分类（互斥桶 + <strong>价值类型</strong> + <strong>是否紧急</strong>）→ （三）迭代维 · 图表 + 环比 → （四）团队趋势（含<strong>各团队测占%分月/分迭代</strong>折线） → （五）人员按部门 + R/T 对标（<strong>点击 QC 姓名</strong>展开关联需求表） → （六）总结 → （七）指标说明。</div>

    <div class="section">
      <h2>（一）分 · 时间维度 — 各月事实与环比</h2>
      <p class="lead">横轴为完成月；左轴为<strong>需求数、测试工时</strong>（QC+测试+预发，与业务线 v4 一致），右轴为<strong>测试工时占比%</strong>（占五阶段；质量可控时倾向越低越好）。环比「相对%」= (本期占比−上期占比)/上期占比；「pt」= 百分点差。</p>
      <div id="c-global-month" class="chart"></div>
      <p class="note">原始月份键：{html_module.escape(" · ".join(months))}</p>
      <div class="table-wrap">
        <table><thead><tr>
          <th>月份</th><th>需求数</th><th>测试工时</th><th>五阶段人天</th><th>测试占比%</th><th>上期占比%</th>
          <th>环比(相对%)</th><th>环比(百分点Δ)</th>
        </tr></thead><tbody>{mom_month_rows}</tbody></table>
      </div>
      <p class="lead" style="margin-top:12px;">{analysis_m}</p>
    </div>
    {category_section_html}

    <div class="section">
      <h2>（三）分 · 迭代维度 — 各 SP 事实与环比</h2>
      <p class="lead">横轴为迭代标签（如 2026-SP1 … SP7）；指标口径与时间维一致。</p>
      <div id="c-global-iter" class="chart"></div>
      <div class="table-wrap">
        <table><thead><tr>
          <th>迭代</th><th>需求数</th><th>测试工时</th><th>五阶段人天</th><th>测试占比%</th><th>上期占比%</th>
          <th>环比(相对%)</th><th>环比(百分点Δ)</th>
        </tr></thead><tbody>{mom_iter_rows}</tbody></table>
      </div>
      <p class="lead" style="margin-top:12px;">{analysis_i}</p>
    </div>

    <div class="section">
      <h2>（四）分 · 团队对比与分月/分迭代趋势</h2>
      <p class="lead">以下为<strong>全部业务线（团队）</strong>，按<strong>全期测试工时</strong>降序排列；环比两列：相对% 与 百分点差。下方折线为<strong>各团队测试工时占五阶段%</strong>：左为<strong>完成月</strong>、右为<strong>所属迭代</strong>（与第三节同一迭代轴）；均为「测试工时÷五阶段人天」，含<strong>【全局】</strong>虚线对标；折线节点旁标注<strong>占比数值</strong>，下同<strong>数据透视表</strong>可对读。</p>
      <div class="chart-grid">
        <div id="c-team-bar-test" class="chart compact" style="height:{team_h_bar_px}px;min-height:320px"></div>
        <div id="c-team-bar-tp" class="chart compact" style="height:{team_h_bar_px}px;min-height:320px"></div>
      </div>
      <div class="table-wrap">
        <table><thead><tr>
          <th>团队</th><th>需求</th><th>测试工时</th><th>测试占比%</th><th>R/T</th><th>Bug/需求</th>
          <th>末月占比%</th><th>环比(相对%)</th><th>环比(pt)</th><th>建议</th>
        </tr></thead><tbody>{chr(10).join(team_rows_html)}</tbody></table>
      </div>
      <div class="chart-grid" style="margin-top:14px;">
        <div>
          <h3 style="margin:0 0 8px;font-size:14px;color:#334155;font-weight:700;">各团队测试工时占比 · 分月（%）</h3>
          <div id="c-team-trend" class="chart compact"></div>
        </div>
        <div>
          <h3 style="margin:0 0 8px;font-size:14px;color:#334155;font-weight:700;">各团队测试工时占比 · 分迭代（%）</h3>
          <div id="c-team-trend-iter" class="chart compact"></div>
        </div>
      </div>
      {team_tp_pivot_html}
      <div id="c-iter-compare" class="chart compact" style="margin-top:14px;"></div>
      <p class="lead">最近两期迭代团队对比（与下表一致）。</p>
      <div class="table-wrap">
        <table><thead><tr>
          <th>团队</th><th>最近迭代</th><th>本期测试占比%</th><th>环比(相对%)</th><th>环比(pt)</th>
        </tr></thead><tbody>{chr(10).join(iter_mom_rows)}</tbody></table>
      </div>
    </div>

    <div class="section">
      <h2>（五）分 · 人员按部门 — R/T 与部门对标</h2>
      <p class="lead">部门 = 业务线，与 <a href="https://report.dev.halftrust.xyz/results/department_stats.html" target="_blank" rel="noopener noreferrer">department_stats</a> 页「大类名称-新分组」及 QC 白名单一致（脚本优先拉取该页，失败时可本地放 <code>department_stats.html</code> 或设 <code>DEPARTMENT_STATS_HTML</code>）。<strong>R/T</strong> = 修正研发工时÷测试工时（与附录一致）。<strong>部门 R/T 均值</strong> = 部门内各人 R/T 的算术平均（仅统计测试工时 &gt; 0.05 人天的成员）。<strong>相对部门 R/T%</strong> = (本人−部门均值)/部门均值；<strong>正值</strong>表示相对部门更偏「重研发/单位测试摊到的修正研发更高」，需结合缺陷与发布质量解读。</p>
      <p class="lead">关联需求：<strong>点击 QC 姓名</strong>在<strong>下一整行</strong>展开明细表（与主表<strong>同宽</strong>，子表表头横跨全表；完成月、分摊测试、占比、R/T、业务线、迭代；需求名可点进系统）。图表仅作分布与排序参考，无弹窗。</p>
      <div class="chart-grid">
        <div id="c-qc-scatter" class="chart compact"></div>
        <div id="c-qc-bar-test" class="chart compact"></div>
      </div>
      <p class="note">散点横轴为「相对部门 R/T%」（正=相对部门更偏重研发），纵轴为测试占比%；右上多为「高 R/T × 高测试占比」压力象限，宜结合缺陷与估分复核。</p>
      {"".join(dept_blocks)}
    </div>

    {closing}
    {glossary_html}
  </div>
  <script>
    var monthsX = __MONTHS__;
    var series = __SERIES__;
    var teamTpIter = __TEAM_TP_ITER__;
    var teamBar = __TEAM_BAR__;
    var iterCmp = __ITER_BAR__;
    var qcCharts = __QC_CHARTS__;
    var gMonth = __GLOBAL_MONTH__;
    var gIter = __GLOBAL_ITER__;
    var catStack = __CAT_STACK__;
    var vtStackM = __VT_STACK_MONTH__;
    var vtStackI = __VT_STACK_ITER__;
    var urgStackM = __URGENT_STACK_MONTH__;
    var urgStackI = __URGENT_STACK_ITER__;
    var charts = [];
    function go() {{
      if (typeof echarts === 'undefined') {{ setTimeout(go, 60); return; }}
      function pushChart(dom, opt) {{
        var el = document.getElementById(dom);
        if (!el) return;
        var c = echarts.init(el);
        c.setOption(opt);
        charts.push(c);
      }}
      pushChart('c-global-month', {{
        title: {{ text: '时间维 · 全局：各月需求/测试工时与测试占比', left: 'center', textStyle: {{ fontSize: 15 }} }},
        tooltip: {{ trigger: 'axis' }},
        legend: {{ bottom: 0 }},
        grid: {{ left: 52, right: 52, top: 48, bottom: 68 }},
        xAxis: {{ type: 'category', data: gMonth.labels }},
        yAxis: [
          {{ type: 'value', name: '数量/工时', position: 'left' }},
          {{ type: 'value', name: '占比%', position: 'right', axisLabel: {{ formatter: '{{value}}%' }}, splitLine: {{ show: false }} }}
        ],
        series: [
          {{ name: '完成需求数', type: 'bar', data: gMonth.demands, yAxisIndex: 0, itemStyle: {{ color: '#64748b' }} }},
          {{ name: '测试工时', type: 'bar', data: gMonth.tests, yAxisIndex: 0, itemStyle: {{ color: '#0284c7' }} }},
          {{ name: '测试占比%', type: 'line', yAxisIndex: 1, smooth: true, data: gMonth.tps, itemStyle: {{ color: '#c026d3' }}, lineStyle: {{ width: 3 }} }}
        ]
      }});
      if (catStack && catStack.labels && catStack.labels.length && catStack.series && catStack.series.length) {{
        pushChart('c-cat-month-stack', {{
          title: {{ text: '时间维 · 分月测试工时结构（按需求分类）', left: 'center', textStyle: {{ fontSize: 14 }} }},
          tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
          legend: {{ type: 'scroll', bottom: 0, textStyle: {{ fontSize: 10 }} }},
          grid: {{ left: 48, right: 24, top: 44, bottom: 62 }},
          xAxis: {{ type: 'category', data: catStack.labels, axisLabel: {{ fontSize: 10 }} }},
          yAxis: {{ type: 'value', name: '测试工时' }},
          series: catStack.series
        }});
      }}
      if (vtStackM && vtStackM.labels && vtStackM.labels.length && vtStackM.series && vtStackM.series.length) {{
        pushChart('c-vt-month-stack', {{
          title: {{ text: '时间维 · 分月测试工时（按价值类型）', left: 'center', textStyle: {{ fontSize: 14 }} }},
          tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
          legend: {{ type: 'scroll', bottom: 0, textStyle: {{ fontSize: 9 }} }},
          grid: {{ left: 46, right: 22, top: 44, bottom: 64 }},
          xAxis: {{ type: 'category', data: vtStackM.labels, axisLabel: {{ fontSize: 10 }} }},
          yAxis: {{ type: 'value', name: '测试工时' }},
          series: vtStackM.series
        }});
      }}
      if (vtStackI && vtStackI.labels && vtStackI.labels.length && vtStackI.series && vtStackI.series.length) {{
        pushChart('c-vt-iter-stack', {{
          title: {{ text: '迭代维 · 各 SP 测试工时（按价值类型）', left: 'center', textStyle: {{ fontSize: 14 }} }},
          tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
          legend: {{ type: 'scroll', bottom: 0, textStyle: {{ fontSize: 9 }} }},
          grid: {{ left: 44, right: 20, top: 44, bottom: 66 }},
          xAxis: {{ type: 'category', data: vtStackI.labels, axisLabel: {{ rotate: 22, fontSize: 9 }} }},
          yAxis: {{ type: 'value', name: '测试工时' }},
          series: vtStackI.series
        }});
      }}
      if (urgStackM && urgStackM.labels && urgStackM.labels.length && urgStackM.series && urgStackM.series.length) {{
        pushChart('c-urgent-month-stack', {{
          title: {{ text: '时间维 · 分月测试工时（紧急 vs 非紧急）', left: 'center', textStyle: {{ fontSize: 14 }} }},
          tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
          legend: {{ bottom: 8 }},
          grid: {{ left: 48, right: 24, top: 44, bottom: 52 }},
          xAxis: {{ type: 'category', data: urgStackM.labels, axisLabel: {{ fontSize: 10 }} }},
          yAxis: {{ type: 'value', name: '测试工时' }},
          series: urgStackM.series
        }});
      }}
      if (urgStackI && urgStackI.labels && urgStackI.labels.length && urgStackI.series && urgStackI.series.length) {{
        pushChart('c-urgent-iter-stack', {{
          title: {{ text: '迭代维 · 各 SP 测试工时（紧急 vs 非紧急）', left: 'center', textStyle: {{ fontSize: 14 }} }},
          tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
          legend: {{ bottom: 8 }},
          grid: {{ left: 44, right: 20, top: 44, bottom: 54 }},
          xAxis: {{ type: 'category', data: urgStackI.labels, axisLabel: {{ rotate: 22, fontSize: 9 }} }},
          yAxis: {{ type: 'value', name: '测试工时' }},
          series: urgStackI.series
        }});
      }}
      pushChart('c-global-iter', {{
        title: {{ text: '迭代维 · 全局：各 SP 需求/测试工时与测试占比', left: 'center', textStyle: {{ fontSize: 15 }} }},
        tooltip: {{ trigger: 'axis' }},
        legend: {{ bottom: 0 }},
        grid: {{ left: 52, right: 52, top: 48, bottom: 68 }},
        xAxis: {{ type: 'category', data: gIter.labels, axisLabel: {{ fontSize: 10 }} }},
        yAxis: [
          {{ type: 'value', name: '数量/工时', position: 'left' }},
          {{ type: 'value', name: '占比%', position: 'right', axisLabel: {{ formatter: '{{value}}%' }}, splitLine: {{ show: false }} }}
        ],
        series: [
          {{ name: '完成需求数', type: 'bar', data: gIter.demands, yAxisIndex: 0, itemStyle: {{ color: '#64748b' }} }},
          {{ name: '测试工时', type: 'bar', data: gIter.tests, yAxisIndex: 0, itemStyle: {{ color: '#059669' }} }},
          {{ name: '测试占比%', type: 'line', yAxisIndex: 1, smooth: true, data: gIter.tps, itemStyle: {{ color: '#d97706' }}, lineStyle: {{ width: 3 }} }}
        ]
      }});
      pushChart('c-team-trend', {{
        title: {{ text: '团队测试占比 · 分月（%）', left: 'center', textStyle: {{ fontSize: 14 }} }},
        tooltip: {{ trigger: 'axis', valueFormatter: function(v) {{ return v != null ? Number(v).toFixed(1) + '%' : ''; }} }},
        legend: {{ type: 'scroll', bottom: 0, textStyle: {{ fontSize: 10 }} }},
        grid: {{ left: 48, right: 28, top: 52, bottom: 70 }},
        xAxis: {{ type: 'category', data: monthsX }},
        yAxis: {{ type: 'value', name: '%', max: 100, axisLabel: {{ formatter: '{{value}}%' }} }},
        series: series
      }});
      if (teamTpIter && teamTpIter.labels && teamTpIter.labels.length && teamTpIter.series && teamTpIter.series.length) {{
        pushChart('c-team-trend-iter', {{
          title: {{ text: '团队测试占比 · 分迭代（%）', left: 'center', textStyle: {{ fontSize: 14 }} }},
          tooltip: {{ trigger: 'axis', valueFormatter: function(v) {{ return v != null ? Number(v).toFixed(1) + '%' : ''; }} }},
          legend: {{ type: 'scroll', bottom: 0, textStyle: {{ fontSize: 10 }} }},
          grid: {{ left: 44, right: 24, top: 52, bottom: 72 }},
          xAxis: {{ type: 'category', data: teamTpIter.labels, axisLabel: {{ rotate: 26, fontSize: 9 }} }},
          yAxis: {{ type: 'value', name: '%', max: 100, axisLabel: {{ formatter: '{{value}}%' }} }},
          series: teamTpIter.series
        }});
      }}
      pushChart('c-team-bar-test', {{
        title: {{ text: '团队测试工时（全部业务线）', left: 'center', textStyle: {{ fontSize: 13 }} }},
        tooltip: {{ trigger: 'axis' }},
        grid: {{ left: 140, right: 44, top: 32, bottom: 24 }},
        xAxis: {{ type: 'value', name: '工时' }},
        yAxis: {{ type: 'category', data: teamBar.names, inverse: true, axisLabel: {{ fontSize: 9, width: 200, overflow: 'truncate' }} }},
        series: [{{ type: 'bar', name: '测试工时', data: teamBar.test, label: {{ show: true, position: 'right', fontSize: 9, formatter: function(p) {{ return p.value != null ? p.value : ''; }} }}, itemStyle: {{ color: '#0284c7', borderRadius: [0,4,4,0] }} }}]
      }});
      pushChart('c-team-bar-tp', {{
        title: {{ text: '团队测试占比·全期', left: 'center', textStyle: {{ fontSize: 13 }} }},
        grid: {{ left: 140, right: 44, top: 32, bottom: 24 }},
        xAxis: {{ type: 'value', max: 100, name: '%' }},
        yAxis: {{ type: 'category', data: teamBar.names, inverse: true, axisLabel: {{ fontSize: 9, width: 200, overflow: 'truncate' }} }},
        series: [{{ type: 'bar', data: teamBar.tp, label: {{ show: true, position: 'right', fontSize: 9, formatter: function(p) {{ return p.value != null ? p.value + '%' : ''; }} }}, itemStyle: {{ color: '#7c3aed', borderRadius: [0,4,4,0] }} }}]
      }});
      if (iterCmp.teams && iterCmp.teams.length && iterCmp.prevLab && iterCmp.lastLab) {{
        pushChart('c-iter-compare', {{
          title: {{ text: '迭代两期对比：' + iterCmp.prevLab + ' vs ' + iterCmp.lastLab, left: 'center', textStyle: {{ fontSize: 13 }} }},
          tooltip: {{ trigger: 'axis', valueFormatter: function(v) {{ return v != null ? Number(v).toFixed(2) + '%' : ''; }} }},
          legend: {{ bottom: 0 }},
          grid: {{ left: 100, right: 16, top: 44, bottom: iterCmp.gridBottom != null ? iterCmp.gridBottom : 48 }},
          xAxis: {{ type: 'category', data: iterCmp.teams, axisLabel: {{ rotate: 26, fontSize: 9 }} }},
          yAxis: {{ type: 'value', name: '%', max: 100 }},
          series: [
            {{ name: iterCmp.prevLab, type: 'bar', data: iterCmp.prev, label: {{ show: true, position: 'top', fontSize: 8, formatter: function(p) {{ return p.value != null ? p.value.toFixed(1) + '%' : ''; }} }}, itemStyle: {{ color: '#94a3b8' }} }},
            {{ name: iterCmp.lastLab, type: 'bar', data: iterCmp.last, label: {{ show: true, position: 'top', fontSize: 8, formatter: function(p) {{ return p.value != null ? p.value.toFixed(1) + '%' : ''; }} }}, itemStyle: {{ color: '#059669' }} }}
          ]
        }});
      }}
      pushChart('c-qc-scatter', {{
        title: {{ text: '个人：相对部门 R/T% × 测试占比%', left: 'center', textStyle: {{ fontSize: 13 }} }},
        tooltip: {{
          formatter: function(p) {{
            var d = p.data;
            return '<b>' + d.name + '</b><br/>部门：' + d.dept + '<br/>R/T：' + d.rt + '（部门均值 ' + d.dm + '）<br/>相对部门 R/T：' + d.value[0] + '%（正=相对更重研发）<br/>测试占比：' + d.value[1] + '%<br/>累计测试工时：' + d.testH;
          }}
        }},
        grid: {{ left: 52, right: 20, top: 36, bottom: 32 }},
        xAxis: {{ name: '相对部门R/T(%)', nameLocation: 'middle', nameGap: 26 }},
        yAxis: {{ name: '测试占比%', axisLabel: {{ formatter: '{{value}}%' }} }},
        series: [{{
          type: 'scatter',
          symbolSize: function(d) {{ return d.symbolSize || 14; }},
          itemStyle: {{ opacity: 0.8, color: '#ea580c' }},
          data: qcCharts.scatter.map(function(d) {{
            return {{ name: d.name, value: d.value, rt: d.rt, dept: d.dept, dm: d.dm, testH: d.testH, symbolSize: d.symbolSize }};
          }})
        }}]
      }});
      pushChart('c-qc-bar-test', {{
        title: {{ text: '个人测试工时 TOP', left: 'center', textStyle: {{ fontSize: 13 }} }},
        grid: {{ left: 88, right: 16, top: 32, bottom: 24 }},
        xAxis: {{ type: 'value', name: '工时' }},
        yAxis: {{ type: 'category', data: qcCharts.barNames, inverse: true, axisLabel: {{ fontSize: 9 }} }},
        series: [{{ type: 'bar', name: '测试工时', data: qcCharts.barVals, itemStyle: {{ color: '#c2410c', borderRadius: [0,4,4,0] }} }}]
      }});
      window.addEventListener('resize', function() {{ charts.forEach(function(c) {{ c.resize(); }}); }});
    }}
    go();
    (function setupQcDemandExpand() {{
      document.querySelectorAll('.qc-name-toggle').forEach(function(btn) {{
        btn.addEventListener('click', function() {{
          var id = btn.getAttribute('aria-controls');
          var row = id && document.getElementById(id);
          if (!row) return;
          var show = row.hasAttribute('hidden');
          if (show) {{ row.removeAttribute('hidden'); }} else {{ row.setAttribute('hidden', ''); }}
          btn.setAttribute('aria-expanded', show ? 'true' : 'false');
        }});
      }});
    }})();
  </script>
</body>
</html>"""

    html = (
        core.replace("__MONTHS__", months_js)
        .replace("__SERIES__", trend_js)
        .replace("__TEAM_TP_ITER__", team_tp_iter_js)
        .replace("__TEAM_BAR__", team_bar_js)
        .replace("__ITER_BAR__", iter_bar_js)
        .replace("__QC_CHARTS__", qc_charts_js)
        .replace("__GLOBAL_MONTH__", global_month_js)
        .replace("__GLOBAL_ITER__", global_iter_js)
        .replace("__CAT_STACK__", cat_stack_js)
        .replace("__VT_STACK_MONTH__", vt_stack_month_js)
        .replace("__VT_STACK_ITER__", vt_stack_iter_js)
        .replace("__URGENT_STACK_MONTH__", urg_stack_month_js)
        .replace("__URGENT_STACK_ITER__", urg_stack_iter_js)
    )
    return html


def _pick_bundle(pairs: List[Tuple[str, str, Optional[str]]], token: str) -> Optional[Tuple[str, str]]:
    for csv_path, prefix, forced in pairs:
        if token in os.path.basename(csv_path) or token in prefix:
            return csv_path, prefix
    return None


def main() -> int:
    pairs = ggen.discover_dimension_csvs()
    time_bundle = _pick_bundle(pairs, "时间")
    iter_bundle = _pick_bundle(pairs, "迭代")
    if not time_bundle or not iter_bundle:
        print("需要时间与迭代两份 CSV", file=sys.stderr)
        return 1

    qc_map = ggen._load_qc_group_mapping()
    rows_t_raw = load_rows(time_bundle[0])
    rows_i_raw = load_rows(iter_bundle[0])
    rows_t = ggen._apply_qc_grouping(rows_t_raw, qc_map)
    rows_i = ggen._apply_qc_grouping(rows_i_raw, qc_map)

    data_t, _, label_time, _ = build_data_payload(rows_t, period_axis="month")
    months = list(data_t.get("months") or [])
    data_i, _, label_iter, _ = build_data_payload(rows_i, period_axis="iteration")
    iter_keys = list(data_i.get("months") or [])

    team_m = aggregate_team_period(rows_t, months, _month_period_key)
    team_i = aggregate_team_period(rows_i, iter_keys, _sp_label)
    qc_m_raw, qc_team = aggregate_qc_period(rows_t, months, _month_period_key)
    qc_demand_details = build_qc_demand_details(rows_t, months)

    html = build_html_p9(
        label_time=str(label_time),
        label_iter=str(label_iter),
        months=months,
        iter_keys=iter_keys,
        rows_t=rows_t,
        rows_i=rows_i,
        team_m=team_m,
        team_i=team_i,
        qc_m=qc_m_raw,
        qc_team=qc_team,
        qc_demand_details=qc_demand_details,
    )
    html = ggen.inject_echarts_fallback(html)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print("Wrote", OUT_HTML)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
