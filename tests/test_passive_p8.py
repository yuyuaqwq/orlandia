# -*- coding: utf-8 -*-
"""v181.M-passive P8 测试——信念·圣化 过载回血增强（faith_overload_heal）。

跑法：python tests/test_passive_p8.py（exit=0 全绿）
覆盖（语义源 = 旧 passive_procs._h_tick_faith overload 段 ×(1+heal_up 0.3)）：
  1. 对照组：牧师无圣化 过载 → 全员回血 max_hp×0.015
  2. 圣化组：学过信念·圣化 → 过载回血 ×1.3（0.0195）
"""
import sys, os
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_passive_p8.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)

from saintess_engine import config as _b2c
from _engine_harness import boot as _eng_cfg; _eng_cfg()
from saintess_engine import Battle as B2, make_actor
from content.mech.class_mech import apply_class_mech

PASS = 0
FAIL = 0


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL")


def mk_priest(skills):
    a = make_actor(uid="p_1", name="牧师", side="player", kind="player",
                   human_controlled=True, class_name="cls_mu_shi", level=97,
                   learned_skills=list(skills), skills=list(skills),
                   atk=60, matk=200, spd=50, hp=5000, max_hp=5000, mp=500, max_mp=500)
    a['effects'] = {}
    a['bonus'] = {'panel': {}, 'cap': {}, 'cost': {}}
    return a


def mk_battle(player, hp=5000):
    e = make_actor(uid="e_1", name="木桩", side="enemy", kind="monster",
                   atk=1, matk=1, spd=1, hp=999999, max_hp=999999)
    e['effects'] = {}
    return B2("monster", sides={"player": [player], "enemy": [e]}, title_bonus={})


def fire_overload(b, owner):
    """模拟信仰叠满 cap 的 threshold 广播（过载触发点）。"""
    from saintess_engine.battle.effect_triggers import fire
    from saintess_engine.battle.effects import _cap_of
    cap = _cap_of(owner, "faith")
    logs = []
    fire(b, "threshold", {"key": "faith", "value": float(cap),
                          "actor": owner}, logs)
    return logs


def test_1_base():
    print("【1. 对照组：无圣化 过载回血 0.015】")
    p = mk_priest(["圣言术"])  # 牧师有 faith 装配（channels）
    apply_class_mech(p)
    b = mk_battle(p)
    p2 = b.sides_of("player")[0]
    p2['hp'] = 3000  # 掉血 2000
    p2['effects']['faith'] = {'stacks': 10, 'expire': None}
    logs = fire_overload(b, p2)
    expect = max(1, int(5000 * 0.015))  # 75
    check("过载回血 ≈75（0.015×max_hp）", int(p2.get("hp", 0)) == 3000 + expect,
          f"hp={p2.get('hp')} expect={3000 + expect}")
    check("信仰清零", float((p2.get("effects") or {}).get("faith", {}).get("stacks", 0)) == 0,
          repr((p2.get("effects") or {}).get("faith")))


def test_2_holy():
    print("【2. 圣化组：学过信念·圣化 → 过载回血 ×1.3】")
    p = mk_priest(["信念·圣化", "圣言术"])
    apply_class_mech(p)
    b = mk_battle(p)
    p2 = b.sides_of("player")[0]
    p2['hp'] = 3000
    p2['effects']['faith'] = {'stacks': 10, 'expire': None}
    logs = fire_overload(b, p2)
    expect = max(1, int(5000 * 0.015 * 1.3))  # 97（×1.3）
    check("过载回血 ≈97（0.015×1.3×max_hp）", int(p2.get("hp", 0)) == 3000 + expect,
          f"hp={p2.get('hp')} expect={3000 + expect}")
    check("过载日志", any("过载" in l or "圣光" in l for l in logs), str(logs[-2:]))


def main():
    test_1_base()
    test_2_holy()
    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
