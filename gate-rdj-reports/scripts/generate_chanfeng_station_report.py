#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从「全景视图导出-产研分站」Excel/CSV 生成分站需求分析报告（HTML）。
版式与叙事结构对齐主站「Gate-RDJ-QC人员-P9人效环比与建议报告」：总分总、目录、执行摘要卡、蓝/琥珀双栏、分月事实表、收口动作与折叠指标说明；指标旁标注与 P9「同名不同义」。
用法:
  python3 scripts/generate_chanfeng_station_report.py
  python3 scripts/generate_chanfeng_station_report.py --xlsx /path/to/file.xlsx
默认: 优先读项目根 全景视图导出-产研分站.csv；若不存在则读 ~/Downloads/全景视图导出-产研分站.xlsx 并写出 CSV。
刷新源数据时显式传入: --xlsx /path/to/file.xlsx
"""

from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from _paths import REPO_ROOT

ROOT = Path(REPO_ROOT)
DEFAULT_CSV = ROOT / "全景视图导出-产研分站.csv"
DEFAULT_XLSX_DL = Path.home() / "Downloads" / "全景视图导出-产研分站.xlsx"
OUT_HTML = ROOT / "产研分站-全景需求分析报告.html"

COL_SCHEDULE_TOTAL = "需求排期-总估分"
COL_NODE = "需求排期-节点"
COL_TEST = "测试总估分（去除RD去除APPQC）"
COL_CREATED = "创建时间"
COL_LINE = "业务线"
COL_PRIORITY = "优先级"
COL_CREATOR = "创建人"
COL_QC = "QC"
COL_TITLE = "标题"
COL_LINK = "工作项链接"

# 产研分站导出中 QC 多为短名（如 Dagger-QC）；下列前缀用于匹配用户给出的「-LDT」展示名
LDT_QC_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Dagger-QC-LDT", ("dagger-qc",)),
    ("Elisa-QC-LDT(埃莉萨)", ("elisa-qc",)),
    ("Gina-QC-LDT", ("gina-qc",)),
    ("Viola-QC-LDT（维奥拉）", ("viola-qc",)),
    ("laoshuang-QC-LDT", ("laoshuang-qc",)),
)


def _norm_qc_part(part: str) -> str:
    s = str(part).strip().lower().replace(" ", "")
    s = re.sub(r"[（(][^）)]*[）)]", "", s)
    return s


def _qc_part_matches_prefixes(part: str, prefixes: tuple[str, ...]) -> bool:
    t = _norm_qc_part(part)
    for pref in prefixes:
        if t == pref or t.startswith(pref + "-"):
            return True
    return False


def _qc_cell_matches_group(qc_val: object, prefixes: tuple[str, ...]) -> bool:
    if qc_val is None or (isinstance(qc_val, float) and str(qc_val) == "nan"):
        return False
    for part in str(qc_val).split("|"):
        if not str(part).strip():
            continue
        if _qc_part_matches_prefixes(part, prefixes):
            return True
    return False


def _qc_cell_matches_any_ldt(qc_val: object) -> bool:
    for _, prefs in LDT_QC_GROUPS:
        if _qc_cell_matches_group(qc_val, prefs):
            return True
    return False


def _qc_token_is_ldt_member(part: str) -> bool:
    return any(_qc_part_matches_prefixes(part, prefs) for _, prefs in LDT_QC_GROUPS)


def ldt_person_expand_id(label: str) -> str:
    """稳定 id：与 P9 `qc-dem-*` 同构，供展开行 aria-controls。"""
    return "ldt-dem-" + hashlib.sha256(label.encode("utf-8")).hexdigest()[:18]


def build_ldt_qc_panel(df: "object", n_all: int, global_ratio: float | None) -> dict | None:
    """五人 LDT QC 子集：共现、分人、分月、业务线；与全量对比。"""
    import pandas as pd

    if COL_QC not in df.columns:
        return None
    mask = df[COL_QC].map(_qc_cell_matches_any_ldt)
    dlt = df.loc[mask].copy()
    n = int(len(dlt))
    if n == 0:
        return {"n": 0, "active": False, "brief": ["本导出 QC 列中未匹配到上述五人前缀（请核对系统内别名）。"]}

    sched_sum = float(dlt["_schedule_days"].sum(skipna=True))
    test_sum = float(dlt["_test"].sum())
    ratio = (test_sum / sched_sum * 100.0) if sched_sum > 0 else None

    month_vc = dlt.loc[dlt["_created"].notna(), "_month"].value_counts().sort_index()
    line_disp = dlt[COL_LINE].fillna("(业务线未填)") if COL_LINE in dlt.columns else pd.Series(["(无列)"] * n)
    line_vc = line_disp.value_counts().head(12)
    pri_vc = dlt[COL_PRIORITY].value_counts() if COL_PRIORITY in dlt.columns else pd.Series(dtype=int)

    person_rows: list[dict] = []
    for label, prefs in LDT_QC_GROUPS:
        sub = dlt[dlt[COL_QC].map(lambda q, pr=prefs: _qc_cell_matches_group(q, pr))]
        pn = int(len(sub))
        psched = float(sub["_schedule_days"].sum(skipna=True))
        ptest = 0.0
        ratios: list[float] = []
        demand_rows: list[dict] = []
        expand_id = ldt_person_expand_id(label)

        for _, r in sub.iterrows():
            parts = [p.strip() for p in str(r[COL_QC]).split("|") if p.strip()]
            if not parts:
                continue
            n_part = len(parts)
            t_full = float(r["_test"])
            share = t_full / n_part
            ptest += share
            sd = r["_schedule_days"]
            if pd.notna(sd) and float(sd) > 0:
                ratios.append(100.0 * t_full / float(sd))

            ratio_line: float | None = None
            if pd.notna(sd) and float(sd) > 0:
                ratio_line = round(100.0 * t_full / float(sd), 2)
            rt_one: float | None = None
            if t_full > 0 and pd.notna(sd) and float(sd) > 0:
                rt_one = round(float(sd) / t_full, 2)

            mo = str(r.get("_month", "") or "").strip()
            if mo and len(mo) >= 7:
                mo = mo[:7]
            else:
                mo = "—"

            tit = str(r.get(COL_TITLE, "") or "")[:200]
            lk = str(r.get(COL_LINK, "") or "").strip()
            lr = r.get(COL_LINE, "")
            if pd.isna(lr) or str(lr).strip().lower() == "nan":
                lin = "—"
            else:
                lin = str(lr).strip() or "—"
            pr_raw = r.get(COL_PRIORITY, "")
            if pd.isna(pr_raw) or str(pr_raw).strip().lower() == "nan":
                pr = "—"
            else:
                pr = str(pr_raw).strip() or "—"

            demand_rows.append(
                {
                    "month": mo,
                    "title": tit,
                    "link": lk,
                    "test_share": round(share, 4),
                    "ratio_pct": ratio_line,
                    "rt": rt_one,
                    "line": lin[:80],
                    "pri": pr[:24],
                }
            )

        demand_rows.sort(key=lambda x: (-float(x["test_share"]), str(x["month"]), str(x["title"])))

        avg_ratio = round(sum(ratios) / len(ratios), 2) if ratios else None
        person_rows.append(
            {
                "label": label,
                "expand_id": expand_id,
                "n": pn,
                "sched_sum": round(psched, 1),
                "test_share": round(ptest, 2),
                "avg_test_per_row": round(ptest / pn, 3) if pn else 0.0,
                "avg_ratio_pct": avg_ratio,
                "demand_rows": demand_rows,
            }
        )

    co: defaultdict[str, int] = defaultdict(int)
    for _, r in dlt.iterrows():
        for part in str(r[COL_QC]).split("|"):
            p = part.strip()
            if not p or _qc_token_is_ldt_member(p):
                continue
            key = _norm_qc_part(p) or p
            co[key] += 1
    co_sorted = sorted(co.items(), key=lambda x: -x[1])[:15]
    coqc_bar = {"categories": [c[0] for c in co_sorted][::-1], "values": [c[1] for c in co_sorted][::-1]}

    brief: list[str] = [
        f"五人在本导出中共出现在「{n}」条需求上，约占全量「{round(100.0 * n / max(n_all, 1), 1)}%」。",
        f"子集排期人天合计「{round(sched_sum, 1)}」，测试估分合计「{round(test_sum, 1)}」；"
        + (
            f"子集测试/排期%约「{round(ratio, 2)}%」。"
            if ratio is not None
            else "子集排期合计为 0，无法算测试/排期%。"
        )
        + (
            f" 同期全站该口径约「{round(global_ratio, 2)}%」。"
            if global_ratio is not None and ratio is not None
            else ""
        ),
    ]
    if co_sorted:
        top3 = "、".join([f"{k}（{v}）" for k, v in co_sorted[:3]])
        brief.append(f"与小组共现最多的非本组 QC（按需求条数计）为：{top3}。")

    detail_rows: list[dict] = []
    top_idx = dlt["_test"].nlargest(min(35, n)).index
    for i in top_idx:
        row = dlt.loc[i]
        detail_rows.append(
            {
                "title": str(row.get(COL_TITLE, ""))[:90],
                "month": str(row.get("_month", ""))[:7],
                "sched": None if pd.isna(row.get("_schedule_days")) else round(float(row["_schedule_days"]), 2),
                "test": float(row["_test"]),
                "qc": str(row.get(COL_QC, ""))[:80],
                "line": str(row.get(COL_LINE, "") or "-"),
                "pri": str(row.get(COL_PRIORITY, "") or "-"),
                "link": str(row.get(COL_LINK, "") or ""),
            }
        )

    return {
        "active": True,
        "n": n,
        "share_of_all_pct": round(100.0 * n / max(n_all, 1), 2),
        "sched_sum": round(sched_sum, 1),
        "test_sum": round(test_sum, 2),
        "ratio_pct": None if ratio is None else round(ratio, 2),
        "global_ratio_pct": None if global_ratio is None else round(global_ratio, 2),
        "person_rows": person_rows,
        "coqc_bar": coqc_bar,
        "month_bar": {"categories": month_vc.index.tolist(), "values": month_vc.astype(int).tolist()},
        "line_bar": {"categories": line_vc.index.tolist()[::-1], "values": line_vc.astype(int).tolist()[::-1]},
        "priority_pie": [{"name": str(k), "value": int(v)} for k, v in pri_vc.items()],
        "brief": brief,
        "detail_rows": detail_rows,
    }


def parse_schedule_days(raw: object) -> float | None:
    if raw is None or (isinstance(raw, float) and str(raw) == "nan"):
        return None
    s = str(raw).strip()
    if not s:
        return None
    m = re.search(r"([\d.]+)\s*天", s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def parse_module_count(raw: object) -> int | None:
    if raw is None or (isinstance(raw, float) and str(raw) == "nan"):
        return None
    m = re.search(r"(\d+)\s*个模块", str(raw))
    if not m:
        return None
    return int(m.group(1))


def node_bucket(raw: object) -> str:
    if raw is None or (isinstance(raw, float) and str(raw) == "nan"):
        return "(空)"
    s = str(raw)
    if s.startswith("需求设计与内审"):
        return "需求设计与内审"
    if s.startswith("需求排期"):
        return "需求排期"
    return "其他/未识别"


def qc_explode_test(df: "object", test_col: str, qc_col: str) -> "object":
    """多人 QC 时按人数均分测试估分后汇总到每人（避免重复满额计入多人）。"""
    import pandas as pd

    rows: list[dict] = []
    for _, r in df.iterrows():
        t = float(r[test_col]) if pd.notna(r[test_col]) else 0.0
        qv = r[qc_col]
        if pd.isna(qv) or str(qv).strip() == "":
            rows.append({"qc": "(未填QC)", "test": t})
            continue
        parts = [p.strip() for p in str(qv).split("|") if p.strip()]
        if not parts:
            rows.append({"qc": "-", "test": t})
            continue
        share = t / len(parts)
        for p in parts:
            rows.append({"qc": p, "test": share})
    return pd.DataFrame(rows)


def load_frame(xlsx: Path | None, csv_path: Path) -> "object":
    import pandas as pd

    if csv_path.exists():
        return pd.read_csv(csv_path, encoding="utf-8-sig")
    if xlsx and xlsx.exists():
        return pd.read_excel(xlsx, sheet_name=0)
    raise FileNotFoundError(f"未找到数据文件: {csv_path} 或 {xlsx}")


def build_payload(df: "object") -> tuple[dict, list[dict], list[dict], list[dict]]:
    """返回 (echarts_payload, appendix_test, appendix_sched, line_agg_rows)。"""
    import pandas as pd

    n = len(df)
    df = df.copy()
    df["_schedule_days"] = df[COL_SCHEDULE_TOTAL].map(parse_schedule_days) if COL_SCHEDULE_TOTAL in df.columns else None
    df["_created"] = pd.to_datetime(df[COL_CREATED], errors="coerce") if COL_CREATED in df.columns else pd.NaT
    df["_month"] = df["_created"].dt.strftime("%Y-%m")

    def week_start_str(ts: object) -> str | None:
        if pd.isna(ts):
            return None
        try:
            p = pd.Timestamp(ts).to_period("W")
            return p.start_time.strftime("%Y-%m-%d")
        except Exception:
            return None

    df["_week"] = df["_created"].map(week_start_str)
    df["_mods"] = df[COL_NODE].map(parse_module_count) if COL_NODE in df.columns else None
    df["_node_cat"] = df[COL_NODE].map(node_bucket) if COL_NODE in df.columns else "(无列)"

    line_display = df[COL_LINE].fillna("(业务线未填)") if COL_LINE in df.columns else pd.Series(["(无列)"] * n)
    month_counts = df.loc[df["_created"].notna(), "_month"].value_counts().sort_index()
    month_counts = month_counts[month_counts.index.notna()]
    week_counts = df["_week"].dropna().value_counts().sort_index()

    line_counts = line_display.value_counts()
    pri_counts = df[COL_PRIORITY].value_counts() if COL_PRIORITY in df.columns else pd.Series(dtype=int)

    creators = df[COL_CREATOR].value_counts().head(15) if COL_CREATOR in df.columns else pd.Series(dtype=int)

    qc_parts: list[str] = []
    if COL_QC in df.columns:
        for v in df[COL_QC].fillna("-"):
            parts = [p.strip() for p in str(v).split("|") if p.strip()]
            qc_parts.extend(parts if parts else ["-"])
    qc_series = pd.Series(qc_parts) if qc_parts else pd.Series(dtype=str)
    qc_counts = qc_series.value_counts().head(15)

    test_vals = pd.to_numeric(df[COL_TEST], errors="coerce").fillna(0) if COL_TEST in df.columns else pd.Series([0.0] * n)
    df["_test"] = test_vals

    def bucket_test(x: float) -> str:
        if x <= 0:
            return "0"
        if x <= 1:
            return "(0,1]"
        if x <= 3:
            return "(1,3]"
        return ">3"

    test_buckets = test_vals.map(bucket_test).value_counts()
    order_b = ["0", "(0,1]", "(1,3]", ">3"]
    test_buckets = test_buckets.reindex([b for b in order_b if b in test_buckets.index])

    sched = df["_schedule_days"].dropna()
    sched_sum = float(sched.sum()) if len(sched) else 0.0
    sched_mean = float(sched.mean()) if len(sched) else 0.0
    sched_median = float(sched.median()) if len(sched) else 0.0

    def bucket_sched(d: float) -> str:
        if d <= 2:
            return "≤2 天"
        if d <= 5:
            return "(2,5] 天"
        if d <= 10:
            return "(5,10] 天"
        return ">10 天"

    sched_bins = sched.map(bucket_sched).value_counts()
    sched_bin_order = ["≤2 天", "(2,5] 天", "(5,10] 天", ">10 天"]
    sched_bin_bar = {
        "categories": [b for b in sched_bin_order if b in sched_bins.index],
        "values": [int(sched_bins[b]) for b in sched_bin_order if b in sched_bins.index],
    }

    missing_line = int((df[COL_LINE].isna() | (df[COL_LINE].astype(str).str.strip() == "")).sum()) if COL_LINE in df.columns else 0
    missing_qc = int(df[COL_QC].isna().sum()) if COL_QC in df.columns else 0

    raw_sched = df[COL_SCHEDULE_TOTAL] if COL_SCHEDULE_TOTAL in df.columns else pd.Series([None] * n)
    parse_fail = int(
        ((raw_sched.notna()) & (raw_sched.astype(str).str.strip() != "") & (df["_schedule_days"].isna())).sum()
    )

    mods_s = df["_mods"].dropna()
    mods_mean = float(mods_s.mean()) if len(mods_s) else 0.0
    mods_median = float(mods_s.median()) if len(mods_s) else 0.0
    mods_vc = df["_mods"].value_counts().sort_index()
    mods_bar = {"categories": [str(int(x)) for x in mods_vc.index.tolist()], "values": mods_vc.astype(int).tolist()}

    node_vc = df["_node_cat"].value_counts()
    node_pie = [{"name": str(k), "value": int(v)} for k, v in node_vc.items()]

    # 按月 × 优先级堆叠
    sub_m = df[df["_created"].notna() & df["_month"].notna()]
    month_pri = (
        sub_m.groupby(["_month", COL_PRIORITY], observed=False).size().unstack(fill_value=0)
        if COL_PRIORITY in df.columns
        else None
    )
    pri_order = ["P0", "P1", "P2"]
    _pri_colors = {"P0": "#dc2626", "P1": "#2563eb", "P2": "#059669"}
    month_stack = {"categories": [], "series": []}
    if month_pri is not None:
        month_stack["categories"] = sorted(month_pri.index.tolist())
        for p in pri_order:
            if p in month_pri.columns:
                month_stack["series"].append(
                    {
                        "name": p,
                        "type": "bar",
                        "stack": "t",
                        "data": [int(month_pri.loc[m, p]) for m in month_stack["categories"]],
                        "itemStyle": {"color": _pri_colors.get(p, "#64748b")},
                    }
                )

    # 已填业务线 Top10 × 优先级热力（条数）
    filled = df[df[COL_LINE].notna() & (df[COL_LINE].astype(str).str.strip() != "")].copy()
    heat_data: list[list] = []
    heat_lines: list[str] = []
    if len(filled) and COL_PRIORITY in df.columns:
        vc_line = filled[COL_LINE].value_counts()
        if len(vc_line) <= 10:
            top_lines = vc_line.index.tolist()
            heat_lines = top_lines
            for i, line in enumerate(top_lines):
                sl = filled[filled[COL_LINE] == line]
                for j, p in enumerate(pri_order):
                    heat_data.append([j, i, int((sl[COL_PRIORITY] == p).sum())])
        else:
            top_lines = vc_line.head(10).index.tolist()
            heat_lines = top_lines + ["其他(已填)"]
            rest = filled[~filled[COL_LINE].isin(top_lines)]
            for i, line in enumerate(top_lines):
                sl = filled[filled[COL_LINE] == line]
                for j, p in enumerate(pri_order):
                    heat_data.append([j, i, int((sl[COL_PRIORITY] == p).sum())])
            i_other = len(top_lines)
            for j, p in enumerate(pri_order):
                heat_data.append([j, i_other, int((rest[COL_PRIORITY] == p).sum())])

    # 散点：排期人天 vs 测试估分
    sc = df[df["_schedule_days"].notna()].copy()
    scatter = [[float(sc.loc[i, "_schedule_days"]), float(sc.loc[i, "_test"])] for i in sc.index]

    # 创建人：排期合计、测试合计 Top10
    cr_sched = df.groupby(COL_CREATOR, dropna=False)["_schedule_days"].sum().sort_values(ascending=False).head(10)
    cr_test = df.groupby(COL_CREATOR, dropna=False)["_test"].sum().sort_values(ascending=False).head(10)
    creator_sched_bar = {"categories": cr_sched.index.astype(str).tolist()[::-1], "values": [round(float(x), 1) for x in cr_sched.tolist()[::-1]]}
    creator_test_bar = {"categories": cr_test.index.astype(str).tolist()[::-1], "values": [round(float(x), 1) for x in cr_test.tolist()[::-1]]}

    # QC 测试负荷（均分）
    qc_ldf = qc_explode_test(df, "_test", COL_QC) if COL_QC in df.columns else None
    qc_test_sum = qc_ldf.groupby("qc")["test"].sum().sort_values(ascending=False).head(12) if qc_ldf is not None else None
    qc_load_bar = (
        {"categories": qc_test_sum.index.tolist()[::-1], "values": [round(float(x), 2) for x in qc_test_sum.tolist()[::-1]]}
        if qc_test_sum is not None
        else {"categories": [], "values": []}
    )

    qc_scatter: list[dict] = []
    if qc_test_sum is not None and len(qc_test_sum) > 0:
        qc_ratio_by: defaultdict[str, list[float]] = defaultdict(list)
        if COL_QC in df.columns:
            for _, r in df.iterrows():
                d, t = r["_schedule_days"], r["_test"]
                if pd.isna(d) or float(d) <= 0:
                    continue
                parts = [p.strip() for p in str(r.get(COL_QC, "")).split("|") if p.strip()]
                if not parts:
                    continue
                pct = 100.0 * float(t) / float(d)
                for q in parts:
                    qc_ratio_by[q].append(pct)
        for qc, load in qc_test_sum.head(15).items():
            lst = qc_ratio_by.get(qc, [])
            yv = round(sum(lst) / len(lst), 2) if lst else 0.0
            qc_scatter.append({"name": qc, "value": [round(float(load), 2), yv]})

    sorted_months = sorted(month_counts.index.tolist())
    month_table_rows: list[dict] = []
    month_combo = {"categories": [], "counts": [], "sched_sums": [], "ratio_pcts": []}
    prev_ratio: float | None = None
    for m in sorted_months:
        gg = df[df["_month"] == m]
        cnt = len(gg)
        ssum = float(gg["_schedule_days"].sum(skipna=True))
        tsum = float(gg["_test"].sum())
        ratio = (tsum / ssum * 100.0) if ssum > 0 else None
        mom_pt = None
        mom_rel = None
        if ratio is not None and prev_ratio is not None and prev_ratio > 0:
            mom_pt = round(ratio - prev_ratio, 2)
            mom_rel = round((ratio - prev_ratio) / prev_ratio * 100.0, 1)
        if ratio is not None:
            prev_ratio = ratio
        month_table_rows.append(
            {
                "month": m,
                "n": cnt,
                "sched_sum": round(ssum, 1),
                "test_sum": round(tsum, 1),
                "ratio_pct": None if ratio is None else round(ratio, 2),
                "mom_pt": mom_pt,
                "mom_rel": mom_rel,
            }
        )
        month_combo["categories"].append(m)
        month_combo["counts"].append(cnt)
        month_combo["sched_sums"].append(round(ssum, 1))
        month_combo["ratio_pcts"].append(None if ratio is None else round(ratio, 2))

    closing_bullets = [
        "将「业务线」与父工作项或区域维对齐后，再与主站 P9 的团队/部门统计并表复盘。",
        "对「高排期×高测试估分」清单做需求级复盘（策略可与 P9「高 R/T×高测占」象限一致），不替代 Jira 门禁与个人绩效评价。",
        "下一轮环比前固定口径：创建月分桶、排期「共 X 天」解析、QC 多人均分规则保持一致。",
    ]

    # 业务线聚合（仅已填）
    line_agg_rows: list[dict] = []
    if len(filled):
        g = filled.groupby(COL_LINE, dropna=False)
        for line, gg in g:
            sd = gg["_schedule_days"]
            tt = gg["_test"]
            ssum = float(sd.sum()) if sd.notna().any() else 0.0
            tsum = float(tt.sum())
            cnt = len(gg)
            avs = float(sd.mean()) if sd.notna().any() else 0.0
            avt = float(tt.mean())
            ratio = (tsum / ssum * 100.0) if ssum > 0 else None
            line_agg_rows.append(
                {
                    "line": str(line),
                    "n": int(cnt),
                    "sched_sum": round(ssum, 1),
                    "test_sum": round(tsum, 1),
                    "avg_sched": round(avs, 2),
                    "avg_test": round(avt, 3),
                    "test_ratio_pct": None if ratio is None else round(ratio, 2),
                }
            )
        line_agg_rows.sort(key=lambda x: -x["n"])

    # R/T：排期/测试（仅测试>0 且排期>0）
    rt_mask = (df["_schedule_days"].notna()) & (df["_schedule_days"] > 0) & (df["_test"] > 0)
    rt_series = (df.loc[rt_mask, "_schedule_days"] / df.loc[rt_mask, "_test"]).astype(float)
    rt_mean = float(rt_series.mean()) if len(rt_series) else None
    rt_median = float(rt_series.median()) if len(rt_series) else None

    test_median = float(test_vals.median())
    test_sum = float(test_vals.sum())
    both = df["_schedule_days"].notna() & (df["_schedule_days"] > 0)
    test_share_rows = df[both]
    global_test_ratio = (
        float(test_share_rows["_test"].sum() / test_share_rows["_schedule_days"].sum() * 100.0)
        if len(test_share_rows) and float(test_share_rows["_schedule_days"].sum()) > 0
        else None
    )

    p0, p1, p2 = int(pri_counts.get("P0", 0)), int(pri_counts.get("P1", 0)), int(pri_counts.get("P2", 0))
    node_design = int(node_vc.get("需求设计与内审", 0))
    node_sched = int(node_vc.get("需求排期", 0))

    insights = [
        f"业务线未填 {missing_line} 条（{missing_line * 100.0 / max(n, 1):.1f}%），已填 {n - missing_line} 条；已填业务线中 MG 区域条数最多（见聚合表）。",
        f"优先级：P0={p0}、P1={p1}、P2={p2}；P2 在已填业务线中集中于少数线（热力图）。",
        f"「需求排期-节点」可归为：需求设计与内审 {node_design} 条（{node_design * 100.0 / max(n, 1):.1f}%）、需求排期 {node_sched} 条；排期模块数均值约 {mods_mean:.2f}、中位数 {mods_median:.0f}。",
        f"排期人天：合计 {round(sched_sum, 1)}，单条均值 {round(sched_mean, 2)}、中位数 {round(sched_median, 2)}；解析失败（有文案但无数值）{parse_fail} 条。",
        f"测试估分：合计 {round(test_sum, 1)} 人天，均值 {round(float(test_vals.mean()), 3)}、中位数 {test_median:.1f}；测试为 0 的条数 {int((test_vals <= 0).sum())}。",
        (
            f"在「排期>0 且测试>0」的 {len(rt_series)} 条上，排期/测试（近似 R/T）均值 {rt_mean:.2f}、中位数 {rt_median:.2f}。"
            if rt_mean is not None
            else "无同时满足排期>0 且测试>0 的样本，无法计算 R/T。"
        ),
        (
            f"全体有效排期条上，测试估分占排期人天比重约 {global_test_ratio:.2f}%（测试合计÷排期合计，口径为粗粒度投入结构）。"
            if global_test_ratio is not None
            else "无法计算全局测试/排期占比（排期合计为 0）。"
        ),
        "创建人、QC  workload 图：QC 侧对多人用「测试估分均分」拆到人头，便于对比相对负荷（非财务口径）。",
    ]

    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "n": n,
        "month_bar": {"categories": month_counts.index.tolist(), "values": month_counts.astype(int).tolist()},
        "week_bar": {"categories": week_counts.index.tolist(), "values": week_counts.astype(int).tolist()},
        "line_bar": {
            "categories": line_counts.index.tolist()[:20],
            "values": line_counts.astype(int).tolist()[:20],
        },
        "priority_pie": [{"name": str(k), "value": int(v)} for k, v in pri_counts.items()],
        "creator_bar": {"categories": creators.index.tolist()[::-1], "values": creators.astype(int).tolist()[::-1]},
        "qc_bar": {"categories": qc_counts.index.tolist()[::-1], "values": qc_counts.astype(int).tolist()[::-1]},
        "test_bucket_bar": {"categories": test_buckets.index.tolist(), "values": test_buckets.astype(int).tolist()},
        "schedule_bins": sched_bin_bar,
        "mods_bar": mods_bar,
        "node_pie": node_pie,
        "month_stack": month_stack,
        "heatmap": {"lines": heat_lines, "prios": pri_order, "data": heat_data},
        "scatter": scatter,
        "creator_sched_bar": creator_sched_bar,
        "creator_test_bar": creator_test_bar,
        "qc_load_bar": qc_load_bar,
        "qc_scatter": qc_scatter,
        "month_combo": month_combo,
        "month_table_rows": month_table_rows,
        "closing_bullets": closing_bullets,
        "insights": insights,
        "line_agg_rows": line_agg_rows[:25],
        "summary": {
            "schedule_sum": round(sched_sum, 1),
            "schedule_mean": round(sched_mean, 2),
            "schedule_median": round(sched_median, 2),
            "test_sum": round(test_sum, 1),
            "test_mean": round(float(test_vals.mean()), 3),
            "test_median": round(test_median, 2),
            "missing_line": missing_line,
            "missing_qc": missing_qc,
            "parse_fail": parse_fail,
            "mods_mean": round(mods_mean, 2),
            "mods_median": int(round(mods_median)) if len(mods_s) else 0,
            "filled_line_n": int(n - missing_line),
            "rt_mean": None if rt_mean is None else round(rt_mean, 2),
            "rt_median": None if rt_median is None else round(rt_median, 2),
            "rt_n": int(len(rt_series)),
            "global_test_ratio_pct": None if global_test_ratio is None else round(global_test_ratio, 2),
            "date_min": str(df["_created"].min())[:10] if pd.notna(df["_created"].min()) else "-",
            "date_max": str(df["_created"].max())[:10] if pd.notna(df["_created"].max()) else "-",
        },
        "ldt_qc_panel": build_ldt_qc_panel(df, n, global_test_ratio),
    }

    top_test_idx = test_vals.nlargest(min(20, n)).index
    appendix_test = []
    for i in top_test_idx:
        row = df.loc[i]
        appendix_test.append(
            {
                "title": str(row.get(COL_TITLE, ""))[:100],
                "test": float(test_vals.loc[i]),
                "sched": None if pd.isna(row.get("_schedule_days")) else round(float(row["_schedule_days"]), 2),
                "line": str(row.get(COL_LINE, "") or "-"),
                "pri": str(row.get(COL_PRIORITY, "") or "-"),
                "link": str(row.get(COL_LINK, "") or ""),
            }
        )

    sched_nonnull = df["_schedule_days"].dropna()
    top_sched_idx = sched_nonnull.nlargest(min(15, len(sched_nonnull))).index
    appendix_sched = []
    for i in top_sched_idx:
        row = df.loc[i]
        appendix_sched.append(
            {
                "title": str(row.get(COL_TITLE, ""))[:100],
                "sched": round(float(row["_schedule_days"]), 2),
                "test": float(test_vals.loc[i]),
                "line": str(row.get(COL_LINE, "") or "-"),
                "link": str(row.get(COL_LINK, "") or ""),
            }
        )

    return payload, appendix_test, appendix_sched, line_agg_rows


def build_html(
    payload: dict,
    appendix_test: list[dict],
    appendix_sched: list[dict],
    csv_name: str,
    from_xlsx: bool,
) -> str:
    data_json = json.dumps(payload, ensure_ascii=False)
    appendix_test_json = json.dumps(appendix_test, ensure_ascii=False)
    appendix_sched_json = json.dumps(appendix_sched, ensure_ascii=False)
    src_note = "已从源 Excel 同步导出同目录 CSV。" if from_xlsx else f"分析基于项目根 CSV：`{html_lib.escape(csv_name)}`。"

    ins_key = "".join(f"<li>{html_lib.escape(x)}</li>" for x in payload["insights"][:5])
    ins_risk = "".join(f"<li>{html_lib.escape(x)}</li>" for x in payload["insights"][5:])
    close_list = "".join(f"<li>{html_lib.escape(x)}</li>" for x in payload["closing_bullets"])
    month_keys_txt = " · ".join(payload.get("month_combo", {}).get("categories", []) or [])

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>产研分站 · 全景与投入结构（对齐 P9 读法）</title>
  <script src="vendor/echarts-5.4.3.min.js"></script>
  <script>window.echarts||document.write('\\x3cscript src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"\\x3e\\x3c/script\\x3e');window.echarts||document.write('\\x3cscript src="https://registry.npmmirror.com/echarts/5.4.3/files/dist/echarts.min.js"\\x3e\\x3c/script\\x3e');</script>
  <style>
    *{{margin:0;padding:0;box-sizing:border-box}}
    body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;background:#f1f5f9;color:#1e293b;line-height:1.6}}
    .container{{max-width:1400px;margin:0 auto;padding:20px 20px 48px}}
    h1{{text-align:center;color:#0c4a6e;margin-bottom:8px;font-size:22px;font-weight:800}}
    .subtitle{{text-align:center;color:#64748b;font-size:13px;margin:0 0 8px}}
    .toc{{font-size:13px;color:#475569;margin:0 0 18px;padding:14px 16px;background:linear-gradient(135deg,#f8fafc,#f1f5f9);border-radius:14px;border:1px solid #e2e8f0;box-shadow:0 2px 8px rgba(0,0,0,0.06)}}
    .lead{{color:#475569;font-size:13px;line-height:1.75;margin-bottom:6px}}
    .tag{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:6px;background:#e0f2fe;color:#0369a1;margin-right:6px}}
    .section{{background:#fff;padding:16px;border-radius:12px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,0.08)}}
    .section-title{{font-size:15px;font-weight:700;color:#0c4a6e;margin:0 0 12px;padding-bottom:8px;border-bottom:2px solid #e2e8f0}}
    .summary-cards{{display:grid;grid-template-columns:repeat(9,1fr);gap:10px;margin-bottom:16px}}
    @media(max-width:1200px){{.summary-cards{{grid-template-columns:repeat(3,1fr)}}}}
    @media(max-width:600px){{.summary-cards{{grid-template-columns:repeat(2,1fr)}}}}
    .card{{background:#fff;padding:14px 8px;border-radius:10px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.08);border:1px solid #e2e8f0;min-width:0}}
    .card h3{{font-size:11px;color:#64748b;margin-bottom:4px;font-weight:600;line-height:1.25}}
    .card .value{{font-size:18px;font-weight:700;color:#0c4a6e}}
    .card .value.test{{color:#0ea5e9}}
    .card .sub{{font-size:10px;color:#94a3b8;margin-top:4px}}
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
    .part-desc{{font-size:12px;color:#64748b;margin:-4px 0 10px;line-height:1.45}}
    .chart-row{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:10px}}
    @media(max-width:960px){{.chart-row{{grid-template-columns:1fr}}}}
    .chart-box{{background:#f8fafc;padding:12px;border-radius:10px;border:1px solid #e2e8f0;min-height:280px}}
    .chart-box.wide{{grid-column:1/-1;min-height:340px}}
    .chart-title{{font-size:13px;font-weight:600;color:#0c4a6e;margin-bottom:8px;text-align:center}}
    .chart{{width:100%;height:400px;margin-top:6px}}
    .chart.compact{{height:340px}}
    .chart-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:10px}}
    @media(max-width:960px){{.chart-grid{{grid-template-columns:1fr}}}}
    .table-wrap{{overflow:auto;margin-top:12px}}
    table.data-tbl{{width:100%;border-collapse:collapse;font-size:12px}}
    table.data-tbl th,table.data-tbl td{{padding:8px 10px;border-bottom:1px solid #e2e8f0}}
    table.data-tbl th:first-child,table.data-tbl td:first-child{{text-align:left}}
    table.data-tbl th{{background:#f8fafc;font-weight:600;color:#475569;text-align:center}}
    table.data-tbl td.num{{text-align:right;font-variant-numeric:tabular-nums}}
    .detail-table{{padding:0;margin-top:10px}}
    .note{{font-size:11px;color:#64748b;margin-top:8px;padding:8px;background:#f8fafc;border-radius:6px}}
    .footer{{text-align:center;padding:16px;color:#64748b;font-size:12px;margin-top:8px}}
    ul.glist{{margin:0;padding-left:1.15rem;color:#334155;font-size:13px;line-height:1.75}}
    ul.glist li{{margin:8px 0}}
    a{{color:#0369a1}}
    details.glossary > summary{{cursor:pointer;font-weight:700;color:#0c4a6e;font-size:14px;padding:8px 0}}
    .muted{{color:#94a3b8;font-size:12px}}
    table.data-tbl tbody tr.qc-summary-row:hover{{background:#f8fafc}}
    .qc-name-cell{{min-width:140px;vertical-align:middle}}
    button.qc-name-toggle{{background:none;border:none;padding:0;margin:0;font:inherit;cursor:pointer;color:#0369a1;font-weight:600;text-decoration:underline;text-align:left}}
    button.qc-name-toggle:hover{{color:#0c4a6e}}
    button.qc-name-toggle:focus-visible{{outline:2px solid #38bdf8;outline-offset:2px;border-radius:2px}}
    tr.qc-demand-expand-row td.qc-demand-expand-cell{{padding:0 10px 12px;background:#f8fafc;border-bottom:1px solid #e2e8f0;vertical-align:top}}
    tr.qc-summary-row:has(+ tr.qc-demand-expand-row:not([hidden])) td{{border-bottom:none}}
    tr.qc-summary-row:has(+ tr.qc-demand-expand-row:not([hidden])) .qc-name-toggle{{color:#0c4a6e}}
    .qc-demand-drawer{{padding:10px 12px 12px;border:1px solid #e2e8f0;border-radius:8px;background:#fff;margin:0 2px 2px;box-shadow:0 1px 2px rgba(0,0,0,0.04)}}
    .qc-demand-table-wrap{{overflow:auto;max-height:min(360px,55vh)}}
    table.qc-demand-mini{{width:100%;font-size:11px;border-collapse:collapse;margin:0}}
    table.qc-demand-mini th,table.qc-demand-mini td{{padding:6px 8px;border-bottom:1px solid #e2e8f0;text-align:center}}
    table.qc-demand-mini th:first-child,table.qc-demand-mini td:first-child{{text-align:left;white-space:nowrap}}
    table.qc-demand-mini th:nth-child(2),table.qc-demand-mini td:nth-child(2){{text-align:left}}
    table.qc-demand-mini th:nth-child(6),table.qc-demand-mini td:nth-child(6){{text-align:left}}
    table.qc-demand-mini th:nth-child(7),table.qc-demand-mini td:nth-child(7){{text-align:left;font-size:11px}}
    table.qc-demand-mini th{{background:#f1f5f9;color:#475569;font-weight:600}}
    table.qc-demand-mini tr:last-child td{{border-bottom:none}}
  </style>
</head>
<body>
  <div class="container">
    <h1>产研分站 · 全景与投入结构（对齐 P9 读法）</h1>
    <p class="subtitle">创建时间 {html_lib.escape(str(payload["summary"]["date_min"]))} ~ {html_lib.escape(str(payload["summary"]["date_max"]))} · 所属空间产研分站 · 生成 {html_lib.escape(payload["generated_at"])}</p>
    <p class="lead"><span class="tag">总</span>先读执行摘要与口径边界；<span class="tag">分</span>看分月事实、业务线、人力与测试结构；<span class="tag">总</span>末段收口动作。读法与版式参照 <a href="Gate-RDJ-QC人员-P9人效环比与建议报告.html">Gate-RDJ-QC人员-P9人效环比与建议报告</a>，<strong>指标含义以本节琥珀面板为准</strong>（同名不同义）。</p>

    <div class="section">
      <div class="section-title">执行摘要（总 · 对齐 P9 版式）</div>
      <div class="summary-cards">
        <div class="card"><h3>工作项数</h3><div class="value" id="c_n">-</div></div>
        <div class="card"><h3>排期人天合计</h3><div class="value" id="c_sched_sum">-</div><div class="sub">解析合计</div></div>
        <div class="card"><h3>测试估分合计</h3><div class="value test" id="c_test_sum">-</div><div class="sub">去除RD/APPQC</div></div>
        <div class="card"><h3>分站·测试/排期%</h3><div class="value test" id="c_gtr">-</div><div class="sub">≠P9测÷五阶段</div></div>
        <div class="card"><h3>排期中位/条</h3><div class="value" id="c_sched_med">-</div><div class="sub">人天</div></div>
        <div class="card"><h3>测试中位/条</h3><div class="value test" id="c_test_med">-</div><div class="sub">人天</div></div>
        <div class="card"><h3>分站·R/T中位</h3><div class="value" id="c_rt_med">-</div><div class="sub">排期÷测</div></div>
        <div class="card"><h3>业务线未填</h3><div class="value" id="c_miss_line">-</div><div class="sub">条</div></div>
        <div class="card"><h3>QC未填 / 解析失败</h3><div class="value" id="c_miss_qc">-</div><div class="sub">QC空 | 排期 <span id="c_parse_fail">0</span></div></div>
      </div>
      <div class="conclusion-box">
        <div class="conclusion-title">方向与成功标准（分站数据能回答的事）</div>
        <p class="brief-p">本页在<strong>全景导出字段</strong>约束下回答：① 创建节奏与分月<strong>投入结构</strong>（条数、排期、测试估分、分站口径测试/排期%）；② 业务线与优先级的<strong>交叉分布</strong>是否过度集中；③ QC/创建人视角的<strong>负荷与「单条测占排期」水平</strong>。成功标准不是单一数值高低，而是「结构可解释 + 口径可复测」；与主站 P9 并读时务必使用下栏<strong>同名不同义</strong>对照。</p>
      </div>
      <div class="grid-2">
        <div class="panel-blue">
          <div class="panel-title">关键观察（数据驱动）</div>
          <ul class="brief-ul">{ins_key}</ul>
        </div>
        <div class="panel-amber">
          <div class="panel-title">风险、边界与主站 P9 对标</div>
          <ul class="brief-ul">{ins_risk}</ul>
          <p class="note" style="margin-top:10px"><strong>对照主站：</strong> P9 使用五阶段人天、修正研发、QC+测+预发测试工时等 Gate-RDJ 宽表字段。本分站导出<strong>无</strong>五阶段分解、无修正研发、无 Bug/迭代完成维；文中「测试/排期%」「R/T」均为<strong>分站近似口径</strong>，请勿与 P9 数值直接比高低。</p>
        </div>
      </div>
    </div>

    <div class="toc"><b>结构：</b>（一）分月事实与组合图 → （二）排期与节点 → （三）优先级与业务线 → （四）人力与 QC 散点 → <b>（专块）LDT 五人组</b> → （五）业务线聚合 → （六）收口动作 → （七）附录表 → （八）指标说明。</div>

    <div class="section">
      <div class="section-title">（一）分 · 时间维度 — 分月事实与组合图</div>
      <p class="part-desc">横轴为创建月；柱为需求条数与排期人天合计；折线为<strong>分站测试/排期%</strong>（当月测试合计÷当月排期合计，排期合计为 0 的月无该线点）。环比「pt」= 本期%−上期%。</p>
      <div id="ch_month_combo" class="chart compact"></div>
      <div class="table-wrap">
        <table class="data-tbl" id="tbl_month"><thead><tr>
          <th>创建月</th><th>条数</th><th>排期合计</th><th>测试合计</th><th>测试/排期%</th><th>环比(pt)</th><th>环比(相对%)</th>
        </tr></thead><tbody></tbody></table>
      </div>
      <p class="note">原始月份键：{html_lib.escape(month_keys_txt)}</p>
      <div class="chart-row" style="margin-top:14px">
        <div class="chart-box"><div class="chart-title">按创建月份条数</div><div id="ch_month" style="height:260px"></div></div>
        <div class="chart-box"><div class="chart-title">按创建周条数</div><div id="ch_week" style="height:260px"></div></div>
      </div>
      <div class="chart-row">
        <div class="chart-box"><div class="chart-title">业务线 Top20（含未填）</div><div id="ch_line" style="height:280px"></div></div>
        <div class="chart-box"><div class="chart-title">节点文案类型</div><div id="ch_node" style="height:280px"></div></div>
      </div>
      <div class="chart-box wide" style="margin-top:14px"><div class="chart-title">按月 × 优先级堆叠</div><div id="ch_month_stack" style="height:320px"></div></div>
    </div>

    <div class="section">
      <div class="section-title">（二）分 · 排期与节点粒度</div>
      <p class="part-desc">从「需求排期-节点」解析「N 个模块」；排期总人天分桶看交付体量分布。</p>
      <div class="chart-row">
        <div class="chart-box"><div class="chart-title">排期模块数分布（条数）</div><div id="ch_mods" style="height:280px"></div></div>
        <div class="chart-box"><div class="chart-title">排期总人天分桶</div><div id="ch_sched_hist" style="height:280px"></div></div>
      </div>
    </div>

    <div class="section">
      <div class="section-title">（三）分 · 优先级与业务线交叉</div>
      <p class="part-desc">热力图仅统计<b>已填业务线</b>：Top10 区域 + 其余合并为「其他(已填)」；值为条数。</p>
      <div class="chart-row">
        <div class="chart-box"><div class="chart-title">优先级占比</div><div id="ch_pri" style="height:280px"></div></div>
        <div class="chart-box"><div class="chart-title">创建人条数 Top 15</div><div id="ch_creator" style="height:280px"></div></div>
      </div>
      <div class="chart-row">
        <div class="chart-box wide"><div class="chart-title">已填业务线 × 优先级（条数热力）</div><div id="ch_heat" style="height:420px"></div></div>
      </div>
    </div>

    <div class="section">
      <div class="section-title">（四）分 · 人力负荷、测试投入与 QC 散点</div>
      <p class="part-desc">创建人维度看「条数」「排期人天合计」「测试估分合计」；QC 为均分后的测试人天。散点图每条需求一点：横轴排期人天、纵轴测试估分。</p>
      <div class="chart-row">
        <div class="chart-box"><div class="chart-title">QC 出现次数 Top 15（原始字段拆分）</div><div id="ch_qc" style="height:300px"></div></div>
        <div class="chart-box"><div class="chart-title">QC 测试负荷 Top 12（多人均分）</div><div id="ch_qc_load" style="height:300px"></div></div>
      </div>
      <div class="chart-row">
        <div class="chart-box"><div class="chart-title">创建人 · 排期人天合计 Top 10</div><div id="ch_cr_sched" style="height:300px"></div></div>
        <div class="chart-box"><div class="chart-title">创建人 · 测试估分合计 Top 10</div><div id="ch_cr_test" style="height:300px"></div></div>
      </div>
      <div class="chart-row">
        <div class="chart-box"><div class="chart-title">测试估分分段（条数）</div><div id="ch_test_b" style="height:260px"></div></div>
        <div class="chart-box"><div class="chart-title">排期人天 vs 测试估分（需求散点）</div><div id="ch_scatter" style="height:260px"></div></div>
      </div>
      <div class="chart-row">
        <div class="chart-box wide"><div class="chart-title">QC：测试负荷 vs 参与需求「测占排期%」均值（分站口径）</div><div id="ch_qc_scatter" style="height:280px"></div></div>
      </div>
      <p class="note">QC 散点横轴为均分后的测试估分合计（人天）；纵轴为该 QC 在所参与需求上「100×测试÷排期」的简单平均，用于粗看人头特征，<strong>非</strong> P9 部门对标。</p>
    </div>

    <div class="section" id="sec-ldt">
      <div class="section-title">（专块）LDT 测试五人组 · Dagger / Elisa / Gina / Viola / laoshuang</div>
      <p class="part-desc">口径：QC 列按「|」拆分后，与导出内 <code>dagger-qc</code>、<code>elisa-qc</code>、<code>gina-qc</code>、<code>viola-qc</code>、<code>laoshuang-qc</code> 等前缀匹配即计入（大小写不敏感；兼容您提供的「-LDT」展示名）。测试估分在多人 QC 时仍按人头均分计入个人行。</p>
      <div id="ldt-empty" class="note" style="display:none"></div>
      <div id="ldt-body" style="display:none">
        <div class="summary-cards" style="grid-template-columns:repeat(5,1fr);margin-bottom:14px">
          <div class="card"><h3>触及需求条数</h3><div class="value" id="ldt_n">—</div><div class="sub">占全量%</div><div class="sub" id="ldt_share">—</div></div>
          <div class="card"><h3>子集排期合计</h3><div class="value" id="ldt_sched">—</div><div class="sub">人天</div></div>
          <div class="card"><h3>子集测试合计</h3><div class="value test" id="ldt_test">—</div><div class="sub">人天</div></div>
          <div class="card"><h3>子集测试/排期%</h3><div class="value test" id="ldt_ratio">—</div><div class="sub">分站口径</div></div>
          <div class="card"><h3>对照全站%</h3><div class="value" id="ldt_glob">—</div><div class="sub">同口径</div></div>
        </div>
        <div class="panel-blue" style="margin-bottom:14px">
          <div class="panel-title">小组摘要</div>
          <ul class="brief-ul" id="ldt_brief_ul"></ul>
        </div>
        <div class="chart-row">
          <div class="chart-box"><div class="chart-title">小组需求 · 按创建月</div><div id="ch_ldt_month" style="height:260px"></div></div>
          <div class="chart-box"><div class="chart-title">小组 · 优先级分布</div><div id="ch_ldt_pri" style="height:260px"></div></div>
        </div>
        <div class="chart-row">
          <div class="chart-box"><div class="chart-title">五人 · 均分测试估分合计 & 参与条数</div><div id="ch_ldt_person" style="height:300px"></div></div>
          <div class="chart-box"><div class="chart-title">共现时 · 非本组 QC Top15（条数）</div><div id="ch_ldt_coqc" style="height:300px"></div></div>
        </div>
        <div class="chart-box wide" style="margin-top:10px"><div class="chart-title">小组需求 · 业务线（Top12）</div><div id="ch_ldt_line" style="height:320px"></div></div>
        <div class="table-wrap" style="margin-top:14px">
          <div class="panel-title" style="margin-bottom:8px">五人明细（参与条数、子集排期、均分测试合计、行内测占排期%均值）</div>
          <p class="note" style="margin-bottom:8px">关联需求（对齐 P9 读法）：<strong>点击第一列展示名</strong>，在<strong>下一整行</strong>展开同宽明细表；按<strong>均分测试</strong>降序排列。列为<strong>创建月</strong>（分站导出无完成月）、需求标题可跳转「工作项链接」。单条 <strong>测占排期%</strong>、<strong>R/T</strong> 为<strong>整条需求</strong>口径（非仅本人分摊），与上方汇总行的「行内均值」可能不完全对应。</p>
          <table class="data-tbl" id="tbl_ldt_person"><thead><tr>
            <th>展示名</th><th>参与条数</th><th>排期合计</th><th>均分测试合计</th><th>条均测试</th><th>行内测占排期%均值</th>
          </tr></thead><tbody></tbody></table>
        </div>
        <div class="table-wrap" style="margin-top:14px">
          <div class="panel-title" style="margin-bottom:8px">小组相关需求 · 测试估分 Top35</div>
          <table class="data-tbl" id="tbl_ldt_detail"><thead><tr>
            <th>标题</th><th>月</th><th>排期</th><th>测试</th><th>优先级</th><th>业务线</th><th>QC</th><th>链接</th>
          </tr></thead><tbody></tbody></table>
        </div>
      </div>
    </div>

    <div class="section">
      <div class="section-title">（五）已填业务线聚合（前 25，按条数降序）</div>
      <p class="part-desc">测试/排期% 仅在该业务线排期合计&gt;0 时计算；为粗粒度结构指标。</p>
      <div class="detail-table">
        <table class="data-tbl" id="tbl_line_agg"><thead>
          <tr><th>业务线</th><th>条数</th><th>排期合计</th><th>测试合计</th><th>均排期/条</th><th>均测试/条</th><th>测试/排期%</th></tr>
        </thead><tbody></tbody></table>
      </div>
    </div>

    <div class="section">
      <div class="section-title">（六）总结与收口动作（总）</div>
      <p class="part-desc">与主站 P9「建议收口」同构的<strong>可执行项</strong>（按分站数据可达性裁剪）。</p>
      <ul class="brief-ul">{close_list}</ul>
    </div>

    <div class="section">
      <div class="section-title">（七）附录 · 清单表</div>
      <div class="detail-table">
        <div class="chart-title" style="text-align:left;margin-bottom:8px">A. 测试估分 Top 20</div>
        <table class="data-tbl" id="tbl_test"><thead>
          <tr><th>标题</th><th>测试</th><th>排期</th><th>优先级</th><th>业务线</th><th>链接</th></tr>
        </thead><tbody></tbody></table>
      </div>
      <div class="detail-table">
        <div class="chart-title" style="text-align:left;margin-bottom:8px">B. 排期人天 Top 15</div>
        <table class="data-tbl" id="tbl_sched"><thead>
          <tr><th>标题</th><th>排期人天</th><th>测试</th><th>业务线</th><th>链接</th></tr>
        </thead><tbody></tbody></table>
      </div>
    </div>

    <div class="section glossary">
      <details class="glossary">
        <summary>（八）指标说明 · 与主站 P9 附录对照（点击展开）</summary>
        <ul class="glist" style="margin-top:10px">
        <li><strong>【分站】测试/排期%</strong>：当月（或全期）测试估分合计 ÷ 排期人天合计（仅统计排期可解析且分母&gt;0 的子集）。<strong>≠ P9</strong>「测试工时÷五阶段总人天」。</li>
        <li><strong>【分站】R/T</strong>：单条为「排期人天÷测试估分」（测试&gt;0 且排期&gt;0）；汇总表中位为样本中位数。<strong>≠ P9</strong>「修正研发÷测试工时」。</li>
        <li><strong>QC 测试负荷</strong>：多人 QC 时单条测试估分按人头均分后加总；与「QC 出现次数」不同义。</li>
        <li><strong>数据来源</strong>：{html_lib.escape(src_note)} 当前状态均为「已完成」。</li>
        </ul>
      </details>
    </div>

    <div class="footer">由 scripts/generate_chanfeng_station_report.py 生成 · 版式与读法对齐 Gate-RDJ-QC人员-P9人效环比与建议报告 · ECharts 依赖策略同主站报告</div>
  </div>
  <script>
    const P = {data_json};
    const APP_T = {appendix_test_json};
    const APP_S = {appendix_sched_json};

    const S = P.summary;
    document.getElementById('c_n').textContent = P.n;
    document.getElementById('c_sched_sum').textContent = S.schedule_sum;
    document.getElementById('c_sched_med').textContent = S.schedule_median;
    document.getElementById('c_parse_fail').textContent = S.parse_fail;
    document.getElementById('c_test_sum').textContent = S.test_sum;
    document.getElementById('c_test_med').textContent = S.test_median;
    document.getElementById('c_miss_line').textContent = S.missing_line;
    document.getElementById('c_miss_qc').textContent = S.missing_qc;
    document.getElementById('c_rt_med').textContent = S.rt_median != null ? S.rt_median : '—';
    document.getElementById('c_gtr').textContent = S.global_test_ratio_pct != null ? S.global_test_ratio_pct + '%' : '—';

    const tbM = document.querySelector('#tbl_month tbody');
    (P.month_table_rows || []).forEach(r => {{
      const tr = document.createElement('tr');
      const rel = r.mom_rel == null ? '—' : ((r.mom_rel > 0 ? '+' : '') + r.mom_rel + '%');
      const pt = r.mom_pt == null ? '—' : ((r.mom_pt > 0 ? '+' : '') + r.mom_pt + 'pt');
      [r.month, r.n, r.sched_sum, r.test_sum, r.ratio_pct == null ? '—' : r.ratio_pct + '%', pt, rel].forEach((cell, idx) => {{
        const td = document.createElement('td');
        td.textContent = cell;
        if (idx > 0) td.className = 'num';
        tr.appendChild(td);
      }});
      tbM.appendChild(tr);
    }});

    const mc = P.month_combo || {{ categories: [], counts: [], sched_sums: [], ratio_pcts: [] }};
    echarts.init(document.getElementById('ch_month_combo')).setOption({{
      tooltip: {{ trigger: 'axis' }},
      legend: {{ top: 2 }},
      grid: {{ left: 46, right: 52, top: 40, bottom: 44 }},
      xAxis: {{ type: 'category', data: mc.categories, axisLabel: {{ rotate: 18, fontSize: 10 }} }},
      yAxis: [
        {{ type: 'value', name: '条数/人天' }},
        {{ type: 'value', name: '测试/排期%', position: 'right', splitLine: {{ show: false }} }}
      ],
      series: [
        {{ name: '条数', type: 'bar', data: mc.counts, itemStyle: {{ color: '#94a3b8' }} }},
        {{ name: '排期人天', type: 'bar', data: mc.sched_sums, itemStyle: {{ color: '#38bdf8' }} }},
        {{ name: '测试/排期%', type: 'line', yAxisIndex: 1, data: mc.ratio_pcts, itemStyle: {{ color: '#0ea5e9' }}, symbol: 'circle', symbolSize: 7 }}
      ]
    }});

    function barOption(cats, vals, horiz, color) {{
      color = color || '#0ea5e9';
      return {{
        tooltip: {{ trigger: 'axis' }},
        grid: {{ left: horiz ? 130 : 40, right: 20, top: 26, bottom: horiz ? 20 : (cats.length>10?56:40) }},
        xAxis: horiz ? {{ type: 'value' }} : {{ type: 'category', data: cats, axisLabel: {{ rotate: cats.length>8?28:0, interval:0, fontSize:9 }} }},
        yAxis: horiz ? {{ type: 'category', data: cats, axisLabel: {{ fontSize:9 }} }} : {{ type: 'value' }},
        series: [{{
          type: 'bar', data: vals, itemStyle: {{ color }},
          label: {{ show: true, position: horiz ? 'right' : 'top', fontSize: 9 }}
        }}]
      }};
    }}

    echarts.init(document.getElementById('ch_month')).setOption(barOption(P.month_bar.categories, P.month_bar.values, false));
    echarts.init(document.getElementById('ch_week')).setOption(barOption(P.week_bar.categories, P.week_bar.values, false, '#0284c7'));
    echarts.init(document.getElementById('ch_line')).setOption(barOption(P.line_bar.categories, P.line_bar.values, true));
    echarts.init(document.getElementById('ch_node')).setOption({{
      tooltip: {{ trigger: 'item' }},
      series: [{{ type: 'pie', radius: ['34%','62%'], data: P.node_pie, label: {{ fontSize: 10 }} }}]
    }});
    echarts.init(document.getElementById('ch_pri')).setOption({{
      tooltip: {{ trigger: 'item' }},
      series: [{{ type: 'pie', radius: ['36%','60%'], data: P.priority_pie, label: {{ fontSize: 10 }} }}]
    }});
    echarts.init(document.getElementById('ch_creator')).setOption(barOption(P.creator_bar.categories, P.creator_bar.values, true));
    echarts.init(document.getElementById('ch_qc')).setOption(barOption(P.qc_bar.categories, P.qc_bar.values, true));
    echarts.init(document.getElementById('ch_qc_load')).setOption(barOption(P.qc_load_bar.categories, P.qc_load_bar.values, true, '#f59e0b'));
    echarts.init(document.getElementById('ch_cr_sched')).setOption(barOption(P.creator_sched_bar.categories, P.creator_sched_bar.values, true, '#0891b2'));
    echarts.init(document.getElementById('ch_cr_test')).setOption(barOption(P.creator_test_bar.categories, P.creator_test_bar.values, true, '#ea580c'));
    echarts.init(document.getElementById('ch_test_b')).setOption(barOption(P.test_bucket_bar.categories, P.test_bucket_bar.values, false));
    echarts.init(document.getElementById('ch_mods')).setOption(barOption(P.mods_bar.categories, P.mods_bar.values, false, '#2dd4bf'));
    echarts.init(document.getElementById('ch_sched_hist')).setOption(barOption(P.schedule_bins.categories, P.schedule_bins.values, false, '#5eead4'));

    if (P.month_stack && P.month_stack.categories && P.month_stack.categories.length && P.month_stack.series.length) {{
      echarts.init(document.getElementById('ch_month_stack')).setOption({{
        tooltip: {{ trigger: 'axis' }},
        legend: {{ top: 0 }},
        grid: {{ left: 44, right: 20, top: 36, bottom: 44 }},
        xAxis: {{ type: 'category', data: P.month_stack.categories, axisLabel: {{ rotate: 20, fontSize: 10 }} }},
        yAxis: {{ type: 'value', name: '条数' }},
        series: P.month_stack.series.map(s => ({{ ...s, itemStyle: {{ ...(s.itemStyle || {{}}), borderRadius: [2,2,0,0] }} }}))
      }});
    }} else {{
      document.getElementById('ch_month_stack').innerHTML = '<p style="padding:24px;color:#64748b;text-align:center">无有效创建月数据</p>';
    }}

    const hm = P.heatmap;
    if (hm.data && hm.data.length) {{
      const maxv = Math.max(...hm.data.map(d => d[2]), 1);
      echarts.init(document.getElementById('ch_heat')).setOption({{
        tooltip: {{ position: 'top' }},
        grid: {{ height: Math.min(56 * hm.lines.length, 360), top: 40, left: 80, right: 24 }},
        xAxis: {{ type: 'category', data: hm.prios, splitArea: {{ show: true }} }},
        yAxis: {{ type: 'category', data: hm.lines, splitArea: {{ show: true }} }},
        visualMap: {{ min: 0, max: maxv, calculable: true, orient: 'horizontal', left: 'center', bottom: 4, inRange: {{ color: ['#f0f9ff','#0369a1'] }} }},
        series: [{{
          type: 'heatmap', data: hm.data,
          label: {{ show: true, fontSize: 10 }},
          emphasis: {{ itemStyle: {{ shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.2)' }} }}
        }}]
      }});
    }} else {{
      document.getElementById('ch_heat').innerHTML = '<p style="padding:24px;color:#64748b;text-align:center">无已填业务线样本</p>';
    }}

    echarts.init(document.getElementById('ch_scatter')).setOption({{
      tooltip: {{ trigger: 'item', formatter: p => '排期: ' + p.value[0] + ' 天<br/>测试: ' + p.value[1] }},
      grid: {{ left: 48, right: 20, top: 24, bottom: 40 }},
      xAxis: {{ type: 'value', name: '排期人天', scale: true }},
      yAxis: {{ type: 'value', name: '测试估分', scale: true }},
      series: [{{
        type: 'scatter', symbolSize: 6,
        data: P.scatter,
        itemStyle: {{ color: 'rgba(14,165,233,0.55)' }}
      }}]
    }});

    if (P.qc_scatter && P.qc_scatter.length) {{
      echarts.init(document.getElementById('ch_qc_scatter')).setOption({{
        tooltip: {{ trigger: 'item', formatter: p => {{
          const nm = (p.data && p.data.name) ? p.data.name : '';
          const v = p.value || (p.data && p.data.value) || [];
          return nm + '<br/>测试负荷(均分): ' + v[0] + '<br/>参与需求·测占排期%均值: ' + v[1];
        }} }},
        grid: {{ left: 52, right: 18, top: 28, bottom: 36 }},
        xAxis: {{ type: 'value', name: '测试负荷', scale: true }},
        yAxis: {{ type: 'value', name: '均值%', scale: true }},
        series: [{{
          type: 'scatter', symbolSize: 11,
          data: P.qc_scatter.map(d => ({{ name: d.name, value: d.value }})),
          itemStyle: {{ color: 'rgba(2,132,199,0.75)' }}
        }}]
      }});
    }} else {{
      document.getElementById('ch_qc_scatter').innerHTML = '<p style="padding:20px;color:#64748b;text-align:center;font-size:12px">无 QC 散点数据</p>';
    }}

    const LDT = P.ldt_qc_panel;
    if (!LDT || !LDT.active) {{
      const em = document.getElementById('ldt-empty');
      em.style.display = 'block';
      em.textContent = (LDT && LDT.brief && LDT.brief.length) ? LDT.brief[0] : '本数据中未匹配到 LDT 五人组。';
    }} else {{
      document.getElementById('ldt-body').style.display = 'block';
      document.getElementById('ldt_n').textContent = LDT.n;
      document.getElementById('ldt_share').textContent = '占全量 ' + LDT.share_of_all_pct + '%';
      document.getElementById('ldt_sched').textContent = LDT.sched_sum;
      document.getElementById('ldt_test').textContent = LDT.test_sum;
      document.getElementById('ldt_ratio').textContent = LDT.ratio_pct != null ? LDT.ratio_pct + '%' : '—';
      document.getElementById('ldt_glob').textContent = LDT.global_ratio_pct != null ? LDT.global_ratio_pct + '%' : '—';
      const ulb = document.getElementById('ldt_brief_ul');
      (LDT.brief || []).forEach(t => {{ const li = document.createElement('li'); li.textContent = t; ulb.appendChild(li); }});
      echarts.init(document.getElementById('ch_ldt_month')).setOption(barOption(LDT.month_bar.categories, LDT.month_bar.values, false));
      echarts.init(document.getElementById('ch_ldt_pri')).setOption({{
        tooltip: {{ trigger: 'item' }},
        series: [{{ type: 'pie', radius: ['34%','58%'], data: LDT.priority_pie, label: {{ fontSize: 10 }} }}]
      }});
      const pr = LDT.person_rows || [];
      echarts.init(document.getElementById('ch_ldt_person')).setOption({{
        tooltip: {{ trigger: 'axis' }},
        grid: {{ left: 130, right: 28, top: 26, bottom: 20 }},
        xAxis: {{ type: 'value', name: '均分测试(人天)' }},
        yAxis: {{ type: 'category', data: pr.map(r => r.label), axisLabel: {{ fontSize: 9 }} }},
        series: [{{
          type: 'bar',
          data: pr.map(r => r.test_share),
          itemStyle: {{ color: '#0ea5e9' }},
          label: {{ show: true, position: 'right', fontSize: 10, formatter: function(p) {{ return pr[p.dataIndex].n + '条'; }} }}
        }}]
      }});
      echarts.init(document.getElementById('ch_ldt_coqc')).setOption(barOption(LDT.coqc_bar.categories, LDT.coqc_bar.values, true, '#64748b'));
      echarts.init(document.getElementById('ch_ldt_line')).setOption(barOption(LDT.line_bar.categories, LDT.line_bar.values, true, '#0369a1'));
      const tbp = document.querySelector('#tbl_ldt_person tbody');
      function appendLdtDemandMini(tbody, rows) {{
        rows.forEach(dr => {{
          const tr = document.createElement('tr');
          const td0 = document.createElement('td');
          td0.textContent = dr.month || '—';
          tr.appendChild(td0);
          const td1 = document.createElement('td');
          td1.style.maxWidth = '280px';
          td1.style.textAlign = 'left';
          const tit = dr.title || '(无标题)';
          const href = (dr.link || '').trim();
          if (href.indexOf('http://') === 0 || href.indexOf('https://') === 0) {{
            const a = document.createElement('a');
            a.href = href; a.target = '_blank'; a.rel = 'noopener noreferrer';
            a.style.cssText = 'color:#0369a1;text-decoration:underline;';
            a.textContent = tit.length > 120 ? tit.slice(0, 117) + '…' : tit;
            td1.appendChild(a);
          }} else {{
            td1.textContent = tit.length > 120 ? tit.slice(0, 117) + '…' : tit;
          }}
          tr.appendChild(td1);
          const td2 = document.createElement('td'); td2.className = 'num';
          td2.textContent = dr.test_share != null ? dr.test_share : '—';
          tr.appendChild(td2);
          const td3 = document.createElement('td'); td3.className = 'num';
          td3.textContent = dr.ratio_pct == null ? '—' : dr.ratio_pct + '%';
          tr.appendChild(td3);
          const td4 = document.createElement('td'); td4.className = 'num';
          td4.textContent = dr.rt == null ? '—' : String(dr.rt);
          tr.appendChild(td4);
          const td5 = document.createElement('td');
          td5.style.textAlign = 'left'; td5.style.maxWidth = '140px';
          td5.textContent = dr.line || '—';
          tr.appendChild(td5);
          const td6 = document.createElement('td');
          td6.style.textAlign = 'left'; td6.style.fontSize = '11px';
          td6.textContent = dr.pri || '—';
          tr.appendChild(td6);
          tbody.appendChild(tr);
        }});
      }}
      pr.forEach(r => {{
        const tr = document.createElement('tr');
        tr.className = 'qc-summary-row';
        const tdName = document.createElement('td');
        tdName.className = 'qc-name-cell';
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'qc-name-toggle';
        btn.setAttribute('aria-expanded', 'false');
        btn.setAttribute('aria-controls', r.expand_id || '');
        btn.textContent = r.label || '';
        tdName.appendChild(btn);
        tr.appendChild(tdName);
        [r.n, r.sched_sum, r.test_share, r.avg_test_per_row, r.avg_ratio_pct == null ? '—' : r.avg_ratio_pct + '%'].forEach((cell) => {{
          const td = document.createElement('td');
          td.textContent = cell;
          td.className = 'num';
          tr.appendChild(td);
        }});
        tbp.appendChild(tr);
        const trEx = document.createElement('tr');
        trEx.className = 'qc-demand-expand-row';
        trEx.id = r.expand_id || '';
        trEx.setAttribute('hidden', '');
        const tdEx = document.createElement('td');
        tdEx.colSpan = 6;
        tdEx.className = 'qc-demand-expand-cell';
        const drawer = document.createElement('div');
        drawer.className = 'qc-demand-drawer';
        const wrap = document.createElement('div');
        wrap.className = 'qc-demand-table-wrap';
        const tbl = document.createElement('table');
        tbl.className = 'qc-demand-mini';
        tbl.innerHTML = '<thead><tr><th>创建月</th><th>需求</th><th>均分测试</th><th>测占排期%</th><th>R/T</th><th>业务线</th><th>优先级</th></tr></thead><tbody></tbody>';
        const tbMini = tbl.querySelector('tbody');
        const drows = r.demand_rows || [];
        if (drows.length) appendLdtDemandMini(tbMini, drows);
        else {{
          const tr0 = document.createElement('tr');
          const td0 = document.createElement('td');
          td0.colSpan = 7;
          td0.className = 'muted';
          td0.style.textAlign = 'left';
          td0.textContent = '无关联需求行';
          tr0.appendChild(td0);
          tbMini.appendChild(tr0);
        }}
        wrap.appendChild(tbl);
        drawer.appendChild(wrap);
        const foot = document.createElement('p');
        foot.className = 'qc-demand-foot muted';
        foot.style.margin = '6px 0 0';
        foot.style.fontSize = '11px';
        foot.textContent = '共 ' + (drows.length) + ' 条（按均分测试降序）';
        drawer.appendChild(foot);
        tdEx.appendChild(drawer);
        trEx.appendChild(tdEx);
        tbp.appendChild(trEx);
      }});
      (function setupLdtDemandExpand() {{
        document.querySelectorAll('#tbl_ldt_person .qc-name-toggle').forEach(function(btn) {{
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
      const tbd = document.querySelector('#tbl_ldt_detail tbody');
      (LDT.detail_rows || []).forEach(r => {{
        const tr = document.createElement('tr');
        const cells = [
          ['title', true], ['month', false], ['sched', false], ['test', false], ['pri', false], ['line', false], ['qc', false], ['link', false]
        ];
        cells.forEach(([k, isTitle], i) => {{
          const td = document.createElement('td');
          if (k === 'title') {{
            const a = document.createElement('a');
            a.href = r.link || '#'; a.target = '_blank'; a.rel = 'noopener';
            a.textContent = r.title || '(无标题)';
            td.appendChild(a);
          }} else if (k === 'link' && r.link) {{
            const a = document.createElement('a');
            a.href = r.link; a.target = '_blank'; a.rel = 'noopener'; a.textContent = '打开';
            td.appendChild(a);
          }} else {{
            td.textContent = (r[k] !== undefined && r[k] !== null) ? r[k] : '—';
          }}
          if (i > 0 && k !== 'line' && k !== 'qc' && k !== 'link' && k !== 'title') td.className = 'num';
          tr.appendChild(td);
        }});
        tbd.appendChild(tr);
      }});
    }}

    const tbA = document.querySelector('#tbl_line_agg tbody');
    (P.line_agg_rows || []).forEach(r => {{
      const tr = document.createElement('tr');
      [r.line, r.n, r.sched_sum, r.test_sum, r.avg_sched, r.avg_test, r.test_ratio_pct == null ? '—' : r.test_ratio_pct + '%'].forEach((cell, idx) => {{
        const td = document.createElement('td');
        td.textContent = cell;
        if (idx > 0) td.className = 'num';
        tr.appendChild(td);
      }});
      tbA.appendChild(tr);
    }});

    function fillApp(tableId, rows, cols) {{
      const tb = document.querySelector(tableId + ' tbody');
      rows.forEach(r => {{
        const tr = document.createElement('tr');
        cols.forEach((c, i) => {{
          const td = document.createElement('td');
          if (c === 'title') {{
            const a = document.createElement('a');
            a.href = r.link || '#'; a.target = '_blank'; a.rel = 'noopener';
            a.textContent = r.title || '(无标题)';
            td.appendChild(a);
          }} else if (c === 'link' && r.link) {{
            const a = document.createElement('a');
            a.href = r.link; a.target = '_blank'; a.rel = 'noopener'; a.textContent = '打开';
            td.appendChild(a);
          }} else {{
            td.textContent = (r[c] !== undefined && r[c] !== null) ? r[c] : '—';
          }}
          if (i > 0 && c !== 'title' && c !== 'line' && c !== 'link' && c !== 'pri') td.className = 'num';
          tr.appendChild(td);
        }});
        tb.appendChild(tr);
      }});
    }}
    fillApp('#tbl_test', APP_T, ['title','test','sched','pri','line','link']);
    fillApp('#tbl_sched', APP_S, ['title','sched','test','line','link']);
  </script>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", type=str, default="", help="源 xlsx 路径")
    ap.add_argument("--csv-out", type=str, default=str(DEFAULT_CSV), help="写出 CSV 路径")
    ap.add_argument("--html-out", type=str, default=str(OUT_HTML), help="写出 HTML 路径")
    args = ap.parse_args()

    xlsx_path = Path(args.xlsx) if args.xlsx else None
    csv_out = Path(args.csv_out)
    html_out = Path(args.html_out)

    if xlsx_path is None and not DEFAULT_CSV.exists() and DEFAULT_XLSX_DL.exists():
        xlsx_path = DEFAULT_XLSX_DL

    df = load_frame(xlsx_path, DEFAULT_CSV)

    wrote_csv = False
    if xlsx_path and xlsx_path.exists():
        df.to_csv(csv_out, index=False, encoding="utf-8-sig")
        wrote_csv = True
    elif not DEFAULT_CSV.exists():
        sys.stderr.write("错误: 项目根无 CSV，且未找到默认 xlsx。请指定 --xlsx\n")
        return 1

    payload, appendix_test, appendix_sched, _ = build_payload(df)
    html = build_html(payload, appendix_test, appendix_sched, str(csv_out.name), wrote_csv)
    html_out.write_text(html, encoding="utf-8")
    print(f"已写出: {html_out}")
    if wrote_csv:
        print(f"已写出 CSV: {csv_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
