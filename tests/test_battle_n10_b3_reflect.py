# -*- coding: utf-8 -*-
"""N10-B3：Boss mech reflect 被动反伤（血<25% 反弹 15%，永不致死；dot 不触发）。

跑法：python tests/test_battle_n10_b3_reflect.py（w1 内）
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_b2_n10b3.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _b2c
from _engine_harness import boot as _eng_cfg; _eng_cfg()
from saintess_engine import Battle as B2, make_actor  # noqa: E402
from saintess_engine import landing as L  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name}: {detail}")
        print(f"  ❌ {name} {detail}")


def make_reflect_boss(hp=1000, mech="reflect", bid="b_om_shadow", inst_id="", max_hp=None):
    """构造剧本 Boss actor：id=b_om_shadow（MONSTER_MODS 真实带 reflect mech token）。

    hp 可低于 max_hp（压血测血线反射）。
    """
    max_hp = max_hp if max_hp is not None else hp
    b = make_actor(uid="boss1", name="影袭者·奥姆", side="enemy", kind="monster",
                   role="boss", is_boss=True, hp=hp, max_hp=max_hp, atk=50, matk=30,
                   spd=10, crit=0.05, level=30, exp=0, gold=0,
                   **{"def": 30, "mdef": 20})
    b["id"] = bid
    b["mech"] = mech
    if inst_id:
        b["_inst_id"] = inst_id
    return b


def make_player(hp=2000):
    p = make_actor(uid="p1", name="勇者", side="player", kind="player",
                   human_controlled=True, class_name="cls_zhan_shi", level=30,
                   hp=hp, max_hp=hp, mp=300, max_mp=300,
                   atk=150, matk=80, spd=15, crit=0.05,
                   equipment={}, skills=[], learned_skills=[],
                   race=None, evolve_path=0, class_tier=0, attributes={},
                   **{"def": 50, "mdef": 30})
    return p


def script_battle(p, boss, inst_id="inst_goblin_camp"):
    """构造带剧本观察者的战斗（st 含 inst_id 供 boss_script_cfg 解析）。

    ★ B8.2 线5：Boss 剧本导演宿主副本已移出仓 → 读**包内端口** `content.flow.boss_script`
    （`content` 由 `_engine_harness.boot` 加载内容包时进 sys.path）。
    """
    from content.flow import boss_script as BS
    st = {"inst_id": inst_id, "boss_script": None}
    _obs = BS.make_script_event(st)
    b = B2(btype="instance", sides={"player": [p], "enemy": [boss]})
    b.on_event = _obs
    return b, st


def test_reflect_low_hp():
    print("【1. Boss 血<25% 受击 → 反弹 15% 给攻击者】")
    p = make_player()
    boss = make_reflect_boss(hp=200, max_hp=1000)  # 20% max
    b, st = script_battle(p, boss)
    L.deal_damage(b, p, boss, 100, [], dmg_kind="phys")
    lost = 2000 - p["hp"]
    check("攻击者受到反弹伤害 ~15", 10 <= lost <= 20, f"lost={lost} p_hp={p['hp']}")


def test_no_reflect_above_25():
    print("【2. Boss 血≥25% 受击 → 不反弹】")
    p = make_player()
    boss = make_reflect_boss(hp=400)  # 40% max 1000
    b, st = script_battle(p, boss)
    L.deal_damage(b, p, boss, 100, [], dmg_kind="phys")
    check("血≥25% 不反弹", p["hp"] == 2000, f"p_hp={p['hp']}")


def test_reflect_no_lethal():
    print("【3. 反伤永不致死（保底 1 HP）】")
    p = make_player(hp=5)
    boss = make_reflect_boss(hp=250, max_hp=1000)  # 25% 边界下；受 100 伤不死（剩 150）
    b, st = script_battle(p, boss)
    L.deal_damage(b, p, boss, 100, [], dmg_kind="phys")
    check("玩家保底 1 HP", p["hp"] == 1, f"p_hp={p['hp']}")


def test_reflect_no_mech():
    print("【4. 无 reflect mech token → 不反弹】")
    p = make_player()
    boss = make_reflect_boss(hp=100, mech="heal,summon")
    b, st = script_battle(p, boss)
    L.deal_damage(b, p, boss, 100, [], dmg_kind="phys")
    check("无 reflect 不反弹", p["hp"] == 2000, f"p_hp={p['hp']}")


def test_dot_no_reflect():
    print("【5. dot 无 source 不反弹（v1.3 语义）】")
    p = make_player()
    boss = make_reflect_boss(hp=200)
    b, st = script_battle(p, boss)
    L.deal_damage(b, None, boss, 50, [], dmg_kind="magi")  # source=None 模拟 DOT
    check("dot 不触发反射", p["hp"] == 2000, f"p_hp={p['hp']}")


if __name__ == "__main__":
    test_reflect_low_hp()
    test_no_reflect_above_25()
    test_reflect_no_lethal()
    test_reflect_no_mech()
    test_dot_no_reflect()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")
