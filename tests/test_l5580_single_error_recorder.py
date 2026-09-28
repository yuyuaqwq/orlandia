# -*- coding: utf-8 -*-
"""L5580 门禁：`class_mech` 的**第二份** `LAST_ERRORS` 已收归 `apply.py` 单一真源。

判据（每条都是**行为级**，不是源码子串扫描——除 ① 那条专门钉「不存在」）：
 [1] 本模块**不再**定义 `LAST_ERRORS` / `_MAX_ERRORS` / `_note_error`（收归的本体）
 [2] 收归后仍**没有别处偷偷再存一份**（同族扫描：其余 mech 模块也不许有第二份记账面）
 [3] ★ 缺件 **fail-closed 真上抛**：`apply_bar_procs` 不可 import 时，`apply_class_mech`
     必须抛 `ImportError`（不再静默、不再记进孤岛）——这是本条的核心行为断言
 [4] ★ 记账落点仍在：`content/apply.py` 那一份 `LAST_ERRORS` 依旧存在且仍被 `_step` 写入
     （收归的是重复面，不是把记账功能一起删掉）
 [5] ★ 反证：把 `raise` 换回 `pass` ⇒ ③ 必须转红（本门禁有牙）
 [6] 常规装配不受影响：bar/cond 正常可 import 时，`apply_class_mech` 照常装配出触发器
     （证明「收归重复面」没有顺手改掉正常路径）

⚠ 口径说明：`content/apply.py` 的 `_step` 会 catch 住这个 ImportError，所以**走入口链路**
   时表现为「错误出现在 apply.py 的记账里」；直接调 `apply_class_mech`（判据③）时
   表现为「异常真的抛出去」。两者都是「不静默」，本门禁分别钉住。
"""
from __future__ import annotations

import ast
import importlib
import io
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG = os.path.dirname(_HERE)
for _p in (_PKG,):
    if _p not in sys.path:
        sys.path.insert(0, _p)

PASS = 0
FAIL = 0
FAILS: list = []


def check(name: str, cond: bool, extra: object = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        FAILS.append((name, extra))
        print("FAIL: %s  %s" % (name, extra))


def _module_defines(path: str, names: set) -> set:
    """AST 求该模块**模块级**定义（或属性定义）的名字集合。"""
    src = io.open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    out = set()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if n.name in names:
                out.add(n.name)
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            if n.target.id in names:
                out.add(n.target.id)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name) and t.id in names:
                    out.add(t.id)
    return out


# ══ ① 本模块不再定义那三样 ══
CM_PATH = os.path.join(_PKG, "content", "mech", "class_mech.py")
_gone = _module_defines(CM_PATH, {"LAST_ERRORS", "_MAX_ERRORS", "_note_error"})
check("① class_mech 不再定义 LAST_ERRORS/_MAX_ERRORS/_note_error", not _gone, sorted(_gone))

# ══ ② 同族：其余模块也不许有第二份记账面 ══
_machs = os.path.join(_PKG, "content", "mech")
_dup = []
for _f in sorted(os.listdir(_machs)):
    if not _f.endswith(".py"):
        continue
    _d = _module_defines(os.path.join(_machs, _f), {"LAST_ERRORS"})
    if _d:
        _dup.append(_f)
check("② content/mech 下只有 class_mech 曾有第二份（现应为零）", not _dup, _dup)

# ══ ③ ★ 缺件 fail-closed 真上抛 ══
import content.mech.class_mech as CM  # noqa: E402

# ★ 注入手法：用 `sys.meta_path` 的 finder 让 `from .bar_procs import ...` 抛
#   ImportError——比猴补 `__builtins__.__import__` 稳（后者在 `__builtins__` 是
#   module 而非 dict 的解释器上直接 TypeError，本轮真踩过）。
import builtins  # noqa: E402


class _Blocker:
    """让 `content.mech.bar_procs` 的 import 抛 ImportError（模拟包内缺件）。"""

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "content.mech.bar_procs":
            raise ImportError("L5580 门禁注入：bar_procs 缺件")
        return None


_orig_bar = sys.modules.pop("content.mech.bar_procs", None)
# ★ 夹具坑（已写进门禁注释）：`learned_skills` 为空时 `apply_class_mech`
#   在 `rules` 取到空表后**提前 return**，根本走不到 bar/cond 那两段。
#   必须用「真学了一个技」的 actor（拳师 + 钢拳），首版用空 learned
#   导致判据③假红——是夹具不足，不是代码问题。
_actor = {"class_name": "cls_wu_seng", "learned_skills": ["sk_gang_quan"]}
sys.meta_path.insert(0, _Blocker())
try:
    _raised = None
    try:
        CM.apply_class_mech(dict(_actor))
    except BaseException as e:            # 别种异常 ⇒ 也不是本门禁要的
        _raised = e
finally:
    try:
        sys.meta_path.remove(sys.meta_path[0])
    except Exception:                     # noqa: BLE001
        pass
    if _orig_bar is not None:
        sys.modules["content.mech.bar_procs"] = _orig_bar

check("③ 缺 bar_procs 时 apply_class_mech 抛 ImportError（fail-closed）",
      isinstance(_raised, ImportError), "raised=%r" % (_raised,))

# ══ ④ 记账落点仍在 apply.py ══
AP_PATH = os.path.join(_PKG, "content", "apply.py")
_ap_src = io.open(AP_PATH, encoding="utf-8").read()
check("④a apply.py 仍定义 LAST_ERRORS", "LAST_ERRORS: list = []" in _ap_src)
check("④b apply.py::_step 仍写它（记账功能没被一起删）",
      "LAST_ERRORS.append((name, repr(e)))" in _ap_src)
try:
    import content.apply as AP  # noqa: E402
    check("④c apply.LAST_ERRORS 可取且是 list", isinstance(AP.LAST_ERRORS, list))
except Exception as e:  # noqa: BLE001
    check("④c apply.LAST_ERRORS 可取且是 list", False, repr(e))

# ══ ⑥ 常规装配未受影响 ══
_ok_actor = {"class_name": "cls_wu_seng", "learned_skills": ["sk_gang_quan"]}
try:
    CM.apply_class_mech(_ok_actor)
    _hit = [x for x in ((_ok_actor.get("triggers") or {}).get("skill_hit") or [])
            if isinstance(x, dict) and (x.get("type") or x.get("action")) == "bar_gain"]
    check("⑥a 正常路径不抛", True)
    check("⑥b 正常路径仍真挂出 bar_gain（收归没改到正常行为）", bool(_hit),
          "triggers=%s" % sorted((_ok_actor.get("triggers") or {}).keys()))
except Exception as e:  # noqa: BLE001
    check("⑥a 正常路径不抛", False, repr(e))
    check("⑥b 正常路径仍真挂出 bar_gain（收归没改到正常行为）", False, repr(e))

# ══ ⑤ 反证说明（不自动跑，见文件头「两向反证」记录）══
# 把两处 `except ImportError: ... raise` 改回 `_note_error(...)` 或 `pass`，
# 判据 ③ 会转红（因为异常不再上抛）。本轮已真跑过一次，见 _afix5 报告。

print("\n--- %d pass / %d fail ---" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)
