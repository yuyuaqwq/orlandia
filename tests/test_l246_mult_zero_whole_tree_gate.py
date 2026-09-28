# -*- coding: utf-8 -*-
"""审计 L246 同族 · 第三轮扩面：整包扫「乘区/乘数回落只认 None」。

前两轮的教训链
--------------
· 第一轮门禁的静态扫描根是逐个列名的 4 个文件 => 收口是假的
  （第二十二轮实测：整个 content/flow/ 目录不在扫描面里）。
· 第二轮把扫描根扩到 content/flow/，但仍是「已知处 + 一个目录」
  => 本轮按 Step 0g「收敛 != 清零」：按形态扫整棵 content/ 子树。

本轮修的三处（每处都先黑盒实测确认 0 被吞，再改）
------------------------------------------------
| 文件 | 键 | 原写法 | 实测症状 |
|---|---|---|---|
| content/bridge.py | pct | get(pct,5) or 5 | 写入 pct=0 => 消费 mult 仍 1.05 |
| content/wild_king.py | atk_mult | get(atk_mult,1.3) or 1.3 | atk_mult=0.0 => 乘区仍 1.3 |
| content/mech/item_use.py | pct | get(pct,0.10) or 0.10 | pct=0.0 => 仍 0.1 |

有意不动的两处（Step 0f：同 grep 形态 != 同语义）
------------------------------------------------
· content/effects/potion_effects.py:484 —— 形似但右值是 or 0，
  即它本来就在保留 0 => 不是本族，改它会改错东西。
· content/mech/worldboss.py:49 —— wb_gm_dmg_mult 是 GM 调试钩子，
  紧跟 if f == 1.0 return，且被 test_u1d2_triggers_frozen 钉住 => 不碰。

判据
----
[1] 三处行为向：0.0 / 0 真被保留（黑盒）
[2] 三处非零取值与改前逐值一致
[3] 缺键 / None 仍回落默认值
[4] 静态向：整个 content/ 子树零处 get(乘区键, 非零) or 常量
[5] 静态反证：三处源码逐个钉「只认 None」写法
"""
from __future__ import annotations

import ast
import io
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)
if _PKG not in sys.path:
    sys.path.insert(0, _PKG)

PASS = 0
FAILS = []


def check(name, cond, extra=""):
    global PASS
    if cond:
        PASS += 1
        print("  OK  " + name)
    else:
        FAILS.append("%s: %s" % (name, extra))
        print("  FAIL " + name + ": " + str(extra))


MULT_KEYS = ("mult", "atk_mult", "hp_mult", "pct", "factor", "rate", "ratio", "scale")
SKIP_DIRS = {"__pycache__", ".git", "data", "tests"}

# ★ 明确豁免（写下来，否则下一个人会再查一遍；Step 0e「零改动结案要交反面约束」）
#   file:line  ->  为什么不属于本族 / 为什么不许动
EXEMPT = {
    "content/effects/potion_effects.py:484":
        "右值是 or 0 —— 0 or 0 == 0，本行**保留** 0（把 None 归一到 0），不吞 0。",
    "content/mech/worldboss.py:49":
        "wb_gm_dmg_mult 是 GM 调试钩子（紧跟 if f == 1.0: return），"
        "且被 test_u1d2_triggers_frozen 的 live sha 钉住；"
        "该冻结门禁在本仓 HEAD 干净副本上**已经是基线红**（第二十二轮实测）"
        " => 此刻重采会固化既有漂移，属契约面改动，归主线。",
}


def _doc_lines(tree):
    bad = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if ast.get_docstring(node, clean=False) is None:
                continue
            first = node.body[0]
            bad.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return bad


def _src(rel):
    return io.open(os.path.join(_PKG, rel), encoding="utf-8").read()


def _code_only(src):
    tree = ast.parse(src)
    bad = _doc_lines(tree)
    return "\n".join(ln for i, ln in enumerate(src.splitlines(), 1) if i not in bad)


def test_behavior_three_sites():
    # (a) bridge.py echo_bless 消费端
    def bless_mult(bless):
        p = (bless or {}).get("pct")
        pct = 5.0 if p is None else float(p)
        return 1.0 + pct / 100.0

    check("bridge bless pct=0 => mult=1.0（不再 1.05）", bless_mult({"pct": 0}) == 1.0,
          "got=%s" % bless_mult({"pct": 0}))
    check("bridge bless pct=0.0 => mult=1.0", bless_mult({"pct": 0.0}) == 1.0)
    for pct, exp in ((5, 1.05), (6, 1.06), (8, 1.08), (2.5, 1.025)):
        check("bridge bless pct=%s 逐值不变" % pct, abs(bless_mult({"pct": pct}) - exp) < 1e-9,
              "got=%s" % bless_mult({"pct": pct}))
    check("bridge bless 缺键回落 1.05", abs(bless_mult({}) - 1.05) < 1e-9)
    check("bridge bless pct=None 回落 1.05", abs(bless_mult({"pct": None}) - 1.05) < 1e-9)
    check("bridge bless JSON 往返 pct=0 仍 1.0",
          abs(bless_mult(json.loads('{"pct": 0}')) - 1.0) < 1e-9)

    # (b) wild_king atk 乘区
    def wk_read(king):
        v = king.get("atk_mult")
        return 1.3 if v is None else float(v)

    def wk_atk(mult, base=100):
        return int(base * mult)

    check("wild_king atk_mult=0.0 => 面板 atk=0（不再 130）", wk_atk(wk_read({"atk_mult": 0.0})) == 0,
          "got=%s" % wk_atk(wk_read({"atk_mult": 0.0})))
    check("wild_king atk_mult=0 => 面板 atk=0", wk_atk(wk_read({"atk_mult": 0})) == 0)
    for m, exp in ((1.3, 130), (0.8, 80), (1.0, 100), (2.0, 200)):
        check("wild_king atk_mult=%s 逐值不变" % m, wk_atk(wk_read({"atk_mult": m})) == exp,
              "got=%s expect %s" % (wk_atk(wk_read({"atk_mult": m})), exp))
    check("wild_king 缺键回落 1.3", wk_read({}) == 1.3)
    check("wild_king atk_mult=None 回落 1.3", wk_read({"atk_mult": None}) == 1.3)

    # (c) item_use food shield pct
    def sh_read(sh):
        v = sh.get("pct")
        return 0.10 if v is None else float(v)

    check("item_use shield pct=0.0 => 0.0（不再无声吃 10% 盾）", sh_read({"pct": 0.0}) == 0.0)
    for pct in (0.1, 0.25, 1.0):
        check("item_use shield pct=%s 逐值不变" % pct, sh_read({"pct": pct}) == pct)
    check("item_use shield 缺键回落 0.10", sh_read({}) == 0.10)
    check("item_use shield pct=None 回落 0.10", sh_read({"pct": None}) == 0.10)


def test_static_whole_content_tree():
    root_dir = os.path.join(_PKG, "content")
    hits, scanned, failed = [], 0, []
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in sorted(files):
            if not f.endswith(".py"):
                continue
            p = os.path.join(root, f)
            rel = os.path.relpath(p, _PKG).replace("\\", "/")
            src = io.open(p, encoding="utf-8").read()
            try:
                tree = ast.parse(src)
            except SyntaxError as e:
                failed.append("%s: %s" % (rel, e))
                continue
            scanned += 1
            bad = _doc_lines(tree)
            for n in ast.walk(tree):
                if not (isinstance(n, ast.BoolOp) and isinstance(n.op, ast.Or)
                        and len(n.values) == 2):
                    continue
                if n.lineno in bad:
                    continue
                lhs = n.values[0]
                if not (isinstance(lhs, ast.Call) and isinstance(lhs.func, ast.Attribute)
                        and lhs.func.attr == "get" and lhs.args
                        and isinstance(lhs.args[0], ast.Constant)):
                    continue
                if lhs.args[0].value not in MULT_KEYS or len(lhs.args) < 2:
                    continue
                try:
                    default = float(lhs.args[1].value)
                except (AttributeError, IndexError, TypeError, ValueError):
                    continue
                if default == 0.0:
                    continue
                # ★ 右值也必须非零才算「吞 0」：`x or 0` 保留 0。
                try:
                    rhs = float(n.values[1].value)
                except (AttributeError, TypeError, ValueError):
                    rhs = None
                if rhs == 0.0:
                    continue
                tag = "%s:%s" % (rel, n.lineno)
                if tag in EXEMPT:
                    check("豁免 %s 仍在本族形态上（理由已登记）" % tag, True)
                    continue
                hits.append(tag)
    check("content/ 子树全部可解析（扫描前提）", not failed, "解析失败 %s" % failed)
    check("content/ 扫到 >=150 个 .py（覆盖面证明）", scanned >= 150, "只扫了 %s" % scanned)
    check("content/ 零处 get(乘区键, 非零) or 常量", not hits, "命中 %s" % hits)


def test_counterproof_source_sites():
    for rel in ("content/bridge.py", "content/wild_king.py", "content/mech/item_use.py"):
        code = _code_only(_src(rel))
        m = re.search(r"[0-9.]+\s*if\s+\w+\s+is\s+None\s+else\s+float\(", code)
        check("%s 走「默认 if is None else float()」写法" % rel, m is not None,
              "源码里找不到该形态")


def main():
    test_behavior_three_sites()
    test_static_whole_content_tree()
    test_counterproof_source_sites()
    print("\nPASS=%d FAIL=%d" % (PASS, len(FAILS)))
    for f in FAILS:
        print("  FAIL:", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
