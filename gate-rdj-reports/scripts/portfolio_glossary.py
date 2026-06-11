"""全景单页 · 各 Tab 指标公式附录（默认收起，样式对齐 Gate-RDJ 源报告）。"""

from __future__ import annotations

from html import escape

from portfolio_formula_core import portfolio_main_formula_callout_html

# (module, category, name, description_html)
_GLOSSARY: list[tuple[str, str, str, str]] = [
    # ── 总览 ──
    ("总览", "规模", "各模块需求数", "总览条形图：主站时间维 / 迭代维 / 分站 / AI / Alpha 各模块 KPI 需求条数，<b>不可相加</b>（时间维与迭代维为同一批需求两种切分）。"),
    ("总览", "R/T", "RT 合并总览", "嵌入 Gate-RDJ RT 合并报告：业务线维度 <code>修正研发 ÷ 测试工时</code>，与主站 Gate-RDJ 五阶段实测口径一致。"),
    ("总览", "R/T", "部门×四源表·编制列", "PD/FE/BE/WBE/API/APP 人数来自 <code>department_stats</code>，按「大类-新分组」与部门行对齐；末行求和。"),
    ("总览", "R/T", "需求明细", "R/T 区内嵌；模块+部门筛选，需求明细表分页浏览。主站行用<b>修正研发÷测试工时</b>核心公式；合计 R/T = Σ研发÷Σ测试。"),
    ("总览", "R/T", "开发角色列", "QC 列按 <code>|</code> 拆分：<b>后缀无 -QC/-qc</b> → 开发角色（如 Change、morgan-be、<code>role-s-qa</code>）；<b>后缀带 -QC/-qc</b> → QC 列。<b>仅展示</b>，不调整系统口径研发/测试/R/T。"),
    ("总览", "明细", "Story ID", "需求链接 <code>/detail/{id}</code> 解析；用于工时修正键、CSV 导出、锚点校验（如 #23430279）。"),
    ("总览", "对照", "模块口径对照表", "总览表列出各 Tab 的「数据性质 / R/T 口径 / 本页展示」——同名指标在不同 Tab <b>含义不同</b>，横比前请先读附录。"),

    # ── 工时修正 ──
    ("工时修正", "覆盖", "手工修正研发/测试", "仅主站·Gate-RDJ；浏览器 <code>localStorage</code> 键 <code>portfolio_hour_overrides_v1</code>；按 Story ID 存覆盖值，<b>不改 CSV</b>。"),
    ("工时修正", "R/T", "修正后单条 R/T", "与系统口径相同条件：测试&gt;0.05 且修正研发&gt;0；保存后联动需求明细、统计条、部门×四源表主站 R/T 列（客户端重算）。"),
    ("工时修正", "展示", "已修正行", "研发/测试列蓝色高亮；行 class <code>hour-ov-row</code>；移除修正恢复系统值。"),

    # ── 主站 Gate-RDJ ──
    ("主站 Gate-RDJ", "工时", "总工时 / 五阶段工时", "SUM(各需求总估分)；五阶段 = 设计评审 + 研发 + QC用例 + 测试节点(去RD) + 预发，各阶段<b>不重叠</b>。"),
    ("主站 Gate-RDJ", "工时", "修正研发工时", "<code>技术方案设计与评审估分</code> + <code>各工种开发估分总和</code> + <code>max(0, 测试估分−测试节点估分(去除RD))</code>"),
    ("主站 Gate-RDJ", "工时", "各工种开发估分", "FE + BE + APP + Engine + DATA + WS + WBE + Admin；全空回退 <code>研发总估分</code>。"),
    ("主站 Gate-RDJ", "工时", "测试工时（R/T 分母）", "<code>测试总估分(去除RD)</code>；空则 <code>QC用例估分+测试估分+预发测试估分</code>。QC 列开发角色<b>不拆</b>测试阶段工时。"),
    ("主站 Gate-RDJ", "工时", "五阶段测试投入", "报告图表用：<code>QC用例估分</code> + <code>测试节点估分(去除RD)</code> + <code>预发测试估分</code>（与 R/T 分母「测试总估分」字段不同）。"),
    ("主站 Gate-RDJ", "R/T", "单条 R/T 条件", "测试工时 &gt; 0.05 且修正研发 &gt; 0 时计算，否则 —。"),
    ("主站 Gate-RDJ", "R/T", "需求明细合计 R/T", "筛选后 Σ修正研发 ÷ Σ测试工时（非单条 R/T 算术平均）。"),
    ("主站 Gate-RDJ", "工时", "测试占比%", "测试工时 ÷ 五阶段总工时 × 100%；健康参考区间 30%–40%（源报告标注）。"),
    ("主站 Gate-RDJ", "工时", "各阶段工时占比", "该阶段工时 ÷ 五阶段合计 × 100%（饼图/阶段条）。"),
    ("主站 Gate-RDJ", "R/T", "平均 R/T", "修正研发工时 ÷ 测试工时；反映研发与测试资源投入比。"),
    ("主站 Gate-RDJ", "R/T", "月度 R/T", "当月完成需求的修正研发合计 ÷ 当月测试工时合计（组合图折线）。"),
    ("主站 Gate-RDJ", "交付", "平均交付周期", "<code>完成日期</code> − <code>创建时间</code>（自然日，排除当天完成）。"),
    ("主站 Gate-RDJ", "交付", "交付周期（工作日）", "使用 <code>chinese_calendar</code> 排除法定节假日与周末后的天数。"),
    ("主站 Gate-RDJ", "交付", "各阶段工期占比", "该阶段工时 ÷ 总工时 × 总交付周期（按工时比例分配自然日，卡片流）。"),
    ("主站 Gate-RDJ", "交付", "QC 人均需求", "当月交付需求数 ÷ 当月参与测试的 QC 人数（去重）。"),
    ("主站 Gate-RDJ", "交付", "测试效率", "当月交付需求数 ÷ 当月总测试工时（个/人天）。"),
    ("主站 Gate-RDJ", "质量", "Bug 数", "各需求关联 <code>Bug数</code> 求和。"),
    ("主站 Gate-RDJ", "质量", "均 Bug", "Bug 总数 ÷ 需求数（需求缺陷密度）。"),
    ("主站 Gate-RDJ", "质量", "Bug 率", "Bug 总数 ÷ 测试工时（每人天测试发现的 Bug 数）。"),
    ("主站 Gate-RDJ", "象限", "四象限划分", "以业务线（需求数≥5）<b>均值</b>为十字线：左上高效高产 · 右上高产周期长 · 左下周期短产出低 · 右下低效低产。"),
    ("主站 Gate-RDJ", "象限", "吞吐量 / 单位测试支撑交付量", "主图=交付需求总数；辅助=总交付估分÷测试工时（估分/人天）。"),
    ("主站 Gate-RDJ", "其他", "时间维 vs 迭代维", "同一批需求按<b>完成月份</b>与<b>迭代(SP)</b>两种切分；两维需求数接近但<b>不可相加</b>。"),
    ("主站 Gate-RDJ", "其他", "环比", "(本月值 − 上月值) ÷ 上月值 × 100%。"),

    # ── 分站 ──
    ("分站 · 产研", "条数", "工作项数", "全景导出 CSV 行数（当前状态均为「已完成」），按<b>创建月</b>分桶。"),
    ("分站 · 产研", "排期", "排期人天", "从「需求排期」字段解析「共 X 天」；无法解析时记为解析失败。"),
    ("分站 · 产研", "排期", "测试估分", "导出字段「测试估分」（人天）；测试=0 的条数单独统计。"),
    ("分站 · 产研", "排期", "测试/排期%", "测试估分合计 ÷ 排期人天合计 × 100%（仅排期&gt;0 子集）。<b>≠ 主站</b>「测试÷五阶段」。"),
    ("分站 · 产研", "排期", "近似 R/T", "单条：排期人天 ÷ 测试估分（测试&gt;0 且排期&gt;0）；汇总取样本中位数。<b>≠ 主站</b>「修正研发÷测试」。"),
    ("分站 · 产研", "人力", "QC 测试负荷", "多人 QC 时单条测试估分按人头均分后加总到个人；用于负荷对比，非财务口径。"),
    ("分站 · 产研", "人力", "测占排期%（散点）", "QC 参与的需求上，单条「测试估分÷排期」的均值（个人维度）。"),
    ("分站 · 产研", "说明", "不展示项", "本分站导出<b>无</b>五阶段分解、修正研发、Bug、迭代完成维；全景 Tab <b>不展示 R/T 与五阶段测试占比</b>。"),

    # ── AI ──
    ("AI 项目集", "分摊", "估算人日Σ", "各项目/业务线「估算人日」求和（Gate-AI 源表）。"),
    ("AI 项目集", "分摊", "测试分摊Σ", "估算人日 × 测试人数 ÷ (开发人数+测试人数)，按人头比例分摊（<b>非</b>五阶段实测）。"),
    ("AI 项目集", "分摊", "测试占比%", "测试分摊 ÷ 估算人日 × 100%（Gate-AI 口径）。"),
    ("AI 项目集", "分摊", "研发分摊Σ", "估算人日 − 测试分摊（同人天口径）。"),
    ("AI 项目集", "交付", "平均/中位交付天", "完成时间 − 创建时间（自然日）；按项目聚合。"),
    ("AI 项目集", "QC", "命中 QC 人", "QC 列命中 department_stats 白名单的人数（去重）。"),
    ("AI 项目集", "说明", "不展示 R/T", "全景 AI Tab <b>不展示分摊 R/T</b>；估分口径不可与主站 Gate-RDJ 横比绝对值。"),

    # ── Alpha · Meegle ──
    ("Alpha · Meegle", "估分", "测试节点Σ", "Meegle 排期「测试」流程节点人日合计（pd）。"),
    ("Alpha · Meegle", "估分", "总估分Σ", "Meegle 视图内各需求总估分合计。"),
    ("Alpha · Meegle", "R/T", "加权 R/T", "(Σ总估分 − Σ测试节点) ÷ Σ测试节点；<b>仅 Meegle 视图内</b>主站/分站对照，不可与 Gate-RDJ 修正研发÷测硬比。"),
    ("Alpha · Meegle", "R/T", "单条 R/T", "(总估pd − 测试pd) ÷ 测试pd（Top15 表）。"),
    ("Alpha · Meegle", "条数", "主站 / 分站条数", "Meegle 视图按主站、分站标签拆分的需求数。"),

    # ── 人员编制 ──
    ("人员编制", "编制", "开发总数", "PD + FE + BE + WBE + API + APP 各角色人数合计（按新分组行）。"),
    ("人员编制", "编制", "各角色人数", "来自 department_stats 表；悬停蓝色数字格可查看成员名单。"),
    ("人员编制", "配比", "开发WEB测试比", "该分组 (FE+BE+WBE+API) ÷ QC（WEB 向开发 vs QC）。"),
    ("人员编制", "配比", "大类开发WEB测试比", "同一大类下所有新分组的 WEB 开发合计 ÷ QC 合计。"),
    ("人员编制", "配比", "开发测试比", "开发总数 ÷ QC（含 APP 开发）；总和行同理。"),
    ("人员编制", "配比", "APP-QC", "APP 测试/QC 编制人数（与 WEB QC 分列）。"),

    # ── 跨模块对照（同名不同义）──
    ("⚠ 同名不同义", "测试占比", "主站 Gate-RDJ", "五阶段实测：QC用例+测试节点(去RD)+预发 ÷ 五阶段总工时。"),
    ("⚠ 同名不同义", "测试占比", "AI 项目集", "人头分摊：测试分摊 ÷ 估算人日。"),
    ("⚠ 同名不同义", "测试占比", "分站", "测试/排期%：测试估分 ÷ 排期人天（粗粒度投入结构）。"),
    ("⚠ 同名不同义", "R/T", "主站 Gate-RDJ", "修正研发工时 ÷ 测试工时（五阶段实测）。"),
    ("⚠ 同名不同义", "R/T", "Alpha · Meegle", "加权 (Σ总估−Σ测)÷Σ测（Meegle 节点口径）。"),
    ("⚠ 同名不同义", "R/T", "分站", "近似：排期÷测试估分；<b>全景不展示</b>。"),
    ("⚠ 同名不同义", "R/T", "AI 项目集", "研发分摊÷测试分摊；<b>全景不展示</b>。"),
    ("⚠ 同名不同义", "交付周期", "主站 / AI", "完成−创建（自然日）；主站另提供工作日版。"),
    ("⚠ 同名不同义", "交付周期", "分站", "按<b>创建月</b>分桶，无完成月维度。"),
]


def _build_rowspans() -> list[dict]:
    """为每行计算 module/category 是否输出及 rowspan。"""
    out: list[dict] = []
    i = 0
    while i < len(_GLOSSARY):
        mod = _GLOSSARY[i][0]
        mod_end = i
        while mod_end < len(_GLOSSARY) and _GLOSSARY[mod_end][0] == mod:
            mod_end += 1
        mod_span = mod_end - i
        j = i
        while j < mod_end:
            cat = _GLOSSARY[j][1]
            cat_end = j
            while cat_end < mod_end and _GLOSSARY[cat_end][1] == cat:
                cat_end += 1
            cat_span = cat_end - j
            for k in range(j, cat_end):
                _, _, name, desc = _GLOSSARY[k]
                out.append({
                    "module": mod,
                    "category": cat,
                    "name": name,
                    "desc": desc,
                    "mod_rowspan": mod_span if k == i else 0,
                    "cat_rowspan": cat_span if k == j else 0,
                })
            j = cat_end
        i = mod_end
    return out


def portfolio_formula_appendix_html() -> str:
    body_rows = []
    for r in _build_rowspans():
        cells = []
        if r["mod_rowspan"]:
            cells.append(
                f'<td class="gl-mod" rowspan="{r["mod_rowspan"]}">{escape(r["module"])}</td>'
            )
        if r["cat_rowspan"]:
            cells.append(
                f'<td class="gl-cat" rowspan="{r["cat_rowspan"]}">{escape(r["category"])}</td>'
            )
        cells.append(f'<td class="gl-name">{escape(r["name"])}</td>')
        cells.append(f'<td class="gl-desc">{r["desc"]}</td>')
        body_rows.append(f"<tr>{''.join(cells)}</tr>")

    footnote = """
<p class="gl-footnote">
<b>数据来源</b>：主站 Gate-RDJ 时间/迭代维 CSV · 产研分站全景导出 · Gate-AI 项目集 HTML · Meegle 视图 8bbOlLnNU ·
<a href="https://report.dev.halftrust.xyz/results/department_stats.html" target="_blank" rel="noopener">部门人员统计</a>。
各 Tab 指标仅在本 Tab 口径内解读；跨 Tab 对比请先查「⚠ 同名不同义」分类。
</p>"""

    return f"""
<details class="section-group formula-appendix">
  <summary class="group-title">附录：效能指标计算公式</summary>
  {portfolio_main_formula_callout_html()}
  <div class="gl-table-wrap">
    <table class="gl-table">
      <thead>
        <tr>
          <th class="gl-th-mod">所属 Tab</th>
          <th class="gl-th-cat">分类</th>
          <th class="gl-th-name">指标名称</th>
          <th class="gl-th-desc">计算公式 / 说明</th>
        </tr>
      </thead>
      <tbody>
        {''.join(body_rows)}
      </tbody>
    </table>
  </div>
  {footnote}
</details>
"""
