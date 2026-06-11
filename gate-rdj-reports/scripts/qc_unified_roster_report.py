#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合并主站 Gate-RDJ、产研分站、Gate-AI、Alpha(Meegle 导出) CSV，按 department_stats QC 白名单输出报告。

结构：**部门（大类-新分组）→ 人员 → 需求明细**。
主站 R/T：修正研发 ÷ 测试总估分(去除RD)。
分站 R/T：（需求排期总估分 − 测试总估分）÷ 测试总估分（与 Alpha 同形；总估分来自「需求排期-总估分」解析为天）。
AI R/T：研发分摊 ÷ 测试分摊（与 Gate-AI 报告一致；测试分摊≤0.05 不设比值）。
Alpha：Meegle 宽表；QC 角色归因；R/T =（总估分 − 测试估分）÷ 测试估分（字段 UUID 固定映射，见脚本常量）。
"""
from __future__ import annotations

import csv
import html as html_module
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from html import unescape
from typing import Any, Dict, List, Optional, Set, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
from _paths import REPO_ROOT

ROOT = str(REPO_ROOT)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from generate_gate_rdj_from_csv import (  # noqa: E402
    DEPARTMENT_STATS_URL,
    _DepartmentTableParser,
    _normalize_qc_token,
)
from gate_rdj_metrics import (  # noqa: E402
    _month_key,
    _parse_dt,
    corrected_rd,
    dedupe_main_rows,
    effort_fields,
    load_rows,
    main_station_role_hours,
)
from generate_chanfeng_station_report import (  # noqa: E402
    COL_CREATED,
    COL_LINK,
    COL_LINE,
    COL_PRIORITY,
    COL_QC,
    COL_SCHEDULE_TOTAL,
    COL_TEST,
    COL_TITLE,
    parse_schedule_days,
)

OUT_HTML = os.path.join(ROOT, "QC人员名单-主站分站合并需求与RT.html")
CSV_ITER = os.path.join(ROOT, "需求导出-Gate-RDJ_迭代维度.csv")
CSV_TIME = os.path.join(ROOT, "需求导出-Gate-RDJ_时间维度.csv")
CSV_STATION = os.path.join(ROOT, "全景视图导出-产研分站.csv")
# 需求级导出（含 QC、工时）；项目交付汇总见 CSV_AI_PROJECT_DELIVERY
CSV_AI_DEMAND_DEFAULT = os.path.join(ROOT, "Gate-AI项目集-需求导出.csv")
CSV_AI_PROJECT_DELIVERY = os.path.join(ROOT, "Gate-AI项目集-各项目需求数与平均交付时间.csv")
CSV_AI_DEMAND_FALLBACKS = (
    os.path.expanduser("~/Downloads/需求导出-Gate-AI项目集 (2).csv"),
    os.path.expanduser("~/Downloads/需求导出-Gate-AI项目集 (1).csv"),
)
CSV_ALPHA_MEEGLE_DEFAULT = os.path.join(ROOT, "data", "meegle_view_8bbOlLnNU.csv")
CSV_ALPHA_MEEGLE_QC_FALLBACK = os.path.join(ROOT, "data", "meegle_page_export.csv")
COL_MEEGLE_TITLE = "uiDataMap.1l5clgkicafc2.uiValue.nameWithComment.value"
COL_MEEGLE_PROJECT = "uiDataMap.1l5clgkicafc2.uiValue.nameWithComment.projectName"
# Meegle 导出 number 字段（与宽表列绑定）：总估分、测试估分
COL_MEEGLE_TOTAL_EST = "uiDataMap.1l5clgkicgqw2.uiValue.number.value"
COL_MEEGLE_TEST_EST = "uiDataMap.4364c1569f37ceb8203ab885d5358656.uiValue.number.value"
COL_MEEGLE_FINISH_MS = "uiDataMap.1m3h9z6r7auxk.uiValue.quickComplete.finish_time_ms"
DATA_SNAPSHOT = os.path.join(ROOT, "data", "department_stats.html")

_AI_RT_TEST_FLOOR = 0.05
MONTH_UNLABELED = "未标注月"
_ROLLUP_ROW_RE = re.compile(r"」共\s*\d+\s*个\s*$")


def _fetch_department_html() -> str:
    if os.path.isfile(DATA_SNAPSHOT):
        try:
            with open(DATA_SNAPSHOT, "r", encoding="utf-8", errors="ignore") as f:
                t = f.read()
            if "departmentTable" in t:
                return t
        except OSError:
            pass
    try:
        r = subprocess.run(
            ["curl", "-fsSL", "--max-time", "45", DEPARTMENT_STATS_URL],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0 and r.stdout and "departmentTable" in r.stdout:
            os.makedirs(os.path.dirname(DATA_SNAPSHOT), exist_ok=True)
            try:
                with open(DATA_SNAPSHOT, "w", encoding="utf-8") as f:
                    f.write(r.stdout)
            except OSError:
                pass
            return r.stdout
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


def _qc_roster_from_html(html_text: str) -> Tuple[Dict[str, str], Dict[str, str], List[str]]:
    parser = _DepartmentTableParser()
    parser.feed(html_text)
    display: Dict[str, str] = {}
    group_of: Dict[str, str] = {}
    order: List[str] = []
    if not parser.headers or not parser.rows:
        return display, group_of, order
    try:
        idx_big = parser.headers.index("大类名称")
        idx_group = parser.headers.index("新分组")
        idx_qc = parser.headers.index("QC")
    except ValueError:
        return display, group_of, order
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
        for name in qc_names:
            raw = str(name).strip()
            tok = _normalize_qc_token(raw)
            if not tok:
                continue
            if tok not in display:
                display[tok] = raw
                group_of[tok] = group_label
                order.append(tok)
    return display, group_of, order


def _dept_label_norm(label: str) -> str:
    return re.sub(r"\s+", "", (label or "").strip())


def _int_cell_text(text: str) -> Optional[int]:
    t = re.sub(r"<[^>]+>", "", text or "").strip()
    m = re.search(r"-?\d+", t)
    return int(m.group()) if m else None


def _dept_stats_metrics_from_html(
    html_text: str,
) -> Tuple[Dict[str, Dict[str, Any]], Optional[Dict[str, Any]]]:
    """解析 department_stats 编制台账：开发总数、QC、开发WEB测试比；含 tfoot 总和。"""
    parser = _DepartmentTableParser()
    parser.feed(html_text)
    by_key: Dict[str, Dict[str, Any]] = {}
    if not parser.headers or not parser.rows:
        return by_key, None
    try:
        idx_big = parser.headers.index("大类名称")
        idx_group = parser.headers.index("新分组")
        idx_dev = parser.headers.index("开发总数")
        idx_qc = parser.headers.index("QC")
        idx_rt = parser.headers.index("开发WEB测试比")
    except ValueError:
        return by_key, None
    for row in parser.rows:
        if len(row) <= max(idx_big, idx_group, idx_dev, idx_qc, idx_rt):
            continue
        big_name = row[idx_big][0].strip()
        group_name = re.sub(r"\s+", "", row[idx_group][0].strip())
        if not group_name:
            continue
        group_label = f"{big_name}-{group_name}" if big_name else group_name
        key = _dept_label_norm(group_label)
        by_key[key] = {
            "label": group_label,
            "dev_total": _int_cell_text(row[idx_dev][0]),
            "qc_count": _int_cell_text(row[idx_qc][0]),
            "dev_web_rt": (row[idx_rt][0].strip() or "—"),
        }
    total: Optional[Dict[str, Any]] = None
    m = re.search(r"<tfoot>(.*?)</tfoot>", html_text, re.S | re.I)
    if m:
        tds = re.findall(r"<td[^>]*>(.*?)</td>", m.group(1), re.S)
        cells = [re.sub(r"<[^>]+>", "", t).strip() for t in tds]
        if len(cells) >= 10:
            total = {
                "dev_total": _int_cell_text(cells[7]),
                "qc_count": _int_cell_text(cells[8]),
                "dev_web_rt": cells[9] or "—",
            }
    return by_key, total


def _qc_exec_tokens(qc_field: object, allow: Set[str]) -> List[str]:
    """与 Gate-AI 一致：| / 逗号等拆分，仅白名单。"""
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


def _read_csv(path: str) -> List[Dict[str, str]]:
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _filter_ai_rollups(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    return [r for r in rows if not _ROLLUP_ROW_RE.search((r.get("名称") or "").strip())]


def _is_ai_demand_csv(rows: List[Dict[str, str]]) -> bool:
    """需求级 Gate-AI 导出须含名称、QC、总估算工作量等列。"""
    if not rows:
        return False
    keys = set(rows[0].keys())
    return "名称" in keys and "QC" in keys and "总估算工作量(人/日)" in keys


def _resolve_ai_demand_csv(explicit: str = "") -> Tuple[str, List[Dict[str, str]]]:
    """解析 AI 需求级 CSV；若传入的是项目汇总表则自动改用需求导出。"""
    candidates: List[str] = []
    if explicit.strip():
        candidates.append(explicit.strip())
    candidates.append(CSV_AI_DEMAND_DEFAULT)
    candidates.extend(CSV_AI_DEMAND_FALLBACKS)
    seen: Set[str] = set()
    for p in candidates:
        ap = os.path.abspath(p)
        if ap in seen or not os.path.isfile(ap):
            continue
        seen.add(ap)
        rows = _read_csv(ap)
        if _is_ai_demand_csv(rows):
            return ap, _filter_ai_rollups(rows)
    return explicit.strip() or CSV_AI_DEMAND_DEFAULT, []


def _build_meegle_qc_index(fallback_csv: str) -> Dict[str, List[str]]:
    """旧版 page_export 含 QC 角色列；按 work_item_id 供新视图补 QC。"""
    idx: Dict[str, List[str]] = {}
    if not os.path.isfile(fallback_csv):
        return idx
    for r in _dedupe_meegle_rows(_read_csv(fallback_csv)):
        wid = (r.get("work_item_id") or "").strip()
        labels = _meegle_qc_labels_from_row(r)
        if wid and labels:
            idx[wid] = labels
    return idx


def _parse_meegle_role_user_json(raw: str) -> List[str]:
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        arr = json.loads(raw)
    except json.JSONDecodeError:
        return []
    out: List[str] = []
    if not isinstance(arr, list):
        return out
    for item in arr:
        if isinstance(item, dict):
            cn = (item.get("name_cn") or item.get("name_en") or "").strip()
            if cn:
                out.append(cn)
    return out


def _meegle_qc_labels_from_row(
    row: Dict[str, str],
    qc_index: Optional[Dict[str, List[str]]] = None,
) -> List[str]:
    """从 Meegle 宽表 roleName=QC 的 roleMultiUser 取执行人；无 QC 列时用 qc_index 按 work_item_id 补全。"""
    names: List[str] = []
    for k, v in row.items():
        if not str(k).endswith(".uiValue.roleMultiUser.roleName"):
            continue
        if (v or "").strip() != "QC":
            continue
        prefix = str(k)[: -len("roleName")]
        val_key = prefix + "value"
        raw = row.get(val_key, "") or ""
        for n in _parse_meegle_role_user_json(raw):
            if n not in names:
                names.append(n)
    if names:
        return names
    if qc_index:
        wid = (row.get("work_item_id") or "").strip()
        if wid and wid in qc_index:
            return list(qc_index[wid])
    return names


def _dedupe_meegle_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    seen: Set[str] = set()
    out: List[Dict[str, str]] = []
    for r in rows:
        wid = (r.get("work_item_id") or "").strip()
        tit = (r.get(COL_MEEGLE_TITLE) or "").strip()
        key = wid if wid else tit
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _sf(x: Any) -> float:
    try:
        return float(str(x).strip() or 0)
    except ValueError:
        return 0.0


def _ai_effort_split(est: float, dev: float, test: float) -> Tuple[float, float]:
    """与 generate_gate_ai_effort_report.effort_split_for_qc_row 同逻辑（纯标量）。"""
    if est <= 0:
        return 0.0, 0.0
    dv, tv = dev, test
    if tv > 0:
        s = dv + tv
        if s <= 0:
            return est, 0.0
        return est * dv / s, est * tv / s
    s = dv + 1.0
    if s <= 0:
        return 0.0, est
    return est * dv / s, est * 1.0 / s


def _main_rt(
    r: Dict[str, str], allow: Optional[Set[str]] = None
) -> Tuple[Optional[float], float, float]:
    if allow:
        rd, test, rt, _, _ = main_station_role_hours(r, allow)
        return rt, rd, test
    _, _, _, _, _, _, tt = effort_fields(r)
    rc = corrected_rd(r)
    if tt <= 0:
        return None, rc, tt
    return rc / tt, rc, tt


def _station_rt(sched_raw: Any, test_raw: Any) -> Tuple[Optional[float], Optional[float], float, float]:
    """分站单条 R/T = max(0, 总估分−测试总估分) ÷ 测试总估分。返回 (rt, total_days, test, rd_approx)。"""
    sd = parse_schedule_days(sched_raw)
    te = _sf(test_raw)
    if sd is None:
        return None, None, te, 0.0
    total = float(sd)
    rd = max(0.0, total - te)
    if te <= _AI_RT_TEST_FLOOR:
        return None, total, te, rd
    return rd / te, total, te, rd


def depts_for_qc(qc_field: str, group_of: Dict[str, str]) -> List[str]:
    """有 QC 参与即算：返回该需求涉及的全部部门（去重、保序）。"""
    allow = set(group_of.keys())
    toks = _qc_exec_tokens(qc_field, allow)
    seen: Set[str] = set()
    out: List[str] = []
    for t in toks:
        g = group_of.get(t, "其他")
        if g not in seen:
            seen.add(g)
            out.append(g)
    return out if out else ["未归属"]


def dept_display(depts: List[str]) -> str:
    if not depts:
        return "未归属"
    return depts[0] if len(depts) == 1 else " · ".join(depts)


def _story_rec_key(rec: Dict[str, Any]) -> str:
    link = str(rec.get("link") or "").strip()
    m = re.search(r"/detail/(\d+)", link)
    if m:
        return f"{rec['src']}:{m.group(1)}"
    title = str(rec.get("title") or "").strip()[:80]
    return f"{rec['src']}:{title}"


def _person_weighted_RT(
    rows: List[Dict[str, Any]],
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float], int, int, int, int, int]:
    """个人级：多人 QC 按 1/n 均分后 Σ研发÷Σ测试。"""
    sum_rc = sum_tt = 0.0
    n_main = 0
    sum_sched = sum_st_test = 0.0
    n_station = 0
    sum_ed = sum_et = 0.0
    n_ai = 0
    sum_alpha_rd = sum_alpha_tt = 0.0
    n_alpha_rows = 0
    n_alpha_rt = 0
    for rec in rows:
        d = float(rec.get("qc_share_denom") or 1)
        src = rec["src"]
        if isinstance(src, str) and src.startswith("Alpha·"):
            n_alpha_rows += 1
            at = float(rec.get("alpha_test") or 0)
            ar = float(rec.get("alpha_rd_approx") or 0)
            if at > _AI_RT_TEST_FLOOR:
                sum_alpha_rd += ar / d
                sum_alpha_tt += at / d
                n_alpha_rt += 1
            continue
        if src == "主站·Gate-RDJ" and rec.get("rd_corr") is not None:
            tr = float(rec["test"] or 0)
            if tr > 0:
                sum_rc += float(rec["rd_corr"]) / d
                sum_tt += tr / d
                n_main += 1
        elif src == "分站·全景":
            rd_st = float(rec.get("station_rd_approx") or 0)
            te = float(rec["test"] or 0)
            if te > _AI_RT_TEST_FLOOR:
                sum_sched += rd_st / d
                sum_st_test += te / d
                n_station += 1
        elif src == "AI·Gate-AI项目集":
            ed = float(rec.get("ai_dev") or 0)
            et = float(rec.get("ai_test") or 0)
            if et > _AI_RT_TEST_FLOOR:
                sum_ed += ed / d
                sum_et += et / d
                n_ai += 1
    rt_m = (sum_rc / sum_tt) if sum_tt > 0 else None
    rt_s = (sum_sched / sum_st_test) if sum_st_test > 0 else None
    rt_a = (sum_ed / sum_et) if sum_et > 0 else None
    rt_al = (sum_alpha_rd / sum_alpha_tt) if sum_alpha_tt > 0 else None
    return rt_m, rt_s, rt_a, rt_al, n_main, n_station, n_ai, n_alpha_rows, n_alpha_rt


def _dept_weighted_RT(
    rows: List[Dict[str, Any]],
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float], int, int, int, int, int, int]:
    """部门级：按需求去重，整单工时累加（有 QC 参与即算、不分摊）。"""
    seen: Set[str] = set()
    sum_rc = sum_tt = 0.0
    n_main = 0
    sum_sched = sum_st_test = 0.0
    n_station = 0
    sum_ed = sum_et = 0.0
    n_ai = 0
    sum_alpha_rd = sum_alpha_tt = 0.0
    n_alpha_rows = 0
    n_alpha_rt = 0
    for rec in rows:
        key = _story_rec_key(rec)
        if key in seen:
            continue
        seen.add(key)
        src = rec["src"]
        if isinstance(src, str) and src.startswith("Alpha·"):
            n_alpha_rows += 1
            at = float(rec.get("alpha_test") or 0)
            ar = float(rec.get("alpha_rd_approx") or 0)
            if at > _AI_RT_TEST_FLOOR:
                sum_alpha_rd += ar
                sum_alpha_tt += at
                n_alpha_rt += 1
            continue
        if src == "主站·Gate-RDJ" and rec.get("rd_corr") is not None:
            tr = float(rec["test"] or 0)
            rc = float(rec["rd_corr"])
            if tr > _AI_RT_TEST_FLOOR and rc > 0:
                sum_rc += rc
                sum_tt += tr
                n_main += 1
        elif src == "分站·全景":
            rd_st = float(rec.get("station_rd_approx") or 0)
            te = float(rec["test"] or 0)
            if te > _AI_RT_TEST_FLOOR and rd_st > 0:
                sum_sched += rd_st
                sum_st_test += te
                n_station += 1
        elif src == "AI·Gate-AI项目集":
            ed = float(rec.get("ai_dev") or 0)
            et = float(rec.get("ai_test") or 0)
            if et > _AI_RT_TEST_FLOOR and ed > 0:
                sum_ed += ed
                sum_et += et
                n_ai += 1
    rt_m = (sum_rc / sum_tt) if sum_tt > _AI_RT_TEST_FLOOR else None
    rt_s = (sum_sched / sum_st_test) if sum_st_test > _AI_RT_TEST_FLOOR else None
    rt_a = (sum_ed / sum_et) if sum_et > _AI_RT_TEST_FLOOR else None
    rt_al = (sum_alpha_rd / sum_alpha_tt) if sum_alpha_tt > _AI_RT_TEST_FLOOR else None
    return rt_m, rt_s, rt_a, rt_al, n_main, n_station, n_ai, n_alpha_rows, n_alpha_rt, len(seen)


def _month_from_text_or_ms(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if re.fullmatch(r"\d{10,13}", s):
        try:
            ms = int(s)
            if ms > 10_000_000_000_000:
                ms //= 1000
            return _month_key(datetime.fromtimestamp(ms / 1000.0))
        except (ValueError, OSError, OverflowError):
            pass
    return _month_key(_parse_dt(s))


def _rec_month(
    src: str,
    *,
    done: str = "",
    created: str = "",
    finish_ms: str = "",
) -> str:
    m: Optional[str] = None
    if src in ("主站·Gate-RDJ", "AI·Gate-AI项目集"):
        m = _month_from_text_or_ms(done)
    elif src == "分站·全景":
        m = _month_from_text_or_ms(created) or _month_from_text_or_ms(done)
    elif isinstance(src, str) and src.startswith("Alpha·"):
        m = _month_from_text_or_ms(finish_ms) or _month_from_text_or_ms(done)
    return m or MONTH_UNLABELED


def _dept_stats_cells(st: Optional[Dict[str, Any]]) -> Tuple[str, str, str]:
    if not st:
        return "—", "—", "—"
    dev_s = str(st["dev_total"]) if st.get("dev_total") is not None else "—"
    qc_s = str(st["qc_count"]) if st.get("qc_count") is not None else "—"
    rt_web = html_module.escape(str(st.get("dev_web_rt") or "—"))
    return dev_s, qc_s, rt_web


def _sum_dept_stats_slice(
    dept_order: List[str],
    dept_keys: Set[str],
    dept_stats_by_key: Dict[str, Dict[str, Any]],
) -> Tuple[str, str, str]:
    """当月有数据的部门：汇总编制开发总数与 QC，并算编制维开发/WEB测试比。"""
    sum_dev = 0
    sum_qc = 0
    any_dev = any_qc = False
    for dept in dept_order:
        if _dept_label_norm(dept) not in dept_keys:
            continue
        st = dept_stats_by_key.get(_dept_label_norm(dept))
        if not st:
            continue
        if st.get("dev_total") is not None:
            sum_dev += int(st["dev_total"])
            any_dev = True
        if st.get("qc_count") is not None:
            sum_qc += int(st["qc_count"])
            any_qc = True
    dev_s = str(sum_dev) if any_dev else "—"
    qc_s = str(sum_qc) if any_qc else "—"
    rt_web = f"{sum_dev / sum_qc:.1f}:1" if sum_qc > 0 and any_dev else "—"
    return dev_s, qc_s, rt_web


def _fmt_rt_row(
    all_recs: List[Dict[str, Any]],
    *,
    dept_mode: bool = False,
) -> Tuple[str, str, str, str, str, str, int]:
    """返回 rm, rs, ra, ral, samp_tail, n_rec, active_qc_placeholder count via n_rec only."""
    if dept_mode:
        rt_m, rt_s, rt_a, rt_al, nm, ns, na, nal, nart, n_rec = _dept_weighted_RT(all_recs)
    else:
        rt_m, rt_s, rt_a, rt_al, nm, ns, na, nal, nart = _person_weighted_RT(all_recs)
        n_rec = len(all_recs)
    rm = f"{rt_m:.2f}" if rt_m is not None else "—"
    rs = f"{rt_s:.2f}" if rt_s is not None else "—"
    ra = f"{rt_a:.2f}" if rt_a is not None else "—"
    ral = f"{rt_al:.2f}" if rt_al is not None else "—"
    samp_tail = f"{nm}/{ns}/{na}/{nal}"
    if nal > 0 and nart != nal:
        samp_tail += f" <span class='muted'>(α可算{nart})</span>"
    return rm, rs, ra, ral, samp_tail, n_rec, n_rec


def _dept_build_order(roster_order: List[str], group_of: Dict[str, str]) -> Tuple[List[str], Dict[str, List[str]]]:
    dept_order: List[str] = []
    buckets: Dict[str, List[str]] = {}
    seen_dept: Set[str] = set()
    for tok in roster_order:
        g = group_of.get(tok, "其他")
        if g not in buckets:
            buckets[g] = []
        buckets[g].append(tok)
        if g not in seen_dept:
            seen_dept.add(g)
            dept_order.append(g)
    return dept_order, buckets


def build_report() -> str:
    html_body = _fetch_department_html()
    display, group_of, roster_order = _qc_roster_from_html(html_body)
    dept_stats_by_key, dept_stats_total = _dept_stats_metrics_from_html(html_body)
    allow = set(display.keys())

    if not allow:
        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'><title>QC 合并报告</title></head>"
            "<body><p>无法解析 department_stats QC 白名单，请检查网络或放置 data/department_stats.html</p></body></html>"
        )

    csv_ai_env = os.environ.get("GATE_AI_CSV", "").strip()
    csv_ai, ai_rows = _resolve_ai_demand_csv(csv_ai_env or CSV_AI_PROJECT_DELIVERY)
    csv_alpha_meegle = os.environ.get("MEEGLE_CSV", "").strip() or CSV_ALPHA_MEEGLE_DEFAULT
    meegle_qc_fallback = os.environ.get("MEEGLE_QC_CSV", "").strip() or CSV_ALPHA_MEEGLE_QC_FALLBACK
    meegle_qc_index = _build_meegle_qc_index(meegle_qc_fallback)

    main_rows = dedupe_main_rows([CSV_ITER, CSV_TIME])
    station_rows = _read_csv(CSV_STATION)
    meegle_rows = _dedupe_meegle_rows(_read_csv(csv_alpha_meegle))

    by_qc: Dict[str, List[Dict[str, Any]]] = {t: [] for t in roster_order}

    for r in main_rows:
        toks = _qc_exec_tokens(r.get("QC"), allow)
        if not toks:
            continue
        rt, rc, tt = _main_rt(r, allow)
        title = (r.get("名称") or "").strip()[:300]
        link = (r.get("需求链接") or "").strip()
        biz = (r.get("业务线") or "").strip()
        sp = (r.get("所属迭代") or "").strip()
        done = (r.get("完成日期") or "").strip()
        n_share = len(toks)
        rec = {
            "src": "主站·Gate-RDJ",
            "title": title,
            "link": link,
            "rt": rt,
            "rt_label": "P9修正÷测试",
            "extra": f"业务线 {biz or '—'} · 迭代 {sp or '—'} · 完成 {done or '—'}",
            "rd_corr": rc,
            "test": tt,
            "sched": None,
            "qc_share_denom": n_share,
            "ai_dev": None,
            "ai_test": None,
            "month": _rec_month("主站·Gate-RDJ", done=done),
        }
        for t in toks:
            if t in by_qc:
                by_qc[t].append(rec.copy())

    for r in station_rows:
        toks = _qc_exec_tokens(r.get(COL_QC), allow)
        if not toks:
            continue
        rt, sd, te, rd_ap = _station_rt(r.get(COL_SCHEDULE_TOTAL), r.get(COL_TEST))
        title = (r.get(COL_TITLE) or "").strip()[:300]
        link = (r.get(COL_LINK) or "").strip()
        line = (r.get(COL_LINE) or "").strip()
        pr = (r.get(COL_PRIORITY) or "").strip()
        cr = (r.get(COL_CREATED) or "").strip()
        n_share = len(toks)
        tot_note = f"{sd:.2f} 天" if sd is not None else "—"
        rec = {
            "src": "分站·全景",
            "title": title,
            "link": link,
            "rt": rt,
            "rt_label": "(总估分-测试)÷测试",
            "extra": (
                f"业务线 {line or '—'} · 优先级 {pr or '—'} · 创建 {cr or '—'} · "
                f"排期总估分 {tot_note} · 测试总估分 {te:.2f}"
            ),
            "rd_corr": None,
            "test": te,
            "sched": sd,
            "station_rd_approx": rd_ap,
            "qc_share_denom": n_share,
            "ai_dev": None,
            "ai_test": None,
            "month": _rec_month("分站·全景", created=cr),
        }
        for t in toks:
            if t in by_qc:
                by_qc[t].append(rec.copy())

    for r in ai_rows:
        toks = _qc_exec_tokens(r.get("QC"), allow)
        if not toks:
            continue
        est = _sf(r.get("总估算工作量(人/日)"))
        dv = _sf(r.get("开发参与人数"))
        tv = _sf(r.get("测试参与人数"))
        ed, et = _ai_effort_split(est, dv, tv)
        rt_ai: Optional[float]
        if et > _AI_RT_TEST_FLOOR:
            rt_ai = ed / et
        else:
            rt_ai = None
        title = (r.get("名称") or "").strip()[:300]
        link = (r.get("需求链接") or "").strip()
        proj = (r.get("所属项目") or "").strip()
        st = (r.get("状态") or "").strip()
        done = (r.get("完成日期") or "").strip()
        n_share = len(toks)
        rec = {
            "src": "AI·Gate-AI项目集",
            "title": title,
            "link": link,
            "rt": rt_ai,
            "rt_label": "研发分摊÷测试分摊",
            "extra": f"所属项目 {proj or '—'} · 状态 {st or '—'} · 完成 {done or '—'}",
            "rd_corr": None,
            "test": et,
            "sched": None,
            "qc_share_denom": n_share,
            "ai_dev": ed,
            "ai_test": et,
            "month": _rec_month("AI·Gate-AI项目集", done=done),
        }
        for t in toks:
            if t in by_qc:
                by_qc[t].append(rec.copy())

    for r in meegle_rows:
        qc_labels = _meegle_qc_labels_from_row(r, meegle_qc_index)
        toks_m: List[str] = []
        for lab in qc_labels:
            tok = _normalize_qc_token(lab)
            if tok and tok in allow and tok not in toks_m:
                toks_m.append(tok)
        if not toks_m:
            continue
        title = (r.get(COL_MEEGLE_TITLE) or "").strip()[:300]
        if not title:
            continue
        proj = (r.get(COL_MEEGLE_PROJECT) or "").strip()
        wid = (r.get("work_item_id") or "").strip()
        pk = (r.get("project_key") or "").strip()
        total_est = _sf(r.get(COL_MEEGLE_TOTAL_EST))
        test_est = _sf(r.get(COL_MEEGLE_TEST_EST))
        rd_approx = max(0.0, total_est - test_est)
        rt_mee: Optional[float] = None
        if test_est > _AI_RT_TEST_FLOOR:
            rt_mee = rd_approx / test_est
        src_label = f"Alpha·Meegle({proj})" if proj else "Alpha·Meegle"
        n_share = len(toks_m)
        rec = {
            "src": src_label,
            "title": title,
            "link": "",
            "rt": rt_mee,
            "rt_label": "(总估分-测试)÷测试",
            "extra": (
                f"项目 {proj or '—'} · 总估分 {total_est:.2f} · 测试估分 {test_est:.2f} · "
                f"work_item_id {wid or '—'} · project_key {pk or '—'}"
            ),
            "rd_corr": rd_approx,
            "test": test_est,
            "sched": None,
            "qc_share_denom": n_share,
            "ai_dev": None,
            "ai_test": None,
            "alpha_rd_approx": rd_approx,
            "alpha_test": test_est,
            "alpha_total": total_est,
            "month": _rec_month(
                src_label,
                finish_ms=(r.get(COL_MEEGLE_FINISH_MS) or ""),
            ),
        }
        for t in toks_m:
            if t in by_qc:
                by_qc[t].append(rec.copy())

    dept_order, dept_buckets = _dept_build_order(roster_order, group_of)

    by_month_dept: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    month_qc_hit: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
    for tok, rows in by_qc.items():
        dept = group_of.get(tok, "其他")
        for rec in rows:
            m = rec.get("month") or MONTH_UNLABELED
            by_month_dept[m][dept].append(rec)
            month_qc_hit[m][dept].add(tok)
    month_order = sorted(by_month_dept.keys(), reverse=True)
    if MONTH_UNLABELED in month_order:
        month_order.remove(MONTH_UNLABELED)
        month_order.append(MONTH_UNLABELED)

    parts: List[str] = []
    parts.append("<!DOCTYPE html>\n<html lang='zh-CN'>\n<head>\n")
    parts.append("<meta charset='UTF-8'/>\n")
    parts.append("<meta name='viewport' content='width=device-width, initial-scale=1'/>\n")
    parts.append("<title>QC · 四源聚合 · 部门—人员—需求（Gate-RDJ 口径对齐）</title>\n")
    parts.append(
        "<style>"
        "*{margin:0;padding:0;box-sizing:border-box}"
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'PingFang SC','Microsoft YaHei',sans-serif;"
        "background:#f1f5f9;color:#1e293b;line-height:1.65;-webkit-font-smoothing:antialiased}"
        ".container{max-width:1280px;margin:0 auto;padding:24px 22px 56px}"
        ".masthead{text-align:center;padding:8px 8px 22px;margin-bottom:8px;"
        "border-bottom:1px solid #e2e8f0;background:linear-gradient(180deg,#ffffff 0%,rgba(248,250,252,0.65) 55%,transparent 100%);"
        "border-radius:0 0 20px 20px}"
        ".eyebrow{font-size:11px;font-weight:700;letter-spacing:0.14em;text-transform:uppercase;color:#0369a1;margin-bottom:10px}"
        "h1{color:#0c4a6e;margin:0 0 8px;font-size:24px;font-weight:800;letter-spacing:-0.02em}"
        ".subtitle{color:#64748b;font-size:13px;margin:0 0 14px}"
        ".subtitle code{font-size:12px;background:rgba(255,255,255,.9);padding:2px 8px;border-radius:6px;border:1px solid #e2e8f0;color:#475569}"
        ".lead{color:#475569;font-size:13px;line-height:1.78;margin:0 auto;max-width:820px}"
        ".lead .tag{margin:0 4px 0 0}"
        ".brief-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:18px 0 18px}"
        "@media(max-width:900px){.brief-grid{grid-template-columns:1fr}}"
        ".panel-blue{background:#eff6ff;border:1px solid #bfdbfe;border-radius:12px;padding:15px 16px;box-shadow:0 1px 2px rgba(14,165,233,0.06)}"
        ".panel-amber{background:#fffbeb;border:1px solid #fde68a;border-radius:12px;padding:15px 16px;box-shadow:0 1px 2px rgba(245,158,11,0.06)}"
        ".panel-title{font-size:13px;font-weight:700;color:#0c4a6e;margin:0 0 10px;padding-bottom:8px;border-bottom:1px solid rgba(14,165,233,0.25)}"
        ".panel-amber .panel-title{color:#92400e;border-bottom-color:rgba(245,158,11,0.35)}"
        ".panel-ul{margin:0;padding-left:1.15rem;font-size:13px;color:#334155;line-height:1.72}"
        ".panel-ul li{margin:6px 0}"
        ".toc{font-size:13px;color:#475569;margin:0 0 22px;padding:15px 18px;background:linear-gradient(135deg,#f8fafc,#f1f5f9);"
        "border-radius:14px;border:1px solid #e2e8f0;box-shadow:0 2px 8px rgba(15,23,42,0.06)}"
        ".toc .toc-h{font-size:12px;font-weight:700;color:#0c4a6e;margin-bottom:10px;display:block;letter-spacing:0.02em}"
        ".toc strong{color:#0c4a6e;font-weight:600}"
        ".toc code{font-size:11.5px;background:#fff;padding:2px 7px;border-radius:6px;border:1px solid #e2e8f0;color:#334155;word-break:break-all}"
        ".section{background:#fff;padding:17px 18px;border-radius:12px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,0.08);border:1px solid #e2e8f0}"
        ".section>h2,.section-title{font-size:15px;font-weight:700;color:#0c4a6e;margin:0 0 12px;padding-bottom:8px;border-bottom:2px solid #e2e8f0}"
        ".summary-cards{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:4px}"
        "@media(max-width:720px){.summary-cards{grid-template-columns:1fr}}"
        ".card{background:#fff;padding:14px 12px;border-radius:10px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.06);"
        "border:1px solid #e2e8f0;min-width:0;transition:box-shadow .15s,border-color .15s}"
        ".card:hover{border-color:#bae6fd;box-shadow:0 2px 8px rgba(14,165,233,0.08)}"
        ".card h3{font-size:11px;color:#64748b;margin-bottom:5px;font-weight:600}"
        ".card .value{font-size:22px;font-weight:700;color:#0c4a6e;line-height:1.2}"
        ".card .value.accent{color:#0ea5e9}"
        ".card .sub{font-size:11px;color:#94a3b8;margin-top:5px}"
        ".table-wrap{overflow:auto;margin-top:10px;border:1px solid #e2e8f0;border-radius:10px;background:#fff}"
        "table.sum-table{width:100%;border-collapse:collapse;font-size:12px}"
        "table.sum-table th,table.sum-table td{padding:9px 11px;text-align:center;border-bottom:1px solid #e2e8f0}"
        "table.sum-table th:first-child,table.sum-table td:first-child{text-align:left}"
        "table.sum-table tbody tr:nth-child(odd){background:#fafafa}"
        "table.sum-table th{background:#f8fafc;font-weight:600;color:#475569}"
        "table.sum-table tbody tr:hover{background:#eff6ff}"
        "table.sum-table tbody tr:last-child td{border-bottom:none}"
        "details.dept{margin:0 0 12px;border-radius:12px;background:#fff;border:1px solid #e2e8f0;"
        "box-shadow:0 1px 3px rgba(0,0,0,0.06);overflow:hidden}"
        "details.dept>summary{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;cursor:pointer;position:relative;"
        "list-style:none;padding:15px 44px 15px 18px;background:linear-gradient(90deg,#eff6ff 0%,#ffffff 48%);"
        "font-size:15px;font-weight:700;color:#0c4a6e;border-left:4px solid #0ea5e9;"
        "transition:background .15s}"
        "details.dept>summary:hover{background:linear-gradient(90deg,#dbeafe 0%,#ffffff 55%)}"
        "details.dept[open]>summary{border-bottom:1px solid #e2e8f0}"
        "details.dept>summary::-webkit-details-marker{display:none}"
        "details.dept>summary::after{content:'';position:absolute;right:18px;top:50%;width:7px;height:7px;"
        "border-right:2px solid #64748b;border-bottom:2px solid #64748b;transform:translateY(-70%) rotate(45deg);opacity:.85;transition:transform .2s ease}"
        "details.dept[open]>summary::after{transform:translateY(-30%) rotate(225deg)}"
        "details.dept>summary:focus-visible{outline:2px solid #38bdf8;outline-offset:2px;border-radius:4px}"
        "details.dept .dept-inner,details.month-fold .dept-inner{padding:14px 16px 16px;background:linear-gradient(180deg,#f8fafc 0%,#f1f5f9 100%)}"
        "details.month-fold{margin:10px 0;border:1px solid #e2e8f0;border-radius:10px;background:#fff}"
        "details.month-fold>summary{padding:12px 16px;cursor:pointer;font-weight:700;color:#0c4a6e;background:#f8fafc}"
        "details.month-fold>summary::-webkit-details-marker{display:none}"
        "details.person{margin:0 0 10px;border-radius:10px;border:1px solid #e2e8f0;background:#fff;overflow:hidden;"
        "box-shadow:0 1px 2px rgba(0,0,0,0.04)}"
        "details.person>summary{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;cursor:pointer;position:relative;"
        "list-style:none;padding:11px 40px 11px 14px;font-size:14px;font-weight:600;color:#334155;background:#fff;"
        "border-bottom:1px solid transparent;transition:color .15s,background .15s}"
        "details.person>summary:hover{background:#f8fafc}"
        "details.person[open]>summary{border-bottom-color:#e2e8f0;color:#0c4a6e;background:#f8fafc}"
        "details.person>summary::-webkit-details-marker{display:none}"
        "details.person>summary::after{content:'';position:absolute;right:14px;top:50%;width:6px;height:6px;"
        "border-right:2px solid #94a3b8;border-bottom:2px solid #94a3b8;transform:translateY(-65%) rotate(45deg);transition:transform .2s ease}"
        "details.person[open]>summary::after{transform:translateY(-35%) rotate(225deg);border-color:#64748b}"
        "details.person>summary:focus-visible{outline:2px solid #38bdf8;outline-offset:-2px}"
        "details.person .person-inner{padding:12px 14px 14px;background:#fff}"
        ".tbl-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:0;border-radius:8px;border:1px solid #e2e8f0;background:#fff;"
        "box-shadow:inset 0 1px 0 rgba(255,255,255,.9)}"
        "table.data-table{width:100%;border-collapse:collapse;font-size:11px;min-width:620px}"
        "table.data-table th,table.data-table td{padding:7px 9px;text-align:center;border-bottom:1px solid #e2e8f0;vertical-align:top}"
        "table.data-table th:first-child,table.data-table td:first-child,table.data-table th:nth-child(2),table.data-table td:nth-child(2){text-align:left}"
        "table.data-table tbody tr:nth-child(even){background:#fafafa}"
        "table.data-table th{background:#f1f5f9;font-weight:600;color:#475569;font-size:11px}"
        "table.data-table tbody tr:hover{background:#eff6ff}"
        "table.data-table tbody tr:last-child td{border-bottom:none}"
        "table.data-table a{color:#0369a1;font-weight:600;text-decoration:none;border-bottom:1px solid #bae6fd}"
        "table.data-table a:hover{color:#0c4a6e;border-bottom-color:#0c4a6e}"
        ".rt-num{font-variant-numeric:tabular-nums;font-feature-settings:'tnum'}"
        ".tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:6px;background:#e0f2fe;color:#0369a1;margin-right:6px;font-weight:600}"
        ".muted{color:#94a3b8;font-size:12px}"
        ".kpi-inline{font-size:12px;font-weight:600;color:#475569}"
        "</style>\n</head>\n<body>\n"
    )
    parts.append('<div class="container">\n')
    parts.append('<div class="masthead">\n')
    parts.append("<div class='eyebrow'>Gate-RDJ · 四源台账</div>\n")
    parts.append("<h1>QC 四源聚合效能（部门 → 人员 → 需求）</h1>\n")
    parts.append(
        "<p class='subtitle'>主站 <code>Gate-RDJ</code> · 分站 <code>产研全景</code> · "
        "<code>Gate-AI</code> · <code>Alpha·Meegle</code> · 口径与 P9 人效报告对齐阅读</p>\n"
    )
    parts.append(
        "<p class='lead'><span class='tag'>总</span>先扫部门汇总与加权 R/T；"
        "<span class='tag'>分</span>再展开到人与单条需求；"
        "<span class='tag'>总</span>四源<strong>同名指标不同义</strong>，仅做结构对照，勿跨源硬比绝对值。</p>\n"
    )
    parts.append("</div>\n")

    parts.append('<div class="brief-grid">\n')
    parts.append(
        '<div class="panel-blue">'
        '<div class="panel-title">关键锚点（怎么读）</div>'
        "<ul class='panel-ul'>"
        "<li><strong>主站</strong>：修正研发 ÷ 测试总估分（去除 RD），与 P9「个人 R/T」一致。</li>"
        "<li><strong>分站</strong>：（需求排期总估分 − 测试总估分）÷ 测试总估分；总估分来自导出「需求排期-总估分」列解析。</li>"
        "<li><strong>AI</strong>：按开发/测试参与人数分摊总估算；测试分摊过小则不展示单条 R/T。</li>"
        "<li><strong>Alpha·Meegle</strong>：宽表「总估分」「测试估分」列；"
        "R/T =（总估分 − 测试估分）÷ 测试估分；QC 角色归因，多人按分摊加权。</li>"
        "<li><strong>编制台账</strong>：与 <code>department_stats</code> 同源——"
        "开发总数、QC 人数、开发WEB测试比；与下方四源加权 R/T 分列展示。</li>"
        "</ul></div>\n"
    )
    parts.append(
        '<div class="panel-amber">'
        '<div class="panel-title">边界提示（避免误读）</div>'
        "<ul class='panel-ul'>"
        "<li><strong>部门 R/T</strong>：有 QC 参与即归入该部门，按需求去重后整单 Σ研发÷Σ测试（不分摊）。"
        "个人 R/T 仍按 1/n 均分。</li>"
        "<li>多人 QC 时同一需求会在每人下重复出现，部门「关联条数」为去重后唯一需求数。</li>"
        "<li>白名单以 <code>department_stats</code> 为准；别名未入库会导致归因偏少；"
        "Meegle 视图无 QC 列时按 <code>meegle_page_export</code> 的 work_item_id 补 QC（仅交集需求）。</li>"
        "<li>本页为数据台账，不替代 Jira 门禁与绩效评价。</li>"
        "</ul></div>\n"
    )
    parts.append("</div>\n")

    parts.append(
        "<div class='toc'><span class='toc-h'>数据与口径（源文件）</span>"
        "<strong>QC 白名单</strong>：<code>department_stats.html</code>（"
        + html_module.escape(DEPARTMENT_STATS_URL)
        + "）。<br/>"
        "<strong>主站</strong>：<code>需求导出-Gate-RDJ_迭代维度.csv</code> + <code>需求导出-Gate-RDJ_时间维度.csv</code>（按 story ID / 需求链接去重合并，时间维与迭代维不可相加）。"
        "<strong>分站</strong>：<code>全景视图导出-产研分站.csv</code>。"
        "<strong>AI 需求</strong>：<code>"
        + html_module.escape(csv_ai)
        + "</code>；<strong>AI 项目交付汇总</strong>：<code>"
        + html_module.escape(CSV_AI_PROJECT_DELIVERY)
        + "</code>。"
        "<strong>Alpha·Meegle</strong>：<code>"
        + html_module.escape(csv_alpha_meegle)
        + "</code>（总/测试估分见脚本常量；QC 优先视图内 QC 角色，缺失时按 work_item_id 合并 <code>"
        + html_module.escape(meegle_qc_fallback)
        + "</code>）。"
        "多人 QC 按人头分摊加权；测试分摊≤"
        f"{_AI_RT_TEST_FLOOR}"
        + " 不展示 AI 单条 R/T。</div>\n"
    )

    total_demands = sum(len(v) for v in by_qc.values())
    parts.append("<div class='section'><div class='section-title'>全局概览</div>\n")
    parts.append("<div class='summary-cards'>")
    parts.append(
        f"<div class='card'><h3>白名单 QC</h3><div class='value'>{len(roster_order)}</div><div class='sub'>人</div></div>"
        f"<div class='card'><h3>关联记录</h3><div class='value accent'>{total_demands}</div><div class='sub'>条（含多人重复列出）</div></div>"
        f"<div class='card'><h3>部门数</h3><div class='value'>{len(dept_order)}</div><div class='sub'>大类-新分组</div></div>"
    )
    if dept_stats_total:
        parts.append(
            f"<div class='card'><h3>编制·开发总数</h3><div class='value'>"
            f"{dept_stats_total.get('dev_total') or '—'}</div>"
            f"<div class='sub'>department_stats 总和</div></div>"
            f"<div class='card'><h3>编制·QC</h3><div class='value'>"
            f"{dept_stats_total.get('qc_count') or '—'}</div>"
            f"<div class='sub'>开发WEB测试比 {html_module.escape(str(dept_stats_total.get('dev_web_rt') or '—'))}</div></div>"
        )
    parts.append("</div></div>\n")

    # 部门汇总表
    parts.append(
        "<div class='section'><h2>（一）部门汇总</h2>"
        "<p class='muted' style='margin:0 0 10px;font-size:13px'>"
        "左侧三列来自 <code>department_stats</code> 编制台账；右侧为四源需求加权 R/T 与样本数。"
        "部门 R/T = 有 QC 参与即算、按需求去重、整单不分摊。</p>\n"
        "<div class='table-wrap'><table class='sum-table'>"
    )
    parts.append(
        "<thead><tr><th>部门（大类-新分组）</th>"
        "<th>开发总数</th><th>QC</th><th>开发WEB测试比</th>"
        "<th>白名单QC</th><th>关联条数</th>"
        "<th>主站加权 R/T</th><th>分站加权 R/T</th><th>AI 加权 R/T</th><th>Alpha 加权 R/T</th>"
        "<th>样本数(主/分/AI/α)</th></tr></thead><tbody>\n"
    )
    for dept in dept_order:
        tokens = dept_buckets.get(dept, [])
        all_recs: List[Dict[str, Any]] = []
        for tok in tokens:
            all_recs.extend(by_qc.get(tok, []))
        rm, rs, ra, ral, samp_tail, n_rec, _ = _fmt_rt_row(all_recs, dept_mode=True)
        st = dept_stats_by_key.get(_dept_label_norm(dept))
        dev_s, qc_s, rt_web = _dept_stats_cells(st)
        parts.append(
            "<tr>"
            f"<td>{html_module.escape(dept)}</td>"
            f"<td class='rt-num'>{dev_s}</td>"
            f"<td class='rt-num'>{qc_s}</td>"
            f"<td class='rt-num'>{rt_web}</td>"
            f"<td class='rt-num'>{len(tokens)}</td>"
            f"<td class='rt-num'>{n_rec}</td>"
            f"<td class='rt-num'>{rm}</td>"
            f"<td class='rt-num'>{rs}</td>"
            f"<td class='rt-num'>{ra}</td>"
            f"<td class='rt-num'>{ral}</td>"
            f"<td class='rt-num'>{samp_tail}</td>"
            "</tr>\n"
        )
    if dept_stats_total:
        parts.append(
            "<tr style='background:#eff6ff;font-weight:600'>"
            "<td>总和（department_stats）</td>"
            f"<td class='rt-num'>{dept_stats_total.get('dev_total') or '—'}</td>"
            f"<td class='rt-num'>{dept_stats_total.get('qc_count') or '—'}</td>"
            f"<td class='rt-num'>{html_module.escape(str(dept_stats_total.get('dev_web_rt') or '—'))}</td>"
            "<td colspan='7' class='muted' style='text-align:left;font-weight:400'>"
            "右侧 R/T 为四源需求台账加权，不与编制测试比直接对标</td>"
            "</tr>\n"
        )
    parts.append("</tbody></table></div></div>\n")

    # 按月 · 部门汇总（折叠）
    parts.append(
        "<div class='section'><h2>（一-B）按完成月 · 部门汇总</h2>"
        "<p class='muted' style='margin:0 0 12px;font-size:13px'>"
        "分月口径：主站 / AI 用<strong>完成日期</strong>；分站用<strong>创建时间</strong>；"
        "Alpha 用 Meegle <code>quickComplete.finish_time_ms</code>。"
        f"无法解析月份归入「{MONTH_UNLABELED}」。仅展示当月有记录的部门。"
        "左侧<strong>开发总数 / QC / 开发WEB测试比</strong>与 <code>department_stats</code> 编制台账同源（部门快照，各月相同）。</p>\n"
    )
    for mi, month in enumerate(month_order):
        dept_map = by_month_dept[month]
        month_total = sum(len(v) for v in dept_map.values())
        dept_active = sum(1 for d in dept_order if dept_map.get(d))
        open_attr = " open" if mi == 0 else ""
        parts.append(f"<details class='month-fold'{open_attr}><summary>")
        parts.append(html_module.escape(month))
        parts.append(
            f" <span class='tag'>{month_total} 条</span>"
            f"<span class='muted'>·</span> <span class='kpi-inline'>{dept_active} 个部门有数据</span>"
        )
        parts.append("</summary>\n<div class='dept-inner'>\n")
        parts.append("<div class='table-wrap'><table class='sum-table'>")
        parts.append(
            "<thead><tr><th>部门</th>"
            "<th>开发总数</th><th>QC</th><th>开发WEB测试比</th>"
            "<th>活跃QC</th><th>关联条数</th>"
            "<th>主站 R/T</th><th>分站 R/T</th><th>AI R/T</th><th>Alpha R/T</th>"
            "<th>样本(主/分/AI/α)</th></tr></thead><tbody>\n"
        )
        month_all: List[Dict[str, Any]] = []
        active_dept_keys: Set[str] = set()
        for dept in dept_order:
            recs = dept_map.get(dept, [])
            if not recs:
                continue
            active_dept_keys.add(_dept_label_norm(dept))
            month_all.extend(recs)
            rm, rs, ra, ral, samp_tail, n_rec, _ = _fmt_rt_row(recs, dept_mode=True)
            n_qc = len(month_qc_hit[month].get(dept, set()))
            dev_s, qc_s, rt_web = _dept_stats_cells(dept_stats_by_key.get(_dept_label_norm(dept)))
            parts.append(
                "<tr>"
                f"<td>{html_module.escape(dept)}</td>"
                f"<td class='rt-num'>{dev_s}</td>"
                f"<td class='rt-num'>{qc_s}</td>"
                f"<td class='rt-num'>{rt_web}</td>"
                f"<td class='rt-num'>{n_qc}</td>"
                f"<td class='rt-num'>{n_rec}</td>"
                f"<td class='rt-num'>{rm}</td>"
                f"<td class='rt-num'>{rs}</td>"
                f"<td class='rt-num'>{ra}</td>"
                f"<td class='rt-num'>{ral}</td>"
                f"<td class='rt-num'>{samp_tail}</td>"
                "</tr>\n"
            )
        if month_all:
            rm, rs, ra, ral, samp_tail, n_rec, _ = _fmt_rt_row(month_all, dept_mode=True)
            dev_t, qc_t, rt_t = _sum_dept_stats_slice(dept_order, active_dept_keys, dept_stats_by_key)
            parts.append(
                "<tr style='background:#f8fafc;font-weight:600'>"
                f"<td>当月合计</td>"
                f"<td class='rt-num'>{dev_t}</td>"
                f"<td class='rt-num'>{qc_t}</td>"
                f"<td class='rt-num'>{html_module.escape(rt_t)}</td>"
                f"<td class='rt-num'>—</td>"
                f"<td class='rt-num'>{n_rec}</td>"
                f"<td class='rt-num'>{rm}</td><td class='rt-num'>{rs}</td>"
                f"<td class='rt-num'>{ra}</td><td class='rt-num'>{ral}</td>"
                f"<td class='rt-num'>{samp_tail}</td></tr>\n"
            )
        parts.append("</tbody></table></div>\n</div></details>\n")
    parts.append("</div>\n")

    parts.append("<div class='section'><h2>（二）按部门展开 · 人员明细</h2>\n")

    # 部门 → 人 → 表
    for dept in dept_order:
        tokens = dept_buckets.get(dept, [])
        all_recs: List[Dict[str, Any]] = []
        for tok in tokens:
            all_recs.extend(by_qc.get(tok, []))
        d_rt_m, d_rt_s, d_rt_a, d_rt_al, d_nm, d_ns, d_na, d_nal, d_nart, d_nuniq = _dept_weighted_RT(
            all_recs
        )

        parts.append("<details class='dept' open><summary>")
        parts.append(html_module.escape(dept))
        parts.append(" ")
        parts.append(
            f"<span class='tag'>{len(tokens)} 人</span>"
            f"<span class='muted'>·</span> <span class='kpi-inline'>{d_nuniq} 条需求（去重）</span>"
        )
        bits_d: List[str] = []
        if d_rt_m is not None:
            bits_d.append(f"主站 R/T ≈ {d_rt_m:.2f} <span class='muted'>（n={d_nm}）</span>")
        if d_rt_s is not None:
            bits_d.append(f"分站 R/T ≈ {d_rt_s:.2f} <span class='muted'>（n={d_ns}）</span>")
        if d_rt_a is not None:
            bits_d.append(f"AI R/T ≈ {d_rt_a:.2f} <span class='muted'>（n={d_na}）</span>")
        if d_nal > 0:
            if d_rt_al is not None:
                bits_d.append(
                    f"Alpha R/T ≈ {d_rt_al:.2f} <span class='muted'>（{d_nal} 条，可算 n={d_nart}）</span>"
                )
            else:
                bits_d.append(
                    f"Alpha·Meegle <span class='muted'>（{d_nal} 条，测试估分≤{_AI_RT_TEST_FLOOR} 不可算）</span>"
                )
        if bits_d:
            parts.append("<span class='muted'>·</span> " + " · ".join(bits_d))
        parts.append("</summary>\n<div class='dept-inner'>\n")

        for tok in tokens:
            name = display.get(tok, tok)
            rows = by_qc.get(tok, [])
            rt_m, rt_s, rt_a, rt_al, nm, ns, na, nal, nart = _person_weighted_RT(rows)

            parts.append("<details class='person'><summary>")
            parts.append(html_module.escape(name))
            parts.append(" ")
            parts.append(
                f"<span class='muted'>·</span> <span class='kpi-inline'>{len(rows)} 条</span>"
            )
            bits_p: List[str] = []
            if rt_m is not None:
                bits_p.append(f"主站 {rt_m:.2f} <span class='muted'>(n={nm})</span>")
            if rt_s is not None:
                bits_p.append(f"分站 {rt_s:.2f} <span class='muted'>(n={ns})</span>")
            if rt_a is not None:
                bits_p.append(f"AI {rt_a:.2f} <span class='muted'>(n={na})</span>")
            if nal > 0:
                if rt_al is not None:
                    bits_p.append(
                        f"Alpha {rt_al:.2f} <span class='muted'>(n={nart}/{nal})</span>"
                    )
                else:
                    bits_p.append(f"α {nal} <span class='muted'>条（无可算 R/T）</span>")
            if bits_p:
                parts.append("<span class='muted'>·</span> " + " · ".join(bits_p))
            parts.append("</summary>\n<div class='person-inner'>\n")

            if not rows:
                parts.append("<p class='muted'>四源均未命中该 QC。</p>\n")
            else:
                parts.append("<div class='tbl-wrap'>")
                parts.append(
                    "<table class='data-table'><thead><tr>"
                    "<th>来源</th><th>需求</th><th>R/T</th><th>口径</th>"
                    "<th>修正研发 / 排期 / 研发分摊</th><th>测试 / 测试分摊</th><th>其他</th>"
                    "</tr></thead><tbody>\n"
                )
                for rec in rows:
                    rt = rec["rt"]
                    rt_s_cell = f"{rt:.2f}" if rt is not None else "—"
                    src = rec["src"]
                    src_s = str(src)
                    if src_s.startswith("Alpha·"):
                        ar = rec.get("alpha_rd_approx")
                        at = rec.get("alpha_test")
                        num_s = f"{float(ar):.2f}" if ar is not None else "—"
                        test_cell = f"{float(at):.4f}" if at is not None else "—"
                    elif src == "主站·Gate-RDJ":
                        num_s = f"{float(rec['rd_corr']):.2f}" if rec.get("rd_corr") is not None else "—"
                        test_cell = f"{float(rec['test']):.4f}"
                    elif src == "分站·全景":
                        sr = rec.get("station_rd_approx")
                        num_s = f"{float(sr):.2f}" if sr is not None else "—"
                        test_cell = f"{float(rec['test']):.4f}"
                    elif src == "AI·Gate-AI项目集":
                        num_s = f"{float(rec['ai_dev']):.2f}" if rec.get("ai_dev") is not None else "—"
                        test_cell = f"{float(rec['test']):.4f}"
                    else:
                        num_s = "—"
                        test_cell = f"{float(rec.get('test') or 0):.4f}"
                    tit = html_module.escape(rec["title"])
                    lk = rec["link"]
                    title_cell = (
                        f"<a href='{html_module.escape(lk)}' target='_blank' rel='noopener'>{tit}</a>"
                        if lk
                        else tit
                    )
                    parts.append(
                        "<tr>"
                        f"<td>{html_module.escape(rec['src'])}</td>"
                        f"<td>{title_cell}</td>"
                        f"<td class='rt-num'>{rt_s_cell}</td>"
                        f"<td>{html_module.escape(rec['rt_label'])}</td>"
                        f"<td class='rt-num'>{num_s}</td>"
                        f"<td class='rt-num'>{test_cell}</td>"
                        f"<td>{html_module.escape(rec['extra'])}</td>"
                        "</tr>\n"
                    )
                parts.append("</tbody></table></div>\n")
            parts.append("</div></details>\n")

        parts.append("</div></details>\n")

    parts.append("</div>\n</div>\n</body>\n</html>")
    return "".join(parts)


def main() -> None:
    s = build_report()
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(s)
    print(OUT_HTML, file=sys.stderr)


if __name__ == "__main__":
    main()
