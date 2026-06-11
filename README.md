# SKILLS

Cursor / Claude Code skills 集合。

## gate-rdj-reports

Gate-RDJ 多源效能报告与 **`RD-Efficiency-Portfolio.html`** 产研效能全景单页。

| 路径 | 说明 |
|------|------|
| `gate-rdj-reports/SKILL.md` | 完整操作手册 |
| `gate-rdj-reports/scripts/build_portfolio_single_html.py` | 全景单页主入口 |
| `gate-rdj-reports/scripts/portfolio_*.py` | 全景 Tab / 样式 / 校验模块 |
| `gate-rdj-reports/templates/portfolio/` | 全景构建说明 + UI 参考壳 |

### 安装

```bash
git clone https://github.com/NERV007/SKILLS.git
ln -s "$(pwd)/SKILLS/gate-rdj-reports" ~/.cursor/skills/gate-rdj-reports
```

业务数据（CSV、上游 HTML、产物 `RD-Efficiency-Portfolio.html`）放在独立的 `GATE_REPORTS_ROOT` 仓库；布局见 `gate-rdj-reports/templates/portfolio/README.md`。

### 构建全景

```bash
export GATE_REPORTS_ROOT=/path/to/your/效能-cursor
cd "$GATE_REPORTS_ROOT"
bash gate-rdj-reports/scripts/refresh_portfolio_pipeline.sh
```
