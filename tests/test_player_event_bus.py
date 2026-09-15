# -*- coding: utf-8 -*-
"""L3-P1 玩家事件总线纯单元测试（零游戏模块依赖，独立运行）。

跑法：python tests/test_player_event_bus.py
覆盖（任务书 §7）：
- 注册顺序保序 / blank=False 不补空行 / blank=True 补空行三态
- 异常订阅不阻断后续 / 返回 None 与 [] 等价
- 未知事件 register raise + fire 空跑
- 重复注册 append 顺序 / ctx.player 重绑可见 / side_effects 通道 / lines 预置追加
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/（`_engine_harness`）

from _engine_harness import boot as _eng_cfg; _eng_cfg()  # 包路径 + 引擎装配（幂等；旧壳 import 期同语义）

from content.player_events import EVENTS, clear_registry, fire, register

_fail = []


def _check(name, cond):
    if cond:
        print(f"  ✅ {name}")
    else:
        _fail.append(name)
        print(f"  ❌ {name}")


def _reset():
    clear_registry()
    _fail.clear()


def _mk_ctx(**kw):
    ctx = {"group_id": "g1", "qq_id": "q1", "player": {"level": 1}, "monster": {}, "killed": [],
           "kind": "field", "side_effects": []}
    ctx.update(kw)
    return ctx


def t_register_order():
    print("t_register_order 注册顺序保序 + 重复注册追加")
    order = []

    def a(ctx):
        order.append("a")
        return ["A"]

    def b(ctx):
        order.append("b")
        return ["B"]

    def a2(ctx):
        order.append("a2")
        return ["A2"]

    register("battle_victory", a, blank_line=False)
    register("battle_victory", b)
    register("battle_victory", a2)
    lines = fire("battle_victory", _mk_ctx())
    _check("执行顺序 a→b→a2", order == ["a", "b", "a2"])
    _check("行序 A→B→A2", lines == ["A", "", "B", "", "A2"])  # a blank=False; b/a2 blank=True 且前一行非空


def t_blank_rules():
    print("t_blank_rules blank 三态")
    clear_registry()
    calls = []

    def fa(ctx):
        return ["X"]

    def fb(ctx):
        return ["Y"]

    # 1) lines 预置且末行非空 + blank=True → 补空行；blank=False → 不补
    clear_registry()
    register("battle_victory", fa, blank_line=False)
    ctx = _mk_ctx(lines=["head"])
    lines = fire("battle_victory", ctx)
    _check("blank=False 紧跟 head", lines == ["head", "X"])
    clear_registry()
    register("battle_victory", fa, blank_line=True)
    lines = fire("battle_victory", _mk_ctx(lines=["head"]))
    _check("blank=True 前非空行补空行", lines == ["head", "", "X"])
    # 2) lines 空 → 不补
    clear_registry()
    register("battle_victory", fa, blank_line=True)
    lines = fire("battle_victory", _mk_ctx())
    _check("blank=True lines 空不补", lines == ["X"])
    # 3) 末行已空 → 不重复补
    clear_registry()
    register("battle_victory", fa, blank_line=True)
    lines = fire("battle_victory", _mk_ctx(lines=["head", ""]))
    _check("blank=True 末行已空不补", lines == ["head", "", "X"])
    # 4) 无行段不触发空行
    clear_registry()
    register("battle_victory", fa, blank_line=True)
    register("battle_victory", fb, blank_line=True)

    def empty(ctx):
        return []

    register("battle_victory", empty, blank_line=True)
    lines = fire("battle_victory", _mk_ctx(lines=["head"]))
    _check("空段不补空行、后续段照常", lines == ["head", "", "X", "", "Y"])


def t_none_vs_empty():
    print("t_none_vs_empty None 与 [] 等价")
    clear_registry()

    def fn_none(ctx):
        return None

    def fn_empty(ctx):
        return []

    register("battle_victory", fn_none)
    register("battle_victory", fn_empty)
    lines = fire("battle_victory", _mk_ctx(lines=["h"]))
    _check("两空段均跳过且不补空行", lines == ["h"])


def t_exception_isolation():
    print("t_exception_isolation 异常订阅不阻断")
    clear_registry()
    ran = []

    def boom(ctx):
        raise RuntimeError("boom")

    def ok(ctx):
        ran.append(1)
        return ["OK"]

    register("battle_victory", boom)
    register("battle_victory", ok)
    lines = fire("battle_victory", _mk_ctx())
    _check("异常后后续订阅仍执行", ran == [1])
    _check("异常订阅行被跳过", lines == ["OK"])


def t_unknown_event():
    print("t_unknown_event 未知事件")
    clear_registry()
    try:
        register("no_such_event", lambda ctx: [])
        _check("register 未知事件 raise", False)
    except ValueError:
        _check("register 未知事件 raise", True)
    lines = fire("no_such_event", _mk_ctx())
    _check("fire 未知事件返回 []", lines == [])
    # EVENTS 内但零订阅 → []（battle_defeat 起步态）
    lines = fire("battle_defeat", _mk_ctx())
    _check("EVENTS 内零订阅空跑", lines == [])


def t_ctx_mutation():
    print("t_ctx_mutation ctx 可变（player 重绑 / side_effects / event 自动补）")
    clear_registry()

    def levelup(ctx):
        ctx["player"] = {"level": 2}  # 重绑
        return ["LEVELUP"]

    def recorder(ctx):
        ctx["side_effects"].append({"type": "broadcast", "text": "👑 broadcast"})
        return ["ACH"]

    register("battle_victory", levelup, blank_line=False)
    register("battle_victory", recorder)
    ctx = _mk_ctx()
    lines = fire("battle_victory", ctx)
    _check("player 重绑对调用方可见", ctx["player"]["level"] == 2)
    _check("side_effects 被收集", ctx["side_effects"] == [{"type": "broadcast", "text": "👑 broadcast"}])
    _check("ctx.event 自动补", ctx["event"] == "battle_victory")
    _check("行收集含两段", lines == ["LEVELUP", "", "ACH"])
    # lines 预置追加
    lines2 = fire("battle_victory", _mk_ctx(lines=["tail?"]))
    _check("订阅方返回是覆盖判断（空行规则基于预置末行）", lines2 == ["tail?", "LEVELUP", "", "ACH"])


def main():
    print("== L3-P1 player_event_bus 单测 ==")
    print(f"EVENTS={EVENTS}")
    _reset()
    t_register_order()
    _reset()
    t_blank_rules()
    _reset()
    t_none_vs_empty()
    _reset()
    t_exception_isolation()
    _reset()
    t_unknown_event()
    _reset()
    t_ctx_mutation()
    print()
    if _fail:
        print(f"失败 {len(_fail)} 项：{_fail}")
        sys.exit(1)
    print("全部通过 ✅")


if __name__ == "__main__":
    main()
