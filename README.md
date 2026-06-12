# SKILLS

Cursor / Claude Code skills 集合。

## gate-rdj-reports

Gate-RDJ 多源效能报告与 **`RD-Efficiency-Portfolio.html`** 产研效能全景单页。

| 路径 | 说明 |
|------|------|
| `gate-rdj-reports/SKILL.md` | 完整操作手册 |
| `gate-rdj-reports/examples/RD-Efficiency-Portfolio.html` | **全景报告完整示例**（可直接浏览器打开） |
| `gate-rdj-reports/scripts/build_portfolio_single_html.py` | 全景单页主入口 |
| `gate-rdj-reports/templates/portfolio/` | 构建说明 + UI 参考壳 |

### 预览示例报告

```bash
git clone https://github.com/NERV007/SKILLS.git
open SKILLS/gate-rdj-reports/examples/RD-Efficiency-Portfolio.html
```

### 安装 skill

```bash
ln -s "$(pwd)/SKILLS/gate-rdj-reports" ~/.cursor/skills/gate-rdj-reports
```

业务数据与重新构建见 `gate-rdj-reports/templates/portfolio/README.md`。
