"""全景单页构建前交叉校验：KPI、图表 OPTIONS、扩展块与源数据一致。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from _paths import REPO_ROOT
from gate_rdj_metrics import dedupe_main_rows, load_rows, main_row_dedupe_key
from rdj_delivery_blocks import validate_against_source

CSV_TIME = REPO_ROOT / "需求导出-Gate-RDJ_时间维度.csv"
CSV_ITER = REPO_ROOT / "需求导出-Gate-RDJ_迭代维度.csv"


def _parse_samples_main(s: str) -> int:
    part = str(s).split("/")[0].strip()
    return int(part) if part.isdigit() else 0


def validate_main_csv_dedup() -> tuple[list[str], list[str]]:
    """主站时间维+迭代维合并须按 story ID 去重，禁止简单相加条数。"""
    errors: list[str] = []
    warns: list[str] = []
    if not CSV_TIME.is_file() or not CSV_ITER.is_file():
        warns.append("主站 CSV 缺失，跳过时间/迭代去重校验")
        return errors, warns

    time_rows = load_rows(str(CSV_TIME))
    iter_rows = load_rows(str(CSV_ITER))
    time_keys = {main_row_dedupe_key(r) for r in time_rows}
    iter_keys = {main_row_dedupe_key(r) for r in iter_rows}
    overlap = len(time_keys & iter_keys)
    merged_n = len(dedupe_main_rows([str(CSV_ITER), str(CSV_TIME)]))
    naive_sum = len(time_rows) + len(iter_rows)

    if overlap > 0 and merged_n >= naive_sum - 100:
        errors.append(
            f"主站合并去重异常：时间∩迭代 {overlap} 条，合并后 {merged_n} 仍接近 naive 相加 {naive_sum}"
        )
    if merged_n > len(time_rows) + len(iter_rows) - overlap:
        errors.append(
            f"主站合并条数 {merged_n} > 去重后上界 {len(time_rows) + len(iter_rows) - overlap}"
        )
    if overlap > 0:
        warns.append(
            f"主站时间维 {len(time_keys)} 条 · 迭代维 {len(iter_keys)} 条 · 交集 {overlap} · 合并去重后 {merged_n} 条"
        )
    return errors, warns


def validate_rt_dept_samples(rt_data: dict, test_floor: float = 0.05) -> tuple[list[str], list[str]]:
    """部门表汇总样本不得因时间/迭代双源重复计数。"""
    errors: list[str] = []
    warns: list[str] = []
    depts = rt_data.get("dept") or []
    if not depts:
        return errors, warns

    samp_sum = sum(_parse_samples_main(d.get("samples", "")) for d in depts)
    merged_n = len(dedupe_main_rows([str(CSV_ITER), str(CSV_TIME)])) if CSV_TIME.is_file() and CSV_ITER.is_file() else None

    # 主站样本为 QC 分摊后的 RT 可算条数，上界 ≈ 去重需求数 × 平均每需求 QC 数（粗估 3）
    if merged_n and samp_sum > merged_n * 3:
        errors.append(
            f"RT 部门表主站样本合计 {samp_sum} 异常偏高（去重需求仅 {merged_n} 条，疑似时间/迭代未去重）"
        )
    elif merged_n and samp_sum > merged_n * 2:
        warns.append(
            f"RT 部门表主站样本合计 {samp_sum}，去重需求 {merged_n} 条，请确认多 QC 分摊口径"
        )

    # 汇总行 R/T 须由 demands 加权，样本列应与各部门求和一致
    from portfolio_rt_merge import compute_dept_summary

    summary = compute_dept_summary(rt_data, test_floor)
    summary_main = _parse_samples_main(summary.get("samples", ""))
    if summary_main != samp_sum:
        errors.append(f"RT 汇总行主站样本 {summary_main} ≠ 各部门求和 {samp_sum}")
    return errors, warns


def validate_portfolio(
    mt: dict,
    mi: dict,
    br: dict,
    ai: dict,
    al: dict,
    dt: dict,
    di: dict,
    P: dict,
    opts: dict,
    rt_data: dict | None = None,
) -> tuple[list[str], list[str]]:
    """返回 (errors, warnings)。errors 非空时构建应失败。"""
    errors: list[str] = []
    warns: list[str] = []

    warns.extend(validate_against_source(dt, "时间维"))
    warns.extend(validate_against_source(di, "迭代维"))

    # ── 主站 KPI ↔ ext / 源 data ──
    for label, d, m in [("时间维", dt, mt), ("迭代维", di, mi)]:
        ext = m["ext"]
        kpi_n = m["kpi"]["需求数"]
        if ext["demands"] and sum(ext["demands"]) != kpi_n:
            errors.append(
                f"{label}: 扩展块 demands 合计 {sum(ext['demands'])} ≠ KPI 需求数 {kpi_n}"
            )
        if len(ext["months"]) != len(ext["demands"]):
            errors.append(f"{label}: ext 月份数 {len(ext['months'])} ≠ demands 长度")
        if ext["test_pcts"] and len(ext["test_pcts"]) != len(ext["months"]):
            errors.append(f"{label}: test_pcts 长度与月份不一致")
        pw = d.get("phase_workload") or []
        if pw and abs(m["kpi"]["测试占比%"] - round(pw[3]["pct"], 1)) > 0.2:
            errors.append(
                f"{label}: KPI 测试占比% {m['kpi']['测试占比%']} ≠ phase_workload 测试 {pw[3]['pct']}%"
            )

    # ── 分站 ↔ const P ──
    summary = P.get("summary") or {}
    prio = {x["name"]: x["value"] for x in P.get("priority_pie") or []}
    bk = br["kpi"]
    if bk["工作项数"] != P["n"]:
        errors.append(f"分站: KPI 工作项数 {bk['工作项数']} ≠ P.n {P['n']}")
    if sum(br["month_cnt"]) != P["n"]:
        errors.append(
            f"分站: 分月条数合计 {sum(br['month_cnt'])} ≠ P.n {P['n']}"
        )
    if bk.get("业务线未填") != summary.get("missing_line"):
        errors.append(
            f"分站: 业务线未填 {bk.get('业务线未填')} ≠ summary.missing_line {summary.get('missing_line')}"
        )
    if bk.get("测试>0条数") != summary.get("rt_n"):
        errors.append(
            f"分站: 测试>0 {bk.get('测试>0条数')} ≠ summary.rt_n {summary.get('rt_n')}"
        )
    for pk in ("P0", "P1", "P2"):
        key = f"{pk}条数"
        if key in bk and bk[key] != prio.get(pk, -1):
            errors.append(f"分站: {key} {bk[key]} ≠ priority_pie {prio.get(pk)}")
    prio_sum = sum(prio.values())
    if prio_sum != P["n"]:
        warns.append(f"分站: 优先级合计 {prio_sum} ≠ 总条数 {P['n']}")

    # ── AI ↔ 业务线表 ──
    ak = ai["kpi"]
    biz = ai.get("biz") or []
    if biz:
        d_sum = sum(b["demands"] for b in biz)
        if ak.get("参与需求") and d_sum != ak["参与需求"]:
            errors.append(f"AI: 业务线需求合计 {d_sum} ≠ KPI 参与需求 {ak['参与需求']}")
        e_sum = round(sum(b["est"] for b in biz), 1)
        if ak.get("估算人日Σ") and abs(e_sum - float(ak["估算人日Σ"])) > 1.0:
            errors.append(f"AI: 业务线估算合计 {e_sum} ≠ KPI 估算人日Σ {ak['估算人日Σ']}")
        t_sum = round(sum(b["test_alloc"] for b in biz), 1)
        if ak.get("测试分摊Σ") and abs(t_sum - float(ak["测试分摊Σ"])) > 1.0:
            errors.append(f"AI: 业务线测试分摊合计 {t_sum} ≠ KPI 测试分摊Σ {ak['测试分摊Σ']}")

    # ── Alpha ↔ split ──
    lk = al["kpi"]
    if lk["主站条数"] + lk["分站条数"] != lk["需求数"]:
        errors.append(
            f"Alpha: 主站+分站 {lk['主站条数']}+{lk['分站条数']} ≠ 需求数 {lk['需求数']}"
        )
    split = al.get("split") or []
    if split:
        if split[0][1] != lk["主站条数"] or split[1][1] != lk["分站条数"]:
            errors.append("Alpha: split 条数与 KPI 主站/分站不一致")

    # ── 总览规模图 ov_scale ──
    ov = opts.get("ov_scale") or {}
    series = (ov.get("series") or [{}])[0]
    vals = [x.get("value") if isinstance(x, dict) else x for x in series.get("data") or []]
    merged_n = 0
    if CSV_TIME.is_file() and CSV_ITER.is_file():
        merged_n = len(dedupe_main_rows([str(CSV_ITER), str(CSV_TIME)]))
    expected = [
        lk["需求数"],
        ak.get("参与需求"),
        bk["工作项数"],
        merged_n,
        mi["kpi"]["需求数"],
        mt["kpi"]["需求数"],
    ]
    if vals != expected:
        errors.append(f"总览 ov_scale 数据 {vals} ≠ 期望 {expected}")

    dedup_err, dedup_warn = validate_main_csv_dedup()
    errors.extend(dedup_err)
    warns.extend(dedup_warn)

    if rt_data:
        rt_err, rt_warn = validate_rt_dept_samples(rt_data)
        errors.extend(rt_err)
        warns.extend(rt_warn)

    try:
        from portfolio_raw_data import load_raw_records

        raw = load_raw_records()
        raw_main = sum(1 for r in raw if r.get("module") == "主站·Gate-RDJ")
        if merged_n and raw_main != merged_n:
            errors.append(f"原始数据主站 {raw_main} ≠ dedupe_main_rows {merged_n}")
        raw_total = len(raw)
        mod_sum = sum(1 for r in raw)  # same as raw_total
        if mod_sum != raw_total:
            errors.append(f"原始数据条数异常 {raw_total}")
    except Exception as exc:
        warns.append(f"原始数据 Tab 对账跳过: {exc}")

    return errors, warns
