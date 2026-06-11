"""全景单页 · 主站需求工时手工修正 Tab（localStorage 持久化，自动重算 R/T）。"""

from __future__ import annotations

import json
from html import escape
from typing import Any

from portfolio_raw_data import load_raw_records

TEST_FLOOR = 0.05


def hour_override_shared_js(main_rows: list[dict[str, Any]] | None = None) -> str:
    """全页共用：读取覆盖并合并到需求行（原始数据 / 需求明细 / 总览明细 / 部门 R/T 表同步）。"""
    rows = main_rows if main_rows is not None else _main_records(load_raw_records())
    rows_json = json.dumps(rows, ensure_ascii=False)
    body = r"""
(function(){
  if(window.PortfolioHourOverrides) return;
  window.PORTFOLIO_MAIN_ROWS=""" + rows_json + r""";
  var KEY='portfolio_hour_overrides_v1';
  var TEST_FLOOR=0.05;
  var RT_MAIN_COL=10;
  function readAll(){
    try{
      var raw=localStorage.getItem(KEY);
      if(!raw) return {};
      var o=JSON.parse(raw);
      return (o&&typeof o==='object')?o:{};
    }catch(e){ return {}; }
  }
  function writeAll(data){
    localStorage.setItem(KEY, JSON.stringify(data||{}));
    if(window.PortfolioHourOverrides) PortfolioHourOverrides.refreshRtDeptTable();
    window.dispatchEvent(new Event('portfolio-hour-overrides-changed'));
  }
  function calcRt(rd, test){
    if(rd==null||test==null||test<=TEST_FLOOR||rd<=0) return null;
    return Math.round(rd/test*100)/100;
  }
  function rtColor(rt){
    if(rt==null) return '#64748b';
    return rt<2?'#16a34a':(rt<3?'#0369a1':'#dc2626');
  }
  function paintRtCell(td, rt){
    if(!td) return;
    if(rt==null){
      td.className='na';
      td.textContent='—';
      td.style.fontWeight='';
      td.style.color='';
      return;
    }
    td.className='rt-num';
    td.style.fontWeight='700';
    td.style.color=rtColor(rt);
    td.textContent=rt.toFixed(2);
  }
  function rowDepts(r){
    return (r.depts&&r.depts.length)?r.depts:(r.dept?[r.dept]:[]);
  }
  function parseHourInput(s){
    if(s==null) return null;
    var t=String(s).trim().replace(/,/g,'.');
    if(!t) return null;
    var v=parseFloat(t);
    return isNaN(v)?null:v;
  }
  function formatHourInput(v){
    if(v==null||v===''||isNaN(v)) return '';
    return String(v);
  }
  function lockBodyScroll(scrollY){
    document.body.style.position='fixed';
    document.body.style.top='-'+(scrollY||0)+'px';
    document.body.style.width='100%';
    document.body.classList.add('hour-ov-modal-open');
  }
  function unlockBodyScroll(scrollY){
    document.body.classList.remove('hour-ov-modal-open');
    document.body.style.position='';
    document.body.style.top='';
    document.body.style.width='';
    var y=scrollY||0;
    requestAnimationFrame(function(){
      window.scrollTo(0, y);
      requestAnimationFrame(function(){ window.scrollTo(0, y); });
    });
  }
  function closeHourModal(modal){
    if(!modal) return;
    var ov=window.PortfolioHourOverrides;
    var scrollY=ov._modalScrollY||window.scrollY;
    modal.hidden=true;
    ov._modalScrollY=0;
    ov._activeStoryId=null;
    unlockBodyScroll(scrollY);
  }
  window.PortfolioHourOverrides={
    KEY: KEY,
    TEST_FLOOR: TEST_FLOOR,
    readAll: readAll,
    writeAll: writeAll,
    get: function(id){ return readAll()[id]||null; },
    _modalScrollY: 0,
    _activeStoryId: null,
    _pendingRestore: [],
    snapshotDetailLists: function(){
      var self=this;
      var modal=document.getElementById('portfolio-hour-ov-modal');
      var scrollY=(modal&&!modal.hidden&&self._modalScrollY)?self._modalScrollY:window.scrollY;
      self._pendingRestore=[];
      document.querySelectorAll('.ov-dmd-detail-wrap, .raw-detail-wrap').forEach(function(wrap){
        var openMonths=[];
        wrap.querySelectorAll('.dmd-month-fold[open]').forEach(function(d){
          var m=d.getAttribute('data-month');
          if(m) openMonths.push(m);
        });
        self._pendingRestore.push({
          wrap: wrap,
          scrollY: scrollY,
          openMonths: openMonths,
          storyId: self._activeStoryId||null
        });
      });
    },
    consumeSnapshot: function(wrapEl){
      if(!this._pendingRestore||!wrapEl) return null;
      for(var i=0;i<this._pendingRestore.length;i++){
        if(this._pendingRestore[i].wrap===wrapEl){
          return this._pendingRestore.splice(i,1)[0];
        }
      }
      return null;
    },
    set: function(id, patch){
      if(!id) return;
      this.snapshotDetailLists();
      var all=readAll();
      var cur=all[id]||{};
      var next={};
      if(patch.rd!=null&&patch.rd!=='') next.rd=parseHourInput(patch.rd);
      else if(cur.rd!=null) next.rd=cur.rd;
      if(patch.test!=null&&patch.test!=='') next.test=parseHourInput(patch.test);
      else if(cur.test!=null) next.test=cur.test;
      if(patch.note!=null) next.note=String(patch.note);
      else if(cur.note) next.note=cur.note;
      next.updated=new Date().toISOString().slice(0,19).replace('T',' ');
      all[id]=next;
      writeAll(all);
    },
    remove: function(id){
      if(!id) return;
      this.snapshotDetailLists();
      var all=readAll();
      delete all[id];
      writeAll(all);
    },
    clear: function(){
      this.snapshotDetailLists();
      writeAll({});
    },
    count: function(){ return Object.keys(readAll()).length; },
    calcRt: calcRt,
    effectiveRow: function(r){
      if(!r||!r.id) return r;
      var o=readAll()[r.id];
      if(!o) return r;
      var rd=(o.rd!=null&&!isNaN(o.rd))?Number(o.rd):r.rd;
      var test=(o.test!=null&&!isNaN(o.test))?Number(o.test):r.test;
      var rt=calcRt(rd, test);
      var out={};
      for(var k in r) if(Object.prototype.hasOwnProperty.call(r,k)) out[k]=r[k];
      out.rd=(rd!=null&&rd>0)?rd:null;
      out.test=(test!=null&&test>0)?test:null;
      out.rt=rt;
      out._hourOverride=true;
      out._origRd=r.rd;
      out._origTest=r.test;
      out._overrideNote=o.note||'';
      return out;
    },
    mapRows: function(rows){
      return (rows||[]).map(function(r){ return window.PortfolioHourOverrides.effectiveRow(r); });
    },
    computeDeptMainRt: function(rows){
      var self=this, byDept={}, floor=TEST_FLOOR;
      (rows||[]).forEach(function(raw){
        var r=self.effectiveRow(raw);
        if(!r.id||!r.rd||!r.test||r.test<=floor||r.rd<=0) return;
        rowDepts(r).forEach(function(dept){
          if(!dept) return;
          if(!byDept[dept]) byDept[dept]={seen:{}, rd:0, test:0};
          var b=byDept[dept];
          if(b.seen[r.id]) return;
          b.seen[r.id]=true;
          b.rd+=r.rd;
          b.test+=r.test;
        });
      });
      return byDept;
    },
    computeGlobalMainRt: function(rows){
      var self=this, seen={}, rd=0, test=0, floor=TEST_FLOOR;
      (rows||[]).forEach(function(raw){
        var r=self.effectiveRow(raw);
        if(!r.id||seen[r.id]) return;
        if(!r.rd||!r.test||r.test<=floor||r.rd<=0) return;
        seen[r.id]=true;
        rd+=r.rd;
        test+=r.test;
      });
      return calcRt(rd, test);
    },
    refreshRtDeptTable: function(){
      var table=document.querySelector('.rt-dept-table');
      if(!table||!window.PORTFOLIO_MAIN_ROWS) return;
      var self=this, byDept=this.computeDeptMainRt(window.PORTFOLIO_MAIN_ROWS);
      table.querySelectorAll('tbody tr').forEach(function(tr){
        var deptTd=tr.querySelector('td.l');
        if(!deptTd) return;
        var dept=(deptTd.textContent||'').trim();
        var agg=byDept[dept];
        var rtTd=tr.children[RT_MAIN_COL];
        if(!agg||agg.test<=TEST_FLOOR) paintRtCell(rtTd, null);
        else paintRtCell(rtTd, calcRt(agg.rd, agg.test));
      });
      var foot=table.querySelector('tfoot tr');
      if(foot){
        paintRtCell(foot.children[RT_MAIN_COL], this.computeGlobalMainRt(window.PORTFOLIO_MAIN_ROWS));
      }
    },
    exportJson: function(){
      return JSON.stringify(readAll(), null, 2);
    },
    importJson: function(text){
      var o=JSON.parse(text);
      if(!o||typeof o!=='object') throw new Error('无效 JSON');
      writeAll(o);
    },
    ensureModal: function(){
      if(document.getElementById('portfolio-hour-ov-modal')) return;
      var html='<div id="portfolio-hour-ov-modal" class="hour-ov-modal" hidden>'
        +'<div class="hour-ov-modal-backdrop" data-hov-close></div>'
        +'<div class="hour-ov-modal-panel" role="dialog" aria-modal="true">'
        +'<div class="hour-ov-modal-header">'
        +'<div class="hour-ov-modal-header-row">'
        +'<span class="hour-ov-modal-badge">工时修正</span>'
        +'<button type="button" class="hour-ov-modal-close" data-hov-close aria-label="关闭">&times;</button>'
        +'</div>'
        +'<p class="hour-ov-modal-id" id="hour-ov-modal-id"></p>'
        +'<p class="hour-ov-modal-title" id="hour-ov-modal-title"></p>'
        +'</div>'
        +'<div class="hour-ov-modal-body">'
        +'<div class="hour-ov-field-row">'
        +'<div class="hour-ov-field"><span class="hour-ov-field-label">修正研发 <em id="hour-ov-sys-rd"></em></span>'
        +'<input type="text" inputmode="decimal" id="hour-ov-in-rd" class="hour-ov-field-input" placeholder="支持小数，如 1.5"/></div>'
        +'<div class="hour-ov-field"><span class="hour-ov-field-label">修正测试 <em id="hour-ov-sys-test"></em></span>'
        +'<input type="text" inputmode="decimal" id="hour-ov-in-test" class="hour-ov-field-input" placeholder="支持小数，如 0.7"/></div>'
        +'</div>'
        +'<div class="hour-ov-field hour-ov-field--full"><span class="hour-ov-field-label">备注</span>'
        +'<input type="text" id="hour-ov-in-note" class="hour-ov-field-input" placeholder="修正原因（可选）"/></div>'
        +'<div class="hour-ov-rt-banner"><span class="hour-ov-rt-label">修正后 R/T</span>'
        +'<strong id="hour-ov-preview-rt" class="hour-ov-rt-value">—</strong></div>'
        +'</div>'
        +'<div class="hour-ov-modal-footer">'
        +'<button type="button" class="hour-ov-btn hour-ov-btn--ghost" data-hov-close>取消</button>'
        +'<button type="button" class="hour-ov-btn hour-ov-btn--ghost" id="hour-ov-btn-remove">移除修正</button>'
        +'<button type="button" class="hour-ov-btn hour-ov-btn--primary" id="hour-ov-btn-save">保存并更新</button>'
        +'</div></div></div>';
      document.body.insertAdjacentHTML('beforeend', html);
      var modal=document.getElementById('portfolio-hour-ov-modal');
      modal.querySelectorAll('[data-hov-close]').forEach(function(el){
        el.addEventListener('click', function(){ closeHourModal(modal); });
      });
      var rdIn=document.getElementById('hour-ov-in-rd');
      var testIn=document.getElementById('hour-ov-in-test');
      var rtEl=document.getElementById('hour-ov-preview-rt');
      function preview(){
        var rd=parseHourInput(rdIn.value);
        var test=parseHourInput(testIn.value);
        var rt=window.PortfolioHourOverrides.calcRt(rd, test);
        if(rt==null){
          rtEl.textContent='—';
          rtEl.style.color='#64748b';
        }else{
          rtEl.textContent=rt.toFixed(2);
          rtEl.style.color=rtColor(rt);
        }
      }
      rdIn.addEventListener('input', preview);
      testIn.addEventListener('input', preview);
      document.getElementById('hour-ov-btn-save').addEventListener('click', function(){
        var id=modal.getAttribute('data-active-id');
        if(!id) return;
        window.PortfolioHourOverrides.set(id, {
          rd: rdIn.value,
          test: testIn.value,
          note: document.getElementById('hour-ov-in-note').value
        });
        closeHourModal(modal);
      });
      document.getElementById('hour-ov-btn-remove').addEventListener('click', function(){
        var id=modal.getAttribute('data-active-id');
        if(!id) return;
        window.PortfolioHourOverrides.remove(id);
        closeHourModal(modal);
      });
    },
    openEditor: function(r){
      if(!r||!r.id) return;
      this.ensureModal();
      var modal=document.getElementById('portfolio-hour-ov-modal');
      var baseRd=(r._origRd!=null)?r._origRd:r.rd;
      var baseTest=(r._origTest!=null)?r._origTest:r.test;
      var cur=this.get(r.id);
      document.getElementById('hour-ov-modal-id').textContent='Story ID · '+r.id;
      document.getElementById('hour-ov-modal-title').textContent=r.title||'';
      document.getElementById('hour-ov-sys-rd').textContent='系统 '+((baseRd!=null)?Number(baseRd).toFixed(2):'—');
      document.getElementById('hour-ov-sys-test').textContent='系统 '+((baseTest!=null)?Number(baseTest).toFixed(2):'—');
      var rdIn=document.getElementById('hour-ov-in-rd');
      var testIn=document.getElementById('hour-ov-in-test');
      rdIn.value=formatHourInput(cur&&cur.rd!=null?cur.rd:(r.rd!=null?r.rd:null));
      testIn.value=formatHourInput(cur&&cur.test!=null?cur.test:(r.test!=null?r.test:null));
      document.getElementById('hour-ov-in-note').value=(cur&&cur.note)?cur.note:'';
      modal.setAttribute('data-active-id', r.id);
      var scrollY=window.scrollY;
      this._modalScrollY=scrollY;
      this._activeStoryId=r.id;
      var rd=parseHourInput(rdIn.value);
      var test=parseHourInput(testIn.value);
      var rt=this.calcRt(rd, test);
      var rtEl=document.getElementById('hour-ov-preview-rt');
      if(rt==null){ rtEl.textContent='—'; rtEl.style.color='#64748b'; }
      else { rtEl.textContent=rt.toFixed(2); rtEl.style.color=rtColor(rt); }
      lockBodyScroll(scrollY);
      modal.hidden=false;
      setTimeout(function(){ try{ rdIn.focus({preventScroll:true}); }catch(e){ rdIn.focus(); } }, 50);
    },
    bindDetailWrap: function(wrapEl, items){
      if(!wrapEl) return;
      wrapEl._hourOvItems=items||[];
      if(wrapEl._hourOvBound) return;
      wrapEl._hourOvBound=true;
      wrapEl.addEventListener('click', function(e){
        var btn=e.target.closest('[data-hour-ov]');
        if(!btn) return;
        e.preventDefault();
        var id=btn.getAttribute('data-hour-ov');
        var r=null;
        (wrapEl._hourOvItems||[]).forEach(function(x){ if(x.id===id) r=x; });
        if(!r){
          (window.PORTFOLIO_MAIN_ROWS||[]).forEach(function(x){ if(x.id===id) r=x; });
        }
        if(r) window.PortfolioHourOverrides.openEditor(r);
      });
    }
  };
  window.PortfolioHourOverrides.refreshRtDeptTable();
})();
"""
    return body


def _main_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in records if r.get("module") == "主站·Gate-RDJ"]


def hour_override_panel_html(records: list[dict[str, Any]]) -> str:
    main = _main_records(records)
    n_main = len(main)
    return f"""
<div class="data-note"><b>工时修正</b>：针对<b>主站·Gate-RDJ</b>特殊需求手工覆盖研发/测试工时，保存于浏览器 <code>localStorage</code>，自动重算单条 R/T。
修正会同步应用到「总览 · 需求明细」「原始数据」「需求明细」等使用同一套明细数据的视图（刷新或切换 Tab 后生效）。当前主站可修正 <b>{n_main}</b> 条。</div>
<nav class="panel-intro" aria-label="使用说明"><div class="panel-intro-label">使用说明</div><ol>
<li>搜索需求（标题 / Story ID / 链接片段），在结果中点「加入修正」</li>
<li>在修正表中编辑研发、测试人天；R/T 随输入自动更新</li>
<li>支持导出/导入 JSON，便于备份或在同事浏览器间同步</li>
</ol></nav>
<div class="hour-ov-toolbar raw-filter-bar">
  <div class="filter-group hour-ov-search-wrap">
    <label for="hov-search">搜索需求</label>
    <input type="search" id="hov-search" class="hour-ov-search" placeholder="标题、ID 或链接片段…" autocomplete="off"/>
  </div>
  <button type="button" class="btn-reset" id="hov-btn-clear-search">清空搜索</button>
  <span class="hour-ov-kpi" id="hov-kpi"></span>
</div>
<div id="hov-search-results" class="hour-ov-search-results muted"></div>
<div class="hour-ov-actions">
  <button type="button" class="btn-download" id="hov-export">导出修正 JSON</button>
  <button type="button" class="btn-download" id="hov-import-btn">导入 JSON</button>
  <input type="file" id="hov-import-file" accept="application/json,.json" hidden/>
  <button type="button" class="btn-reset" id="hov-clear-all">清空全部修正</button>
</div>
<div class="raw-tables-stack">
<details class="raw-table-fold collapsible-table" open>
  <summary class="raw-fold-summary">
    <span class="raw-fold-title">已修正需求 · 研发 / 测试 / R/T</span>
    <span class="raw-fold-actions"><span class="muted" id="hov-table-count"></span></span>
  </summary>
  <div class="raw-fold-body">
    <p class="section-desc muted table-caption">留空输入框表示沿用系统原值；点「移除」仅删除手工覆盖，恢复导出口径。</p>
    <div id="hov-table-wrap" class="detail-table raw-detail-wrap"></div>
  </div>
</details>
</div>
"""


def hour_override_tab_script(records: list[dict[str, Any]]) -> str:
    main = _main_records(records)
    payload = json.dumps(main, ensure_ascii=False)
    return f"""
(function(){{
  if(window.HOUR_OVERRIDE_TAB_INIT) return;
  window.HOUR_OVERRIDE_TAB_INIT=true;
  var ROWS={payload};
  var searchHits=[];

  function esc(s){{return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}}
  function attr(s){{return String(s||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;');}}
  function fmt(v){{return(v===null||v===undefined||v==='')?'—':(typeof v==='number'?Number(v).toFixed(2):v);}}
  function rtCell(v){{
    if(v===null||v===undefined) return '<span class="na">—</span>';
    var c=v<2?'pill-low':(v<3?'pill-mid':'pill-high');
    return '<span class="pill '+c+'">'+Number(v).toFixed(2)+'</span>';
  }}
  function PO(){{ return window.PortfolioHourOverrides; }}
  function rowById(id){{ for(var i=0;i<ROWS.length;i++) if(ROWS[i].id===id) return ROWS[i]; return null; }}

  function effectivePair(r, o){{
    var rd=(o&&o.rd!=null&&!isNaN(o.rd))?Number(o.rd):r.rd;
    var test=(o&&o.test!=null&&!isNaN(o.test))?Number(o.test):r.test;
    return {{rd: rd, test: test, rt: PO().calcRt(rd, test)}};
  }}

  function sumOverrides(){{
    var all=PO().readAll(), rd=0, test=0, n=0;
    Object.keys(all).forEach(function(id){{
      var r=rowById(id);
      if(!r) return;
      var p=effectivePair(r, all[id]);
      if(p.rt==null) return;
      if(p.rd!=null) rd+=p.rd;
      if(p.test!=null) test+=p.test;
      n++;
    }});
    var rt=(test>0.05&&rd>0)?PO().calcRt(rd, test):null;
    return {{count: Object.keys(all).length, rtN: n, rd: rd, test: test, rt: rt}};
  }}

  function renderKpi(){{
    var s=sumOverrides(), el=document.getElementById('hov-kpi');
    if(!el) return;
  el.innerHTML='已修正 <b>'+s.count+'</b> 条 · 可算 R/T <b>'+s.rtN+'</b>'
    +(s.rt!=null?' · 修正集 R/T <b class="rt-num">'+s.rt.toFixed(2)+'</b>':'');
    var tc=document.getElementById('hov-table-count');
    if(tc) tc.textContent=s.count+' 条修正';
  }}

  function renderSearch(){{
    var el=document.getElementById('hov-search-results');
    if(!el) return;
    if(!searchHits.length){{
      el.innerHTML='<p class="muted">输入关键词搜索主站需求（最多展示 30 条）</p>';
      return;
    }}
    var html='<table class="data-table hour-ov-mini"><thead><tr>'
      +'<th>ID</th><th class="l">需求</th><th>原研发</th><th>原测试</th><th>原R/T</th><th></th></tr></thead><tbody>';
    searchHits.forEach(function(r){{
      html+='<tr><td class="rt-num">'+esc(r.id)+'</td><td class="l">'
        +(r.link?'<a href="'+attr(r.link)+'" target="_blank" rel="noopener">'+esc(r.title)+'</a>':esc(r.title))
        +'</td><td class="rt-num">'+fmt(r.rd)+'</td><td class="rt-num">'+fmt(r.test)+'</td><td class="rt-num">'
        +(r.rt!=null?r.rt.toFixed(2):'—')+'</td><td><button type="button" class="btn-download btn-sm" data-hov-add="'+attr(r.id)+'">加入修正</button></td></tr>';
    }});
    html+='</tbody></table>';
    el.innerHTML=html;
    el.querySelectorAll('[data-hov-add]').forEach(function(btn){{
      btn.addEventListener('click', function(){{
        var id=btn.getAttribute('data-hov-add');
        var r=rowById(id);
        if(!r) return;
        var cur=PO().get(id);
        if(!cur) PO().set(id, {{rd: r.rd, test: r.test, note: ''}});
        renderTable();
        renderKpi();
      }});
    }});
  }}

  function doSearch(q){{
    q=(q||'').trim().toLowerCase();
    if(!q){{ searchHits=[]; renderSearch(); return; }}
    searchHits=ROWS.filter(function(r){{
      return (r.title&&r.title.toLowerCase().indexOf(q)>=0)
        || (r.id&&String(r.id).indexOf(q)>=0)
        || (r.link&&r.link.toLowerCase().indexOf(q)>=0);
    }}).slice(0, 30);
    renderSearch();
  }}

  function renderTable(){{
    var wrap=document.getElementById('hov-table-wrap');
    if(!wrap) return;
    var all=PO().readAll();
    var ids=Object.keys(all).sort();
    if(!ids.length){{
      wrap.innerHTML='<p class="muted">暂无手工修正。请搜索需求并「加入修正」，或导入 JSON。</p>';
      return;
    }}
    var html='<table class="data-table hour-ov-table"><thead><tr>'
      +'<th>ID</th><th class="l">需求</th><th>原研发</th><th>原测试</th>'
      +'<th>修正研发</th><th>修正测试</th><th>R/T</th><th>备注</th><th></th></tr></thead><tbody>';
    ids.forEach(function(id){{
      var r=rowById(id);
      var o=all[id];
      if(!r){{
        html+='<tr class="hour-ov-missing"><td>'+esc(id)+'</td><td colspan="8" class="muted">源数据中未找到该 ID（可移除）</td>'
          +'<td><button type="button" class="btn-reset btn-sm" data-hov-remove="'+attr(id)+'">移除</button></td></tr>';
        return;
      }}
      var p=effectivePair(r, o);
      html+='<tr data-hov-id="'+attr(id)+'">'
        +'<td class="rt-num">'+esc(id)+'</td>'
        +'<td class="l">'+(r.link?'<a href="'+attr(r.link)+'" target="_blank" rel="noopener">'+esc(r.title)+'</a>':esc(r.title))+'</td>'
        +'<td class="rt-num muted">'+fmt(r.rd)+'</td><td class="rt-num muted">'+fmt(r.test)+'</td>'
        +'<td><input type="text" inputmode="decimal" class="hour-ov-input" data-field="rd" value="'+((o.rd!=null)?o.rd:'')+'" placeholder="'+fmt(r.rd)+'"/></td>'
        +'<td><input type="text" inputmode="decimal" class="hour-ov-input" data-field="test" value="'+((o.test!=null)?o.test:'')+'" placeholder="'+fmt(r.test)+'"/></td>'
        +'<td class="rt-num" data-hov-rt>'+rtCell(p.rt)+'</td>'
        +'<td><input type="text" class="hour-ov-note" value="'+esc(o.note||'')+'" placeholder="修正原因"/></td>'
        +'<td><button type="button" class="btn-reset btn-sm" data-hov-remove="'+attr(id)+'">移除</button></td></tr>';
    }});
    html+='</tbody></table>';
    wrap.innerHTML=html;

    wrap.querySelectorAll('tr[data-hov-id]').forEach(function(tr){{
      var id=tr.getAttribute('data-hov-id');
      function syncFromInputs(){{
        var rdIn=tr.querySelector('[data-field="rd"]');
        var testIn=tr.querySelector('[data-field="test"]');
        var noteIn=tr.querySelector('.hour-ov-note');
        PO().set(id, {{rd: rdIn.value, test: testIn.value, note: noteIn.value}});
        var r=rowById(id);
        var p=effectivePair(r, PO().get(id));
        var rtEl=tr.querySelector('[data-hov-rt]');
        if(rtEl) rtEl.innerHTML=rtCell(p.rt);
        renderKpi();
      }}
      tr.querySelectorAll('.hour-ov-input').forEach(function(inp){{
        inp.addEventListener('input', syncFromInputs);
      }});
      var noteIn=tr.querySelector('.hour-ov-note');
      if(noteIn) noteIn.addEventListener('change', syncFromInputs);
    }});
    wrap.querySelectorAll('[data-hov-remove]').forEach(function(btn){{
      btn.addEventListener('click', function(){{
        PO().remove(btn.getAttribute('data-hov-remove'));
        renderTable();
        renderKpi();
      }});
    }});
  }}

  function bindToolbar(){{
    var search=document.getElementById('hov-search');
    if(search){{
      search.addEventListener('input', function(){{ doSearch(search.value); }});
    }}
    var clr=document.getElementById('hov-btn-clear-search');
    if(clr) clr.addEventListener('click', function(){{
      if(search) search.value='';
      doSearch('');
    }});
    var exp=document.getElementById('hov-export');
    if(exp) exp.addEventListener('click', function(){{
      var blob=new Blob([PO().exportJson()], {{type:'application/json'}});
      var a=document.createElement('a');
      a.href=URL.createObjectURL(blob);
      a.download='portfolio-hour-overrides.json';
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      URL.revokeObjectURL(a.href);
    }});
    var impBtn=document.getElementById('hov-import-btn');
    var impFile=document.getElementById('hov-import-file');
    if(impBtn&&impFile){{
      impBtn.addEventListener('click', function(){{ impFile.click(); }});
      impFile.addEventListener('change', function(){{
        var f=impFile.files&&impFile.files[0];
        if(!f) return;
        var reader=new FileReader();
        reader.onload=function(){{
          try{{
            PO().importJson(reader.result);
            renderTable();
            renderKpi();
            alert('导入成功');
          }}catch(e){{ alert('导入失败：'+e.message); }}
          impFile.value='';
        }};
        reader.readAsText(f, 'utf-8');
      }});
    }}
    var clearAll=document.getElementById('hov-clear-all');
    if(clearAll) clearAll.addEventListener('click', function(){{
      if(!confirm('确定清空全部手工工时修正？')) return;
      PO().clear();
      renderTable();
      renderKpi();
    }});
  }}

  function render(){{
    renderKpi();
    renderTable();
    renderSearch();
  }}

  window.initHourOverrideTab=function(){{
    bindToolbar();
    render();
  }};

  window.addEventListener('portfolio-hour-overrides-changed', function(){{
    if(document.querySelector('.panel[data-tab="houroverride"].active')) render();
  }});
}})();
"""


def build_hour_override_tab() -> tuple[str, str]:
    records = load_raw_records()
    return hour_override_panel_html(records), hour_override_tab_script(records)
