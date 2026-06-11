#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 QC（角色 multi-user）聚合 meegle_page_export.csv；支持测试节点人日、总估分。

Meegle 中 QC 字段对应视图聚合键「1l5n0fktf4wf6」（label: QC）。
若当前导出未含该列（常见于多项目视图未勾选 QC），可使用 --proxy creator 按创建人临时拆分。
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from _paths import DATA_DIR, REPO_ROOT

_REPO_ROOT = REPO_ROOT

K_TEST = "uiDataMap.4364c1569f37ceb8203ab885d5358656.uiValue.number.value"
K_TOTAL = "uiDataMap.1l5clgkicgqw2.uiValue.number.value"
K_QC_UUID = "1l5n0fktf4wf6"
K_CREATOR = "uiDataMap.1l5clgkicbtwi.uiValue.user.value"


def fnum(x: str | None) -> float:
    if not x or not str(x).strip():
        return 0.0
    try:
        return float(str(x).replace(",", ""))
    except ValueError:
        return 0.0


def discover_qc_value_column(fieldnames: list[str]) -> str | None:
    """匹配 uiDataMap.<QC_UUID>....roleMultiUser.value"""
    for name in fieldnames:
        if K_QC_UUID not in name:
            continue
        if name.endswith("roleMultiUser.value"):
            return name
    return None


def parse_role_multi_user_names(raw: str | None) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    names = []
    for u in data:
        if not isinstance(u, dict):
            continue
        n = u.get("name_cn") or u.get("name_en") or u.get("email")
        if n:
            names.append(str(n).strip())
    return names


def is_qc_user(u: dict) -> bool:
    """QC 角色字段里有时会混入其它职能账号，仅保留明显 QC。"""
    email = (u.get("email") or "").lower()
    if "-qc@" in email or email.endswith("qc@gate.me"):
        return True
    for k in ("name_cn", "name_en"):
        s = u.get(k) or ""
        if not isinstance(s, str):
            continue
        sl = s.lower()
        if "-qc" in sl or "_qc" in sl or "qc-rdj" in sl or "-qc-" in sl:
            return True
    return False


def parse_qc_role_names(raw: str | None) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    names: list[str] = []
    for u in data:
        if not isinstance(u, dict):
            continue
        if not is_qc_user(u):
            continue
        n = u.get("name_cn") or u.get("name_en") or u.get("email")
        if n:
            names.append(str(n).strip())
    return names


def bucket_qc_names(names: list[str]) -> str:
    if not names:
        return "(未分配)"
    return "|".join(names)


def parse_creator_bucket(raw: str | None) -> str:
    names = parse_role_multi_user_names(raw)
    return names[0] if names else "(创建人空)"


def load_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        return list(reader), list(fields)


def main() -> None:
    ap = argparse.ArgumentParser(description="Meegle CSV 按 QC 聚合")
    ap.add_argument(
        "csv_path",
        nargs="?",
        default=str(_REPO_ROOT / "data" / "meegle_page_export.csv"),
    )
    ap.add_argument(
        "-o",
        "--output",
        default=str(_REPO_ROOT / "data" / "meegle_aggregate_by_qc.csv"),
    )
    ap.add_argument(
        "--proxy",
        choices=("none", "creator"),
        default="none",
        help="无 QC 列时：creator=按创建人拆分（临时口径）",
    )
    args = ap.parse_args()

    src = Path(args.csv_path)
    out = Path(args.output)
    rows, fieldnames = load_rows(src)
    qc_col = discover_qc_value_column(fieldnames)

    agg: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {"story_count": 0, "test_pd": 0.0, "total_pd": 0.0}
    )
    dimension = "QC"

    if qc_col:
        for r in rows:
            names = parse_qc_role_names(r.get(qc_col))
            key = bucket_qc_names(names)
            agg[key]["story_count"] += 1
            agg[key]["test_pd"] = float(agg[key]["test_pd"]) + fnum(r.get(K_TEST))
            agg[key]["total_pd"] = float(agg[key]["total_pd"]) + fnum(r.get(K_TOTAL))
    elif args.proxy == "creator":
        dimension = "创建人(代理)"
        for r in rows:
            key = parse_creator_bucket(r.get(K_CREATOR))
            agg[key]["story_count"] += 1
            agg[key]["test_pd"] = float(agg[key]["test_pd"]) + fnum(r.get(K_TEST))
            agg[key]["total_pd"] = float(agg[key]["total_pd"]) + fnum(r.get(K_TOTAL))
    else:
        dimension = "QC(导出未含列·汇总)"
        all_test = sum(fnum(r.get(K_TEST)) for r in rows)
        agg["_导出缺少QC列_请先视图勾选QC后重抓"] = {
            "story_count": len(rows),
            "test_pd": all_test,
            "total_pd": sum(fnum(r.get(K_TOTAL)) for r in rows),
        }

    all_test = sum(float(m["test_pd"]) for m in agg.values())
    out_rows: list[dict[str, str | float | int]] = []
    for bucket, m in sorted(agg.items(), key=lambda x: -float(x[1]["test_pd"])):
        tp = float(m["test_pd"])
        tt = float(m["total_pd"])
        out_rows.append(
            {
                "dimension": dimension,
                "qc_bucket": bucket,
                "story_count": int(m["story_count"]),
                "test_pd_sum": round(tp, 2),
                "total_pd_sum": round(tt, 2),
                "total_over_test": round(tt / tp, 4) if tp else "",
                "test_share_pct": round(100.0 * tp / all_test, 2) if all_test else "",
            }
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    fn = [
        "dimension",
        "qc_bucket",
        "story_count",
        "test_pd_sum",
        "total_pd_sum",
        "total_over_test",
        "test_share_pct",
    ]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fn)
        w.writeheader()
        for row in out_rows:
            w.writerow(row)

    print(f"已写入 {out} ，dimension={dimension} ，共 {len(out_rows)} 行")
    if not qc_col:
        print(
            "提示: 当前 CSV 未发现 QC 列 (uiDataMap.*1l5n0fktf4wf6*roleMultiUser.value)。"
            "请在飞书项目多项目视图中勾选「QC」列后重新抓取；或临时使用: "
            f"python3 {Path(__file__).name} --proxy creator",
        )


if __name__ == "__main__":
    main()
