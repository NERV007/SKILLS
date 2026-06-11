"""全景单页 · 设计系统样式（dashboard / KPI / chart / table / tab）。"""

RDJ_DASHBOARD_CSS = """
:root {
  --bg: #eef2f6;
  --surface: #ffffff;
  --surface-2: #f8fafc;
  --border: #e2e8f0;
  --border-accent: #cbd5e1;
  --text: #334155;
  --text-strong: #0f172a;
  --text-muted: #475569;
  --text-faint: #64748b;
  --brand: #0369a1;
  --brand-light: #0ea5e9;
  --brand-cyan: #38bdf8;
  --brand-pale: #e0f2fe;
  --brand-bg: #f8fafc;
  --table-head: #0e7490;
  --radius-sm: 10px;
  --radius-md: 14px;
  --radius-lg: 16px;
  --shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.05);
  --shadow-md: 0 4px 14px rgba(15, 23, 42, 0.06);
  --shadow-lg: 0 12px 32px rgba(15, 23, 42, 0.08);
  --font: 'PingFang SC', 'Microsoft YaHei', 'Segoe UI', sans-serif;
  --kpi-accent: #0369a1;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: var(--font);
  background: var(--bg);
  min-height: 100vh;
  padding: 24px 20px 40px;
  color: var(--text);
  line-height: 1.65;
  font-size: 15px;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.dashboard {
  max-width: 1720px;
  margin: 0 auto;
  background: var(--surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  overflow: visible;
  border: 1px solid rgba(203, 213, 225, 0.65);
}

/* ── Header（汇报向） ── */
.header {
  background: linear-gradient(125deg, #0c4a6e 0%, #0369a1 42%, #0ea5e9 100%);
  color: #fff;
  padding: 36px 40px 28px;
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
}
.header-top { max-width: 100%; }
.header-brand { text-align: left; }
.header .eyebrow {
  display: inline-block;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  padding: 5px 14px;
  margin-bottom: 14px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.18);
}
.header h1 {
  font-size: 2rem;
  font-weight: 800;
  letter-spacing: 0.01em;
  margin-bottom: 10px;
  line-height: 1.2;
}
.header .sub {
  font-size: 0.95rem;
  font-weight: 400;
  max-width: 820px;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.82);
}
.header-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 22px;
  padding-top: 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.14);
}
.header-pill {
  display: inline-flex;
  align-items: baseline;
  gap: 8px;
  padding: 8px 14px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 999px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.78);
}
.header-pill em {
  font-style: normal;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.header-pill strong {
  font-size: 15px;
  font-weight: 800;
  color: #fff;
  font-variant-numeric: tabular-nums;
}
.header-pill--accent {
  background: rgba(255, 255, 255, 0.16);
  border-color: rgba(255, 255, 255, 0.28);
}

/* ── Nav Tabs（底边线导航） ── */
.nav-tabs {
  display: flex;
  gap: 0;
  flex-wrap: wrap;
  justify-content: flex-start;
  padding: 0 36px;
  background: #fff;
  border-bottom: 2px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 30;
  backdrop-filter: blur(10px);
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.04);
}
.nav-tab {
  border: none;
  background: transparent;
  border-radius: 0;
  padding: 15px 20px;
  margin-bottom: -2px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 700;
  color: var(--text-faint);
  border-bottom: 3px solid transparent;
  transition: color 0.15s, border-color 0.15s;
}
.nav-tab:hover {
  color: var(--brand);
  background: transparent;
  box-shadow: none;
}
.nav-tab.active {
  color: var(--brand);
  background: transparent;
  border-bottom-color: var(--brand);
  box-shadow: none;
}
.nav-tab[data-tab="main"].active { color: #2563eb; border-bottom-color: #2563eb; }
.nav-tab[data-tab="branch"].active { color: #059669; border-bottom-color: #059669; }
.nav-tab[data-tab="ai"].active { color: #7c3aed; border-bottom-color: #7c3aed; }
.nav-tab[data-tab="alpha"].active { color: #ea580c; border-bottom-color: #ea580c; }
.nav-tab[data-tab="dept"].active { color: #0891b2; border-bottom-color: #0891b2; }
.nav-tab[data-tab="rawdata"].active { color: #475569; border-bottom-color: #475569; }

/* ── 原始数据 Tab ── */
.panel[data-tab="rawdata"] { padding: 24px 28px 36px; }
.raw-filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 16px;
  align-items: stretch;
  margin: 16px 0 8px;
  padding: 14px 16px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}
.raw-filter-path {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 12px;
  align-items: flex-end;
  padding: 10px 14px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: #fafbfc;
}
.raw-filter-path--dept { border-color: #bfdbfe; background: #f8fbff; }
.raw-filter-path--biz { border-color: #fde68a; background: #fffbeb; }
.raw-filter-path-label {
  flex: 0 0 100%;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  color: var(--text-faint);
}
.raw-filter-plus {
  align-self: center;
  padding-bottom: 6px;
  font-size: 14px;
  font-weight: 700;
  color: var(--text-faint);
}
.raw-filter-or {
  align-self: center;
  padding: 0 2px 6px;
  font-size: 14px;
  font-weight: 700;
  color: var(--text-muted);
}
.raw-filter-bar .btn-reset { align-self: center; margin-left: auto; }
.raw-filter-hint { margin: 0 0 12px; font-size: 12px; }
.raw-stats {
  margin: 0 0 16px;
  padding: 10px 14px;
  background: #f0f9ff;
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: var(--text-muted);
}
.raw-section { margin-top: 20px; }
/* 原始数据 · 折叠表（对齐 Gate-RDJ 时间维 collapsible-table） */
.raw-tables-stack { margin-top: 4px; }
.raw-table-fold.collapsible-table {
  margin-top: 16px;
  border-radius: 8px;
  overflow: hidden;
}
.raw-tables-stack .raw-table-fold > summary.raw-fold-summary {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 92px 76px;
  align-items: center;
  column-gap: 10px;
  padding: 8px 0;
  padding-bottom: 6px;
  border-bottom: 2px solid #38bdf8;
  cursor: pointer;
  list-style: none;
  user-select: none;
}
.raw-table-fold > summary.raw-fold-summary::-webkit-details-marker { display: none; }
.raw-table-fold > summary.raw-fold-summary::marker { display: none; }
.raw-fold-title {
  grid-column: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 700;
  color: #0c4a6e;
  letter-spacing: 0.02em;
}
.raw-fold-actions {
  grid-column: 2;
  display: flex;
  align-items: center;
  justify-content: flex-end;
}
.raw-fold-actions .btn-download {
  width: 92px;
  text-align: center;
  box-sizing: border-box;
}
.raw-tables-stack .raw-table-fold > summary.raw-fold-summary::after {
  grid-column: 3;
  justify-self: end;
  content: '▶ 展开';
  font-size: 10px;
  font-weight: 500;
  color: #94a3b8;
  background: #f1f5f9;
  padding: 3px 10px;
  border-radius: 12px;
  transition: all 0.25s;
  white-space: nowrap;
}
.raw-table-fold[open] > summary.raw-fold-summary::after {
  content: '▼ 收起';
  color: #0369a1;
  background: #e0f2fe;
}
.raw-table-fold[open] > summary.raw-fold-summary {
  margin-bottom: 10px;
}
.raw-fold-body .table-caption {
  margin: 0 0 8px;
  color: #6b7280;
  font-size: 0.85em;
  line-height: 1.4;
}
.raw-fold-body .detail-table {
  padding: 12px;
  margin-bottom: 0;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  overflow: visible;
  background: #fff;
}
.raw-table-fold .raw-summary-wrap,
.raw-table-fold .raw-detail-wrap {
  max-height: none;
  overflow: visible;
}
.raw-table-fold .raw-sum-table th,
.raw-table-fold .raw-detail-table th {
  background: #0e7490;
  color: #fff;
  font-weight: 600;
  font-size: 10.5px;
  letter-spacing: 0.02em;
  border-color: #e2e8f0;
}
.raw-table-fold .raw-sum-table tr:nth-child(even),
.raw-table-fold .raw-detail-table tr:nth-child(even) {
  background: #f8fafc;
}
.raw-table-fold .raw-sum-table tr:hover,
.raw-table-fold .raw-detail-table tr:hover {
  background: #e0f2fe;
}
.raw-section-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 12px;
  margin-bottom: 6px;
}
.raw-section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--brand);
}
.btn-download {
  padding: 4px 12px;
  font-size: 11px;
  font-weight: 600;
  color: #0369a1;
  background: #fff;
  border: 1px solid #7dd3fc;
  border-radius: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.btn-download:hover { background: #e0f2fe; border-color: #38bdf8; }
.raw-sum-table td.l,
.raw-detail-table td.l { text-align: left; max-width: 200px; }
.raw-pager {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  margin: 0 0 10px;
  font-size: 13px;
}
.raw-page-btn { padding: 4px 12px; font-size: 12px; }
.raw-warn { color: #dc2626; font-weight: 600; }

/* ── 人员编制 Tab（对齐源报表清晰度） ── */
.panel[data-tab="dept"] {
  background: #f7f9fc;
  padding: 28px 32px 40px;
}
.panel[data-tab="dept"] .dept-zone {
  max-width: 100%;
}
.panel[data-tab="dept"] .dept-page-title {
  margin: 0 0 8px;
  font-size: 22px;
  font-weight: 800;
  color: #111827;
  letter-spacing: 0.01em;
}
.panel[data-tab="dept"] .dept-page-meta {
  margin: 0 0 20px;
  font-size: 14px;
  color: #4b5563;
  line-height: 1.5;
}
.panel[data-tab="dept"] .dept-page-meta a {
  color: #0f4c81;
  font-weight: 700;
  text-decoration: none;
}
.panel[data-tab="dept"] .dept-page-meta a:hover { text-decoration: underline; }
.panel[data-tab="dept"] .kpi-grid {
  margin-bottom: 20px;
}
.panel[data-tab="dept"] .kpi-tile {
  background: #fff;
  border: 1px solid #e5e7eb;
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.06);
}
.panel[data-tab="dept"] .kpi-tile-label {
  font-size: 13px;
  font-weight: 700;
  color: #4b5563;
}
.panel[data-tab="dept"] .kpi-tile-value {
  font-size: 26px;
  font-weight: 800;
  color: #111827;
}
.panel[data-tab="dept"] .kpi-tile.is-highlight .kpi-tile-value {
  color: #0f4c81;
}
.panel[data-tab="dept"] .kpi-tile-foot {
  font-size: 12px;
  color: #6b7280;
}
.dept-table-wrap {
  overflow-x: auto;
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 8px 28px rgba(15, 23, 42, 0.08);
}
.dept-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 14px;
  min-width: 1280px;
  color: #1f2937;
}
.dept-table th,
.dept-table td {
  padding: 10px 12px;
  text-align: center;
  white-space: nowrap;
  border-right: 1px solid #e5e7eb;
  border-bottom: 1px solid #e5e7eb;
}
.dept-table thead th:last-child,
.dept-table tbody td:last-child,
.dept-table tfoot td:last-child {
  border-right: none;
}
.dept-table th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: #f3f4f6;
  color: #111827;
  font-weight: 700;
  font-size: 14px;
}
.dept-table tbody tr:nth-child(even) { background: #fafafa; }
.dept-table tbody tr:hover { background: #eef6ff; }
.dept-table .dept-cat,
.dept-table .dept-group {
  text-align: left;
  font-weight: 600;
  color: #1f2937;
}
.dept-table .dept-group { font-weight: 700; }
.dept-table .dept-count {
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: #0f4c81;
  cursor: help;
}
.dept-table .dept-count-strong {
  font-weight: 800;
  color: #111827;
}
.dept-table .dept-count-zero {
  color: #9ca3af;
  font-weight: 500;
  cursor: default;
}
.dept-table .dept-ratio {
  font-weight: 600;
  color: #374151;
}
.dept-table tfoot .dept-total td {
  background: #eff6ff;
  font-weight: 700;
  color: #111827;
  border-top: 2px solid #bfdbfe;
}
.dept-name-tooltip {
  position: fixed;
  display: none;
  max-width: 420px;
  max-height: 580px;
  overflow: auto;
  padding: 10px 12px;
  background: rgba(17, 24, 39, 0.96);
  color: #f9fafb;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.45;
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.28);
  z-index: 9999;
  pointer-events: none;
}
.dept-name-tooltip .dept-tip-title {
  margin-bottom: 8px;
  font-weight: 700;
  color: #93c5fd;
}

/* ── Panel ── */
.panel {
  display: none;
  padding: 28px 40px 44px;
  background: linear-gradient(180deg, #f9fafb 0%, #fff 160px);
}
.panel.active { display: block; }

/* ── Callout / Note ── */
.data-note, .lead {
  font-size: 14px;
  color: var(--text-muted);
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-left: 4px solid var(--brand);
  border-radius: var(--radius-sm);
  padding: 16px 18px;
  margin-bottom: 22px;
  line-height: 1.75;
  box-shadow: none;
}
.data-note b, .lead b { color: var(--brand); font-weight: 800; }
.data-note strong, .lead strong { color: #0c4a6e; font-weight: 800; }

/* ── Section / Part（对齐 Gate-RDJ 全局美化） ── */
.part {
  margin: 0 0 24px;
  padding: 18px 20px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
}
.part-title,
.rdj-part .part-title {
  font-size: 15px;
  font-weight: 800;
  color: var(--text-strong);
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 2px solid #e2e8f0;
  letter-spacing: 0.01em;
  display: block;
}
.part-title::before { display: none; }

details.section-group {
  margin-bottom: 20px;
  border-radius: var(--radius-md);
}
details.section-group > summary.group-title {
  font-size: 16px;
  font-weight: 800;
  color: var(--text-strong);
  margin: 0 0 12px;
  padding: 12px 0;
  border-bottom: 2px solid #cbd5e1;
  letter-spacing: 0.02em;
  cursor: pointer;
  list-style: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  user-select: none;
}
details.section-group > summary.group-title::-webkit-details-marker { display: none; }
details.section-group > summary.group-title::marker { display: none; content: ''; }
details.section-group > summary.group-title::after {
  content: '▲ 收起';
  font-size: 11px;
  font-weight: 500;
  color: #94a3b8;
  background: #f1f5f9;
  padding: 4px 14px;
  border-radius: 14px;
  flex-shrink: 0;
  margin-left: 12px;
}
details.section-group:not([open]) > summary.group-title::after {
  content: '▼ 展开';
  color: #0369a1;
  background: #e0f2fe;
}
details.section-group:not([open]) > summary.group-title {
  border-bottom-color: #e2e8f0;
  color: #64748b;
}
details.section-group[open] > summary.group-title { margin-bottom: 14px; }
details.section-group.rdj-section { margin-top: 0; }
details.section-group .rdj-delivery-zone { padding: 0; }

/* ── 面板阅读动线 ── */
.panel-intro {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  margin-bottom: 20px;
  padding: 14px 18px;
  background: #fff;
  border: 1px dashed #d1d5db;
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: #6b7280;
  line-height: 1.7;
}
.panel-intro-label {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 800;
  color: var(--brand);
  background: var(--brand-pale);
  padding: 4px 10px;
  border-radius: 6px;
  letter-spacing: 0.04em;
  margin-top: 2px;
}
.panel-intro ol {
  margin: 0;
  padding-left: 1.25rem;
}
.panel-intro li { margin: 3px 0; }
.panel-stack {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
details.panel-section {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 4px 16px 14px;
  box-shadow: var(--shadow-sm);
}
details.panel-section > summary.group-title {
  margin-top: 4px;
}
.section-group-body {
  padding: 0 2px 4px;
}
.section-group-body .part-desc {
  margin: 0 0 12px;
  font-size: 12px;
  color: #64748b;
  line-height: 1.6;
}
.section-group-body .ov-grid { margin-bottom: 0; }
.insight-box {
  margin-top: 4px;
  border-left-color: #059669;
  border-color: #bbf7d0;
  background: linear-gradient(135deg, #f0fdf4 0%, #fff 55%);
}

/* 分组内轻量卡片（避免 part 套 part 双边框） */
.block-card {
  background: #f8fafc;
  border: 1px solid #e8eef4;
  border-radius: var(--radius-sm);
  padding: 14px 16px;
  margin-bottom: 14px;
}
.block-card:last-child { margin-bottom: 0; }
.block-card-title {
  font-size: 13px;
  font-weight: 700;
  color: #334155;
  margin-bottom: 10px;
}
.block-card-desc {
  font-size: 12px;
  color: #64748b;
  margin: -4px 0 10px;
  line-height: 1.55;
}
.section-group-body .chart-row { margin-bottom: 0; }
.section-group-body .chart-row .block-card { margin-bottom: 0; }
.rt-drill-section { margin-top: 12px; background: #fff; }

/* ── 总览 · 需求明细（内嵌筛选 + 明细表） ── */
.ov-dmd-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px 16px;
  margin: 0 0 12px;
  padding: 10px 14px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}
.ov-dmd-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 14px;
}
.ov-dmd-field {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}
.ov-dmd-label {
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  white-space: nowrap;
}
.ov-dmd-select {
  min-width: 148px;
  max-width: 220px;
  padding: 7px 28px 7px 10px;
  font-size: 13px;
  color: #0f172a;
  background: #f8fafc url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2364748b' d='M3 4.5L6 7.5L9 4.5'/%3E%3C/svg%3E") no-repeat right 10px center;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  appearance: none;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.ov-dmd-select:hover { border-color: #94a3b8; }
.ov-dmd-select:focus {
  outline: none;
  border-color: #38bdf8;
  box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.2);
}
.ov-dmd-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ov-dmd-btn {
  padding: 7px 14px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 8px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.ov-dmd-btn--ghost {
  color: #475569;
  background: #f8fafc;
  border-color: #e2e8f0;
}
.ov-dmd-btn--ghost:hover { background: #f1f5f9; border-color: #cbd5e1; }
.ov-dmd-btn--primary {
  color: #fff;
  background: #0369a1;
  border-color: #0369a1;
}
.ov-dmd-btn--primary:hover { background: #0284c7; }
.ov-dmd-stats {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 12px;
  margin: 0 0 10px;
  padding: 8px 12px;
  background: linear-gradient(90deg, #f0f9ff 0%, #f8fafc 100%);
  border-radius: 8px;
  font-size: 12px;
  color: #475569;
}
.ov-dmd-stats-row { display: flex; flex-wrap: wrap; gap: 12px 16px; }
.ov-dmd-stat em { font-style: normal; font-weight: 700; color: #0c4a6e; }
.ov-dmd-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.ov-dmd-chip {
  padding: 2px 10px;
  font-size: 11px;
  font-weight: 600;
  color: #0369a1;
  background: #e0f2fe;
  border-radius: 999px;
}
.ov-dmd-chip--all { color: #64748b; background: #f1f5f9; }
.ov-dmd-pager {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 0 0 8px;
  font-size: 12px;
  color: #64748b;
}
.ov-dmd-pager-info b { color: #0c4a6e; }
.ov-dmd-detail-wrap { margin-bottom: 8px; }
.ov-dmd-foot { margin: 8px 0 0; font-size: 11px; }

/* 需求明细 · 按月折叠（默认收起摘要条） */
.dmd-month-stack { display: flex; flex-direction: column; gap: 8px; }
.dmd-month-fold {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #fff;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.05);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.dmd-month-fold:hover { border-color: #cbd5e1; }
.dmd-month-fold[open] {
  border-color: #bae6fd;
  box-shadow: 0 2px 8px rgba(3, 105, 161, 0.08);
}
.dmd-month-fold > summary.dmd-month-summary {
  display: grid;
  grid-template-columns: minmax(120px, 1fr) auto;
  align-items: center;
  gap: 12px 20px;
  padding: 11px 16px;
  min-height: 44px;
  cursor: pointer;
  list-style: none;
  user-select: none;
  background: #fff;
  border-bottom: 1px solid transparent;
  transition: background 0.15s, border-color 0.15s;
}
.dmd-month-fold > summary.dmd-month-summary::-webkit-details-marker { display: none; }
.dmd-month-fold > summary.dmd-month-summary::marker { display: none; }
.dmd-month-fold > summary.dmd-month-summary:hover { background: #f8fafc; }
.dmd-month-fold[open] > summary.dmd-month-summary {
  border-bottom-color: #e2e8f0;
  background: linear-gradient(180deg, #f8fafc 0%, #fff 100%);
}
.dmd-month-label {
  font-size: 13px;
  font-weight: 700;
  color: #334155;
  letter-spacing: 0.01em;
  padding-left: 20px;
  position: relative;
  white-space: nowrap;
}
.dmd-month-label::before {
  content: '▸';
  position: absolute;
  left: 0;
  top: 0;
  font-size: 14px;
  line-height: 1.2;
  color: #94a3b8;
  transition: transform 0.2s, color 0.15s;
}
.dmd-month-fold[open] .dmd-month-label::before {
  transform: rotate(90deg);
  color: #0369a1;
}
.dmd-month-fold[open] .dmd-month-label { color: #0c4a6e; }
.dmd-month-kpi {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 4px 16px;
  font-size: 12px;
  color: #64748b;
  font-variant-numeric: tabular-nums;
}
.dmd-month-kpi-item b { color: #0369a1; font-weight: 700; }
.dmd-month-body {
  padding: 0;
  overflow-x: auto;
}
.dmd-month-table { margin: 0; border: none; border-radius: 0; }
.dmd-month-table thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: #0e7490;
}
.dmd-month-table tbody tr:nth-child(even) { background: #f8fafc; }
.dmd-month-table tbody tr:hover { background: #eff6ff; }
.dmd-month-subtotal {
  background: #f0f9ff !important;
  font-weight: 600;
}
.dmd-month-subtotal td { border-top: 2px solid #bae6fd; }
.dmd-month-subnote {
  display: block;
  font-size: 11px;
  font-weight: 400;
  color: #64748b;
  margin-top: 2px;
}
.dmd-month-grand {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 16px;
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid #bae6fd;
  background: linear-gradient(135deg, #eff6ff, #f0f9ff);
}
.dmd-month-grand-label {
  font-size: 13px;
  font-weight: 700;
  color: #0369a1;
}
.dmd-month-pager-hint {
  display: block;
  font-size: 12px;
  color: #64748b;
  padding: 6px 0 2px;
  line-height: 1.5;
}
.dmd-month-pager-hint b { color: #0369a1; font-weight: 600; }
.raw-pager .dmd-month-pager-hint,
.ov-dmd-pager .dmd-month-pager-hint { margin: 0 0 6px; }

.rt-drill-block .drill-empty {
  padding: 24px;
  text-align: center;
  color: #94a3b8;
  font-size: 13px;
}

/* 部门四源表 · 表头固定 + 汇总行 */
.rt-table-wrap table.rt-dept-table thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--table-head);
  box-shadow: 0 2px 0 rgba(15, 23, 42, 0.06);
}
table.rt-dept-table tfoot tr.rt-dept-total td {
  background: #eff6ff;
  border-top: 2px solid #93c5fd;
  padding-top: 12px;
  padding-bottom: 12px;
  vertical-align: top;
}
table.rt-dept-table tfoot .rt-total-note {
  font-size: 11px;
  font-weight: 500;
  color: #64748b;
  margin-top: 4px;
  line-height: 1.45;
}
table.rt-dept-table tfoot strong { color: #0c4a6e; }

/* ── 主站核心公式说明块 ── */
.formula-core-box {
  margin: 12px 0 16px;
  padding: 16px 18px;
  background: #fff;
  border: 1px solid #e2e8f0;
  border-left: 4px solid var(--brand);
  border-radius: var(--radius-sm);
  font-size: 13px;
  line-height: 1.6;
  color: #374151;
  box-shadow: var(--shadow-sm);
}
.formula-core-box--compact { padding: 10px 14px; font-size: 12px; }
.formula-core-title { margin: 0 0 10px; color: var(--brand); font-size: 14px; font-weight: 800; }
.formula-core-box--compact .formula-core-title { margin-bottom: 8px; font-size: 13px; }
.formula-core-list { margin: 0; padding-left: 1.25rem; }
.formula-core-list li { margin: 6px 0; }
.formula-core-list code {
  font-size: 12px;
  background: #e0f2fe;
  padding: 1px 5px;
  border-radius: 4px;
}
.formula-core-line { margin: 4px 0; }
.formula-core-foot { margin: 10px 0 0; font-size: 12px; }

/* ── 页面底部公式附录（默认收起） ── */
.formula-appendix {
  margin: 0;
  padding: 8px 40px 32px;
  background: #f9fafb;
  border-top: 1px solid var(--border);
}
.formula-appendix > summary.group-title {
  font-size: 15px;
  margin-bottom: 0;
}
.formula-appendix[open] > summary.group-title {
  margin-bottom: 16px;
}
.gl-table-wrap {
  overflow-x: auto;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
}
.gl-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  min-width: 880px;
}
.gl-table thead th {
  background: #0e7490;
  color: #fff;
  font-weight: 700;
  padding: 11px 14px;
  text-align: left;
  white-space: nowrap;
  border-right: 1px solid rgba(255, 255, 255, 0.15);
}
.gl-table thead th:last-child { border-right: none; }
.gl-table tbody td {
  padding: 10px 14px;
  border-bottom: 1px solid #e5e7eb;
  border-right: 1px solid #e5e7eb;
  vertical-align: top;
  line-height: 1.55;
  color: #334155;
}
.gl-table tbody td:last-child { border-right: none; }
.gl-table tbody tr:nth-child(even) { background: #f8fafc; }
.gl-table tbody tr:hover { background: #f0f9ff; }
.gl-table .gl-mod {
  font-weight: 800;
  color: #0c4a6e;
  background: #e0f2fe;
  text-align: center;
  vertical-align: middle;
  min-width: 108px;
  font-size: 12px;
  line-height: 1.4;
}
.gl-table .gl-cat {
  font-weight: 700;
  color: #0369a1;
  background: #f0f9ff;
  text-align: center;
  vertical-align: middle;
  min-width: 72px;
  writing-mode: vertical-lr;
  text-orientation: mixed;
  letter-spacing: 0.06em;
  font-size: 12px;
}
.gl-table .gl-name {
  font-weight: 700;
  color: #0f172a;
  white-space: nowrap;
  min-width: 140px;
}
.gl-table .gl-desc {
  font-weight: 400;
  color: #334155;
}
.gl-table .gl-desc code {
  background: #e0f2fe;
  padding: 1px 5px;
  border-radius: 4px;
  color: #0c4a6e;
  font-size: 12px;
}
.gl-table .gl-desc b { color: #0c4a6e; }
.gl-footnote {
  margin: 14px 0 0;
  padding: 12px 14px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 12px;
  color: #64748b;
  line-height: 1.65;
}
.gl-footnote a { color: #0369a1; font-weight: 600; }
.gl-footnote b { color: #0c4a6e; }
.part-desc {
  color: var(--text-faint);
  font-size: 0.85em;
  margin: 0 0 10px;
  line-height: 1.45;
}
.subsection-title {
  font-size: 0.95em;
  font-weight: 600;
  color: var(--brand);
  margin: 14px 0 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border-accent);
}

/* ── KPI 指标条（横向卡片，数值只出现一次） ── */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 14px;
  margin-bottom: 24px;
}
@media (min-width: 1200px) {
  .kpi-grid:has(.kpi-tile:nth-child(6):last-child) {
    grid-template-columns: repeat(6, 1fr);
  }
  .kpi-grid:has(.kpi-tile:nth-child(5):last-child):not(:has(.kpi-tile:nth-child(6))) {
    grid-template-columns: repeat(5, 1fr);
  }
}
.kpi-tile {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 0;
  padding: 16px 18px 16px 20px;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  transition: box-shadow 0.2s, border-color 0.2s, transform 0.15s;
  overflow: hidden;
}
.kpi-tile::before {
  content: '';
  position: absolute;
  left: 0;
  top: 10px;
  bottom: 10px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: color-mix(in srgb, var(--kpi-accent, #0369a1) 70%, #94a3b8);
}
.kpi-tile:hover {
  box-shadow: var(--shadow-md);
  border-color: #cbd5e1;
  transform: translateY(-1px);
}
.kpi-tile.is-highlight {
  border-color: color-mix(in srgb, var(--kpi-accent, #0369a1) 35%, #e2e8f0);
  background: linear-gradient(135deg, #fff 0%, color-mix(in srgb, var(--kpi-accent) 5%, #fff) 100%);
}
.kpi-tile-icon { display: none; }
.kpi-tile-body { flex: 1; min-width: 0; text-align: left; }
.kpi-tile-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-faint);
  margin-bottom: 4px;
  letter-spacing: 0.02em;
}
.kpi-tile-value {
  font-size: 24px;
  font-weight: 800;
  color: var(--text-strong);
  font-variant-numeric: tabular-nums;
  line-height: 1.15;
  letter-spacing: -0.02em;
}
.kpi-tile.is-highlight .kpi-tile-value {
  color: var(--kpi-accent, #0369a1);
}
.kpi-tile-foot {
  margin-top: 6px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-faint);
}
/* 兼容旧类名（若残留） */
.summary-cards { display: none; }

/* ── Charts ── */
.chart-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 12px;
}
.chart-row.single { grid-template-columns: 1fr; }
@media (max-width: 960px) { .chart-row { grid-template-columns: 1fr; } }

.chart-box {
  background: #fff;
  padding: 16px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  min-height: 280px;
  box-shadow: var(--shadow-sm);
}
.chart-box:hover { box-shadow: var(--shadow-md); }
.chart-box.wide { grid-column: 1 / -1; min-height: 360px; }
.chart-box .ec {
  width: 100%;
  min-height: 200px;
}
.chart-title {
  font-size: 0.85em;
  font-weight: 600;
  color: #0c4a6e;
  margin-bottom: 8px;
  text-align: center;
  letter-spacing: 0.01em;
}
.chart-caption {
  font-size: 0.85em;
  color: var(--text-faint);
  margin-bottom: 8px;
  line-height: 1.45;
  text-align: center;
}

/* ── Tables（Gate-RDJ：#0e7490 表头 + 无模块内滚动） ── */
.detail-table, .tbl-wrap, .tbl-scroll, .rt-table-wrap {
  padding: 12px;
  margin-bottom: 12px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: #fff;
  overflow: visible;
  max-height: none;
}
.detail-table:last-child, .tbl-wrap:last-child { margin-bottom: 0; }
.tbl-wrap { margin-top: 0; padding: 0; }

table, table.data, table.dense, table.sum-table, table.data-table, table.biz-pct {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
  border-radius: 6px;
}
table thead { position: static; }
th, td {
  border: 1px solid #e5e7eb;
  padding: 8px 10px;
  text-align: center;
  color: #374151;
  vertical-align: middle;
}
th {
  background: var(--table-head);
  color: #fff;
  font-weight: 700;
  font-size: 11px;
  letter-spacing: 0.03em;
  white-space: nowrap;
}
tbody tr:nth-child(even) { background: #f9fafb; }
tbody tr:hover { background: #eef6fc; }
td.l {
  text-align: left;
  font-weight: 600;
  color: var(--text-strong);
  word-break: break-word;
  line-height: 1.45;
}
table.dense th, table.dense td { font-size: 11px; padding: 6px 8px; }
table.biz-pct th, table.biz-pct td { font-size: 11px; padding: 5px 6px; }
td.ch { font-size: 11px; color: var(--text-muted); white-space: nowrap; }
.note {
  font-size: 0.85em;
  color: var(--text-muted);
  margin-top: 8px;
  line-height: 1.5;
  padding: 8px 12px;
  background: var(--brand-bg);
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-accent);
}
.rt-num {
  font-variant-numeric: tabular-nums;
  color: var(--text-strong);
  font-weight: 600;
}

/* ── Insights / Lists ── */
.pts {
  margin: 0;
  padding-left: 1.1rem;
  list-style: disc;
  font-size: 0.9em;
  color: var(--text-muted);
  line-height: 1.75;
}
.pts li { margin: 6px 0; padding: 0; background: none; border: none; }
.pts li::before { display: none; }

.conclusion-box {
  background: #fff;
  border: 1px solid #bbf7d0;
  border-left: 4px solid #22c55e;
  border-radius: var(--radius-md);
  padding: 16px 18px;
  margin-bottom: 20px;
  box-shadow: var(--shadow-sm);
}
.conclusion-title {
  font-size: 0.95em;
  font-weight: 700;
  color: #166534;
  margin-bottom: 8px;
}

/* ── Brief panels ── */
.brief-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 20px;
}
@media (max-width: 900px) { .brief-grid { grid-template-columns: 1fr; } }
.panel-blue {
  background: linear-gradient(135deg, #eff6ff 0%, #f8fafc 100%);
  border: 1px solid #bfdbfe;
  border-radius: var(--radius-md);
  padding: 18px 20px;
}
.panel-amber {
  background: linear-gradient(135deg, #fffbeb 0%, #fefce8 100%);
  border: 1px solid #fde68a;
  border-radius: var(--radius-md);
  padding: 18px 20px;
}
.panel-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 10px;
}
.panel-amber .panel-title { color: #92400e; }
.panel-ul {
  margin: 0;
  padding-left: 1.2rem;
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.75;
}

/* ── Sub-tabs ── */
.subtabs {
  display: inline-flex;
  gap: 4px;
  margin-bottom: 20px;
  padding: 4px;
  background: #f1f5f9;
  border-radius: 999px;
  border: 1px solid var(--border);
}
.subtab {
  border: none;
  background: transparent;
  border-radius: 999px;
  padding: 8px 20px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-muted);
  transition: background 0.15s, color 0.15s;
}
.subtab:hover { color: var(--brand); background: #fff; }
.subtab.active {
  background: #fff;
  color: var(--brand);
  box-shadow: var(--shadow-sm);
}
.subpanel { display: none; }
.subpanel.active {
  display: block;
  padding-top: 4px;
  border-top: 1px solid #f1f5f9;
  margin-top: 4px;
}

/* ── RDJ 交付效能块（对齐 Gate-RDJ 时间维 part 结构） ── */
.rdj-delivery-zone { margin-top: 0; }
.rdj-part {
  margin: 0 0 20px;
  padding: 0;
  background: transparent;
  border: none;
  box-shadow: none;
}
.rdj-part:last-child { margin-bottom: 0; }
.rdj-delivery-zone .part {
  background: transparent;
  border: none;
  box-shadow: none;
  padding: 0;
  margin-bottom: 16px;
}

/* 需求交付周期 — delivery-cycle-wrap */
.delivery-cycle-wrap {
  margin: 0;
  padding: 20px;
  background: #fff;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  overflow-x: auto;
}
.delivery-cycle-wrap h4 {
  text-align: left;
  color: var(--text-strong);
  font-size: 15px;
  margin-bottom: 14px;
  font-weight: 800;
}
.dc-kpi-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
  margin: 0 0 16px;
}
.dc-kpi-badge {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: #f8fafc;
}
.dc-kpi-blue { border-left: 3px solid #0ea5e9; }
.dc-kpi-amber { border-left: 3px solid #f59e0b; }
.dc-kpi-ico {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
  border-radius: 10px;
  background: #fff;
}
.dc-kpi-body { flex: 1; min-width: 0; }
.dc-kpi-lbl { font-size: 12px; font-weight: 600; color: var(--text-faint); margin-bottom: 4px; }
.dc-kpi-num {
  font-size: 22px;
  font-weight: 800;
  color: var(--text-strong);
  font-variant-numeric: tabular-nums;
  line-height: 1.15;
}
.dc-kpi-unit { font-size: 13px; font-weight: 600; color: var(--text-faint); margin-left: 2px; }
.dc-kpi-sub { font-size: 11px; color: var(--text-faint); margin-top: 4px; font-weight: 500; }

.delivery-cycle-wrap .dc-flow {
  display: flex;
  align-items: center;
  flex-wrap: nowrap;
  gap: 0;
  min-width: min-content;
  margin-bottom: 16px;
  justify-content: center;
}
.delivery-cycle-wrap .dc-node {
  flex: 0 0 auto;
  min-width: 76px;
  padding: 8px 6px;
  text-align: center;
  font-size: 0.75em;
  border: 2px solid #38bdf8;
  background: #fff;
  color: #0c4a6e;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}
.delivery-cycle-wrap .dc-node.start-end {
  background: #e0f2fe;
  color: #0369a1;
  border-color: #7dd3fc;
}
.delivery-cycle-wrap .dc-node .dc-name {
  font-weight: 700;
  display: block;
  margin-bottom: 4px;
  font-size: 0.9em;
}
.delivery-cycle-wrap .dc-node .dc-metric {
  display: block;
  font-size: 0.75em;
  color: #6b7280;
  line-height: 1.3;
}
.delivery-cycle-wrap .dc-node .dc-metric.dc-days { color: #0369a1; font-weight: 600; }
.delivery-cycle-wrap .dc-node .dc-metric.dc-ratio { color: #b45309; font-weight: 600; font-size: 0.8em; }
.delivery-cycle-wrap .dc-arrow {
  flex: 0 0 20px;
  text-align: center;
  color: #38bdf8;
  font-size: 1em;
  font-weight: 700;
}
.delivery-cycle-wrap .flow-legend {
  font-size: 0.8em;
  color: #6b7280;
  margin: 6px 0 12px;
  text-align: center;
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 6px;
}
.dc-stack-wrap { margin-bottom: 16px; }
.dc-stack-title {
  font-size: 0.85em;
  font-weight: 600;
  color: #0369a1;
  margin-bottom: 8px;
  text-align: center;
}
.dc-stack-bar {
  display: flex;
  height: 36px;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  min-width: 360px;
}
.dc-stack-seg {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  color: #fff;
  font-size: 0.65em;
  font-weight: 700;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
  padding: 2px 3px;
  line-height: 1.2;
  min-width: 2%;
}
.dc-stack-seg .seg-name { font-size: 1em; white-space: nowrap; }
.dc-stack-seg .seg-pct { opacity: 0.95; }
.dc-stack-legend {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px 16px;
  margin-top: 10px;
  font-size: 0.75em;
  color: #4b5563;
}
.dc-stack-legend span { display: inline-flex; align-items: center; gap: 5px; }
.dc-stack-legend .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dc-phase-tips {
  margin-top: 14px;
  padding: 12px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}
.dc-phase-tips table { width: 100%; font-size: 0.8em; border-radius: 6px; overflow: hidden; }
.dc-phase-tips th {
  background: #0e7490;
  color: #fff;
  padding: 6px 8px;
  text-align: left;
  font-weight: 600;
}
.dc-phase-tips td {
  padding: 6px 8px;
  border-bottom: 1px solid #e2e8f0;
  vertical-align: top;
  color: #334155;
  text-align: center;
}
.dc-phase-tips tr:nth-child(even) { background: #f8fafc; }
.dc-phase-tips .col-phase { width: 72px; font-weight: 600; color: #0369a1; text-align: left; }
.dc-phase-tips .col-ratio { font-weight: 600; color: #b45309; }

.dc-caliber-bar {
  margin: 0 0 12px;
  padding: 8px 12px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 8px;
  font-size: 11px;
  color: #92400e;
  line-height: 1.55;
}
.dc-unified-flow {
  display: flex;
  align-items: stretch;
  gap: 0;
  overflow-x: auto;
  padding: 8px 0 12px;
  margin-bottom: 8px;
}
.dc-flow-end {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}
.dc-end-inner {
  text-align: center;
  padding: 10px 14px;
  border-radius: 12px;
  font-weight: 700;
  font-size: 12px;
  line-height: 1.35;
  min-width: 52px;
}
.dc-flow-start .dc-end-inner {
  background: linear-gradient(180deg, #e0f2fe, #bae6fd);
  color: #0c4a6e;
  box-shadow: 0 2px 8px rgba(14, 165, 233, 0.15);
}
.dc-flow-done .dc-end-inner {
  background: linear-gradient(180deg, #dcfce7, #bbf7d0);
  color: #166534;
  box-shadow: 0 2px 8px rgba(22, 163, 74, 0.15);
}
.dc-flow-arrow {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}
.dc-stage-card {
  flex: 1;
  min-width: 100px;
  text-align: center;
  padding: 14px 10px 12px;
  background: #fff;
  border-radius: 12px;
  border-top: 4px solid #0ea5e9;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.06);
}
.dc-stage-title {
  font-weight: 700;
  font-size: 13px;
  letter-spacing: 0.5px;
  margin-bottom: 10px;
}
.dc-stage-block {
  border-radius: 8px;
  padding: 8px 6px;
  margin-bottom: 8px;
}
.dc-block-sched {
  background: linear-gradient(135deg, #f0f9ff, #e0f2fe);
}
.dc-block-effort {
  background: linear-gradient(135deg, #fef3c7, #fde68a);
}
.dc-block-lbl {
  font-size: 9px;
  font-weight: 600;
  margin-bottom: 2px;
}
.dc-block-sched .dc-block-lbl { color: #0369a1; }
.dc-block-effort .dc-block-lbl { color: #92400e; }
.dc-block-val {
  font-size: 24px;
  font-weight: 800;
  color: #0c4a6e;
  line-height: 1;
}
.dc-block-val.dc-val-sm { font-size: 18px; color: #78350f; }
.dc-block-val span {
  font-size: 11px;
  font-weight: 500;
  color: #64748b;
}
.dc-block-effort .dc-block-val span { color: #92400e; }
.dc-block-sub {
  font-size: 9px;
  color: #64748b;
  margin-top: 2px;
}
.dc-block-effort .dc-block-sub { color: #92400e; }
.dc-total-eff {
  color: #a16207 !important;
  margin-left: 4px;
}
.dc-act-track {
  border-radius: 4px;
  height: 6px;
  overflow: hidden;
  margin-top: 4px;
}
.dc-act-fill {
  height: 100%;
  border-radius: 4px;
}
.dc-act-lbl {
  font-size: 10px;
  font-weight: 600;
  margin-top: 3px;
}
.dc-two-bars {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  margin: 16px 0;
  align-items: start;
}
@media (max-width: 768px) {
  .dc-two-bars { grid-template-columns: 1fr; }
}
.dc-bar-panel {
  border-radius: 12px;
  padding: 14px 16px;
}
.dc-panel-sched {
  background: #f0f9ff;
  border: 1px solid #bae6fd;
}
.dc-panel-effort {
  background: #fef3c7;
  border: 1px solid #fde68a;
}
.dc-bar-panel-title {
  font-weight: 800;
  font-size: 13px;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.dc-panel-sched .dc-bar-panel-title { color: #0369a1; }
.dc-panel-effort .dc-bar-panel-title { color: #92400e; }
.dc-seg-row {
  display: flex;
  height: 56px;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}
.dc-seg-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  text-align: center;
  line-height: 1.25;
  padding: 2px 4px;
  min-width: 0;
  overflow: hidden;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
}

.quadrant-conclusion {
  margin: 16px 0 8px;
  padding: 16px 18px;
  background: linear-gradient(135deg, #f8fafc, #f0f9ff);
  border-radius: 10px;
  border: 1px solid #bae6fd;
  font-size: 12.5px;
  color: #334155;
  line-height: 1.9;
}
.quad-concl-title {
  font-weight: 700;
  font-size: 14px;
  color: #0c4a6e;
  margin-bottom: 6px;
}
.quad-concl-sub {
  margin: 0 0 10px;
  font-size: 11px;
  color: #64748b;
}
.quad-concl-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 20px;
}
@media (max-width: 720px) {
  .quad-concl-grid { grid-template-columns: 1fr; }
}
.quad-hint {
  font-size: 11px;
  color: #64748b;
}
.quad-concl-findings {
  margin-top: 12px;
  border-top: 1px solid #e2e8f0;
  padding-top: 10px;
}
.chart-row-quad {
  align-items: stretch;
}
.chart-box-quad {
  overflow: visible;
  min-height: 600px;
}
.chart-box-quad .ec {
  overflow: visible;
}

/* 彩色内容盒（测试占比 / 业务线表 / 月度指标） */
.rdj-box {
  margin-top: 16px;
  padding: 18px 20px;
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
}
.rdj-box-red {
  background: linear-gradient(135deg, #fef2f2 0%, #fff 100%);
  border: 2px solid #fca5a5;
}
.rdj-box-cyan {
  background: linear-gradient(135deg, #f0f9ff 0%, #fff 100%);
  border: 2px solid #7dd3fc;
}
.rdj-box-white {
  background: #fff;
  border: 1px solid #e2e8f0;
}
.rdj-box-h {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.rdj-emoji { font-size: 16px; }
.rdj-box-title {
  font-weight: 700;
  color: #0369a1;
  font-size: 14px;
}
.rdj-title-red { color: #b91c1c; }
.rdj-box-hint {
  font-size: 11px;
  color: #64748b;
  margin-left: auto;
}
@media (max-width: 720px) { .rdj-box-hint { margin-left: 0; width: 100%; } }
.rdj-box .ec { width: 100%; display: block; }

/* 四象限说明 + caption */
.quadrant-info {
  margin-bottom: 10px;
  padding: 10px 14px;
  background: #f0f9ff;
  border-radius: 8px;
  border: 1px solid #bae6fd;
  font-size: 12px;
  color: #334155;
  line-height: 1.7;
}
.quadrant-info-sub { font-size: 11px; color: #64748b; }
.rdj-part .chart-box {
  background: #fff;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}
.rdj-part .chart-title {
  font-size: 0.85em;
  font-weight: 600;
  color: #0c4a6e;
  margin-bottom: 8px;
  text-align: center;
}
.chart-caption.quad-cap {
  margin: 10px 0 0;
  padding: 8px 12px;
  background: #f8fafc;
  border-radius: 6px;
  font-size: 11px;
  color: #475569;
  line-height: 1.6;
  border: 1px solid #e2e8f0;
  text-align: left;
}

/* 月度交付核心指标 2×2 */
.rdj-monthly-wrap { margin-top: 24px; }
.monthly-metrics-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
  margin-bottom: 10px;
}
@media (max-width: 900px) { .monthly-metrics-grid { grid-template-columns: 1fr; } }
.monthly-chart-tile {
  background: #fff;
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  padding: 8px;
  min-height: 320px;
}
.monthly-metrics-table { margin-top: 10px; padding: 0; }
.table-caption {
  margin: 8px 0 0;
  color: #64748b;
  font-size: 0.85em;
  line-height: 1.5;
}
.biz-pct-wrap { padding: 0; border: none; background: transparent; overflow-x: auto; }
.biz-pct-wrap table.biz-pct { font-size: 11px; }
.biz-pct-wrap table.biz-pct th,
.biz-pct-wrap table.biz-pct td { padding: 5px 6px; }

/* 团队内月度环比 */
.team-mom-wrap { margin-top: 16px; }
.team-mom-summary {
  margin-top: 14px;
  padding: 0;
  border: none;
  background: transparent;
  overflow-x: auto;
}
.team-mom-summary table {
  font-size: 12px;
  width: 100%;
}
.team-mom-summary th,
.team-mom-summary td { padding: 6px 10px; }
.team-mom-summary td.l { text-align: left; font-weight: 600; max-width: 200px; }
.team-mom-details {
  margin-top: 12px;
  border: 1px solid #e2e8f0;
  border-radius: var(--radius-sm);
  background: #f8fafc;
  padding: 10px 12px;
}
.team-mom-details summary {
  cursor: pointer;
  font-size: 13px;
  font-weight: 700;
  color: #0369a1;
  user-select: none;
}
.team-mom-pivot-wrap {
  margin-top: 10px;
  overflow: auto;
  max-width: 100%;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #fff;
}
table.team-mom-pivot {
  width: max-content;
  min-width: 100%;
  font-size: 11px;
  border-collapse: separate;
  border-spacing: 0;
}
table.team-mom-pivot th,
table.team-mom-pivot td {
  padding: 6px 10px;
  text-align: center;
  border-bottom: 1px solid #e8eef4;
  white-space: nowrap;
}
table.team-mom-pivot thead th {
  background: #f1f5f9;
  font-weight: 600;
  color: #475569;
  position: sticky;
  top: 0;
  z-index: 3;
}
table.team-mom-pivot th.sticky-col,
table.team-mom-pivot td.sticky-col {
  text-align: left;
  position: sticky;
  left: 0;
  z-index: 2;
  background: #fff;
  box-shadow: 4px 0 8px -4px rgba(15, 23, 42, 0.12);
}
table.team-mom-pivot thead th.sticky-col { z-index: 4; background: #f1f5f9; }
table.team-mom-pivot .tp-global-row td.sticky-col { background: #eff6ff; font-weight: 700; }
table.team-mom-pivot .tp-global-row td:not(.sticky-col) { background: #f8fafc; }

@media (max-width: 768px) {
  .delivery-cycle-wrap .dc-flow { flex-wrap: wrap; justify-content: flex-start; }
  .dc-stack-bar { min-width: 260px; }
  .dc-stack-seg { font-size: 0.55em; }
}

/* legacy（其它模块仍可能引用） */
.section-block {
  margin: 0 0 16px;
  padding: 16px;
  background: var(--brand-bg);
  border: 1px solid var(--border-accent);
  border-radius: var(--radius-md);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}
.section-block.section-accent-red {
  background: #fff5f5;
  border-color: #fecaca;
}
.section-h {
  font-size: 1em;
  font-weight: 700;
  color: var(--brand);
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.section-icon {
  display: inline-flex;
  width: 24px;
  height: 24px;
  align-items: center;
  justify-content: center;
  background: var(--brand-pale);
  color: var(--brand);
  border-radius: 6px;
  font-size: 11px;
  font-weight: 800;
}
.inner-card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 12px;
  margin-bottom: 10px;
}
.inner-card:last-child { margin-bottom: 0; }
.grid-metrics { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
@media (max-width: 900px) { .grid-metrics { grid-template-columns: 1fr; } }
.grid-metrics .inner-card:last-child { grid-column: 1 / -1; }

.dc-wrap {
  padding: 16px;
  background: #fff;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
}
.dc-kpis { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 14px; }
.dc-kpi {
  flex: 1;
  min-width: 140px;
  background: #f8fafc;
  border-radius: var(--radius-sm);
  padding: 12px;
  border-left: 4px solid var(--brand-cyan);
}
.dc-kpi-k { font-size: 11px; color: var(--text-faint); font-weight: 600; }
.dc-kpi-v {
  font-size: 1.3em;
  font-weight: 700;
  color: var(--text-strong);
  margin-top: 4px;
  font-variant-numeric: tabular-nums;
}
.dc-flow {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  justify-content: center;
  margin: 12px 0;
}
.dc-node {
  padding: 8px 10px;
  border: 2px solid var(--brand-cyan);
  background: #fff;
  border-radius: var(--radius-sm);
  font-size: 11px;
  text-align: center;
  min-width: 72px;
  color: var(--text-strong);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}
.dc-node.dc-end {
  background: var(--brand-pale);
  border-color: #7dd3fc;
  color: var(--brand);
  font-weight: 700;
}
.dc-nm { display: block; font-weight: 700; color: var(--text-strong); }
.dc-meta { display: block; font-size: 10px; color: var(--text-faint); margin-top: 3px; }
.dc-arrow { color: var(--brand-cyan); font-weight: 700; font-size: 1em; }
.dc-stack {
  display: flex;
  height: 36px;
  border-radius: var(--radius-sm);
  overflow: hidden;
  margin: 12px 0;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}
.dc-seg {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  line-height: 1.2;
  min-width: 2%;
}
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 960px) { .grid2 { grid-template-columns: 1fr; } }
.dev-pos { color: #059669; font-weight: 700; }
.dev-neg { color: #dc2626; font-weight: 700; }
.tbl-scroll { max-height: none; overflow: visible; }

/* ── 总览模块卡 ── */
.ov-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  margin-bottom: 0;
}
@media (max-width: 1200px) { .ov-grid { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 640px) { .ov-grid { grid-template-columns: 1fr; } }
.ov-tile {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 14px 14px 12px;
  box-shadow: var(--shadow-sm);
  border-top: 3px solid var(--ov-accent, #94a3b8);
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: box-shadow 0.2s;
}
.ov-tile:hover { box-shadow: var(--shadow-md); }
.ov-tile-main {
  display: flex;
  align-items: center;
  gap: 0;
  text-align: left;
}
.ov-tile-icon { display: none; }
.ov-tile-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-faint);
  margin-bottom: 2px;
}
.ov-tile-value {
  font-size: 24px;
  font-weight: 800;
  color: var(--text-strong);
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}
.ov-tile-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding-top: 8px;
  border-top: 1px solid #f1f5f9;
}
.ov-meta-item {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  font-size: 11px;
  padding: 3px 8px;
  background: #f8fafc;
  border-radius: 6px;
  color: var(--text-muted);
}
.ov-meta-item em {
  font-style: normal;
  font-weight: 600;
  color: var(--text-faint);
}
.ov-meta-item strong {
  font-weight: 800;
  color: var(--text-strong);
  font-variant-numeric: tabular-nums;
}
.ov-cards { display: contents; }

.ec { width: 100%; }

.footer {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: flex-end;
  gap: 8px 24px;
  padding: 22px 40px 26px;
  color: var(--text-faint);
  background: #f8fafc;
  border-top: 1px solid var(--border);
  font-size: 12px;
  border-radius: 0 0 var(--radius-lg) var(--radius-lg);
}
.footer-main {
  font-weight: 700;
  color: var(--text-muted);
  font-size: 13px;
}
.footer-sources { color: var(--text-faint); }

/* ── Print ── */
@media print {
  body { background: #fff; padding: 0; font-size: 12px; }
  .dashboard { box-shadow: none; border: none; }
  .nav-tabs { position: static; box-shadow: none; }
  .panel { display: block !important; page-break-inside: avoid; padding: 16px 20px; }
  .chart-box { break-inside: avoid; }
  .header-meta { flex-wrap: wrap; }
}

/* ── RT 合并块（总览嵌入） ── */
.rt-merge-block { margin-top: 8px; }
.alert-box {
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: var(--radius-md);
  padding: 14px 18px;
  margin-bottom: 20px;
  font-size: 14px;
  line-height: 1.75;
  color: #78350f;
}
.alert-box b { color: #92400e; }
.rt-section {
  background: var(--brand-bg);
  border: 1px solid var(--border-accent);
  border-radius: var(--radius-md);
  padding: 16px 18px;
  margin-bottom: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}
.rt-section-title {
  font-size: 1em;
  font-weight: 800;
  color: var(--brand);
  margin: 0 0 10px;
  padding-bottom: 6px;
  border-bottom: 2px solid var(--brand-cyan);
}
.section-desc {
  font-size: 0.85em;
  color: var(--text-faint);
  margin: 0 0 10px;
  line-height: 1.45;
}
.section-desc.muted { color: var(--text-faint); }
.rt-table-wrap {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: #fff;
  overflow: visible;
  max-height: none;
  padding: 0;
  margin-bottom: 0;
}
table.sum-table { font-size: 12px; }
table.sum-table th {
  background: var(--table-head);
  color: #fff;
  position: static;
}
table.sum-table td.samples { font-size: 12px; color: var(--text-muted); }
.na { color: #94a3b8; font-weight: 600; }
.pill {
  display: inline-block;
  padding: 3px 11px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.pill-low { background: #dcfce7; color: #15803d; }
.pill-mid { background: #dbeafe; color: #1d4ed8; }
.pill-high { background: #fef2f2; color: #dc2626; }
.insight-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}
@media (max-width: 900px) { .insight-grid { grid-template-columns: 1fr; } }
.ins-card {
  border-radius: var(--radius-sm);
  padding: 16px 18px;
  border-left: 4px solid;
  background: var(--surface);
  border: 1px solid var(--border);
  border-left-width: 4px;
}
.ins-card h4 { font-size: 15px; font-weight: 700; margin-bottom: 10px; }
.ins-card ul { margin: 0; padding-left: 18px; font-size: 14px; line-height: 1.85; color: var(--text); }
.ins-card.c1 { border-left-color: var(--brand-light); background: #f0f9ff; }
.ins-card.c1 h4 { color: var(--brand); }
.ins-card.c2 { border-left-color: #10b981; background: #f0fdf4; }
.ins-card.c2 h4 { color: #059669; }
.ins-card.c3 { border-left-color: #f59e0b; background: #fffbeb; }
.ins-card.c3 h4 { color: #d97706; }
.ins-card.c4 { border-left-color: #6366f1; background: #eef2ff; }
.ins-card.c4 h4 { color: #4f46e5; }
.drill-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: flex-end;
  padding: 16px 18px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  margin-bottom: 16px;
}
.drill-filter .filter-group { flex: 1; min-width: 200px; }
.drill-filter label {
  display: block;
  font-size: 12px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 6px;
}
.drill-filter select {
  width: 100%;
  padding: 11px 14px;
  border: 1px solid #cbd5e1;
  border-radius: var(--radius-sm);
  font-size: 14px;
  background: var(--surface);
  color: var(--text);
}
.drill-filter select:focus {
  outline: none;
  border-color: var(--brand-light);
  box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.15);
}
.drill-filter .btn-reset {
  padding: 11px 18px;
  border-radius: var(--radius-sm);
  border: 1px solid #cbd5e1;
  background: var(--surface);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  cursor: pointer;
}
.drill-filter .btn-reset:hover { background: var(--surface-2); }
.drill-stats {
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 14px;
  padding: 12px 16px;
  background: var(--brand-bg);
  border: 1px solid #bfdbfe;
  border-radius: var(--radius-sm);
}
.drill-stats b { color: var(--brand); }
.drill-empty {
  text-align: center;
  padding: 40px 20px;
  color: var(--text-faint);
  font-size: 14px;
  background: var(--surface-2);
  border-radius: var(--radius-sm);
  border: 1px dashed #cbd5e1;
}
details.dept {
  margin: 0 0 12px;
  border-radius: var(--radius-md);
  background: var(--surface);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}
details.dept > summary .dept-name {
  flex: 1 1 160px;
  min-width: 120px;
}
.rt-src-tags {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.rt-src-chip {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  font-size: 12px;
  font-weight: 600;
  padding: 3px 8px;
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 6px;
  color: #0369a1;
}
.rt-src-chip em {
  font-style: normal;
  font-size: 11px;
  color: #64748b;
  font-weight: 700;
}
.rt-src-chip .rt-num { font-weight: 800; color: #0c4a6e; }
details.dept > summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  cursor: pointer;
  position: relative;
  list-style: none;
  padding: 16px 44px 16px 18px;
  background: linear-gradient(90deg, #eff6ff 0%, #fff 48%);
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
  border-left: 4px solid var(--brand-light);
}
details.dept > summary::-webkit-details-marker { display: none; }
details.dept > summary::after {
  content: '';
  position: absolute;
  right: 18px;
  top: 50%;
  width: 8px;
  height: 8px;
  border-right: 2px solid var(--text-muted);
  border-bottom: 2px solid var(--text-muted);
  transform: translateY(-70%) rotate(45deg);
}
details.dept[open] > summary { border-bottom: 1px solid var(--border); }
details.dept .dept-inner {
  padding: 14px 16px 16px;
  background: var(--surface-2);
}
details.person {
  margin: 0 0 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--surface);
  overflow: hidden;
}
details.person > summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 10px;
  cursor: pointer;
  position: relative;
  list-style: none;
  padding: 12px 40px 12px 14px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-muted);
  background: var(--surface);
}
details.person > summary::-webkit-details-marker { display: none; }
details.person[open] > summary {
  border-bottom: 1px solid var(--border);
  color: var(--text);
  background: var(--surface-2);
}
details.person .person-inner { padding: 12px 14px; }
.tbl-wrap.drill-tbl { max-height: none; overflow: visible; }
.drill-fold-hint {
  font-size: 12px;
  color: #64748b;
  font-weight: 500;
}

/* Gate-AI Tab · 业务线双图 */
.panel[data-tab="ai"] .ai-charts-zone {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-top: 4px;
}
@media (max-width: 960px) {
  .panel[data-tab="ai"] .ai-charts-zone { grid-template-columns: 1fr; }
}
.panel[data-tab="ai"] .ai-chart-card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 16px 18px 12px;
  box-shadow: var(--shadow-sm);
}
.panel[data-tab="ai"] .ai-chart-mix { border-top: 3px solid #f59e0b; }
.panel[data-tab="ai"] .ai-chart-est { border-top: 3px solid #7c3aed; }
.panel[data-tab="ai"] .ai-chart-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}
.panel[data-tab="ai"] .ai-chart-ico {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
  border-radius: 10px;
  background: #f8fafc;
}
.panel[data-tab="ai"] .ai-chart-est .ai-chart-ico { background: #f5f3ff; }
.panel[data-tab="ai"] .ai-chart-mix .ai-chart-ico { background: #fff7ed; }
.panel[data-tab="ai"] .ai-chart-title {
  font-size: 14px;
  font-weight: 800;
  color: var(--text-strong);
  margin-bottom: 4px;
}
.panel[data-tab="ai"] .ai-chart-hint {
  font-size: 12px;
  color: var(--text-faint);
  line-height: 1.5;
}
.panel[data-tab="ai"] .ai-chart-hint b { color: var(--text-strong); font-weight: 800; }
.panel[data-tab="ai"] .ai-chart-card .ec {
  width: 100%;
  border-radius: var(--radius-sm);
  background: #fafbfc;
}
table.data-table { font-size: 13px; min-width: 0; width: 100%; }
table.data-table th,
table.data th,
.detail-table th,
.sum-table th {
  background: var(--table-head);
  color: #fff;
  position: static;
  font-size: 0.85em;
  font-weight: 800;
}
table.data-table td { color: var(--text); }
table.data-table a { color: var(--brand); font-weight: 600; }
.tag {
  display: inline-block;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--brand-pale);
  color: var(--brand);
  font-weight: 600;
}
.muted { color: var(--text-faint); }
.kpi-inline { font-size: 13px; font-weight: 600; color: var(--text-muted); }

.hour-ov-toolbar { flex-wrap: wrap; gap: 12px; }
.hour-ov-search-wrap { flex: 1 1 280px; min-width: 200px; }
.hour-ov-search {
  width: 100%;
  max-width: 420px;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 14px;
}
.hour-ov-kpi { font-size: 13px; color: var(--text-muted); font-weight: 600; }
.hour-ov-search-results { margin: 8px 0 16px; }
.hour-ov-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
.hour-ov-table .hour-ov-input,
.hour-ov-table .hour-ov-note {
  width: 100%;
  min-width: 72px;
  max-width: 120px;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
}
.hour-ov-table .hour-ov-note { max-width: 160px; }
.hour-ov-mini { font-size: 13px; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.hour-ov-missing td { background: #fef2f2; }
.btn-hour-ov--active { background: #fef3c7; border-color: #f59e0b; color: #92400e; }
.hour-ov-row td { background: #fffbeb; }
.hour-ov-val { font-weight: 700; color: #b45309; }
.hour-ov-modal {
  position: fixed;
  inset: 0;
  z-index: 10000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.hour-ov-modal[hidden] { display: none !important; }
body.hour-ov-modal-open { overflow: hidden; }
.hour-ov-modal-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(15, 23, 42, 0.52);
  backdrop-filter: blur(4px);
}
.hour-ov-modal-panel {
  position: relative;
  width: min(480px, 100%);
  background: var(--surface);
  border-radius: 16px;
  box-shadow: 0 24px 48px rgba(15, 23, 42, 0.18);
  border: 1px solid var(--border);
  overflow: hidden;
  animation: hour-ov-in 0.22s ease-out;
}
@keyframes hour-ov-in {
  from { opacity: 0; transform: translateY(12px) scale(0.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
.hour-ov-modal-header {
  background: linear-gradient(135deg, #0369a1 0%, #0ea5e9 100%);
  color: #fff;
  padding: 18px 22px 16px;
}
.hour-ov-modal-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.hour-ov-modal-badge {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.18);
}
.hour-ov-modal-close {
  border: none;
  background: rgba(255, 255, 255, 0.15);
  color: #fff;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
}
.hour-ov-modal-close:hover { background: rgba(255, 255, 255, 0.28); }
.hour-ov-modal-id {
  font-size: 12px;
  opacity: 0.9;
  margin-bottom: 4px;
  font-weight: 600;
}
.hour-ov-modal-title {
  font-size: 14px;
  line-height: 1.45;
  font-weight: 600;
  margin: 0;
  color: #fff;
}
.hour-ov-modal-body { padding: 20px 22px 16px; }
.hour-ov-field-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin-bottom: 14px;
}
.hour-ov-field { display: flex; flex-direction: column; gap: 6px; }
.hour-ov-field--full { margin-bottom: 14px; }
.hour-ov-field-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted);
  letter-spacing: 0.02em;
}
.hour-ov-field-label em {
  font-style: normal;
  font-weight: 500;
  color: var(--text-faint);
  margin-left: 4px;
}
.hour-ov-field-input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-strong);
  background: #f8fafc;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.hour-ov-field-input:focus {
  outline: none;
  border-color: #38bdf8;
  box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.15);
  background: #fff;
}
.hour-ov-rt-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 12px;
  background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
  border: 1px solid #bae6fd;
}
.hour-ov-rt-label { font-size: 13px; font-weight: 700; color: #0369a1; }
.hour-ov-rt-value {
  font-size: 28px;
  font-weight: 800;
  line-height: 1;
  color: #0369a1;
}
.hour-ov-modal-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
  padding: 14px 22px 18px;
  border-top: 1px solid var(--border);
  background: #f8fafc;
}
.hour-ov-btn {
  padding: 8px 16px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  border: 1px solid transparent;
}
.hour-ov-btn--ghost {
  background: #fff;
  border-color: #cbd5e1;
  color: var(--text-muted);
}
.hour-ov-btn--ghost:hover { background: #f1f5f9; }
.hour-ov-btn--primary {
  background: #0369a1;
  border-color: #0369a1;
  color: #fff;
  box-shadow: 0 4px 12px rgba(3, 105, 161, 0.25);
}
.hour-ov-btn--primary:hover { background: #0284c7; }
"""
