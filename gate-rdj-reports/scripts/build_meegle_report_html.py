#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 meegle_page_export.csv 生成「主站 / 分站」对照 HTML（版式对齐 QC 四源聚合页）。

主站：协作业务线不含 RDJ-（视为 Gate-WEB3 / Alpha 本阵需求）。
分站：协作业务线含 RDJ-（视为总部产研线协作支撑）。
口径与《QC人员名单-主站分站合并》中 Alpha·Meegle 说明一致：
  测试 = 视图「测试」流程节点人日；总估 = 「总估分(人/日)」；
  R/T（分站/Meegle 展示）= (总估 − 测试) ÷ 测试。
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

from _paths import DATA_DIR, REPO_ROOT

_REPO = REPO_ROOT

K_TEST = "uiDataMap.4364c1569f37ceb8203ab885d5358656.uiValue.number.value"
K_TOTAL = "uiDataMap.1l5clgkicgqw2.uiValue.number.value"
K_COLLAB = "uiDataMap.1l5ggwqgi1hcx.uiValue.cascadeSelect.value"
K_ORIGIN = "uiDataMap.1lbv4asx1qqkz.uiValue.cascadeSelect.value"
K_PRIO = "uiDataMap.1l5clgkicb4ma.uiValue.select.value"
K_TITLE = "uiDataMap.1l5clgkicafc2.uiValue.nameWithComment.value"
K_STATUS = "uiDataMap.1l5clgkicezoi.uiValue.workItemStatus.value"
K_STORY = "storyID"
QC_UUID = "1l5n0fktf4wf6"


def fnum(x: str | None) -> float:
    if not x or not str(x).strip():
        return 0.0
    try:
        return float(str(x).replace(",", ""))
    except ValueError:
        return 0.0


def cascade_leaf_selected(raw: str | None) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    out: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            lab = node.get("label") or node.get("filterValue")
            kids = node.get("selectedChildren") or []
            if kids:
                for c in kids:
                    walk(c)
            elif lab and node.get("isSelected") is True:
                out.append(str(lab))
        elif isinstance(node, list):
            for x in node:
                walk(x)

    for item in data if isinstance(data, list) else [data]:
        walk(item)
    seen: set[str] = set()
    uniq = []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def cascade_bucket(raw: str | None) -> str:
    labs = cascade_leaf_selected(raw)
    return labs[-1] if labs else "(未填)"


def prio_label(raw: str | None) -> str:
    if not raw or not str(raw).strip():
        return "—"
    try:
        j = json.loads(raw)
        if isinstance(j, list) and j:
            return str(j[0].get("label") or j[0].get("filterValue") or "—")
    except json.JSONDecodeError:
        pass
    return "—"


def status_label(raw: str | None) -> str:
    if not raw or not str(raw).strip():
        return "—"
    try:
        j = json.loads(raw)
        if isinstance(j, list) and j:
            return str(j[0].get("label") or j[0].get("filterValue") or "—")
    except json.JSONDecodeError:
        pass
    return "—"


def is_qc_user(u: dict) -> bool:
    email = (u.get("email") or "").lower()
    if "-qc@" in email or email.endswith("qc@gate.me"):
        return True
    for k in ("name_cn", "name_en"):
        s = u.get(k) or ""
        if isinstance(s, str):
            sl = s.lower()
            if "-qc" in sl or "_qc" in sl or "qc-rdj" in sl or "-qc-" in sl:
                return True
    return False


def qc_names_from_row(
    r: dict[str, str], qc_col: str | None, *, qc_role_field: bool = False
) -> str:
    if not qc_col:
        return "—"
    raw = r.get(qc_col, "")
    if not raw or not str(raw).strip():
        return "—"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return html.escape(raw[:80])
    if not isinstance(data, list):
        return "—"
    names = []
    for u in data:
        if not isinstance(u, dict):
            continue
        if qc_role_field or is_qc_user(u):
            n = u.get("name_cn") or u.get("name_en") or u.get("email")
            if n:
                names.append(str(n).strip())
    return "、".join(names) if names else "—"


def discover_qc_column(
    fieldnames: list[str], rows: list[dict[str, str]] | None = None
) -> tuple[str | None, bool]:
    """返回 (QC 人员列, 是否为 Meegle QC 角色字段)."""
    for name in fieldnames:
        if QC_UUID in name and name.endswith("roleMultiUser.value"):
            return name, True
    sample = rows or []
    for name in fieldnames:
        if not name.endswith("uiValue.roleMultiUser.value"):
            continue
        role_name_col = name.replace(
            ".uiValue.roleMultiUser.value", ".uiValue.roleMultiUser.roleName"
        )
        if role_name_col in fieldnames:
            for r in sample[:40]:
                if (r.get(role_name_col) or "").strip().upper() == "QC":
                    return name, True
        for r in sample[:40]:
            raw = (r.get(name) or "").lower()
            if "-qc@" in raw or "qc-rdj" in raw or "yuliana-qc" in raw:
                return name, False
    return None, False


def row_bucket(title: str, collab_raw: str) -> str:
    """返回 main | branch"""
    t = title or ""
    cr = collab_raw or ""
    if "【分站】" in t or "分站" in cr or "RDJ-" in cr:
        return "branch"
    if "【主站】" in t:
        return "main"
    return "main"


def rt_meegle(total: float, test: float) -> str:
    if test <= 0:
        return "—"
    return f"{(total - test) / test:.2f}"


def load_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        return list(r), list(r.fieldnames or [])


def summarize(rows: list[dict[str, str]], qc_col: str | None) -> dict:
    n = len(rows)
    st = sum(fnum(r.get(K_TEST)) for r in rows)
    tot = sum(fnum(r.get(K_TOTAL)) for r in rows)
    rts = []
    for r in rows:
        t, tt = fnum(r.get(K_TEST)), fnum(r.get(K_TOTAL))
        if t > 0:
            rts.append((tt - t) / t)
    med = statistics.median(rts) if rts else None
    w_rt = (tot - st) / st if st > 0 else None
    return {
        "n": n,
        "test_sum": st,
        "total_sum": tot,
        "weighted_rt": w_rt,
        "median_rt": med,
    }


def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?", default=str(_REPO / "data" / "meegle_page_export.csv"))
    ap.add_argument("-o", "--output", default=str(_REPO / "Meegle-Gate-WEB3-主站分站-效能报告.html"))
    args = ap.parse_args()
    src = Path(args.csv)
    out = Path(args.output)
    rows, fields = load_csv(src)
    qc_col, qc_role_field = discover_qc_column(fields, rows)

    main_rows = [r for r in rows if row_bucket(r.get(K_TITLE, ""), r.get(K_COLLAB, "")) == "main"]
    branch_rows = [r for r in rows if row_bucket(r.get(K_TITLE, ""), r.get(K_COLLAB, "")) == "branch"]
    sm = summarize(main_rows, qc_col)
    sb = summarize(branch_rows, qc_col)
    sg = summarize(rows, qc_col)

    gen_at = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    prio_counts: dict[str, int] = {}
    for r in rows:
        pl = prio_label(r.get(K_PRIO))
        prio_counts[pl] = prio_counts.get(pl, 0) + 1
    prio_line = "、".join(f"{k} {v} 条" for k, v in sorted(prio_counts.items()))

    def fmt_rt(v: float | None) -> str:
        return f"{v:.2f}" if v is not None else "—"

    # 按测试人日排序明细
    def sort_key(r: dict[str, str]) -> float:
        return -fnum(r.get(K_TEST))

    rows_sorted = sorted(rows, key=sort_key)

    def table_body(row_list: list[dict[str, str]]) -> str:
        parts = []
        for r in sorted(row_list, key=sort_key):
            sid = (r.get(K_STORY) or "").strip()
            link = f"https://project.larksuite.com/iocb9y/project_story/detail/{sid}" if sid else "#"
            title = r.get(K_TITLE, "") or "（无标题）"
            t = fnum(r.get(K_TEST))
            tt = fnum(r.get(K_TOTAL))
            parts.append(
                "<tr>"
                f'<td class="rt-num">{esc(sid)}</td>'
                f'<td style="text-align:left;max-width:360px;"><a href="{esc(link)}" target="_blank" rel="noopener">{esc(title)}</a></td>'
                f'<td>{esc(prio_label(r.get(K_PRIO)))}</td>'
                f'<td style="text-align:left;font-size:11px;">{esc(cascade_bucket(r.get(K_ORIGIN)))}</td>'
                f'<td style="text-align:left;font-size:11px;">{esc(cascade_bucket(r.get(K_COLLAB)))}</td>'
                f'<td style="text-align:left;font-size:11px;">{esc(qc_names_from_row(r, qc_col, qc_role_field=qc_role_field))}</td>'
                f'<td class="rt-num">{t:.2f}</td>'
                f'<td class="rt-num">{tt:.2f}</td>'
                f'<td class="rt-num">{rt_meegle(tt, t)}</td>'
                f'<td>{esc(status_label(r.get(K_STATUS)))}</td>'
                "</tr>"
            )
        return "\n".join(parts)

    cards = lambda s: (
        f'<div class="card"><h3>需求数</h3><div class="value">{s["n"]}</div><div class="sub">条</div></div>'
        f'<div class="card"><h3>测试节点人日 Σ</h3><div class="value accent">{s["test_sum"]:.1f}</div><div class="sub">pd</div></div>'
        f'<div class="card"><h3>总估分 Σ</h3><div class="value">{s["total_sum"]:.1f}</div><div class="sub">pd</div></div>'
        f'<div class="card"><h3>加权 R/T</h3><div class="value">{(s["weighted_rt"] if s["weighted_rt"] is not None else 0):.2f}</div>'
        f'<div class="sub">(Σ总−Σ测)÷Σ测</div></div>'
    )

    css = """*{margin:0;padding:0;box-sizing:border-box}body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'PingFang SC','Microsoft YaHei',sans-serif;background:#f1f5f9;color:#1e293b;line-height:1.6}
.container{max-width:1320px;margin:0 auto;padding:24px 20px 48px}.masthead{text-align:center;padding:12px 12px 20px;margin-bottom:16px;border-bottom:1px solid #e2e8f0;background:linear-gradient(180deg,#fff 0%,rgba(248,250,252,.7) 60%,transparent);border-radius:0 0 18px 18px}
.eyebrow{font-size:11px;font-weight:700;letter-spacing:.12em;color:#0369a1}h1{color:#0c4a6e;font-size:24px;font-weight:800;margin:8px 0}.subtitle{color:#64748b;font-size:13px;margin-bottom:10px}
.lead{max-width:900px;margin:0 auto;font-size:13px;color:#475569}.brief-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:18px 0}@media(max-width:900px){.brief-grid{grid-template-columns:1fr}}
.panel-blue{background:#eff6ff;border:1px solid #bfdbfe;border-radius:12px;padding:14px 16px}.panel-amber{background:#fffbeb;border:1px solid #fde68a;border-radius:12px;padding:14px 16px}
.panel-title{font-size:13px;font-weight:700;color:#0c4a6e;margin-bottom:8px}.panel-amber .panel-title{color:#92400e}.panel-ul{margin:0;padding-left:1.1rem;font-size:12.5px;color:#334155;line-height:1.7}
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin:16px 0 8px}.tab-btn{font-size:13px;padding:8px 16px;border-radius:8px;border:1px solid #cbd5e1;background:#fff;cursor:pointer;color:#475569;font-weight:600}
.tab-btn:hover{background:#f8fafc}.tab-btn.active{background:#0ea5e9;border-color:#0ea5e9;color:#fff}.panel{display:none}.panel.active{display:block}
.section{background:#fff;padding:16px 18px;border-radius:12px;margin-bottom:14px;border:1px solid #e2e8f0;box-shadow:0 1px 3px rgba(0,0,0,.06)}.section-title{font-size:15px;font-weight:700;color:#0c4a6e;margin-bottom:12px;padding-bottom:8px;border-bottom:2px solid #e2e8f0}
.summary-cards{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:8px}@media(max-width:900px){.summary-cards{grid-template-columns:1fr 1fr}}
.card{background:#f8fafc;padding:12px;border-radius:10px;text-align:center;border:1px solid #e2e8f0}.card h3{font-size:11px;color:#64748b;font-weight:600}.card .value{font-size:20px;font-weight:700;color:#0c4a6e}.card .value.accent{color:#0ea5e9}.card .sub{font-size:10px;color:#94a3b8;margin-top:4px}
.table-wrap{overflow:auto;border:1px solid #e2e8f0;border-radius:10px;background:#fff}table.sum-table{width:100%;border-collapse:collapse;font-size:12px}table.sum-table th,table.sum-table td{padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:center}
table.sum-table th:first-child,table.sum-table td:first-child{text-align:left}table.sum-table th{background:#f1f5f9;font-weight:600;color:#475569}table.sum-table tr:nth-child(odd){background:#fafafa}table.sum-table tr:hover{background:#eff6ff}
.rt-num{font-variant-numeric:tabular-nums}.meta{font-size:11px;color:#94a3b8;margin-top:12px;text-align:center}"""

    html_out = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Gate-WEB3 · Meegle 视图 · 主站/分站效能</title>
<style>{css}</style>
</head>
<body>
<div class="container">
<div class="masthead">
<div class="eyebrow">Alpha · Meegle · 多项目视图</div>
<h1>Gate-WEB3 需求效能报告（主站 / 分站）</h1>
<p class="subtitle">数据源：<code>{esc(str(src.relative_to(_REPO)) if src.is_relative_to(_REPO) else str(src))}</code> · 生成时间 {esc(gen_at)} · 共 {len(rows)} 条需求</p>
<p class="lead">主站与分站划分规则：<strong>分站</strong> = 标题含「【分站】」或协作业务线字段中出现「RDJ-」或「分站」；其余归为<strong>主站</strong>（WEB3/Alpha 本阵）。指标与《QC人员名单-主站分站合并》中 Alpha·Meegle 口径对齐。本页仅基于 Meegle 导出视图，与 Gate-RDJ 修正研发÷测、产研全景 (总估−测)÷测 等<strong>不可硬比绝对值</strong>，仅作同视图内主站/分站对照。</p>
</div>
<div class="brief-grid">
<div class="panel-blue"><div class="panel-title">主站（{sm["n"]} 条）</div><ul class="panel-ul">
<li>测试节点人日合计 <strong>{sm["test_sum"]:.1f}</strong> pd；总估分合计 <strong>{sm["total_sum"]:.1f}</strong> pd。</li>
<li>加权 R/T（Meegle）= <strong>{(sm["weighted_rt"] if sm["weighted_rt"] is not None else 0):.2f}</strong>。</li>
</ul></div>
<div class="panel-amber"><div class="panel-title">分站 / 跨线协作（{sb["n"]} 条）</div><ul class="panel-ul">
<li>测试节点人日合计 <strong>{sb["test_sum"]:.1f}</strong> pd；总估分合计 <strong>{sb["total_sum"]:.1f}</strong> pd。</li>
<li>加权 R/T = <strong>{(sb["weighted_rt"] if sb["weighted_rt"] is not None else 0):.2f}</strong>（无数据时显示 0）。</li>
</ul></div>
</div>

<div class="section">
<div class="section-title">分析摘要</div>
<ul class="panel-ul" style="font-size:13px;color:#334155;line-height:1.8">
<li>优先级分布：{esc(prio_line)}。</li>
<li>主站 {sm["n"]} 条 · 测试 Σ {sm["test_sum"]:.1f} pd · 总估 Σ {sm["total_sum"]:.1f} pd · 加权 R/T {fmt_rt(sm["weighted_rt"])} · 中位 R/T {fmt_rt(sm["median_rt"])}。</li>
<li>分站 {sb["n"]} 条 · 测试 Σ {sb["test_sum"]:.1f} pd · 总估 Σ {sb["total_sum"]:.1f} pd · 加权 R/T {fmt_rt(sb["weighted_rt"])} · 中位 R/T {fmt_rt(sb["median_rt"])}。</li>
<li>全局中位 R/T {fmt_rt(sg["median_rt"])}；单条 R/T 最高需求见明细表（按测试 pd 降序）。</li>
</ul>
</div>

<div class="section">
<div class="section-title">全局卡片</div>
<div class="summary-cards">{cards(sg)}</div>
<p style="font-size:12px;color:#64748b;margin-top:8px">加权 R/T = (Σ总估分 − Σ测试节点) ÷ Σ测试节点；单条 R/T 列同公式。测试节点 = 视图排期「测试」流程节点人日。本视图未导出 QC 角色列时，QC 栏显示为 —。</p>
</div>

<div class="tabs">
<button type="button" class="tab-btn active" data-tab="all">全部</button>
<button type="button" class="tab-btn" data-tab="main">主站</button>
<button type="button" class="tab-btn" data-tab="branch">分站</button>
</div>

<div id="panel-all" class="panel active section">
<h2 class="section-title">全部需求明细</h2>
<div class="summary-cards">{cards(sg)}</div>
<div class="table-wrap"><table class="sum-table">
<thead><tr><th>ID</th><th>需求标题</th><th>优先级</th><th>发起业务线</th><th>协作业务线</th><th>QC</th><th>测试pd</th><th>总估pd</th><th>R/T</th><th>状态</th></tr></thead>
<tbody>{table_body(rows_sorted)}</tbody>
</table></div>
</div>

<div id="panel-main" class="panel section">
<h2 class="section-title">主站 · 明细</h2>
<div class="summary-cards">{cards(sm)}</div>
<div class="table-wrap"><table class="sum-table">
<thead><tr><th>ID</th><th>需求标题</th><th>优先级</th><th>发起业务线</th><th>协作业务线</th><th>QC</th><th>测试pd</th><th>总估pd</th><th>R/T</th><th>状态</th></tr></thead>
<tbody>{table_body(main_rows)}</tbody>
</table></div>
</div>

<div id="panel-branch" class="panel section">
<h2 class="section-title">分站 · 明细</h2>
<div class="summary-cards">{cards(sb)}</div>
<div class="table-wrap"><table class="sum-table">
<thead><tr><th>ID</th><th>需求标题</th><th>优先级</th><th>发起业务线</th><th>协作业务线</th><th>QC</th><th>测试pd</th><th>总估pd</th><th>R/T</th><th>状态</th></tr></thead>
<tbody>{table_body(branch_rows)}</tbody>
</table></div>
</div>

<p class="meta">由 scripts/build_meegle_report_html.py 生成 · QC 列：{esc(qc_col.split(".")[1] if qc_col and "." in qc_col else ("已识别" if qc_col else "未导出"))}</p>
</div>
<script>
document.querySelectorAll('.tab-btn').forEach(function(btn) {{
  btn.addEventListener('click', function() {{
    document.querySelectorAll('.tab-btn').forEach(function(b) {{ b.classList.remove('active'); }});
    document.querySelectorAll('.panel').forEach(function(p) {{ p.classList.remove('active'); }});
    btn.classList.add('active');
    var id = 'panel-' + btn.getAttribute('data-tab');
    var el = document.getElementById(id);
    if (el) el.classList.add('active');
  }});
}});
</script>
</body>
</html>"""

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_out, encoding="utf-8")
    print(f"已写入 {out}")


if __name__ == "__main__":
    main()
