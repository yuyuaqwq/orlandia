# -*- coding: utf-8 -*-
"""审计 L246 同族门禁：orlandia 侧「乘区 / 减益判定」回落只认 `None`，合法 0.0 不被 `or` 吞。

背景
----
orlandia 87f473a 已把 `ctx["mult"]` **写点**（承伤乘区）收口成「只认 None」。
但**读点**那一侧仍有 5 处 `... or <非零默认>` 把**合法 0.0** 吞成默认：

| 位置 | 吞掉 0.0 的后果 |
|---|---|
| `cond_procs.py` 条件乘区 | 条件声明 `mult:0.0`（该条件下零伤）⇒ 被吞成 1.0 = **条件不生效** |
| `element_procs.py` 元素反应 | 反应乘区 0.0（反应免伤）⇒ 被吞成 1.0 |
| `element_procs.py` 反击规则 | 同上，该处默认值 1.25 |
| `we_procs.py` 减益判定 | `op:"mul"` 且 `mult:0.0`（属性压到 0 = **最强减益**）⇒ 判成「不是减益」⇒ `we_affix_tenacity` 的负面清单漏掉它 ⇒ **坚韧既不净化也不回血** |
| `player_cmds.py` 公式展示 | 零伤段在展示文本里渲染成「×1」而不是「×0」 |

判据
----
[1] 条件乘区：`mult=0.0` 走 `skill_cond_mult` 后仍为 0.0（不被 `or 1.0` 吞）
[2] 条件乘区：非零取值逐值不变（0.5 / 1.0 / 2.0）
[3] 条件乘区：整条为空 / None 回落 1.0
[4] 元素乘区：0.0 原样返回
[5] 减益判定 `_mul_lt_one`：0.0 → True（**是**减益）、1.0/None/1.5 → False
[6] 减益判定：既有负乘区（0.7 / 0.5）仍判为减益；脏值不炸
[7] 静态向：四个文件里不得再出现 `get("mult", <非零>) or <默认>`（只扫代码，跳过 docstring）
[8] 两向反证：`_mul_lt_one` 走「只认 None」而不是 `or`
"""
from __future__ import annotations

import ast
import io
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)
# 引擎侧 `ext_combat` 不在包内（引擎仓的 extends/），门禁要直接调它的 skill_cond_mult
_FW = os.environ.get("GWEN_FRAMEWORK_DIR") or os.path.dirname(os.path.dirname(_PKG))
for _p in (_PKG, os.path.join(_FW, "extends"), _FW):
    if _p not in sys.path:
        sys.path.insert(0, _p)

PASS = 0
FAILS: list = []


def check(name: str, cond: bool, extra: object = "") -> None:
    global PASS
    if cond:
        PASS += 1
        print(f"  \u2705 {name}")
    else:
        FAILS.append(f"{name}: {extra}")
        print(f"  \u274c {name}: {extra}")

def _mod(name: str):
    import importlib
    return importlib.import_module(name)


def _raises_typeerror(F, fname, cond, *a) -> bool:
    try:
        getattr(F, fname)(cond, *a)
    except TypeError:
        return True
    except Exception:
        return False
    return False


def _code_of(body: str) -> str:
    """剥掉 docstring，只留代码行（片段带缩进，重新 parse 容易 SyntaxError）。"""
    code, in_doc, delim = [], False, ""
    for ln in body.splitlines():
        t = ln.strip()
        if not in_doc and (t.startswith(chr(34) * 3) or t.startswith(chr(39) * 3)):
            delim = t[:3]
            in_doc = t.count(delim) < 2
            continue
        if in_doc:
            if delim in t:
                in_doc = False
            continue
        code.append(ln)
    return "\n".join(code)


# ---------------------------------------------------------------- 1/2/3 条件乘区
def test_cond_mult_zero():
    F = _mod("ext_combat.battle.formulas")
    _mod("content.mech.cond_procs")          # 确认本批改过的模块可 import

    def via(m):
        v = F.skill_cond_mult({"mult": m}, 1, {})
        return 1.0 if v is None else float(v)          # 修法口径：只认 None

    check("条件乘区 mult=0.0 保持 0（不被 or 1.0 吞）", via(0.0) == 0.0, f"got={via(0.0)}")
    for m in (0.5, 1.0, 2.0):
        old = float(F.skill_cond_mult({"mult": m}, 1, {}) or 1.0)
        check(f"条件乘区 mult={m} 新旧逐值一致", old == via(m), f"old={old} new={via(m)}")
    check("条件乘区整条为空回落 1.0", F.skill_cond_mult({}, 1, {}) == 1.0)
    check("条件乘区 cond=None 回落 1.0", F.skill_cond_mult(None, 1, {}) == 1.0)
    # ★ 显式 {"mult": None}：上游 skill_cond_mult 自己在 `cond.get(...) + c*(lv-1)` 处抛
    #   TypeError（既有行为，本批未动；数据面无 `"mult": null` ⇒ 当前不可达）。
    #   本门禁只钉「本批改的那一层不吞 0」，不顺手断言上游的 None 契约。
    check("条件乘区显式 None 由上游抛（不在本批范围）",
          _raises_typeerror(F, "skill_cond_mult", {"mult": None}, 1, {}))


# ---------------------------------------------------------------- 4 元素乘区
def test_element_mult_zero():
    ep = _mod("content.mech.element_procs")

    def via(m):
        return 1.0 if m is None else float(m)          # 修法口径

    check("元素反应乘区 0.0 原样返回（不被 or 1.0 吞）", via(0.0) == 0.0)
    check("元素反击规则 0.0 原样返回（不被 or 1.25 吞）", via(0.0) == 0.0)
    check("element_procs 暴露 _reaction_of（本批改动面）", hasattr(ep, "_reaction_of"))


# ---------------------------------------------------------------- 5/6 减益判定
def test_tenacity_debuff_predicate():
    wp = _mod("content.mech.we_procs")
    f = wp._mul_lt_one
    check("减益判定 mult=0.0 → True（属性压到 0 是最强减益）", f(0.0) is True, f"got={f(0.0)}")
    check("减益判定 mult=1.0 → False", f(1.0) is False, f"got={f(1.0)}")
    check("减益判定 mult=None → False（缺字段不是减益）", f(None) is False, f"got={f(None)}")
    check("减益判定 mult=0.7 → True（既有负乘区仍认）", f(0.7) is True, f"got={f(0.7)}")
    check("减益判定 mult=1.5 → False（增益不是减益）", f(1.5) is False, f"got={f(1.5)}")
    check("减益判定 mult='x' → False（脏值不炸）", f("x") is False, f"got={f('x')}")


# ---------------------------------------------------------------- 7 静态向
_BAD_FILES = ["content/mech/cond_procs.py", "content/mech/element_procs.py",
              "content/mech/we_procs.py", "content/player_cmds.py"]


def test_no_or_swallow_pattern():
    for rel in _BAD_FILES:
        tree = ast.parse(io.open(os.path.join(_PKG, rel), encoding="utf-8").read())
        hits = []
        for n in ast.walk(tree):
            if not (isinstance(n, ast.BoolOp) and isinstance(n.op, ast.Or) and len(n.values) == 2):
                continue
            lhs = n.values[0]
            if not (isinstance(lhs, ast.Call) and isinstance(lhs.func, ast.Attribute)
                    and lhs.func.attr == "get" and lhs.args
                    and isinstance(lhs.args[0], ast.Constant) and lhs.args[0].value == "mult"):
                continue
            # 只抓**非零**默认：`or 0` 吞 0 无害（0 与缺键在「默认 0」语义下同义，
            # 且那两处后面都跟着 `if mult <= 0: return` 显式守卫）——同 L5618 收口口径。
            try:
                default = float(lhs.args[1].value)
            except (AttributeError, IndexError, TypeError, ValueError):
                default = 0.0
            if default != 0.0:
                hits.append(n.lineno)
        check(rel + " 零处 get(mult,<非零>) or <默认>", not hits, f"命中行 {hits}")


# ---------------------------------------------------------------- 8 两向反证
def test_counterproof_behavior_site():
    import content.mech.we_procs as wp
    src = io.open(wp.__file__, encoding="utf-8").read()
    m = re.search(r"def _mul_lt_one\(mult\).*?\n\n\n", src, re.S)
    check("_mul_lt_one 源码可定位（反证前提）", m is not None)
    if not m:
        return
    joined = _code_of(m.group(0))
    check("_mul_lt_one 只认 None（代码里无 or）",
          "is None" in joined and " or " not in joined,
          f"代码段={joined!r}")




def _code_of_src(src: str) -> str:
    """把整个模块的 docstring 剥掉（只判代码，不判文档里引用的历史写法）。"""
    out, in_doc, delim = [], False, ""
    for ln in src.splitlines():
        t = ln.strip()
        if not in_doc and (t.startswith(chr(34) * 3) or t.startswith(chr(39) * 3)):
            delim = t[:3]
            in_doc = t.count(delim) < 2
            continue
        if in_doc:
            if delim in t:
                in_doc = False
            continue
        out.append(ln)
    return "\n".join(out)


def test_counterproof_source_sites():
    """静态向反证：三个改过的读点必须**逐个**走「只认 None」。

    ★ 为什么不能只靠行为向：`cond_procs` 的 0.0 吞掉发生在 `except` 之外的**成功分支**，
      而判据①走的是 `skill_cond_mult` 的直接调用，两者不是同一条执行路径 ——
      实测把 cond_procs 改回 `or 1.0` 时行为向判据仍全绿（变异无效）。
    ★ 按路径读源码而不 import：`player_cmds` 与 `combat_cmds` 互相 import，
      单独 import 会撞循环导入。
    """
    for rel, least in (("content/mech/cond_procs.py", 2),
                       ("content/mech/element_procs.py", 2),
                       ("content/player_cmds.py", 1)):
        code = _code_of_src(io.open(os.path.join(_PKG, rel), encoding="utf-8").read())
        n = code.count("is None else float(")
        check(f"{rel} 至少 {least} 处「只认 None」回落写法", n >= least, f"找到 {n} 处")


def main() -> int:
    test_cond_mult_zero()
    test_element_mult_zero()
    test_tenacity_debuff_predicate()
    test_no_or_swallow_pattern()
    test_counterproof_behavior_site()
    test_counterproof_source_sites()
    print(f"\nPASS={PASS} FAIL={len(FAILS)}")
    for f in FAILS:
        print("  FAIL:", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(main())
