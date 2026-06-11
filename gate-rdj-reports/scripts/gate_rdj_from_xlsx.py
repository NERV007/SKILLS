#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gate-RDJ：Excel 导出 → CSV → HTML 报告（一键入口）。

示例：
  python3 scripts/gate_rdj_from_xlsx.py --xlsx ~/Downloads/需求导出-Gate-RDJ\\ \\(10\\).xlsx
  python3 scripts/gate_rdj_from_xlsx.py --xlsx ~/Downloads/需求导出-Gate-RDJ\\ \\(10\\).xlsx --dimension time
  python3 scripts/gate_rdj_from_xlsx.py --regenerate   # 仅用现有根目录 CSV 重生成报告
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _paths import REPO_ROOT  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = REPO_ROOT
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from generate_gate_rdj_from_csv import (  # noqa: E402
    ROOT as GEN_ROOT,
    build_merged_report_shell,
    discover_dimension_csvs,
    write_dimension_bundle,
)
from gate_rdj_metrics import build_data_payload, filter_rows_for_time_axis, load_rows  # noqa: E402

TIME_CSV = ROOT / "需求导出-Gate-RDJ_时间维度.csv"
ITER_CSV = ROOT / "需求导出-Gate-RDJ_迭代维度.csv"
DATA_DIR = ROOT / "data"


def _version_from_path(path: Path) -> str | None:
    m = re.search(r"\((\d+)\)", path.name, re.I)
    return m.group(1) if m else None


def _dim_tag_from_path(path: Path) -> str:
    if "时间" in path.name:
        return "时间维度"
    if "迭代" in path.name:
        return "迭代维度"
    return ""


def xlsx_to_csv(
    xlsx: Path,
    *,
    sync_time: bool = False,
    sync_iter: bool = False,
    archive_suffix: str = "",
) -> Path:
    try:
        import pandas as pd
    except ImportError as e:
        raise SystemExit("需要 pandas：pip install pandas openpyxl") from e

    df = pd.read_excel(xlsx, sheet_name=0)
    ref = TIME_CSV if TIME_CSV.exists() else ITER_CSV
    if ref.exists():
        ref_cols = pd.read_csv(ref, encoding="utf-8-sig", nrows=0).columns.tolist()
        cols = [c for c in ref_cols if c in df.columns]
        extra = [c for c in df.columns if c not in cols]
        df = df[cols + extra]

    ver = _version_from_path(xlsx)
    dim_tag = archive_suffix or _dim_tag_from_path(xlsx)
    name = f"需求导出-Gate-RDJ-{ver or 'latest'}"
    if dim_tag:
        name += f"-{dim_tag}"
    archive = DATA_DIR / f"{name}.csv"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(archive, index=False, encoding="utf-8-sig")
    print("Wrote archive", archive)

    if sync_time:
        df.to_csv(TIME_CSV, index=False, encoding="utf-8-sig")
        print("Wrote", TIME_CSV)
    if sync_iter:
        df.to_csv(ITER_CSV, index=False, encoding="utf-8-sig")
        print("Wrote", ITER_CSV)

    return archive


def print_metrics(csv_path: Path, period_axis: str) -> None:
    rows = load_rows(str(csv_path))
    if period_axis == "month":
        rows = filter_rows_for_time_axis(rows)
    data, _, label, _ = build_data_payload(rows, period_axis=period_axis)
    ss = data.get("summary_stats", {})
    print(f"  口径: {label}  横轴: {data.get('months', [])}")
    print(f"  有效需求: {len(rows)}  业务线: {ss.get('biz_count')}  R/T: {ss.get('avg_rt_ratio')}")


def regenerate(dimensions: list[str], merged: bool) -> None:
    mapping = {
        "time": (TIME_CSV, "Gate-RDJ-时间维度", "month"),
        "iteration": (ITER_CSV, "Gate-RDJ-迭代维度", "iteration"),
    }
    for dim in dimensions:
        csv_path, prefix, axis = mapping[dim]
        if not csv_path.is_file():
            print("Skip (missing CSV):", csv_path, file=sys.stderr)
            continue
        write_dimension_bundle(str(csv_path), prefix, forced_axis=axis)
        print_metrics(csv_path, axis)

    if merged:
        prefixes = [p for path, p, _ in discover_dimension_csvs() if Path(path).is_file()]
        html = build_merged_report_shell(prefixes)
        if html:
            out = Path(GEN_ROOT) / "Gate-RDJ-综合维度-统一报告.html"
            out.write_text(html, encoding="utf-8")
            print("Wrote", out)


def main() -> None:
    ap = argparse.ArgumentParser(description="Gate-RDJ：xlsx → CSV → HTML 报告")
    ap.add_argument("--xlsx", type=str, default="", help="单文件：同时用于所选维度")
    ap.add_argument("--xlsx-time", type=str, default="", help="时间维专用 xlsx")
    ap.add_argument("--xlsx-iteration", type=str, default="", help="迭代维专用 xlsx")
    ap.add_argument(
        "--dimension",
        choices=["time", "iteration", "both"],
        default="time",
        help="同步/生成哪个维度（默认 time）",
    )
    ap.add_argument(
        "--regenerate",
        action="store_true",
        help="不读 xlsx，仅用现有 CSV 重生成 HTML",
    )
    ap.add_argument("--no-merged", action="store_true", help="不更新综合维度统一入口")
    args = ap.parse_args()

    dims = ["time", "iteration"] if args.dimension == "both" else [args.dimension]

    if args.regenerate:
        regenerate(dims, merged=not args.no_merged)
        return

    if args.xlsx_time or args.xlsx_iteration:
        if args.xlsx:
            ap.error("请使用 --xlsx-time / --xlsx-iteration，或与 --xlsx 二选一")
        if args.xlsx_time:
            p = Path(args.xlsx_time).expanduser().resolve()
            if not p.is_file():
                raise SystemExit(f"文件不存在: {p}")
            xlsx_to_csv(p, sync_time=True, sync_iter=False)
        if args.xlsx_iteration:
            p = Path(args.xlsx_iteration).expanduser().resolve()
            if not p.is_file():
                raise SystemExit(f"文件不存在: {p}")
            xlsx_to_csv(p, sync_time=False, sync_iter=True)
        reg_dims = []
        if args.xlsx_time:
            reg_dims.append("time")
        if args.xlsx_iteration:
            reg_dims.append("iteration")
        regenerate(reg_dims or dims, merged=not args.no_merged)
        return

    if not args.xlsx:
        ap.error("请指定 --xlsx、--xlsx-time/--xlsx-iteration，或使用 --regenerate")

    xlsx = Path(args.xlsx).expanduser().resolve()
    if not xlsx.is_file():
        raise SystemExit(f"文件不存在: {xlsx}")

    sync_time = "time" in dims
    sync_iter = "iteration" in dims
    xlsx_to_csv(xlsx, sync_time=sync_time, sync_iter=sync_iter)
    regenerate(dims, merged=not args.no_merged)


if __name__ == "__main__":
    main()
