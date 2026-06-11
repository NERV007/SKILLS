#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验全景单页「原始数据 / 需求明细」与 gate_rdj_metrics 口径一致，且 HTML 内嵌 JSON 同源。"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from gate_rdj_metrics import (  # noqa: E402
    corrected_rd,
    dedupe_main_rows,
    main_station_role_hours,
    main_station_test_hours_core,
)
from portfolio_dept_stats import DEPT_CACHE  # noqa: E402
from portfolio_raw_data import load_raw_records  # noqa: E402
from qc_unified_roster_report import (  # noqa: E402
    CSV_ITER,
    CSV_TIME,
    _qc_roster_from_html,
)

PORTFOLIO_HTML = ROOT / "RD-Efficiency-Portfolio.html"
TEST_FLOOR = 0.05


def _hour_display(v: float | None) -> float | None:
    """与 portfolio_raw_data 一致：≤0 显示为 None。"""
    if v is None or float(v) <= 0:
        return None
    return float(v)


def _rt_expected(rd: float | None, test: float | None) -> float | None:
    if rd is None or test is None or test <= TEST_FLOOR or rd <= 0:
        return None
    return round(rd / test, 2)


def _load_allow() -> set[str]:
    if not DEPT_CACHE.is_file():
        return set()
    html = DEPT_CACHE.read_text(encoding="utf-8")
    _, group_of, _ = _qc_roster_from_html(html)
    return set(group_of.keys())


def _html_contains_record(html: str, rec: dict) -> bool:
    """HTML 内嵌 JSON 与 Python 记录字段一致（抽样/锚点）。"""
    sid = str(rec.get("id"))
    chunk = (
        f'"id": "{sid}"'
        if f'"id": "{sid}"' in html
        else f'"id":"{sid}"'
    )
    if chunk not in html:
        return False
    rd = rec.get("rd")
    test = rec.get("test")
    rt = rec.get("rt")
    if rd is not None and f'"rd": {rd}' not in html and f'"rd":{rd}' not in html:
        return False
    if test is not None and f'"test": {test}' not in html and f'"test":{test}' not in html:
        return False
    if rt is not None and f'"rt": {rt}' not in html and f'"rt":{rt}' not in html:
        return False
    return True


def main() -> int:
    errors: list[str] = []
    allow = _load_allow()
    records = load_raw_records()
    by_id = {str(r.get("id")): r for r in records if r.get("id")}

    # ── 1. 主站 CSV 重算 vs load_raw_records ──
    csv_by_id: dict[str, dict] = {}
    for r in dedupe_main_rows([CSV_ITER, CSV_TIME]):
        link = r.get("需求链接") or ""
        sid_m = re.search(r"/detail/(\d+)", link)
        if not sid_m:
            continue
        sid = sid_m.group(1)
        rd, test, rt, qc_p, dev_p = main_station_role_hours(r, allow)
        csv_by_id[sid] = {
            "rd": rd,
            "test": test,
            "rt": rt,
            "qc": " · ".join(qc_p) if qc_p else (r.get("QC") or "—"),
            "dev_roles": " · ".join(dev_p) if dev_p else "",
        }

    main_recs = [r for r in records if r.get("module") == "主站·Gate-RDJ"]
    if len(main_recs) != len(csv_by_id):
        errors.append(
            f"主站条数不一致: records={len(main_recs)} csv_dedupe={len(csv_by_id)}"
        )

    for rec in main_recs:
        sid = str(rec.get("id"))
        exp = csv_by_id.get(sid)
        if not exp:
            errors.append(f"主站记录 {sid} 在 CSV 去重集中缺失")
            continue
        exp_rd = _hour_display(exp["rd"])
        exp_test = _hour_display(exp["test"])
        exp_rt = exp["rt"] if exp["rt"] is not None else _rt_expected(exp_rd, exp_test)
        for field, a, b in (
            ("rd", rec.get("rd"), exp_rd),
            ("test", rec.get("test"), exp_test),
            ("rt", rec.get("rt"), exp_rt),
        ):
            if a is None and b is None:
                continue
            if a is None or b is None or abs(float(a) - float(b)) > 0.011:
                errors.append(
                    f"主站 {sid} {field} 不一致: record={a} expected={b}"
                )
        rt_calc = _rt_expected(rec.get("rd"), rec.get("test"))
        if rec.get("rt") != rt_calc:
            errors.append(
                f"主站 {sid} rt 逻辑错误: stored={rec.get('rt')} calc={rt_calc}"
            )

    # ── 2. 全量 rt 字段自洽 + depts 结构 ──
    for rec in records:
        rt_calc = _rt_expected(rec.get("rd"), rec.get("test"))
        if rec.get("rt") != rt_calc:
            errors.append(
                f"{rec.get('module')} id={rec.get('id')} rt={rec.get('rt')} expected={rt_calc}"
            )
        depts = rec.get("depts")
        if not depts or not isinstance(depts, list):
            errors.append(f"id={rec.get('id')} 缺少 depts 列表")

    # ── 3. HTML 产物抽检（公式说明 + 锚点 + 全量 id 出现次数）──
    if not PORTFOLIO_HTML.is_file():
        errors.append(f"缺少 {PORTFOLIO_HTML}")
    else:
        html = PORTFOLIO_HTML.read_text(encoding="utf-8")
        if "formula-core-box" not in html:
            errors.append("HTML 缺少 formula-core-box 公式说明块")
        if "修正研发" not in html or "测试总估分(去除RD)" not in html:
            errors.append("HTML 公式文案缺失")
        if html.count("window.initDemandDetailOverview=function") < 1:
            errors.append("HTML 缺少 initDemandDetailOverview 脚本")
        id_hits = 0
        for rec in records:
            sid = str(rec.get("id"))
            if f'"id": "{sid}"' in html or f'"id":"{sid}"' in html:
                id_hits += 1
            else:
                errors.append(f"HTML 未嵌入 id={sid}")
        if id_hits != len(records):
            errors.append(f"HTML id 命中 {id_hits}/{len(records)}")
        for probe in (by_id.get("23430279"), main_recs[0] if main_recs else None):
            if probe and not _html_contains_record(html, probe):
                errors.append(f"HTML 锚点/首条字段不一致 id={probe.get('id')}")

    # ── 4. 锚点需求 23430279 ──
    anchor = by_id.get("23430279")
    if not anchor:
        errors.append("锚点需求 23430279 缺失")
    else:
        if anchor.get("rd") != 3.0 or anchor.get("test") != 3.5 or anchor.get("rt") != 0.86:
            errors.append(
                f"23430279 锚点异常: rd={anchor.get('rd')} test={anchor.get('test')} "
                f"rt={anchor.get('rt')}"
            )
        if anchor.get("qc") != "Fancy-QC" or anchor.get("dev_roles") != "Change":
            errors.append(f"23430279 角色列异常: {anchor}")

    # ── 5. 部门横向：1交易-交易组 主站参与口径 ──
    dept_target = "1交易-交易组"
    trade_main = [
        r for r in main_recs
        if dept_target in (r.get("depts") or [])
    ]
    tr_rd = sum(r["rd"] for r in trade_main if r.get("rt") is not None and r.get("rd") is not None)
    tr_tt = sum(r["test"] for r in trade_main if r.get("rt") is not None and r.get("test") is not None)
    tr_rt = round(tr_rd / tr_tt, 2) if tr_tt > TEST_FLOOR else None
    tr_rt_n = sum(1 for r in trade_main if r.get("rt") is not None)
    print(f"── 横向锚点 {dept_target} 主站 ──")
    print(
        f"  筛选 {len(trade_main)} 条 · 可算 {tr_rt_n} 条 · "
        f"Σ研发 {round(tr_rd, 1)} · Σ测试 {round(tr_tt, 1)} · R/T {tr_rt}"
    )

    # ── 6. 主站汇总 KPI ──
    tr = sum(r["rd"] for r in main_recs if r.get("rd") is not None)
    tt = sum(r["test"] for r in main_recs if r.get("test") is not None)
    print("── 校验摘要 ──")
    print(f"总记录: {len(records)}")
    print("模块分布:", dict(Counter(r["module"] for r in records)))
    print(f"主站 Σ修正研发: {round(tr, 1)}  Σ测试: {round(tt, 1)}  R/T: {round(tr/tt, 2)}")
    print(f"校验项错误数: {len(errors)}")
    if errors:
        print("\n── 错误明细（前 20 条）──")
        for e in errors[:20]:
            print(" ✗", e)
        if len(errors) > 20:
            print(f" ... 另有 {len(errors) - 20} 条")
        return 1
    print("✓ 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
