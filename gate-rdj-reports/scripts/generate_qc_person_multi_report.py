#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成「QC 人员 · 多维度深描」独立 HTML（不覆盖既有 Gate-RDJ-* 报告）。

口径要点：
- 数据来源：自动发现根目录「需求导出-Gate-RDJ_时间维度.csv」「需求导出-Gate-RDJ_迭代维度.csv」
- 人员与团队：与主流程一致，使用 department_stats 的 QC 白名单 + 新分组（通过 generate_gate_rdj_from_csv 内逻辑）
- 多 QC 同需求：测试工时 / 五阶段工时 / 研发修正 / Bug 等按该需求上白名单 QC 人数均分；需求数按 1/n 加权
- 无白名单 QC 的需求：不参与个人聚合（仍存在于业务「其他」中，本报告脚注说明）
"""
from __future__ import annotations

import html as html_module
import json
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from gate_rdj_metrics import (  # noqa: E402
    _cycle_days,
    _month_period_key,
    _parse_dt,
    _pf,
    _sp_label,
    build_data_payload,
    corrected_rd,
    effort_fields,
    five_phase_total,
    load_rows,
)
import generate_gate_rdj_from_csv as ggen  # noqa: E402

from _paths import REPO_ROOT

ROOT = str(REPO_ROOT)
OUT_HTML = os.path.join(ROOT, "Gate-RDJ-QC人员-多维度深描报告.html")


def _qc_labels(row: Dict[str, str]) -> List[str]:
    raw = (row.get("QC") or "").strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split("|") if x.strip()]


def aggregate_by_qc(rows: List[Dict[str, str]]) -> Tuple[Dict[str, Dict[str, Any]], int]:
    """返回 (qc_key -> stats, skipped_rows_no_qc)。"""
    stats: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "team_w": defaultdict(float),
            "demands_w": 0.0,
            "test": 0.0,
            "five": 0.0,
            "rd_corr": 0.0,
            "bugs_w": 0.0,
            "cycle_w": 0.0,
            "w_cycle": 0.0,
            "months": defaultdict(float),
            "iters": defaultdict(float),
        }
    )
    skipped = 0
    for r in rows:
        qcs = _qc_labels(r)
        if not qcs:
            skipped += 1
            continue
        w = 1.0 / len(qcs)
        team = (r.get("业务线") or "").strip() or "其他"
        d, rd, qc_e, tnode, te, pr, tt = effort_fields(r)
        five = five_phase_total(r)
        bugs = _pf(r.get("总 bug 数"))
        rc = corrected_rd(r)
        cy = _cycle_days(_parse_dt(r.get("创建时间")), _parse_dt(r.get("完成日期")))
        mk = _month_period_key(r)
        sk = _sp_label(r)
        for q in qcs:
            o = stats[q]
            o["team_w"][team] += w
            o["demands_w"] += w
            o["test"] += tt * w
            o["five"] += five * w
            o["rd_corr"] += rc * w
            o["bugs_w"] += bugs * w
            if cy is not None:
                o["cycle_w"] += float(cy) * w
                o["w_cycle"] += w
            if mk:
                o["months"][mk] += w
            if sk:
                o["iters"][sk] += w
    out_stats: Dict[str, Dict[str, Any]] = {}
    for q, o in stats.items():
        tw = o.pop("team_w", {})
        if tw:
            best_team = max(tw.items(), key=lambda kv: kv[1])[0]
        else:
            best_team = ""
        o["team"] = best_team
        out_stats[q] = o
    return out_stats, skipped


def _finish_stats(rows: List[Dict[str, str]]) -> Tuple[Optional[str], Optional[str], int]:
    dates = []
    for r in rows:
        d = _parse_dt(r.get("完成日期"))
        if d:
            dates.append(d)
    if not dates:
        return None, None, 0
    dates.sort()
    return dates[0].strftime("%Y-%m-%d"), dates[-1].strftime("%Y-%m-%d"), len(dates)


def _build_table_rows(
    st_a: Dict[str, Dict[str, Any]],
    st_b: Dict[str, Dict[str, Any]],
    label_a: str,
    label_b: str,
) -> str:
    keys = sorted(set(st_a) | set(st_b), key=lambda k: (-max(st_a.get(k, {}).get("test", 0), st_b.get(k, {}).get("test", 0)), k))
    lines = []
    for k in keys:
        a = st_a.get(k, {})
        b = st_b.get(k, {})
        team = (a.get("team") or b.get("team") or "").strip() or "—"
        lines.append(
            "<tr>"
            f'<td style="text-align:left;font-weight:600;">{html_module.escape(k)}</td>'
            f'<td style="text-align:left;font-size:12px;color:#64748b;">{html_module.escape(team)}</td>'
            f"<td>{round(float(a.get('demands_w', 0)), 2)}</td>"
            f"<td>{round(float(b.get('demands_w', 0)), 2)}</td>"
            f"<td>{round(float(a.get('test', 0)), 1)}</td>"
            f"<td>{round(float(b.get('test', 0)), 1)}</td>"
            f"<td>{round(float(a.get('rd_corr', 0)) / (float(a.get('test', 0)) + 1e-6), 2) if a.get('test') else '—'}</td>"
            f"<td>{round(float(b.get('rd_corr', 0)) / (float(b.get('test', 0)) + 1e-6), 2) if b.get('test') else '—'}</td>"
            f"<td>{round(float(a.get('bugs_w', 0)), 1)}</td>"
            f"<td>{round(float(b.get('bugs_w', 0)), 1)}</td>"
            "</tr>"
        )
    return "\n".join(lines)


def _insights_html(st_time: Dict[str, Dict[str, Any]], st_iter: Dict[str, Dict[str, Any]]) -> str:
    common = set(st_time) & set(st_iter)
    if not common:
        return "<p class=\"note\">两维度无交集 QC，无法计算对照洞察。</p>"
    gaps = []
    for k in common:
        dt = float(st_time[k]["demands_w"])
        di = float(st_iter[k]["demands_w"])
        gaps.append((k, abs(dt - di), dt, di))
    gaps.sort(key=lambda x: -x[1])
    top_gap = gaps[:5]
    test_gap = []
    for k in common:
        tt = float(st_time[k]["test"])
        ti = float(st_iter[k]["test"])
        test_gap.append((k, abs(tt - ti), tt, ti))
    test_gap.sort(key=lambda x: -x[1])
    top_test = test_gap[:5]
    parts = ["<div class=\"section\"><h2>自动洞察 · 两维度对照</h2><ul style=\"margin:0;padding-left:18px;color:#cbd5e1;font-size:13px;line-height:1.75;\">"]
    for k, g, a, b in top_gap:
        parts.append(
            f"<li><b>{html_module.escape(k)}</b>：加权需求数 时间 {a:.2f} vs 迭代 {b:.2f}，绝对差 {g:.2f}（若时间窗口与迭代窗口不完全重叠，出现偏差属正常）。</li>"
        )
    parts.append("</ul><ul style=\"margin:12px 0 0 0;padding-left:18px;color:#cbd5e1;font-size:13px;line-height:1.75;\">")
    for k, g, a, b in top_test:
        parts.append(
            f"<li><b>{html_module.escape(k)}</b>：测试工时 时间 {a:.1f} vs 迭代 {b:.1f}，绝对差 {g:.1f} 人天。</li>"
        )
    parts.append("</ul></div>")
    return "\n".join(parts)


def build_html(
    *,
    label_time: str,
    label_iter: str,
    time_rows_n: int,
    iter_rows_n: int,
    time_skipped: int,
    iter_skipped: int,
    st_time: Dict[str, Dict[str, Any]],
    st_iter: Dict[str, Dict[str, Any]],
    t0_t: Optional[str],
    t1_t: Optional[str],
    t0_i: Optional[str],
    t1_i: Optional[str],
) -> str:
    scatter = []
    for k in sorted(set(st_time) & set(st_iter), key=lambda x: x.lower()):
        scatter.append(
            {
                "name": k,
                "x": round(st_time[k]["demands_w"], 3),
                "y": round(st_iter[k]["demands_w"], 3),
                "tx": round(st_time[k]["test"], 2),
                "ty": round(st_iter[k]["test"], 2),
            }
        )
    scatter_js = json.dumps(scatter, ensure_ascii=False)
    top_time = sorted(st_time.items(), key=lambda kv: -kv[1]["test"])[:18]
    bar_time = {
        "names": [k for k, _ in top_time],
        "vals": [round(v["test"], 2) for _, v in top_time],
    }
    top_iter = sorted(st_iter.items(), key=lambda kv: -kv[1]["test"])[:18]
    bar_iter = {
        "names": [k for k, _ in top_iter],
        "vals": [round(v["test"], 2) for _, v in top_iter],
    }
    bar_time_js = json.dumps(bar_time, ensure_ascii=False)
    bar_iter_js = json.dumps(bar_iter, ensure_ascii=False)
    compare_rows = _build_table_rows(st_time, st_iter, label_time, label_iter)
    insights = _insights_html(st_time, st_iter)

    def esc(s: Optional[str]) -> str:
        return html_module.escape(s or "—")

    core = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Gate-RDJ · QC 人员多维度深描</title>
  <style>
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:#0f172a; color:#e2e8f0; }}
    .wrap {{ max-width:1280px; margin:0 auto; padding:24px 20px 80px; }}
    h1 {{ font-size:22px; font-weight:800; margin:0 0 8px; letter-spacing:-0.02em; }}
    .sub {{ color:#94a3b8; font-size:13px; line-height:1.6; margin-bottom:20px; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:14px; margin-bottom:22px; }}
    .card {{ background:linear-gradient(145deg,#1e293b,#0f172a); border:1px solid #334155; border-radius:14px; padding:16px 18px; }}
    .card h2 {{ margin:0 0 10px; font-size:14px; color:#cbd5e1; font-weight:600; }}
    .metric {{ font-size:26px; font-weight:800; color:#38bdf8; }}
    .metric small {{ font-size:12px; color:#64748b; font-weight:500; margin-left:6px; }}
    .section {{ margin-top:26px; background:#1e293b; border:1px solid #334155; border-radius:14px; padding:18px 18px 8px; }}
    .section h2 {{ margin:0 0 12px; font-size:16px; color:#f1f5f9; }}
    .note {{ font-size:12px; color:#94a3b8; line-height:1.65; margin-bottom:14px; padding:10px 12px; background:#0f172a; border-radius:10px; border:1px solid #334155; }}
    .chart {{ width:100%; height:380px; margin:10px 0 18px; }}
    table {{ width:100%; border-collapse:collapse; font-size:12px; }}
    th, td {{ border-bottom:1px solid #334155; padding:8px 6px; text-align:right; }}
    th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) {{ text-align:left; }}
    th {{ color:#94a3b8; font-weight:600; background:#0f172a; position:sticky; top:0; z-index:1; }}
    tr:hover td {{ background:rgba(56,189,248,0.06); }}
    .pill {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; margin-right:6px; background:#334155; color:#cbd5e1; }}
  </style>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
</head>
<body>
  <div class="wrap">
    <h1>QC 人员 · 多维度深描</h1>
    <p class="sub">
      <span class="pill">时间维度</span>{esc(label_time)}，完成区间 {esc(t0_t)} ~ {esc(t1_t)}，原始行数 <b>{time_rows_n}</b><br/>
      <span class="pill">迭代维度</span>{esc(label_iter)}，完成区间 {esc(t0_i)} ~ {esc(t1_i)}，原始行数 <b>{iter_rows_n}</b><br/>
      团队标签来自 department_stats「新分组」映射；仅统计出现在该页 <b>QC</b> 列白名单内的人员。
    </p>
    <div class="grid">
      <div class="card"><h2>时间维度 · 活跃 QC 人数</h2><div class="metric">{len(st_time)}<small>人</small></div></div>
      <div class="card"><h2>迭代维度 · 活跃 QC 人数</h2><div class="metric">{len(st_iter)}<small>人</small></div></div>
      <div class="card"><h2>无白名单 QC 的需求行（各维度）</h2><div class="metric">{time_skipped}<small>时间</small> / {iter_skipped}<small>迭代</small></div></div>
    </div>
    <div class="note">
      <b>加权说明：</b>同一需求多名白名单 QC 时，该需求的测试工时、五阶段总工时、修正研发、Bug 数按人头均分；需求数按 1/n 加权，避免多人重复满额计数。
      与「只看主 QC」相比，更能反映协作参与；若需主 QC 口径可再开一版开关。
    </div>
    {insights}
    <div class="section">
      <h2>时间 vs 迭代 · 需求覆盖散点（两轴均为加权需求数）</h2>
      <p style="font-size:12px;color:#94a3b8;margin:0 0 8px;">落在对角线附近表示两维度下该 QC 需求覆盖面接近；偏离表示该 QC 在一侧数据集中更集中。</p>
      <div id="chart-scatter" class="chart"></div>
    </div>
    <div class="section">
      <h2>测试工时 TOP（两维度各一张）</h2>
      <div id="chart-bar-time" class="chart"></div>
      <div id="chart-bar-iter" class="chart"></div>
    </div>
    <div class="section">
      <h2>全量对照表 · 按 QC</h2>
      <p style="font-size:12px;color:#94a3b8;margin:0 0 8px;">列：团队 · 加权需求数（时间|迭代）· 测试工时 · R/T · Bug（加权）</p>
      <div style="overflow:auto;max-height:520px;border-radius:10px;border:1px solid #334155;">
        <table>
          <thead>
            <tr>
              <th>QC</th><th>团队（新分组）</th>
              <th>需求ω·时间</th><th>需求ω·迭代</th>
              <th>测试·时间</th><th>测试·迭代</th>
              <th>R/T·时间</th><th>R/T·迭代</th>
              <th>Bugω·时间</th><th>Bugω·迭代</th>
            </tr>
          </thead>
          <tbody>
            {compare_rows}
          </tbody>
        </table>
      </div>
    </div>
  </div>
  <script>
    var scatterData = __SCATTER_JSON__;
    var barTime = __BAR_TIME_JSON__;
    var barIter = __BAR_ITER_JSON__;
    function boot() {{
      if (typeof echarts === 'undefined') {{ setTimeout(boot, 80); return; }}
      var sc = echarts.init(document.getElementById('chart-scatter'));
      sc.setOption({{
        backgroundColor: 'transparent',
        tooltip: {{
          trigger: 'item',
          formatter: function(p) {{
            var d = p.data;
            return '<b>' + d.name + '</b><br/>需求ω 时间: ' + d.value[0] + '<br/>需求ω 迭代: ' + d.value[1] +
              '<br/>测试 时间: ' + d.data.tx + ' · 迭代: ' + d.data.ty;
          }}
        }},
        grid: {{ left:52, right:24, top:24, bottom:44 }},
        xAxis: {{ name: '加权需求数（时间）', nameTextStyle: {{ color:'#94a3b8' }}, axisLabel: {{ color:'#94a3b8' }}, splitLine: {{ lineStyle: {{ color:'#334155' }} }} }},
        yAxis: {{ name: '加权需求数（迭代）', nameTextStyle: {{ color:'#94a3b8' }}, axisLabel: {{ color:'#94a3b8' }}, splitLine: {{ lineStyle: {{ color:'#334155' }} }} }},
        series: [{{
          type: 'scatter',
          symbolSize: 14,
          itemStyle: {{ color: '#38bdf8', opacity: 0.85 }},
          data: scatterData.map(function(d) {{
            return {{ name: d.name, value: [d.x, d.y], tx: d.tx, ty: d.ty }};
          }})
        }}]
      }});
      function bar(domId, title, src) {{
        var el = document.getElementById(domId);
        if (!el) return;
        var c = echarts.init(el);
        c.setOption({{
          backgroundColor: 'transparent',
          title: {{ text: title, left: 'center', top: 6, textStyle: {{ fontSize: 14, color: '#e2e8f0' }} }},
          grid: {{ left:120, right:28, top:44, bottom:28 }},
          xAxis: {{ type: 'value', axisLabel: {{ color:'#94a3b8' }}, splitLine: {{ lineStyle: {{ color:'#334155' }} }} }},
          yAxis: {{ type: 'category', data: src.names, axisLabel: {{ color:'#cbd5e1', fontSize: 11 }} }},
          tooltip: {{ trigger: 'axis' }},
          series: [{{ type: 'bar', data: src.vals, itemStyle: {{ color: '#22d3ee', borderRadius: [0,4,4,0] }} }}]
        }});
        return c;
      }}
      bar('chart-bar-time', '测试工时 TOP（时间维度）', barTime);
      bar('chart-bar-iter', '测试工时 TOP（迭代维度）', barIter);
      window.addEventListener('resize', function() {{
        sc.resize();
        echarts.getInstanceByDom(document.getElementById('chart-bar-time'))?.resize();
        echarts.getInstanceByDom(document.getElementById('chart-bar-iter'))?.resize();
      }});
    }}
    boot();
  </script>
</body>
</html>
"""
    return (
        core.replace("__SCATTER_JSON__", scatter_js)
        .replace("__BAR_TIME_JSON__", bar_time_js)
        .replace("__BAR_ITER_JSON__", bar_iter_js)
    )


def _pick_bundle(pairs: List[Tuple[str, str, Optional[str]]], token: str) -> Optional[Tuple[str, str]]:
    for csv_path, prefix, forced in pairs:
        if token in os.path.basename(csv_path) or token in prefix:
            return csv_path, prefix
    return None


def main() -> int:
    pairs = ggen.discover_dimension_csvs()
    if not pairs:
        print("未找到 需求导出-Gate-RDJ_*.csv", file=sys.stderr)
        return 1
    time_bundle = _pick_bundle(pairs, "时间")
    iter_bundle = _pick_bundle(pairs, "迭代")
    if not time_bundle or not iter_bundle:
        print("需要同时存在时间维度与迭代维度 CSV", file=sys.stderr)
        return 1

    qc_map = ggen._load_qc_group_mapping()
    rows_t_raw = load_rows(time_bundle[0])
    rows_i_raw = load_rows(iter_bundle[0])
    rows_t = ggen._apply_qc_grouping(rows_t_raw, qc_map)
    rows_i = ggen._apply_qc_grouping(rows_i_raw, qc_map)

    st_time, sk_t = aggregate_by_qc(rows_t)
    st_iter, sk_i = aggregate_by_qc(rows_i)

    _, _, label_time, _ = build_data_payload(rows_t_raw, period_axis="month")
    _, _, label_iter, _ = build_data_payload(rows_i_raw, period_axis="iteration")

    t0_t, t1_t, _ = _finish_stats(rows_t)
    t0_i, t1_i, _ = _finish_stats(rows_i)

    html = build_html(
        label_time=str(label_time),
        label_iter=str(label_iter),
        time_rows_n=len(rows_t),
        iter_rows_n=len(rows_i),
        time_skipped=sk_t,
        iter_skipped=sk_i,
        st_time=st_time,
        st_iter=st_iter,
        t0_t=t0_t,
        t1_t=t1_t,
        t0_i=t0_i,
        t1_i=t1_i,
    )
    html = ggen.inject_echarts_fallback(html)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print("Wrote", OUT_HTML)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
