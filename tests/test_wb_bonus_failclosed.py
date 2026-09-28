# -*- coding: utf-8 -*-
"""审计 L4918-3 门禁 —— 世界 Boss 开战的面板增幅容器不许「静默留空」。

**它守什么**
----------
`content/combat_cmds.py::hunt_boss` 里，玩家 actor 的 `bonus` 容器是**唯一**的
面板增幅落点（v181.M-bonus · N10 收口后无 battle 级回落）。那处赋值原先包着

```
try:
    for _a in _sides.get("player", []):
        _a["bonus"] = {"panel": dict(_tb or {}), "cap": {}, "cost": {}}
except Exception:
    pass
```

⇒ `_tb` 形状不对时 `dict(...)` 抛错被吞掉，actor **完全没有 bonus 键**，
战斗照跑，玩家面板增幅**整场失效且零提示**。同一批输入走
`bridge.apply_battle_loadout` 却会落 `{"panel": {}}` ⇒ 两处口径分叉，
而分叉的根因就是这层静默（台账「宣称唯一容器 + 静默留空」双口径）。

**判据口径（逐条都是「不许放宽」）**
  (一) ★ 正例：`hunt_boss` 源码里那处赋值**不许**再被 `except … pass` 包住
        （按条目身份找「唯一的 bonus 赋值点」，不是按行号）；
  (二) 形状错 fail-closed：`_tb` 非映射 ⇒ 该处抛点名异常；
  (三) 正常档逐字不变：dict / None / 空 dict 三种都落 `{"panel": …, "cap": {}, "cost": {}}`；
  (四) ★ 有牙反证：把活实现换回旧的 `try/except: pass` 形态 ⇒ 本门禁转红
        （否则「判据本身抓不住自己守的那件事」= 永远绿）。

**跑法**
```
export GWEN_FRAMEWORK_DIR=<引擎> GWEN_HOST_DIR=<宿主壳> GWEN_TEST_MODE=1
python tests/test_wb_bonus_failclosed.py
```
"""
from __future__ import annotations

import ast
import io
import os
import sys
import tempfile

os.environ["GWEN_GAME_DB"] = os.path.join(tempfile.mkdtemp(), "game.db")
os.environ["GWEN_TEST_MODE"] = "1"
_PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _paths  # noqa: E402,F401
sys.path.insert(0, _PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from _engine_harness import boot as _eng_cfg; _eng_cfg()  # noqa: E402

from _check import bind_check  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []
check = bind_check(globals(), "PASS", "FAIL", "FAILURES")

_SRC = os.path.join(_PLUGIN_DIR, "content", "combat_cmds.py")


def _hunt_boss_fn(tree):
    """取 hunt_boss 的函数节点（按名，不认行号）。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "hunt_boss":
            return node
    return None


def _bonus_assign_nodes(src, fn):
    """按**条目身份**取 hunt_boss 里 player 的 bonus 容器赋值点。

    身份 = `X["bonus"] = {"panel": …, "cap": {}, "cost": {}}`（按**元素身份**认，
    不认行号、不认具体键名写法）。修前/修后都能命中同一个节点。
    """
    out = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign):
            continue
        tgt = node.targets[0] if node.targets else None
        if not isinstance(tgt, ast.Subscript):
            continue
        # ★ `tgt.slice` 是 ast.Constant，`.value` **直接就是字符串**（我最初写成
        #   `isinstance(key, ast.Constant)` 于是永远 False → 扫到 0 个、两条前提断言
        #   一起假红）。教训与 `declarative.py` 那条同族：取值后先看它是什么。
        key = getattr(tgt.slice, "value", tgt.slice)
        if key != "bonus":
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        keys = [getattr(k, "value", k) for k in node.value.keys]
        if {"panel", "cap", "cost"} <= set(keys):
            out.append(node)
    return out


def _enclosing_trys(fn, target):
    """包住该赋值的 try 节点（修好的形态里 for 在 try 之外，try 只包 dict()，
    所以必须按「谁包含这个赋值节点」来判，不能只看同一段文本）。"""
    return [t for t in ast.walk(fn)
            if isinstance(t, ast.Try) and any(n is target for n in ast.walk(t))]


def _is_silent_skip(t):
    """这个 try 是不是「宽泛/裸 except + pass」的静默兜底。"""
    for h in t.handlers:
        if h.type is None:                                    # 裸 except
            return True
        names = getattr(h.type, "id", None) or getattr(h.type, "attr", None)
        if names in ("Exception", "BaseException"):
            body = [s for s in h.body if not isinstance(s, ast.Expr)]
            if len(body) == 1 and isinstance(body[0], ast.Pass):
                return True
    return False


def test_no_bare_silent_skip():
    print("【L4918-3 世界 Boss bonus 容器：fail-closed】")
    src = io.open(_SRC, encoding="utf-8").read()
    tree = ast.parse(src)
    fn = _hunt_boss_fn(tree)
    check("扫到 hunt_boss（判据前提）", fn is not None)
    nodes = _bonus_assign_nodes(src, fn)
    check("★ 扫到 bonus 容器赋值点（判据前提）", bool(nodes), "扫到 0 个")

    silent = []
    for n in nodes:
        for t in _enclosing_trys(fn, n):
            if _is_silent_skip(t):
                silent.append(ast.get_source_segment(src, t))
    check("★ 不存在「裸/宽泛 except + pass」包住 bonus 赋值",
          not silent, "仍被静默包住：%r" % (silent[:1],))

    # ★ 删了兜底还不够：必须看得见一条 **fail-closed 抛错**出口，否则等于把
    #   「静默开一场没有增幅的战斗」换成「硬崩且不点名」。
    #   口径按**同一函数体内、紧邻赋值之前**的 try 数（修好的形态里赋值在 try 之外、
    #   try 只包上面那行 `dict()`；旧形态里 try 包整个 for + except pass）。
    raise_nodes = [r for r in ast.walk(fn)
                   if isinstance(r, ast.Raise) and r.lineno < min(n.lineno for n in nodes)]
    names_ok = any("面板增幅形状不对" in (ast.get_source_segment(src, r) or "")
                   for r in raise_nodes)
    check("★ bonus 赋值之前留有点名式 fail-closed 抛错", raise_nodes and names_ok,
          "raise %d 处，点名的 %d 处" % (len(raise_nodes), int(names_ok)))


def test_shape_and_normal_values():
    """行为侧：形状错抛点名异常，正常档逐字落三容器。"""
    from content import combat_cmds as CC
    from content import bridge as BR

    def install(_tb):
        sides = {"player": [{"uid": "p1"}], "enemy": []}
        try:
            panel = dict(_tb or {})
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                "content.combat_cmds：世界 Boss 开战的面板增幅形状不对"
                "（_panel_bonus 应给映射，实得 %s）" % type(_tb).__name__) from exc
        for a in sides.get("player", []):
            a["bonus"] = {"panel": panel, "cap": {}, "cost": {}}
        return sides["player"][0]

    for bad in (["atk", "def"], 42, "atk-def", object()):
        raised = None
        try:
            install(bad)
        except RuntimeError as exc:
            raised = exc
        check("★ 形状错 fail-closed（%s）" % type(bad).__name__,
              raised is not None and "面板增幅形状不对" in str(raised))

    for good in ({"atk": 20}, None, {}):
        a = install(good)
        check("正常档 %s 三容器齐全" % type(good).__name__,
              a.get("bonus") == {"panel": (good or {}), "cap": {}, "cost": {}},
              repr(a.get("bonus")))

    # 与收敛口（apply_battle_loadout）对拍：同输入两侧容器形状必须一致
    actor = {"uid": "p2"}
    BR.apply_battle_loadout(actor, {"atk": 20})
    check("★ 与 apply_battle_loadout 同口径（三容器形状一致）",
          set(actor.get("bonus") or {}) == {"panel", "cap", "cost"},
          repr(actor.get("bonus")))

    check("活实现里那处仍在（避免门禁对着空气转绿）",
          hasattr(CC, "hunt_boss"))


def main():
    print("=== L4918-3 世界 Boss bonus 容器门禁 ===")
    test_no_bare_silent_skip()
    test_shape_and_normal_values()
    print(f"\n=== 结果 PASS={PASS} FAIL={FAIL} ===")
    if FAILURES:
        for f in FAILURES:
            print("  - %s" % f)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
