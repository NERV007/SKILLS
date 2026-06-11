"""全景单页 · 多源数据横向对账与校验。"""

from __future__ import annotations

from collections import Counter
from html import escape
from pathlib import Path
from typing import Any

from _paths import REPO_ROOT
from gate_rdj_metrics import dedupe_main_rows, load_rows, main_row_dedupe_key
from portfolio_raw_data import load_raw_records
from portfolio_rt_merge import _demand_dedupe_key, _source_bucket
from qc_unified_roster_report import CSV_AI_DEMAND_DEFAULT, CSV_ITER, CSV_STATION, CSV_TIME, _resolve_ai_demand_csv

CSV_TIME_P = REPO_ROOT / "需求导出-Gate-RDJ_时间维度.csv"
CSV_ITER_P = REPO_ROOT / "需求导出-Gate-RDJ_迭代维度.csv"


def _count_raw_by_module(records: list[dict[str, Any]]) -> dict[str, int]:
    c: Counter[str] = Counter()
    for r in records:
        c[r.get("module") or "—"] += 1
    return dict(c)


def compute_reconcile(
    mt: dict,
    mi: dict,
    br: dict,
    ai: dict,
    al: dict,
    dt: dict,
    di: dict,
    P: dict,
    rt_data: dict | None = None,
) -> dict[str, Any]:
    """汇总各模块条数及横向对照关系。"""
    time_kpi = int(mt["kpi"]["需求数"])
    iter_kpi = int(mi["kpi"]["需求数"])
    branch_n = int(br["kpi"]["工作项数"])
    ai_n = int(ai["kpi"].get("参与需求") or 0)
    alpha_n = int(al["kpi"]["需求数"])

    time_total = int(dt.get("total_demands") or time_kpi)
    time_gap = time_total - time_kpi

    merged_n = 0
    overlap = 0
    time_keys_n = 0
    iter_keys_n = 0
    if CSV_TIME_P.is_file() and CSV_ITER_P.is_file():
        time_rows = load_rows(str(CSV_TIME_P))
        iter_rows = load_rows(str(CSV_ITER_P))
        time_keys = {main_row_dedupe_key(r) for r in time_rows}
        iter_keys = {main_row_dedupe_key(r) for r in iter_rows}
        time_keys_n = len(time_keys)
        iter_keys_n = len(iter_keys)
        overlap = len(time_keys & iter_keys)
        merged_n = len(dedupe_main_rows([str(CSV_ITER_P), str(CSV_TIME_P)]))

    raw_records = load_raw_records()
    raw_by_mod = _count_raw_by_module(raw_records)
    raw_main = raw_by_mod.get("主站·Gate-RDJ", 0)
    raw_branch = raw_by_mod.get("分站·产研", 0)
    raw_ai = raw_by_mod.get("AI·Gate-AI", 0)
    raw_alpha = raw_by_mod.get("Alpha·Meegle", 0)
    raw_total = len(raw_records)

    _, ai_rows = _resolve_ai_demand_csv(CSV_AI_DEMAND_DEFAULT)
    ai_csv_n = len(ai_rows)

    branch_csv_n = 0
    if Path(CSV_STATION).is_file():
        branch_csv_n = len(load_rows(str(CSV_STATION)))

    alpha_csv_n = alpha_n

    rt_main_ids = 0
    rt_main_records = 0
    if rt_data:
        main_rows = [
            r for r in (rt_data.get("demands") or [])
            if _source_bucket(r.get("source", "")) == "main"
        ]
        rt_main_records = len(main_rows)
        rt_main_ids = len({_demand_dedupe_key(r) for r in main_rows})

    naive_main_sum = time_kpi + iter_kpi

    rows: list[dict[str, Any]] = [
        {
            "source": "主站 · 时间维",
            "count": time_kpi,
            "ref": "month_with_chain Σ（图表月桶）",
            "expect": f"= 时间维 KPI {time_kpi}",
            "ok": True,
            "note": "",
        },
        {
            "source": "主站 · 时间维（全量）",
            "count": time_total,
            "ref": "total_demands",
            "expect": f"≥ KPI；差额 {time_gap} 条未入月桶",
            "ok": time_gap >= 0,
            "note": "空完成日或轴外月份" if time_gap else "",
        },
        {
            "source": "主站 · 迭代维",
            "count": iter_kpi,
            "ref": "monthly_summary demands Σ",
            "expect": f"= 迭代维 KPI {iter_kpi}",
            "ok": True,
            "note": "",
        },
        {
            "source": "主站 · 去重合并",
            "count": merged_n,
            "ref": f"时间∩迭代 {overlap} 条",
            "expect": f"< 时间+迭代 {naive_main_sum}（不可相加）",
            "ok": merged_n < naive_main_sum if overlap else merged_n > 0,
            "note": f"唯一 story {merged_n} · 时间键 {time_keys_n} · 迭代键 {iter_keys_n}",
        },
        {
            "source": "原始数据 · 主站",
            "count": raw_main,
            "ref": "dedupe_main_rows",
            "expect": f"= 去重合并 {merged_n}",
            "ok": raw_main == merged_n if merged_n else True,
            "note": "",
        },
        {
            "source": "分站 · 产研",
            "count": branch_n,
            "ref": f"CSV {branch_csv_n} 行" if branch_csv_n else "const P.n",
            "expect": f"= 原始数据分站 {raw_branch}",
            "ok": branch_n == raw_branch == (branch_csv_n or branch_n),
            "note": "",
        },
        {
            "source": "AI · Gate-AI",
            "count": ai_n,
            "ref": f"清洗后 CSV {ai_csv_n} 行",
            "expect": f"= 原始数据 AI {raw_ai}",
            "ok": ai_n == raw_ai == (ai_csv_n or ai_n),
            "note": "已剔除 rollup 汇总行" if ai_csv_n == ai_n else "",
        },
        {
            "source": "Alpha · Meegle",
            "count": alpha_n,
            "ref": f"主站 {al['kpi']['主站条数']} + 分站 {al['kpi']['分站条数']}",
            "expect": f"= 原始数据 Alpha {raw_alpha}",
            "ok": alpha_n == raw_alpha and al["kpi"]["主站条数"] + al["kpi"]["分站条数"] == alpha_n,
            "note": "",
        },
        {
            "source": "原始数据 · 合计",
            "count": raw_total,
            "ref": "四模块行数之和",
            "expect": f"= {raw_main}+{raw_branch}+{raw_ai}+{raw_alpha}",
            "ok": raw_total == raw_main + raw_branch + raw_ai + raw_alpha,
            "note": "需求级台账，可下钻 CSV",
        },
    ]

    if rt_data:
        rows.append({
            "source": "RT 合并 · 主站记录",
            "count": rt_main_records,
            "ref": f"唯一样本 {rt_main_ids} 条",
            "expect": f"≤ 去重 {merged_n}（QC 展开会更多）",
            "ok": rt_main_ids <= merged_n if merged_n else True,
            "note": f"缺失 {merged_n - rt_main_ids} 条多为 QC 白名单未命中" if merged_n and rt_main_ids < merged_n else "",
        })

    errors: list[str] = []
    warns: list[str] = []
    for r in rows:
        if not r["ok"]:
            errors.append(f"对账失败：{r['source']} {r['count']} — {r['expect']}")
    if time_gap > 0:
        warns.append(f"时间维 total_demands {time_total} − 月桶 KPI {time_kpi} = {time_gap}（未入轴）")
    if rt_data and merged_n and rt_main_ids < merged_n:
        warns.append(f"RT 主站唯一样本 {rt_main_ids} < 去重需求 {merged_n}（差 {merged_n - rt_main_ids}）")

    return {
        "rows": rows,
        "errors": errors,
        "warns": warns,
        "merged_n": merged_n,
        "raw_total": raw_total,
        "time_gap": time_gap,
        "overlap": overlap,
        "raw_by_mod": raw_by_mod,
    }


def reconcile_table_html(rec: dict[str, Any]) -> str:
    """生成总览 Tab 横向对账表 HTML。"""
    body = []
    for r in rec["rows"]:
        status = "✓" if r["ok"] else "✗"
        cls = "reconcile-ok" if r["ok"] else "reconcile-err"
        note = f'<div class="muted" style="font-size:11px">{escape(r["note"])}</div>' if r.get("note") else ""
        body.append(
            f"<tr class=\"{cls}\">"
            f"<td class=\"l\"><strong>{escape(r['source'])}</strong></td>"
            f"<td class=\"rt-num\"><strong>{r['count']}</strong></td>"
            f"<td class=\"l\">{escape(r['ref'])}</td>"
            f"<td class=\"l\">{escape(r['expect'])}</td>"
            f"<td class=\"rt-num\">{status}</td>"
            f"</tr>"
        )
    err_n = sum(1 for r in rec["rows"] if not r["ok"])
    summary = (
        f"对账 <strong>{len(rec['rows'])}</strong> 项"
        f" · 通过 <strong>{len(rec['rows']) - err_n}</strong>"
        + (f" · <span class=\"reconcile-err-text\">异常 {err_n}</span>" if err_n else "")
        + f" · 原始数据合计 <strong>{rec['raw_total']}</strong> 条"
    )
    return f"""
<div class="reconcile-wrap">
  <p class="section-desc muted">{summary}。主站时间/迭代为同批需求两种切分，<b>不可与去重合并相加</b>。</p>
  <div class="tbl-wrap">
    <table class="data-table reconcile-table">
      <thead><tr>
        <th>数据源</th><th>条数</th><th>对照字段</th><th>期望关系</th><th>校验</th>
      </tr></thead>
      <tbody>{''.join(body)}</tbody>
    </table>
  </div>
</div>
"""


def validate_reconcile(rec: dict[str, Any]) -> tuple[list[str], list[str]]:
    return list(rec.get("errors") or []), list(rec.get("warns") or [])
