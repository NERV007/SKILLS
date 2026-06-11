#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按「测试」节点人日（视图 node_point 测试阶段）对 meegle_page_export.csv 做多维聚合。

默认输出 data/meegle_aggregate_by_test.csv
口径：测试 = uiDataMap.4364c1569…number.value；总估 = uiDataMap.1l5clgkicgqw2…number.value
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


K_TEST = "uiDataMap.4364c1569f37ceb8203ab885d5358656.uiValue.number.value"
K_TOTAL = "uiDataMap.1l5clgkicgqw2.uiValue.number.value"
K_COLLAB = "uiDataMap.1l5ggwqgi1hcx.uiValue.cascadeSelect.value"
K_ORIGIN = "uiDataMap.1lbv4asx1qqkz.uiValue.cascadeSelect.value"
K_PRIO = "uiDataMap.1l5clgkicb4ma.uiValue.select.value"


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


def prio_bucket(raw: str | None) -> str:
    if not raw or not str(raw).strip():
        return "(空)"
    try:
        j = json.loads(raw)
        if isinstance(j, list) and j:
            return str(j[0].get("label") or j[0].get("filterValue") or "?")
    except json.JSONDecodeError:
        pass
    return "?"


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def aggregate(
    rows: list[dict[str, str]],
    key_fn,
) -> dict[str, dict[str, float | int]]:
    g: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {"story_count": 0, "test_pd": 0.0, "total_pd": 0.0}
    )
    for r in rows:
        k = key_fn(r)
        g[k]["story_count"] += 1  # type: ignore
        g[k]["test_pd"] = float(g[k]["test_pd"]) + fnum(r.get(K_TEST))  # type: ignore
        g[k]["total_pd"] = float(g[k]["total_pd"]) + fnum(r.get(K_TOTAL))  # type: ignore
    return dict(g)


def main() -> None:
    ap = argparse.ArgumentParser(description="Meegle CSV 按测试维度聚合")
    ap.add_argument(
        "csv_path",
        nargs="?",
        default="data/meegle_page_export.csv",
        help="meegle_page_export.csv 路径",
    )
    ap.add_argument(
        "-o",
        "--output",
        default="data/meegle_aggregate_by_test.csv",
        help="输出聚合 CSV",
    )
    args = ap.parse_args()
    src = Path(args.csv_path)
    out = Path(args.output)
    rows = load_rows(src)
    all_test = sum(fnum(r.get(K_TEST)) for r in rows)

    out_rows: list[dict[str, str | float | int]] = []

    def add_dimension(dim: str, agg: dict[str, dict[str, float | int]]) -> None:
        for val, m in sorted(agg.items(), key=lambda x: -float(x[1]["test_pd"])):
            tp = float(m["test_pd"])
            tt = float(m["total_pd"])
            out_rows.append(
                {
                    "dimension": dim,
                    "bucket": val,
                    "story_count": int(m["story_count"]),
                    "test_pd_sum": round(tp, 2),
                    "total_pd_sum": round(tt, 2),
                    "total_over_test": round(tt / tp, 4) if tp else "",
                    "test_share_pct": round(100.0 * tp / all_test, 2) if all_test else "",
                }
            )

    add_dimension(
        "_全局",
        {
            "_全部": {
                "story_count": len(rows),
                "test_pd": all_test,
                "total_pd": sum(fnum(r.get(K_TOTAL)) for r in rows),
            }
        },
    )
    add_dimension("发起业务线", aggregate(rows, lambda r: cascade_bucket(r.get(K_ORIGIN))))
    add_dimension("协作业务线", aggregate(rows, lambda r: cascade_bucket(r.get(K_COLLAB))))
    add_dimension("优先级", aggregate(rows, lambda r: prio_bucket(r.get(K_PRIO))))

    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "dimension",
        "bucket",
        "story_count",
        "test_pd_sum",
        "total_pd_sum",
        "total_over_test",
        "test_share_pct",
    ]
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in out_rows:
            w.writerow(row)
    print(f"已写入 {out} ，共 {len(out_rows)} 行聚合记录（含全局）")


if __name__ == "__main__":
    main()
