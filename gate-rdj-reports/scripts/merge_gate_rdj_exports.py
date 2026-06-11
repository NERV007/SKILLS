#!/usr/bin/env python3
"""合并 Gate-RDJ-4 / Gate-RDJ-2 导出 CSV，去重并按业务线汇总（1 估分 = 1 工作日）。"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from _paths import DATA_DIR

CORE_COLS = [
    "名称",
    "价值类型",
    "全部节点估分",
    "优先级",
    "状态",
    "需求类型",
    "创建时间",
    "需求排期 截止时间",
    "完成日期",
    "计划开发时间",
    "计划测试时间",
    "预发测试排期",
    "技术方案设计与评审 估分",
    "研发总估分",
    "QC测试用例设计与评审 估分",
    "测试节点估分(去除 RD)",
    "测试 估分",
    "预发测试估分",
    "测试总估分(去除RD)",
    "QC",
    "总 bug 数",
    "是否紧急需求",
    "业务复杂度分级",
    "OKR权重",
    "所属子项目",
    "所属子项目 (ID)",
    "所属迭代",
    "所属迭代 (ID)",
    "冒烟是否通过",
    "冒烟打回次数",
    "FE开发 估分",
    "BE开发 估分",
    "APP开发 估分",
    "Engine开发 估分",
    "DATA开发 估分",
    "WS开发 估分",
    "WBE开发 估分",
    "Admin开发 估分",
    "需求链接",
]

NUM_COLS = [
    "全部节点估分",
    "技术方案设计与评审 估分",
    "研发总估分",
    "QC测试用例设计与评审 估分",
    "测试节点估分(去除 RD)",
    "测试 估分",
    "预发测试估分",
    "测试总估分(去除RD)",
    "总 bug 数",
    "冒烟打回次数",
    "FE开发 估分",
    "BE开发 估分",
    "APP开发 估分",
    "Engine开发 估分",
    "DATA开发 估分",
    "WS开发 估分",
    "WBE开发 估分",
    "Admin开发 估分",
]


def load_stories(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    cols = [c for c in CORE_COLS if c in raw.columns]
    df = raw[cols].copy()
    is_group = df["名称"].astype(str).str.match(r"^「.*」共\d+个$")
    return df[~is_group].copy()


def business_line_from_subproject(sub: object) -> str:
    """根据 Gate-RDJ-4 的「所属子项目」粗分业务线（顺序敏感）。"""
    if pd.isna(sub) or str(sub).strip() == "":
        return "未分类"
    s = str(sub)
    if "PAY" in s or "法币" in s:
        return "PAY"
    if "闪兑" in s:
        return "闪兑"
    if "合约" in s:
        return "合约"
    if "杠杆" in s or "EU站-支持杠杆" in s:
        return "现货/杠杆"
    if "现货引擎" in s:
        return "现货引擎"
    if "交易工具" in s:
        return "交易工具"
    if "行情" in s:
        return "行情"
    if "理财" in s:
        return "理财"
    if "打新" in s:
        return "打新"
    if "社交" in s:
        return "社交"
    if "SEO" in s or "学院" in s:
        return "SEO"
    if any(
        k in s
        for k in (
            "返佣",
            "营销",
            "增长",
            "触达",
            "活动",
            "投放",
            "定制活动",
            "卡券",
        )
    ):
        return "增长/营销"
    if "分站" in s:
        return "分站"
    return "其他"


def coerce_numeric(df: pd.DataFrame) -> None:
    for c in NUM_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DATA_DIR,
    )
    args = parser.parse_args()
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    p4 = out_dir / "需求导出-Gate-RDJ-4.csv"
    p2 = out_dir / "需求导出-Gate-RDJ-2.csv"

    s4 = load_stories(p4)
    s2 = load_stories(p2)
    s4["数据源"] = "Gate-RDJ-4"
    s4["业务线"] = s4["所属子项目"].map(business_line_from_subproject)
    # 子项目为空时按名称兜底（导出缺字段）
    miss = s4["业务线"].eq("未分类") & s4["名称"].astype(str).str.contains("CandyDrop", na=False)
    s4.loc[miss, "业务线"] = "增长/营销"
    s2["数据源"] = "Gate-RDJ-2"
    s2["业务线"] = "PAY"

    merged = pd.concat([s4, s2], ignore_index=True)
    dup_before = int(merged["需求链接"].duplicated().sum())
    merged = merged.drop_duplicates(subset=["需求链接"], keep="first")
    coerce_numeric(merged)

    out_merged = out_dir / "需求导出-Gate-RDJ_merged.csv"
    merged.to_csv(out_merged, index=False, encoding="utf-8-sig")

    g = merged.groupby("业务线", dropna=False)
    rows = []
    for line, part in g:
        rd = float(part["研发总估分"].fillna(0).sum())
        te = float(part["测试总估分(去除RD)"].fillna(0).sum())
        rows.append(
            {
                "业务线": line,
                "需求条数": len(part),
                "全部节点_工作日": float(part["全部节点估分"].fillna(0).sum()),
                "研发_工作日": rd,
                "测试去RD_工作日": te,
                "研发加测试_工作日": rd + te,
                "总bug数": float(part["总 bug 数"].fillna(0).sum()),
            }
        )
    by_line = pd.DataFrame(rows).sort_values("全部节点_工作日", ascending=False)
    by_line["全部节点占比"] = (by_line["全部节点_工作日"] / by_line["全部节点_工作日"].sum() * 100).round(1)

    out_summary = out_dir / "需求导出-Gate-RDJ_merged_by_业务线.csv"
    by_line.to_csv(out_summary, index=False, encoding="utf-8-sig")

    # 简要说明文件
    note = out_dir / "需求导出-Gate-RDJ_merged_README.txt"
    note.write_text(
        "\n".join(
            [
                "合并规则:",
                f"- Gate-RDJ-4: {len(s4)} 条；业务线由「所属子项目」关键词映射；名称含 CandyDrop 且子项目为空时归为增长/营销（见 scripts/merge_gate_rdj_exports.py）。",
                f"- Gate-RDJ-2: {len(s2)} 条；业务线固定为 PAY。",
                f"- 按「需求链接」去重: 合并前重复 {dup_before} 条，合并后 {len(merged)} 条。",
                "- 1 估分 = 1 工作日。",
                "",
                f"输出: {out_merged.name}, {out_summary.name}",
            ]
        ),
        encoding="utf-8",
    )

    print(f"merged rows: {len(merged)} (dedup removed {dup_before})")
    print(by_line.to_string(index=False))
    print(f"wrote {out_merged}")
    print(f"wrote {out_summary}")
    print(f"wrote {note}")


if __name__ == "__main__":
    main()
