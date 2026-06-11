"""全景单页 · 原始数据 Tab：各模块 CSV 统一为可筛选明细表 + 部门×项目汇总。"""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path
from typing import Any

from _paths import DATA_DIR, REPO_ROOT
from build_meegle_report_html import (
    K_COLLAB,
    K_PRIO,
    K_TEST,
    K_TITLE,
    K_TOTAL,
    discover_qc_column,
    fnum,
    load_csv,
    prio_label,
    row_bucket,
)
from gate_rdj_metrics import (
    _biz_line,
    dedupe_main_rows,
    main_row_dedupe_key,
    main_station_role_hours,
)
from generate_chanfeng_station_report import (
    COL_CREATED,
    COL_LINE,
    COL_LINK,
    COL_PRIORITY,
    COL_QC,
    COL_SCHEDULE_TOTAL,
    COL_TEST,
    COL_TITLE,
    parse_schedule_days,
)
from portfolio_dept_stats import DEPT_CACHE
from portfolio_formula_core import portfolio_main_formula_callout_html
from qc_unified_roster_report import (
    CSV_AI_DEMAND_DEFAULT,
    CSV_ITER,
    CSV_STATION,
    CSV_TIME,
    _qc_roster_from_html,
    _resolve_ai_demand_csv,
    dept_display,
    depts_for_qc,
)

ROOT = REPO_ROOT
MEEGLE_CSV = DATA_DIR / "meegle_view_8bbOlLnNU.csv"
TEST_FLOOR = 0.05


def _load_qc_dept_map() -> dict[str, str]:
    html = ""
    if DEPT_CACHE.is_file():
        html = DEPT_CACHE.read_text(encoding="utf-8")
    if not html:
        return {}
    _, group_of, _ = _qc_roster_from_html(html)
    return group_of


def _dept_fields(qc_field: str, group_of: dict[str, str]) -> dict[str, Any]:
    depts = depts_for_qc(qc_field, group_of)
    return {"depts": depts, "dept": dept_display(depts)}


def _story_id(link: str) -> str:
    m = re.search(r"/detail/(\d+)", link or "")
    return m.group(1) if m else ""


def _parse_meta_biz(meta: str) -> str:
    m = re.search(r"业务线\s+([^·]+)", meta or "")
    return (m.group(1).strip() if m else "") or "—"


def _rt_val(rd: float | None, test: float | None) -> float | None:
    if rd is None or test is None or test <= TEST_FLOOR or rd <= 0:
        return None
    return round(rd / test, 2)


def _load_main_rows(group_of: dict[str, str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    allow = set(group_of.keys())
    for r in dedupe_main_rows([CSV_ITER, CSV_TIME]):
        rd, test, rt, qc_parts, dev_parts = main_station_role_hours(r, allow)
        link = (r.get("需求链接") or "").strip()
        qc_raw = (r.get("QC") or "").strip()
        sub = (r.get("所属子项目") or "").strip() or "未填子项目"
        rows.append({
            "module": "主站·Gate-RDJ",
            **_dept_fields(qc_raw, group_of),
            "biz_line": _biz_line(r),
            "project": sub,
            "title": (r.get("名称") or "").strip()[:120],
            "qc": " · ".join(qc_parts) if qc_parts else (qc_raw or "—"),
            "dev_roles": " · ".join(dev_parts) if dev_parts else "",
            "priority": (r.get("优先级") or "").strip() or "—",
            "status": (r.get("状态") or "").strip() or "—",
            "finish_date": (r.get("完成日期") or "").strip()[:10] or "—",
            "rd": rd if rd > 0 else None,
            "test": test if test > 0 else None,
            "rt": rt if rt is not None else _rt_val(rd if rd > 0 else None, test if test > 0 else None),
            "link": link,
            "id": _story_id(link) or main_row_dedupe_key(r),
        })
    return rows


def _load_branch_rows(group_of: dict[str, str]) -> list[dict[str, Any]]:
    import csv

    path = Path(CSV_STATION)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            te = float(r.get(COL_TEST) or 0) if str(r.get(COL_TEST) or "").strip() else 0.0
            sd = parse_schedule_days(r.get(COL_SCHEDULE_TOTAL))
            rd_raw = (sd - te) if sd is not None and te else None
            rd_disp = round(rd_raw, 2) if rd_raw is not None and rd_raw > 0 else None
            test_disp = round(te, 2) if te > 0 else None
            link = (r.get(COL_LINK) or "").strip()
            qc = (r.get(COL_QC) or "").strip()
            line = (r.get(COL_LINE) or "").strip() or "未填业务线"
            rows.append({
                "module": "分站·产研",
                **_dept_fields(qc, group_of),
                "biz_line": line,
                "project": line,
                "title": (r.get(COL_TITLE) or "").strip()[:120],
                "qc": qc or "—",
                "dev_roles": "",
                "priority": (r.get(COL_PRIORITY) or "").strip() or "—",
                "status": (r.get("当前状态") or "").strip() or "—",
                "finish_date": (r.get(COL_CREATED) or "").strip()[:10] or "—",
                "rd": rd_disp,
                "test": test_disp,
                "rt": _rt_val(rd_disp, test_disp),
                "link": link,
                "id": _story_id(link) or (r.get(COL_TITLE) or "")[:40],
            })
    return rows


def _load_ai_rows(group_of: dict[str, str]) -> list[dict[str, Any]]:
    _, ai_rows = _resolve_ai_demand_csv(CSV_AI_DEMAND_DEFAULT)
    rows: list[dict[str, Any]] = []
    for r in ai_rows:
        est = float(r.get("总估算工作量(人/日)") or 0)
        dv = float(r.get("开发参与人数") or 0)
        tv = float(r.get("测试参与人数") or 0)
        total_p = dv + tv
        ed = est * dv / total_p if total_p > 0 else None
        et = est * tv / total_p if total_p > 0 else None
        rd_disp = round(ed, 2) if ed and ed > 0 else None
        test_disp = round(et, 2) if et and et > 0 else None
        link = (r.get("需求链接") or "").strip()
        qc = (r.get("QC") or "").strip()
        proj = (r.get("所属项目") or "").strip() or "未填项目"
        rows.append({
            "module": "AI·Gate-AI",
            **_dept_fields(qc, group_of),
            "biz_line": proj,
            "project": proj,
            "title": (r.get("名称") or "").strip()[:120],
            "qc": qc or "—",
            "dev_roles": "",
            "priority": (r.get("优先级") or "").strip() or "—",
            "status": (r.get("状态") or "").strip() or "—",
            "finish_date": (r.get("完成日期") or "").strip()[:10] or "—",
            "rd": rd_disp,
            "test": test_disp,
            "rt": _rt_val(rd_disp, test_disp),
            "link": link,
            "id": _story_id(link) or (r.get("名称") or "")[:40],
        })
    return rows


def _load_alpha_rows(group_of: dict[str, str]) -> list[dict[str, Any]]:
    if not MEEGLE_CSV.is_file():
        return []
    raw_rows, fields = load_csv(MEEGLE_CSV)
    qc_col, _ = discover_qc_column(fields, raw_rows)
    rows: list[dict[str, Any]] = []
    for r in raw_rows:
        title = (
            r.get("uiDataMap.1l5clgkicafc2.uiValue.nameWithComment.value")
            or r.get(K_TITLE)
            or ""
        ).strip()
        collab = r.get(K_COLLAB, "")
        bucket = row_bucket(title, collab)
        test_pd = fnum(r.get(K_TEST))
        total_pd = fnum(r.get(K_TOTAL))
        rd_raw = (total_pd - test_pd) if total_pd and test_pd else None
        rd_disp = round(rd_raw, 2) if rd_raw and rd_raw > 0 else None
        test_disp = round(test_pd, 2) if test_pd > 0 else None
        qc_raw = (r.get(qc_col) or "").strip() if qc_col else ""
        sid = (r.get("storyID") or r.get("work_item_id") or "").strip()
        link = (
            f"https://project.larksuite.com/iocb9y/project_story/detail/{sid}"
            if sid.isdigit()
            else ""
        )
        bucket_label = "主站" if bucket == "main" else "分站"
        rows.append({
            "module": "Alpha·Meegle",
            **_dept_fields(qc_raw, group_of),
            "biz_line": f"Meegle·{bucket_label}",
            "project": bucket_label,
            "title": title[:120],
            "qc": qc_raw or "—",
            "dev_roles": "",
            "priority": prio_label(r.get(K_PRIO)),
            "status": (r.get("work_item_status") or r.get("状态") or "—"),
            "finish_date": "—",
            "rd": rd_disp,
            "test": test_disp,
            "rt": _rt_val(rd_disp, test_disp),
            "link": link,
            "id": sid or title[:40],
        })
    return rows


def load_raw_records() -> list[dict[str, Any]]:
    group_of = _load_qc_dept_map()
    records: list[dict[str, Any]] = []
    records.extend(_load_main_rows(group_of))
    records.extend(_load_branch_rows(group_of))
    records.extend(_load_ai_rows(group_of))
    records.extend(_load_alpha_rows(group_of))
    return records


def raw_data_panel_html(records: list[dict[str, Any]]) -> str:
    modules = sorted({r["module"] for r in records})
    depts = sorted({d for r in records for d in (r.get("depts") or [r.get("dept")]) if d})
    biz_lines = sorted({r["biz_line"] for r in records if r.get("biz_line")})

    mod_opts = "".join(f'<option value="{escape(m)}">{escape(m)}</option>' for m in modules)
    dept_opts = "".join(f'<option value="{escape(d)}">{escape(d)}</option>' for d in depts)
    biz_opts = "".join(f'<option value="{escape(b)}">{escape(b)}</option>' for b in biz_lines)

    counts = {m: sum(1 for r in records if r["module"] == m) for m in modules}
    count_note = " · ".join(f"{m} {counts[m]} 条" for m in modules)

    return f"""
<div class="data-note"><b>原始数据台账</b>：各模块需求级 CSV 直出，主站已按 story ID 去重（时间+迭代维合并）。
部门=<b>有 QC 参与即算</b>（可跨多部门展示）；筛选按参与部门匹配；R/T 为整单不分摊。<b>主导业务线</b>：主站按 v4 标准业务线（<code>_biz_line</code>）、分站/AI=业务线或所属项目。
<b>汇总表</b>为分组聚合（行数少于明细是正常的）；<b>合计条数与明细总数始终一致</b>。当前共 <b>{len(records)}</b> 条（{escape(count_note)}）。</div>
{portfolio_main_formula_callout_html()}
{panel_intro_raw()}
<div class="raw-filter-bar">
  <div class="raw-filter-path raw-filter-path--dept">
    <span class="raw-filter-path-label">按部门</span>
    <div class="filter-group"><label for="raw-fModuleDept">模块</label>
      <select id="raw-fModuleDept"><option value="">全部模块</option>{mod_opts}</select></div>
    <span class="raw-filter-plus" aria-hidden="true">+</span>
    <div class="filter-group"><label for="raw-fDept">部门</label>
      <select id="raw-fDept"><option value="">全部部门</option>{dept_opts}</select></div>
  </div>
  <div class="raw-filter-or" aria-hidden="true">或</div>
  <div class="raw-filter-path raw-filter-path--biz">
    <span class="raw-filter-path-label">按业务线</span>
    <div class="filter-group"><label for="raw-fModuleBiz">模块</label>
      <select id="raw-fModuleBiz"><option value="">全部模块</option>{mod_opts}</select></div>
    <span class="raw-filter-plus" aria-hidden="true">+</span>
    <div class="filter-group"><label for="raw-fBiz">主导业务线</label>
      <select id="raw-fBiz"><option value="">全部业务线</option>{biz_opts}</select></div>
  </div>
  <button type="button" class="btn-reset" id="raw-btnReset">重置筛选</button>
</div>
<p class="section-desc muted raw-filter-hint">两条筛选路径<b>二选一</b>：<b>模块 + 部门</b>（QC 归属）或 <b>模块 + 主导业务线</b>（v4 标准线）；选一条路径时会清空另一条。</p>
<div id="raw-stats" class="raw-stats"></div>
<div class="raw-tables-stack">
<details class="raw-table-fold collapsible-table" open>
  <summary class="raw-fold-summary">
    <span class="raw-fold-title">汇总表 · 模块 × 部门 × 主导业务线</span>
    <span class="raw-fold-actions">
      <button type="button" class="btn-download" id="raw-dl-summary" title="导出当前筛选结果的汇总表">下载 CSV</button>
    </span>
  </summary>
  <div class="raw-fold-body">
    <p class="section-desc muted table-caption">分组聚合；底部<b>合计条数</b>须与明细总数相同（若不同则为 bug）。主站 R/T 见上方公式；合计 R/T = Σ修正研发÷Σ测试工时。</p>
    <div id="raw-summary-wrap" class="detail-table raw-summary-wrap"></div>
  </div>
</details>
<details class="raw-table-fold collapsible-table" open>
  <summary class="raw-fold-summary">
    <span class="raw-fold-title">明细表 · 需求原始行</span>
    <span class="raw-fold-actions">
      <button type="button" class="btn-download" id="raw-dl-detail" title="导出当前筛选结果的全部明细行">下载 CSV</button>
    </span>
  </summary>
  <div class="raw-fold-body">
    <p class="section-desc muted table-caption">按<b>完成/创建月</b>折叠展示；默认收起月份摘要，点击展开明细；底部<b>筛选合计</b>基于全部筛选行。</p>
    <div id="raw-detail-pager" class="raw-pager"></div>
    <div id="raw-detail-wrap" class="detail-table raw-detail-wrap"></div>
  </div>
</details>
</div>
"""


def panel_intro_raw() -> str:
    items = [
        "筛选：模块+部门 或 模块+主导业务线（二选一）",
        "汇总表：分组聚合；合计条数 = 明细总条数",
        "明细表：分页 + 底部合计；两表均支持下载 CSV",
    ]
    lis = "".join(f"<li>{escape(it)}</li>" for it in items)
    return (
        f'<nav class="panel-intro" aria-label="阅读顺序">'
        f'<div class="panel-intro-label">使用说明</div><ol>{lis}</ol></nav>'
    )


def month_grouped_detail_js_helpers() -> str:
    """明细表按月折叠：默认收起摘要条，点击月份展开明细。"""
    return """
  function monthKey(r){
    var d=r.finish_date;
    if(!d||d==='—') return '未标注';
    return d.length>=7 ? d.slice(0,7) : d;
  }
  function monthLabel(key){
    if(key==='未标注') return '未标注日期';
    var p=key.split('-');
    return p[0]+'年'+parseInt(p[1],10)+'月';
  }
  function groupByMonth(items){
    var map={};
    items.forEach(function(r){
      var m=monthKey(r);
      if(!map[m]) map[m]=[];
      map[m].push(r);
    });
    return Object.keys(map).sort(function(a,b){
      if(a==='未标注') return 1;
      if(b==='未标注') return -1;
      return b.localeCompare(a);
    }).map(function(m){
      return {month:m, rows:map[m].slice().sort(function(a,b){
        return (b.finish_date||'').localeCompare(a.finish_date||'');
      })};
    });
  }
  function hourOvBtn(r){
    if(!r.id||!window.PortfolioHourOverrides) return '<span class="na">—</span>';
    var cls='btn-download btn-sm btn-hour-ov'+(r._hourOverride?' btn-hour-ov--active':'');
    return '<button type="button" class="'+cls+'" data-hour-ov="'+attr(r.id)+'">工时修正</button>';
  }
  function renderDetailRow(r){
    var title=r.link?'<a href="'+attr(r.link)+'" target="_blank" rel="noopener">'+esc(r.title)+'</a>':esc(r.title);
    var rdDisp=fmt(r.rd), testDisp=fmt(r.test);
    if(r._hourOverride){
      rdDisp='<span class="hour-ov-val">'+rdDisp+'</span>';
      testDisp='<span class="hour-ov-val">'+testDisp+'</span>';
    }
    return '<tr'+(r._hourOverride?' class="hour-ov-row"':'')+'>'
      +'<td>'+esc(r.module)+'</td><td class="l">'+esc(r.dept)+'</td><td class="l">'+esc(r.biz_line)+'</td>'
      +'<td class="l">'+title+'</td><td class="rt-num">'+esc(r.id||'—')+'</td>'
      +'<td>'+esc(r.qc)+'</td><td class="l muted">'+esc(r.dev_roles||'—')+'</td>'
      +'<td>'+esc(r.priority)+'</td><td>'+esc(r.status)+'</td>'
      +'<td class="rt-num">'+esc(r.finish_date)+'</td>'
      +'<td class="rt-num">'+rdDisp+'</td><td class="rt-num">'+testDisp+'</td>'
      +'<td class="rt-num">'+rtCell(r.rt)+'</td>'
      +'<td class="rt-num">'+hourOvBtn(r)+'</td></tr>';
  }
  var DETAIL_TBL_HEAD='<table class="data-table raw-detail-table dmd-month-table"><thead><tr>'
    +'<th>模块</th><th>部门</th><th>主导业务线</th><th>需求</th><th>Story ID</th><th>QC</th><th>开发角色</th><th>优先级</th><th>状态</th>'
    +'<th>完成/创建</th><th>研发</th><th>测试</th><th>R/T</th><th>操作</th></tr></thead><tbody>';
  function renderMonthGroupedDetail(wrapEl, pagerEl, items, allTot){
    if(!wrapEl) return;
    var listSnap=(window.PortfolioHourOverrides)?PortfolioHourOverrides.consumeSnapshot(wrapEl):null;
    if(!items.length){
      wrapEl.innerHTML='<div class="drill-empty">当前筛选无匹配需求</div>';
      if(pagerEl) pagerEl.innerHTML='';
      return;
    }
    var groups=groupByMonth(items), html='<div class="dmd-month-stack">';
    groups.forEach(function(g){
      var sub=sumDetail(g.rows), subRt=sub.rt;
      var body=g.rows.map(renderDetailRow).join('');
      var foot='<tr class="dmd-month-subtotal"><td colspan="11"><strong>'+esc(monthLabel(g.month))+' 小计</strong>'
        +'<span class="dmd-month-subnote">'+g.rows.length+' 条 · 可算 '+sub.rtN+'</span></td>'
        +'<td class="rt-num"><strong>'+fmt(sub.rd)+'</strong></td>'
        +'<td class="rt-num"><strong>'+fmt(sub.test)+'</strong></td>'
        +'<td class="rt-num">'+rtCell(subRt)+'</td></tr>';
      html+='<details class="dmd-month-fold" data-month="'+attr(g.month)+'">'
        +'<summary class="dmd-month-summary">'
        +'<span class="dmd-month-label">'+esc(monthLabel(g.month))+'</span>'
        +'<span class="dmd-month-kpi">'
        +'<span class="dmd-month-kpi-item"><b>'+g.rows.length+'</b> 条</span>'
        +'<span class="dmd-month-kpi-item">研发 <b>'+fmt(sub.rd)+'</b></span>'
        +'<span class="dmd-month-kpi-item">测试 <b>'+fmt(sub.test)+'</b></span>'
        +'<span class="dmd-month-kpi-item">R/T <b class="rt-num">'+(subRt!=null?subRt.toFixed(2):'—')+'</b></span>'
        +'</span></summary>'
        +'<div class="dmd-month-body">'+DETAIL_TBL_HEAD+body+foot+'</tbody></table></div></details>';
    });
    html+='<div class="dmd-month-grand">'
      +'<span class="dmd-month-grand-label">筛选合计</span>'
      +'<span class="dmd-month-kpi">'
      +'<span class="dmd-month-kpi-item"><b>'+allTot.n+'</b> 条</span>'
      +'<span class="dmd-month-kpi-item">研发 <b>'+fmt(allTot.rd)+'</b></span>'
      +'<span class="dmd-month-kpi-item">测试 <b>'+fmt(allTot.test)+'</b></span>'
      +'<span class="dmd-month-kpi-item">R/T <b class="rt-num">'+(allTot.rt!=null?allTot.rt.toFixed(2):'—')+'</b></span>'
      +'<span class="dmd-month-kpi-item muted">可算 '+allTot.rtN+'</span>'
      +'</span></div></div>';
    wrapEl.innerHTML=html;
    if(pagerEl){
      pagerEl.innerHTML='<span class="dmd-month-pager-hint">按 <b>'+groups.length+'</b> 个月份分组 · 默认收起 · 点击月份展开明细 · 共 <b>'+items.length+'</b> 条</span>';
    }
    if(window.PortfolioHourOverrides) PortfolioHourOverrides.bindDetailWrap(wrapEl, items);
    else wrapEl._hourOvItems=items;
    if(listSnap){
      listSnap.openMonths.forEach(function(m){
        var d=wrapEl.querySelector('.dmd-month-fold[data-month="'+m+'"]');
        if(d) d.open=true;
      });
      if(listSnap.scrollY!=null){
        var y=listSnap.scrollY;
        requestAnimationFrame(function(){
          window.scrollTo(0, y);
          requestAnimationFrame(function(){ window.scrollTo(0, y); });
        });
      }
    }
  }
"""


def raw_data_script_js(records: list[dict[str, Any]]) -> str:
    payload = json.dumps(records, ensure_ascii=False)
    return f"""
(function(){{
  if(window.RAW_DATA_INIT) return;
  window.RAW_DATA_INIT=true;
  var ROWS={payload};
  var DEFAULT_BIZ='RDJ-交易工具';
  var state={{module:'',dept:'',biz:DEFAULT_BIZ}};
  var PAGE_SIZE=200;
  var detailPage=1;

  function esc(s){{return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}}
  function attr(s){{return String(s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;');}}
  function fmt(v){{return(v===null||v===undefined||v==='')?'—':(typeof v==='number'?v.toFixed(2):v);}}
  function rtCell(v){{
    if(v===null||v===undefined) return '<span class="na">—</span>';
    var c=v<2?'pill-low':(v<3?'pill-mid':'pill-high');
    return '<span class="pill '+c+'">'+Number(v).toFixed(2)+'</span>';
  }}
  function rowDepts(r){{ return (r.depts&&r.depts.length)?r.depts:(r.dept?[r.dept]:[]); }}
  function inDept(r,d){{ return !d||rowDepts(r).indexOf(d)>=0; }}
  function matchRow(r){{
    if(state.module&&r.module!==state.module) return false;
    if(state.dept) return inDept(r,state.dept);
    if(state.biz) return r.biz_line===state.biz;
    return true;
  }}
  function filtered(){{
    var rows=ROWS.filter(matchRow);
    return (window.PortfolioHourOverrides)?PortfolioHourOverrides.mapRows(rows):rows;
  }}

  function sumDetail(items){{
    var rd=0,test=0,rtN=0;
    items.forEach(function(r){{
      if(r.rd!=null) rd+=r.rd;
      if(r.test!=null) test+=r.test;
      if(r.rt!=null) rtN++;
    }});
    var rt=(test>0.05&&rd>0)?Math.round(rd/test*100)/100:null;
    return {{n:items.length,rd:rd,test:test,rt:rt,rtN:rtN}};
  }}
{month_grouped_detail_js_helpers()}
  function csvCell(v){{
    if(v===null||v===undefined) return '';
    var s=String(v);
    if(/[",\\n\\r]/.test(s)) return '"'+s.replace(/"/g,'""')+'"';
    return s;
  }}
  function downloadCsv(filename, headers, rows){{
    var lines=[headers.map(csvCell).join(',')];
    rows.forEach(function(row){{ lines.push(row.map(csvCell).join(',')); }});
    var blob=new Blob(['\\ufeff'+lines.join('\\n')],{{type:'text/csv;charset=utf-8'}});
    var a=document.createElement('a');
    a.href=URL.createObjectURL(blob);
    a.download=filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
  }}
  function filterSlug(){{
    var parts=[];
    if(state.module) parts.push(state.module);
    if(state.dept) parts.push(state.dept);
    if(state.biz) parts.push(state.biz);
    return parts.length?parts.join('-').replace(/[\\\\/:*?"<>|]/g,'_'):'全部';
  }}

  function aggSummary(items){{
    var map={{}};
    items.forEach(function(r){{
      var k=r.module+'\\0'+r.dept+'\\0'+r.biz_line;
      if(!map[k]) map[k]={{module:r.module,dept:r.dept,biz_line:r.biz_line,count:0,rd:0,test:0,rtN:0}};
      var a=map[k];
      a.count++;
      if(r.rt!=null){{
        if(r.rd!=null) a.rd+=r.rd;
        if(r.test!=null) a.test+=r.test;
        a.rtN++;
      }}
    }});
    var rows=Object.keys(map).map(function(k){{return map[k];}});
    rows.sort(function(a,b){{
      if(a.module!==b.module) return a.module.localeCompare(b.module);
      if(a.dept!==b.dept) return a.dept.localeCompare(b.dept);
      return a.biz_line.localeCompare(b.biz_line);
    }});
    return rows;
  }}

  function renderSummary(items){{
    var sums=aggSummary(items);
    var totRd=0,totTest=0,totN=0;
    var body='';
    sums.forEach(function(s){{
      var rt=(s.test>0.05&&s.rd>0)?Math.round(s.rd/s.test*100)/100:null;
      totRd+=s.rd; totTest+=s.test; totN+=s.count;
      body+='<tr><td>'+esc(s.module)+'</td><td class="l">'+esc(s.dept)+'</td><td class="l">'+esc(s.biz_line)+'</td>'
        +'<td class="rt-num">'+s.count+'</td><td class="rt-num">'+fmt(s.test)+'</td><td class="rt-num">'+fmt(s.rd)+'</td>'
        +'<td class="rt-num">'+rtCell(rt)+'</td><td class="rt-num">'+s.rtN+'</td></tr>';
    }});
    var totRt=(totTest>0.05&&totRd>0)?Math.round(totRd/totTest*100)/100:null;
    var parity=totN===items.length?'':' <span class="raw-warn">⚠ 合计条数 '+totN+' ≠ 明细 '+items.length+'</span>';
    var foot='<tr class="rt-dept-total"><td colspan="3"><strong>合计</strong>'
      +'<div class="rt-total-note">'+sums.length+' 个分组 · 明细共 '+items.length+' 条'+parity+'</div></td>'
      +'<td class="rt-num"><strong>'+totN+'</strong></td>'
      +'<td class="rt-num"><strong>'+fmt(totTest)+'</strong></td>'
      +'<td class="rt-num"><strong>'+fmt(totRd)+'</strong></td>'
      +'<td class="rt-num">'+rtCell(totRt)+'</td><td>—</td></tr>';
    var el=document.getElementById('raw-summary-wrap');
    if(!el) return;
    el.innerHTML='<table class="data-table raw-sum-table"><thead><tr>'
      +'<th>模块</th><th>部门</th><th>主导业务线</th><th>条数</th><th>测试</th><th>研发</th><th>R/T</th><th>可算R/T</th>'
      +'</tr></thead><tbody>'+body+foot+'</tbody></table>';
  }}

  function renderDetail(items){{
    renderMonthGroupedDetail(
      document.getElementById('raw-detail-wrap'),
      document.getElementById('raw-detail-pager'),
      items,
      sumDetail(items)
    );
  }}

  function renderStats(items){{
    var el=document.getElementById('raw-stats');
    if(!el) return;
    var sums=aggSummary(items);
    var tot=sumDetail(items);
    el.innerHTML='<span class="kpi-inline">明细 <b>'+items.length+'</b> 条</span>'
      +' <span class="muted">·</span> 汇总 <b>'+sums.length+'</b> 组'
      +' <span class="muted">·</span> 测试 <b>'+fmt(tot.test)+'</b>'
      +' <span class="muted">·</span> 研发 <b>'+fmt(tot.rd)+'</b>'
      +' <span class="muted">·</span> 加权 R/T <b class="rt-num">'+(tot.rt!=null?tot.rt.toFixed(2):'—')+'</b>'
      +' <span class="muted">·</span> 可算 '+tot.rtN+' 条';
  }}

  function stateKeyFor(field){{
    return field==='biz_line'?'biz':field;
  }}
  function refreshSelect(id, field, label){{
    var sel=document.getElementById(id);
    if(!sel) return;
    var set={{}},list=[];
    ROWS.forEach(function(r){{
      if(!matchRowExcept(r, field)) return;
      if(field==='dept'){{
        rowDepts(r).forEach(function(v){{ if(v&&!set[v]){{set[v]=1;list.push(v);}} }});
      }} else {{
        var v=r[field];
        if(v&&!set[v]){{set[v]=1;list.push(v);}}
      }}
    }});
    list.sort();
    var cur=sel.value;
    var sk=stateKeyFor(field);
    sel.innerHTML='<option value="">'+label+'</option>'+list.map(function(p){{return '<option value="'+attr(p)+'">'+esc(p)+'</option>';}}).join('');
    if(list.indexOf(cur)>=0) sel.value=cur; else{{sel.value='';state[sk]='';}}
  }}
  function matchRowExcept(r, skipField){{
    if(skipField!=='module'&&state.module&&r.module!==state.module) return false;
    if(state.dept&&skipField!=='dept'&&!inDept(r,state.dept)) return false;
    if(state.biz&&skipField!=='biz_line'&&r.biz_line!==state.biz) return false;
    return true;
  }}
  function refreshCascade(fromKey){{
    if(fromKey==='module'){{
      refreshSelect('raw-fDept','dept','全部部门');
      refreshSelect('raw-fBiz','biz_line','全部业务线');
    }}
  }}
  function render(){{
    var items=filtered();
    detailPage=1;
    renderStats(items);
    renderSummary(items);
    renderDetail(items);
  }}

  function syncModuleSelects(val){{
    state.module=val;
    ['raw-fModuleDept','raw-fModuleBiz'].forEach(function(id){{
      var el=document.getElementById(id);
      if(el&&el.value!==val) el.value=val;
    }});
  }}
  function clearBizPath(){{
    state.biz='';
    var b=document.getElementById('raw-fBiz');
    if(b) b.value='';
  }}
  function clearDeptPath(){{
    state.dept='';
    var d=document.getElementById('raw-fDept');
    if(d) d.value='';
  }}
  function bindModule(id){{
    var el=document.getElementById(id);
    if(!el) return;
    el.addEventListener('change',function(){{
      syncModuleSelects(el.value);
      if(id==='raw-fModuleDept') clearBizPath();
      else clearDeptPath();
      refreshCascade('module');
      render();
    }});
  }}
  function bindDept(){{
    var el=document.getElementById('raw-fDept');
    if(!el) return;
    el.addEventListener('change',function(){{
      state.dept=el.value;
      if(state.dept) clearBizPath();
      render();
    }});
  }}
  function bindBiz(){{
    var el=document.getElementById('raw-fBiz');
    if(!el) return;
    el.addEventListener('change',function(){{
      state.biz=el.value;
      if(state.biz) clearDeptPath();
      render();
    }});
  }}
  function exportSummaryCsv(){{
    var items=filtered();
    var sums=aggSummary(items);
    var totRd=0,totTest=0,totN=0;
    var rows=sums.map(function(s){{
      var rt=(s.test>0.05&&s.rd>0)?Math.round(s.rd/s.test*100)/100:'';
      totRd+=s.rd; totTest+=s.test; totN+=s.count;
      return [s.module,s.dept,s.biz_line,s.count,s.test||'',s.rd||'',rt,s.rtN];
    }});
    var totRt=(totTest>0.05&&totRd>0)?Math.round(totRd/totTest*100)/100:'';
    rows.push(['合计','','',totN,totTest||'',totRd||'',totRt,'']);
    downloadCsv('原始数据-汇总-'+filterSlug()+'.csv',
      ['模块','部门','主导业务线','条数','测试','研发','R/T','可算R/T'], rows);
  }}
  function exportDetailCsv(){{
    var items=filtered();
    var tot=sumDetail(items);
    var rows=items.map(function(r){{
      return [r.module,r.dept,r.biz_line,r.title,r.id||'',r.qc,r.dev_roles||'',r.priority,r.status,r.finish_date,
        r.rd!=null?r.rd:'',r.test!=null?r.test:'',r.rt!=null?r.rt:'',r.link||''];
    }});
    rows.push(['合计','','','','','','','','','',tot.rd||'',tot.test||'',tot.rt!=null?tot.rt:'','']);
    downloadCsv('原始数据-明细-'+filterSlug()+'.csv',
      ['模块','部门','主导业务线','需求','Story ID','QC','开发角色','优先级','状态','完成/创建','研发','测试','R/T','链接'], rows);
  }}

  bindModule('raw-fModuleDept');
  bindModule('raw-fModuleBiz');
  bindDept();
  bindBiz();
  function bindDownload(id, fn){{
    var el=document.getElementById(id);
    if(!el) return;
    el.addEventListener('click', function(e){{
      e.preventDefault();
      e.stopPropagation();
      fn();
    }});
  }}
  bindDownload('raw-dl-summary', exportSummaryCsv);
  bindDownload('raw-dl-detail', exportDetailCsv);
  function applyDefaults(){{
    state={{module:'',dept:'',biz:DEFAULT_BIZ}};
    syncModuleSelects('');
    var d=document.getElementById('raw-fDept'); if(d) d.value='';
    refreshSelect('raw-fDept','dept','全部部门');
    refreshSelect('raw-fBiz','biz_line','全部业务线');
    var b=document.getElementById('raw-fBiz');
    if(b){{
      var ok=false;
      for(var i=0;i<b.options.length;i++) if(b.options[i].value===DEFAULT_BIZ) ok=true;
      if(ok){{ b.value=DEFAULT_BIZ; state.biz=DEFAULT_BIZ; }}
      else{{ b.value=''; state.biz=''; }}
    }}
  }}

  var reset=document.getElementById('raw-btnReset');
  if(reset) reset.addEventListener('click',function(){{
    applyDefaults();
    render();
  }});

  window.initRawDataTab=function(){{
    applyDefaults();
    render();
  }};
  window.addEventListener('portfolio-hour-overrides-changed', function(){{
    if(document.querySelector('.panel[data-tab="rawdata"].active')) render();
  }});
}})();
"""


def build_raw_data_tab() -> tuple[str, str]:
    records = load_raw_records()
    return raw_data_panel_html(records), raw_data_script_js(records)


def demand_detail_panel_html(records: list[dict[str, Any]]) -> str:
    modules = sorted({r["module"] for r in records})
    depts = sorted({d for r in records for d in (r.get("depts") or [r.get("dept")]) if d})
    mod_opts = "".join(f'<option value="{escape(m)}">{escape(m)}</option>' for m in modules)
    counts = {m: sum(1 for r in records if r["module"] == m) for m in modules}
    count_note = " · ".join(f"{m} {counts[m]} 条" for m in modules)
    return f"""
<div class="data-note"><b>需求明细</b>：与「原始数据」同源；部门=<b>有 QC 参与即算</b>，筛选按参与部门匹配，R/T 整单不分摊。当前共 <b>{len(records)}</b> 条（{escape(count_note)}）。</div>
{portfolio_main_formula_callout_html(compact=True)}
<nav class="panel-intro" aria-label="阅读顺序"><div class="panel-intro-label">使用说明</div><ol>
<li>筛选：模块 + 部门（联动）</li>
<li>汇总表：模块 × 部门 × 主导业务线分组聚合</li>
<li>明细表：分页 + 合计 + CSV 下载</li>
</ol></nav>
<div class="raw-filter-bar">
  <div class="raw-filter-path raw-filter-path--dept">
    <span class="raw-filter-path-label">按部门</span>
    <div class="filter-group"><label for="dmd-fModule">模块</label>
      <select id="dmd-fModule"><option value="">全部模块</option>{mod_opts}</select></div>
    <span class="raw-filter-plus" aria-hidden="true">+</span>
    <div class="filter-group"><label for="dmd-fDept">部门</label>
      <select id="dmd-fDept"><option value="">全部部门</option></select></div>
  </div>
  <button type="button" class="btn-reset" id="dmd-btnReset">重置筛选</button>
</div>
<p class="section-desc muted raw-filter-hint">筛选路径：<b>模块 + 部门</b>；选模块后部门列表自动收窄。</p>
<div id="dmd-stats" class="raw-stats"></div>
<div class="raw-tables-stack">
<details class="raw-table-fold collapsible-table" open>
  <summary class="raw-fold-summary">
    <span class="raw-fold-title">汇总表 · 模块 × 部门 × 主导业务线</span>
    <span class="raw-fold-actions">
      <button type="button" class="btn-download" id="dmd-dl-summary" title="导出汇总表">下载 CSV</button>
    </span>
  </summary>
  <div class="raw-fold-body">
    <p class="section-desc muted table-caption">分组聚合；底部合计条数须与明细总数一致。</p>
    <div id="dmd-summary-wrap" class="detail-table raw-summary-wrap"></div>
  </div>
</details>
<details class="raw-table-fold collapsible-table" open>
  <summary class="raw-fold-summary">
    <span class="raw-fold-title">明细表 · 需求原始行</span>
    <span class="raw-fold-actions">
      <button type="button" class="btn-download" id="dmd-dl-detail" title="导出明细">下载 CSV</button>
    </span>
  </summary>
  <div class="raw-fold-body">
    <p class="section-desc muted table-caption">按<b>完成/创建月</b>折叠；默认收起，点击月份展开。</p>
    <div id="dmd-detail-pager" class="raw-pager"></div>
    <div id="dmd-detail-wrap" class="detail-table raw-detail-wrap"></div>
  </div>
</details>
</div>
"""


def demand_detail_script_js(records: list[dict[str, Any]]) -> str:
    """模块+部门筛选；表结构与原始数据 Tab 一致。"""
    payload = json.dumps(records, ensure_ascii=False)
    return f"""
(function(){{
  if(window.DEMAND_DETAIL_INIT) return;
  window.DEMAND_DETAIL_INIT=true;
  var ROWS={payload};
  var state={{module:'',dept:''}};
  var PAGE_SIZE=200;
  var detailPage=1;
  function esc(s){{return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}}
  function attr(s){{return String(s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;');}}
  function fmt(v){{return(v===null||v===undefined||v==='')?'—':(typeof v==='number'?v.toFixed(2):v);}}
  function rtCell(v){{
    if(v===null||v===undefined) return '<span class="na">—</span>';
    var c=v<2?'pill-low':(v<3?'pill-mid':'pill-high');
    return '<span class="pill '+c+'">'+Number(v).toFixed(2)+'</span>';
  }}
  function rowDepts(r){{ return (r.depts&&r.depts.length)?r.depts:(r.dept?[r.dept]:[]); }}
  function inDept(r,d){{ return !d||rowDepts(r).indexOf(d)>=0; }}
  function matchRow(r){{
    if(state.module&&r.module!==state.module) return false;
    if(state.dept&&!inDept(r,state.dept)) return false;
    return true;
  }}
  function matchExcept(r,skip){{
    if(skip!=='module'&&state.module&&r.module!==state.module) return false;
    if(state.dept&&skip!=='dept'&&!inDept(r,state.dept)) return false;
    return true;
  }}
  function filtered(){{
    var rows=ROWS.filter(matchRow);
    return (window.PortfolioHourOverrides)?PortfolioHourOverrides.mapRows(rows):rows;
  }}
  function sumDetail(items){{
    var rd=0,test=0,rtN=0;
    items.forEach(function(r){{
      if(r.rd!=null) rd+=r.rd;
      if(r.test!=null) test+=r.test;
      if(r.rt!=null) rtN++;
    }});
    var rt=(test>0.05&&rd>0)?Math.round(rd/test*100)/100:null;
    return {{n:items.length,rd:rd,test:test,rt:rt,rtN:rtN}};
  }}
{month_grouped_detail_js_helpers()}
  function csvCell(v){{
    if(v===null||v===undefined) return '';
    var s=String(v);
    if(/[",\\n\\r]/.test(s)) return '"'+s.replace(/"/g,'""')+'"';
    return s;
  }}
  function downloadCsv(filename, headers, rows){{
    var lines=[headers.map(csvCell).join(',')];
    rows.forEach(function(row){{ lines.push(row.map(csvCell).join(',')); }});
    var blob=new Blob(['\\ufeff'+lines.join('\\n')],{{type:'text/csv;charset=utf-8'}});
    var a=document.createElement('a');
    a.href=URL.createObjectURL(blob);
    a.download=filename;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
  }}
  function filterSlug(){{
    var p=[]; if(state.module)p.push(state.module); if(state.dept)p.push(state.dept);
    return p.length?p.join('-').replace(/[\\\\/:*?"<>|]/g,'_'):'全部';
  }}
  function aggSummary(items){{
    var map={{}};
    items.forEach(function(r){{
      var k=r.module+'\\0'+r.dept+'\\0'+r.biz_line;
      if(!map[k]) map[k]={{module:r.module,dept:r.dept,biz_line:r.biz_line,count:0,rd:0,test:0,rtN:0}};
      var a=map[k]; a.count++;
      if(r.rt!=null){{ if(r.rd!=null)a.rd+=r.rd; if(r.test!=null)a.test+=r.test; a.rtN++; }}
    }});
    return Object.keys(map).map(function(k){{return map[k];}}).sort(function(a,b){{
      if(a.module!==b.module)return a.module.localeCompare(b.module);
      if(a.dept!==b.dept)return a.dept.localeCompare(b.dept);
      return a.biz_line.localeCompare(b.biz_line);
    }});
  }}
  function refreshSelect(id,field,label){{
    var sel=document.getElementById(id); if(!sel) return;
    var set={{}},list=[];
    ROWS.forEach(function(r){{
      if(!matchExcept(r,field)) return;
      if(field==='dept'){{
        rowDepts(r).forEach(function(v){{ if(v&&!set[v]){{set[v]=1;list.push(v);}} }});
      }} else {{
        var v=r[field]; if(v&&!set[v]){{set[v]=1;list.push(v);}}
      }}
    }});
    list.sort();
    var cur=sel.value;
    sel.innerHTML='<option value="">'+label+'</option>'+list.map(function(p){{return '<option value="'+attr(p)+'">'+esc(p)+'</option>';}}).join('');
    if(list.indexOf(cur)>=0) sel.value=cur; else{{sel.value=''; if(field==='dept')state.dept='';}}
  }}
  function renderSummary(items){{
    var sums=aggSummary(items), totRd=0,totTest=0,totN=0, body='';
    sums.forEach(function(s){{
      var rt=(s.test>0.05&&s.rd>0)?Math.round(s.rd/s.test*100)/100:null;
      totRd+=s.rd; totTest+=s.test; totN+=s.count;
      body+='<tr><td>'+esc(s.module)+'</td><td class="l">'+esc(s.dept)+'</td><td class="l">'+esc(s.biz_line)+'</td>'
        +'<td class="rt-num">'+s.count+'</td><td class="rt-num">'+fmt(s.test)+'</td><td class="rt-num">'+fmt(s.rd)+'</td>'
        +'<td class="rt-num">'+rtCell(rt)+'</td><td class="rt-num">'+s.rtN+'</td></tr>';
    }});
    var totRt=(totTest>0.05&&totRd>0)?Math.round(totRd/totTest*100)/100:null;
    var foot='<tr class="rt-dept-total"><td colspan="3"><strong>合计</strong><div class="rt-total-note">'+sums.length+' 组 · 明细 '+items.length+' 条</div></td>'
      +'<td class="rt-num"><strong>'+totN+'</strong></td><td class="rt-num"><strong>'+fmt(totTest)+'</strong></td>'
      +'<td class="rt-num"><strong>'+fmt(totRd)+'</strong></td><td class="rt-num">'+rtCell(totRt)+'</td><td>—</td></tr>';
    var el=document.getElementById('dmd-summary-wrap');
    if(el) el.innerHTML='<table class="data-table raw-sum-table"><thead><tr>'
      +'<th>模块</th><th>部门</th><th>主导业务线</th><th>条数</th><th>测试</th><th>研发</th><th>R/T</th><th>可算R/T</th>'
      +'</tr></thead><tbody>'+body+foot+'</tbody></table>';
  }}
  function renderDetail(items){{
    renderMonthGroupedDetail(
      document.getElementById('dmd-detail-wrap'),
      document.getElementById('dmd-detail-pager'),
      items,
      sumDetail(items)
    );
  }}
  function renderStats(items){{
    var el=document.getElementById('dmd-stats'); if(!el) return;
    var sums=aggSummary(items), tot=sumDetail(items);
    el.innerHTML='<span class="kpi-inline">明细 <b>'+items.length+'</b> 条</span> · 汇总 <b>'+sums.length+'</b> 组'
      +' · 测试 <b>'+fmt(tot.test)+'</b> · 研发 <b>'+fmt(tot.rd)+'</b> · R/T <b class="rt-num">'+(tot.rt!=null?tot.rt.toFixed(2):'—')+'</b> · 可算 '+tot.rtN;
  }}
  function render(){{
    var items=filtered(); detailPage=1;
    renderStats(items); renderSummary(items); renderDetail(items);
  }}
  function applyDefaults(){{
    state={{module:'',dept:''}};
    var m=document.getElementById('dmd-fModule'); if(m) m.value='';
    var d=document.getElementById('dmd-fDept'); if(d) d.value='';
    refreshSelect('dmd-fDept','dept','全部部门');
  }}
  var fMod=document.getElementById('dmd-fModule');
  if(fMod) fMod.addEventListener('change',function(){{
    state.module=this.value; state.dept='';
    var d=document.getElementById('dmd-fDept'); if(d) d.value='';
    refreshSelect('dmd-fDept','dept','全部部门'); render();
  }});
  var fDept=document.getElementById('dmd-fDept');
  if(fDept) fDept.addEventListener('change',function(){{ state.dept=this.value; render(); }});
  var reset=document.getElementById('dmd-btnReset');
  if(reset) reset.addEventListener('click',function(){{ applyDefaults(); render(); }});
  function bindDl(id,fn){{
    var el=document.getElementById(id);
    if(el) el.addEventListener('click',function(e){{e.preventDefault();e.stopPropagation();fn();}});
  }}
  bindDl('dmd-dl-summary',function(){{
    var items=filtered(), sums=aggSummary(items), totRd=0,totTest=0,totN=0;
    var rows=sums.map(function(s){{
      var rt=(s.test>0.05&&s.rd>0)?Math.round(s.rd/s.test*100)/100:'';
      totRd+=s.rd;totTest+=s.test;totN+=s.count;
      return [s.module,s.dept,s.biz_line,s.count,s.test||'',s.rd||'',rt,s.rtN];
    }});
    var totRt=(totTest>0.05&&totRd>0)?Math.round(totRd/totTest*100)/100:'';
    rows.push(['合计','','',totN,totTest||'',totRd||'',totRt,'']);
    downloadCsv('需求明细-汇总-'+filterSlug()+'.csv',['模块','部门','主导业务线','条数','测试','研发','R/T','可算R/T'],rows);
  }});
  bindDl('dmd-dl-detail',function(){{
    var items=filtered(), tot=sumDetail(items);
    var rows=items.map(function(r){{
      return [r.module,r.dept,r.biz_line,r.title,r.id||'',r.qc,r.dev_roles||'',r.priority,r.status,r.finish_date,
        r.rd!=null?r.rd:'',r.test!=null?r.test:'',r.rt!=null?r.rt:'',r.link||''];
    }});
    rows.push(['合计','','','','','','','','','',tot.rd||'',tot.test||'',tot.rt!=null?tot.rt:'','']);
    downloadCsv('需求明细-明细-'+filterSlug()+'.csv',['模块','部门','主导业务线','需求','Story ID','QC','开发角色','优先级','状态','完成/创建','研发','测试','R/T','链接'],rows);
  }});
  window.initDemandDetailTab=function(){{ applyDefaults(); render(); }};
}})();
"""


def build_demand_detail_tab() -> tuple[str, str]:
    records = load_raw_records()
    return demand_detail_panel_html(records), demand_detail_script_js(records)


def demand_detail_overview_html(records: list[dict[str, Any]]) -> str:
    """总览 R/T 区内嵌：模块+部门筛选 + 需求明细表。"""
    modules = sorted({r["module"] for r in records})
    mod_opts = "".join(f'<option value="{escape(m)}">{escape(m)}</option>' for m in modules)
    counts = {m: sum(1 for r in records if r["module"] == m) for m in modules}
    count_note = " · ".join(f"{m} {counts[m]} 条" for m in modules)
    return f"""
<div class="rt-drill-block" id="ov-dmd-root">
{portfolio_main_formula_callout_html(compact=True)}
<div class="ov-dmd-toolbar">
  <div class="ov-dmd-filters">
    <label class="ov-dmd-field">
      <span class="ov-dmd-label">模块</span>
      <select id="ov-dmd-fModule" class="ov-dmd-select"><option value="">全部</option>{mod_opts}</select>
    </label>
    <label class="ov-dmd-field">
      <span class="ov-dmd-label">部门</span>
      <select id="ov-dmd-fDept" class="ov-dmd-select"><option value="">全部</option></select>
    </label>
  </div>
  <div class="ov-dmd-actions">
    <button type="button" class="ov-dmd-btn ov-dmd-btn--ghost" id="ov-dmd-btnReset">重置</button>
    <button type="button" class="ov-dmd-btn ov-dmd-btn--primary" id="ov-dmd-dl-detail">下载 CSV</button>
  </div>
</div>
<div id="ov-dmd-stats" class="ov-dmd-stats"></div>
<div id="ov-dmd-pager" class="ov-dmd-pager"></div>
<div id="ov-dmd-detail-wrap" class="detail-table ov-dmd-detail-wrap"></div>
<p class="ov-dmd-foot muted">与「原始数据」同源 · 部门=有 QC 参与即算 · 共 {len(records)} 条（{escape(count_note)}）· 合计 R/T = Σ研发÷Σ测试（整单不分摊）· 完整公式见页面底部附录</p>
</div>
"""


def demand_detail_overview_script(records: list[dict[str, Any]]) -> str:
    """总览内嵌需求明细：明细表 + 分页，initDemandDetailOverview。"""
    payload = json.dumps(records, ensure_ascii=False)
    return f"""
(function(){{
  if(window.DEMAND_DETAIL_OVERVIEW_INIT) return;
  window.DEMAND_DETAIL_OVERVIEW_INIT=true;
  var ROWS={payload};
  var state={{module:'',dept:''}};
  var ready=false;
  var PAGE_SIZE=150;
  var detailPage=1;
  function esc(s){{return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}}
  function attr(s){{return String(s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;');}}
  function fmt(v){{return(v===null||v===undefined||v==='')?'—':(typeof v==='number'?v.toFixed(2):v);}}
  function rtCell(v){{
    if(v===null||v===undefined) return '<span class="na">—</span>';
    var c=v<2?'pill-low':(v<3?'pill-mid':'pill-high');
    return '<span class="pill '+c+'">'+Number(v).toFixed(2)+'</span>';
  }}
  function rowDepts(r){{ return (r.depts&&r.depts.length)?r.depts:(r.dept?[r.dept]:[]); }}
  function inDept(r,d){{ return !d||rowDepts(r).indexOf(d)>=0; }}
  function root(){{ return document.getElementById('ov-dmd-root'); }}
  function matchRow(r){{
    if(state.module&&r.module!==state.module) return false;
    if(state.dept&&!inDept(r,state.dept)) return false;
    return true;
  }}
  function matchExcept(r,skip){{
    if(skip!=='module'&&state.module&&r.module!==state.module) return false;
    if(state.dept&&skip!=='dept'&&!inDept(r,state.dept)) return false;
    return true;
  }}
  function filtered(){{
    var rows=ROWS.filter(matchRow);
    return (window.PortfolioHourOverrides)?PortfolioHourOverrides.mapRows(rows):rows;
  }}
  function csvCell(v){{
    if(v===null||v===undefined) return '';
    var s=String(v);
    if(/[",\\n\\r]/.test(s)) return '"'+s.replace(/"/g,'""')+'"';
    return s;
  }}
  function downloadCsv(filename, headers, rows){{
    var lines=[headers.map(csvCell).join(',')];
    rows.forEach(function(row){{ lines.push(row.map(csvCell).join(',')); }});
    var blob=new Blob(['\\ufeff'+lines.join('\\n')],{{type:'text/csv;charset=utf-8'}});
    var a=document.createElement('a');
    a.href=URL.createObjectURL(blob);
    a.download=filename;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
  }}
  function filterSlug(){{
    var p=[]; if(state.module)p.push(state.module); if(state.dept)p.push(state.dept);
    return p.length?p.join('-').replace(/[\\\\/:*?"<>|]/g,'_'):'全部';
  }}
  function sumDetail(items){{
    var rd=0,test=0,rtN=0;
    items.forEach(function(r){{
      if(r.rd!=null) rd+=r.rd;
      if(r.test!=null) test+=r.test;
      if(r.rt!=null) rtN++;
    }});
    var rt=(test>0.05&&rd>0)?Math.round(rd/test*100)/100:null;
    return {{n:items.length,rd:rd,test:test,rt:rt,rtN:rtN}};
  }}
{month_grouped_detail_js_helpers()}
  function sortByDateDesc(items){{
    return items.slice().sort(function(a,b){{
      return (b.finish_date||'').localeCompare(a.finish_date||'');
    }});
  }}
  function refreshSelect(id,field,label){{
    var sel=document.getElementById(id); if(!sel) return;
    var set={{}},list=[];
    ROWS.forEach(function(r){{
      if(!matchExcept(r,field)) return;
      if(field==='dept'){{
        rowDepts(r).forEach(function(v){{ if(v&&!set[v]){{set[v]=1;list.push(v);}} }});
      }} else {{
        var v=r[field]; if(v&&!set[v]){{set[v]=1;list.push(v);}}
      }}
    }});
    list.sort();
    var cur=sel.value;
    sel.innerHTML='<option value="">'+label+'</option>'+list.map(function(p){{return '<option value="'+attr(p)+'">'+esc(p)+'</option>';}}).join('');
    if(list.indexOf(cur)>=0) sel.value=cur; else{{sel.value=''; if(field==='dept')state.dept='';}}
  }}
  function renderDetail(items){{
    renderMonthGroupedDetail(
      document.getElementById('ov-dmd-detail-wrap'),
      document.getElementById('ov-dmd-pager'),
      items,
      sumDetail(items)
    );
  }}
  function renderStats(items){{
    var el=document.getElementById('ov-dmd-stats'); if(!el) return;
    var tot=sumDetail(items);
    var chips='';
    if(state.module) chips+='<span class="ov-dmd-chip">'+esc(state.module)+'</span>';
    if(state.dept) chips+='<span class="ov-dmd-chip">'+esc(state.dept)+'</span>';
    if(!chips) chips='<span class="ov-dmd-chip ov-dmd-chip--all">全部</span>';
    el.innerHTML='<div class="ov-dmd-stats-row">'
      +'<span class="ov-dmd-stat"><em>'+items.length+'</em> 条</span>'
      +'<span class="ov-dmd-stat">测试 <em>'+fmt(tot.test)+'</em></span>'
      +'<span class="ov-dmd-stat">研发 <em>'+fmt(tot.rd)+'</em></span>'
      +'<span class="ov-dmd-stat">R/T <em class="rt-num">'+(tot.rt!=null?tot.rt.toFixed(2):'—')+'</em></span>'
      +'</div><div class="ov-dmd-chips">'+chips+'</div>';
  }}
  function render(){{
    var items=filtered();
    renderStats(items);
    renderDetail(items);
  }}
  function syncStateFromDom(){{
    var m=document.getElementById('ov-dmd-fModule');
    var d=document.getElementById('ov-dmd-fDept');
    state.module=m?m.value:'';
    state.dept=d?d.value:'';
  }}
  function applyDefaults(){{
    state={{module:'',dept:''}};
    var m=document.getElementById('ov-dmd-fModule'); if(m) m.value='';
    var d=document.getElementById('ov-dmd-fDept'); if(d) d.value='';
    refreshSelect('ov-dmd-fDept','dept','全部');
  }}
  function exportDetail(){{
    var items=sortByDateDesc(filtered()), tot=sumDetail(items);
    var rows=items.map(function(r){{
      return [r.module,r.dept,r.biz_line,r.title,r.id||'',r.qc,r.dev_roles||'',r.priority,r.status,r.finish_date,
        r.rd!=null?r.rd:'',r.test!=null?r.test:'',r.rt!=null?r.rt:'',r.link||''];
    }});
    rows.push(['合计','','','','','','','','','',tot.rd||'',tot.test||'',tot.rt!=null?tot.rt:'','']);
    downloadCsv('需求明细-'+filterSlug()+'.csv',['模块','部门','主导业务线','需求','Story ID','QC','开发角色','优先级','状态','完成/创建','研发','测试','R/T','链接'],rows);
  }}
  function bindOnce(){{
    var box=root(); if(!box||box._ovDmdBound) return;
    box._ovDmdBound=true;
    box.addEventListener('change',function(e){{
      var t=e.target;
      if(t.id==='ov-dmd-fModule'){{
        state.module=t.value||''; state.dept='';
        var d=document.getElementById('ov-dmd-fDept'); if(d) d.value='';
        refreshSelect('ov-dmd-fDept','dept','全部'); render();
      }} else if(t.id==='ov-dmd-fDept'){{
        state.dept=t.value||''; render();
      }}
    }});
    box.addEventListener('click',function(e){{
      var t=e.target;
      if(t&&t.id==='ov-dmd-btnReset'){{ e.preventDefault(); applyDefaults(); render(); }}
      if(t&&t.id==='ov-dmd-dl-detail'){{ e.preventDefault(); exportDetail(); }}
    }});
    var drill=document.querySelector('.rt-drill-section');
    if(drill&&!drill._ovDmdToggle){{
      drill._ovDmdToggle=true;
      drill.addEventListener('toggle',function(){{
        if(drill.open&&!ready) window.initDemandDetailOverview();
      }});
    }}
  }}
  window.initDemandDetailOverview=function(){{
    if(!root()) return;
    bindOnce();
    if(!ready){{ applyDefaults(); ready=true; }}
    else syncStateFromDom();
    render();
  }};
  window.addEventListener('portfolio-hour-overrides-changed', function(){{
    if(!root()) return;
    render();
  }});
}})();
"""


def build_demand_detail_overview() -> tuple[str, str]:
    records = load_raw_records()
    return demand_detail_overview_html(records), demand_detail_overview_script(records)
