# HTML 模板（Gate-RDJ 单源报告）

由 `scripts/generate_gate_rdj_from_csv.py` / `gate_rdj_from_xlsx.py` 读取并注入数据。  
**全景单页** `RD-Efficiency-Portfolio.html` 不在此目录生成，见 `build_portfolio_single_html.py`。

| 文件 | 用途 |
|------|------|
| `Gate-RDJ-12-skill-需求分析报告.html` | 时间/迭代维 · 完整需求分析 |
| `Gate-RDJ-12-skill-需求分析报告_精简版.html` | 同上 · 精简版 |
| `Gate-RDJ-12-skill-测试效能汇总报告.html` | 测试效能汇总 |
| `Gate-RDJ-12-v4-业务线分析报告.html` | v4 业务线（含 QC 个人表；多人 QC `1/n` 均分） |
| `Gate-RDJ-QC人员-P9人效环比与建议报告.html` | P9 人效参考模板 |
| `rt_merge_report.html` | RT 四源合并（`generate_rt_merge_report.py`） |

## 主站 R/T 口径（模板内图表与全景一致）

- **修正研发** = 技术方案 + 各工种开发估分 + `max(0, 测试估分 − 测试节点估分(去除RD))`
- **测试工时** = `测试总估分(去除RD)`；空则 QC用例 + 测试 + 预发
- **QC 列展示**：`-QC/-qc` → 测试侧；无 qc 后缀 → 开发角色（含 `role-s-qa`），**不调整**上述工时公式

个案工时覆盖仅在全景 **工时修正** Tab（`portfolio_hour_override.py`，浏览器 `localStorage`）。
