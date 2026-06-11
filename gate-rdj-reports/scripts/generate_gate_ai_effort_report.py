#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从「需求导出-Gate-AI项目集」xlsx 生成 HTML 速览报告。

读法与叙事顺序参考同仓库 Gate-RDJ-QC人员-P9人效环比与建议报告.html（先看测试嵌入与 R/T，再落到 QC）。
Gate-AI 导出字段远少于 Gate-RDJ CSV，不能与 P9 数值对标；报告内写明差异，结论仅供参考。

口径：总估算人日按开发/测试参与人数分摊；R/T=研发分摊÷测试分摊（非 P9 的修正研发÷测试工时）。
QC 归因：仅「执行 QC」列 + department_stats 白名单（QCO 不参与摊分，见脚本注释）。
"""
from __future__ import annotations

import html as html_module
import json
import os
import re
import sys
from datetime import datetime
from html import unescape
from typing import Dict, List, Set, Tuple
from urllib.error import URLError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from generate_gate_rdj_from_csv import (  # noqa: E402
    DEPARTMENT_STATS_LOCAL_CANDIDATES,
    DEPARTMENT_STATS_URL,
    _DepartmentTableParser,
    _normalize_qc_token,
    _qc_group_mapping_from_html,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
from _paths import REPO_ROOT

ROOT = str(REPO_ROOT)
DEFAULT_XLSX = os.path.expanduser("~/Downloads/需求导出-Gate-AI项目集 (1).xlsx")
OUT_HTML = os.path.join(ROOT, "Gate-AI项目集-测试工时与RT分析报告.html")
OUT_PROJECT_DELIVERY_CSV = os.path.join(ROOT, "Gate-AI项目集-各项目需求数与平均交付时间.csv")
ECHARTS = os.path.join(ROOT, "vendor", "echarts-5.4.3.min.js")
# QC 个人维度：汇总测试人日低于此阈值时不展示 R/T（与 P9「测试工时>0.05」同一数量级，避免除零放大）
QC_RT_TEST_FLOOR = 0.05


def _load(path: str) -> pd.DataFrame:
    return pd.read_excel(path)


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    need = ["名称", "所属项目", "总估算工作量(人/日)", "开发参与人数", "测试参与人数", "创建者"]
    d = df.dropna(subset=need).copy()
    if "当前负责人" in d.columns:
        d["当前负责人"] = d["当前负责人"].fillna("").astype(str)
    else:
        d["当前负责人"] = ""
    if "QC" in d.columns:
        d["QC"] = d["QC"].fillna("").astype(str)
    else:
        d["QC"] = ""
    if "QCO" in d.columns:
        d["QCO"] = d["QCO"].fillna("").astype(str)
    else:
        d["QCO"] = ""
    d["dev"] = d["开发参与人数"].fillna(0).astype(float)
    d["test"] = d["测试参与人数"].fillna(0).astype(float)
    d["head_sum"] = d["dev"] + d["test"]
    d.loc[d["head_sum"] <= 0, "head_sum"] = np.nan
    d["est"] = d["总估算工作量(人/日)"].fillna(0).astype(float)
    d["est_dev"] = d["est"] * (d["dev"] / d["head_sum"])
    d["est_test"] = d["est"] * (d["test"] / d["head_sum"])
    return d


def _agg(
    d: pd.DataFrame, by: str, name_col: str = "名称"
) -> pd.DataFrame:
    g = (
        d.groupby(by, dropna=False)
        .agg(reqs=(name_col, "count"), est_total=("est", "sum"), est_dev=("est_dev", "sum"), est_test=("est_test", "sum"))
        .reset_index()
    )
    g["test_pct"] = np.where(g["est_total"] > 0, g["est_test"] / g["est_total"] * 100.0, np.nan)
    g["r_div_t"] = np.where(g["est_test"] > 0, g["est_dev"] / g["est_test"], np.nan)
    # 按测试聚合排序：优先测试分摊人日，其次总估算人日
    return g.sort_values(["est_test", "est_total"], ascending=[False, False])


def aggregate_project_delivery(df_raw: pd.DataFrame) -> pd.DataFrame:
    """按所属项目统计需求条数与交付耗时（自然日）= 完成日期 − 创建时间。

    仅当创建时间、完成日期均可解析且完成≥创建时计入「可计交付」子集；否则该条不参与均值/中位。
    """
    need = ["名称", "所属项目"]
    if not all(c in df_raw.columns for c in need):
        return pd.DataFrame(
            columns=["所属项目", "需求数", "可计交付条数", "平均交付天数", "中位交付天数"]
        )
    d = df_raw.dropna(subset=need).copy()
    if "创建时间" not in d.columns or "完成日期" not in d.columns:
        return pd.DataFrame(
            columns=["所属项目", "需求数", "可计交付条数", "平均交付天数", "中位交付天数"]
        )
    d["创建时间"] = pd.to_datetime(d["创建时间"], errors="coerce")
    d["完成日期"] = pd.to_datetime(d["完成日期"], errors="coerce")
    d["lead_days"] = (d["完成日期"] - d["创建时间"]).dt.days
    bad = d["创建时间"].isna() | d["完成日期"].isna() | d["lead_days"].isna() | (d["lead_days"] < 0)
    d.loc[bad, "lead_days"] = np.nan

    def _n_valid(s: pd.Series) -> int:
        return int(s.notna().sum())

    g = (
        d.groupby("所属项目", dropna=False)
        .agg(
            需求数=("名称", "count"),
            可计交付条数=("lead_days", _n_valid),
            平均交付天数=("lead_days", "mean"),
            中位交付天数=("lead_days", "median"),
        )
        .reset_index()
    )
    g["平均交付天数"] = g["平均交付天数"].round(2)
    g["中位交付天数"] = g["中位交付天数"].round(2)
    return g.sort_values("需求数", ascending=False)


def lead_days_valid_series(df_raw: pd.DataFrame) -> pd.Series:
    """每条需求的交付天数（自然日），无效则为 NaN。"""
    need = ["名称", "所属项目"]
    if not all(c in df_raw.columns for c in need):
        return pd.Series(dtype=float)
    if "创建时间" not in df_raw.columns or "完成日期" not in df_raw.columns:
        return pd.Series(dtype=float)
    d = df_raw.dropna(subset=need).copy()
    d["创建时间"] = pd.to_datetime(d["创建时间"], errors="coerce")
    d["完成日期"] = pd.to_datetime(d["完成日期"], errors="coerce")
    d["lead_days"] = (d["完成日期"] - d["创建时间"]).dt.days
    bad = d["创建时间"].isna() | d["完成日期"].isna() | d["lead_days"].isna() | (d["lead_days"] < 0)
    d.loc[bad, "lead_days"] = np.nan
    return d["lead_days"]


def load_department_stats_html() -> str:
    """与 generate_gate_rdj_from_csv 一致：先拉 URL，再读本地候选。"""
    req = Request(
        DEPARTMENT_STATS_URL,
        headers={"User-Agent": "Gate-AI-effort-report/1.0 (+https://report.dev.halftrust.xyz/)"},
    )
    try:
        with urlopen(req, timeout=45) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except (OSError, URLError) as exc:
        print(f"Warn: 未能拉取 department_stats（{exc}），尝试本地文件", file=sys.stderr)

    for raw_path in DEPARTMENT_STATS_LOCAL_CANDIDATES:
        if not raw_path:
            continue
        path = os.path.expanduser(raw_path)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                txt = f.read()
            if txt.strip():
                print(f"Note: department_stats 来自本地 {path}", file=sys.stderr)
                return txt
        except OSError as exc:
            print(f"Warn: 读取 {path} 失败 ({exc})", file=sys.stderr)
    return ""


def qc_roster_sections(html: str) -> List[Tuple[str, List[str]]]:
    """解析 departmentTable，返回 [(大类-新分组, QC 显示名列表), ...]（表格行序）。"""
    if not html.strip():
        return []
    parser = _DepartmentTableParser()
    parser.feed(html)
    if not parser.headers or not parser.rows:
        return []
    try:
        idx_big = parser.headers.index("大类名称")
        idx_group = parser.headers.index("新分组")
        idx_qc = parser.headers.index("QC")
    except ValueError:
        return []
    sections: List[Tuple[str, List[str]]] = []
    for row in parser.rows:
        if len(row) <= max(idx_big, idx_group, idx_qc):
            continue
        big_name = row[idx_big][0].strip()
        group_name = re.sub(r"\s+", "", row[idx_group][0].strip())
        if not group_name:
            continue
        group_label = f"{big_name}-{group_name}" if big_name else group_name
        qc_names_raw = row[idx_qc][1].get("data-names", "[]")
        try:
            qc_names = json.loads(unescape(qc_names_raw))
        except json.JSONDecodeError:
            qc_names = []
        if qc_names:
            sections.append((group_label, [str(n) for n in qc_names]))
    return sections


def qc_allow_tokens(html: str) -> Set[str]:
    m = _qc_group_mapping_from_html(html)
    return set(m.keys())


def qc_token_display_and_group(
    roster: List[Tuple[str, List[str]]],
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """标准化 token -> 展示全名、-> department_stats 行对应分组标签（首次出现为准）。"""
    display: Dict[str, str] = {}
    group_of: Dict[str, str] = {}
    for group_label, names in roster:
        for name in names:
            raw = str(name).strip()
            tok = _normalize_qc_token(raw)
            if not tok:
                continue
            if tok not in display:
                display[tok] = raw
                group_of[tok] = group_label
    return display, group_of


def qc_exec_tokens_only(qc_field: object, allow: Set[str]) -> List[str]:
    """仅从「执行 QC」列解析白名单 token（支持 | / 逗号等），去重且保持书写顺序。

    **不含 QCO / 当前负责人 / 创建者**：业务上 QCO 多为测试 Owner 或协调，不等同执行；
    若把 QCO 与 QC 一起均分，会把未实际执行的需求摊到 Owner（例如 Beyonce 仅出现在 QCO 的多数行）。
    """
    found: List[str] = []
    s = str(qc_field or "").strip()
    if not s or s.lower() in ("-", "—", "nan", "none"):
        return found
    s = s.replace("｜", "|")
    for part in re.split(r"[|,/，、]+", s):
        part = part.strip()
        if not part or part.lower() in ("-", "—"):
            continue
        tok = _normalize_qc_token(part)
        if tok and tok in allow and tok not in found:
            found.append(tok)
    return found


def effort_split_for_qc_row(row: pd.Series) -> Tuple[float, float]:
    """QC 归因专用：将单行估算拆成研发/测试侧人日。

    - 测试参与人数 > 0：与全表一致，按 dev:test 比例分摊。
    - 测试参与人数 == 0 且该行会归到 QC：导出常漏填测试人数，用 **1 名虚拟测试 vs 开发人数** 分摊，
      避免「测≈0、研很大」导致个人 R/T 上千的假象（与业务线表仍用人头口径，二者可并存）。
    """
    est = float(row.get("est", 0) or 0)
    if est <= 0:
        return 0.0, 0.0
    dv = float(row.get("dev", 0) or 0)
    tv = float(row.get("test", 0) or 0)
    if tv > 0:
        s = dv + tv
        if s <= 0:
            return est, 0.0
        return est * dv / s, est * tv / s
    # tv == 0：虚拟 1 名测试参与分摊
    s = dv + 1.0
    if s <= 0:
        return 0.0, est
    return est * dv / s, est * 1.0 / s


def aggregate_project_attribution_coverage(d: pd.DataFrame, allow: Set[str]) -> pd.DataFrame:
    """按所属项目拆分：QC 列命中白名单的估算人日 vs 需业务线兜底的估算人日（同一行只计一侧）。"""
    parts: List[Dict[str, object]] = []
    for _, row in d.iterrows():
        toks = qc_exec_tokens_only(row.get("QC"), allow)
        bkey = _row_biz_key(row)
        est = float(row.get("est", 0) or 0)
        parts.append(
            {
                "所属项目": bkey,
                "est_qc": est if toks else 0.0,
                "est_fb": est if not toks else 0.0,
                "req_qc": 1 if toks else 0,
                "req_fb": 0 if toks else 1,
            }
        )
    if not parts:
        return pd.DataFrame(
            columns=["所属项目", "est_qc", "est_fb", "req_qc", "req_fb", "est_total", "qc_cov_pct"]
        )
    df = pd.DataFrame(parts)
    g = (
        df.groupby("所属项目", dropna=False)
        .agg(est_qc=("est_qc", "sum"), est_fb=("est_fb", "sum"), req_qc=("req_qc", "sum"), req_fb=("req_fb", "sum"))
        .reset_index()
    )
    g["est_total"] = g["est_qc"] + g["est_fb"]
    g["qc_cov_pct"] = np.where(g["est_total"] > 0, g["est_qc"] / g["est_total"] * 100.0, np.nan)
    return g


def _row_biz_key(row: pd.Series) -> str:
    biz = row.get("所属项目")
    return str(biz).strip() if pd.notna(biz) and str(biz).strip() else "（所属项目空）"


def data_health_metrics(d: pd.DataFrame, allow: Set[str], n_used: int, est_all: float, fallback_biz: pd.DataFrame) -> Dict[str, float]:
    """QC 列非空率、白名单命中条数占比、兜底估算占比等。"""
    n_nonempty = 0
    n_hit = 0
    for _, row in d.iterrows():
        s = str(row.get("QC") or "").strip()
        if s and s.lower() not in ("-", "—", "nan", "none"):
            n_nonempty += 1
        if qc_exec_tokens_only(row.get("QC"), allow):
            n_hit += 1
    fb_est = float(fallback_biz["est_total"].sum()) if not fallback_biz.empty else 0.0
    return {
        "n_nonempty": float(n_nonempty),
        "n_hit": float(n_hit),
        "qc_nonempty_pct": (n_nonempty / n_used * 100.0) if n_used else 0.0,
        "whitelist_hit_pct": (n_hit / n_used * 100.0) if n_used else 0.0,
        "fallback_est_pct": (fb_est / est_all * 100.0) if est_all > 0 else 0.0,
    }


def _median_safe(s: pd.Series) -> float:
    v = pd.to_numeric(s, errors="coerce").dropna()
    if v.empty:
        return float("nan")
    return float(v.median())


def html_qc_row_suggestions(
    r_div_t: float,
    test_pct: float,
    med_rt: float,
    med_tp: float,
) -> str:
    """类 P9「建议」列：与本期 QC 子集的中位对标，避免与 P9 全局数值混读。"""
    bits: List[str] = []
    if not (isinstance(r_div_t, float) and np.isnan(r_div_t)) and not (isinstance(med_rt, float) and np.isnan(med_rt)):
        if med_rt > 0 and r_div_t > med_rt * 1.3:
            bits.append(
                "个人 R/T 明显高于本期命中 QC 集合的中位：优先核对「测试参与人数=0」触发的虚拟测口径，再对齐估分与拆批。"
            )
        elif med_rt > 0 and r_div_t < med_rt * 0.55:
            bits.append("个人 R/T 明显低于中位：常见于测试分摊不低或样本量小，勿单独解读为研发风险低。")
    if not (isinstance(test_pct, float) and np.isnan(test_pct)) and not (isinstance(med_tp, float) and np.isnan(med_tp)):
        if test_pct > med_tp + 12:
            bits.append("测试点比（分摊）偏高：结合全表兜底占比，排查 QC 列未填是否把压力挤到少数可命中的人。")
        elif test_pct < med_tp - 12:
            bits.append("测试点比偏低：若需求偏研发主导可接受；若导出漏填测试人数则占比失真。")
    if not bits:
        bits.append("指标处于本期 QC 集合常见区间；务必与（一）业务线堆叠归因同读，不与 P9 个人表对标绝对值。")
    return "<br/>".join(html_module.escape(b) for b in bits)


def build_action_suggestions(health: Dict[str, float], n_fallback_reqs: int, n_used: int) -> List[str]:
    out: List[str] = []
    if health["whitelist_hit_pct"] < 50:
        out.append(
            f"仅约 {health['whitelist_hit_pct']:.0f}% 需求在 <code>QC</code> 列命中白名单；建议导出侧统一填写执行 QC，并与 department_stats 名单对齐拼写。"
        )
    if health["fallback_est_pct"] > 25:
        out.append(
            f"约 {health['fallback_est_pct']:.0f}% 估算人日落在业务线兜底（<code>QC</code> 空或未命中）；个人表与「谁测了」会偏弱，优先补全 <code>QC</code> 比纠结图表版式更有效。"
        )
    if health["qc_nonempty_pct"] - health["whitelist_hit_pct"] > 15:
        out.append(
            "<code>QC</code> 列有字但未命中白名单的比例较高：多为别名、英文名或未入库；可把常用写法补进 department_stats，或清洗导出。"
        )
    if n_fallback_reqs > 0 and health["whitelist_hit_pct"] >= 70:
        out.append(
            f"仍有 {n_fallback_reqs} 条需求走项目兜底，多为 <code>QC</code> 全空；<code>QCO</code> 不参与个人摊分（避免 Owner 虚高），若需个人维度可改填 <code>QC</code>。"
        )
    if not out:
        out.append("数据归因整体尚可；可关注测试参与人数为 0 的行的虚拟测规则是否与业务复盘预期一致。")
    return out


def aggregate_by_qc(
    d: pd.DataFrame, allow: Set[str]
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """按 QC 聚合；无法从 QC 列命中白名单的整行，按「所属项目」汇总到第二张表（与第一节同用人头分摊）。

    返回 (qc_df, fallback_by_项目_df)。fallback 使用 prepared 的 est_dev/est_test（开发:测试人数），
    **不用** QC 行的虚拟测试拆分，以便与（一）全量业务线口径一致。
    """
    acc: Dict[str, Dict[str, float]] = {}
    fb: Dict[str, Dict[str, float]] = {}

    for _, row in d.iterrows():
        toks = qc_exec_tokens_only(row.get("QC"), allow)
        est = float(row.get("est", 0) or 0)
        if not toks:
            ed = float(row["est_dev"]) if pd.notna(row["est_dev"]) else 0.0
            et = float(row["est_test"]) if pd.notna(row["est_test"]) else 0.0
            biz = row.get("所属项目")
            if pd.isna(biz) or str(biz).strip() == "":
                bkey = "（所属项目空）"
            else:
                bkey = str(biz).strip()
            if bkey not in fb:
                fb[bkey] = {"reqs": 0.0, "est": 0.0, "est_test": 0.0, "est_dev": 0.0}
            fb[bkey]["reqs"] += 1.0
            fb[bkey]["est"] += est
            fb[bkey]["est_test"] += et
            fb[bkey]["est_dev"] += ed
            continue
        ed, et = effort_split_for_qc_row(row)
        w = 1.0 / len(toks)
        for t in toks:
            if t not in acc:
                acc[t] = {"reqs": 0.0, "est": 0.0, "est_test": 0.0, "est_dev": 0.0}
            acc[t]["reqs"] += w
            acc[t]["est"] += est * w
            acc[t]["est_test"] += et * w
            acc[t]["est_dev"] += ed * w

    rows = []
    for tok, v in acc.items():
        rows.append(
            {
                "qc_token": tok,
                "reqs": v["reqs"],
                "est_total": v["est"],
                "est_test": v["est_test"],
                "est_dev": v["est_dev"],
            }
        )
    g = pd.DataFrame(rows)
    if not g.empty:
        g["test_pct"] = np.where(g["est_total"] > 0, g["est_test"] / g["est_total"] * 100.0, np.nan)
        g["r_div_t"] = np.where(
            g["est_test"] > QC_RT_TEST_FLOOR,
            g["est_dev"] / g["est_test"],
            np.nan,
        )
        g = g.sort_values(["est_test", "est_total"], ascending=[False, False])

    fb_rows = []
    for bkey, v in fb.items():
        fb_rows.append(
            {
                "所属项目": bkey,
                "reqs": v["reqs"],
                "est_total": v["est"],
                "est_test": v["est_test"],
                "est_dev": v["est_dev"],
            }
        )
    fb_df = pd.DataFrame(fb_rows)
    if not fb_df.empty:
        fb_df["test_pct"] = np.where(fb_df["est_total"] > 0, fb_df["est_test"] / fb_df["est_total"] * 100.0, np.nan)
        fb_df["r_div_t"] = np.where(
            fb_df["est_test"] > QC_RT_TEST_FLOOR,
            fb_df["est_dev"] / fb_df["est_test"],
            np.nan,
        )
        fb_df = fb_df.sort_values(["est_test", "est_total"], ascending=[False, False])
    return g, fb_df


def _fmt_pct(x: float) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    return f"{x:.1f}"


def _fmt_rt(x: float) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "—"
    return f"{x:.2f}"


def _fmt_num(x: float, d: int = 1) -> str:
    if isinstance(x, float) and np.isnan(x):
        return "—"
    return f"{float(x):.{d}f}"


def _html_roster_appendix(
    dept_url: str,
    sections: List[Tuple[str, List[str]]],
    dept_source_note: str,
) -> str:
    link = (
        f'<a href="{html_module.escape(dept_url)}" target="_blank" rel="noopener noreferrer">'
        f"{html_module.escape(dept_url)}</a>"
    )
    if not sections:
        return f"""<details class="method">
<summary>测试人员白名单（department_stats）</summary>
<p class="note">未能加载 department_stats 页面正文（网络或本地文件）。请执行：<code>curl -fsSL '{html_module.escape(dept_url)}' -o department_stats.html</code> 放在仓库根目录，或设置环境变量 <code>DEPARTMENT_STATS_HTML</code>。{html_module.escape(dept_source_note)}</p>
</details>"""

    blocks = []
    for group_label, names in sections:
        lis = "".join(f"<li>{html_module.escape(n)}</li>" for n in sorted(names))
        blocks.append(
            f"<div class='roster-block'><h4 class='roster-h4'>{html_module.escape(group_label)}</h4><ul class='roster-ul'>{lis}</ul></div>"
        )
    return f"""<details class="method">
<summary>测试人员白名单（与 department_stats 同源）</summary>
<p style="margin:8px 0 12px;font-size:13px;color:#475569;">以下分组与 QC 名单来自 {link} 中 <code>id=departmentTable</code> 的「大类名称 / 新分组 / QC」列，与 Gate-RDJ 报告 QC 白名单一致。{html_module.escape(dept_source_note)}</p>
<div class="roster-grid">{"".join(blocks)}</div>
</details>"""


def build_html(df_raw: pd.DataFrame, src_path: str, proj_delivery: pd.DataFrame | None = None) -> str:
    if proj_delivery is None:
        proj_delivery = aggregate_project_delivery(df_raw)

    dept_html = load_department_stats_html()
    roster = qc_roster_sections(dept_html)
    allow_qc = qc_allow_tokens(dept_html)
    n_qc_tokens = len(allow_qc)
    dept_source_note = (
        f"已解析 QC 标准化 token {n_qc_tokens} 个。"
        if n_qc_tokens
        else "未解析到 QC 映射（表结构可能变更）。"
    )

    d = _prepare(df_raw)
    by_biz = _agg(d, "所属项目")

    tok_display, tok_group = qc_token_display_and_group(roster)
    by_qc, fallback_biz = aggregate_by_qc(d, allow_qc)
    n_qc_with_rows = len(by_qc)
    n_fallback_reqs = int(round(float(fallback_biz["reqs"].sum()))) if not fallback_biz.empty else 0

    cov_df = aggregate_project_attribution_coverage(d, allow_qc)
    health = data_health_metrics(d, allow_qc, len(d), float(d["est"].sum()), fallback_biz)
    suggestions = build_action_suggestions(health, n_fallback_reqs, len(d))

    est_all = float(d["est"].sum())
    test_all = float(d["est_test"].sum())
    dev_all = float(d["est_dev"].sum())
    test_pct_all = (test_all / est_all * 100.0) if est_all > 0 else 0.0
    rt_all = (dev_all / test_all) if test_all > 0 else float("nan")

    actual_all_zero = bool((df_raw["总实际工作量(人/日)"].fillna(0) == 0).all())
    n_raw = len(df_raw)
    n_used = len(d)

    by_biz_enriched = by_biz.merge(
        cov_df[["所属项目", "est_qc", "est_fb", "req_qc", "req_fb", "qc_cov_pct"]],
        on="所属项目",
        how="left",
    )
    by_biz_enriched["est_qc"] = by_biz_enriched["est_qc"].fillna(0.0)
    by_biz_enriched["est_fb"] = by_biz_enriched["est_fb"].fillna(0.0)
    by_biz_enriched["req_qc"] = by_biz_enriched["req_qc"].fillna(0).astype(int)
    by_biz_enriched["req_fb"] = by_biz_enriched["req_fb"].fillna(0).astype(int)

    rows_biz = []
    for _, r in by_biz_enriched.iterrows():
        cov_cell = _fmt_pct(float(r["qc_cov_pct"])) if pd.notna(r.get("qc_cov_pct")) else "—"
        rows_biz.append(
            "<tr>"
            f"<td class='td-left'>{html_module.escape(str(r['所属项目']))}</td>"
            f"<td>{int(r['reqs'])}</td>"
            f"<td>{_fmt_num(r['est_total'], 1)}</td>"
            f"<td>{_fmt_num(float(r['est_qc']), 1)}</td>"
            f"<td>{_fmt_num(float(r['est_fb']), 1)}</td>"
            f"<td>{cov_cell}%</td>"
            f"<td>{int(r['req_qc'])}/{int(r['req_fb'])}</td>"
            f"<td>{_fmt_num(r['est_test'], 2)}</td>"
            f"<td>{_fmt_pct(r['test_pct'])}</td>"
            f"<td>{_fmt_rt(r['r_div_t'])}</td>"
            "</tr>"
        )

    med_rt_qc = _median_safe(by_qc["r_div_t"]) if not by_qc.empty else float("nan")
    med_tp_qc = _median_safe(by_qc["test_pct"]) if not by_qc.empty else float("nan")

    obs_bullets: List[str] = [
        f"本期 <strong>{health['whitelist_hit_pct']:.0f}%</strong> 需求在 <code>QC</code> 列命中白名单；约 <strong>{health['fallback_est_pct']:.0f}%</strong> 估算人日只能按「所属项目」兜底，<strong>个人维度会被系统性削弱</strong>。"
    ]
    if not by_biz.empty:
        bits = []
        for _, br in by_biz.head(3).iterrows():
            bits.append(
                f"{html_module.escape(str(br['所属项目']))}（测 {_fmt_num(float(br['est_test']), 1)} 人日）"
            )
        obs_bullets.append("测试分摊人日前三业务线（全表人头口径）：" + "；".join(bits) + "。")
    if not np.isnan(med_rt_qc):
        obs_bullets.append(
            f"命中 QC 个人的 <strong>R/T</strong> 中位数约 <strong>{_fmt_rt(med_rt_qc)}</strong>（本节内部对标用，<strong>≠ P9</strong> 全局中位）。"
        )
    obs_bullets.append(
        "<strong>无</strong>完成月 / 迭代 / 需求类型 / Bug / 修正研发字段——若要做 P9 同款「分月 + 分类 + 团队趋势」，请换 Gate-RDJ 导出跑 <code>generate_qc_p9_efficiency_report.py</code>。"
    )

    rows_qc: List[str] = []
    for _, r in by_qc.iterrows():
        tok = str(r["qc_token"])
        qname = tok_display.get(tok, tok)
        grp = tok_group.get(tok, "—")
        rtp = float(r["test_pct"]) if pd.notna(r["test_pct"]) else float("nan")
        rtr = float(r["r_div_t"]) if pd.notna(r["r_div_t"]) else float("nan")
        sug = html_qc_row_suggestions(rtr, rtp, med_rt_qc, med_tp_qc)
        rows_qc.append(
            "<tr>"
            f"<td class='td-left'>{html_module.escape(qname)}</td>"
            f"<td class='td-left' style='font-size:11px;color:#64748b'>{html_module.escape(grp)}</td>"
            f"<td>{_fmt_num(r['reqs'], 2)}</td>"
            f"<td>{_fmt_num(r['est_total'], 1)}</td>"
            f"<td>{_fmt_num(r['est_test'], 2)}</td>"
            f"<td>{_fmt_pct(r['test_pct'])}</td>"
            f"<td>{_fmt_rt(r['r_div_t'])}</td>"
            f"<td style='text-align:left;max-width:300px;font-size:11px;line-height:1.55;color:#334155'>{sug}</td>"
            "</tr>"
        )

    rows_fallback: List[str] = []
    for _, r in fallback_biz.iterrows():
        rows_fallback.append(
            "<tr>"
            f"<td class='td-left'>{html_module.escape(str(r['所属项目']))}</td>"
            f"<td>{int(round(float(r['reqs'])))}</td>"
            f"<td>{_fmt_num(r['est_total'], 1)}</td>"
            f"<td>{_fmt_num(r['est_test'], 2)}</td>"
            f"<td>{_fmt_pct(r['test_pct'])}</td>"
            f"<td>{_fmt_rt(r['r_div_t'])}</td>"
            "</tr>"
        )

    chart_cover_categories = [str(x) for x in by_biz_enriched["所属项目"].tolist()]
    chart_cover_est_qc = [round(float(x), 2) for x in by_biz_enriched["est_qc"]]
    chart_cover_est_fb = [round(float(x), 2) for x in by_biz_enriched["est_fb"]]
    cover_stack_max = max(
        [a + b for a, b in zip(chart_cover_est_qc, chart_cover_est_fb)] + [1.0]
    )
    cover_x_max = float(np.ceil(cover_stack_max / 10.0) * 10.0 + 10.0)

    roster_html = _html_roster_appendix(DEPARTMENT_STATS_URL, roster, dept_source_note)

    gen_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    echarts_src = "./vendor/echarts-5.4.3.min.js"
    if not os.path.isfile(ECHARTS):
        echarts_src = "https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"

    payload = {
        "coverCategories": chart_cover_categories,
        "coverEstQc": chart_cover_est_qc,
        "coverEstFb": chart_cover_est_fb,
        "coverXMax": cover_x_max,
    }

    obs_li_joined = "".join(f"<li>{b}</li>" for b in obs_bullets)
    sug_li_joined = "".join(f"<li>{s}</li>" for s in suggestions)

    rows_proj: List[str] = []
    for _, pr in proj_delivery.iterrows():
        avg = pr["平均交付天数"]
        med = pr["中位交付天数"]
        avg_s = _fmt_num(float(avg), 1) if pd.notna(avg) else "—"
        med_s = _fmt_num(float(med), 1) if pd.notna(med) else "—"
        rows_proj.append(
            "<tr>"
            f"<td class='td-left'>{html_module.escape(str(pr['所属项目']))}</td>"
            f"<td>{int(pr['需求数'])}</td>"
            f"<td>{int(pr['可计交付条数'])}</td>"
            f"<td>{avg_s}</td>"
            f"<td>{med_s}</td>"
            "</tr>"
        )
    ld_series = lead_days_valid_series(df_raw)
    n_ld_ok = int(ld_series.notna().sum())
    n_ld_total = int(len(ld_series))
    pct_ld_ok = (n_ld_ok / n_ld_total * 100.0) if n_ld_total else 0.0
    g_lead_mean = float(ld_series.mean()) if n_ld_ok else float("nan")
    g_lead_med = float(ld_series.median()) if n_ld_ok else float("nan")
    g_mean_s = _fmt_num(g_lead_mean, 2) if n_ld_ok else "—"
    g_med_s = _fmt_num(g_lead_med, 2) if n_ld_ok else "—"

    payload_json = json.dumps(payload, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Gate-AI 项目集 · QC 测试结构与 R/T（轻量版 · 骨架对齐 P9）</title>
<script src="{html_module.escape(echarts_src)}"></script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'PingFang SC','Microsoft YaHei',-apple-system,BlinkMacSystemFont,sans-serif;background:#f1f5f9;color:#1e293b;line-height:1.6;font-size:14px}}
.container{{max-width:1320px;margin:0 auto;padding:20px 20px 48px}}
h1{{text-align:center;color:#0c4a6e;margin-bottom:8px;font-size:23px;font-weight:800}}
.subtitle{{text-align:center;color:#64748b;font-size:13px;margin:0 0 12px}}
.lead{{color:#475569;font-size:13px;line-height:1.75;margin:0 0 16px;padding:0 4px}}
.tag{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:6px;background:#e0f2fe;color:#0369a1;margin-right:6px;font-weight:600}}
.meta{{margin-top:10px;padding:12px 14px;background:#fff;border:1px solid #e2e8f0;border-radius:10px;font-size:12px;color:#475569}}
.meta code{{background:#f1f5f9;padding:2px 6px;border-radius:4px;font-size:11px}}
.lex-table{{width:100%;font-size:12px;border-collapse:collapse}}
.lex-table th,.lex-table td{{border:1px solid #e2e8f0;padding:8px 10px;text-align:left;vertical-align:top}}
.lex-table th{{background:#f8fafc;width:18%;color:#475569}}
.section{{background:#fff;padding:16px;border-radius:12px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.section h2,.section-title{{font-size:15px;font-weight:700;color:#0c4a6e;margin:0 0 12px;padding-bottom:8px;border-bottom:2px solid #e2e8f0}}
.summary-cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:16px}}
.card{{background:#fff;padding:12px 8px;border-radius:10px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.06);border:1px solid #e2e8f0;min-width:0}}
.card h3{{font-size:11px;color:#64748b;margin-bottom:4px;font-weight:600}}
.card .value{{font-size:19px;font-weight:700;color:#0c4a6e}}
.card .value.test{{color:#0ea5e9}}
.card .sub{{font-size:10px;color:#94a3b8;margin-top:4px;line-height:1.35}}
.conclusion-box{{background:#f0fdf4;border:1px solid #86efac;border-radius:10px;padding:14px;margin-top:4px}}
.conclusion-title{{font-size:14px;font-weight:700;color:#166534;margin-bottom:8px}}
.brief-p{{font-size:13px;color:#334155;line-height:1.78;margin:0}}
.brief-ul{{margin:8px 0 0;padding-left:1.1rem;font-size:13px;color:#334155;line-height:1.75}}
.brief-ul li{{margin:6px 0}}
.grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:14px}}
@media(max-width:900px){{.grid-2{{grid-template-columns:1fr}}}}
.panel-blue{{background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;padding:14px}}
.panel-amber{{background:#fffbeb;border:1px solid #fde68a;border-radius:10px;padding:14px}}
.panel-title{{font-size:14px;font-weight:700;color:#0c4a6e;margin-bottom:8px}}
.chart{{width:100%;height:360px;margin-top:10px}}
.chart-tall{{height:400px}}
.table-wrap{{overflow:auto;margin-top:10px;max-height:560px;border:1px solid #e2e8f0;border-radius:8px}}
table.data{{width:100%;border-collapse:collapse;font-size:12px}}
table.data th,table.data td{{padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:center}}
table.data th:first-child,table.data td:first-child{{text-align:left}}
table.data th{{background:#f8fafc;font-weight:600;color:#475569}}
tr:hover td{{background:#fafafa}}
.note{{font-size:11px;color:#64748b;margin-top:8px;padding:8px;background:#f8fafc;border-radius:6px}}
footer{{text-align:center;font-size:12px;color:#94a3b8;margin-top:24px}}
details.method{{background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:12px 14px;margin-top:14px;font-size:13px;color:#475569}}
details.method summary{{cursor:pointer;font-weight:600;color:#0c4a6e;list-style:none}}
details.method summary::-webkit-details-marker{{display:none}}
details.method ul{{margin:10px 0 0 18px}}
.roster-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px;margin-top:10px}}
.roster-block{{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 12px}}
.roster-h4{{font-size:12px;color:#0c4a6e;margin-bottom:8px}}
.roster-ul{{margin:0;padding-left:18px;font-size:11px;color:#475569;max-height:200px;overflow-y:auto}}
.p9-ref-table{{width:100%;font-size:11px;border-collapse:collapse;margin-top:10px}}
.p9-ref-table th,.p9-ref-table td{{border:1px solid #e2e8f0;padding:8px;text-align:left;vertical-align:top}}
.p9-ref-table th{{background:#fefce8;color:#854d0e;font-weight:600;width:20%}}
</style>
</head>
<body>
<div class="container">
<header>
<h1>Gate-AI 项目集 · QC 测试结构与 R/T（轻量版）</h1>
<p class="subtitle">骨架参考 <a href="Gate-RDJ-QC人员-P9人效环比与建议报告.html">P9 报告</a> · 指标为 Gate-AI 可得字段近似 · <strong>勿与 P9 数值对标</strong></p>
<p class="lead"><span class="tag">总</span>摘要与交付快照 → <span class="tag">分</span>（〇）交付表、（一）业务线归因+表、（二）QC 表、（三）兜底表 → <span class="tag">附录</span>口径与健康度。</p>
<div class="meta">
<strong>数据源：</strong><code>{html_module.escape(src_path)}</code> · 原始 {n_raw} 行 · 工时分析 <strong>{n_used}</strong> 行 · department_stats token <strong>{n_qc_tokens}</strong> · 命中 QC <strong>{n_qc_with_rows}</strong> 人 · 兜底 <strong>{n_fallback_reqs}</strong> 条<br>
<strong>生成时间：</strong>{html_module.escape(gen_time)} · {"估算口径：总实际工作量为 0" if actual_all_zero else "主口径仍为估算人日"}
</div>
</header>

<div class="section">
<div class="section-title">执行摘要</div>
<div class="summary-cards">
<div class="card"><h3>参与需求数</h3><div class="value">{n_used}</div><div class="sub">工时清洗</div></div>
<div class="card"><h3>估算人日合计</h3><div class="value">{_fmt_num(est_all, 1)}</div><div class="sub">≠ P9 五阶段</div></div>
<div class="card"><h3>测试分摊人日</h3><div class="value test">{_fmt_num(test_all, 1)}</div><div class="sub">人头比</div></div>
<div class="card"><h3>本页·测试占比</h3><div class="value test">{_fmt_pct(test_pct_all)}%</div><div class="sub">测÷估算</div></div>
<div class="card"><h3>研发分摊人日</h3><div class="value">{_fmt_num(dev_all, 1)}</div><div class="sub">人头比</div></div>
<div class="card"><h3>本页·全局 R/T</h3><div class="value">{_fmt_rt(rt_all)}</div><div class="sub">研÷测</div></div>
<div class="card"><h3>本期命中 QC 人</h3><div class="value">{n_qc_with_rows}</div><div class="sub">白名单</div></div>
</div>
<p style="font-size:12px;font-weight:600;color:#0f766e;margin:8px 0 8px">交付耗时（全表 · 自然日）</p>
<div class="summary-cards" style="max-width:720px;margin:0 auto 12px">
<div class="card"><h3>平均交付天数</h3><div class="value">{g_mean_s}</div><div class="sub">{n_ld_ok} 条可计</div></div>
<div class="card"><h3>中位交付天数</h3><div class="value">{g_med_s}</div><div class="sub">同上</div></div>
<div class="card"><h3>日期齐全占比</h3><div class="value">{pct_ld_ok:.1f}%</div><div class="sub">{n_ld_ok}/{n_ld_total}</div></div>
</div>
<div class="conclusion-box">
<div class="conclusion-title">能回答什么</div>
<p class="brief-p"><strong>①</strong> 测/研人头分摊与业务线归因堆叠。<strong>②</strong> QC 个人（仅 <code>QC</code> 列）与建议列。<strong>③</strong> 创建→完成自然日（章节〇表）。分月/迭代/Bug/五阶段请用 Gate-RDJ 跑 P9 脚本。</p>
</div>
<div class="grid-2">
<div class="panel-blue">
<div class="panel-title">关键观察</div>
<ul class="brief-ul">
{obs_li_joined}
</ul>
</div>
<div class="panel-amber">
<div class="panel-title">可执行项</div>
<ul class="brief-ul">{sug_li_joined}</ul>
</div>
</div>
</div>

<div class="section">
<h2>（〇）各所属项目 · 需求数与交付耗时</h2>
<p class="lead" style="margin-top:0">交付 = <code>完成日期</code>−<code>创建时间</code>（整天）。需求数：名称+项目非空。均值/中位仅统计「可计交付」列&gt;0 的项目内子集；全表快照见摘要。</p>
<div class="table-wrap">
<table class="data">
<thead><tr><th>所属项目</th><th>需求数</th><th>可计交付</th><th>平均天</th><th>中位天</th></tr></thead>
<tbody>
{"".join(rows_proj) if rows_proj else "<tr><td colspan='5' style='text-align:center;color:#64748b'>无数据</td></tr>"}
</tbody>
</table>
</div>
</div>

<div class="section">
<h2>（一）业务线 · 归因 + 测试结构</h2>
<p class="lead" style="margin-top:0">堆叠：<strong>青</strong>=<code>QC</code> 可归因估算，<strong>琥珀</strong>=项目兜底（与（三）一致）。下表含测试分摊与 R/T。</p>
<div id="chartCover" class="chart chart-tall"></div>
<div class="table-wrap">
<table class="data">
<thead><tr><th>业务线</th><th>需求数</th><th>估算人日</th><th>QC可归因</th><th>兜底估算</th><th>QC覆盖估算%</th><th>命中/兜底条</th><th>测试分摊</th><th>测试占比%</th><th>R/T</th></tr></thead>
<tbody>
{"".join(rows_biz)}
</tbody>
</table>
</div>
</div>

<div class="section">
<h2>（二）QC 个人</h2>
<p class="lead" style="margin-top:0">仅 <code>QC</code> 列白名单；建议列对照<strong>本期 QC 子集</strong>中位。<code>QCO</code> 不参与摊分。测人数=0 时用虚拟测，与（一）纯人头可能不一致。</p>
<div class="table-wrap">
<table class="data">
<thead><tr><th>QC</th><th>新分组</th><th>加权需求</th><th>估算人日</th><th>测试分摊</th><th>测试占比%</th><th>R/T</th><th>建议</th></tr></thead>
<tbody>
{"".join(rows_qc) if rows_qc else "<tr><td colspan='8' style='text-align:center;color:#64748b'>无命中白名单的 QC</td></tr>"}
</tbody>
</table>
</div>
</div>

<div class="section">
<h2>（三）QC 未覆盖 · 按项目兜底</h2>
<p class="lead" style="margin-top:0">与（一）琥珀段同源；开发:测试人头分摊，无虚拟测。</p>
<div class="table-wrap">
<table class="data">
<thead><tr><th>所属项目</th><th>需求数</th><th>估算人日</th><th>测试分摊</th><th>测试占比%</th><th>R/T</th></tr></thead>
<tbody>
{"".join(rows_fallback) if rows_fallback else "<tr><td colspan='6' style='text-align:center;color:#64748b'>无兜底行</td></tr>"}
</tbody>
</table>
</div>
</div>

<details class="method" style="margin-bottom:16px">
<summary>附录 · 数据健康度与口径（展开）</summary>
<table class="lex-table" style="margin-top:10px">
<tbody>
<tr><th style="width:26%">QC 列非空</th><td>{int(health["n_nonempty"])} 条（{health["qc_nonempty_pct"]:.1f}%）</td></tr>
<tr><th>白名单命中</th><td>{int(health["n_hit"])} 条（{health["whitelist_hit_pct"]:.1f}%）</td></tr>
<tr><th>兜底估算占全表</th><td>{health["fallback_est_pct"]:.1f}%</td></tr>
</tbody>
</table>
<table class="p9-ref-table" style="margin-top:12px">
<thead><tr><th>概念</th><th>P9 / Gate-RDJ</th><th>本页 Gate-AI</th></tr></thead>
<tbody>
<tr><th>测试工时</th><td>QC+测+预发</td><td>估算×测人数÷(开+测)</td></tr>
<tr><th>测试占比</th><td>测÷五阶段</td><td>测分摊÷估算</td></tr>
<tr><th>R/T</th><td>修正研发÷测</td><td>研发分摊÷测分摊</td></tr>
<tr><th>交付耗时</th><td>可分月</td><td>完成−创建（自然日）</td></tr>
<tr><th>个人 QC</th><td>部门对标等</td><td>仅 QC 列；建议=子集中位</td></tr>
</tbody>
</table>
<ul style="margin:10px 0 0 18px;font-size:12px;color:#475569">
<li>QC 行测分摊 &lt; {QC_RT_TEST_FLOOR} 人日时 R/T 显示「—」。</li>
<li>（一）（三）与 QC 表按测试分摊降序。</li>
</ul>
</details>

{roster_html}

<footer>scripts/generate_gate_ai_effort_report.py · 勿与 P9 对标数值</footer>
</div>

<script>
const DATA = {payload_json};
function initCover() {{
  const el = document.getElementById('chartCover');
  if (!el || typeof echarts === 'undefined') return;
  if (!DATA.coverCategories || DATA.coverCategories.length === 0) return;
  const chart = echarts.init(el);
  chart.setOption({{
    title: {{ text: '业务线：QC可归因 vs 兜底（估算人日）', left: 'center', textStyle: {{ fontSize: 14, color: '#475569' }} }},
    tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
    legend: {{ data: ['QC列可归因估算', '需项目兜底估算'], bottom: 0 }},
    grid: {{ left: '3%', right: '6%', bottom: '52px', containLabel: true }},
    xAxis: {{ type: 'value', name: '人日', max: DATA.coverXMax }},
    yAxis: {{ type: 'category', data: DATA.coverCategories, inverse: true, axisLabel: {{ fontSize: 11 }} }},
    series: [
      {{ name: 'QC列可归因估算', type: 'bar', stack: 't', data: DATA.coverEstQc, itemStyle: {{ color: '#0e7490', borderRadius: [0,0,0,0] }}, label: {{ show: false }} }},
      {{ name: '需项目兜底估算', type: 'bar', stack: 't', data: DATA.coverEstFb, itemStyle: {{ color: '#ea580c', borderRadius: [0, 4, 4, 0] }}, label: {{ show: true, position: 'right', formatter: function(p) {{ const i = p.dataIndex; const t = (DATA.coverEstQc[i]||0)+(DATA.coverEstFb[i]||0); return t.toFixed(1); }}, fontSize: 10 }} }}
    ]
  }});
  window.addEventListener('resize', function() {{ chart.resize(); }});
}}
if (document.readyState === 'loading') {{
  document.addEventListener('DOMContentLoaded', function() {{ initCover(); }});
}} else {{
  initCover();
}}
</script>
</body>
</html>
"""


def main() -> int:
    src = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_XLSX
    out = sys.argv[2] if len(sys.argv) > 2 else OUT_HTML
    if not os.path.isfile(src):
        print(f"找不到数据源: {src}", file=sys.stderr)
        return 1
    df = _load(src)
    csv_out = os.path.splitext(src)[0] + ".csv"
    df.to_csv(csv_out, index=False, encoding="utf-8-sig")
    print(f"已写入 CSV: {csv_out}")
    proj_delivery = aggregate_project_delivery(df)
    proj_delivery.to_csv(OUT_PROJECT_DELIVERY_CSV, index=False, encoding="utf-8-sig")
    print(f"已写入 CSV: {OUT_PROJECT_DELIVERY_CSV}")
    html = build_html(df, os.path.abspath(src), proj_delivery)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"已写入 HTML: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
