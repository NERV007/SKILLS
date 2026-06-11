#!/usr/bin/env bash
# 数据源更新后：按依赖顺序刷新各单源报告 → RD-Efficiency-Portfolio.html
# 用法：
#   cd "$GATE_REPORTS_ROOT" && bash gate-rdj-reports/scripts/refresh_portfolio_pipeline.sh
#   # 或（根目录 scripts 为符号链接时）
#   bash scripts/refresh_portfolio_pipeline.sh
set -euo pipefail

ROOT="${GATE_REPORTS_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$ROOT"

if [[ -d "$ROOT/scripts" && -f "$ROOT/scripts/build_portfolio_single_html.py" ]]; then
  PY="python3"
  RUN() { $PY "$ROOT/scripts/$1" "${@:2}"; }
elif [[ -f "$ROOT/gate-rdj-reports/scripts/build_portfolio_single_html.py" ]]; then
  RUN() { python3 "$ROOT/gate-rdj-reports/scripts/$1" "${@:2}"; }
else
  echo "错误: 未找到 build_portfolio_single_html.py（请设 GATE_REPORTS_ROOT）" >&2
  exit 1
fi

step() { echo ""; echo "======== $* ========"; }

step "1/7 Gate-RDJ 时间维+迭代维 HTML"
if [[ -f "$ROOT/需求导出-Gate-RDJ_时间维度.csv" ]]; then
  RUN gate_rdj_from_xlsx.py --regenerate --dimension both \
    || RUN generate_gate_rdj_from_csv.py
else
  echo "跳过: 缺少 需求导出-Gate-RDJ_时间维度.csv"
fi

step "2/7 产研分站全景"
if [[ -f "$ROOT/全景视图导出-产研分站.csv" ]] || ls "$ROOT"/*.xlsx 2>/dev/null | grep -qi 分站; then
  RUN generate_chanfeng_station_report.py
else
  echo "跳过: 缺少分站 CSV/xlsx"
fi

step "3/7 Gate-AI 项目集"
AI_XLSX=""
for f in "$ROOT"/Gate-AI*.xlsx "$ROOT"/需求导出-Gate-AI*.xlsx; do
  [[ -f "$f" ]] && AI_XLSX="$f" && break
done
if [[ -n "$AI_XLSX" ]]; then
  RUN generate_gate_ai_effort_report.py "$AI_XLSX"
elif [[ -f "$ROOT/Gate-AI项目集-测试工时与RT分析报告.html" ]]; then
  echo "跳过 HTML 重生成（无 xlsx）；沿用现有 Gate-AI项目集-测试工时与RT分析报告.html"
else
  echo "警告: 无 Gate-AI xlsx 且无现成 HTML" >&2
fi

step "4/7 Meegle 视图（可选，Alpha Tab 读 CSV）"
MEEGLE_CSV="$ROOT/data/meegle_view_8bbOlLnNU.csv"
if [[ -f "$MEEGLE_CSV" ]]; then
  RUN build_meegle_report_html.py "$MEEGLE_CSV" \
    -o "$ROOT/Meegle-视图8bbOlLnNU-主站分站-效能报告.html" || true
else
  echo "跳过: 无 $MEEGLE_CSV（Alpha 仍可从 CSV 直读若后续放入 data/）"
fi

step "5/7 QC 四源台账（RT 合并上游）"
export MEEGLE_CSV="${MEEGLE_CSV:-data/meegle_view_8bbOlLnNU.csv}"
export MEEGLE_QC_CSV="${MEEGLE_QC_CSV:-data/meegle_page_export.csv}"
PYTHONPATH="${ROOT}/scripts:${ROOT}/gate-rdj-reports/scripts:${PYTHONPATH:-}" \
  RUN qc_unified_roster_report.py

step "6/7 RT 四源合并"
RUN generate_rt_merge_report.py

step "7/7 产研效能全景单页"
RUN build_portfolio_single_html.py

echo ""
echo "完成 → $ROOT/RD-Efficiency-Portfolio.html"
echo "页内标题: 产研效能报告 | 原始数据默认筛选: 主导业务线=RDJ-交易工具"
