# -*- coding: utf-8 -*-
"""v181.M-passive P14 测试——法师奥术线（cap 收敛 + 燃尽兑现 + 奥术直觉回能）。

跑法：python tests/test_passive_p14.py（exit=0 全绿）
覆盖（v153 法师奥术线）：
  1. arcane cap 收敛 5（旧 10 漂移）
  2. 奥术脉冲燃尽：arcane 满层施放 → 每层 ×1.15 乘区 + 清空（dmg_mult_clear）
  3. 奥术直觉：turn_start 每次行动回 1 充能
"""
import sys, os
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_passive_p14.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)

from saintess_engine import config as _b2c
from _engine_harness import boot as _eng_cfg; _eng_cfg()
from ext_combat import Battle as B2, make_actor
from content.mech.class_mech import apply_class_mech

PASS = 0
FAIL = 0


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL")


def mk_mage(skills, hp=5000):
    a = make_actor(uid="p_1", name="法师", side="player", kind="player",
                   human_controlled=True, class_name="cls_fa_shi", level=95,
                   learned_skills=list(skills), skills=list(skills),
                   atk=50, matk=250, spd=60, hp=hp, max_hp=hp, mp=500, max_mp=500)
    a['effects'] = {}
    a['bonus'] = {'panel': {}, 'cap': {}, 'cost': {}}
    return a


def mk_battle(m, e_hp=999999):
    e = make_actor(uid="e_1", name="木桩", side="enemy", kind="monster",
                   atk=1, matk=1, spd=1, hp=e_hp, max_hp=e_hp)
    e['effects'] = {}
    e['dodge'] = 0.0
    return B2("monster", sides={"player": [m], "enemy": [e]})


def arc_of(a):
    en = (a.get("effects") or {}).get("arcane")
    return float(en.get("stacks", 0) or 0) if isinstance(en, dict) else 0.0


def test_1_cap():
    print("【1. arcane cap 收敛 5】")
    from ext_combat.battle.effects import _cap_of
    m = mk_mage(["奥术弹幕"])
    apply_class_mech(m)
    check("arcane cap = 5（v153 满层）", _cap_of(m, "arcane") == 5,
          f"cap={_cap_of(m, 'arcane')}")


def test_2_burst():
    print("【2. 奥术脉冲燃尽：满层施放 → 每层 ×1.15 + 清空】")
    m = mk_mage(["奥术脉冲", "奥术弹幕"])
    apply_class_mech(m)
    m['effects']['arcane'] = {'stacks': 5, 'expire': None}
    b = mk_battle(m)
    m2 = b.sides_of("player")[0]
    e = b.sides_of("enemy")[0]
    logs, _, _ = b.human_act("skill", "奥术脉冲", m2)
    check("燃尽清空充能（arcane 0）", arc_of(m2) == 0, f"arc={arc_of(m2)}")
    # 燃尽乘区生效证据：m2 有 arcane_burst dmg_calc trigger + 伤害显著（对比无充能难直接——查 trigger）
    dm = [t for t in (m2.get("triggers") or {}).get("dmg_calc", [])
          if t.get("action") == "mech_cash_dmg_mult" and t.get("mech") == "arcane_burst"]
    check("奥术脉冲挂燃尽乘区（per_layer 0.15）",
          len(dm) == 1 and abs(float(dm[0].get("per_layer") or 0) - 0.15) < 1e-9,
          repr(dm))


def test_3_intuition():
    print("【3. 奥术直觉：turn_start 每次行动回 1 充能】")
    m = mk_mage(["奥术直觉", "奥术弹幕"])
    apply_class_mech(m)
    b = mk_battle(m)
    m2 = b.sides_of("player")[0]
    m2['effects']['arcane'] = {'stacks': 0, 'expire': None}
    logs, _, _ = b.human_act("skill", "奥术弹幕", m2)
    # turn_start 回 1 + 奥术弹幕命中 +1 = 2（若渠道在）
    check("行动后 arcane ≥1（直觉回合回能）", arc_of(m2) >= 1,
          f"arc={arc_of(m2)} logs={[l for l in logs if '奥术' in l or '充能' in l][-2:]}")


def main():
    test_1_cap()
    test_2_burst()
    test_3_intuition()
    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
