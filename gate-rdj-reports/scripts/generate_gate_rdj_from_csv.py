#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""根据维度 CSV 生成 Gate-RDJ HTML（与 Gate-RDJ-12 模板样式/口径一致）。

默认：从「需求导出-Gate-RDJ_迭代维度.csv」「需求导出-Gate-RDJ_时间维度.csv」
各生成 4 份报告（需求分析完整版/精简版、测试效能汇总、v4 业务线），共 8 个 HTML。

可选：``python3 scripts/generate_gate_rdj_from_csv.py --legacy-csv`` 使用根目录
「需求导出-Gate-RDJ.csv」生成旧的 ``Gate-RDJ-csv-*`` 四件套（一般不推荐）。
"""
import html as html_module
import json
import math
import os
import re
import sys
import time
from html import unescape
from html.parser import HTMLParser
from urllib.error import URLError
from urllib.request import Request, urlopen
from collections import Counter, defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from gate_rdj_metrics import (  # noqa: E402
    _biz_line,
    build_data_payload,
    compute_test_report_script_vars,
    corrected_rd,
    effort_fields,
    filter_rows_for_time_axis,
    five_phase_total,
    iqr_filter,
    load_rows,
    replace_json_object_after,
    _cycle_days,
    _month_key,
    _month_period_key,
    _parse_dt,
    _pf,
    _primary_qc,
    _short_biz,
    _sp_label,
)
from gate_rdj_v4_patch import patch_gate_rdj_v4_html  # noqa: E402
from _paths import DATA_DIR, REPO_ROOT, TEMPLATES_DIR  # noqa: E402

ROOT = str(REPO_ROOT)
CSV = os.path.join(ROOT, "需求导出-Gate-RDJ.csv")
# 与 https://report.dev.halftrust.xyz/results/department_stats.html 同源（id=departmentTable）
DEPARTMENT_STATS_URL = "https://report.dev.halftrust.xyz/results/department_stats.html"
DEPARTMENT_STATS_LOCAL_CANDIDATES = (
    os.environ.get("DEPARTMENT_STATS_HTML", "").strip(),
    os.path.join(ROOT, "department_stats.html"),
    os.path.join(ROOT, "data", "department_stats.html"),
    os.path.join(SCRIPT_DIR, "department_stats.html"),
)
TEMPLATES = {
    "req_full": "Gate-RDJ-12-skill-需求分析报告.html",
    "req_short": "Gate-RDJ-12-skill-需求分析报告_精简版.html",
    "biz": "Gate-RDJ-12-v4-业务线分析报告.html",
    "test": "Gate-RDJ-12-skill-测试效能汇总报告.html",
}
OUT = {
    "req_full": "Gate-RDJ-csv-skill-需求分析报告.html",
    "req_short": "Gate-RDJ-csv-skill-需求分析报告_精简版.html",
    "biz": "Gate-RDJ-csv-v4-业务线分析报告.html",
    "test": "Gate-RDJ-csv-skill-测试效能汇总报告.html",
}

MODULE_OUTPUT_SUFFIX = {
    "req_full": "skill-需求分析报告.html",
    "req_short": "skill-需求分析报告_精简版.html",
    "test": "skill-测试效能汇总报告.html",
    "biz": "v4-业务线分析报告.html",
}


class _DepartmentTableParser(HTMLParser):
    """解析 department_stats.html 中 departmentTable。"""

    def __init__(self) -> None:
        super().__init__()
        self._in_target_table = False
        self._in_thead = False
        self._in_tbody = False
        self._in_tr = False
        self._in_th = False
        self._in_td = False
        self._cur_text = ""
        self._cur_td_attrs: Dict[str, str] = {}
        self.headers: List[str] = []
        self.rows: List[List[Tuple[str, Dict[str, str]]]] = []
        self._cur_row: List[Tuple[str, Dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        amap = {k: (v or "") for k, v in attrs}
        if tag == "table" and amap.get("id") == "departmentTable":
            self._in_target_table = True
        if not self._in_target_table:
            return
        if tag == "thead":
            self._in_thead = True
        elif tag == "tbody":
            self._in_tbody = True
        elif tag == "tr" and (self._in_thead or self._in_tbody):
            self._in_tr = True
            self._cur_row = []
        elif tag == "th" and self._in_thead and self._in_tr:
            self._in_th = True
            self._cur_text = ""
        elif tag == "td" and self._in_tbody and self._in_tr:
            self._in_td = True
            self._cur_text = ""
            self._cur_td_attrs = amap

    def handle_data(self, data: str) -> None:
        if self._in_th or self._in_td:
            self._cur_text += data

    def handle_endtag(self, tag: str) -> None:
        if not self._in_target_table:
            return
        if tag == "th" and self._in_th:
            txt = self._cur_text.strip().replace("▴▾", "").replace("▴", "").replace("▾", "").strip()
            self.headers.append(txt)
            self._in_th = False
        elif tag == "td" and self._in_td:
            self._cur_row.append((self._cur_text.strip(), self._cur_td_attrs))
            self._in_td = False
        elif tag == "tr" and self._in_tr:
            if self._in_tbody and self._cur_row:
                self.rows.append(self._cur_row)
            self._in_tr = False
        elif tag == "thead":
            self._in_thead = False
        elif tag == "tbody":
            self._in_tbody = False
        elif tag == "table" and self._in_target_table:
            self._in_target_table = False


def _normalize_qc_token(name: str) -> str:
    s = (name or "").strip()
    if not s:
        return ""
    s = s.replace("（", "(")
    s = s.split("(", 1)[0].strip()
    s = s.split("|", 1)[0].strip()
    s = s.split("-", 1)[0].strip().lower()
    s = re.sub(r"[^a-z0-9_]+", "", s)
    return s


def _qc_group_mapping_from_html(html: str) -> Dict[str, str]:
    """解析 department_stats.html 正文，返回 normalize(QC名) -> 大类-新分组。"""
    parser = _DepartmentTableParser()
    parser.feed(html)
    if not parser.headers or not parser.rows:
        return {}
    try:
        idx_big = parser.headers.index("大类名称")
        idx_group = parser.headers.index("新分组")
        idx_qc = parser.headers.index("QC")
    except ValueError:
        return {}
    mapping: Dict[str, str] = {}
    for row in parser.rows:
        if len(row) <= max(idx_big, idx_group, idx_qc):
            continue
        big_name = row[idx_big][0].strip()
        group_name = re.sub(r"\s+", "", row[idx_group][0].strip())
        if not group_name:
            continue
        group_label = f"{big_name}-{group_name}" if big_name else group_name
        qc_names_raw = row[idx_qc][1].get("data-names", "[]")
        qc_names_json = unescape(qc_names_raw)
        try:
            qc_names = json.loads(qc_names_json)
        except json.JSONDecodeError:
            qc_names = []
        for name in qc_names:
            key = _normalize_qc_token(str(name))
            if key and key not in mapping:
                mapping[key] = group_label
    return mapping


def _load_qc_group_mapping(url: str = DEPARTMENT_STATS_URL) -> Dict[str, str]:
    """优先拉取官方页；失败再读本地快照（环境变量 DEPARTMENT_STATS_HTML 或仓库内 department_stats.html）。"""
    req = Request(
        url,
        headers={"User-Agent": "Gate-RDJ-scripts/1.0 (+https://report.dev.halftrust.xyz/)"},
    )
    try:
        with urlopen(req, timeout=45) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        m = _qc_group_mapping_from_html(html)
        if m:
            return m
        print("Warn: department_stats 页面已拉取但未解析出映射（表结构是否变更？）", file=sys.stderr)
    except (OSError, URLError) as exc:
        print(f"Warn: failed to fetch department stats from {url} ({exc})", file=sys.stderr)

    for raw_path in DEPARTMENT_STATS_LOCAL_CANDIDATES:
        if not raw_path:
            continue
        path = os.path.expanduser(raw_path)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                m = _qc_group_mapping_from_html(f.read())
            if m:
                print(f"Note: QC 部门映射来自本地文件 {path}", file=sys.stderr)
                return m
        except OSError as exc:
            print(f"Warn: could not read local department stats {path} ({exc})", file=sys.stderr)

    return {}


def _apply_qc_grouping(rows: List[Dict[str, str]], qc_group_map: Dict[str, str]) -> List[Dict[str, str]]:
    if not qc_group_map:
        print(
            "Warn: department_stats 映射为空，保留 CSV 原始「业务线」（未按新分组重标）。"
            "请拉取快照: curl -fsSL 'https://report.dev.halftrust.xyz/results/department_stats.html' -o department_stats.html"
            " 或设置环境变量 DEPARTMENT_STATS_HTML=/path/to/department_stats.html",
            file=sys.stderr,
        )
        return [dict(r) for r in rows]
    out: List[Dict[str, str]] = []
    allow_tokens = set(qc_group_map.keys())
    for r in rows:
        nr = dict(r)
        qc_field = (r.get("QC") or "").strip()
        candidates = [x.strip() for x in qc_field.split("|") if x.strip()] if qc_field else []
        matched_tokens: List[str] = []
        for cand in candidates:
            tok = _normalize_qc_token(cand)
            if tok and tok in allow_tokens and tok not in matched_tokens:
                matched_tokens.append(tok)
        mapped = None
        for tok in matched_tokens:
            if tok in qc_group_map:
                mapped = qc_group_map[tok]
                break
        if mapped is None:
            key = _normalize_qc_token(_primary_qc(qc_field))
            if key in allow_tokens:
                matched_tokens = [key]
                mapped = qc_group_map.get(key)
        # 仅保留白名单 QC，统一标准化命名，保证 QC 总量不会超过 department_stats 的 QC 列
        nr["QC"] = "|".join(f"{tok}-QC" for tok in matched_tokens)
        nr["业务线"] = mapped or "其他"
        out.append(nr)
    return out


def inject_echarts_fallback(html: str) -> str:
    """优先加载本地 vendor/echarts，再回退 CDN（jsdelivr → npmmirror）。解决内网/拦截 CDN 时整页图表空白。"""
    needles = (
        '<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>',
        '<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js" onerror="this.onerror=null;this.src=\'https://registry.npmmirror.com/echarts/5.4.3/files/dist/echarts.min.js\'"></script>',
    )
    # 勿在行首再加缩进：needle 会匹配行内子串，原行的 4 空格会保留，否则会出现 8 空格。
    vendor_block = (
        '<script src="vendor/echarts-5.4.3.min.js"></script>\n'
        '    <script>'
        "window.echarts||document.write('\\x3cscript src=\"https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js\"\\x3e\\x3c/script\\x3e');"
        "window.echarts||document.write('\\x3cscript src=\"https://registry.npmmirror.com/echarts/5.4.3/files/dist/echarts.min.js\"\\x3e\\x3c/script\\x3e');"
        "</script>"
    )
    for needle in needles:
        if needle in html:
            return html.replace(needle, vendor_block, 1)
    return html


def _percentile(vals: List[float], p: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    k = (len(s) - 1) * p / 100.0
    lo = int(math.floor(k))
    hi = int(math.ceil(k))
    if lo == hi:
        return round(s[lo], 2)
    return round(s[lo] * (hi - k) + s[hi] * (k - lo), 2)


def _appendix_axis_key(r: Dict[str, str], axis_iteration: bool) -> Optional[str]:
    return _sp_label(r) if axis_iteration else _month_period_key(r)


def _appendix_table1_rows(rows: List[Dict[str, str]], months: List[str], axis_iteration: bool = False) -> str:
    lines = []
    for mi, m in enumerate(months):
        sub = [r for r in rows if _appendix_axis_key(r, axis_iteration) == m]
        n = len(sub)
        cys = [
            float(x)
            for x in (
                _cycle_days(_parse_dt(r.get("创建时间")), _parse_dt(r.get("完成日期")))
                for r in sub
            )
            if x is not None
        ]
        mean_c = round(sum(cys) / len(cys), 2) if cys else 0.0
        p50 = int(round(_percentile(cys, 50))) if cys else 0
        p75 = int(round(_percentile(cys, 75))) if cys else 0
        p90 = int(round(_percentile(cys, 90))) if cys else 0
        gt30 = round(sum(1 for x in cys if x > 30) / len(cys) * 100, 1) if cys else 0.0
        nodes = [_pf(r.get("全部节点估分")) for r in sub]
        avg_node = round(sum(nodes) / max(n, 1), 1) if n else 0.0
        big = round(sum(1 for x in nodes if x > 20) / max(n, 1) * 100, 1) if n else 0.0
        row = (
            f"<tr><td>{m}</td><td>{n}</td><td>{mean_c}天</td><td>{p50}天</td>"
            f"<td>{p75}天</td><td>{p90}天</td><td>{gt30}%</td><td>{avg_node}</td><td>{big}%</td></tr>"
        )
        if mi == len(months) - 1 and n:
            row = row.replace("<tr>", '<tr style="background:#fef2f2;">', 1).replace(
                f"<td>{m}</td>", f'<td style="font-weight:700;">{m}</td>', 1
            )
        lines.append(row)
    return "\n".join(lines)


def _appendix_table2_rows(rows: List[Dict[str, str]], months: List[str], axis_iteration: bool = False) -> str:
    lines = []
    for mi, m in enumerate(months):
        sub = [r for r in rows if _appendix_axis_key(r, axis_iteration) == m]
        n = len(sub)
        if not n:
            lines.append(f"<tr><td>{m}</td><td>0</td><td>0%</td><td>0</td><td>0%</td></tr>")
            continue
        same = 0
        cross = 0
        cross_ge2 = 0
        for r in sub:
            cd = _parse_dt(r.get("创建时间"))
            fd = _parse_dt(r.get("完成日期"))
            if not cd or not fd:
                continue
            cm = _month_key(cd)
            fm = _month_key(fd)
            if cm == fm:
                same += 1
            else:
                cross += 1
                diff = (fd.year - cd.year) * 12 + (fd.month - cd.month)
                if diff >= 2:
                    cross_ge2 += 1
        lines.append(
            f"<tr><td>{m}</td><td>{same}</td><td>{round(same/n*100,1)}%</td>"
            f"<td>{cross}</td><td>{round(cross_ge2/max(n,1)*100,1)}%</td></tr>"
        )
        if mi == len(months) - 1:
            lines[-1] = lines[-1].replace("<tr>", '<tr style="background:#fef2f2;">', 1).replace(
                f"<td>{m}</td>", f'<td style="font-weight:700;">{m}</td>', 1
            )
    return "\n".join(lines)


def _appendix_table3_rows(rows: List[Dict[str, str]], months: List[str], axis_iteration: bool = False) -> str:
    lines = []
    for mi, m in enumerate(months):
        sub = [r for r in rows if _appendix_axis_key(r, axis_iteration) == m]
        cys = [
            float(x)
            for x in (
                _cycle_days(_parse_dt(r.get("创建时间")), _parse_dt(r.get("完成日期")))
                for r in sub
            )
            if x is not None
        ]
        if not cys:
            lines.append(
                f"<tr><td>{m}</td><td>0天</td><td>0天</td><td>0天</td><td>0天</td><td>0天</td><td>0%</td><td>0%</td></tr>"
            )
            continue
        p10 = int(round(_percentile(cys, 10)))
        p25 = int(round(_percentile(cys, 25)))
        p50 = int(round(_percentile(cys, 50)))
        p75 = int(round(_percentile(cys, 75)))
        p90 = int(round(_percentile(cys, 90)))
        gt30 = round(sum(1 for x in cys if x > 30) / len(cys) * 100, 1)
        gt45 = round(sum(1 for x in cys if x > 45) / len(cys) * 100, 1)
        row = (
            f"<tr><td>{m}</td><td>{p10}天</td><td>{p25}天</td><td>{p50}天</td>"
            f"<td>{p75}天</td><td>{p90}天</td><td>{gt30}%</td><td>{gt45}%</td></tr>"
        )
        if mi == len(months) - 1:
            row = row.replace("<tr>", '<tr style="background:#fef2f2;">', 1).replace(
                f"<td>{m}</td>", f'<td style="font-weight:700;">{m}</td>', 1
            )
        lines.append(row)
    return "\n".join(lines)


def _replace_tbody_after_anchor(html: str, anchor: str, new_inner: str) -> str:
    pos = html.find(anchor)
    if pos < 0:
        return html
    t0 = html.find("<tbody>", pos)
    t1 = html.find("</tbody>", t0)
    if t0 < 0 or t1 < t0:
        return html
    return html[: t0 + 7] + "\n" + new_inner + "\n" + html[t1:]


def patch_requirement_appendix(
    html: str,
    rows: List[Dict[str, str]],
    months: List[str],
    label: str,
    axis_iteration: bool = False,
) -> str:
    if months == ["N/A"]:
        return html
    stat_note = "按所属迭代（年+SPRINT）统计" if axis_iteration else "按完成日期所在月统计"
    html = html.replace(
        "<b style=\"color:#0c4a6e;\">数据范围：</b>2025-10 ~ 2026-02（Gate-RDJ，按完成日期所在月统计）",
        f'<b style="color:#0c4a6e;">数据范围：</b>{label}（Gate-RDJ，{stat_note}）',
    )
    html = _replace_tbody_after_anchor(
        html, '一、数据全景</div>', _appendix_table1_rows(rows, months, axis_iteration)
    )
    html = _replace_tbody_after_anchor(
        html, "完成需求的创建时间分布", _appendix_table2_rows(rows, months, axis_iteration)
    )
    html = _replace_tbody_after_anchor(
        html, "交付周期分位数", _appendix_table3_rows(rows, months, axis_iteration)
    )
    if len(months) >= 2 and months != ["N/A"]:
        mp, ml = months[-2], months[-1]
        html = html.replace(
            "2026-01 约 5.0 Bug/需求 vs 2026-02 约 3.7，返工与回归多",
            f"{mp} 与 {ml} 的对比请以正文图表及本节上方数据表为准（此处为原报告示例句，已随数据区间更新标签）。",
        )
    return html


def _shift_month_label(ym: str, delta: int) -> str:
    """YYYY-MM 加若干自然月；非法格式原样返回。"""
    parts = ym.split("-")
    if len(parts) != 2:
        return ym
    try:
        y, mo = int(parts[0]), int(parts[1])
    except ValueError:
        return ym
    if y <= 0 or not (1 <= mo <= 12):
        return ym
    mo += delta
    while mo > 12:
        mo -= 12
        y += 1
    while mo < 1:
        mo += 12
        y -= 1
    return f"{y:04d}-{mo:02d}"


def patch_requirement_ai_forecast_title(
    html: str, months: List[str], axis_iteration: bool = False
) -> str:
    """替换 AI 测算区写死的月份区间（时间轴）；迭代轴用无自然月外推的说明。"""
    if not months or months == ["N/A"]:
        return html
    m_last = months[-1]
    if axis_iteration:
        return html.replace(
            "AI 提效落地后三个月测算（2026-02 ~ 2026-04）",
            f"AI 提效落地后三期测算（示意，基线为截至 {m_last} 的各迭代工时）",
        )
    if len(m_last) == 7 and m_last[4] == "-":
        end3 = _shift_month_label(m_last, 2)
        return html.replace(
            "AI 提效落地后三个月测算（2026-02 ~ 2026-04）",
            f"AI 提效落地后三个月测算（{m_last} ~ {end3}）",
        )
    return html


def patch_requirement_last_two_month_strings(
    html: str, m_prev: str, m_last: str, axis_iteration: bool = False
) -> str:
    """将模板中写死的环比对比改为当前数据的末两期。"""
    html = re.sub(r"\d{4}-\d{2}\s+vs\s+\d{4}-\d{2}", f"{m_last} vs {m_prev}", html, count=1)
    rep_title = f"Executive Summary · {m_last} 迭代报告" if axis_iteration else f"Executive Summary · {m_last} 月度报告"
    html = re.sub(r"Executive Summary · .*?(?:月度|迭代)报告", rep_title, html, count=1)
    html = re.sub(r"return m\.month==='[^']+'", f"return m.month==='{m_last}'", html, count=1)
    html = re.sub(r"return m\.month==='[^']+'", f"return m.month==='{m_prev}'", html, count=1)
    html = re.sub(r"m\.month==='[^']+'", f"m.month==='{m_last}'", html, count=1)
    html = re.sub(r"m\.month==='[^']+'", f"m.month==='{m_prev}'", html, count=1)
    html = re.sub(r"monthFzMap\['[^']+'\]", f"monthFzMap['{m_last}']", html, count=1)
    html = re.sub(r"monthFzMap\['[^']+'\]", f"monthFzMap['{m_prev}']", html, count=1)
    html = re.sub(r"monthFzMap2\['[^']+'\]", f"monthFzMap2['{m_last}']", html, count=1)
    html = re.sub(r"monthFzMap2\['[^']+'\]", f"monthFzMap2['{m_prev}']", html, count=1)
    html = re.sub(r"m\.name === '[^']+'", f"m.name === '{m_last}'", html, count=1)
    html = re.sub(r"m\.name === '[^']+'", f"m.name === '{m_prev}'", html, count=1)
    rep = json.dumps([m_prev, m_last], ensure_ascii=False)
    html = re.sub(r"\['[^']+',\s*'[^']+'\]", rep, html, count=1)
    html = re.sub(
        r"'<td style=\"padding:6px 8px;font-weight:600;color:#0c4a6e;\">[^<]+</td>' \+",
        f"'<td style=\"padding:6px 8px;font-weight:600;color:#0c4a6e;\">{m_prev}</td>' +",
        html,
        count=1,
    )
    html = re.sub(
        r"'<td style=\"padding:6px 8px;font-weight:600;color:#0c4a6e;\">[^<]+</td>' \+",
        f"'<td style=\"padding:6px 8px;font-weight:600;color:#0c4a6e;\">{m_last}</td>' +",
        html,
        count=1,
    )
    html = re.sub(r"//\s*动态渲染\s*[^ ]+\s*月度效能卡片", f"// 动态渲染 {m_last} 效能卡片", html, count=1)
    html = re.sub(r"\d{4}-\d{2}\s+Top15 长周期需求", f"{m_last} Top15 长周期需求", html, count=1)
    return html


def patch_requirement_part_month_title(html: str, months: List[str], axis_iteration: bool = False) -> str:
    if not months or months == ["N/A"]:
        return html
    m_last = months[-1]
    if axis_iteration:
        html = html.replace("2026-02 月度效能专题", f"{m_last} 迭代效能专题")
        key = f"{m_last} 迭代效能专题"
    else:
        html = html.replace("2026-02 月度效能专题", f"{m_last} 月度效能专题")
        key = f"{m_last} 月度效能专题"
    idx = html.find(key)
    if idx < 0:
        return html
    p0 = html.find('<p class="part-desc"', idx)
    p1 = html.find("</p>", p0)
    if p0 < 0 or p1 < p0:
        return html
    if axis_iteration:
        newp = (
            f'<p class="part-desc" style="margin-bottom:12px;font-size:11px;">以下数据按需求 <b>所属迭代</b> 归入 {m_last} 的汇总；'
            "环比对象为上一迭代周期。请关注<b style=\"color:#dc2626;\">效能指标</b>（测试效率、单需求成本等）的变化。</p>"
        )
    else:
        y, mo = m_last.split("-")
        newp = (
            f'<p class="part-desc" style="margin-bottom:12px;font-size:11px;">以下数据为 {y} 年 {int(mo)} 月'
            "完成需求的汇总；环比对象为上一完成月。请关注<b style=\"color:#dc2626;\">效能指标</b>（测试效率、单需求成本等）的变化。</p>"
        )
    return html[:p0] + newp + html[p1 + 4 :]


def _fmt_vs_team_cell(d_team: float) -> str:
    """与原版一致：|d|≥2 用 ↑/↓ 着色；|d|<2 用 ~Xpp 或 →0pp。"""
    r = round(d_team, 1)
    if abs(r) < 0.05:
        return "<td>→0pp</td>"
    if abs(r) < 2:
        return f"<td>~{r}pp</td>"
    if r > 0:
        return f'<td class="highlight-red">↑+{r}pp</td>'
    return f'<td class="trend-down">↓{r}pp</td>'


def _fmt_vs_prev_cell(d0: float) -> str:
    r = round(d0, 1)
    if abs(r) < 0.05:
        return "<td>→0pp</td>"
    if abs(r) < 2:
        return f"<td>~{r}pp</td>"
    if r > 0:
        return f'<td class="highlight-red">↑+{r}pp</td>'
    return f'<td class="trend-down">↓{r}pp</td>'


def patch_skill_report_iteration_js(html: str) -> str:
    """横轴为迭代（SPn 或 YYYY-SPn）时，避免按自然月外推预测月导致脚本异常。"""
    old = (
        "var foreMonths = (function() { var last = histMonths[histMonths.length-1]; var pts = last.split('-'), "
        "y = parseInt(pts[0]), m = parseInt(pts[1]); var r = []; for (var i = 0; i < 3; i++) { m++; if (m > 12) { m = 1; y++; } "
        "r.push(y + '-' + (m < 10 ? '0' + m : m)); } return r; })();"
    )
    new = (
        "var foreMonths = (function() { var last = histMonths[histMonths.length-1]; "
        "if (!last || /^SP\\\\d+$/i.test(String(last)) || /^\\\\d{4}-SP\\\\d+$/i.test(String(last))) return []; "
        "var pts = String(last).split('-'); "
        "if (pts.length < 2) return []; var y = parseInt(pts[0],10), m = parseInt(pts[1],10); "
        "if (!y || !m) return []; var r = []; for (var i = 0; i < 3; i++) { m++; if (m > 12) { m = 1; y++; } "
        "r.push(y + '-' + (m < 10 ? '0' + m : m)); } return r; })();"
    )
    if old in html:
        html = html.replace(old, new, 1)
    html = html.replace(
        "best.month.split('-')[1] + ' 月显著高于均值'",
        "(best.month.indexOf('-') > 0 ? best.month.split('-')[1] : best.month) + (best.month.indexOf('-') > 0 ? ' 月' : ' 迭代') + '显著高于均值'",
    )
    html = html.replace("近 5 个月效率均值", "近 5 个迭代效率均值")
    return html


def patch_iteration_dynamic_labels(html: str, m_prev: str, m_last: str) -> str:
    """迭代横轴下，替换正文中仍写死「2月」等月份字样的展示。"""
    html = re.sub(r"\d+月紧急占比变化", f"{m_last} 紧急占比变化", html)
    html = re.sub(r"\d+月紧急占比", f"{m_last} 紧急占比", html)
    html = re.sub(r"\d+月分站占比变化", f"{m_last} 分站占比变化", html)
    html = re.sub(r"\d+月分站占比", f"{m_last} 分站占比", html)
    return html


def strip_exec_summary_section(html: str) -> str:
    """移除顶部「执行摘要」区块及其动态渲染脚本（保留 summary-cards 概览卡片）。"""
    html = re.sub(
        r"\s*<!--\s*={3,}\s*执行摘要\s*={3,}\s*-->\s*"
        r'<div\s+id="execSummaryContainer"[^>]*>.*?</div>\s*',
        "\n",
        html,
        count=1,
        flags=re.DOTALL,
    )
    html = re.sub(
        r"\s*//\s*动态渲染执行摘要\s*\(function\(\)\s*\{.*?\}\)\(\);\s*",
        "\n",
        html,
        count=1,
        flags=re.DOTALL,
    )
    return html


def patch_requirement_html(html: str, months: List[str], label: str) -> str:
    html = re.sub(r"\d{4}-\d{2}\s*~\s*\d{4}-\d{2}", label, html, count=1)
    html = re.sub(r"\d{4}-\d{2}~\d{4}-\d{2}", label.replace(" ", ""), html, count=1)
    if months == ["N/A"]:
        return html
    if len(months) >= 3:
        m1 = json.dumps(months[:3], ensure_ascii=False)
        lbl1 = f"统计区间一（{months[0]}～{months[2]}）"
    else:
        m1 = json.dumps(months, ensure_ascii=False)
        lbl1 = "统计区间一"
    if len(months) > 3:
        m2 = json.dumps(months[3:6] if len(months) >= 6 else months[3:], ensure_ascii=False)
        lbl2 = f"统计区间二（{months[3]}～{months[-1]}）"
    elif len(months) > 1:
        m2 = json.dumps(months[1:], ensure_ascii=False)
        lbl2 = "统计区间二"
    else:
        m2 = json.dumps(months, ensure_ascii=False)
        lbl2 = "统计区间二"
    html = re.sub(
        r"renderQuarterFlowDiagram\('quarterFlowDiagram2025Q4',\s*\[[^\]]*\],\s*'[^']*'\);",
        f"renderQuarterFlowDiagram('quarterFlowDiagram2025Q4', {m1}, {json.dumps(lbl1, ensure_ascii=False)});",
        html,
        count=1,
    )
    html = re.sub(
        r"renderQuarterFlowDiagram\('quarterFlowDiagram2026Q1',\s*\[[^\]]*\],\s*'[^']*'\);",
        f"renderQuarterFlowDiagram('quarterFlowDiagram2026Q1', {m2}, {json.dumps(lbl2, ensure_ascii=False)});",
        html,
        count=1,
    )
    return html


def _replace_bracket_var(html: str, name: str, new_body: str) -> str:
    """var name = [ ... ]; 或 { ... };"""
    m = re.search(rf"var {re.escape(name)}\s*=\s*", html)
    if not m:
        raise ValueError(name)
    start = m.end()
    opener = html[start]
    if opener not in "[{":
        raise ValueError(opener)
    closer = "]" if opener == "[" else "}"
    depth = 0
    in_str = False
    esc = False
    q = None
    for i in range(start, len(html)):
        c = html[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == q:
                in_str = False
                q = None
            continue
        if c in "\"'":
            in_str = True
            q = c
            continue
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                end = i + 1
                while end < len(html) and html[end] in " \t\n\r":
                    end += 1
                if end < len(html) and html[end] == ";":
                    end += 1
                return html[: m.start()] + f"var {name} = {new_body};" + html[end:]
    raise ValueError(name)


def build_phase_table_html(months: List[str], effort_pct: Dict[str, Any], month_totals: List[float]) -> str:
    phase_keys = [("设计评审", "#7c3aed"), ("研发", "#0369a1"), ("QC用例", "#0ea5e9"), ("测试", "#dc2626"), ("预发", "#0284c7")]
    header = "".join(f'<th colspan="2">{html_module.escape(m)}</th>' for m in months)
    subh = "".join("<th>占比</th><th>环比</th>" for _ in months)
    rows = []
    for label, color in phase_keys:
        cells = []
        prev = None
        for mi, m in enumerate(months):
            pct = effort_pct[m][label] if isinstance(effort_pct[m], dict) else 0
            if prev is None:
                cells.append(f"<td>{pct}%</td><td>—</td>")
            else:
                d = round(pct - prev, 1)
                if d > 0:
                    cells.append(f'<td>{pct}%</td><td class="trend-up">↑{d}pp</td>')
                elif d < 0:
                    cells.append(f'<td>{pct}%</td><td class="trend-down">↓{abs(d)}pp</td>')
                else:
                    cells.append(f"<td>{pct}%</td><td>→0pp</td>")
            prev = pct
        cls = "test-row" if label == "测试" else ""
        pre = "▲ " if label == "测试" else ""
        rows.append(
            f'<tr class="{cls}"><td class="phase-name" style="color:{color};">{pre}{html_module.escape(label)}</td>'
            + "".join(cells)
            + "</tr>"
        )
    tot_cells = []
    for mi, m in enumerate(months):
        v = round(month_totals[mi], 1)
        if mi == 0:
            tot_cells.append(f"<td>{v}</td><td>—</td>")
        else:
            pv = month_totals[mi - 1]
            if pv < 5:
                tot_cells.append(f"<td>{v}</td><td>—</td>")
            else:
                ch = round((month_totals[mi] - pv) / pv * 100, 1)
                tr = "trend-up" if ch > 0 else "trend-down" if ch < 0 else "trend-stable"
                ar = "↑" if ch > 0 else "↓" if ch < 0 else ""
                tot_cells.append(f'<td>{v}</td><td class="{tr}">{ar}{ch}%</td>')
    rows.append(f'<tr class="total-row"><td class="phase-name">总工时(人天)</td>{"".join(tot_cells)}</tr>')
    return f"""<table class="phase-table">
<thead>
<tr>
<th rowspan="2">阶段</th>
{header}
</tr>
<tr>
{subh}
</tr>
</thead>
<tbody>
{"".join(rows)}
</tbody>
</table>"""


def build_biz_test_pct_table(
    rows: List[Dict[str, str]],
    months: List[str],
    period_key: Optional[Callable[[Dict[str, str]], Optional[str]]] = None,
) -> str:
    if period_key is None:
        period_key = _month_period_key
    biz_m_tt: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    biz_m_five: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        b = _biz_line(r)
        mk = period_key(r)
        if not mk or mk not in months:
            continue
        d, rd, qc, _, te, pr, tt = effort_fields(r)
        biz_m_tt[b][mk] += tt
        biz_m_five[b][mk] += d + rd + qc + te + pr
    team_avg = []
    for m in months:
        s_tt = sum(biz_m_tt[b][m] for b in biz_m_tt)
        s_w = sum(biz_m_five[b][m] for b in biz_m_five)
        team_avg.append(round(s_tt / (s_w + 1e-6) * 100, 1))
    biz_avg = {}
    for b in biz_m_five:
        s_tt = sum(biz_m_tt[b].values())
        s_w = sum(biz_m_five[b].values())
        biz_avg[b] = round(s_tt / (s_w + 1e-6) * 100, 1) if s_w else 0.0
    sorted_biz = sorted(biz_avg.keys(), key=lambda x: -sum(biz_m_five[x].values()))
    header = "".join(f'<th colspan="3">{html_module.escape(m)}</th>' for m in months)
    subh = "".join(
        f'<th>当月</th><th style="font-size:10px;color:#64748b;">VS均值{team_avg[mi]}%</th>'
        f'<th style="font-size:10px;color:#64748b;">VS上月</th>'
        for mi, m in enumerate(months)
    )
    body = []
    for b in sorted_biz[:35]:
        tds = [
            f'<td style="text-align:left;font-weight:600;">{html_module.escape(_short_biz(b))}</td>',
            f"<td>{biz_avg[b]}%</td>",
        ]
        prev_pct = None
        for mi, m in enumerate(months):
            w = biz_m_five[b][m]
            tt = biz_m_tt[b][m]
            cur = round(tt / (w + 1e-6) * 100, 1) if w else 0.0
            vs = team_avg[mi]
            d_team = round(cur - vs, 1)
            tds.append(f"<td>{cur}%</td>")
            tds.append(_fmt_vs_team_cell(d_team))
            if prev_pct is None:
                tds.append("<td>—</td>")
            else:
                d0 = round(cur - prev_pct, 1)
                tds.append(_fmt_vs_prev_cell(d0))
            prev_pct = cur
        if len(months) >= 2:
            def pct_b(mm):
                w0 = biz_m_five[b].get(mm, 0)
                t0 = biz_m_tt[b].get(mm, 0)
                return round(t0 / (w0 + 1e-6) * 100, 1) if w0 else 0

            t_end = pct_b(months[-1])
            t0 = pct_b(months[0])
            if t_end > t0 + 3:
                trend = '<td class="trend-up">上升</td>'
            elif t_end < t0 - 3:
                trend = '<td class="trend-down">下降</td>'
            else:
                trend = '<td class="trend-stable">稳定</td>'
        else:
            trend = "<td>—</td>"
        tds.append(trend)
        body.append("<tr>" + "".join(tds) + "</tr>")
    return f"""<table>
<thead>
<tr>
<th rowspan="2">业务线</th>
<th rowspan="2">该部门平均<br>测试占比</th>
{header}
<th rowspan="2">趋势</th>
</tr>
<tr>
{subh}
</tr>
</thead>
<tbody>
{"".join(body)}
</tbody>
</table>"""


def build_value_type_table(rows: List[Dict[str, str]]) -> str:
    vt: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"n": 0, "node": 0.0, "bugs": 0.0, "tt": 0.0, "rd": 0.0, "biz": set()}
    )

    def cat(r: Dict[str, str]) -> str:
        t = (r.get("需求类型") or "").strip()
        if "产品" in t:
            return "产品需求"
        if "技术" in t:
            return "技术需求"
        if "合规" in t or "风控" in t:
            return "合规风控需求"
        return "其他需求"

    colors = {"产品需求": "#3b82f6", "技术需求": "#10b981", "合规风控需求": "#f59e0b", "其他需求": "#6b7280"}
    for r in rows:
        v = (r.get("价值类型") or "").strip() or "未分类"
        o = vt[v]
        o["n"] += 1
        o["node"] += float(r.get("全部节点估分") or 0) or 0
        o["bugs"] += float(r.get("总 bug 数") or 0) or 0
        *_, ttv = effort_fields(r)
        o["tt"] += ttv
        o["rd"] += corrected_rd(r)
        o["biz"].add(_biz_line(r))
        if "_sample" not in o:
            o["_sample"] = r
    lines = []
    for name, o in sorted(vt.items(), key=lambda x: -x[1]["tt"])[:22]:
        c = cat(o["_sample"])
        rt = round(o["rd"] / (o["tt"] + 1e-6), 2) if o["tt"] else 0
        cys = [
            _cycle_days(_parse_dt(r.get("创建时间")), _parse_dt(r.get("完成日期")))
            for r in rows
            if ((r.get("价值类型") or "").strip() or "未分类") == name
        ]
        cys = [float(x) for x in cys if x is not None]
        ac = sum(cys) / len(cys) if cys else 0
        tp = round(o["tt"] / (o["node"] + 1e-6) * 100, 1) if o["node"] else 0
        lines.append(
            "<tr>"
            f'<td style="text-align:left;font-weight:600;">{html_module.escape(name)}</td>'
            f'<td style="color:{colors.get(c, "#6b7280")};font-weight:500;">{html_module.escape(c)}</td>'
            f"<td>{o['n']}</td>"
            f'<td style="font-weight:700;color:#dc2626;">{round(o["tt"], 1)}</td>'
            f'<td style="color:#dc2626;">{round(o["tt"] / max(o["n"], 1), 2)}</td>'
            f'<td style="color:#dc2626;">{tp}%</td>'
            f"<td>{round(o['rd'], 2)}</td>"
            f"<td>{round(o['rd'] / max(o['n'], 1), 2)}</td>"
            f"<td>{rt}</td>"
            f"<td>{round(ac, 2)}天</td>"
            f"<td>{int(o['bugs'])}</td>"
            f"<td>{len(o['biz'])}</td>"
            "</tr>"
        )
    return "\n".join(lines)


def _qc_share_tokens(qc_field: str) -> List[str]:
    """多人 QC 同需求：与 P9 / v4 一致按人头均分，避免只计首位 QC。"""
    raw = (qc_field or "").strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split("|") if x.strip()]


def build_rt_bucket_table(rows: List[Dict[str, str]]) -> str:
    qc_stat: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"rd": 0.0, "tt": 0.0, "biz": Counter()})
    for r in rows:
        qcs = _qc_share_tokens(r.get("QC") or "")
        if not qcs:
            continue
        w = 1.0 / len(qcs)
        rc = corrected_rd(r)
        tt = effort_fields(r)[6]
        biz = _biz_line(r)
        for q in qcs:
            qc_stat[q]["rd"] += rc * w
            qc_stat[q]["tt"] += tt * w
            qc_stat[q]["biz"][biz] += w
    rt_list = []
    for q, o in qc_stat.items():
        if o["tt"] <= 0:
            continue
        rt_list.append((q, o["rd"] / o["tt"], o["biz"]))
    buckets: Dict[str, List[Tuple[str, float, Counter]]] = {
        "R/T < 1": [],
        "1 ≤ R/T < 1.5": [],
        "1.5 ≤ R/T < 2": [],
        "2 ≤ R/T < 2.5": [],
        "R/T ≥ 2.5": [],
    }
    for q, rt, bc in rt_list:
        if rt < 1:
            buckets["R/T < 1"].append((q, rt, bc))
        elif rt < 1.5:
            buckets["1 ≤ R/T < 1.5"].append((q, rt, bc))
        elif rt < 2:
            buckets["1.5 ≤ R/T < 2"].append((q, rt, bc))
        elif rt < 2.5:
            buckets["2 ≤ R/T < 2.5"].append((q, rt, bc))
        else:
            buckets["R/T ≥ 2.5"].append((q, rt, bc))
    styles = [
        ("R/T < 1", "#dc2626", "#fef2f2"),
        ("1 ≤ R/T < 1.5", "#f59e0b", "#fff"),
        ("1.5 ≤ R/T < 2", "#10b981", "#fff"),
        ("2 ≤ R/T < 2.5", "#0ea5e9", "#fff"),
        ("R/T ≥ 2.5", "#6366f1", "#fff"),
    ]
    rows_html = []
    for title, color, bg in styles:
        items = buckets[title]
        cnt = len(items)
        biz_parts = []
        all_bc: Counter = Counter()
        for _, _, bc in items:
            all_bc.update(bc)
        for bn, c in all_bc.most_common(12):
            biz_parts.append(f"{_short_biz(bn)}({c})")
        biz_txt = ", ".join(biz_parts) if biz_parts else "—"
        detail = "<br>".join(f"{html_module.escape(q)}({round(rt, 2)})" for q, rt, _ in sorted(items, key=lambda x: x[1])[:25])
        if not detail:
            detail = "—"
        rows_html.append(
            f'<tr style="background:{bg};border-bottom:1px solid #e2e8f0;">'
            f'<td style="padding:10px 8px;font-weight:600;color:{color};">{html_module.escape(title)}</td>'
            f'<td style="padding:10px 8px;text-align:center;font-weight:700;color:{color};">{cnt}</td>'
            f'<td style="padding:10px 8px;font-size:11px;color:#64748b;">{html_module.escape(biz_txt)}</td>'
            f'<td style="padding:10px 8px;font-size:11px;">{detail}</td></tr>'
        )
    return "\n".join(rows_html)


def patch_test_html(
    template: str,
    rows: List[Dict[str, str]],
    months: List[str],
    label: str,
    period_key: Optional[Callable[[Dict[str, str]], Optional[str]]] = None,
    axis_iteration: bool = False,
) -> str:
    _mt, mtot, mtw, monthly, effort_pct = compute_test_report_script_vars(rows, months, period_key)
    sub = "按所属迭代 SP 分桶" if axis_iteration else "按完成日期分月"
    template = re.sub(
        r"<h1>📊 测试效能汇总报告[^<]*</h1>",
        f"<h1>📊 测试效能汇总报告</h1><p style=\"font-size:13px;opacity:.9;margin-top:8px;color:#64748b;\">数据范围：{html_module.escape(label)} · {sub}</p>",
        template,
        count=1,
    )
    template = _replace_bracket_var(template, "months", json.dumps(months, ensure_ascii=False))
    template = _replace_bracket_var(template, "monthTotals", json.dumps(mtot))
    template = _replace_bracket_var(template, "monthTestWork", json.dumps(mtw))
    monthly_js = json.dumps(monthly, ensure_ascii=False, separators=(",", ":"))
    effort_js = json.dumps(effort_pct, ensure_ascii=False, separators=(",", ":"))
    template = re.sub(r"var monthly\s*=\s*\{[\s\S]*?\};", f"var monthly = {monthly_js};", template, count=1)
    template = re.sub(r"var effortData\s*=\s*\{[\s\S]*?\};", f"var effortData = {effort_js};", template, count=1)
    template = re.sub(
        r'<table class="phase-table">[\s\S]*?</table>',
        build_phase_table_html(months, effort_pct, mtot),
        template,
        count=1,
    )
    template = re.sub(
        r"(<div class=\"section-title\">测试阶段占比：各业务线当月实际 vs 各月团队均值</div>\s*<div style=\"overflow-x:auto;\">\s*)<table>[\s\S]*?</table>",
        r"\1" + build_biz_test_pct_table(rows, months, period_key=period_key or _month_period_key),
        template,
        count=1,
    )
    mvt = template.find("按需求价值类型汇总（全局）")
    if mvt >= 0:
        t0 = template.find("<tbody>", mvt)
        t1 = template.find("</tbody>", t0)
        if t0 >= 0 and t1 > t0:
            template = template[: t0 + 7] + "\n" + build_value_type_table(rows) + "\n" + template[t1:]
    rt = template.find("R/T 值分布汇总（按范围和业务线）")
    if rt >= 0:
        t0 = template.find("<tbody>", rt)
        t1 = template.find("</tbody>", t0)
        if t0 >= 0 and t1 > t0:
            template = template[: t0 + 7] + "\n" + build_rt_bucket_table(rows) + "\n" + template[t1:]
    return template


def emit_requirement_report(
    template_key: str,
    out_path: str,
    rows: List[Dict[str, str]],
    data: Dict[str, Any],
    delivery_sd: Dict[str, Any],
    months: List[str],
    label: str,
    source_basename: str,
    *,
    axis_iteration: bool = False,
) -> None:
    src = os.path.join(TEMPLATES_DIR, TEMPLATES[template_key])
    with open(src, "r", encoding="utf-8") as f:
        html = f.read()
    html = replace_json_object_after(html, "var data = ", data)
    html = replace_json_object_after(html, "var sd = ", delivery_sd)
    html = patch_requirement_html(html, months, label)
    html = patch_requirement_appendix(html, rows, months, label, axis_iteration=axis_iteration)
    html = patch_requirement_ai_forecast_title(html, months, axis_iteration=axis_iteration)
    if len(months) >= 2 and months != ["N/A"]:
        html = patch_requirement_last_two_month_strings(
            html, months[-2], months[-1], axis_iteration=axis_iteration
        )
    html = patch_requirement_part_month_title(html, months, axis_iteration=axis_iteration)
    stat_line = "按所属迭代（年+SPRINT）统计" if axis_iteration else "按需求完成日期统计"
    html = re.sub(
        r"数据范围：[^·]+·按需求完成日期统计",
        f"数据范围：{label} · {stat_line}",
        html,
        count=1,
    )
    if axis_iteration:
        html = html.replace("（Gate-RDJ，按完成日期所在月统计）", f"（Gate-RDJ，{stat_line}）")
        html = html.replace(" · 按需求完成日期统计", f" · {stat_line}")
        html = patch_skill_report_iteration_js(html)
        html = patch_iteration_dynamic_labels(html, months[-2], months[-1])
    if template_key == "req_full":
        html = strip_exec_summary_section(html)
    html = html.replace("需求导出-Gate-RDJ (10).csv", source_basename)
    html = inject_echarts_fallback(html)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("Wrote", out_path)


def emit_biz_report(
    out_path: str,
    rows: List[Dict[str, str]],
    data: Dict[str, Any],
    months: List[str],
    label: str,
    source_basename: str,
    *,
    axis_iteration: bool = False,
    qc_group_map: Optional[Dict[str, str]] = None,
) -> None:
    from gate_rdj_metrics import _sp_label as _sp_label_fn

    def pk_row(r: Dict[str, Any]) -> Optional[str]:
        return _sp_label_fn(r) if axis_iteration else _month_period_key(r)

    biz_rows = _apply_qc_grouping(rows, qc_group_map or {})
    axis = "iteration" if axis_iteration else "month"
    biz_data, _biz_sd, _biz_label, _biz_months = build_data_payload(biz_rows, period_axis=axis)
    with open(os.path.join(TEMPLATES_DIR, TEMPLATES["biz"]), "r", encoding="utf-8") as f:
        biz_html = f.read()
    biz_html = patch_gate_rdj_v4_html(
        biz_html, biz_rows, biz_data, months, label,
        period_key=pk_row,
        axis_iteration=axis_iteration,
    )
    biz_html = biz_html.replace("需求导出-Gate-RDJ.csv", source_basename)
    biz_html = inject_echarts_fallback(biz_html)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(biz_html)
    print("Wrote", out_path)


def write_dimension_bundle(csv_path: str, file_prefix: str, forced_axis: Optional[str] = None) -> None:
    """与 main() 同口径：完整版 / 精简版 / 测试汇总 / v4 业务线 共 4 份 HTML（模板与 Gate-RDJ-12 一致）。"""
    rows = load_rows(csv_path)
    axis_kind = forced_axis if forced_axis in ("month", "iteration") else infer_period_axis(rows)
    axis_iteration = axis_kind == "iteration"
    if not axis_iteration:
        rows = filter_rows_for_time_axis(rows)
    period_axis = "iteration" if axis_iteration else "month"
    data, delivery_sd, label, _ = build_data_payload(rows, period_axis=period_axis)
    months = data["months"]
    qc_group_map = _load_qc_group_mapping()
    base = os.path.basename(csv_path)

    def pk_row(r: Dict[str, str]) -> Optional[str]:
        return _sp_label(r) if axis_iteration else _month_period_key(r)

    emit_requirement_report(
        "req_full",
        os.path.join(ROOT, f"{file_prefix}-skill-需求分析报告.html"),
        rows,
        data,
        delivery_sd,
        months,
        label,
        base,
        axis_iteration=axis_iteration,
    )
    emit_requirement_report(
        "req_short",
        os.path.join(ROOT, f"{file_prefix}-skill-需求分析报告_精简版.html"),
        rows,
        data,
        delivery_sd,
        months,
        label,
        base,
        axis_iteration=axis_iteration,
    )
    tpath = os.path.join(TEMPLATES_DIR, TEMPLATES["test"])
    with open(tpath, "r", encoding="utf-8") as f:
        test_html = f.read()
    test_html = inject_echarts_fallback(
        patch_test_html(
            test_html, rows, months, label, period_key=pk_row, axis_iteration=axis_iteration
        )
    )
    test_out = os.path.join(ROOT, f"{file_prefix}-skill-测试效能汇总报告.html")
    with open(test_out, "w", encoding="utf-8") as f:
        f.write(test_html)
    print("Wrote", test_out)
    emit_biz_report(
        os.path.join(ROOT, f"{file_prefix}-v4-业务线分析报告.html"),
        rows,
        data,
        months,
        label,
        base,
        axis_iteration=axis_iteration,
        qc_group_map=qc_group_map,
    )


def infer_period_axis(rows: List[Dict[str, str]]) -> str:
    """根据数据本身判断维度：迭代标签命中率高则视为 iteration，否则 month。"""
    if not rows:
        return "month"
    sample = rows[: min(len(rows), 300)]
    hit = sum(1 for r in sample if _sp_label(r))
    return "iteration" if hit / max(len(sample), 1) >= 0.3 else "month"


def discover_dimension_csvs() -> List[Tuple[str, str, Optional[str]]]:
    """自动发现并生成输出前缀，避免写死“时间维度/迭代维度”文件名。"""
    pairs: List[Tuple[str, str, Optional[str]]] = []
    for name in sorted(os.listdir(ROOT)):
        if not name.startswith("需求导出-Gate-RDJ_") or not name.endswith(".csv"):
            continue
        dim = name.replace("需求导出-Gate-RDJ_", "").replace(".csv", "").strip()
        if not dim:
            continue
        forced_axis: Optional[str] = None
        if "时间" in dim:
            forced_axis = "month"
        elif "迭代" in dim:
            forced_axis = "iteration"
        pairs.append((os.path.join(ROOT, name), f"Gate-RDJ-{dim}", forced_axis))
    return pairs


def build_merged_report_shell(bundle_prefixes: List[str]) -> str:
    """将时间维度与迭代维度报告合并成一个统一入口页。"""
    module_defs = [
        ("req_full", "需求分析报告"),
        ("req_short", "需求分析报告（精简版）"),
        ("test", "测试效能汇总报告"),
        ("biz", "业务线分析报告"),
    ]
    if not bundle_prefixes:
        return ""
    dim_tabs = []
    panel_html = []
    for di, prefix in enumerate(bundle_prefixes):
        dim_name = prefix.replace("Gate-RDJ-", "")
        dim_tabs.append(
            f'<button class="dim-tab{" active" if di == 0 else ""}" data-dim="{di}">{html_module.escape(dim_name)}</button>'
        )
        module_tabs = []
        frames = []
        for mi, (module_key, module_title) in enumerate(module_defs):
            rel = f"{prefix}-{MODULE_OUTPUT_SUFFIX[module_key]}"
            abs_rel = os.path.join(ROOT, rel)
            ver = str(int(os.path.getmtime(abs_rel))) if os.path.exists(abs_rel) else str(int(time.time()))
            module_tabs.append(
                f'<button class="module-tab{" active" if mi == 0 else ""}" data-dim="{di}" data-module="{module_key}">{module_title}</button>'
            )
            frames.append(
                f'<iframe class="report-frame{" active" if mi == 0 else ""}" data-dim="{di}" data-module="{module_key}" src="{html_module.escape(rel, quote=True)}?v={ver}"></iframe>'
            )
        panel_html.append(
            f"""
<section class="dim-panel{" active" if di == 0 else ""}" data-dim="{di}">
  <div class="module-tabs">{''.join(module_tabs)}</div>
  <div class="frame-wrap">{''.join(frames)}</div>
</section>"""
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Gate-RDJ 综合维度统一报告</title>
  <style>
    body {{ margin: 0; font-family: -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:#f8fafc; color:#0f172a; }}
    .header {{ padding: 16px 20px; background:#fff; border-bottom:1px solid #e2e8f0; position: sticky; top:0; z-index:10; }}
    .title {{ font-size:18px; font-weight:700; margin-bottom:12px; }}
    .dim-tabs, .module-tabs {{ display:flex; gap:8px; flex-wrap:wrap; }}
    button {{ border:1px solid #cbd5e1; background:#fff; border-radius:8px; padding:8px 12px; cursor:pointer; color:#334155; }}
    button.active {{ background:#2563eb; color:#fff; border-color:#2563eb; }}
    .content {{ padding:16px 20px; }}
    .dim-panel {{ display:none; }}
    .dim-panel.active {{ display:block; }}
    .frame-wrap {{ margin-top:12px; border:1px solid #e2e8f0; border-radius:10px; overflow:hidden; background:#fff; }}
    .report-frame {{ display:none; width:100%; height: calc(100vh - 230px); border:none; }}
    .report-frame.active {{ display:block; }}
  </style>
</head>
<body>
  <div class="header">
    <div class="title">Gate-RDJ 综合维度统一报告</div>
    <div class="dim-tabs">{''.join(dim_tabs)}</div>
  </div>
  <main class="content">
    {''.join(panel_html)}
  </main>
  <script>
    (function() {{
      const dimTabs = Array.from(document.querySelectorAll('.dim-tab'));
      const dimPanels = Array.from(document.querySelectorAll('.dim-panel'));
      function setActiveDim(dim) {{
        dimTabs.forEach(btn => btn.classList.toggle('active', btn.dataset.dim === dim));
        dimPanels.forEach(panel => panel.classList.toggle('active', panel.dataset.dim === dim));
      }}
      function setActiveModule(dim, module) {{
        document.querySelectorAll('.module-tab').forEach(btn => {{
          const active = btn.dataset.dim === dim && btn.dataset.module === module;
          btn.classList.toggle('active', active);
        }});
        document.querySelectorAll('.report-frame').forEach(frame => {{
          const active = frame.dataset.dim === dim && frame.dataset.module === module;
          frame.classList.toggle('active', active);
        }});
      }}
      dimTabs.forEach(btn => btn.addEventListener('click', () => setActiveDim(btn.dataset.dim)));
      document.querySelectorAll('.module-tab').forEach(btn => {{
        btn.addEventListener('click', () => setActiveModule(btn.dataset.dim, btn.dataset.module));
      }});
    }})();
  </script>
</body>
</html>
"""


def main() -> None:
    rows = filter_rows_for_time_axis(load_rows(CSV))
    data, delivery_sd, label, _ = build_data_payload(rows)
    months = data["months"]
    base = os.path.basename(CSV)
    for key in ("req_full", "req_short"):
        emit_requirement_report(
            key,
            os.path.join(ROOT, OUT[key]),
            rows,
            data,
            delivery_sd,
            months,
            label,
            base,
        )

    tpath = os.path.join(TEMPLATES_DIR, TEMPLATES["test"])
    with open(tpath, "r", encoding="utf-8") as f:
        test_html = f.read()
    test_html = inject_echarts_fallback(patch_test_html(test_html, rows, months, label))
    with open(os.path.join(ROOT, OUT["test"]), "w", encoding="utf-8") as f:
        f.write(test_html)
    print("Wrote", os.path.join(ROOT, OUT["test"]))

    emit_biz_report(os.path.join(ROOT, OUT["biz"]), rows, data, months, label, base)


def main_dimension_csvs() -> None:
    """自动发现维度 CSV，按同口径生成报告，并输出统一入口页。"""
    pairs = discover_dimension_csvs()
    bundle_prefixes: List[str] = []
    for csv_path, file_prefix, forced_axis in pairs:
        if not os.path.isfile(csv_path):
            print("Skip (missing):", csv_path, file=sys.stderr)
            continue
        write_dimension_bundle(csv_path, file_prefix, forced_axis=forced_axis)
        bundle_prefixes.append(file_prefix)
    merged_html = build_merged_report_shell(bundle_prefixes)
    if merged_html:
        merged_out = os.path.join(ROOT, "Gate-RDJ-综合维度-统一报告.html")
        with open(merged_out, "w", encoding="utf-8") as f:
            f.write(merged_html)
        print("Wrote", merged_out)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--legacy-csv":
        main()
    else:
        # 默认：时间维度 + 迭代维度 两份 CSV → Gate-RDJ-时间维度-* / Gate-RDJ-迭代维度-*
        main_dimension_csvs()
