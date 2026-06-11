"""从 Gate-RDJ-RT合并分析报告.html 抽取 D 数据，生成总览嵌入块。"""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path

from _paths import REPO_ROOT
from portfolio_dept_stats import DEPT_CACHE, fetch_dept_stats_html, parse_dept_stats

SRC_RT_MERGE = REPO_ROOT / "Gate-RDJ-RT合并分析报告.html"

_ROSTER_KEYS = ("pd", "fe", "be", "wbe", "api", "app")


def _dept_roster_by_label() -> dict[str, dict]:
    """department_stats 新分组 label → 各角色编制。"""
    try:
        html = DEPT_CACHE.read_text(encoding="utf-8") if DEPT_CACHE.is_file() else ""
        if not html.strip():
            html = fetch_dept_stats_html()
        ds = parse_dept_stats(html)
    except (OSError, ValueError):
        return {}
    return {str(r.get("label") or ""): r for r in ds.get("rows") or []}


def _roster_cells(dept_label: str, roster: dict[str, dict]) -> tuple[int, ...]:
    row = roster.get(dept_label) or {}
    return tuple(_parse_nonneg_int(row.get(k)) for k in _ROSTER_KEYS)


def load_rt_merge_data(path: Path | None = None) -> tuple[dict, float]:
    src = path or SRC_RT_MERGE
    text = src.read_text(encoding="utf-8")
    start = text.find("var D = ")
    if start < 0:
        raise ValueError(f"未找到 var D：{src}")
    start += len("var D = ")
    end = text.find(";\nvar TEST_FLOOR", start)
    if end < 0:
        end = text.find(";\nvar TEST_FLOOR", start)
    if end < 0:
        raise ValueError("未找到 D 结束标记")
    data = json.loads(text[start:end])
    m = re.search(r"var TEST_FLOOR\s*=\s*([\d.]+)", text)
    floor = float(m.group(1)) if m else 0.05
    return data, floor


def _fmt_rt(v: float | None) -> str:
    return "—" if v is None else f"{v:.2f}"


def _rt_cell(v: float | None) -> str:
    if v is None:
        return '<td class="na">—</td>'
    color = "#16a34a" if v < 2 else ("#0369a1" if v < 3 else "#dc2626")
    return f'<td class="rt-num" style="font-weight:700;color:{color}">{v:.2f}</td>'


def _parse_nonneg_int(v) -> int:
    try:
        n = int(str(v).strip())
        return n if n >= 0 else 0
    except (TypeError, ValueError):
        return 0


def _source_bucket(source: str) -> str | None:
    if source == "主站·Gate-RDJ":
        return "main"
    if source == "分站·全景":
        return "station"
    if source == "AI·Gate-AI项目集":
        return "ai"
    if source and str(source).startswith("Alpha"):
        return "alpha"
    return None


def _demand_dedupe_key(rec: dict) -> str:
    """同一需求多 QC 会展开为多行；汇总 R/T 须按需求去重，避免重复加总拉偏比值。"""
    url = str(rec.get("url") or "").strip()
    m = re.search(r"/detail/(\d+)", url)
    if m:
        return f"id:{m.group(1)}"
    title = str(rec.get("title") or "").strip()
    finish = str(rec.get("finish_date") or rec.get("month") or "").strip()
    return f"title:{title}|{finish}"


def compute_dept_summary(data: dict, test_floor: float = 0.05) -> dict:
    """全表汇总：编制各列求和；四源 R/T 由 demands 按需求去重后加权（Σ研发÷Σ测试）。"""
    depts = data.get("dept") or []
    dev_sum = qc_sum = 0
    role_sums = {k: 0 for k in _ROSTER_KEYS}
    samp = [0, 0, 0, 0]
    roster = _dept_roster_by_label()
    for d in depts:
        dev_sum += _parse_nonneg_int(d.get("dev"))
        qc_sum += _parse_nonneg_int(d.get("qc"))
        pd, fe, be, wbe, api, app = _roster_cells(str(d.get("dept") or ""), roster)
        role_sums["pd"] += pd
        role_sums["fe"] += fe
        role_sums["be"] += be
        role_sums["wbe"] += wbe
        role_sums["api"] += api
        role_sums["app"] += app
        for i, part in enumerate(str(d.get("samples", "")).split("/")[:4]):
            if part.strip().isdigit():
                samp[i] += int(part.strip())

    agg = {k: {"rd": 0.0, "test": 0.0} for k in ("main", "station", "ai", "alpha")}
    seen: dict[str, set[str]] = {k: set() for k in agg}
    for rec in data.get("demands") or []:
        bucket = _source_bucket(rec.get("source", ""))
        if not bucket:
            continue
        rd, test = rec.get("rd"), rec.get("test")
        if rd is None or test is None or float(test) <= test_floor or float(rd) <= 0:
            continue
        dkey = _demand_dedupe_key(rec)
        if dkey in seen[bucket]:
            continue
        seen[bucket].add(dkey)
        agg[bucket]["rd"] += float(rd)
        agg[bucket]["test"] += float(test)

    def wrt(k: str) -> float | None:
        a = agg[k]
        return round(a["rd"] / a["test"], 2) if a["test"] > 0 else None

    dev_qc = f"{dev_sum / qc_sum:.1f}:1" if qc_sum > 0 else "—"
    return {
        "label": "汇总",
        **role_sums,
        "dev": dev_sum,
        "qc": qc_sum,
        "dev_qc": dev_qc,
        "rt_main": wrt("main"),
        "rt_station": wrt("station"),
        "rt_ai": wrt("ai"),
        "rt_alpha": wrt("alpha"),
        "samples": f"{samp[0]}/{samp[1]}/{samp[2]}/{samp[3]}",
        "n_dept": len(depts),
        "n_records": len(data.get("demands") or []),
    }


def dept_summary_row_html(summary: dict) -> str:
    note = (
        f"编制 {summary['n_dept']} 个部门求和；"
        f"关联记录 {summary['n_records']} 条；"
        f"样本列=各部门 QC 可算条数求和；"
        f"R/T=有 QC 参与即算、按需求去重、整单 Σ研发÷Σ测试（部门级不分摊）"
    )
    role_tds = "".join(
        f"<td class='rt-num'><strong>{summary.get(k, 0)}</strong></td>"
        for k in _ROSTER_KEYS
    )
    return (
        f"<tr class='rt-dept-total'>"
        f"<td class='l'><strong>{escape(summary['label'])}</strong>"
        f"<div class='rt-total-note'>{note}</div></td>"
        f"{role_tds}"
        f"<td class='rt-num'><strong>{summary['dev']}</strong></td>"
        f"<td class='rt-num'><strong>{summary['qc']}</strong></td>"
        f"<td class='rt-num'><strong>{escape(summary['dev_qc'])}</strong></td>"
        f"{_rt_cell(summary.get('rt_main'))}"
        f"{_rt_cell(summary.get('rt_station'))}"
        f"{_rt_cell(summary.get('rt_ai'))}"
        f"{_rt_cell(summary.get('rt_alpha'))}"
        f"<td class='samples'><strong>{escape(summary['samples'])}</strong></td>"
        f"</tr>"
    )


def dept_table_html(data: dict, test_floor: float = 0.05) -> str:
    roster = _dept_roster_by_label()
    rows = []
    for d in data.get("dept") or []:
        pd, fe, be, wbe, api, app = _roster_cells(str(d.get("dept") or ""), roster)
        role_tds = "".join(f'<td class="rt-num">{n}</td>' for n in (pd, fe, be, wbe, api, app))
        rows.append(
            f"<tr>"
            f'<td class="l">{escape(d["dept"])}</td>'
            f"{role_tds}"
            f'<td class="rt-num">{escape(str(d["dev"]))}</td>'
            f'<td class="rt-num">{escape(str(d["qc"]))}</td>'
            f'<td class="rt-num">{escape(str(d["dev_qc"]))}</td>'
            f'{_rt_cell(d.get("rt_main"))}'
            f'{_rt_cell(d.get("rt_station"))}'
            f'{_rt_cell(d.get("rt_ai"))}'
            f'{_rt_cell(d.get("rt_alpha"))}'
            f'<td class="samples">{escape(str(d.get("samples", "")))}</td>'
            f"</tr>"
        )
    colspan = 15
    body = "".join(rows) if rows else f'<tr><td colspan="{colspan}" class="na">无部门数据</td></tr>'
    summary = compute_dept_summary(data, test_floor)
    foot = dept_summary_row_html(summary)
    return f"""<div class="rt-table-wrap">
<table class="sum-table rt-dept-table">
<thead><tr>
<th>部门</th><th>PD人数</th><th>FE人数</th><th>BE人数</th><th>WBE人数</th><th>API人数</th><th>APP开发</th>
<th>开发</th><th>QC</th><th>开发:QC</th>
<th>主站 R/T</th><th>分站 R/T</th><th>AI R/T</th><th>Alpha R/T</th><th>样本(主/分/AI/α)</th>
</tr></thead>
<tbody>{body}</tbody>
<tfoot>{foot}</tfoot>
</table></div>"""


def insights_html(data: dict) -> str:
    colors = ("c1", "c2", "c3", "c4")
    cards = []
    for i, block in enumerate(data.get("insights") or []):
        items = "".join(f"<li>{it}</li>" for it in block.get("items") or [])
        cls = colors[i % len(colors)]
        cards.append(
            f'<div class="ins-card {cls}">'
            f'<h4>{escape(block.get("title", ""))}</h4>'
            f"<ul>{items}</ul></div>"
        )
    return f'<div class="insight-grid">{"".join(cards)}</div>'


def rt_overview_panel(data: dict, test_floor: float, demand_embed: str = "") -> str:
    alert = (
        f"⚠️ <b>展示规则</b>：R/T = 研发工时 ÷ 测试工时。"
        f"测试 ≤ {test_floor} 人天 → <b>—</b>；某源样本 = 0 → 该源列为 —。不重算不估算。"
    )
    drill = ""
    if demand_embed:
        drill = (
            f'<details class="section-group rt-drill-section" open>'
            f'<summary class="group-title">需求明细</summary>'
            f'<div class="section-group-body">'
            f'<p class="part-desc">按模块 + 部门筛选；明细默认按月收起展示，点击月份展开。</p>'
            f"{demand_embed}</div></details>"
        )
    return f"""<div class="rt-merge-block">
<div class="alert-box">{alert}</div>
{part_rt("部门 × 四源加权 R/T（主站/分站/AI/Alpha)",
         "左侧 PD/FE/BE/WBE/API/APP 来自 department_stats；右侧为四源加权 R/T；某源样本=0 则该列 —",
         dept_table_html(data, test_floor))}
{part_rt("核心洞察", "基于可算 R/T 样本，不做估算补全", insights_html(data))}
{drill}
</div>"""


def part_rt(title: str, desc: str, body: str) -> str:
    d = f'<p class="section-desc">{escape(desc)}</p>' if desc else ""
    return (
        f'<section class="rt-section">'
        f'<h3 class="rt-section-title">{title}</h3>{d}{body}</section>'
    )


def rt_merge_script_js(data: dict, test_floor: float) -> str:
    """RT 合并静态表无额外脚本；需求明细由 portfolio_raw_data 注入。"""
    return ""
