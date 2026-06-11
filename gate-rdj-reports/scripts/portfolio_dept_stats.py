"""部门人员统计：从 report.dev.halftrust.xyz 拉取并解析，生成全景 Tab 图表与表格。"""

from __future__ import annotations

import html as html_mod
import json
import re
import urllib.error
import urllib.request
from html import escape

from _paths import DATA_DIR

DEPT_URL = "https://report.dev.halftrust.xyz/results/department_stats.html"
DEPT_CACHE = DATA_DIR / "department_stats.html"

DEPT_TOOLTIP_JS = """
(function initDeptTooltip(){
  var tip = document.getElementById('deptNameTooltip');
  var table = document.getElementById('deptStatsTable');
  if (!tip || !table) return;
  function namesOf(el) {
    try { return JSON.parse(el.getAttribute('data-names') || '[]'); }
    catch (e) { return []; }
  }
  function show(names, evt) {
    tip.innerHTML = '';
    var title = document.createElement('div');
    title.className = 'dept-tip-title';
    title.textContent = '成员名单';
    tip.appendChild(title);
    if (!names.length) {
      var empty = document.createElement('div');
      empty.textContent = '暂无人员';
      tip.appendChild(empty);
    } else {
      names.forEach(function(n, i) {
        var row = document.createElement('div');
        row.textContent = (i + 1) + '. ' + n;
        tip.appendChild(row);
      });
    }
    tip.style.display = 'block';
    var x = evt.clientX + 14, y = evt.clientY + 14;
    var maxX = window.innerWidth - tip.offsetWidth - 10;
    var maxY = window.innerHeight - tip.offsetHeight - 10;
    tip.style.left = Math.max(10, Math.min(x, maxX)) + 'px';
    tip.style.top = Math.max(10, Math.min(y, maxY)) + 'px';
  }
  table.querySelectorAll('.dept-count').forEach(function(cell) {
    cell.addEventListener('mouseenter', function(e) { show(namesOf(this), e); });
    cell.addEventListener('mousemove', function(e) { show(namesOf(this), e); });
    cell.addEventListener('mouseleave', function() { tip.style.display = 'none'; });
  });
})();
"""


def fetch_dept_stats_html() -> str:
    """优先拉取线上页面，失败则读本地缓存。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(
            DEPT_URL,
            headers={"User-Agent": "gate-rdj-portfolio/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
        DEPT_CACHE.write_text(text, encoding="utf-8")
        return text
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        if DEPT_CACHE.is_file():
            return DEPT_CACHE.read_text(encoding="utf-8")
        raise RuntimeError(f"无法获取部门统计且本地无缓存: {exc}") from exc


def _parse_names(attr: str) -> list[str]:
    m = re.search(r'data-names="([^"]*)"', attr)
    if not m:
        return []
    raw = html_mod.unescape(m.group(1))
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []


def _cell_text(inner: str) -> str:
    return re.sub(r"<[^>]+>", "", inner).strip()


def _parse_cells(tr_html: str) -> list[dict]:
    cells = []
    for m in re.finditer(r"<td([^>]*)>(.*?)</td>", tr_html, re.S):
        cells.append({
            "text": _cell_text(m.group(2)),
            "names": _parse_names(m.group(1)),
        })
    return cells


def _to_int(s: str) -> int:
    s = s.strip().replace(",", "")
    if not s or s == "—":
        return 0
    try:
        return int(float(s))
    except ValueError:
        return 0


_NAME_ROLES = ("pd", "fe", "be", "wbe", "api", "app", "qc", "app_qc")
_TOTAL_NUM_KEYS = ("pd", "fe", "be", "wbe", "api", "app", "dev_total", "qc", "app_qc")


def _dedupe_names(names: list[str]) -> list[str]:
    """成员名单去重（保序），与展示人数对齐。"""
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        s = (n or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _normalize_row_counts(row: dict) -> None:
    """有 data-names 时以去重后人数为准，并刷新开发测试比。"""
    names = row.get("names") or {}
    for role in _NAME_ROLES:
        deduped = _dedupe_names(names.get(role) or [])
        names[role] = deduped
        if deduped:
            row[role] = len(deduped)
    qc = int(row.get("qc") or 0)
    dev = int(row.get("dev_total") or 0)
    if qc > 0 and dev > 0:
        row["dev_rt"] = f"{dev / qc:.1f}:1"


def _recompute_totals(rows: list[dict], source_totals: dict) -> dict:
    totals = {k: sum(int(r.get(k) or 0) for r in rows) for k in _TOTAL_NUM_KEYS}
    qc = int(totals.get("qc") or 0)
    dev = int(totals.get("dev_total") or 0)
    totals["dev_rt"] = f"{dev / qc:.1f}:1" if qc > 0 and dev > 0 else source_totals.get("dev_rt", "—")
    totals["web_rt"] = source_totals.get("web_rt", "—")
    totals["cat_web_rt"] = source_totals.get("cat_web_rt", "—")
    return totals


def parse_dept_stats(html: str) -> dict:
    title_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    title = _cell_text(title_m.group(1)) if title_m else "部门人员统计"
    date_m = re.search(r"(\d{4}-\d{2}-\d{2})", title)
    as_of = date_m.group(1) if date_m else ""

    tbody_m = re.search(r"<tbody>(.*?)</tbody>", html, re.S)
    if not tbody_m:
        raise ValueError("department_stats: 未找到 tbody")
    rows: list[dict] = []
    for tr in re.findall(r"<tr>(.*?)</tr>", tbody_m.group(1), re.S):
        cells = _parse_cells(tr)
        if len(cells) < 14:
            continue
        rows.append({
            "category": cells[0]["text"],
            "group": cells[1]["text"],
            "label": f"{cells[0]['text']}-{cells[1]['text']}",
            "pd": _to_int(cells[2]["text"]),
            "fe": _to_int(cells[3]["text"]),
            "be": _to_int(cells[4]["text"]),
            "wbe": _to_int(cells[5]["text"]),
            "api": _to_int(cells[6]["text"]),
            "app": _to_int(cells[7]["text"]),
            "dev_total": _to_int(cells[8]["text"]),
            "qc": _to_int(cells[9]["text"]),
            "web_rt": cells[10]["text"],
            "cat_web_rt": cells[11]["text"],
            "app_qc": _to_int(cells[12]["text"]),
            "dev_rt": cells[13]["text"],
            "names": {
                "pd": cells[2]["names"],
                "fe": cells[3]["names"],
                "be": cells[4]["names"],
                "wbe": cells[5]["names"],
                "api": cells[6]["names"],
                "app": cells[7]["names"],
                "qc": cells[9]["names"],
                "app_qc": cells[12]["names"],
            },
        })
        _normalize_row_counts(rows[-1])

    tfoot_m = re.search(r"<tfoot>(.*?)</tfoot>", html, re.S)
    totals: dict[str, int | str] = {}
    if tfoot_m:
        tr = re.search(r"<tr[^>]*>(.*?)</tr>", tfoot_m.group(1), re.S)
        if tr:
            cells = _parse_cells(tr.group(1))
            # tfoot 首格 colspan=2（总和），数值列从 index 1 起
            off = 1 if cells and "总和" in cells[0]["text"] else 2
            if len(cells) >= off + 12:
                totals = {
                    "pd": _to_int(cells[off + 0]["text"]),
                    "fe": _to_int(cells[off + 1]["text"]),
                    "be": _to_int(cells[off + 2]["text"]),
                    "wbe": _to_int(cells[off + 3]["text"]),
                    "api": _to_int(cells[off + 4]["text"]),
                    "app": _to_int(cells[off + 5]["text"]),
                    "dev_total": _to_int(cells[off + 6]["text"]),
                    "qc": _to_int(cells[off + 7]["text"]),
                    "web_rt": cells[off + 8]["text"],
                    "cat_web_rt": cells[off + 9]["text"],
                    "app_qc": _to_int(cells[off + 10]["text"]),
                    "dev_rt": cells[off + 11]["text"],
                }
    if rows:
        totals = _recompute_totals(rows, totals)

    cats = sorted({r["category"] for r in rows})
    return {
        "title": title,
        "as_of": as_of,
        "source_url": DEPT_URL,
        "rows": rows,
        "totals": totals,
        "group_count": len(rows),
        "category_count": len(cats),
        "categories": cats,
    }


def load_dept_stats() -> dict:
    return parse_dept_stats(fetch_dept_stats_html())


def dept_kpi(ds: dict) -> dict[str, int | str]:
    t = ds.get("totals") or {}
    return {
        "开发总数": t.get("dev_total", 0),
        "QC人数": t.get("qc", 0),
        "PD人数": t.get("pd", 0),
        "新分组数": ds.get("group_count", 0),
        "开发测试比": t.get("dev_rt", "—"),
        "APP-QC": t.get("app_qc", 0),
    }


def _names_attr(names: list[str]) -> str:
    if not names:
        return ' data-names="[]"'
    payload = json.dumps(names, ensure_ascii=False)
    return f' data-names="{escape(payload, quote=True)}"'


def _count_cell(value: int, names: list[str], *, strong: bool = False) -> str:
    cls = "dept-count" + (" dept-count-strong" if strong else "")
    if not value and not names:
        return f'<td class="{cls} dept-count-zero">0</td>'
    return f'<td class="{cls}"{_names_attr(names)}>{value}</td>'


def dept_table_html(ds: dict) -> str:
    head = """
<thead><tr>
<th>大类名称</th><th>新分组</th><th>PD人数</th><th>FE人数</th><th>BE人数</th><th>WBE人数</th>
<th>API人数</th><th>APP开发</th><th>开发总数</th><th>QC</th><th>开发WEB测试比</th>
<th>大类开发WEB测试比</th><th>APP-QC</th><th>开发测试比</th>
</tr></thead>"""
    body_rows = []
    for r in ds["rows"]:
        n = r["names"]
        body_rows.append(
            f"<tr>"
            f"<td class=\"dept-cat\">{escape(r['category'])}</td>"
            f"<td class=\"dept-group\">{escape(r['group'])}</td>"
            f"{_count_cell(r['pd'], n.get('pd') or [])}"
            f"{_count_cell(r['fe'], n.get('fe') or [])}"
            f"{_count_cell(r['be'], n.get('be') or [])}"
            f"{_count_cell(r['wbe'], n.get('wbe') or [])}"
            f"{_count_cell(r['api'], n.get('api') or [])}"
            f"{_count_cell(r['app'], n.get('app') or [])}"
            f"<td class=\"dept-count dept-count-strong\">{r['dev_total']}</td>"
            f"{_count_cell(r['qc'], n.get('qc') or [])}"
            f"<td class=\"dept-ratio\">{escape(r['web_rt'])}</td>"
            f"<td class=\"dept-ratio\">{escape(r['cat_web_rt'])}</td>"
            f"{_count_cell(r['app_qc'], n.get('app_qc') or [])}"
            f"<td class=\"dept-ratio\">{escape(r['dev_rt'])}</td>"
            f"</tr>"
        )
    t = ds.get("totals") or {}
    foot = f"""
<tfoot><tr class="dept-total">
<td colspan="2"><strong>总和</strong></td>
<td><strong>{t.get('pd', 0)}</strong></td>
<td><strong>{t.get('fe', 0)}</strong></td>
<td><strong>{t.get('be', 0)}</strong></td>
<td><strong>{t.get('wbe', 0)}</strong></td>
<td><strong>{t.get('api', 0)}</strong></td>
<td><strong>{t.get('app', 0)}</strong></td>
<td><strong>{t.get('dev_total', 0)}</strong></td>
<td><strong>{t.get('qc', 0)}</strong></td>
<td><strong>{escape(str(t.get('web_rt', '—')))}</strong></td>
<td><strong>{escape(str(t.get('cat_web_rt', '—')))}</strong></td>
<td><strong>{t.get('app_qc', 0)}</strong></td>
<td><strong>{escape(str(t.get('dev_rt', '—')))}</strong></td>
</tr></tfoot>"""
    return (
        f'<div class="dept-table-wrap">'
        f'<table class="dept-table" id="deptStatsTable">{head}'
        f"<tbody>{''.join(body_rows)}</tbody>{foot}</table></div>"
    )


def dept_panel_html(ds: dict, kpi_html: str) -> str:
    as_of = ds.get("as_of") or "—"
    title = ds.get("title") or "部门人员统计"
    return f"""
<div class="dept-zone">
  <p class="dept-page-meta">数据源 <a href="{escape(ds['source_url'])}" target="_blank" rel="noopener">部门人员统计</a>
  · 截至 {escape(as_of)} · {ds['group_count']} 个新分组 · {ds['category_count']} 个大类 · 悬停蓝色数字查看成员名单</p>
  {kpi_html}
  <details open class="section-group panel-section">
    <summary class="group-title">人员编制明细</summary>
    <div class="section-group-body">{dept_table_html(ds)}</div>
  </details>
</div>
<div id="deptNameTooltip" class="dept-name-tooltip" aria-hidden="true"></div>
<script>{DEPT_TOOLTIP_JS}</script>
"""
