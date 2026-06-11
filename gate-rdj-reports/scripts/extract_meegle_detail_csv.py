#!/usr/bin/env python3
"""从 meegle_page_capture.json 仅抽取 data.work_item_detail_v2，生成干净的 CSV（修复错误混入其它接口数组的问题）。"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from _paths import DATA_DIR


def flatten_obj(obj: object, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    if obj is None:
        out[prefix or "value"] = ""
        return out
    if isinstance(obj, list):
        out[prefix or "items"] = json.dumps(obj, ensure_ascii=False)
        return out
    if not isinstance(obj, dict):
        out[prefix or "value"] = str(obj)
        return out
    for k, v in obj.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten_obj(v, key))
        elif isinstance(v, list):
            out[key] = json.dumps(v, ensure_ascii=False)
        else:
            out[key] = "" if v is None else str(v)
    return out


def extract_detail_v2_rows(capture_body: dict) -> list[dict]:
    data = capture_body.get("data")
    if not isinstance(data, dict):
        return []
    v2 = data.get("work_item_detail_v2")
    if not isinstance(v2, dict):
        return []
    rows: list[dict] = []
    for arr in v2.values():
        if not isinstance(arr, list):
            continue
        for row in arr:
            if isinstance(row, dict):
                rows.append(row)
    return rows


def dedupe(rows: list[dict]) -> list[dict]:
    m: dict[str, dict] = {}
    for row in rows:
        wid = row.get("work_item_id")
        sid = row.get("storyID")
        key = None
        if wid is not None and str(wid).strip() != "":
            key = f"w:{wid}"
        elif sid is not None and str(sid).strip() != "":
            key = f"s:{sid}"
        if not key:
            continue
        prev = m.get(key)
        ua = row.get("updatedAt")
        pa = prev.get("updatedAt") if prev else None
        if prev is None:
            m[key] = row
        elif isinstance(ua, int) and isinstance(pa, int) and ua >= pa:
            m[key] = row
        elif isinstance(ua, int) and not isinstance(pa, int):
            m[key] = row
    return list(m.values())


def rows_to_csv(rows: list[dict]) -> str:
    if not rows:
        return ""
    flats = [flatten_obj(r) for r in rows]
    keys: list[str] = []
    seen: set[str] = set()
    for fl in flats:
        for k in fl:
            if k not in seen:
                seen.add(k)
                keys.append(k)

    def esc(s: str) -> str:
        if any(c in s for c in '",\n\r'):
            return '"' + s.replace('"', '""') + '"'
        return s

    lines = [",".join(esc(k) for k in keys)]
    for fl in flats:
        lines.append(",".join(esc(fl.get(k, "")) for k in keys))
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "capture_json",
        type=Path,
        nargs="?",
        default=DATA_DIR / "meegle_page_capture.json",
    )
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="默认写入 data/meegle_page_export.csv",
    )
    args = ap.parse_args()
    inp = args.capture_json
    out = args.output or DATA_DIR / "meegle_page_export.csv"
    if not inp.is_file():
        print(f"找不到 {inp}", file=sys.stderr)
        sys.exit(1)

    raw = json.loads(inp.read_text(encoding="utf-8"))
    captures = raw.get("captures") or []
    all_rows: list[dict] = []
    hits = 0
    for cap in captures:
        body = cap.get("body") or {}
        rows = extract_detail_v2_rows(body)
        if rows:
            hits += 1
            all_rows.extend(rows)

    merged = dedupe(all_rows)
    csv_text = rows_to_csv(merged)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(csv_text, encoding="utf-8")

    print(
        f"work_item_detail_v2: {hits} 个响应, 原始行 {len(all_rows)}, 去重后 {len(merged)} → {out}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
