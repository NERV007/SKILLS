#!/usr/bin/env python3
"""Meegle 导出 CSV：按列索引读取（避免 DictReader 吞并列），work_item_id/storyID 去重并可选过滤。"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from _paths import DATA_DIR


def first_col_idx(header: list[str], *names: str) -> int | None:
    targets = {n.lower() for n in names}
    for i, h in enumerate(header):
        if (h or "").strip().lower() in targets:
            return i
    return None


def cell(row: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ""
    return (row[idx] or "").strip()


def row_key(
    row: list[str],
    wid_i: int | None,
    sid_i: int | None,
    story_ui_i: int | None,
) -> str | None:
    w = cell(row, wid_i)
    if w.isdigit():
        return f"w:{w}"
    s = cell(row, sid_i)
    if s.isdigit():
        return f"s:{s}"
    # 部分行只在嵌套列里有 storyID
    su = cell(row, story_ui_i)
    if su.isdigit():
        return f"s:{su}"
    return None


def parse_int(s: str) -> int | None:
    try:
        return int(str(s).strip())
    except (TypeError, ValueError):
        return None


def keep_row(
    row: list[str],
    idx: dict[str, int | None],
    *,
    story_only: bool,
) -> bool:
    wid_i = idx["work_item_id"]
    sid_i = idx["storyID"]
    tk_i = idx["type_key"]
    api_i = idx["api_name"]
    witk_i = idx["work_item_type_key"]
    wapi_i = idx["workItemAPIName"]
    name_i = idx["name"]

    w = cell(row, wid_i)
    sid = cell(row, sid_i)
    story_nested = cell(row, idx["storyID_nested"])

    if not w.isdigit() and not sid.isdigit() and not story_nested.isdigit():
        return False

    tk = cell(row, tk_i)
    api = cell(row, api_i)
    if tk == "chart" or api == "chart":
        return False

    nv = cell(row, name_i)
    if nv.startswith("i18n_bits_work_item_type"):
        return False

    if story_only:
        witk = cell(row, witk_i)
        if witk and witk not in ("project_story", "需求"):
            return False

    return True


def build_indices(header: list[str]) -> dict[str, int | None]:
    return {
        "work_item_id": first_col_idx(header, "work_item_id"),
        "storyID": first_col_idx(header, "storyid", "story_id"),
        "storyID_nested": first_col_idx(
            header,
            "uiDataMap.1l5clgkicafc2.uiValue.nameWithComment.storyID",
        ),
        "type_key": first_col_idx(header, "type_key"),
        "api_name": first_col_idx(header, "api_name"),
        "work_item_type_key": first_col_idx(header, "work_item_type_key"),
        "workItemAPIName": first_col_idx(
            header,
            "uiDataMap.1l5clgkicafc2.uiValue.nameWithComment.workItemAPIName",
        ),
        "name": first_col_idx(header, "name"),
        "updatedAt": first_col_idx(header, "updatedat", "updated_at"),
    }


def dedupe(
    rows: list[list[str]],
    idx: dict[str, int | None],
    *,
    keep: str,
) -> list[list[str]]:
    wid_i = idx["work_item_id"]
    sid_i = idx["storyID"]
    sn_i = idx["storyID_nested"]
    up_i = idx["updatedAt"]

    order: list[str] = []
    best: dict[str, list[str]] = {}

    for row in rows:
        k = row_key(row, wid_i, sid_i, sn_i)
        if not k:
            continue
        if k not in best:
            order.append(k)
            best[k] = row
            continue
        old = best[k]
        if keep == "first":
            continue
        if up_i is not None:
            ou = parse_int(cell(old, up_i))
            nu = parse_int(cell(row, up_i))
            if nu is not None and ou is not None and nu >= ou:
                best[k] = row
            elif nu is not None and ou is None:
                best[k] = row
        else:
            best[k] = row

    return [best[k] for k in order]


def main() -> None:
    ap = argparse.ArgumentParser(description="Meegle CSV 去重与过滤")
    ap.add_argument(
        "input",
        type=Path,
        nargs="?",
        default=DATA_DIR / "meegle_page_export.csv",
    )
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--keep", choices=("first", "last"), default="last")
    ap.add_argument(
        "--story-only",
        action="store_true",
        help="只保留 work_item_type_key 为空或为 project_story 的行（忽略 workflow 等 UI API 名）",
    )
    ap.add_argument(
        "--in-place",
        action="store_true",
        help="覆盖输入文件（会先写到临时文件再替换）",
    )
    args = ap.parse_args()
    inp = args.input
    if not inp.is_file():
        print(f"找不到文件: {inp}", file=sys.stderr)
        sys.exit(1)

    out = args.output
    if args.in_place:
        out = inp.with_suffix(".csv.tmp")
    elif out is None:
        out = inp.with_name(inp.stem + "_deduped.csv")

    with inp.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        body = list(reader)

    idx = build_indices(header)
    filtered = [r for r in body if keep_row(r, idx, story_only=args.story_only)]
    result_rows = dedupe(filtered, idx, keep=args.keep)

    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(result_rows)

    if args.in_place:
        out.replace(inp)
        out = inp

    print(
        f"输入 {len(body)} 行 → 过滤后 {len(filtered)} 行 → 去重后 {len(result_rows)} 行 → {out}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
