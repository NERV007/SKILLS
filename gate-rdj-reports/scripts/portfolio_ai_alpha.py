"""全景单页：Gate-AI 与 Alpha(Meegle) 数据（对齐 Gate-AI 源 HTML，不含兜底模块）。"""

from __future__ import annotations

import re
from html import escape, unescape
from pathlib import Path

from _paths import DATA_DIR, REPO_ROOT
from build_meegle_report_html import (
    K_COLLAB,
    K_PRIO,
    K_TEST,
    K_TITLE,
    K_TOTAL,
    discover_qc_column,
    fnum,
    load_csv,
    prio_label,
    row_bucket,
    summarize,
)

MEEGLE_CSV = DATA_DIR / "meegle_view_8bbOlLnNU.csv"
SRC_AI_HTML = REPO_ROOT / "Gate-AI项目集-测试工时与RT分析报告.html"


def _strip_td(cell: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", cell).strip())


def _tbody_after_header(html: str, header_marker: str) -> str:
    """按表头锚点截取 tbody 内容（避免 re.S 跨表误匹配）。"""
    anchor = html.find(header_marker)
    if anchor < 0:
        return ""
    tb = html.find("<tbody>", anchor)
    if tb < 0:
        return ""
    te = html.find("</tbody>", tb)
    return html[tb + 7 : te] if te > tb else ""


def _parse_ai_biz(html: str) -> list[dict]:
    biz = []
    body = _tbody_after_header(html, "<th>业务线</th><th>需求数</th><th>估算人日</th>")
    if not body:
        return biz
    for row in re.findall(r"<tr>(.*?)</tr>", body, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(cells) < 8:
            continue
        test_pct = rt = None
        if len(cells) >= 10:
            tp = _strip_td(cells[8])
            test_pct = float(tp) if tp and tp != "—" else None
            rtv = _strip_td(cells[9])
            rt = float(rtv) if rtv and rtv != "—" else None
        biz.append({
            "name": _strip_td(cells[0]),
            "demands": int(_strip_td(cells[1])),
            "est": float(_strip_td(cells[2])),
            "test_alloc": float(_strip_td(cells[7])),
            "test_pct": test_pct,
            "rt": rt,
        })
    return biz


def _parse_ai_delivery(html: str) -> list[dict]:
    out = []
    body = _tbody_after_header(
        html, "<th>所属项目</th><th>需求数</th><th>可计交付</th>"
    )
    if not body:
        return out
    for row in re.findall(r"<tr>(.*?)</tr>", body, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(cells) >= 5:
            out.append({
                "name": _strip_td(cells[0]),
                "demands": int(_strip_td(cells[1])),
                "counted": int(_strip_td(cells[2])),
                "avg": float(_strip_td(cells[3])),
                "med": float(_strip_td(cells[4])),
            })
    return out


def _parse_ai_qc(html: str) -> list[dict]:
    out = []
    body = _tbody_after_header(html, "<th>QC</th><th>新分组</th><th>加权需求</th>")
    if not body:
        return out
    for row in re.findall(r"<tr>(.*?)</tr>", body, re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(cells) >= 7:
            rtv = _strip_td(cells[6])
            out.append({
                "name": _strip_td(cells[0]),
                "group": _strip_td(cells[1]),
                "w_dem": float(_strip_td(cells[2])),
                "est": float(_strip_td(cells[3])),
                "test": float(_strip_td(cells[4])),
                "test_pct": _strip_td(cells[5]),
                "rt": float(rtv) if rtv and rtv != "—" else None,
            })
    return sorted(out, key=lambda x: -x["test"])


def _parse_ai_health(html: str) -> dict:
    h: dict[str, float] = {}
    m = re.search(r"白名单命中</th><td>([\d.]+)%", html)
    if m:
        h["whitelist_hit_pct"] = float(m.group(1))
    return h


def _parse_ai_summary_kpi(html: str) -> dict:
    kpi: dict[str, float | int] = {}
    patterns = [
        ("参与需求", r"<h3>参与需求数</h3><div class=\"value\">(\d+)</div>"),
        ("估算人日Σ", r"<h3>估算人日合计</h3><div class=\"value\">([\d.]+)</div>"),
        ("测试分摊Σ", r"<h3>测试分摊人日</h3><div class=\"value test\">([\d.]+)</div>"),
        ("测试占比%", r"<h3>本页·测试占比</h3><div class=\"value test\">([\d.]+)</div>"),
        ("研发分摊Σ", r"<h3>研发分摊人日</h3><div class=\"value\">([\d.]+)</div>"),
        ("分摊R/T", r"<h3>本页·全局 R/T</h3><div class=\"value\">([\d.]+)</div>"),
        ("命中QC人", r"<h3>本期命中 QC 人</h3><div class=\"value\">(\d+)</div>"),
        ("平均交付天", r"<h3>平均交付天数</h3><div class=\"value\">([\d.]+)</div>"),
        ("中位交付天", r"<h3>中位交付天数</h3><div class=\"value\">([\d.]+)</div>"),
        ("日期齐全%", r"<h3>日期齐全占比</h3><div class=\"value\">([\d.]+)</div>"),
    ]
    for name, pat in patterns:
        m = re.search(pat, html)
        if m:
            v = m.group(1)
            kpi[name] = float(v) if "." in v else int(v)
    return kpi


def _parse_ai_brief_obs(html: str) -> list[str]:
    """源报告「关键观察」，去掉含「兜底」的条目。"""
    m = re.search(r"panel-blue.*?<ul class=\"brief-ul\">(.*?)</ul>", html, re.S)
    if not m:
        return []
    out = []
    for li in re.findall(r"<li>(.*?)</li>", m.group(1), re.S):
        text = unescape(re.sub(r"<[^>]+>", "", li).strip())
        if text and "兜底" not in text:
            out.append(text)
    return out


def load_ai_from_html(path: Path | None = None) -> dict:
    src = path or SRC_AI_HTML
    html = src.read_text(encoding="utf-8")
    biz = _parse_ai_biz(html)
    delivery = _parse_ai_delivery(html)
    qc = _parse_ai_qc(html)
    health = _parse_ai_health(html)
    kpi = _parse_ai_summary_kpi(html)

    insights: list[str] = []
    for text in _parse_ai_brief_obs(html):
        if "R/T" not in text and "r/t" not in text.lower():
            insights.append(text)
    if delivery:
        slow = max(delivery, key=lambda x: x["avg"])
        insights.append(
            f"交付最慢项目 {slow['name']} 均值 {slow['avg']:.1f} 天（可计 {slow['counted']}/{slow['demands']} 条）。"
        )
    if health.get("whitelist_hit_pct") is not None:
        insights.append(
            f"本期 {health['whitelist_hit_pct']:.0f}% 需求在 QC 列命中白名单（源报告附录）。"
        )
    if not any("Gate-RDJ" in x or "分月" in x for x in insights):
        insights.append(
            "无完成月/迭代/Bug/修正研发字段；分月趋势需 Gate-RDJ 导出跑 P9 脚本。"
        )

    return {
        "label": "原始 338 行 · 工时清洗 329 行（Gate-AI 源报告）",
        "source": str(src.name),
        "kpi": kpi,
        "biz": biz,
        "delivery": delivery,
        "qc": qc,
        "insights": insights,
    }


def _rt_meegle(total: float, test: float) -> float | None:
    if test <= 0:
        return None
    return round((total - test) / test, 2)


def load_alpha_from_csv(csv_path: Path | None = None) -> dict:
    src = csv_path or MEEGLE_CSV
    rows, fields = load_csv(src)
    qc_col, _ = discover_qc_column(fields, rows)

    main_rows = [r for r in rows if row_bucket(r.get(K_TITLE, ""), r.get(K_COLLAB, "")) == "main"]
    branch_rows = [r for r in rows if row_bucket(r.get(K_TITLE, ""), r.get(K_COLLAB, "")) == "branch"]
    sm = summarize(main_rows, qc_col)
    sb = summarize(branch_rows, qc_col)
    sg = summarize(rows, qc_col)

    prio_counts: dict[str, int] = {}
    for r in rows:
        pl = prio_label(r.get(K_PRIO))
        prio_counts[pl] = prio_counts.get(pl, 0) + 1

    top = []
    for r in sorted(rows, key=lambda x: -fnum(x.get(K_TEST))):
        t = fnum(r.get(K_TEST))
        tt = fnum(r.get(K_TOTAL))
        sid = (r.get("storyID") or "").strip()
        title = r.get(
            "uiDataMap.1l5clgkicafc2.uiValue.nameWithComment.value", ""
        ) or "（无标题）"
        top.append({
            "id": sid,
            "title": title[:48] + ("…" if len(title) > 48 else ""),
            "prio": prio_label(r.get(K_PRIO)),
            "test_pd": t,
            "est_pd": tt,
            "rt": _rt_meegle(tt, t),
            "bucket": row_bucket(r.get(K_TITLE, ""), r.get(K_COLLAB, "")),
        })
    top = top[:15]

    g_rt = sg["weighted_rt"]
    insights = [
        f"共 {len(rows)} 条已完成需求；优先级 {', '.join(f'{k} {v} 条' for k, v in sorted(prio_counts.items()))}。",
        f"主站 {sm['n']} 条 · 测试 Σ {sm['test_sum']:.1f} pd · 总估 Σ {sm['total_sum']:.1f} pd · "
        f"加权 R/T {sm['weighted_rt']:.2f}（Meegle 口径）"
        if sm["weighted_rt"] is not None
        else f"主站 {sm['n']} 条",
        f"分站 {sb['n']} 条 · 测试 Σ {sb['test_sum']:.1f} pd · 总估 Σ {sb['total_sum']:.1f} pd · "
        f"加权 R/T {sb['weighted_rt']:.2f}"
        if sb["weighted_rt"] is not None
        else f"分站 {sb['n']} 条",
        f"全局加权 R/T {g_rt:.2f} = (Σ总估−Σ测)÷Σ测；与 Gate-RDJ 修正研发÷测不可硬比绝对值。",
        f"单条 R/T 最高：{top[0]['title']}（{top[0]['rt']:.2f}）" if top and top[0].get("rt") else "",
    ]
    insights = [x for x in insights if x]

    return {
        "label": f"Meegle 视图 8bbOlLnNU · {src.name}",
        "csv": str(src),
        "kpi": {
            "需求数": sg["n"],
            "测试节点Σ": round(sg["test_sum"], 1),
            "总估分Σ": round(sg["total_sum"], 1),
            "加权R/T": round(g_rt, 2) if g_rt is not None else "—",
            "主站条数": sm["n"],
            "分站条数": sb["n"],
        },
        "main": sm,
        "branch": sb,
        "global": sg,
        "split": [
            ("主站（WEB3/Alpha）", sm["n"], round(sm["test_sum"], 1), sm["weighted_rt"]),
            ("分站 / 跨线协作", sb["n"], round(sb["test_sum"], 1), sb["weighted_rt"]),
        ],
        "priority": [(k, v) for k, v in sorted(prio_counts.items())],
        "top_test": top,
        "insights": insights,
    }


def ai_biz_table_rows(ai: dict) -> list[list]:
    return [
        [
            b["name"],
            b["demands"],
            f"{b['est']:g}",
            f"{b['test_alloc']:g}",
            f"{b['test_pct']:g}" if b.get("test_pct") is not None else "—",
        ]
        for b in ai["biz"]
    ]


def alpha_brief_panels(al: dict) -> str:
    sm, sb = al["main"], al["branch"]

    def panel(title: str, s: dict, cls: str) -> str:
        rt = f"{s['weighted_rt']:.2f}" if s["weighted_rt"] is not None else "—"
        return f"""<div class="{cls}">
<div class="panel-title">{escape(title)}（{s['n']} 条）</div>
<ul class="panel-ul">
<li>测试节点人日合计 <strong>{s['test_sum']:.1f}</strong> pd；总估分合计 <strong>{s['total_sum']:.1f}</strong> pd。</li>
<li>加权 R/T（Meegle）= <strong>{rt}</strong>。</li>
</ul></div>"""

    return f"""<div class="brief-grid">
{panel("主站", sm, "panel-blue")}
{panel("分站 / 跨线协作", sb, "panel-amber")}
</div>"""


def alpha_top_table_rows(al: dict) -> list[list]:
    return [
        [
            r["id"], r["title"], r["prio"], r["bucket"],
            f"{r['test_pd']:g}", f"{r['est_pd']:g}",
            f"{r['rt']:g}" if r.get("rt") is not None else "—",
        ]
        for r in al["top_test"]
    ]
