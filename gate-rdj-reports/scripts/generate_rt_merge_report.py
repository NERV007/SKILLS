#!/usr/bin/env python3
"""从三份源 HTML 抽取 RT 数据，生成 Gate-RDJ-RT合并分析报告.html。

规则（与用户要求一致）：
- 仅使用源报告已有字段；不重算、不估算、不插值。
- 测试工时缺失或 ≤ TEST_FLOOR(0.05) → 不展示 R/T（显示 —）。
- 部门四源对照：某源样本数 = 0 → 该列 R/T 强制 —（即使源 HTML 有残留值）。
- 人员分布：测试不可算者归入「不可算」桶，不计入 R/T 分档。
"""

from __future__ import annotations

import html as html_module
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _paths import REPO_ROOT, SCRIPTS_DIR, TEMPLATES_DIR

ROOT = REPO_ROOT
OUT = ROOT / "Gate-RDJ-RT合并分析报告.html"
SRC_TIME = ROOT / "Gate-RDJ-时间维度-v4-业务线分析报告.html"
SRC_ITER = ROOT / "Gate-RDJ-迭代维度-skill-测试效能汇总报告.html"
SRC_QC = ROOT / "QC人员名单-主站分站合并需求与RT.html"
ECHARTS = "vendor/echarts-5.4.3.min.js"

TEST_FLOOR = 0.05

# 与全景「原始数据」Tab module 列对齐
SOURCE_TO_MODULE = {
    "主站·Gate-RDJ": "主站·Gate-RDJ",
    "分站·全景": "分站·产研",
    "AI·Gate-AI项目集": "AI·Gate-AI",
}


def source_to_module(source: str) -> str:
    s = (source or "").strip()
    if s in SOURCE_TO_MODULE:
        return SOURCE_TO_MODULE[s]
    if s.startswith("Alpha"):
        return "Alpha·Meegle"
    return s or "—"


def _strip(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    s = html_module.unescape(s).strip()
    return s.replace("天", "天").strip()


def _pf(s: str) -> Optional[float]:
    if not s or s in ("—", "-", "None", "nan"):
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def rt_or_none(test: Optional[float], rd: Optional[float], rt_src: Optional[float] = None) -> Optional[float]:
    """有测试分母且 > floor 才返回 R/T；否则 None。"""
    if test is None or test <= TEST_FLOOR:
        return None
    if rt_src is not None:
        return rt_src
    if rd is None:
        return None
    return round(rd / test, 2)


def parse_time_global(html: str) -> Dict[str, Any]:
    m = re.search(r"<h3>整体 R/T</h3><div class=\"value\">([\d.]+)</div>", html)
    overall = float(m.group(1)) if m else None

    m2 = re.search(
        r"分月统计（全局）</div>.*?<tbody>(.*?)</tbody>",
        html,
        re.S,
    )
    months: List[str] = []
    rt_monthly: List[Optional[float]] = []
    test_monthly: List[Optional[float]] = []
    if m2:
        for tr in re.findall(r"<tr>(.*?)</tr>", m2.group(1), re.S):
            tds = [_strip(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if len(tds) < 7:
                continue
            months.append(tds[0])
            test = _pf(tds[3])
            rd = _pf(tds[5])
            rt_src = _pf(tds[6])
            rt_monthly.append(rt_or_none(test, rd, rt_src))
            test_monthly.append(test)
    return {"overall": overall, "months": months, "rt_monthly": rt_monthly, "test_monthly": test_monthly}


def parse_time_biz(html: str) -> List[Dict[str, Any]]:
    m = re.search(
        r"各业务线测试效能汇总</div>.*?<tbody>(.*?)</tbody>",
        html,
        re.S,
    )
    rows: List[Dict[str, Any]] = []
    if not m:
        return rows
    for tr in re.findall(r"<tr>(.*?)</tr>", m.group(1), re.S):
        tds = [_strip(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(tds) < 9:
            continue
        test = _pf(tds[3])
        rd = _pf(tds[4])
        rt_src = _pf(tds[5])
        rows.append(
            {
                "name": tds[0],
                "demands": int(_pf(tds[1]) or 0),
                "test": test,
                "rd": rd,
                "rt": rt_or_none(test, rd, rt_src),
                "avg_bug": _pf(tds[7]),
                "cycle": tds[6],
            }
        )
    return rows


def parse_time_teams(html: str) -> Dict[str, int]:
    m = re.search(r"团队汇总</div>.*?<tbody>(.*?)</tbody>", html, re.S)
    qc_map: Dict[str, int] = {}
    if not m:
        return qc_map
    for tr in re.findall(r"<tr>(.*?)</tr>", m.group(1), re.S):
        tds = [_strip(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(tds) < 3:
            continue
        qc_map[tds[1]] = int(_pf(tds[2]) or 0)
    return qc_map


def parse_iter_value_types(html: str) -> List[Dict[str, Any]]:
    m = re.search(r"按需求价值类型汇总（全局）</div>.*?<tbody>(.*?)</tbody>", html, re.S)
    rows: List[Dict[str, Any]] = []
    if not m:
        return rows
    for tr in re.findall(r"<tr>(.*?)</tr>", m.group(1), re.S):
        tds = [_strip(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(tds) < 10:
            continue
        test = _pf(tds[3])
        rd = _pf(tds[6])
        rt_src = _pf(tds[8])
        rows.append(
            {
                "name": tds[0],
                "cat": tds[1],
                "demands": int(_pf(tds[2]) or 0),
                "test": test,
                "rd": rd,
                "rt": rt_or_none(test, rd, rt_src),
            }
        )
    return rows


def parse_iter_rt_buckets(html: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """返回 (有效分档列表, 不可算人员列表)。"""
    m = re.search(r"R/T 值分布汇总（按范围和业务线）.*?<tbody>(.*?)</tbody>", html, re.S)
    buckets: List[Dict[str, Any]] = []
    invalid: List[Dict[str, Any]] = []
    if not m:
        return buckets, invalid

    bin_defs = [
        ("R/T<1", "R/T < 1", "#dc2626", "#fef2f2"),
        ("1~1.5", "1 ≤ R/T < 1.5", "#f59e0b", "#fffbeb"),
        ("1.5~2", "1.5 ≤ R/T < 2", "#10b981", "#f0fdf4"),
        ("2~2.5", "2 ≤ R/T < 2.5", "#0ea5e9", "#eff6ff"),
        ("≥2.5", "R/T ≥ 2.5", "#6366f1", "#eef2ff"),
    ]
    people: List[Tuple[str, float]] = []
    row_keys = ["R/T<1", "1~1.5", "1.5~2", "2~2.5", "≥2.5"]
    src_counts: Dict[str, int] = {}
    row_idx = 0
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(tds) < 4:
            continue
        cnt = int(_pf(_strip(tds[1])) or 0)
        if row_idx < len(row_keys):
            src_counts[row_keys[row_idx]] = cnt
            row_idx += 1
        detail_html = tds[3]
        for part in re.split(r"<br\s*/?>", detail_html):
            part = _strip(part)
            pm = re.match(r"([^()]+)\(([\d.]+)\)\s*$", part)
            if pm:
                people.append((pm.group(1).strip(), float(pm.group(2))))

    valid_people: List[Tuple[str, float]] = []
    for name, rt in people:
        if rt <= 0:
            invalid.append({"name": name, "reason": "研发或测试工时缺失（源报告 R/T=0）"})
        else:
            valid_people.append((name, rt))

    bucket_map: Dict[str, List[Tuple[str, float]]] = {k: [] for k, _, _, _ in bin_defs}
    for name, rt in valid_people:
        if rt < 1:
            bucket_map["R/T<1"].append((name, rt))
        elif rt < 1.5:
            bucket_map["1~1.5"].append((name, rt))
        elif rt < 2:
            bucket_map["1.5~2"].append((name, rt))
        elif rt < 2.5:
            bucket_map["2~2.5"].append((name, rt))
        else:
            bucket_map["≥2.5"].append((name, rt))

    total_src = sum(src_counts.values()) or 1
    for key, title, color, bg in bin_defs:
        items = bucket_map[key]
        count = src_counts.get(key, len(items))
        names = "、".join(f"{n}({rt:.2f})" for n, rt in sorted(items, key=lambda x: x[1]))
        if count > len(items):
            suffix = f"（源表明细截断，该档共 {count} 人）"
            names = (names + " … " + suffix) if names else suffix
        buckets.append(
            {
                "key": key,
                "title": title,
                "color": color,
                "bg": bg,
                "count": count,
                "pct": round(count / total_src * 100),
                "names": names or "—",
            }
        )
    return buckets, invalid


def _parse_samples_rt(
    samp: str, rt_vals: List[str]
) -> Tuple[List[int], List[Optional[float]]]:
    parts = samp.split("/")
    ns = [int(x) if x.isdigit() else 0 for x in parts[:4]] + [0] * (4 - len(parts))
    ns = ns[:4]
    rts: List[Optional[float]] = []
    for val, n in zip(rt_vals, ns):
        rts.append(None if n <= 0 else _pf(val))
    return ns, rts


def _summary_label(summary_html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", summary_html)
    text = html_module.unescape(text).strip()
    text = re.split(r"\s*·\s*", text)[0].strip()
    return text


def _link_title(td_html: str) -> Tuple[Optional[str], str]:
    m = re.search(r"href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", td_html, re.S | re.I)
    if m:
        return m.group(1), _strip(m.group(2))
    return None, _strip(td_html)


def _parse_finish_month(meta: str) -> str:
    m = re.search(r"完成\s*(\d{4}-\d{2})", meta or "")
    return m.group(1) if m else "未标注月"


def _parse_finish_date(meta: str) -> Optional[str]:
    m = re.search(r"完成\s*(\d{4}-\d{2}-\d{2})", meta or "")
    return m.group(1) if m else None


def _iter_details_blocks(html: str, class_name: str):
    """匹配嵌套 details，按外层 class 切分。"""
    marker = f"<details class='{class_name}'"
    pos = 0
    while True:
        start = html.find(marker, pos)
        if start < 0:
            return
        depth = 0
        i = start
        while i < len(html):
            if html.startswith("<details", i):
                depth += 1
                i += 8
                continue
            if html.startswith("</details>", i):
                depth -= 1
                i += 10
                if depth == 0:
                    yield html[start:i]
                    pos = i
                    break
                continue
            i += 1
        else:
            return


def parse_qc_dept_monthly(html: str) -> List[Dict[str, Any]]:
    """（一-B）按完成月 · 部门汇总 — 直抽各月部门表。"""
    m = re.search(
        r"（一-B）按完成月 · 部门汇总</h2>(.*?)(?:<div class='section'><h2>（二）|$)",
        html,
        re.S,
    )
    if not m:
        return []
    block = m.group(1)
    out: List[Dict[str, Any]] = []
    for fold in re.finditer(
        r"<details class='month-fold'[^>]*>.*?<summary>(.*?)</summary>(.*?)</details>",
        block,
        re.S,
    ):
        summary = _strip(fold.group(1))
        mm = re.match(r"(\d{4}-\d{2}|未标注月)", summary)
        if not mm:
            continue
        month = mm.group(1)
        tag_m = re.search(r"<span class='tag'>(\d+)\s*条", fold.group(1))
        total_records = int(tag_m.group(1)) if tag_m else None
        tbody_m = re.search(r"<tbody>(.*?)</tbody>", fold.group(2), re.S)
        rows: List[Dict[str, Any]] = []
        if tbody_m:
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tbody_m.group(1), re.S):
                tds = [_strip(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
                if len(tds) < 11 or "合计" in tds[0]:
                    continue
                samp = tds[10]
                _, rts = _parse_samples_rt(samp, tds[6:10])
                rows.append(
                    {
                        "dept": tds[0],
                        "dev": tds[1],
                        "qc": tds[2],
                        "dev_qc": tds[3],
                        "active_qc": tds[4],
                        "records": int(_pf(tds[5]) or 0),
                        "rt_main": rts[0],
                        "rt_station": rts[1],
                        "rt_ai": rts[2],
                        "rt_alpha": rts[3],
                        "samples": samp,
                    }
                )
        out.append({"month": month, "total_records": total_records, "rows": rows})
    return out


def parse_qc_demands(html: str) -> List[Dict[str, Any]]:
    """（二）部门 → 人员 → 需求明细 — 直抽行级数据。"""
    m = re.search(r"（二）按部门展开 · 人员明细</h2>(.*)", html, re.S)
    if not m:
        return []
    block = m.group(1)
    demands: List[Dict[str, Any]] = []
    for dept_html in _iter_details_blocks(block, "dept"):
        sm = re.search(r"<summary>(.*?)</summary>", dept_html, re.S)
        if not sm:
            continue
        dept = _summary_label(sm.group(1))
        inner = dept_html[sm.end() :]
        for person_html in _iter_details_blocks(inner, "person"):
            psm = re.search(r"<summary>(.*?)</summary>", person_html, re.S)
            if not psm:
                continue
            person = _summary_label(psm.group(1))
            tbody_m = re.search(r"<tbody>(.*?)</tbody>", person_html, re.S)
            if not tbody_m:
                continue
            for tr in re.findall(r"<tr>(.*?)</tr>", tbody_m.group(1), re.S):
                tds_raw = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
                if len(tds_raw) < 7:
                    continue
                source = _strip(tds_raw[0])
                url, title = _link_title(tds_raw[1])
                rt_src = _pf(_strip(tds_raw[2]))
                rd = _pf(_strip(tds_raw[4]))
                test = _pf(_strip(tds_raw[5]))
                meta = _strip(tds_raw[6])
                rt = rt_or_none(test, rd, rt_src)
                finish_date = _parse_finish_date(meta)
                demands.append(
                    {
                        "dept": dept,
                        "person": person,
                        "month": _parse_finish_month(meta),
                        "finish_date": finish_date,
                        "source": source,
                        "module": source_to_module(source),
                        "title": title[:120],
                        "url": url,
                        "rt": rt,
                        "rd": rd,
                        "test": test,
                        "meta": meta[:200],
                    }
                )
    return demands


def build_person_monthly(demands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """人员×月汇总：条数、工时合计；R/T 仅当测试合计 > floor 时用行级工时比（非插值）。"""
    agg: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for d in demands:
        key = (d["dept"], d["person"], d["month"])
        if key not in agg:
            agg[key] = {
                "dept": d["dept"],
                "person": d["person"],
                "month": d["month"],
                "count": 0,
                "rd_sum": 0.0,
                "test_sum": 0.0,
                "rt_rows": 0,
            }
        a = agg[key]
        a["count"] += 1
        if d.get("rd") is not None:
            a["rd_sum"] += d["rd"]
        if d.get("test") is not None:
            a["test_sum"] += d["test"]
        if d.get("rt") is not None:
            a["rt_rows"] += 1
    rows: List[Dict[str, Any]] = []
    for a in agg.values():
        rt = None
        if a["test_sum"] > TEST_FLOOR and a["rd_sum"] > 0:
            rt = round(a["rd_sum"] / a["test_sum"], 2)
        rows.append(
            {
                "dept": a["dept"],
                "person": a["person"],
                "month": a["month"],
                "count": a["count"],
                "rd_sum": round(a["rd_sum"], 2) if a["rd_sum"] else None,
                "test_sum": round(a["test_sum"], 2) if a["test_sum"] else None,
                "rt": rt,
                "rt_rows": a["rt_rows"],
            }
        )
    rows.sort(key=lambda x: (x["month"], x["dept"], x["person"]))
    return rows


def parse_qc_dept(html: str) -> List[Dict[str, Any]]:
    m = re.search(r"（一）部门汇总</h2>.*?<tbody>(.*?)</tbody>", html, re.S)
    rows: List[Dict[str, Any]] = []
    if not m:
        return rows
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.S):
        tds_raw = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(tds_raw) < 11:
            continue
        tds = [_strip(x) for x in tds_raw]
        if "总和" in tds[0]:
            continue
        samp = tds[10]
        _, rts = _parse_samples_rt(samp, tds[6:10])
        rows.append(
            {
                "dept": tds[0],
                "dev": tds[1],
                "qc": tds[2],
                "dev_qc": tds[3],
                "rt_main": rts[0],
                "rt_station": rts[1],
                "rt_ai": rts[2],
                "rt_alpha": rts[3],
                "samples": samp,
            }
        )
    return rows


def fmt_rt(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.2f}"


def rt_color(v: Optional[float]) -> str:
    if v is None:
        return "#cbd5e1"
    if v < 2:
        return "#16a34a"
    if v < 3:
        return "#0369a1"
    return "#dc2626"


def pill_class(v: Optional[float]) -> str:
    if v is None:
        return ""
    if v < 2:
        return "pill-low"
    if v < 3:
        return "pill-mid"
    return "pill-high"


TPL = SCRIPTS_DIR / "templates" / "rt_merge_report.html"
if not TPL.is_file():
    TPL = TEMPLATES_DIR / "rt_merge_report.html"


def build_html(data: Dict[str, Any]) -> str:
    js = json.dumps(data, ensure_ascii=False)
    tpl = TPL.read_text(encoding="utf-8")
    return (
        tpl.replace("__DATA__", js)
        .replace("__TEST_FLOOR__", str(TEST_FLOOR))
        .replace("__ECHARTS__", ECHARTS)
    )


def build_insights(
    overall: Optional[float],
    biz: List[Dict[str, Any]],
    buckets: List[Dict[str, Any]],
    invalid: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    valid_biz = [b for b in biz if b["rt"] is not None]
    hi = sorted(valid_biz, key=lambda x: x["rt"] or 0, reverse=True)[:3]
    lo = sorted(valid_biz, key=lambda x: x["rt"] or 999)[:3]
    ge25 = next((b for b in buckets if b["key"] == "≥2.5"), None)
    total_p = sum(b["count"] for b in buckets)
    return [
        {
            "title": "整体与结构",
            "items": [
                f"团队整体 R/T（时间维）= <b>{fmt_rt(overall)}</b>，仅统计源报告已汇总口径。",
                f"可算业务线 {len(valid_biz)}/{len(biz)} 条；跨度 "
                + (f"{lo[0]['rt']:.2f} ~ {hi[0]['rt']:.2f}" if lo and hi else "—"),
                f"人员样本 {sum(b['count'] for b in buckets)} 人（源表），其中 R/T=0 不可算 {len(invalid)} 人："
                + "、".join(x["name"] for x in invalid)
                if invalid
                else "无 R/T=0 不可算人员",
            ],
        },
        {
            "title": "高 R/T 观察（测试分母有效）",
            "items": [
                "、".join(f"{b['name']}({b['rt']:.2f})" for b in hi if b["rt"] is not None) or "—",
                "需结合 Bug 与需求复杂度判断是高效还是测试投入偏薄，不做估算补全。",
            ],
        },
        {
            "title": "低 R/T + 高 Bug",
            "items": [
                "、".join(
                    f"{b['name']}({b['rt']:.2f}/{b['avg_bug']})"
                    for b in valid_biz
                    if b["rt"] is not None and b["rt"] < 2 and (b["avg_bug"] or 0) >= 6
                )[:4]
                or "—",
                "测试投入重但缺陷高 → 查测试有效性，而非简单加人。",
            ],
        },
        {
            "title": "数据纪律",
            "items": [
                f"测试工时 ≤ {TEST_FLOOR} 人天 → 不展示 R/T。",
                "四源样本 = 0 → 对应列 R/T 为 —，禁止跨源硬比。",
                "本页所有数值均从源 HTML 直抽，更新源报告后请重跑本脚本。",
            ],
        },
    ]


def main() -> None:
    time_html = SRC_TIME.read_text(encoding="utf-8")
    iter_html = SRC_ITER.read_text(encoding="utf-8")
    qc_html = SRC_QC.read_text(encoding="utf-8")

    global_data = parse_time_global(time_html)
    biz = parse_time_biz(time_html)
    qc_map = parse_time_teams(time_html)
    values = parse_iter_value_types(iter_html)
    buckets, invalid = parse_iter_rt_buckets(iter_html)
    dept = parse_qc_dept(qc_html)
    dept_monthly = parse_qc_dept_monthly(qc_html)
    demands = parse_qc_demands(qc_html)
    person_monthly = build_person_monthly(demands)

    filter_meta = {
        "modules": sorted({d["module"] for d in demands}),
        "depts": sorted({d["dept"] for d in demands}),
        "people": sorted({d["person"] for d in demands}),
    }

    payload = {
        "global": global_data,
        "biz": biz,
        "qc_map": qc_map,
        "values": values,
        "buckets": buckets,
        "invalid": invalid,
        "dept": dept,
        "dept_monthly": dept_monthly,
        "person_monthly": person_monthly,
        "demands": demands,
        "filter_meta": filter_meta,
        "insights": build_insights(global_data["overall"], biz, buckets, invalid),
    }

    OUT.write_text(build_html(payload), encoding="utf-8")
    print(f"Wrote {OUT}")
    print(
        f"  biz with RT: {sum(1 for b in biz if b['rt'] is not None)}/{len(biz)}"
        f"  invalid people: {len(invalid)}"
        f"  demands: {len(demands)}"
        f"  person_monthly: {len(person_monthly)}"
        f"  dept_monthly months: {len(dept_monthly)}"
    )


if __name__ == "__main__":
    main()
