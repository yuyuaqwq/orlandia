# -*- coding: utf-8 -*-
"""N5 验收：serialize 序列化（to_state/from_state 往返 + 续战）。

覆盖：
- to_state → JSON 化 dict → from_state 重建：sides/hp/state/buffs/ct 完整
- 重建后战斗能继续（续战：from_state 后继续 auto_run 到结束）
- killed 击杀记录恢复
- 中途状态（打了一半的血）保留

跑法：python tests/test_battle_n5_serialize.py
"""
import os
import sys
import json
import random

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
TEST_DB = os.path.join(PLUGIN_DIR, "test_battle_n5.db")
os.environ.setdefault("GWEN_GAME_DB", TEST_DB)
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from _engine_harness import boot as _eng_cfg; _eng_cfg()  # noqa: E402
from content.panel import player_final_stats
from ext_combat import Battle as BT_NEW, make_actor  # noqa: E402
from saintess_engine import config as _b2config  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")



def stk(a, k, d=0):
    """V 系列：读效果叠层数 effects[key].stacks。"""
    e = (a or {}).get("effects") or {}
    ent = e.get(k)
    return int(ent.get("stacks", 0) or 0) if isinstance(ent, dict) else int(d)


def ent(a, k):
    """V 系列：读效果条目 dict effects[key]。"""
    e = (a or {}).get("effects") or {}
    return e.get(k) or {}


def mk_player(cls="战士", level=10):
    st = player_final_stats(cls, level, {}, 0, {}, 1)
    return make_actor(uid="p_q1", name="测试勇者", side="player", kind="player",
                      human_controlled=True, class_name=cls, level=level,
                      hp=int(st["max_hp"]), max_hp=int(st["max_hp"]),
                      mp=int(st["max_mp"]), max_mp=int(st["max_mp"]),
                      equipment={}, skills=[], learned_skills=[],
                      race=None, evolve_path=1, class_tier=0, attributes={},
                      **{k: st[k] for k in ("atk", "matk", "def", "mdef", "spd", "crit") if k in st})


def mk_monster(hp=200, atk=5):
    return make_actor(uid="e_0", name="野狼", side="enemy", kind="monster",
                      hp=hp, max_hp=hp, atk=atk, **{"def": 5},
                      matk=5, mdef=5, spd=5, crit=0.05, level=5)


def test_roundtrip_full():
    print("【N5.1 往返：to_state → JSON → from_state 状态完整】")
    p = mk_player("战士", 10)
    m = mk_monster()
    b = BT_NEW(btype="monster", sides={"player": [p], "enemy": [m]})
    # 打一半状态：玩家放技能/挂 state
    from ext_combat.battle import effects as FX
    p["effects"]["zhan_yi"] = {"stacks": 3}
    p["effects"]["atk_up"] = {"stacks": 4}
    m["effects"]["burn"] = {"stacks": 2}
    p["hp"] = 123
    m["hp"] = 77
    # 序列化
    st = b.to_state()
    check("to_state 有 sides", "sides" in st and "player" in st["sides"] and "enemy" in st["sides"])
    # JSON 化（模拟 DB 存取）
    js = json.dumps(st, ensure_ascii=False, default=str)
    st2 = json.loads(js)
    # 恢复
    b2 = BT_NEW.from_state(st2)
    p2 = b2.sides["player"][0]
    m2 = b2.sides["enemy"][0]
    check("sides 重建", len(b2.sides["player"]) == 1 and len(b2.sides["enemy"]) == 1)
    check("玩家 hp 保留", p2["hp"] == 123, f"hp={p2['hp']}")
    check("玩家 zhan_yi 保留", stk(p2, "zhan_yi", 0) == 3)
    check("玩家 buffs 保留", stk(p2, "atk_up", 0) == 4)
    check("怪 hp 保留", m2["hp"] == 77, f"hp={m2['hp']}")
    check("怪 burn 保留", stk(m2, "burn", 0) == 2)
    check("玩家 class_name 保留", p2["class_name"] == "战士")
    check("玩家 level 保留", p2["level"] == 10)


def test_continue_after_restore():
    print("【N5.2 续战：from_state 后战斗能继续打完】")
    p = mk_player("战士", 12)
    m = mk_monster(hp=150, atk=5)
    b = BT_NEW(btype="monster", sides={"player": [p], "enemy": [m]})
    # 打一下（中途存档）
    logs0, _, _ = b.human_act("attack", None, p)
    mid_hp = m["hp"]
    st = b.to_state()
    b2 = BT_NEW.from_state(st)
    p2 = b2.sides["player"][0]
    m2 = b2.sides["enemy"][0]
    check("恢复后怪 hp 与中断时一致", m2["hp"] == mid_hp, f"m2={m2['hp']} mid={mid_hp}")
    # 续战打完
    logs = []
    b2.auto_run(logs)
    check("续战能打完", b2.result in ("victory", "defeat"), f"result={b2.result}")


def test_result_preserved():
    print("【N5.3 result/击杀恢复】")
    p = mk_player("战士", 20)
    m = mk_monster(hp=30, atk=1)
    b = BT_NEW(btype="monster", sides={"player": [p], "enemy": [m]})
    logs = []
    b.auto_run(logs)
    check("原战斗 victory", b.result == "victory")
    st = b.to_state()
    b2 = BT_NEW.from_state(st)
    check("恢复后 result 保留", b2.result == "victory", f"result={b2.result}")
    check("击杀记录恢复", len(b2.killed_actors) >= 1,
          f"killed={len(b2.killed_actors)}")


def main():
    print("=== N5 saintess_engine 序列化测试 ===")
    test_roundtrip_full()
    test_continue_after_restore()
    test_result_preserved()
    print(f"\n=== 结果 PASS={PASS} FAIL={FAIL} ===")
    if FAILURES:
        for f in FAILURES:
            print(f"  - {f}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
