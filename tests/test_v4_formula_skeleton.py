# -*- coding: utf-8 -*-
"""V4 门禁：引擎「写死游戏数值」下沉后，内容侧两处（JSON 真源 / 挂载面）逐值一致。

背景（V4 作业书 §3）
--------------------
引擎 `saintess_engine/battle/{effects,landing,actions,formulas}.py` 与
`saintess_engine/gauge/__init__.py` 里最后 7 处写死的游戏数值，下沉到**既有的**
`FORMULA_SKELETON` / `formula_skeleton_fn` 注入面（不新开第二张表）：

    shield_default_pct  护盾兜底（含 shield_pct 缺省）      0.20
    block               cap 0.40 / reduce 0.5
    heal_down           per_stack 0.10 / cap 0.50
    anti_heal           cap 0.80
    reduce              default_pct 0.20 / cap 0.9
    gauge               default_max 100
    skill_max_level     5

本测试钉三件事（**缺一即红**）
------------------------------
A. **两处同值**：`content/rules/game_config.json` 的 `formula_skeleton.FORMULA_SKELETON`
   与挂载面 `content/mech/params.py:FORMULA_SKELETON` 的 7 组**逐值相等**
   （改一处忘另一处 = 真源漂移）。
B. **引擎真读内容侧**：`formulas` 的具名 getter 读的是挂载表（改挂载表 → getter 跟着变）。
C. **未装配 → 中性不崩**：卸掉 `formula_skeleton_fn` 后 getter 全部可调、返回中性值
   （零效应语义，见 `formulas._NEUTRAL_SKELETON`）。

路径装配为何**不硬依赖** `tests/_paths.py`
------------------------------------------
`_paths` 要求发现宿主壳根（`<root>/host/shell.py`）—— 那是**部署树**才有的半边；
本仓（以及只有 `pkg/` + `eng/` 的镜像）里不存在，`_paths` 会按设计**醒目报错**而非静默跳过。
本文件只做「纯值 / getter」三件事，不需要宿主壳 ⇒ 捕获 `_paths` 的 RuntimeError 后
**打印警告并自装配两个根**（包根 + 引擎根），继续把 A/B/C 三条跑完 —— 不是静默 skip，
打印面 + 断言面都保留。能发现 `_paths` 时仍优先用它（与全仓口径一致）。

跑法：python tests/test_v4_formula_skeleton.py   （pytest 亦可）
"""
from __future__ import annotations

import json
import os
import sys
import warnings

_HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(_HERE)
_ENGINE_CANDIDATES = (
    os.environ.get("GWEN_FRAMEWORK_DIR") or "",
    os.path.join(os.path.dirname(PKG_ROOT), "framework"),
    os.path.dirname(PKG_ROOT),
    os.path.join(PKG_ROOT, "framework"),
)

if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

_discovered = False
try:
    import _paths                                                       # noqa: E402
    PKG_ROOT = _paths.PKG_ROOT
    ENGINE_ROOT = _paths.ENGINE_ROOT
    _discovered = True
except Exception as exc:                                                # noqa: BLE001
    ENGINE_ROOT = next((p for p in _ENGINE_CANDIDATES
                        if p and os.path.isfile(os.path.join(p, "saintess_engine", "package.py"))),
                       "")
    for _p in (ENGINE_ROOT, PKG_ROOT, _HERE):
        if _p and _p in sys.path:
            sys.path.remove(_p)
        if _p:
            sys.path.insert(0, _p)
    warnings.warn("未发现宿主壳根（%s）→ 用自装配路径跑纯值门禁；"
                  "包根=%s 引擎根=%s" % (type(exc).__name__, PKG_ROOT, ENGINE_ROOT),
                  RuntimeWarning, stacklevel=2)
    print("   ⚠️ _paths 未装配（%s: %s）—— 退化为纯值门禁（不影响 A/B/C 三条）"
          % (type(exc).__name__, str(exc)[:80]))

from saintess_engine import config as CFG                                # noqa: E402
from saintess_engine.battle import formulas as F                         # noqa: E402
from content.mech import params as P                                     # noqa: E402

#: 本批下沉的 7 组（JSON 真源 ↔ 引擎挂载面）
V4_GROUPS = (
    "shield_default_pct", "block", "heal_down", "anti_heal",
    "reduce", "gauge", "skill_max_level",
)

PASS = FAIL = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ✅ %s" % name)
    else:
        FAIL += 1
        FAILURES.append("%s: %s" % (name, detail))
        print("  ❌ %s  %s" % (name, detail))


def _json_skeleton() -> dict:
    """读包内 `content/rules/game_config.json` 的 formula_skeleton 组（**内容真源**）。"""
    path = os.path.join(PKG_ROOT, "content", "rules", "game_config.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return ((data.get("formula_skeleton") or {}).get("FORMULA_SKELETON") or {})


# ============================================================
# A. 两处同值（JSON 真源 ↔ 引擎挂载面）
# ============================================================

def test_two_sides_equal():
    print("【A. content/rules/game_config.json ↔ content/mech/params.py 逐值相等】")
    js = _json_skeleton()
    for key in V4_GROUPS:
        check("JSON 声明了 %s" % key, key in js, "JSON 键=%s" % sorted(js.keys())[:40])
        check("挂载面声明了 %s" % key, key in P.FORMULA_SKELETON,
              "params 键=%s" % sorted(P.FORMULA_SKELETON.keys()))
        check("%s 逐值相等（JSON=%r / params=%r）"
              % (key, js.get(key), P.FORMULA_SKELETON.get(key)),
              js.get(key) == P.FORMULA_SKELETON.get(key),
              "JSON=%r params=%r" % (js.get(key), P.FORMULA_SKELETON.get(key)))
    # 历史两段也要继续同值（skill_growth / skill_learn_cost）
    for key in ("skill_growth", "skill_learn_cost"):
        check("历史段 %s 仍逐值相等" % key,
              js.get(key) == P.FORMULA_SKELETON.get(key),
              "JSON=%r params=%r" % (js.get(key), P.FORMULA_SKELETON.get(key)))


# ============================================================
# B. 引擎真读内容侧（挂载表 → getter）
# ============================================================

GETTERS = (
    ("shield_default_pct", lambda: F.shield_default_pct(), 0.20),
    ("block.cap", lambda: F.block_cap(), 0.40),
    ("block.reduce", lambda: F.block_reduce(), 0.5),
    ("heal_down.per_stack", lambda: F.heal_down_per_stack(), 0.10),
    ("heal_down.cap", lambda: F.heal_down_cap(), 0.50),
    ("anti_heal.cap", lambda: F.anti_heal_cap(), 0.80),
    ("reduce.default_pct", lambda: F.reduce_default_pct(), 0.20),
    ("reduce.cap", lambda: F.reduce_cap(), 0.9),
    ("gauge.default_max", lambda: F.gauge_default_max(), 100.0),
    ("skill_max_level", lambda: F.skill_max_level_default(), 5),
)


def test_engine_reads_content():
    print("【B. 引擎 getter 读挂载表（装配后 = 内容声明值）】")
    CFG._hook_provider = None
    CFG.mount(formulas=F, formula_skeleton_fn=P.formula_skeleton)
    try:
        for label, fn, want in GETTERS:
            got = fn()
            check("%s → %r" % (label, want), got == want, "got=%r" % (got,))
        # 反向证据：改挂载表 → getter 跟着变（证明确实读内容侧，不是第二份常量）
        saved = P.FORMULA_SKELETON["shield_default_pct"]
        try:
            P.FORMULA_SKELETON["shield_default_pct"] = 0.35
            check("挂载表改 0.35 → getter 0.35（真读内容侧）",
                  F.shield_default_pct() == 0.35, "got=%r" % F.shield_default_pct())
        finally:
            P.FORMULA_SKELETON["shield_default_pct"] = saved
        check("还原后 getter = 0.20", F.shield_default_pct() == 0.20,
              "got=%r" % F.shield_default_pct())
    finally:
        CFG._HOOKS["formula_skeleton_fn"] = None


# ============================================================
# C. 未装配 → 中性不崩
# ============================================================

def test_neutral_path():
    print("【C. 未装配骨架 → 中性值、不崩（_NEUTRAL_SKELETON）】")
    CFG._hook_provider = None
    CFG._HOOKS["formula_skeleton_fn"] = None
    try:
        for label, fn, _want in GETTERS:
            try:
                got = fn()
                check("%s 未装配可调 → %r" % (label, got), isinstance(got, (int, float)),
                      "%r (%s)" % (got, type(got).__name__))
            except Exception as exc:                            # noqa: BLE001
                check("%s 未装配可调" % label, False, "%s: %s" % (type(exc).__name__, exc))
        # 中性语义（零效应）逐条钉住
        check("中性 block.cap = 0（不格挡）", F.block_cap() == 0.0, "%r" % F.block_cap())
        check("中性 heal_down.per_stack = 0（不减疗）",
              F.heal_down_per_stack() == 0.0, "%r" % F.heal_down_per_stack())
        check("中性 anti_heal.cap = 0", F.anti_heal_cap() == 0.0, "%r" % F.anti_heal_cap())
        check("中性 reduce.default_pct = 0", F.reduce_default_pct() == 0.0,
              "%r" % F.reduce_default_pct())
        check("中性 gauge.default_max = 0（调用处回落 100）",
              F.gauge_default_max() == 0.0, "%r" % F.gauge_default_max())
        check("中性 skill_max_level = 5（技能等级兜底语义不变）",
              F.skill_max_level_default() == 5, "%r" % F.skill_max_level_default())
        check("未装配 skill_max_level(None) == 5", F.skill_max_level(None) == 5,
              "%r" % F.skill_max_level(None))
    finally:
        CFG.mount(formulas=F, formula_skeleton_fn=P.formula_skeleton)


if __name__ == "__main__":
    test_two_sides_equal()
    test_engine_reads_content()
    test_neutral_path()
    print("\n== 结果：通过 %d / 共 %d ==" % (PASS, PASS + FAIL))
    if FAILURES:
        for f in FAILURES:
            print("  FAIL: %s" % f)
        sys.exit(1)
    print("全绿 ✅")
