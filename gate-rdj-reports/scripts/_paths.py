"""gate-rdj-reports 包路径：脚本 / 模板 / vendor 与 SKILL 同包；CSV / HTML 产物在仓库根。"""
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PACKAGE_ROOT.parent
SCRIPTS_DIR = PACKAGE_ROOT / "scripts"
TEMPLATES_DIR = PACKAGE_ROOT / "templates"
VENDOR_DIR = PACKAGE_ROOT / "vendor"
DATA_DIR = REPO_ROOT / "data"
SKILL_MD = PACKAGE_ROOT / "SKILL.md"

# HTML 内 ECharts：仓库根 vendor 为 symlink，两种相对路径均可用
ECHARTS_REL = "vendor/echarts-5.4.3.min.js"
ECHARTS_CDN_FALLBACK = (
    "https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"
)
