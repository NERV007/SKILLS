"""全景单页 · 主站 R/T 核心公式说明（需求明细 / 原始数据 / 附录共用）。"""

from __future__ import annotations

from html import escape


def portfolio_main_formula_callout_html(*, compact: bool = False) -> str:
    """主站 Gate-RDJ 工时与 R/T 公式说明块。"""
    title = "主站·Gate-RDJ 工时与 R/T 公式"
    if compact:
        return f"""
<div class="formula-core-box formula-core-box--compact">
  <p class="formula-core-title"><b>{escape(title)}</b></p>
  <p class="formula-core-line"><b>修正研发</b> = 技术方案设计与评审估分 + 各工种开发估分总和 + max(0, 测试估分−测试节点估分(去除RD))</p>
  <p class="formula-core-line"><b>测试工时</b> = 测试总估分(去除RD)；空则 QC用例估分+测试估分+预发测试估分</p>
  <p class="formula-core-line"><b>单条 R/T</b> = 修正研发÷测试工时（测试&gt;0.05）；<b>合计 R/T</b> = Σ修正研发÷Σ测试工时</p>
  <p class="formula-core-line muted">各工种 = FE/BE/APP/Engine/DATA/WS/WBE/Admin（全空回退「研发总估分」）。QC 列：后缀 -QC/-qc → 测试侧展示；无 qc 后缀 → 开发角色；<b>不调整</b>工时。</p>
</div>"""

    return f"""
<div class="formula-core-box">
  <p class="formula-core-title"><b>{escape(title)}</b>（需求明细 / 原始数据 Tab 主站行）</p>
  <ol class="formula-core-list">
    <li><b>各工种开发估分总和</b> = FE + BE + APP + Engine + DATA + WS + WBE + Admin；以上全空时回退 <code>研发总估分</code>。</li>
    <li><b>修正研发</b> = <code>技术方案设计与评审估分</code> + 各工种开发估分总和 + max(0, <code>测试估分</code> − <code>测试节点估分(去除RD)</code>)。</li>
    <li><b>测试工时</b> = <code>测试总估分(去除RD)</code>；若为空或 ≤0，则 = <code>QC测试用例设计与评审估分</code> + <code>测试估分</code> + <code>预发测试估分</code>。</li>
    <li><b>单条 R/T</b> = 修正研发 ÷ 测试工时（测试工时 &gt; 0.05 且修正研发 &gt; 0，否则显示 —）。</li>
    <li><b>筛选合计 R/T</b> = Σ修正研发 ÷ Σ测试工时（<b>非</b>单条 R/T 的平均值）。</li>
    <li><b>QC 列 · 开发角色</b>：按 <code>|</code> 拆分——后缀带 <code>-QC</code>/<code>-qc</code> → QC 列（含离职、未在 department_stats 名册的测试）；<b>后缀不带 qc</b> → 开发角色列（如 Change、morgan-be）。<b>仅展示，不调整工时</b>。</li>
  </ol>
  <p class="formula-core-foot muted">其他模块（分站 / AI / Alpha）口径不同，见页面底部「附录：效能指标计算公式」。</p>
</div>"""
