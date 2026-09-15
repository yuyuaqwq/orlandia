# -*- coding: utf-8 -*-
"""v130.7 越级风险增强固化测试（玩家意见 #28）

覆盖：
  ① 移动撞怪 _travel_ambush 普通图：撞怪概率随等级差提升
     diff=5 → 0.30、diff=10 → 0.55(=0.30+5*0.05)、diff=20 → 0.60(cap)；
     diff=0 → 0.18、diff=-3 → 0.08 不变；diff≤-5 → 威慑不撞
  ② 副本图分支不回归（diff≥5 仍 0.30）、城镇不撞
  ③ 探索随机事件：地图等级高于玩家时每高 1 级 +5%（cap +25% → 0.60 顶格 clamp）
  ④ 同级无加成回归、城镇探索回归

运行：python tests/test_v1307_zone_risk.py（exit=0 全绿）
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _engine_harness import C, db, clean_db, Main, FakeEvent, run, make_player  # noqa: E402

# `content.combat_cmds` 的探索期耦合（`_overlay` / `_attach_tlog` 注入槽）——见下。
from _engine_harness import tlog_setup as _tlog_setup  # noqa: E402
from content.tlog_collect import BattleTLog as _BattleTLog  # noqa: E402
from content import combat_cmds as _combat_cmds  # noqa: E402
_tlog_setup.disable()   # 未启用流水 → attach 零行为


def _host_attach_tlog(b, *, btype="monster", player=None, enemies=None, seed=None):
    """`game/services/battle_bridge.py::attach_tlog` 的测试侧同款（平台件，旧宿主薄壳）。"""
    try:
        tl = _tlog_setup.tlog()
        if tl is None:
            return b
        _BattleTLog(tl).attach(b, btype=btype, seed=seed, player=player, enemies=enemies)
    except Exception:                                            # noqa: BLE001
        pass
    return b


_combat_cmds.bind_host(attach_tlog=_host_attach_tlog)

passed = failed = 0
G = 1095961596
MARKER = "【越级事件·危机】"
GP = C.MAP_BY_ID["gold_plain"]       # 金穗平原：野外 lv30，入口子区域 gold_plain_1 有怪池
TOWN = C.MAP_BY_ID["oak_town"]       # 城镇区域（安全区）
INSTANCE = C.MAP_BY_ID["goblin_camp"]  # 副本 lv15
FAKE_MON = ("m_goblin_test", "戈布林测试王", "boss", 15, [], [])


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")


def _ambush(m, level, rnd):
    """直调 _travel_ambush：玩家 level vs 金穗平原(lv30)，random.random 钉死为 rnd。"""
    orig = random.random
    try:
        random.random = lambda: rnd
        r = m._travel_ambush({"level": level}, GP)
        return r is not None, r
    finally:
        random.random = orig


async def _explore(m, qid, level, rnd, map_id="gold_plain"):
    """完整探索流程：玩家落在 map_id 地图，random.random 钉死为 rnd，返回输出文本。

    v173.3：patch explore_king 返回 None——野王按日期+时段哈希 spawn（金穗平原可能
    被选中），探索会优先撞野王导致测试断言普通探索事件失败。本测试只关心等级差事件率，
    屏蔽野王保证确定性。
    """
    from content import combat_cmds as _combat_mod
    clean_db()
    make_player(G, qid, "越级测试", "战士", level=level)
    db.update_player(G, qid, cur_map=map_id)  # cur_subarea 自动补首个子区域
    orig = random.random
    _orig_ek = _combat_mod.explore_king
    _combat_mod.explore_king = lambda g, q, cm: None  # 屏蔽野王
    try:
        random.random = lambda: rnd
        ev = FakeEvent(G, qid, "探索")
        out = await run(m.explore, ev)
    finally:
        random.random = orig
        _combat_mod.explore_king = _orig_ek
    return "".join(str(x) for x in out)


def _ambush_case(m, name, level, rnd_hit, expect_hit, detail=""):
    hit, r = _ambush(m, level, rnd_hit)
    check(f"{name}（rnd={rnd_hit}）", hit is expect_hit and (not expect_hit or isinstance(r, dict)),
          f"hit={hit} r={r}")
    return hit


async def main():
    clean_db()
    m = Main(None)

    # 日期/环境依赖打桩：今日奇遇（event_chance 会扰动事件率探针）、野外 NPC 偶遇（日期轮换）。
    # ★ 终态打桩落点 = 包内命令模块 `content.combat_cmds`（见其 `_overlay` / `_wild_king`：
    #   包内直取优先 + 命令模块属性覆写面）。
    from content import combat_cmds as _cc
    _orig_tde = _cc.today_event_effects
    _orig_wild = _cc.roll_wild_encounter
    _cc.today_event_effects = lambda map_id: {}
    _cc.roll_wild_encounter = lambda *a, **k: None
    # 越级事件命中 → 直接返回标记文本（不跑真实事件模板，防随机消耗与 DB 依赖）。
    # ★ 终态打桩落点 = 包内模块函数本体（`_engine_harness.Main.__getattr__` 按
    #   `fn.__module__ == 所属模块` 校验 ⇒ 必须先保存原函数再改绑，桩函数带 `_binds_shell` 签名）。
    _orig_hev = _cc._handle_explore_event

    def _hev_stub(self, *a, **k):
        return (True, MARKER)

    _hev_stub.__module__ = _cc.__name__
    _cc._handle_explore_event = _hev_stub
    _orig_main = _cc._main_kill_target_on_map  # 副本分支用例会临时替换

    try:
        print("【① 移动撞怪：普通图概率随等级差提升（金穗平原 lv30）】")
        # diff=5（玩家 25 级）→ 0.30
        _ambush_case(m, "diff=5 → 0.30 命中(rnd=0.29)", 25, 0.29, True)
        _ambush_case(m, "diff=5 → 0.30 不命中(rnd=0.31)", 25, 0.31, False)
        # diff=10（玩家 20 级）→ 0.55 = 0.30 + (10-5)*0.05；旧逻辑 0.30 时 rnd=0.40 必不撞 → 判别点
        _ambush_case(m, "diff=10 → 0.55 命中(rnd=0.40)", 20, 0.40, True)
        _ambush_case(m, "diff=10 → 0.55 命中(rnd=0.54)", 20, 0.54, True)
        _ambush_case(m, "diff=10 → 0.55 不命中(rnd=0.55)", 20, 0.55, False)
        # diff=20（玩家 10 级）→ min(0.30+15*0.05, 0.60) = 0.60 cap
        _ambush_case(m, "diff=20 → 0.60 cap 命中(rnd=0.59)", 10, 0.59, True)
        _ambush_case(m, "diff=20 → 0.60 cap 不命中(rnd=0.61)", 10, 0.61, False)
        # diff=0 → 0.18 不变
        _ambush_case(m, "diff=0 → 0.18 命中(rnd=0.17)", 30, 0.17, True)
        _ambush_case(m, "diff=0 → 0.18 不命中(rnd=0.19)", 30, 0.19, False)
        # diff=-3 → 0.08 不变
        _ambush_case(m, "diff=-3 → 0.08 命中(rnd=0.07)", 33, 0.07, True)
        _ambush_case(m, "diff=-3 → 0.08 不命中(rnd=0.09)", 33, 0.09, False)
        # diff=-5 → 威慑不撞（玩家≥地图+5）
        hit, r = _ambush(m, 35, 0.0)
        check("diff=-5 → 威慑不撞(rnd=0.0)", not hit, f"hit={hit}")
        hit, r = _ambush(m, 35, 0.99)
        check("diff=-5 → 威慑不撞(rnd=0.99)", not hit, f"hit={hit}")

        print("【② 副本/城镇不回归】")
        check("城镇不撞怪", m._travel_ambush({"level": 1}, TOWN) is None)
        check("副本无群上下文跳过(不撞)", m._travel_ambush({"level": 10}, INSTANCE) is None)
        # 副本分支（有主线目标）diff=5：chance 仍为 0.30（本轮改动不动副本分支）
        m._main_kill_target_on_map = lambda g, q, cm: FAKE_MON
        _mk_stub = lambda self, g, q, cm: FAKE_MON
        _mk_stub.__module__ = _cc.__name__
        _cc._main_kill_target_on_map = _mk_stub
        orig = random.random
        try:
            random.random = lambda: 0.29
            r = m._travel_ambush({"level": 10}, INSTANCE, G, "zr_inst")
        finally:
            random.random = orig
        check("副本 diff=5 仍 0.30 命中(rnd=0.29)", isinstance(r, dict), f"r={r}")
        try:
            random.random = lambda: 0.31
            r2 = m._travel_ambush({"level": 10}, INSTANCE, G, "zr_inst")
        finally:
            random.random = orig
        check("副本 diff=5 仍 0.30 不命中(rnd=0.31)", r2 is None, f"r2={r2}")

        print("【③ 探索事件率：等级差加成（金穗平原 lv30）】")
        out = await _explore(m, "zr_gap2_hit", 28, 0.44)   # gap=2 → 0.45
        check("gap=2 → 0.45 触发事件(rnd=0.44)", MARKER in out, out[:100])
        out = await _explore(m, "zr_gap2_miss", 28, 0.46)
        check("gap=2 → 0.45 不触发(rnd=0.46)", MARKER not in out and out, out[:100])
        out = await _explore(m, "zr_gap10_hit", 20, 0.59)  # gap=10 → +25% cap → 0.60
        check("gap=10 → 0.60 触发事件(rnd=0.59)", MARKER in out, out[:100])
        out = await _explore(m, "zr_gap10_cap", 20, 0.61)
        check("gap=10 → 0.60 cap 不触发(rnd=0.61)", MARKER not in out and out, out[:100])
        out = await _explore(m, "zr_gap0", 30, 0.55)       # 同级 → 0.35 无加成
        check("同级(gap=0) → 0.35 不触发(rnd=0.55)", MARKER not in out and out, out[:100])

        print("【④ 城镇探索回归】")
        out = await _explore(m, "zr_town", 30, 0.99, map_id="oak_town")
        check("城镇探索安全区文案", "安全的城镇" in out, out[:100])
    finally:
        _cc.today_event_effects = _orig_tde
        _cc.roll_wild_encounter = _orig_wild
        _cc._handle_explore_event = _orig_hev
        _cc._main_kill_target_on_map = _orig_main

    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)


os_asy = __import__("asyncio")
os_asy.run(main())