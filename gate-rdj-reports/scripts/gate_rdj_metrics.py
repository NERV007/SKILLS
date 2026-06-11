# -*- coding: utf-8 -*-
"""
从「需求导出-Gate-RDJ.csv」解析并聚合 Gate-RDJ 报告所需指标。
口径与既有 HTML 报告一致：
- 按「完成日期」所在月份分桶（无完成日期则不计入分月统计）。
- 总工时（五阶段）= 技术方案设计与评审估分 + 研发总估分 + QC用例估分 + 测试估分 + 预发测试估分
- 修正研发 = 技术方案设计与评审 + 各工种开发估分总和 + max(0, 测试估分−测试节点估分(去除RD))
- 测试工时 = 测试总估分(去除RD)；若为空则用 QC用例估分+测试估分+预发测试估分
- R/T = 修正研发 ÷ 测试工时
"""
from __future__ import annotations

import csv
import json
import math
import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple


def _pf(x: Any) -> float:
    if x is None:
        return 0.0
    s = str(x).strip()
    if s in ("", "-", "—", "None", "null"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_dt(s: Any) -> Optional[datetime]:
    if not s or not str(s).strip():
        return None
    s = str(s).strip().split()[0]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10].replace("/", "-"), "%Y-%m-%d")
        except ValueError:
            continue
    return None


def _month_key(d: Optional[datetime]) -> Optional[str]:
    if not d:
        return None
    return f"{d.year}-{d.month:02d}"


def _cycle_days(created: Optional[datetime], done: Optional[datetime]) -> Optional[float]:
    if not created or not done:
        return None
    delta = (done - created).days
    if delta < 0:
        return None
    return float(delta)


def _primary_qc(qc_field: str) -> str:
    if not qc_field:
        return "未分配"
    part = str(qc_field).split("|")[0].strip()
    return part or "未分配"


# 透视/宽表导出里常见的「某某共 N 个」汇总行（无完成日期），需排除以免重复计入
_ROLLUP_NAME_RE = re.compile(r"」共\s*\d+\s*个\s*$")

# 与 Gate-RDJ-12-v4 模板中 biz-content id 对齐（用于子项目→标准业务线 + Tab 匹配）
V4_CANONICAL_BIZ: Tuple[str, ...] = (
    "RDJ-增长工具",
    "RDJ-理财",
    "RDJ-合约",
    "RDJ-KYC",
    "RDJ-用户旅程",
    "RDJ-资产",
    "RDJ-营销活动",
    "RDJ-交易工具",
    "RDJ-PAY",
    "RDJ-返佣",
    "RDJ-行情中台",
    "RDJ-打新",
    "RDJ-社交",
    "RDJ-统一账户",
    "RDJ-现货",
    "RDJ-核心交易",
    "RDJ-平台基建",
    "RDJ-资管",
    "RDJ-期权",
    "RDJ-闪兑",
    "RDJ-管理中台",
    "RDJ-分站",
    "RDJ-VIP",
    "RDJ-广场",
    "RDJ-用户中心",
    "WEB3-Web3",
    "DATA",
    "RDJ-交易风控",
)

_V4_BIZ_LONGEST_FIRST: Tuple[str, ...] = tuple(sorted(V4_CANONICAL_BIZ, key=len, reverse=True))
_V4_CANON_SET = frozenset(V4_CANONICAL_BIZ)

# 所属子项目首段（非 RDJ- 前缀）→ 模板业务线
_SUBPROJ_HEAD_TO_BIZ: Dict[str, str] = {
    "合约": "RDJ-合约",
    "增长工具": "RDJ-增长工具",
    "2026资产": "RDJ-资产",
    "期权": "RDJ-期权",
    "VIP": "RDJ-VIP",
    "行情": "RDJ-行情中台",
    "统一账户功能": "RDJ-统一账户",
    "闪兑": "RDJ-闪兑",
    "KYC": "RDJ-KYC",
    "专业K线交易工具": "RDJ-交易工具",
    "支持各业务线行情需求": "RDJ-行情中台",
    "平台": "RDJ-平台基建",
    "模版活动": "RDJ-营销活动",
    "定制活动": "RDJ-营销活动",
    "PAY": "RDJ-PAY",
    "理财": "RDJ-理财",
    "社交": "RDJ-社交",
    "跟单": "RDJ-社交",
    "打新CandyDrop": "RDJ-打新",
    "打新Launchpool": "RDJ-打新",
    "行情性能和用户体验": "RDJ-行情中台",
    "返佣体验": "RDJ-返佣",
    "返佣基建": "RDJ-返佣",
    "借贷引擎": "RDJ-资管",
    "现货": "RDJ-现货",
    "资产": "RDJ-资产",
    "官网平台": "RDJ-用户中心",
    "活动中心": "RDJ-营销活动",
    "广场日常迭代": "RDJ-广场",
    "福利中心": "RDJ-广场",
    "资管平台": "RDJ-资管",
    "k线/行情": "RDJ-行情中台",
    "交易系统 3.0": "RDJ-核心交易",
    "保证金引擎": "RDJ-核心交易",
    "机构业务": "RDJ-VIP",
    "营销活动": "RDJ-营销活动",
    "社交渗透日常维护": "RDJ-社交",
    "裂变拉新非OKR类需求": "RDJ-增长工具",
    "增长中台非OKR类需求": "RDJ-增长工具",
    "邀请好友": "RDJ-增长工具",
    "Price": "RDJ-行情中台",
    "EU站": "RDJ-分站",
}


def filter_roll_up_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    return [r for r in rows if not _ROLLUP_NAME_RE.search((r.get("名称") or ""))]


# 迭代维度：从「所属迭代」解析桶键。必须带年份（2026-SP7），否则多年数据会挤进同一 SPn 导致占比全错/大量 0%。
_SP_AXIS_SORT_UE = 3000  # 无年份的「SPn」排在真实年份之后，便于排序稳定


def _sp_axis_sort_key(label: str) -> Tuple[int, int]:
    m = re.match(r"^(20\d{2})-SP(\d+)$", label)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    m2 = re.match(r"^SP(\d+)$", label)
    if m2:
        return (_SP_AXIS_SORT_UE, int(m2.group(1)))
    return (9999, 9999)


# 迭代维横轴排除的 SP 编号（如 SP10 仅 1 条噪声，不进入图表与分 SP 汇总）
EXCLUDED_ITERATION_SP_NUMBERS: frozenset = frozenset({10})


def _iteration_label_excluded(label: Optional[str]) -> bool:
    """是否从迭代维统计中剔除（匹配 2026-SP10 / SP10 等）。"""
    if not label:
        return False
    m = re.match(r"^(20\d{2})-SP(\d+)$", label, re.IGNORECASE)
    if m:
        return int(m.group(2)) in EXCLUDED_ITERATION_SP_NUMBERS
    m2 = re.match(r"^SP(\d+)$", label, re.IGNORECASE)
    if m2:
        return int(m2.group(1)) in EXCLUDED_ITERATION_SP_NUMBERS
    return False


def _sp_label(r: Dict[str, str]) -> Optional[str]:
    raw = (r.get("所属迭代") or "").strip()
    if not raw:
        return None
    raw_c = re.sub(r"\s+", "", raw)
    # 常见：2026SP7(4.14~4.27)、2026-SP7
    m = re.search(r"(20\d{2})SP(\d+)", raw_c, re.IGNORECASE)
    if m:
        y, n = int(m.group(1)), int(m.group(2))
        if 1 <= n <= 99:
            return f"{y}-SP{n}"
    m2 = re.search(r"SP(\d+)", raw_c, re.IGNORECASE)
    if m2:
        n = int(m2.group(1))
        if 1 <= n <= 99:
            return f"SP{n}"
    return None


def _biz_line(r: Dict[str, str]) -> str:
    """
    业务线分桶：优先「业务线」列；无列或为空时用「所属子项目」归一到与 v4 模板一致的标准名，
    以便 Sankey / 热力 / v4 主 Tab 与既有 HTML 面板 id 对齐。
    """
    b = (r.get("业务线") or "").strip()
    if b:
        return b
    sub = (r.get("所属子项目") or "").strip()
    if not sub:
        return "未分类"
    for tok in _V4_BIZ_LONGEST_FIRST:
        if sub.startswith(tok):
            return tok
    if sub.startswith("RDJ-"):
        parts = sub.split("-")
        if len(parts) >= 2:
            cand = f"RDJ-{parts[1]}"
            if cand in _V4_CANON_SET:
                return cand
        return "其他"
    head = sub.split("-", 1)[0].strip()
    if head in _SUBPROJ_HEAD_TO_BIZ:
        return _SUBPROJ_HEAD_TO_BIZ[head]
    if head:
        return "其他"
    return "未分类"


def load_rows(csv_path: str) -> List[Dict[str, str]]:
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return filter_roll_up_rows(rows)


_STORY_ID_RE = re.compile(r"/detail/(\d+)")


def main_row_dedupe_key(row: Dict[str, str]) -> str:
    """主站时间维/迭代维合并去重键：优先 story ID，其次规范化链接，最后 名称|完成日期。"""
    link = (row.get("需求链接") or "").strip()
    if link:
        m = _STORY_ID_RE.search(link)
        if m:
            return f"id:{m.group(1)}"
        base = link.split("?")[0].rstrip("/")
        if base:
            return f"url:{base}"
    name = (row.get("名称") or "").strip()
    done = (row.get("完成日期") or "").strip()
    return f"name:{name}|{done}"


def dedupe_main_rows(paths: List[str]) -> List[Dict[str, str]]:
    """合并多份主站 Gate-RDJ CSV（时间维+迭代维），按 main_row_dedupe_key 去重，先出现的优先。"""
    seen: set[str] = set()
    merged: List[Dict[str, str]] = []
    for p in paths:
        try:
            rows = load_rows(p)
        except OSError:
            continue
        for r in rows:
            key = main_row_dedupe_key(r)
            if key in seen:
                continue
            seen.add(key)
            merged.append(r)
    return merged


DEV_ROLE_COLS = (
    "FE开发 估分",
    "BE开发 估分",
    "APP开发 估分",
    "Engine开发 估分",
    "DATA开发 估分",
    "WS开发 估分",
    "WBE开发 估分",
    "Admin开发 估分",
)


def dev_roles_total(r: Dict[str, str]) -> float:
    """各工种开发估分总和；工种列全空时回退「研发总估分」。"""
    roles = sum(_pf(r.get(c)) for c in DEV_ROLE_COLS)
    if roles > 0:
        return roles
    return _pf(r.get("研发总估分"))


def effort_fields(r: Dict[str, str]) -> Tuple[float, float, float, float, float, float, float]:
    """design, rd, qc, test_node_col, test, pre, test_total_col"""
    d = _pf(r.get("技术方案设计与评审 估分"))
    rd = _pf(r.get("研发总估分"))
    qc = _pf(r.get("QC测试用例设计与评审 估分"))
    tnode = _pf(r.get("测试节点估分(去除 RD)"))
    te = _pf(r.get("测试 估分"))
    pr = _pf(r.get("预发测试估分"))
    tt = _pf(r.get("测试总估分(去除RD)"))
    if tt <= 0:
        tt = qc + te + pr
    return d, rd, qc, tnode, te, pr, tt


def five_phase_total(r: Dict[str, str]) -> float:
    d, rd, qc, _, te, pr, _ = effort_fields(r)
    return d + rd + qc + te + pr


def corrected_rd(r: Dict[str, str]) -> float:
    """修正研发工时 = 技术方案设计与评审 + 各工种开发估分总和 + 测试估分 − 测试节点估分(去除RD)。"""
    d, _, _, tnode, te, _, _ = effort_fields(r)
    return d + dev_roles_total(r) + max(0.0, te - tnode)


def _normalize_qc_token_local(name: str) -> str:
    s = (name or "").strip()
    if not s:
        return ""
    s = s.replace("（", "(")
    s = s.split("(", 1)[0].strip()
    s = s.split("|", 1)[0].strip()
    s = s.split("-", 1)[0].strip().lower()
    s = re.sub(r"[^a-z0-9_]+", "", s)
    return s


def _qc_field_raw_parts(qc_field: object) -> List[str]:
    s = str(qc_field or "").strip()
    if not s or s.lower() in ("-", "—", "nan", "none"):
        return []
    s = s.replace("｜", "|")
    out: List[str] = []
    for part in re.split(r"[|,/，、]+", s):
        part = part.strip()
        if part and part.lower() not in ("-", "—"):
            out.append(part)
    return out


def _token_has_qc_suffix(part: str) -> bool:
    """后缀带 -QC / -qc 视为测试侧（含已离职、未在 department_stats 名册的 QC）。"""
    s = (part or "").strip()
    if not s:
        return False
    return bool(re.search(r"[-_][Qq][Cc]$", s))


def split_qc_field_roles(
    qc_field: object, allow: Optional[set[str]] = None
) -> Tuple[List[str], List[str]]:
    """QC 列按后缀拆分：-QC/-qc → 测试侧；否则 → 开发角色（如 Change、role-s-qa）。

    仅影响展示列；不调整 corrected_rd / 测试工时（个案用工时修正 Tab）。
    """
    _ = allow  # 部门白名单仅用于归属，不用于 QC/开发展示拆分
    qc_parts: List[str] = []
    dev_parts: List[str] = []
    seen_qc: set[str] = set()
    seen_dev: set[str] = set()
    for part in _qc_field_raw_parts(qc_field):
        key = part.lower()
        if _token_has_qc_suffix(part):
            if key not in seen_qc:
                seen_qc.add(key)
                qc_parts.append(part)
        else:
            if key not in seen_dev:
                seen_dev.add(key)
                dev_parts.append(part)
    return qc_parts, dev_parts


def main_station_test_hours_core(r: Dict[str, str]) -> float:
    """测试工时（核心）：测试总估分(去除RD)；空则 QC用例+测试+预发。"""
    _, _, qc, _, te, pr, tt = effort_fields(r)
    return tt if tt > 0 else qc + te + pr


def main_station_role_hours(
    r: Dict[str, str],
    allow: Optional[set[str]] = None,
    test_floor: float = 0.05,
) -> Tuple[float, float, Optional[float], List[str], List[str]]:
    """主站研发/测试工时 + R/T（仅核心公式，不按 QC 列人头拆测试阶段工时）。

    - 研发 = corrected_rd
    - 测试 = main_station_test_hours_core
    - QC 列白名单/非白名单仅用于展示拆分，不调整工时。
    """
    rc = corrected_rd(r)
    test_h = main_station_test_hours_core(r)
    qc_parts, dev_parts = split_qc_field_roles(r.get("QC") or "", allow or set())
    rt = (
        round(rc / test_h, 2)
        if test_h > test_floor and rc > 0
        else None
    )
    return round(rc, 2), round(test_h, 2), rt, qc_parts, dev_parts


def is_urgent(r: Dict[str, str]) -> bool:
    v = (r.get("是否紧急需求") or "").strip()
    return "紧急" in v and "非" not in v


def is_station(r: Dict[str, str]) -> bool:
    return "分站" in (r.get("所属子项目") or "") or "分站" in (r.get("价值类型") or "")


def iqr_filter(
    values: List[float], mult: float = 1.5
) -> Tuple[List[float], int, int]:
    """返回 (保留值列表, 排除无效数, 排除异常数)"""
    vals = [v for v in values if v is not None and v > 0]
    invalid = len(values) - len(vals)
    if len(vals) < 4:
        return vals, invalid, 0
    sorted_vals = sorted(vals)
    n = len(sorted_vals)
    q1 = sorted_vals[n // 4]
    q3 = sorted_vals[(3 * n) // 4]
    iqr = q3 - q1 or 1e-9
    hi = q3 + mult * iqr
    kept = [v for v in sorted_vals if v <= hi]
    outliers = len(sorted_vals) - len(kept)
    return kept, invalid, outliers


MIN_MONTH_DEMANDS = 5  # 月份需求数低于此值则视为边缘噪声月，不纳入横轴
TIME_AXIS_END = "2026-05"  # 时间维报告最大完成月（含）；更晚完成月不参与统计


def _month_allowed_on_time_axis(mk: Optional[str]) -> bool:
    if not mk:
        return True
    if TIME_AXIS_END and mk > TIME_AXIS_END:
        return False
    return True


def filter_rows_for_time_axis(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """排除完成月晚于 TIME_AXIS_END 的需求（时间维专用）。"""
    out: List[Dict[str, str]] = []
    for r in rows:
        mk = _month_key(_parse_dt(r.get("完成日期")))
        if _month_allowed_on_time_axis(mk):
            out.append(r)
    return out


def build_month_list(rows: List[Dict[str, str]]) -> List[str]:
    """返回需求数 >= MIN_MONTH_DEMANDS 的月份列表（过滤首尾噪声月）。"""
    c: Dict[str, int] = defaultdict(int)
    for r in rows:
        mk = _month_key(_parse_dt(r.get("完成日期")))
        if mk and _month_allowed_on_time_axis(mk):
            c[mk] += 1
    return sorted(k for k, v in c.items() if v >= MIN_MONTH_DEMANDS)


def contiguous_month_span(sorted_keys: List[str]) -> List[str]:
    """在最小月～最大月之间补全连续月份（与图表 X 轴、环比表一致）。"""
    if not sorted_keys or sorted_keys == ["N/A"]:
        return sorted_keys
    start, end = sorted_keys[0], sorted_keys[-1]
    y0, m0 = int(start[:4]), int(start[5:7])
    y1, m1 = int(end[:4]), int(end[5:7])
    out: List[str] = []
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        out.append(f"{y}-{m:02d}")
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return out


def _pct(part: float, whole: float) -> float:
    if whole <= 0:
        return 0.0
    return round(part / whole * 100, 1)


def _pct_change(old: float, new: float) -> float:
    if old == 0:
        return 0.0 if new == 0 else 100.0
    return round((new - old) / abs(old) * 100, 1)


def _month_period_key(r: Dict[str, str]) -> Optional[str]:
    """默认横轴：完成日期所在月 YYYY-MM。"""
    return _month_key(_parse_dt(r.get("完成日期")))


def build_data_payload(
    rows: List[Dict[str, str]],
    *,
    period_axis: str = "month",
) -> Tuple[Dict[str, Any], Dict[str, Any], str, str]:
    """
    返回 (data, delivery_sd, date_range_label, months_joined)
    data 与既有 Gate-RDJ-12-skill-需求分析报告.html 中 var data 的顶层结构对齐。
    period_axis: \"month\" 按完成日期所在月；\"iteration\" 按所属迭代（年+SPRINT，如 2026-SP7）。
    """
    use_sp = period_axis == "iteration"

    def pk(r: Dict[str, str]) -> Optional[str]:
        return _sp_label(r) if use_sp else _month_key(_parse_dt(r.get("完成日期")))

    if use_sp:
        rows = [r for r in rows if not _iteration_label_excluded(pk(r))]
        keys = sorted(
            {k for k in (pk(r) for r in rows) if k and not _iteration_label_excluded(k)},
            key=_sp_axis_sort_key,
        )
        months = keys if keys else ["N/A"]
        month_counts: Dict[str, Any] = {m: 0 for m in months} if keys else defaultdict(int)
        for r in rows:
            k = pk(r)
            if not k:
                continue
            if keys and k in month_counts:
                month_counts[k] += 1
            elif not keys:
                month_counts[k] += 1
    else:
        rows = filter_rows_for_time_axis(rows)
        raw_month_keys = build_month_list(rows)
        months = contiguous_month_span(raw_month_keys) if raw_month_keys else ["N/A"]
        # ---------- 分月需求数（完成月），连续区间内缺月补 0 ----------
        if months == ["N/A"]:
            month_counts = defaultdict(int)
            for r in rows:
                mk = pk(r)
                if mk:
                    month_counts[mk] += 1
        else:
            month_counts = {m: 0 for m in months}
            for r in rows:
                mk = pk(r)
                if mk in month_counts:
                    month_counts[mk] += 1

    month_with_chain: List[Dict[str, Any]] = []
    prev_v: Optional[int] = None
    for m in months:
        v = month_counts[m] if isinstance(month_counts, dict) else month_counts.get(m, 0)
        ratio = None if prev_v is None or prev_v == 0 else round((v - prev_v) / prev_v * 100, 1)
        month_with_chain.append({"name": m, "value": v, "chain_ratio": ratio})
        prev_v = v

    # ---------- 全局五阶段 ----------
    g_design = g_rd = g_qc = g_te = g_tnode = g_pr = g_tt = 0.0
    g_bugs = 0.0
    g_node = 0.0
    for r in rows:
        d, rd, qc, tnode, te, pr, tt = effort_fields(r)
        g_design += d
        g_rd += rd
        g_qc += qc
        g_tnode += tnode
        g_te += te
        g_pr += pr
        g_tt += tt
        g_bugs += _pf(r.get("总 bug 数"))
        g_node += _pf(r.get("全部节点估分"))

    five_sum = g_design + g_rd + g_qc + g_te + g_pr
    phase_workload = [
        {"name": "技术方案设计与评审", "value": round(g_design, 1), "pct": _pct(g_design, five_sum)},
        {"name": "研发", "value": round(g_rd, 1), "pct": _pct(g_rd, five_sum)},
        {"name": "QC用例评审", "value": round(g_qc, 1), "pct": _pct(g_qc, five_sum)},
        {"name": "测试", "value": round(g_te, 1), "pct": _pct(g_te, five_sum)},
        {"name": "预发", "value": round(g_pr, 1), "pct": _pct(g_pr, five_sum)},
    ]
    g_rd_corr = sum(corrected_rd(r) for r in rows)
    rd_test_pie = [
        {"name": "研发工时", "value": round(g_rd_corr, 1)},
        {"name": "测试工时", "value": round(g_tt, 1)},
    ]

    total_demands = len(rows)
    total_test = round(g_tt, 1)
    total_rd_corr = round(g_rd_corr, 1)
    avg_rt = round(total_rd_corr / total_test, 2) if total_test > 0 else 0.0

    # ---------- 按业务线 ----------
    by_biz_map: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "n": 0,
            "design": 0.0,
            "rd": 0.0,
            "rd_corr": 0.0,
            "qc": 0.0,
            "tnode": 0.0,
            "te": 0.0,
            "pr": 0.0,
            "tt": 0.0,
            "node": 0.0,
            "bugs": 0.0,
            "cycles": [],
            "urgent": 0,
            "station": 0,
        }
    )
    for r in rows:
        b = _biz_line(r)
        o = by_biz_map[b]
        d, rd, qc, tnode, te, pr, tt = effort_fields(r)
        o["n"] += 1
        o["design"] += d
        o["rd"] += rd
        o["qc"] += qc
        o["tnode"] += tnode
        o["te"] += te
        o["pr"] += pr
        o["tt"] += tt
        o["node"] += _pf(r.get("全部节点估分"))
        o["bugs"] += _pf(r.get("总 bug 数"))
        cy = _cycle_days(_parse_dt(r.get("创建时间")), _parse_dt(r.get("完成日期")))
        if cy is not None:
            o["cycles"].append(cy)
        if is_urgent(r):
            o["urgent"] += 1
        if is_station(r):
            o["station"] += 1
        o["rd_corr"] = o.get("rd_corr", 0.0) + corrected_rd(r)

    def biz_row(name: str, o: Dict[str, Any]) -> Dict[str, Any]:
        n = max(o["n"], 1)
        crd = o.get("rd_corr", o["design"] + o["rd"] + max(0.0, o["te"] - o["tnode"]))
        tt = o["tt"]
        five = o["design"] + o["rd"] + o["qc"] + o["te"] + o["pr"]
        avg_c = sum(o["cycles"]) / len(o["cycles"]) if o["cycles"] else 0.0
        # 工作日近似：*5/7
        avg_wd = avg_c * 5.0 / 7.0 if avg_c else 0.0
        rt = round(crd / tt, 3) if tt > 0 else 0.0
        test_pct = round(tt / five * 100, 1) if five > 0 else 0.0
        bugs = o["bugs"]
        return {
            "name": name,
            "demand_count": o["n"],
            "total_score": round(o["node"], 1),
            "design": round(o["design"], 1),
            "rd": round(o["rd"], 1),
            "qc_design": round(o["qc"], 1),
            "test_node": round(o["tnode"], 1),
            "test_score": round(o["te"], 1),
            "test_total": round(tt, 1),
            "pre_test": round(o["pr"], 1),
            "bugs": bugs,
            "corrected_rd": round(crd, 1),
            "rt_ratio": rt,
            "avg_score_per_demand": round(o["node"] / n, 3),
            "avg_bugs_per_demand": round(bugs / n, 3),
            "avg_delivery_cycle_days": round(avg_c, 2),
            "avg_delivery_cycle_wd": round(avg_wd, 2),
            "duration_count": len(o["cycles"]),
            "test_efficiency": round(o["node"] / tt, 2) if tt > 0 else 0.0,
            "avg_score_per_duration": round(o["node"] / avg_c, 3) if avg_c > 0 else 0.0,
            "total_workload": round(five, 1),
            "test_pct": round(test_pct, 1),
            "urgent_count": o["urgent"],
            "urgent_pct": round(o["urgent"] / n * 100, 1),
            "fenzan_count": 0,
            "fenzan_pct": 0.0,
            "demand_density": round(o["node"] / n, 2),
            "quality_index": round(bugs / n / 2.0, 2),
            "cost_efficiency": round(tt / (o["node"] + 1e-6), 4),
            "resource_utilization": round(five / (o["node"] + 1e-6), 2),
            "delivery_speed": round(n / (avg_c + 1e-6), 3) if avg_c > 0 else 0.0,
            "stability_index": round(1.0 - min(1.0, bugs / (o["node"] + 1)), 2),
            "bug_density": round(bugs / (tt + 1e-6), 2),
            "tech_debt_index": 0.95,
            "maturity_score": round(min(5.0, max(1.0, 4.5 - test_pct / 25.0 + (rt - 1.5) * 0.5)), 2),
            "risk_level": ("高" if test_pct > 48 or rt < 1.2 else ("中" if test_pct > 38 or rt < 1.6 else "低")),
        }

    biz_list = [biz_row(b, by_biz_map[b]) for b in sorted(by_biz_map, key=lambda x: -by_biz_map[x]["n"])]
    by_biz_chart = [{"name": b["name"], "value": b["demand_count"]} for b in biz_list[:12]]
    score_by_biz = [{"name": b["name"], "value": b["total_score"]} for b in sorted(biz_list, key=lambda x: -x["total_score"])[:15]]
    duration_score_by_biz = [
        {"name": b["name"], "duration": b["avg_delivery_cycle_days"], "score": b["total_score"]}
        for b in sorted(biz_list, key=lambda x: -x["demand_count"])[:14]
    ]
    bug_by_biz = [
        {"name": _short_biz(b["name"]), "value": float(b["bugs"])}
        for b in sorted(biz_list, key=lambda x: -x["bugs"])[:15]
    ]
    qc_by_biz = [{"name": b["name"], "value": round(b["qc_design"], 1)} for b in biz_list]
    test_stages_by_biz = [
        {"name": b["name"], "qc_design": b["qc_design"], "test_node": b["test_node"], "pre_test": b["pre_test"]}
        for b in biz_list
    ]

    # sankey: 业务线 -> 五阶段（节点名与旧版一致）
    sankey_biz_nodes = [{"name": b["name"]} for b in biz_list]
    phase_node_names = ["设计评审", "研发", "QC用例评审", "测试", "预发测试"]
    sankey_nodes = sankey_biz_nodes + [{"name": n} for n in phase_node_names]
    sankey_links = []
    for b in biz_list:
        nm = b["name"]
        sankey_links.append({"source": nm, "target": "设计评审", "value": round(b["design"], 1)})
        sankey_links.append({"source": nm, "target": "研发", "value": round(b["rd"], 1)})
        sankey_links.append({"source": nm, "target": "QC用例评审", "value": round(b["qc_design"], 1)})
        sankey_links.append({"source": nm, "target": "测试", "value": round(b["test_score"], 1)})
        sankey_links.append({"source": nm, "target": "预发测试", "value": round(b["pre_test"], 1)})

    # ---------- 价值类型等维度 ----------
    def count_dim(key: str) -> List[Dict[str, Any]]:
        m: Dict[str, int] = defaultdict(int)
        for r in rows:
            v = (r.get(key) or "").strip() or "未分类"
            m[v] += 1
        arr = [{"name": k, "value": v} for k, v in m.items()]
        arr.sort(key=lambda x: -x["value"])
        return arr

    by_value_type = count_dim("价值类型")
    by_priority = count_dim("优先级")
    by_status = count_dim("状态")
    by_req_type = count_dim("需求类型")
    by_month = [{"name": m, "value": month_counts.get(m, 0)} for m in months]

    # value_type_list
    vt_map: Dict[str, Any] = defaultdict(
        lambda: {"n": 0, "node": 0.0, "bugs": 0.0, "tt": 0.0}
    )
    for r in rows:
        vt = (r.get("价值类型") or "").strip() or "未分类"
        o = vt_map[vt]
        o["n"] += 1
        o["node"] += _pf(r.get("全部节点估分"))
        o["bugs"] += _pf(r.get("总 bug 数"))
        *_, tt = effort_fields(r)
        o["tt"] += tt
    total_node = sum(x["node"] for x in vt_map.values()) or 1.0
    value_type_list = []
    for vt, o in sorted(vt_map.items(), key=lambda x: -x[1]["n"]):
        value_type_list.append(
            {
                "name": vt,
                "demand_count": o["n"],
                "total_effort": round(o["node"], 1),
                "bugs": int(o["bugs"]),
                "test_total": round(o["tt"], 1),
                "demand_density": round(o["n"] / total_demands * 100, 2) if total_demands else 0,
                "avg_bugs_per_demand": round(o["bugs"] / max(o["n"], 1), 2),
                "effort_pct": round(o["node"] / total_node * 100, 1),
            }
        )
    value_type_top5 = []
    for i, vt in enumerate(sorted(vt_map.items(), key=lambda x: -x[1]["n"])[:5], 1):
        name, o = vt
        value_type_top5.append(
            {
                "rank": i,
                "name": name,
                "demand_count": o["n"],
                "pct_demand": round(o["n"] / total_demands * 100, 1) if total_demands else 0,
                "total_effort": round(o["node"], 1),
                "bugs": int(o["bugs"]),
            }
        )
    top5_demand = sum(x["demand_count"] for x in value_type_top5) / total_demands * 100 if total_demands else 0
    top5_effort = sum(vt_map[x["name"]]["node"] for x in value_type_top5) / total_node * 100 if value_type_list else 0
    value_type_summary = {
        "value_type_count": len(vt_map),
        "top5_demand_pct": round(top5_demand, 1),
        "top5_effort_pct": round(top5_effort, 1),
        "avg_demand_density": round(
            sum(x["demand_density"] for x in value_type_list) / max(len(value_type_list), 1), 2
        ),
        "avg_test_per_demand": round(total_test / total_demands, 2) if total_demands else 0,
    }

    # dim_biz_vt, dim_biz_priority
    dim_biz_vt: List[Dict[str, Any]] = []
    for r in rows:
        dim_biz_vt.append(
            {
                "biz": _biz_line(r),
                "vt": (r.get("价值类型") or "").strip() or "未分类",
                "count": 1,
            }
        )
    # 聚合相同组合
    dd: Dict[Tuple[str, str], int] = defaultdict(int)
    for x in dim_biz_vt:
        dd[(x["biz"], x["vt"])] += 1
    dim_biz_vt = [{"biz": a, "vt": b, "count": c} for (a, b), c in sorted(dd.items(), key=lambda x: -x[1])]

    dim_biz_priority = []
    ddp: Dict[Tuple[str, str], int] = defaultdict(int)
    for r in rows:
        ddp[(_biz_line(r), (r.get("优先级") or "").strip() or "-")] += 1
    dim_biz_priority = [{"biz": a, "priority": b, "count": c} for (a, b), c in sorted(ddp.items(), key=lambda x: -x[1])]

    # ---------- 分月五阶段热力 + 3D ----------
    month_idx = {m: i for i, m in enumerate(months)}
    phase_labels = ["设计评审", "研发", "QC用例", "测试", "预发"]
    heat_data = []
    for m in months:
        mi = month_idx[m]
        acc = [0.0] * 5
        for r in rows:
            if pk(r) != m:
                continue
            d, rd, qc, _, te, pr, _ = effort_fields(r)
            acc[0] += d
            acc[1] += rd
            acc[2] += qc
            acc[3] += te
            acc[4] += pr
        for pj, val in enumerate(acc):
            heat_data.append([mi, pj, round(val, 1)])
    heat_month_phase = {"xAxis": months, "yAxis": phase_labels, "data": heat_data}

    # heat_biz_month: 与模板 JS 一致 — bizMonthWork[bizIdx][monthIdx] = value，故为 [月索引, 业务线索引, 值]
    heat_biz_month_data = []
    for bi, b in enumerate(biz_list[:20]):
        for m in months:
            ssum = 0.0
            for r in rows:
                if _biz_line(r) != b["name"]:
                    continue
                if pk(r) != m:
                    continue
                ssum += five_phase_total(r)
            heat_biz_month_data.append([month_idx[m], bi, round(ssum, 1)])
    heat_biz_month = {
        "xAxis": months,
        "yAxis": [b["name"] for b in biz_list[:20]],
        "data": heat_biz_month_data,
    }

    # heat_biz_phase
    hbp_data = []
    for bi, b in enumerate(biz_list[:20]):
        acc = [0.0] * 5
        for r in rows:
            if _biz_line(r) != b["name"]:
                continue
            d, rd, qc, _, te, pr, _ = effort_fields(r)
            acc[0] += d
            acc[1] += rd
            acc[2] += qc
            acc[3] += te
            acc[4] += pr
        for pj, val in enumerate(acc):
            hbp_data.append([bi, pj, round(val, 1)])
    heat_biz_phase = {
        "xAxis": [b["name"] for b in biz_list[:20]],
        "yAxis": phase_labels,
        "data": hbp_data,
    }

    biz_month_phase_3d = []
    for bi, b in enumerate(biz_list):
        for mi, m in enumerate(months):
            acc = [0.0] * 5
            for r in rows:
                if _biz_line(r) != b["name"]:
                    continue
                if pk(r) != m:
                    continue
                d, rd, qc, _, te, pr, _ = effort_fields(r)
                acc[0] += d
                acc[1] += rd
                acc[2] += qc
                acc[3] += te
                acc[4] += pr
            biz_month_phase_3d.append([b["name"], mi, [round(x, 1) for x in acc]])

    # ---------- 分月平均工期（自然日 / 工作日近似）----------
    month_avg_cycle = []
    month_avg_cycle_wd = []
    monthly_eff = []
    monthly_summary = []
    month_test_totals = []
    throughput_by_month = []
    by_month_effort: Dict[str, float] = defaultdict(float)

    for m in months:
        cys = []
        t_eff = 0.0
        rd_m = 0.0
        d_m = 0.0
        te_m = 0.0
        tnode_m = 0.0
        n_m = 0
        for r in rows:
            if pk(r) != m:
                continue
            n_m += 1
            cy = _cycle_days(_parse_dt(r.get("创建时间")), _parse_dt(r.get("完成日期")))
            if cy is not None:
                cys.append(cy)
            _d, _rd, _qc, _tnode, _te, _pr, tt = effort_fields(r)
            t_eff += tt
            d_m += _d
            rd_m += _rd
            te_m += _te
            tnode_m += _tnode
            by_month_effort[m] += five_phase_total(r)
        avg_c = sum(cys) / len(cys) if cys else 0.0
        month_avg_cycle.append(round(avg_c, 2))
        month_avg_cycle_wd.append(round(avg_c * 5.0 / 7.0, 2))
        m_rd_corr = sum(corrected_rd(r) for r in rows if pk(r) == m)
        monthly_eff.append(
            {
                "month": m,
                "demands": n_m,
                "test_effort": round(t_eff, 1),
                "efficiency": round(n_m / (t_eff + 1e-6), 2),
            }
        )
        monthly_summary.append(
            {
                "month": m,
                "demands": n_m,
                "test_effort": round(t_eff, 1),
                "rd_corrected": round(m_rd_corr, 1),
                "rt_ratio": round(m_rd_corr / (t_eff + 1e-6), 2),
            }
        )
        # t_eff：effort_fields 的「测试总估分(去除RD)」列；缺列时为 qc+测试+预发，与 HTML 中 monthTestWork（热力 phase 索引 2–4）分子口径一致
        month_test_totals.append({"name": m, "value": round(t_eff, 1)})
        throughput_by_month.append({"name": m, "value": n_m})

    # ---------- delivery_sd（各阶段日历天近似）----------
    delivery_sd = _build_delivery_sd(rows, months, month_avg_cycle, pk)

    # ---------- biz_month_cycle_map ----------
    biz_month_cycle_map: Dict[str, Dict[str, float]] = defaultdict(dict)
    for b in biz_list:
        name = b["name"]
        for m in months:
            cys = []
            for r in rows:
                if _biz_line(r) != name:
                    continue
                if pk(r) != m:
                    continue
                cy = _cycle_days(_parse_dt(r.get("创建时间")), _parse_dt(r.get("完成日期")))
                if cy is not None:
                    cys.append(cy)
            biz_month_cycle_map[name][m] = round(sum(cys) / len(cys), 2) if cys else 0.0

    # ---------- 紧急 / 分站 分月 ----------
    monthly_urgent = []
    for m in months:
        tot = urg = 0
        t_eff = ur_te = 0.0
        for r in rows:
            if pk(r) != m:
                continue
            tot += 1
            *_, tt = effort_fields(r)
            t_eff += tt
            if is_urgent(r):
                urg += 1
                ur_te += tt
        monthly_urgent.append(
            {
                "month": m,
                "total": tot,
                "urgent": urg,
                "pct": round(urg / tot * 100, 1) if tot else 0,
                "test_effort": round(t_eff, 1),
                "urgent_test": round(ur_te, 1),
                "urgent_test_pct": round(ur_te / (t_eff + 1e-6) * 100, 1),
            }
        )

    biz_urgent = []
    for b in biz_list:
        tot = urg = 0
        t_eff = ur_te = 0.0
        for r in rows:
            if _biz_line(r) != b["name"]:
                continue
            tot += 1
            *_, tt = effort_fields(r)
            t_eff += tt
            if is_urgent(r):
                urg += 1
                ur_te += tt
        biz_urgent.append(
            {
                "name": b["name"],
                "total": tot,
                "urgent": urg,
                "pct": round(urg / tot * 100, 1) if tot else 0,
                "test_effort": round(t_eff, 1),
                "urgent_test": round(ur_te, 1),
                "urgent_test_pct": round(ur_te / (t_eff + 1e-6) * 100, 1),
            }
        )

    monthly_station = []
    for m in months:
        tot = st = 0
        t_eff = st_te = 0.0
        for r in rows:
            if pk(r) != m:
                continue
            tot += 1
            *_, tt = effort_fields(r)
            t_eff += tt
            if is_station(r):
                st += 1
                st_te += tt
        monthly_station.append(
            {
                "month": m,
                "total": tot,
                "station": st,
                "pct": round(st / tot * 100, 1) if tot else 0,
                "test_effort": round(t_eff, 1),
                "station_test": round(st_te, 1),
                "station_test_pct": round(st_te / (t_eff + 1e-6) * 100, 1),
            }
        )

    sta_tot = sta_st = 0
    sta_te = sta_st_te = 0.0
    for r in rows:
        sta_tot += 1
        *_, tt = effort_fields(r)
        sta_te += tt
        if is_station(r):
            sta_st += 1
            sta_st_te += tt
    station_summary = {
        "total": sta_tot,
        "pct": round(sta_st / sta_tot * 100, 1) if sta_tot else 0,
        "test_effort": round(sta_te, 1),
        "test_pct": round(sta_st_te / (sta_te + 1e-6) * 100, 1),
        "total_demands": sta_tot,
    }
    biz_station: List[Any] = []

    # ---------- summary / stats ----------
    cycles_all = []
    for r in rows:
        cy = _cycle_days(_parse_dt(r.get("创建时间")), _parse_dt(r.get("完成日期")))
        if cy is not None:
            cycles_all.append(cy)
    avg_cycle_all = sum(cycles_all) / len(cycles_all) if cycles_all else 0.0
    summary = {
        "total_demands": total_demands,
        "total_effort": round(five_sum, 1),
        "total_bugs": int(g_bugs),
        "total_test": total_test,
        "avg_cycle": round(avg_cycle_all, 2),
        "rt_ratio": avg_rt,
    }
    summary_stats = {
        "biz_count": len(biz_list),
        "total_demands": total_demands,
        "total_score": round(g_node, 1),
        "total_bugs": int(g_bugs),
        "total_rd": round(g_rd + g_design, 1),
        "total_test": total_test,
        "avg_rt_ratio": avg_rt,
        "qc_per_person": round(total_demands / max(1, len({ _primary_qc(r.get("QC") or "") for r in rows })), 2),
        "five_phase_total": round(five_sum, 1),
    }

    # jan / feb 占位：取分月列表最后两个月填「对比用」结构（前端仍读 jan_2026 / feb_2026）
    def month_bucket_stats(month: str) -> Dict[str, Any]:
        demands = 0
        test_effort = d = rd = qc = tnode = te = pr = bugs = 0.0
        for r in rows:
            if pk(r) != month:
                continue
            demands += 1
            dd_, rdd, qcc, tnd, tee, prr, ttt = effort_fields(r)
            test_effort += ttt
            rd += rdd
            d += dd_
            qc += qcc
            tnode += tnd
            te += tee
            pr += prr
            bugs += _pf(r.get("总 bug 数"))
        five_m = sum(
            five_phase_total(r)
            for r in rows
            if pk(r) == month
        )
        rd_corr = sum(corrected_rd(r) for r in rows if pk(r) == month)
        cys = []
        for r in rows:
            if pk(r) != month:
                continue
            cy = _cycle_days(_parse_dt(r.get("创建时间")), _parse_dt(r.get("完成日期")))
            if cy is not None:
                cys.append(cy)
        cavg = sum(cys) / len(cys) if cys else 0.0
        urg = sum(1 for r in rows if pk(r) == month and is_urgent(r))
        urgent_pct = round(urg / demands * 100, 1) if demands else 0.0
        test_pct = round(test_effort / five_m * 100, 1) if five_m else 0.0
        rt_ratio = round(rd_corr / (test_effort + 1e-6), 2)
        eff = round(demands / (test_effort + 1e-6), 2)
        t_cost = round(test_effort / max(demands, 1), 2)
        bpd = round(bugs / max(demands, 1), 2)
        return {
            "demands": demands,
            "total_effort": round(five_m, 1),
            "test_effort": round(test_effort, 1),
            "bugs": int(bugs),
            "rd_effort": round(rd, 1),
            "rd_corrected": round(rd_corr, 1),
            "urgent_count": urg,
            "urgent_pct": urgent_pct,
            "pct": urgent_pct,
            "cycle": round(cavg, 2),
            "cycle_wd": round(cavg * 5.0 / 7.0, 2),
            "design": round(d, 1),
            "qc": round(qc, 1),
            "test_node": round(tnode + te, 1),
            "prefab": round(pr, 1),
            "pre_test": round(pr, 1),
            "test_pct": test_pct,
            "rt_ratio": rt_ratio,
            "efficiency": eff,
            "test_cost": t_cost,
            "bugs_per_demand": bpd,
        }

    m_last = months[-1] if months else ""
    m_prev = months[-2] if len(months) > 1 else m_last
    jan_2026 = month_bucket_stats(m_prev)
    feb_2026 = month_bucket_stats(m_last)
    if len(months) > 1:
        feb_2026["demands_change"] = _pct_change(jan_2026["demands"], feb_2026["demands"])
        feb_2026["total_change"] = _pct_change(jan_2026["total_effort"], feb_2026["total_effort"])
        feb_2026["test_change"] = _pct_change(jan_2026["test_effort"], feb_2026["test_effort"])
        feb_2026["bugs_change"] = _pct_change(float(jan_2026["bugs"]), float(feb_2026["bugs"]))
        feb_2026["rt_change"] = _pct_change(jan_2026["rt_ratio"], feb_2026["rt_ratio"])
        feb_2026["urgent_change"] = _pct_change(jan_2026["urgent_pct"], feb_2026["urgent_pct"])
        feb_2026["cycle_change"] = _pct_change(jan_2026["cycle"], feb_2026["cycle"])
    else:
        feb_2026["demands_change"] = 0.0
        feb_2026["total_change"] = 0.0
        feb_2026["test_change"] = 0.0
        feb_2026["bugs_change"] = 0.0
        feb_2026["rt_change"] = 0.0
        feb_2026["urgent_change"] = 0.0
        feb_2026["cycle_change"] = 0.0
    feb_2026["jan_efficiency"] = jan_2026["efficiency"]
    feb_2026["jan_test_cost"] = jan_2026["test_cost"]
    feb_2026["jan_bugs_per_demand"] = jan_2026["bugs_per_demand"]
    feb_2026["jan_rt_ratio"] = jan_2026["rt_ratio"]

    year_2026 = {
        "demands": total_demands,
        "total_effort": round(five_sum, 1),
        "test_effort": total_test,
        "bugs": int(g_bugs),
        "biz_count": len(biz_list),
        "avg_cycle": round(avg_cycle_all, 2),
        "test_pct": round(total_test / five_sum * 100, 1) if five_sum else 0,
    }

    summary_2026 = []
    for m in months:
        if m == "N/A":
            continue
        demands = month_counts.get(m, 0)
        ssum = sum(five_phase_total(r) for r in rows if pk(r) == m)
        te = sum(effort_fields(r)[6] for r in rows if pk(r) == m)
        bugs = sum(_pf(r.get("总 bug 数")) for r in rows if pk(r) == m)
        d = sum(_pf(r.get("技术方案设计与评审 估分")) for r in rows if pk(r) == m)
        rd = sum(_pf(r.get("研发总估分")) for r in rows if pk(r) == m)
        qc = sum(_pf(r.get("QC测试用例设计与评审 估分")) for r in rows if pk(r) == m)
        tn = sum(_pf(r.get("测试 估分")) for r in rows if pk(r) == m)
        pr = sum(_pf(r.get("预发测试估分")) for r in rows if pk(r) == m)
        summary_2026.append(
            {
                "month": m,
                "demands": demands,
                "total_effort": round(ssum, 1),
                "design": round(d, 1),
                "rd": round(rd, 1),
                "qc_design": round(qc, 1),
                "test_node": round(tn, 1),
                "pre_test": round(pr, 1),
                "test_total": round(te, 1),
                "bugs": int(bugs),
                "test_pct": round(te / ssum * 100, 1) if ssum else 0,
            }
        )

    biz_detail_2026 = [
        {
            "name": b["name"],
            "demands": b["demand_count"],
            "total_effort": b["total_score"],
            "test_effort": b["test_total"],
            "test_pct": b["test_pct"],
            "rt_ratio": b["rt_ratio"],
            "bugs": int(b["bugs"]),
            "bugs_per_demand": b["avg_bugs_per_demand"],
            "urgent_count": b["urgent_count"],
            "urgent_pct": b["urgent_pct"],
            "station_count": 0,
            "station_pct": 0.0,
            "cycle": b["avg_delivery_cycle_days"],
            "cycle_wd": b["avg_delivery_cycle_wd"],
        }
        for b in biz_list
    ]

    monthly_biz_detail: Dict[str, List[Dict[str, Any]]] = {}
    for m in months[-2:]:
        lst = []
        for b in biz_list:
            nm = b["name"]
            sub = [r for r in rows if _biz_line(r) == nm and pk(r) == m]
            if not sub:
                continue
            te = sum(effort_fields(r)[6] for r in sub)
            ssum = sum(five_phase_total(r) for r in sub)
            lst.append(
                {
                    "name": nm,
                    "demands": len(sub),
                    "test_effort": round(te, 1),
                    "test_pct": round(te / ssum * 100, 1) if ssum else 0,
                }
            )
        monthly_biz_detail[m] = lst

    test_phase_dist = {
        "qc": round(g_qc, 1),
        "qc_pct": _pct(g_qc, g_tt),
        "test_node": round(g_te, 1),
        "test_node_pct": _pct(g_te, g_tt),
        "prefab": round(g_pr, 1),
        "prefab_pct": _pct(g_pr, g_tt),
        "total": round(g_tt, 1),
    }
    test_phase_pie = [
        {"name": "QC用例", "value": round(g_qc, 1), "pct": _pct(g_qc, g_tt)},
        {"name": "测试执行", "value": round(g_te, 1), "pct": _pct(g_te, g_tt)},
        {"name": "预发", "value": round(g_pr, 1), "pct": _pct(g_pr, g_tt)},
    ]

    biz_eff_rank = [
        {
            "name": b["name"],
            "demands": b["demand_count"],
            "test_effort": b["test_total"],
            "total_score": b["total_score"],
            "efficiency": b["test_efficiency"],
        }
        for b in sorted(biz_list, key=lambda x: -x["test_efficiency"])[:20]
    ]

    urgent_summary = {
        "total": sum(1 for r in rows if is_urgent(r)),
        "pct": round(sum(1 for r in rows if is_urgent(r)) / total_demands * 100, 1) if total_demands else 0,
        "test_effort": total_test,
        "test_pct": round(
            sum(effort_fields(r)[6] for r in rows if is_urgent(r)) / (total_test + 1e-6) * 100, 1
        ),
        "total_demands": total_demands,
    }

    urgent_multi_dim = {
        "total_urgent": urgent_summary["total"],
        "by_priority": count_dim("优先级")[:6],
        "by_req_type": count_dim("需求类型"),
        "by_value_type": count_dim("价值类型")[:10],
        "by_complexity": count_dim("业务复杂度分级"),
        "by_smoke": count_dim("冒烟是否通过"),
        "quality_by_biz": [{"name": b["name"], "bugs_per_demand": b["avg_bugs_per_demand"]} for b in biz_list[:15]],
    }

    industry_benchmark = {
        "demand_density": round(total_demands / len(biz_list), 1) if biz_list else 0,
        "quality_index": round(g_bugs / total_demands, 2) if total_demands else 0,
        "cost_efficiency": round(five_sum / (total_test + 1e-6), 2),
        "dev_test_ratio": avg_rt,
        "avg_bugs_per_demand": round(g_bugs / total_demands, 2) if total_demands else 0,
        "resource_utilization": 0.25,
        "delivery_speed": round(total_demands / (avg_cycle_all + 1e-6), 1),
        "stability_index": 0.72,
    }

    duration_score_summary = {
        "avg_duration": round(
            sum(b["avg_delivery_cycle_days"] for b in biz_list) / max(len(biz_list), 1), 2
        ),
        "avg_duration_wd": round(
            sum(b["avg_delivery_cycle_wd"] for b in biz_list) / max(len(biz_list), 1), 2
        ),
        "avg_score": round(g_node / total_demands, 2) if total_demands else 0,
        "avg_score_per_duration": round(g_node / (avg_cycle_all * total_demands + 1e-6), 3),
    }

    exec_summary = {
        "overall_efficiency": round(total_demands / (total_test + 1e-6), 2),
        "feb_efficiency": feb_2026.get("demands", 0) / (feb_2026.get("test_effort", 1) + 1e-6),
        "jan_efficiency": jan_2026.get("demands", 0) / (jan_2026.get("test_effort", 1) + 1e-6),
        "efficiency_change": 0.0,
        "test_cost_per_demand": round(total_test / total_demands, 2) if total_demands else 0,
        "bugs_per_demand": round(g_bugs / total_demands, 2) if total_demands else 0,
        "feb_urgent_pct": round(
            sum(1 for r in rows if is_urgent(r) and pk(r) == m_last)
            / max(1, month_counts.get(m_last, 1))
            * 100,
            1,
        ),
        "jan_urgent_pct": round(
            sum(1 for r in rows if is_urgent(r) and pk(r) == m_prev)
            / max(1, month_counts.get(m_prev, 1))
            * 100,
            1,
        ),
        "best_biz": (
            {"name": _short_biz(biz_by_eff[-1]["name"]), "efficiency": round(biz_by_eff[-1]["total_score"] / (biz_by_eff[-1]["test_total"] + 1e-6), 2), "value": round(biz_by_eff[-1]["total_score"] / (biz_by_eff[-1]["test_total"] + 1e-6), 2)}
            if (biz_by_eff := sorted([b for b in biz_list if b.get("test_total", 0) > 50], key=lambda b: b["total_score"] / (b["test_total"] + 1e-6)))
            else {"name": "", "efficiency": 0, "value": 0}
        ),
        "worst_biz": (
            [{"name": _short_biz(b["name"]), "value": round(b["total_score"] / (b["test_total"] + 1e-6), 2)} for b in biz_by_eff_w[:2]]
            if (biz_by_eff_w := sorted([b for b in biz_list if b.get("test_total", 0) > 30], key=lambda b: b["total_score"] / (b["test_total"] + 1e-6)))
            else [{"name": "", "value": 0}]
        ),
        "high_bug_biz": (
            {"name": _short_biz(biz_by_bug[0]["name"]), "value": round(biz_by_bug[0]["avg_bugs_per_demand"], 1)}
            if (biz_by_bug := sorted([b for b in biz_list if b.get("demand_count", 0) >= 10], key=lambda b: -b["avg_bugs_per_demand"]))
            else {"name": "", "value": 0}
        ),
    }

    test_efficiency = {
        "qc_effort": round(g_qc, 1),
        "test_effort": round(g_te, 1),
        "prefab_effort": round(g_pr, 1),
        "total_test_effort": total_test,
        "total_demands": total_demands,
        "total_bugs": int(g_bugs),
        "avg_test_per_demand": round(total_test / total_demands, 2) if total_demands else 0,
        "avg_bugs_per_demand": round(g_bugs / total_demands, 2) if total_demands else 0,
        "top5_biz": [b["name"] for b in biz_list[:5]],
        "bottom5_biz": [b["name"] for b in biz_list[-5:]],
    }

    biz_month_fenzan_test = {"months": months, "biz_names": [b["name"] for b in biz_list], "data": []}
    biz_month_urgent_test = {"months": months, "biz_names": [b["name"] for b in biz_list], "data": []}

    if use_sp:
        date_range_label = (
            f"{months[0]}～{months[-1]}" if months and months != ["N/A"] else "所属迭代"
        )
    else:
        date_range_label = f"{months[0]} ~ {months[-1]}" if months else ""

    data: Dict[str, Any] = {
        "axisKind": "iteration" if use_sp else "month",
        "months": months,
        "month_with_chain": month_with_chain,
        "phase_workload": phase_workload,
        "rd_test_pie": rd_test_pie,
        "sankey_nodes": sankey_nodes,
        "sankey_links": sankey_links,
        "duration_score_by_biz": duration_score_by_biz,
        "by_biz": by_biz_chart,
        "by_value_type": by_value_type,
        "by_priority": by_priority,
        "by_status": by_status,
        "by_req_type": by_req_type,
        "score_by_biz": score_by_biz,
        "bug_by_biz": bug_by_biz,
        "by_month": by_month,
        "biz_list": biz_list,
        "value_type_list": value_type_list,
        "throughput_by_month": throughput_by_month,
        "industry_benchmark": industry_benchmark,
        "qc_by_biz": qc_by_biz,
        "biz_avg_duration_vs_score": [
            {"name": b["name"], "duration": b["avg_delivery_cycle_days"], "score": b["total_score"]}
            for b in biz_list[:20]
        ],
        "heat_biz_phase": heat_biz_phase,
        "heat_month_phase": heat_month_phase,
        "heat_biz_month": heat_biz_month,
        "biz_month_phase_3d": biz_month_phase_3d,
        "duration_score_summary": duration_score_summary,
        "test_stages_by_biz": test_stages_by_biz,
        "test_phase_pie": test_phase_pie,
        "test_optimizations": [],
        "dim_biz_vt": dim_biz_vt,
        "dim_biz_priority": dim_biz_priority,
        "biz_month_urgent_test": biz_month_urgent_test,
        "urgent_multi_dim": urgent_multi_dim,
        "biz_month_fenzan_test": biz_month_fenzan_test,
        "total_fenzan_count": 0,
        "month_avg_cycle": month_avg_cycle,
        "month_avg_cycle_wd": month_avg_cycle_wd,
        "biz_month_cycle_map": dict(biz_month_cycle_map),
        "month_test_totals": month_test_totals,
        "summary_2026": summary_2026,
        "summary_stats": summary_stats,
        "exec_summary": exec_summary,
        "total_demands": total_demands,
        "feb_2026": feb_2026,
        "year_2026": year_2026,
        "jan_2026": jan_2026,
        "monthly_summary": monthly_summary,
        "biz_detail_2026": biz_detail_2026,
        "monthly_biz_detail": monthly_biz_detail,
        "test_phase_dist": test_phase_dist,
        "monthly_eff": monthly_eff,
        "biz_eff_rank": biz_eff_rank,
        "urgent_summary": urgent_summary,
        "monthly_urgent": monthly_urgent,
        "biz_urgent": biz_urgent,
        "station_summary": station_summary,
        "biz_station": biz_station,
        "monthly_station": monthly_station,
        "avg_rt_ratio": avg_rt,
        "total_test_effort": total_test,
        "total_rd_corrected": total_rd_corr,
        "jan_rt_ratio": round(
            jan_2026.get("rd_corrected", 0) / (jan_2026.get("test_effort", 0) + 1e-6), 2
        ),
        "test_efficiency": test_efficiency,
        "total_score": round(g_node, 1),
        "total_bugs": float(g_bugs),
        "total_rd": round(g_rd + g_design, 1),
        "total_test": total_test,
        "summary": summary,
        "value_type_top5": value_type_top5,
        "value_type_summary": value_type_summary,
    }

    return data, delivery_sd, date_range_label, ",".join(months)


def _short_biz(name: str) -> str:
    if name.startswith("RDJ-"):
        return name[4:]
    return name


def _build_delivery_sd(
    rows: List[Dict[str, str]],
    months: List[str],
    month_avg_cycle: List[float],
    period_key: Callable[[Dict[str, str]], Optional[str]],
) -> Dict[str, Any]:
    stages = ["需求阶段", "研发阶段", "测试阶段", "预发测试", "发布上线"]
    # 全局：按工时权重拆分平均交付周期
    acc_eff = [0.0] * 5
    acc_days_weighted = [0.0] * 5
    n_valid = 0
    for r in rows:
        cy = _cycle_days(_parse_dt(r.get("创建时间")), _parse_dt(r.get("完成日期")))
        if cy is None or cy <= 0:
            continue
        d, rd, qc, _, te, pr, _ = effort_fields(r)
        w = d + rd + qc + te + pr
        if w <= 0:
            continue
        n_valid += 1
        acc_eff[0] += d
        acc_eff[1] += rd
        acc_eff[2] += qc + te
        acc_eff[3] += pr
        acc_eff[4] += max(0.0, 0.05 * w)
        acc_days_weighted[0] += cy * (d / w)
        acc_days_weighted[1] += cy * (rd / w)
        acc_days_weighted[2] += cy * ((qc + te) / w)
        acc_days_weighted[3] += cy * (pr / w)
        acc_days_weighted[4] += cy * 0.05
    def avg_stage(i: int) -> float:
        return round(acc_days_weighted[i] / n_valid, 2) if n_valid else 0.0

    summary = {
        "需求阶段": {
            "avg": avg_stage(0),
            "median": avg_stage(0),
            "count": n_valid,
            "total_effort": round(acc_eff[0], 1),
            "avg_effort": round(acc_eff[0] / max(n_valid, 1), 2),
            "activity": 2.0,
        },
        "研发阶段": {
            "avg": avg_stage(1),
            "median": avg_stage(1),
            "count": n_valid,
            "total_effort": round(acc_eff[1], 1),
            "avg_effort": round(acc_eff[1] / max(n_valid, 1), 2),
            "activity": 40.0,
        },
        "测试阶段": {
            "avg": avg_stage(2),
            "median": avg_stage(2),
            "count": n_valid,
            "total_effort": round(acc_eff[2], 1),
            "avg_effort": round(acc_eff[2] / max(n_valid, 1), 2),
            "activity": 38.0,
        },
        "预发测试": {
            "avg": avg_stage(3),
            "median": avg_stage(3),
            "count": n_valid,
            "total_effort": round(acc_eff[3], 1),
            "avg_effort": round(acc_eff[3] / max(n_valid, 1), 2),
            "activity": 35.0,
        },
        "发布上线": {
            "avg": avg_stage(4),
            "median": avg_stage(4),
            "count": n_valid,
            "total_effort": 0.0,
            "avg_effort": 0.0,
            "activity": 0.0,
        },
        "交付周期": {
            "avg": round(sum(month_avg_cycle) / max(len(month_avg_cycle), 1), 2),
            "median": round(sorted(month_avg_cycle)[len(month_avg_cycle) // 2], 2) if month_avg_cycle else 0,
        },
    }
    monthly: Dict[str, Any] = {}
    for mi, m in enumerate(months):
        cavg = month_avg_cycle[mi] if mi < len(month_avg_cycle) else 0.0
        acc = [0.0] * 5
        wsum = 0.0
        for r in rows:
            if period_key(r) != m:
                continue
            d, rd, qc, _, te, pr, _ = effort_fields(r)
            w = d + rd + qc + te + pr
            if w <= 0:
                continue
            acc[0] += cavg * (d / w)
            acc[1] += cavg * (rd / w)
            acc[2] += cavg * ((qc + te) / w)
            acc[3] += cavg * (pr / w)
            acc[4] += cavg * 0.05
            wsum += 1
        if wsum == 0:
            monthly[m] = {
                "需求阶段": 0,
                "研发阶段": 0,
                "测试阶段": 0,
                "预发测试": 0,
                "发布上线": 0,
                "交付周期": cavg,
            }
        else:
            monthly[m] = {
                "需求阶段": round(acc[0] / wsum, 1),
                "研发阶段": round(acc[1] / wsum, 1),
                "测试阶段": round(acc[2] / wsum, 1),
                "预发测试": round(acc[3] / wsum, 1),
                "发布上线": round(acc[4] / wsum, 1),
                "交付周期": round(cavg, 1),
            }
    # 与模板「统一交付流程图」tooltip 一致：各月五阶段估分人天（设计/研发/QC+测试+预发/发布占位0）
    monthly_effort: Dict[str, Dict[str, float]] = {
        m: {"需求阶段": 0.0, "研发阶段": 0.0, "测试阶段": 0.0, "预发测试": 0.0, "发布上线": 0.0} for m in months
    }
    for r in rows:
        mk = period_key(r)
        if not mk or mk not in monthly_effort:
            continue
        d, rd, qc, _, te, pr, _ = effort_fields(r)
        monthly_effort[mk]["需求阶段"] += d
        monthly_effort[mk]["研发阶段"] += rd
        monthly_effort[mk]["测试阶段"] += qc + te
        monthly_effort[mk]["预发测试"] += pr
    for m in months:
        for k in monthly_effort[m]:
            monthly_effort[m][k] = round(monthly_effort[m][k], 1)
    return {"stages": stages, "summary": summary, "monthly": monthly, "monthly_effort": monthly_effort}


def replace_json_object_after(html: str, marker: str, new_obj: Dict[str, Any]) -> str:
    """将 marker 后的第一个 JSON 对象替换为 new_obj 的序列化（保留后续分号等）。"""
    idx = html.find(marker)
    if idx < 0:
        raise ValueError(f"marker not found: {marker}")
    start = idx + len(marker)
    js = html[start:]
    depth = 0
    in_str = False
    esc = False
    q = None
    end_rel = None
    for i, c in enumerate(js):
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == q:
                in_str = False
                q = None
            continue
        else:
            if c in "\"'":
                in_str = True
                q = c
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end_rel = i + 1
                    break
    if end_rel is None:
        raise ValueError("JSON object not closed")
    tail = html[start + end_rel :]
    # 若紧跟分号则保留在 tail
    new_json = json.dumps(new_obj, ensure_ascii=False, separators=(",", ":"))
    return html[:start] + new_json + tail


def compute_test_report_script_vars(
    rows: List[Dict[str, str]],
    months: List[str],
    period_key: Optional[Callable[[Dict[str, str]], Optional[str]]] = None,
) -> Tuple[List[str], List[float], List[float], Dict[str, Any], Dict[str, Any]]:
    """供「测试效能汇总报告」替换 var months / monthTotals / monthTestWork / monthly / effortData。"""
    if period_key is None:
        period_key = _month_period_key
    month_totals = [0.0] * len(months)
    month_test = [0.0] * len(months)
    mi = {m: i for i, m in enumerate(months)}
    monthly: Dict[str, Dict[str, float]] = {
        m: {"需求阶段": 0.0, "研发阶段": 0.0, "测试阶段": 0.0, "预发测试": 0.0, "发布上线": 0.0, "_n": 0.0}
        for m in months
    }
    effort_acc: Dict[str, Dict[str, float]] = {
        m: {"设计评审": 0.0, "研发": 0.0, "QC用例": 0.0, "测试": 0.0, "预发": 0.0} for m in months
    }
    for r in rows:
        mk = period_key(r)
        if not mk or mk not in mi:
            continue
        i = mi[mk]
        d, rd, qc, _, te, pr, tt = effort_fields(r)
        five = d + rd + qc + te + pr
        month_totals[i] += five
        month_test[i] += tt
        effort_acc[mk]["设计评审"] += d
        effort_acc[mk]["研发"] += rd
        effort_acc[mk]["QC用例"] += qc
        effort_acc[mk]["测试"] += te
        effort_acc[mk]["预发"] += pr
        cy = _cycle_days(_parse_dt(r.get("创建时间")), _parse_dt(r.get("完成日期")))
        if cy is None or cy <= 0 or five <= 0:
            continue
        monthly[mk]["需求阶段"] += cy * (d / five)
        monthly[mk]["研发阶段"] += cy * (rd / five)
        monthly[mk]["测试阶段"] += cy * ((qc + te) / five)
        monthly[mk]["预发测试"] += cy * (pr / five)
        monthly[mk]["发布上线"] += cy * 0.05
        monthly[mk]["_n"] += 1
    for m in months:
        n = monthly[m]["_n"] or 1
        for k in ["需求阶段", "研发阶段", "测试阶段", "预发测试", "发布上线"]:
            monthly[m][k] = round(monthly[m][k] / n, 1)
        del monthly[m]["_n"]
    effort_pct: Dict[str, Any] = {}
    for m in months:
        tot = month_totals[mi[m]] or 1.0
        effort_pct[m] = {
            "设计评审": round(effort_acc[m]["设计评审"] / tot * 100, 1),
            "研发": round(effort_acc[m]["研发"] / tot * 100, 1),
            "QC用例": round(effort_acc[m]["QC用例"] / tot * 100, 1),
            "测试": round(effort_acc[m]["测试"] / tot * 100, 1),
            "预发": round(effort_acc[m]["预发"] / tot * 100, 1),
        }
    return (
        months,
        [round(x, 1) for x in month_totals],
        [round(x, 1) for x in month_test],
        monthly,
        effort_pct,
    )


def extract_first_json_object(html: str, marker: str) -> Dict[str, Any]:
    idx = html.find(marker)
    if idx < 0:
        raise ValueError(marker)
    start = idx + len(marker)
    js = html[start:]
    depth = 0
    in_str = False
    esc = False
    q = None
    for i, c in enumerate(js):
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == q:
                in_str = False
                q = None
            continue
        else:
            if c in "\"'":
                in_str = True
                q = c
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(js[: i + 1])
    raise ValueError("bad json")
