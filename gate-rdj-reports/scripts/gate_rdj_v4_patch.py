# -*- coding: utf-8 -*-
"""从 Gate-RDJ-12-v4 模板生成与 CSV 数据对齐的静态片段（主 Tab、汇总卡、分月 Tab、尾部 monthlyTestPct 等）。"""
from __future__ import annotations

import html as html_module
import json
import re
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple

from gate_rdj_metrics import (
    _biz_line,
    corrected_rd,
    effort_fields,
    five_phase_total,
    iqr_filter,
    _cycle_days,
    _month_key,
    _month_period_key,
    _parse_dt,
    _pf,
    _primary_qc,
    _sp_label,
)

_COLORS = ["#dc2626", "#2563eb", "#059669", "#db2777", "#7c3aed", "#d97706", "#0891b2", "#475569"]


def _global_month_row(
    rows: List[Dict[str, str]],
    m: str,
    period_key: Optional[Callable[[Dict[str, str]], Optional[str]]] = None,
) -> Dict[str, Any]:
    if period_key is None:
        period_key = _month_period_key
    sub = [r for r in rows if period_key(r) == m]
    n = len(sub)
    if not n:
        return {
            "month": m,
            "total_effort": 0.0,
            "test_effort": 0.0,
            "qc_effort": 0.0,
            "test_node": 0.0,
            "preflight": 0.0,
            "design_effort": 0.0,
            "dev_effort": 0.0,
            "pct": 0.0,
            "clean_pct": 0.0,
            "demand_count": 0,
            "clean_count": 0,
            "outlier_count": 0,
        }
    cys = []
    for r in sub:
        cy = _cycle_days(_parse_dt(r.get("创建时间")), _parse_dt(r.get("完成日期")))
        if cy is not None and cy > 0:
            cys.append(float(cy))
    kept, _inv, out = iqr_filter(cys)
    clean_rows = [
        r
        for r in sub
        if (lambda c: c is not None and c > 0 and c in kept)(
            _cycle_days(_parse_dt(r.get("创建时间")), _parse_dt(r.get("完成日期")))
        )
    ]
    if len(clean_rows) < max(3, n // 5):
        clean_rows = sub
        out = 0
    qc = te = pr = tt = five = dsum = rds = 0.0
    for r in sub:
        d, rd, qc0, _, te0, pr0, ttv = effort_fields(r)
        qc += qc0
        te += te0
        pr += pr0
        tt += ttv
        five += five_phase_total(r)
        dsum += d
        rds += rd
    qc_c = te_c = pr_c = tt_c = five_c = 0.0
    for r in clean_rows:
        d, rd, qc0, _, te0, pr0, ttv = effort_fields(r)
        qc_c += qc0
        te_c += te0
        pr_c += pr0
        tt_c += ttv
        five_c += five_phase_total(r)
    pct = round(tt / (five + 1e-6) * 100, 1) if five else 0.0
    clean_pct = round(tt_c / (five_c + 1e-6) * 100, 1) if five_c else 0.0
    return {
        "month": m,
        "total_effort": round(five, 1),
        "test_effort": round(tt, 1),
        "qc_effort": round(qc, 1),
        "test_node": round(te, 1),
        "preflight": round(pr, 1),
        "design_effort": round(dsum, 1),
        "dev_effort": round(rds, 1),
        "pct": pct,
        "clean_pct": clean_pct,
        "demand_count": n,
        "clean_count": len(clean_rows),
        "outlier_count": int(out),
    }


def build_global_monthly_test_pct(
    rows: List[Dict[str, str]],
    months: List[str],
    period_key: Optional[Callable[[Dict[str, str]], Optional[str]]] = None,
) -> List[Dict[str, Any]]:
    return [_global_month_row(rows, m, period_key) for m in months]


def build_monthly_test_pct_by_biz(
    rows: List[Dict[str, str]],
    months: List[str],
    period_key: Optional[Callable[[Dict[str, str]], Optional[str]]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    biz_names = sorted({_biz_line(r) for r in rows})
    out: Dict[str, List[Dict[str, Any]]] = {}
    for b in biz_names:
        sub_all = [r for r in rows if _biz_line(r) == b]
        if not sub_all:
            continue
        out[b] = [_global_month_row(sub_all, m, period_key) for m in months]
    return out


def _fmt_month_panel_id(m: str) -> str:
    return "global-month-" + m.replace("-", "")


def _qc_members(raw: str) -> List[str]:
    if not raw:
        return []
    out: List[str] = []
    for x in str(raw).split("|"):
        name = x.strip()
        if not name:
            continue
        # 仅保留以 QC/qc 结尾的标识（如 cheney-QC）
        if re.search(r"(?i)qc$", name):
            out.append(name)
    return out


def _qc_row_share(r: Dict[str, str], qc: str) -> float:
    """同一需求多 QC 时按人头均分（与 P9 / QC 台账一致），避免个人 R/T 与团队汇总脱节。"""
    members = _qc_members(r.get("QC") or "")
    if qc not in members or not members:
        return 0.0
    return 1.0 / len(members)


def _aggregate_qc_person_stats(
    team_rows: List[Dict[str, str]], qc: str
) -> Tuple[float, float, float, float, float, List[Dict[str, str]]]:
    """返回 (demands_w, five, test, rd_corr, cycle_w_sum, linked_rows)。"""
    demands_w = five = test = rd_corr = cycle_w = 0.0
    linked: List[Dict[str, str]] = []
    for r in team_rows:
        w = _qc_row_share(r, qc)
        if w <= 0:
            continue
        linked.append(r)
        demands_w += w
        five += five_phase_total(r) * w
        test += effort_fields(r)[6] * w
        rd_corr += corrected_rd(r) * w
        cy = _cycle_days(_parse_dt(r.get("创建时间")), _parse_dt(r.get("完成日期")))
        if cy is not None:
            cycle_w += float(cy) * w
    return demands_w, five, test, rd_corr, cycle_w, linked


def _replace_panel_by_id(html: str, panel_id: str, new_inner: str) -> str:
    marker = f'<div class="biz-content" id="{panel_id}">'
    s0 = html.find(marker)
    if s0 < 0:
        return html
    start = s0 + len(marker)
    s1 = html.find('\n<div class="biz-content"', start)
    if s1 < 0:
        s1 = html.find("</body>", start)
    if s1 < 0:
        return html
    return html[:start] + "\n" + new_inner + "\n" + html[s1:]


def build_qc_summary_panel_html(
    rows: List[Dict[str, str]],
    months: List[str],
    period_key: Optional[Callable[[Dict[str, str]], Optional[str]]] = None,
) -> str:
    if period_key is None:
        period_key = _month_period_key
    teams: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"rows": [], "qcs": set(), "demands": 0, "five": 0.0, "test": 0.0, "rd_corr": 0.0, "cycles": []}
    )
    for r in rows:
        team = _biz_line(r)
        obj = teams[team]
        obj["rows"].append(r)
        obj["demands"] += 1
        obj["five"] += five_phase_total(r)
        obj["test"] += effort_fields(r)[6]
        obj["rd_corr"] += corrected_rd(r)
        for q in _qc_members(r.get("QC") or ""):
            obj["qcs"].add(q)
        cy = _cycle_days(_parse_dt(r.get("创建时间")), _parse_dt(r.get("完成日期")))
        if cy is not None:
            obj["cycles"].append(float(cy))
    sorted_teams = sorted(teams.items(), key=lambda kv: (-kv[1]["demands"], kv[0]))
    summary_rows = []
    for i, (team, o) in enumerate(sorted_teams, 1):
        d = int(o["demands"])
        test = float(o["test"])
        rd_corr = float(o["rd_corr"])
        rt = round(rd_corr / (test + 1e-6), 2) if test else 0.0
        avg_cycle = round(sum(o["cycles"]) / len(o["cycles"]), 2) if o["cycles"] else 0.0
        summary_rows.append(
            "<tr>"
            f"<td>{i}</td>"
            f'<td style="text-align:left;font-weight:600;">{html_module.escape(team)}</td>'
            f"<td>{len(o['qcs'])}</td>"
            f"<td>{d}</td>"
            f"<td>{round(o['five'], 1)}</td>"
            f'<td class="test-highlight">{round(test, 1)}</td>'
            f'<td class="test-highlight">{round(test / max(d, 1), 2)}</td>'
            f"<td>{round(rd_corr, 1)}</td>"
            f"<td>{rt}</td>"
            f"<td>{avg_cycle}天</td>"
            "</tr>"
        )
    detail_blocks = []
    for team, o in sorted_teams:
        qc_rows = []
        for qc in sorted(o["qcs"]):
            demands_w, five, test, rd_corr, cycle_w, sub = _aggregate_qc_person_stats(o["rows"], qc)
            if demands_w <= 0:
                continue
            d = demands_w
            rt = round(rd_corr / (test + 1e-6), 2) if test else 0.0
            avg_cycle = round(cycle_w / demands_w, 2) if demands_w else 0.0
            demand_items = []
            for rr in sub:
                nm = (rr.get("名称") or "").strip() or "未命名需求"
                lk = (rr.get("需求链接") or "").strip()
                if lk:
                    demand_items.append(
                        f'<li style="margin:2px 0;"><a href="{html_module.escape(lk, quote=True)}" target="_blank" style="color:#0369a1;text-decoration:none;">{html_module.escape(nm)}</a></li>'
                    )
                else:
                    demand_items.append(f"<li style=\"margin:2px 0;\">{html_module.escape(nm)}</li>")
            d_label = f"{d:.1f}" if abs(d - round(d)) > 0.05 else str(int(round(d)))
            qc_cell = (
                f'<details><summary style="cursor:pointer;color:#0c4a6e;">{html_module.escape(qc)}（{d_label}）</summary>'
                f'<ul style="margin:6px 0 0 16px;padding:0;max-height:180px;overflow:auto;">{"".join(demand_items)}</ul>'
                "</details>"
            )
            qc_rows.append(
                "<tr>"
                f'<td style="text-align:left;">{qc_cell}</td>'
                f"<td>{d_label}</td><td>{round(five, 1)}</td>"
                f'<td class="test-highlight">{round(test, 1)}</td>'
                f'<td class="test-highlight">{round(test / max(demands_w, 1e-6), 2)}</td>'
                f"<td>{round(rd_corr, 1)}</td><td>{rt}</td><td>{avg_cycle}天</td>"
                "</tr>"
            )
        if not qc_rows:
            continue
        detail_blocks.append(
            f"""<details style="margin-bottom:10px;border:1px solid #e2e8f0;border-radius:8px;padding:8px 12px;background:#fff;">
<summary style="cursor:pointer;font-weight:600;color:#0c4a6e;">{html_module.escape(team)}（QC人数 {len(o["qcs"])}，需求 {o["demands"]}）</summary>
<div class="table-wrap" style="margin-top:10px;">
<table>
<thead><tr><th>QC</th><th>需求数</th><th>总工时</th><th class="test-highlight">测试工时</th><th class="test-highlight">均测试</th><th>研发工时</th><th>R/T</th><th>平均工期</th></tr></thead>
<tbody>
{''.join(qc_rows)}
</tbody>
</table>
</div>
</details>"""
        )
    months_js = json.dumps(months, ensure_ascii=False)
    return f"""
<div class="section" style="background:linear-gradient(135deg,#f8fafc,#f1f5f9);border:1px solid #e2e8f0;border-radius:12px;">
  <div style="padding:12px 16px 0 16px;">
    <div style="font-size:15px;font-weight:700;color:#334155;">📈 团队测试工时占比趋势</div>
    <div style="font-size:11px;color:#64748b;margin-top:4px;">口径：按新分组统计（QC用例+测试+预发）÷5阶段总工时</div>
  </div>
  <div id="team-monthly-pct-chart" style="width:100%;height:350px;"></div>
</div>
<div class="section">
  <div class="section-title">📊 团队汇总</div>
  <div style="font-size:12px;color:#64748b;margin-bottom:8px;">团队数：<b style="color:#0c4a6e;">{len(sorted_teams)}</b>，统计周期：<b style="color:#0c4a6e;">{html_module.escape(months[0] if months else '-')} ~ {html_module.escape(months[-1] if months else '-')}</b></div>
  <div class="table-wrap">
    <table>
      <thead><tr><th>#</th><th>团队</th><th>QC人数</th><th>需求数</th><th>总工时</th><th class="test-highlight">测试工时</th><th class="test-highlight">均测试</th><th>研发工时</th><th>R/T</th><th>平均工期</th></tr></thead>
      <tbody>{''.join(summary_rows)}</tbody>
    </table>
  </div>
</div>
<div class="section">
  <div class="section-title">📅 按团队分组明细（点击展开）</div>
  <div style="font-size:12px;color:#64748b;margin-bottom:10px;">以下明细按新分组展开，组内展示 QC 个人指标。多人同测需求按 QC 人头均分工时与修正研发（需求数显示加权值，可与团队汇总对齐）。</div>
  {''.join(detail_blocks)}
</div>
<script>window.__teamMonths={months_js};</script>
"""


def build_v4_main_tabs_html(biz_list: List[Dict[str, Any]], html: str) -> str:
    """仅保留模板中已有对应 biz-content 面板的业务线，避免 data-biz 与 id 不一致导致空白。"""
    parts = [
        '<div class="main-tab summary-tab active" data-biz="summary">📊 全局汇总</div>',
        '<div class="main-tab qc-tab" data-biz="qc-summary">👥 QC人员分析</div>',
        '<div class="tab-divider"></div>',
    ]
    for b in biz_list:
        nm = b["name"]
        bid = f'id="biz-{nm}"'
        if bid not in html:
            continue
        parts.append(
            f'<div class="main-tab biz-tab" data-biz="{html_module.escape(nm, quote=True)}">'
            f"{html_module.escape(nm)} ({b['demand_count']})</div>"
        )
    return "\n".join(parts)


def remap_biz_content_panel_ids(html: str, biz_names: List[str]) -> str:
    """
    将模板内既有 biz-* 面板顺序重映射到当前业务组，避免新分组名称与模板旧 id 不一致导致切页空白。
    """
    old_ids = re.findall(r'id="(biz-[^"]+)"', html)
    if not old_ids or not biz_names:
        return html
    uniq_old_ids: List[str] = []
    for oid in old_ids:
        if oid not in uniq_old_ids:
            uniq_old_ids.append(oid)
    # 固定面板不可重映射：否则会导致“全局汇总 / QC人员分析”页签失效
    uniq_old_ids = [x for x in uniq_old_ids if x not in ("biz-summary", "biz-qc-summary")]
    remap_count = min(len(uniq_old_ids), len(biz_names))
    for i in range(remap_count):
        old_id = uniq_old_ids[i]
        old_name = old_id[4:] if old_id.startswith("biz-") else old_id
        new_name = biz_names[i]
        marker = f'<div class="biz-content" id="{old_id}">'
        s0 = html.find(marker)
        if s0 < 0:
            continue
        s1 = html.find('\n<div class="biz-content"', s0 + len(marker))
        if s1 < 0:
            s1 = html.find("</body>", s0 + len(marker))
        if s1 < 0:
            continue
        block = html[s0:s1]
        old_safe = old_name.replace("-", "_")
        new_safe = new_name.replace("-", "_")
        block = block.replace(f'id="{old_id}"', f'id="biz-{new_name}"', 1)
        # 同步修正面板内用于 JS 定位的各类 id / data-panel 后缀
        block = block.replace(old_safe, new_safe)
        html = html[:s0] + block + html[s1:]
    return html


def build_v4_summary_cards_html(data: Dict[str, Any], rows: List[Dict[str, str]]) -> str:
    nd = len(rows)
    g_tt = sum(effort_fields(r)[6] for r in rows)
    g_five = sum(five_phase_total(r) for r in rows)
    g_rd = sum(corrected_rd(r) for r in rows)
    g_bugs = sum(_pf(r.get("总 bug 数")) for r in rows)
    cys = [
        float(x)
        for x in (
            _cycle_days(_parse_dt(r.get("创建时间")), _parse_dt(r.get("完成日期")))
            for r in rows
        )
        if x is not None
    ]
    avg_c = sum(cys) / len(cys) if cys else 0.0
    avg_test = round(g_tt / max(nd, 1), 2)
    avg_dev = round(sum(_pf(r.get("研发总估分")) for r in rows) / max(nd, 1), 2)
    rt = round(g_rd / (g_tt + 1e-6), 2) if g_tt else 0.0
    return f"""<div class="summary-cards">
<div class="card"><h3>需求总数</h3><div class="value">{nd}</div></div>
<div class="card"><h3>总工时</h3><div class="value">{round(g_five, 2)}</div><div class="sub">人天</div></div>
<div class="card"><h3>测试工时</h3><div class="value test">{round(g_tt, 2)}</div><div class="sub">人天</div></div>
<div class="card"><h3>均测试工时</h3><div class="value test">{avg_test}</div><div class="sub">人天/需求</div></div>
<div class="card"><h3>研发工时</h3><div class="value">{round(sum(_pf(r.get("研发总估分")) for r in rows), 2)}</div><div class="sub">人天</div></div>
<div class="card"><h3>均开发工时</h3><div class="value">{avg_dev}</div><div class="sub">人天/需求</div></div>
<div class="card"><h3>整体 R/T</h3><div class="value">{rt}</div></div>
<div class="card"><h3>平均工期</h3><div class="value">{round(avg_c, 2)}</div><div class="sub">天</div></div>
<div class="card"><h3>Bug 总数</h3><div class="value">{int(g_bugs)}</div><div class="sub">均{round(g_bugs/max(nd,1),2)}/需求</div></div>
</div>"""


def _replace_tbody_after_anchor(html: str, anchor: str, new_rows_html: str) -> str:
    pos = html.find(anchor)
    if pos < 0:
        return html
    t0 = html.find("<tbody>", pos)
    t1 = html.find("</tbody>", t0)
    if t0 < 0 or t1 < t0:
        return html
    return html[: t0 + 7] + "\n" + new_rows_html + "\n" + html[t1:]


def build_biz_efficiency_rows_html(biz_list: List[Dict[str, Any]]) -> str:
    rows = []
    for b in sorted(biz_list, key=lambda x: -float(x.get("demand_count", 0))):
        rows.append(
            "<tr>"
            f'<td style="text-align:left;font-weight:600;">{html_module.escape(str(b.get("name", "")))}</td>'
            f'<td>{int(b.get("demand_count", 0))}</td>'
            f"<td>{round(float(b.get('total_workload', 0.0)), 1)}</td>"
            f'<td class="test-highlight">{round(float(b.get("test_total", 0.0)), 1)}</td>'
            f"<td>{round(float(b.get('corrected_rd', 0.0)), 1)}</td>"
            f"<td>{round(float(b.get('rt_ratio', 0.0)), 2)}</td>"
            f"<td>{round(float(b.get('avg_delivery_cycle_days', 0.0)), 2)}天</td>"
            f"<td>{int(float(b.get('bugs', 0.0)))}</td>"
            f"<td>{round(float(b.get('avg_bugs_per_demand', 0.0)), 2)}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def build_biz_test_stage_rows_html(biz_list: List[Dict[str, Any]]) -> str:
    total_qc = sum(float(b.get("qc_design", 0.0)) for b in biz_list)
    total_test = sum(float(b.get("test_score", 0.0)) for b in biz_list)
    total_pre = sum(float(b.get("pre_test", 0.0)) for b in biz_list)
    total_stage = total_qc + total_test + total_pre
    rows = []
    for b in sorted(biz_list, key=lambda x: -float(x.get("test_total", 0.0))):
        qc = float(b.get("qc_design", 0.0))
        test_node = float(b.get("test_score", 0.0))
        pre = float(b.get("pre_test", 0.0))
        tt = float(b.get("test_total", 0.0))
        rows.append(
            "<tr>"
            f'<td style="text-align:left;font-weight:600;">{html_module.escape(str(b.get("name", "")))}</td>'
            f'<td>{int(b.get("demand_count", 0))}</td>'
            f'<td class="test-highlight">{round(qc, 1)}</td>'
            f'<td class="test-highlight">{round(test_node, 1)}</td>'
            f'<td class="test-highlight">{round(pre, 1)}</td>'
            f'<td class="test-highlight">{round(qc / (tt + 1e-6) * 100, 1)}%</td>'
            f'<td class="test-highlight">{round(test_node / (tt + 1e-6) * 100, 1)}%</td>'
            f'<td class="test-highlight">{round(pre / (tt + 1e-6) * 100, 1)}%</td>'
            f'<td class="test-highlight" style="font-weight:700;">{round(tt, 1)}</td>'
            f'<td style="font-weight:600;color:#0369a1;">{round(tt / (total_stage + 1e-6) * 100, 1)}%</td>'
            "</tr>"
        )
    rows.append(
        '<tr style="background:#f1f5f9;font-weight:700;">'
        '<td style="text-align:left;">合计</td>'
        f"<td>{sum(int(b.get('demand_count', 0)) for b in biz_list)}</td>"
        f'<td class="test-highlight">{round(total_qc, 1)}</td>'
        f'<td class="test-highlight">{round(total_test, 1)}</td>'
        f'<td class="test-highlight">{round(total_pre, 1)}</td>'
        f'<td class="test-highlight">{round(total_qc / (total_stage + 1e-6) * 100, 1)}%</td>'
        f'<td class="test-highlight">{round(total_test / (total_stage + 1e-6) * 100, 1)}%</td>'
        f'<td class="test-highlight">{round(total_pre / (total_stage + 1e-6) * 100, 1)}%</td>'
        f'<td class="test-highlight">{round(total_stage, 1)}</td>'
        "<td>100%</td>"
        "</tr>"
    )
    return "\n".join(rows)


def build_js_biz_data(rows: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    stats: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "demands": 0,
            "total_work": 0.0,
            "design": 0.0,
            "rd": 0.0,
            "test_score": 0.0,
            "test_node": 0.0,
            "test_total": 0.0,
            "qc": 0.0,
            "pre": 0.0,
            "bugs": 0.0,
            "cycles": [],
        }
    )
    for r in rows:
        b = _biz_line(r)
        d, rd, qc, tnode, te, pr, tt = effort_fields(r)
        o = stats[b]
        o["demands"] += 1
        o["total_work"] += d + rd + qc + te + pr
        o["design"] += d
        o["rd"] += rd
        o["test_score"] += te
        o["test_node"] += tnode
        o["test_total"] += tt
        o["qc"] += qc
        o["pre"] += pr
        o["bugs"] += _pf(r.get("总 bug 数"))
        cy = _cycle_days(_parse_dt(r.get("创建时间")), _parse_dt(r.get("完成日期")))
        if cy is not None:
            o["cycles"].append(float(cy))
    out: List[Dict[str, Any]] = []
    for b, o in sorted(stats.items(), key=lambda kv: -kv[1]["demands"]):
        test_total = float(o["test_total"])
        rd_corr = float(o["design"] + o["rd"] + max(0.0, o["test_score"] - o["test_node"]))
        avg_cycle = round(sum(o["cycles"]) / len(o["cycles"]), 2) if o["cycles"] else 0.0
        out.append(
            {
                "业务线": b,
                "需求数": int(o["demands"]),
                "总工时": round(float(o["total_work"]), 2),
                "技术方案": round(float(o["design"]), 1),
                "研发总": round(float(o["rd"]), 1),
                "测试估分": round(float(o["test_score"]), 1),
                "测试节点": round(float(o["test_node"]), 1),
                "修正研发": round(rd_corr, 1),
                "测试工时": round(test_total, 1),
                "QC用例": round(float(o["qc"]), 1),
                "预发测试": round(float(o["pre"]), 1),
                "Bug数": int(o["bugs"]),
                "R/T": round(rd_corr / (test_total + 1e-6), 2) if test_total else 0.0,
                "平均工期": avg_cycle,
                "平均工时": round(float(o["total_work"]) / max(int(o["demands"]), 1), 2),
                "均Bug": round(float(o["bugs"]) / max(int(o["demands"]), 1), 2),
            }
        )
    return out


def build_js_demand_scatter(rows: List[Dict[str, str]]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        b = _biz_line(r)
        d, rd, _qc, tnode, te, _pr, tt = effort_fields(r)
        cy = _cycle_days(_parse_dt(r.get("创建时间")), _parse_dt(r.get("完成日期")))
        dev_corr = d + rd + max(0.0, te - tnode)
        out[b].append(
            {
                "name": (r.get("名称") or "").strip()[:80] or "未命名需求",
                "fullname": (r.get("名称") or "").strip() or "未命名需求",
                "cycle": round(float(cy), 1) if cy is not None else 0.0,
                "effort": round(float(d + rd + _qc + te + _pr), 1),
                "test_effort": round(float(tt), 1),
                "dev_effort": round(float(dev_corr), 1),
                "rt": round(float(dev_corr) / (float(tt) + 1e-6), 2) if tt else 0.0,
                "bugs": int(_pf(r.get("总 bug 数"))),
                "vtype": (r.get("价值类型") or "").strip() or "未分类",
                "link": (r.get("需求链接") or "").strip(),
                "finish_date": (r.get("完成日期") or "").strip().split(" ")[0],
            }
        )
    for k in out:
        out[k].sort(key=lambda x: (-x["test_effort"], -x["effort"]))
    return dict(out)


def _month_detail_block(
    rows: List[Dict[str, str]],
    m: str,
    active: bool,
    period_key: Optional[Callable[[Dict[str, str]], Optional[str]]] = None,
) -> str:
    if period_key is None:
        period_key = _month_period_key
    g = _global_month_row(rows, m, period_key)
    n = g["demand_count"]
    if not n:
        body = "<p style=\"padding:12px;color:#64748b;\">该月无完成需求</p>"
    else:
        rd_m = sum(_pf(r.get("研发总估分")) for r in rows if period_key(r) == m)
        xs = [
            float(x)
            for x in (
                _cycle_days(_parse_dt(r.get("创建时间")), _parse_dt(r.get("完成日期")))
                for r in rows
                if period_key(r) == m
            )
            if x is not None
        ]
        ac = sum(xs) / len(xs) if xs else 0.0
        bugs = int(sum(_pf(r.get("总 bug 数")) for r in rows if period_key(r) == m))
        avg_dev_m = round(rd_m / max(n, 1), 2)
        rd_corr = sum(corrected_rd(r) for r in rows if period_key(r) == m)
        rt_m = round(rd_corr / (g["test_effort"] + 1e-6), 2) if g["test_effort"] else 0.0
        body = f"""<div class="summary-cards" style="margin-bottom:16px;">
<div class="card"><h3>需求数</h3><div class="value">{n}</div></div>
<div class="card"><h3>总工时</h3><div class="value">{g["total_effort"]}</div><div class="sub">人天</div></div>
<div class="card"><h3>测试工时</h3><div class="value test">{g["test_effort"]}</div><div class="sub">人天</div></div>
<div class="card"><h3>均测试工时</h3><div class="value test">{round(g["test_effort"]/max(n,1),2)}</div><div class="sub">人天/需求</div></div>
<div class="card"><h3>研发工时</h3><div class="value">{round(rd_m,2)}</div><div class="sub">人天</div></div>
<div class="card"><h3>均开发工时</h3><div class="value">{avg_dev_m}</div><div class="sub">人天/需求</div></div>
<div class="card"><h3>R/T</h3><div class="value">{rt_m}</div></div>
<div class="card"><h3>平均工期</h3><div class="value">{round(ac,2)}</div><div class="sub">天</div></div>
<div class="card"><h3>Bug数</h3><div class="value">{bugs}</div><div class="sub">均Bug: {round(bugs/max(n,1),2)}</div></div>
</div>
<div style="padding:14px;background:#f8fafc;border-radius:10px;border:1px solid #e2e8f0;">
<div style="font-weight:600;color:#0369a1;margin-bottom:10px;">📊 测试相关工时明细</div>
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;font-size:13px;">
<div style="text-align:center;padding:10px;background:#fff;border-radius:8px;border:1px solid #e0f2fe;">
<div style="color:#64748b;font-size:11px;">QC用例</div>
<div style="font-size:18px;font-weight:700;color:#0369a1;">{g["qc_effort"]}</div>
</div>
<div style="text-align:center;padding:10px;background:#fff;border-radius:8px;border:1px solid #e0f2fe;">
<div style="color:#64748b;font-size:11px;">测试</div>
<div style="font-size:18px;font-weight:700;color:#0369a1;">{g["test_node"]}</div>
</div>
<div style="text-align:center;padding:10px;background:#fff;border-radius:8px;border:1px solid #e0f2fe;">
<div style="color:#64748b;font-size:11px;">预发</div>
<div style="font-size:18px;font-weight:700;color:#0369a1;">{g["preflight"]}</div>
</div>
<div style="text-align:center;padding:10px;background:#fef2f2;border-radius:8px;border:1px solid #fecaca;">
<div style="color:#64748b;font-size:11px;">测试占比</div>
<div style="font-size:18px;font-weight:700;color:#dc2626;">{g["pct"]}%</div>
</div>
</div>
</div>"""
    cls = "inner-panel active" if active else "inner-panel"
    pid = _fmt_month_panel_id(m)
    return f'<div class="{cls}" id="panel-{pid}">{body}</div>'


def build_v4_global_month_section_html(
    rows: List[Dict[str, str]],
    months: List[str],
    period_key: Optional[Callable[[Dict[str, str]], Optional[str]]] = None,
    axis_iteration: bool = False,
) -> str:
    if period_key is None:
        period_key = _month_period_key
    if months == ["N/A"]:
        return '<div class="section"><div class="section-title">📅 分月统计（全局）</div><p>无完成日期数据</p></div>'
    glist = build_global_monthly_test_pct(rows, months, period_key)
    period_label = "迭代" if axis_iteration else "月份"
    tabs = [f'<div class="inner-tab active" data-panel="global-month-all">📊 汇总对比</div>']
    for m in months:
        tabs.append(
            f'<div class="inner-tab" data-panel="{_fmt_month_panel_id(m)}">{m}</div>'
        )
    rows_tb = []
    for g in glist:
        m = g["month"]
        n = g["demand_count"]
        rd_m = sum(_pf(r.get("研发总估分")) for r in rows if period_key(r) == m)
        xs = [
            float(x)
            for x in (
                _cycle_days(_parse_dt(r.get("创建时间")), _parse_dt(r.get("完成日期")))
                for r in rows
                if period_key(r) == m
            )
            if x is not None
        ]
        ac = sum(xs) / len(xs) if xs else 0.0
        bugs = int(sum(_pf(r.get("总 bug 数")) for r in rows if period_key(r) == m))
        rd_corr = sum(corrected_rd(r) for r in rows if period_key(r) == m)
        rt_m = round(rd_corr / (g["test_effort"] + 1e-6), 2) if g["test_effort"] else 0.0
        hi = 'style="background:#fef2f2;color:#dc2626;font-weight:600;"' if g["pct"] >= 40 else ""
        rows_tb.append(
            f"<tr><td style=\"font-weight:600;\">{m}</td><td>{n}</td><td>{g['total_effort']}</td>"
            f"<td class=\"test-highlight\">{g['test_effort']}</td><td class=\"test-highlight\">{round(g['test_effort']/max(n,1),2)}</td>"
            f"<td>{round(rd_m,2)}</td><td>{rt_m}</td><td>{round(ac,2)}天</td><td>{bugs}</td>"
            f"<td>{round(bugs/max(n,1),2)}</td><td class=\"test-highlight\" {hi}>{g['pct']}%</td></tr>"
        )
    all_panel = f"""<div class="inner-panel active" id="panel-global-month-all">
<div class="table-wrap">
<table>
<thead><tr><th>{period_label}</th><th>需求数</th><th>总工时</th><th class="test-highlight">测试工时</th><th class="test-highlight">均测试</th><th>研发工时</th><th>R/T</th><th>平均工期</th><th>Bug数</th><th>均Bug</th><th class="test-highlight">测试占比</th></tr></thead>
<tbody>
{"".join(rows_tb)}
</tbody></table></div></div>"""
    month_panels = "".join(_month_detail_block(rows, m, False, period_key) for m in months)
    return f"""<div class="section">
<div class="section-title">📅 分月统计（全局）</div>
<div class="inner-tabs" id="global-month-tabs">
{"".join(tabs)}
</div>
{all_panel}
{month_panels}
</div>"""


def build_qc_team_chart_series(
    rows: List[Dict[str, str]],
    months: List[str],
    period_key: Optional[Callable[[Dict[str, str]], Optional[str]]] = None,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """按团队（新分组）聚合，取测试工时最多的 7 个团队 + 其他，序列与 months 对齐（测试工时÷五阶段×100）。"""
    if period_key is None:
        period_key = _month_period_key
    team_m_tt: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    team_m_five: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        team = _biz_line(r)
        mk = period_key(r)
        if not mk:
            continue
        d, rd, qc, _, te, pr, tt = effort_fields(r)
        team_m_tt[team][mk] += tt
        team_m_five[team][mk] += d + rd + qc + te + pr
    tot_by_team: Dict[str, float] = {t: sum(team_m_tt[t].values()) for t in team_m_tt}
    top = sorted(tot_by_team.keys(), key=lambda x: -tot_by_team[x])[:7]
    legend = list(top) + (["其他"] if len(tot_by_team) > 7 else [])
    series = []
    for i, name in enumerate(legend):
        col = _COLORS[i % len(_COLORS)]
        data = []
        for m in months:
            if name == "其他":
                s_tt = sum(team_m_tt[t][m] for t in team_m_tt if t not in top)
                s_w = sum(team_m_five[t][m] for t in team_m_five if t not in top)
            else:
                s_tt = team_m_tt[name][m]
                s_w = team_m_five[name][m]
            data.append(round(s_tt / (s_w + 1e-6) * 100, 1) if s_w else 0.0)
        series.append(
            {
                "name": name,
                "type": "line",
                "smooth": False,
                "symbol": "circle",
                "symbolSize": 6,
                "lineStyle": {"width": 2, "color": col},
                "itemStyle": {"color": col, "borderColor": "#fff", "borderWidth": 1},
                "emphasis": {"scale": True, "focus": "series"},
                "data": data,
            }
        )
    return legend, series


def build_team_monthly_pct_chart_script(
    months: List[str],
    rows: List[Dict[str, str]],
    period_key: Optional[Callable[[Dict[str, str]], Optional[str]]] = None,
) -> str:
    legend, series = build_qc_team_chart_series(rows, months, period_key)
    months_js = json.dumps(months, ensure_ascii=False)
    legend_js = json.dumps(legend, ensure_ascii=False)
    series_js = json.dumps(series, ensure_ascii=False, separators=(",", ":"))
    return f"""<script>
var teamMonthlyPctChart = null;
function initTeamMonthlyPctChart() {{
    if (teamMonthlyPctChart) {{
        teamMonthlyPctChart.resize();
        return;
    }}
    var dom = document.getElementById('team-monthly-pct-chart');
    if (!dom || dom.offsetWidth === 0) return;
    teamMonthlyPctChart = echarts.init(dom);
    var monthsX = {months_js};
    var option = {{
        tooltip: {{
            trigger: 'axis',
            backgroundColor: 'rgba(255,255,255,0.98)',
            borderColor: '#e2e8f0',
            borderWidth: 1,
            textStyle: {{ color: '#1e293b', fontSize: 12 }},
            formatter: function(params) {{
                var result = '<div style="font-weight:600;margin-bottom:8px;color:#334155;">' + params[0].axisValue + '</div>';
                params.sort(function(a, b) {{ return b.value - a.value; }});
                params.forEach(function(p) {{
                    result += '<div style="display:flex;align-items:center;margin:4px 0;"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + p.color + ';margin-right:8px;"></span><span style="flex:1;">' + p.seriesName + '</span><b style="color:' + p.color + ';">' + p.value + '%</b></div>';
                }});
                return result;
            }}
        }},
        legend: {{
            data: {legend_js},
            bottom: 10,
            type: 'scroll',
            textStyle: {{ fontSize: 11, color: '#475569' }},
            itemWidth: 16,
            itemHeight: 10,
            itemGap: 16
        }},
        grid: {{ left: 50, right: 30, bottom: 60, top: 30 }},
        xAxis: {{
            type: 'category',
            boundaryGap: false,
            data: monthsX,
            axisLabel: {{ fontSize: 11, color: '#475569' }},
            axisLine: {{ lineStyle: {{ color: '#cbd5e1' }} }},
            axisTick: {{ show: false }}
        }},
        yAxis: {{
            type: 'value',
            name: '占比',
            nameTextStyle: {{ fontSize: 11, color: '#94a3b8', padding: [0, 30, 0, 0] }},
            axisLabel: {{ formatter: '{{value}}%', fontSize: 11, color: '#64748b' }},
            axisLine: {{ show: false }},
            splitLine: {{ lineStyle: {{ color: '#f1f5f9', type: 'dashed' }} }}
        }},
        series: {series_js}
    }};
    teamMonthlyPctChart.setOption(option);
}}
window.addEventListener('resize', function() {{ if (teamMonthlyPctChart) teamMonthlyPctChart.resize(); }});
</script>"""


def replace_js_const_between(html: str, start_marker: str, end_marker: str, new_middle: str) -> str:
    a = html.find(start_marker)
    if a < 0:
        raise ValueError(start_marker)
    start = a + len(start_marker)
    b = html.find(end_marker, start)
    if b < 0:
        raise ValueError(end_marker)
    return html[:start] + new_middle + html[b:]


def patch_gate_rdj_v4_html(
    html: str,
    rows: List[Dict[str, str]],
    data: Dict[str, Any],
    months: List[str],
    label: str,
    period_key: Optional[Callable[[Dict[str, str]], Optional[str]]] = None,
    axis_iteration: bool = False,
) -> str:
    if period_key is None:
        period_key = _month_period_key
    html = html.replace("<title>业务线分析报告（测试效能视角）</title>", "<title>业务线分析报告（测试效能视角 · CSV）</title>", 1)
    stat_note = "按所属迭代（年+SPRINT）统计" if axis_iteration else "按完成日期分月统计"
    html = re.sub(
        r"<h1>📊 业务线分析报告（测试效能视角）</h1>",
        f'<h1>📊 业务线分析报告（测试效能视角）</h1><p style="text-align:center;color:#64748b;margin:8px 0 0 0;font-size:13px;">{label} · {stat_note}</p>',
        html,
        count=1,
    )
    biz_list = data.get("biz_list") or []
    html = remap_biz_content_panel_ids(html, [b.get("name", "") for b in biz_list if b.get("name")])
    # main tabs
    m0 = html.find('<div class="main-tabs" id="mainTabs">')
    if m0 >= 0:
        m1m = re.search(r"</div>\s*</div>\s*<div\s+class=\"biz-content\s+active\"", html[m0:])
        if m1m:
            m1 = m0 + m1m.start()
            html = (
                html[: m0 + len('<div class="main-tabs" id="mainTabs">')]
                + "\n"
                + build_v4_main_tabs_html(biz_list, html)
                + "\n"
                + html[m1:]
            )
    # 汇总卡 + 全局占比图区块 + 分月 Tab 整块
    s0 = html.find('<div class="summary-cards">')
    s1 = html.find('<div class="section">\n<div class="section-title">📈 业务线四象限对比</div>', s0)
    if s0 >= 0 and s1 > s0:
        mid = (
            build_v4_summary_cards_html(data, rows)
            + """<div class="section">
<div class="section-title">📈 测试相关工时占比趋势（全局）</div>
<div style="margin-bottom:12px;padding:10px 14px;background:#fef2f2;border-radius:8px;border:1px solid #fca5a5;font-size:12px;color:#b91c1c;">
<b>口径说明：</b>（QC用例 + 测试 + 预发）÷（设计评审 + 研发 + QC用例 + 测试 + 预发）× 100%
</div>
<div id="global-test-pct-chart" style="height:300px;"></div>
</div>
"""
            + build_v4_global_month_section_html(rows, months, period_key, axis_iteration)
        )
        html = html[:s0] + mid + html[s1:]
    monthly = build_monthly_test_pct_by_biz(rows, months, period_key)
    global_list = build_global_monthly_test_pct(rows, months, period_key)
    html = _replace_tbody_after_anchor(
        html,
        "📋 各业务线测试效能汇总",
        build_biz_efficiency_rows_html(biz_list),
    )
    html = _replace_tbody_after_anchor(
        html,
        "🔬 测试各阶段工时分布（按业务线）",
        build_biz_test_stage_rows_html(biz_list),
    )
    html = _replace_panel_by_id(
        html,
        "biz-qc-summary",
        build_qc_summary_panel_html(rows, months, period_key),
    )
    js_biz_data = json.dumps(build_js_biz_data(rows), ensure_ascii=False, separators=(",", ":"))
    js_demand_scatter = json.dumps(build_js_demand_scatter(rows), ensure_ascii=False, separators=(",", ":"))
    html = replace_js_const_between(html, "const bizData =", "const demandScatter =", js_biz_data + ";\n")
    html = replace_js_const_between(html, "const demandScatter =", "const monthlyTestPct =", js_demand_scatter + ";\n")
    monthly_js = json.dumps(monthly, ensure_ascii=False, separators=(",", ":"))
    global_js = json.dumps(global_list, ensure_ascii=False, separators=(",", ":"))
    html = replace_js_const_between(html, "const monthlyTestPct =", "const globalMonthlyTestPct =", monthly_js + "\n")
    html = replace_js_const_between(html, "const globalMonthlyTestPct =", "const demandCharts", global_js + ";\n")
    helper_js = """
function ensureBizPanelStructure(bizName) {
    if (!bizName || bizName === 'summary' || bizName === 'qc-summary') return;
    const panel = document.getElementById('biz-' + bizName);
    if (!panel) return;
    const bizId = bizName.replace(/-/g, '_');
    const needIds = [
        'test-pct-chart-' + bizId,
        'quadrant-chart-' + bizId,
        'conclusion-' + bizId,
        'outliers-content-' + bizId
    ];
    if (needIds.every(id => document.getElementById(id))) return;
    const rec = (bizData || []).find(x => x['业务线'] === bizName) || null;
    const demands = rec ? Number(rec['需求数'] || 0) : 0;
    const totalEffort = rec ? Number(rec['总工时'] || 0).toFixed(1) : '0.0';
    const testEffort = rec ? Number(rec['测试工时'] || 0).toFixed(1) : '0.0';
    const rt = rec ? Number(rec['R/T'] || 0).toFixed(2) : '0.00';
    const avgCycle = rec ? Number(rec['平均工期'] || 0).toFixed(2) : '0.00';
    panel.innerHTML = ''
        + '<div class="summary-cards">'
        + '<div class="card"><h3>需求数</h3><div class="value">' + demands + '</div></div>'
        + '<div class="card"><h3>总工时</h3><div class="value">' + totalEffort + '</div><div class="sub">人天</div></div>'
        + '<div class="card"><h3>测试工时</h3><div class="value test">' + testEffort + '</div><div class="sub">人天</div></div>'
        + '<div class="card"><h3>R/T</h3><div class="value">' + rt + '</div></div>'
        + '<div class="card"><h3>平均工期</h3><div class="value">' + avgCycle + '</div><div class="sub">天</div></div>'
        + '</div>'
        + '<div class="section">'
        + '  <div class="section-title">📈 测试相关工时占比趋势</div>'
        + '  <div id="test-pct-chart-' + bizId + '" style="height:300px;"></div>'
        + '</div>'
        + '<div class="section" id="quadrant-section-' + bizId + '">'
        + '  <div class="section-title">📊 交付周期 vs 总工时（四象限）</div>'
        + '  <div id="quadrant-chart-' + bizId + '" style="height:420px;"></div>'
        + '  <div id="conclusion-' + bizId + '"></div>'
        + '</div>'
        + '<div class="section">'
        + '  <div class="section-title">⚠️ 异常数据点</div>'
        + '  <div id="outliers-content-' + bizId + '"><div style="padding:20px;text-align:center;color:#94a3b8;">加载中...</div></div>'
        + '</div>';
}
"""
    html = html.replace("function renderDemandQuadrant(bizName) {", helper_js + "\nfunction renderDemandQuadrant(bizName) {", 1)
    html = html.replace("            renderDemandQuadrant(biz);", "            ensureBizPanelStructure(biz);\n            renderDemandQuadrant(biz);", 1)
    # 团队占比趋势图脚本
    ts0 = html.find("<div id=\"team-monthly-pct-chart\"")
    if ts0 >= 0:
        tsc = html.find("<script>", ts0)
        tse = html.find("</script>", tsc) + len("</script>")
        if tsc > ts0 and tse > tsc:
            html = html[:tsc] + build_team_monthly_pct_chart_script(months, rows, period_key) + html[tse:]
    return html
