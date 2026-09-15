# -*- coding: utf-8 -*-
"""economy_lib.report —— 输出层（md 表格 / JSON，与 numeric_lib.report 同风格）"""
import json


def md_table(headers: list, rows: list) -> str:
    """markdown 表格（行=dict 时按 headers 取键）。"""
    lines = ["| " + " | ".join(str(h) for h in headers) + " |",
             "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        if isinstance(r, dict):
            vals = [str(r.get(h, "")) for h in headers]
        else:
            vals = [str(x) for x in r]
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def to_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def health_text(rows_with_issues: list) -> str:
    """健康检查文本（有问题的行输出违规清单）。"""
    out = []
    for row, issues in rows_with_issues:
        if issues:
            out.append(f"\n🔴 {row['stage']} (Lv{row['lv']}):")
            for i in issues:
                out.append(f"  - {i}")
    return "\n".join(out) if out else "\n✅ 全部阶段经济指标健康"
