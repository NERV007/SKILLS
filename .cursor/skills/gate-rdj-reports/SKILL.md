---
name: gate-rdj-reports
description: >-
  Gate-RDJ / 全景 / QC 四源 / RT 合并报告。完整手册见仓库内 gate-rdj-reports/SKILL.md。
disable-model-invocation: true
---

# gate-rdj-reports

完整操作手册：**`gate-rdj-reports/SKILL.md`**。

```bash
export GATE_REPORTS_ROOT="${GATE_REPORTS_ROOT:-$HOME/work/效能-cursor}"
cd "$GATE_REPORTS_ROOT"
bash gate-rdj-reports/scripts/refresh_portfolio_pipeline.sh
```
