---
name: gate-rdj-reports
description: >-
  Gate-RDJ / 全景 RD-Efficiency-Portfolio / QC 四源。完整手册与 portfolio 脚本见 gate-rdj-reports/SKILL.md。
disable-model-invocation: true
---

# gate-rdj-reports

- 完整手册：`gate-rdj-reports/SKILL.md`
- 全景单页：`scripts/build_portfolio_single_html.py` + `scripts/portfolio_*.py`
- 模版说明：`templates/portfolio/README.md`

```bash
export GATE_REPORTS_ROOT="${GATE_REPORTS_ROOT:-$HOME/work/效能-cursor}"
bash gate-rdj-reports/scripts/refresh_portfolio_pipeline.sh
```
