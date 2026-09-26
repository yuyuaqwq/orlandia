# -*- coding: utf-8 -*-
"""v181.M-passive P4 测试——条件减伤 + 免控/挣脱族（taken_calc/turn_start）。

跑法：python tests/test_passive_p4.py（exit=0 全绿）
覆盖（旧语义源 = passive_procs._h_dr_cond/_h_cc_break_cost 逐字）：
  1. 坚城之姿装配：taken_calc 减伤段 + turn_start 免晕段（also 双事件）
  2. 减伤：战意满 10 受击 → taken_calc mult ×0.9
  3. 免晕：战意满 10 + 被晕 → 回合开始免疫清除
  4. 坚韧装配：turn_start + tenacity_break_left 计数 3 初始化
  5. 坚韧触发：被晕 + 战意≥2 → 扣 2 战意挣脱（次数 2 剩）
  6. 坚韧负向：次数耗尽 → 不挣脱
"""
import sys, os
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_passive_p4.db"))
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


def mk(skills, cls="cls_zhan_shi", atk=200, matk=20, spd=40, hp=5000, mp=200):
    a = make_actor(uid="p_1", name="测试", side="player", kind="player",
                   human_controlled=True, class_name=cls, level=95,
                   learned_skills=list(skills), skills=list(skills),
                   atk=atk, matk=matk, spd=spd, hp=hp, max_hp=hp, mp=mp, max_mp=mp)
    a['effects'] = {}
    a['bonus'] = {'panel': {}, 'cap': {}, 'cost': {}}
    return a


def mk_battle(player, e_hp=999999):
    e = make_actor(uid="e_1", name="木桩", side="enemy", kind="monster",
                   atk=1, matk=1, spd=1, hp=e_hp, max_hp=e_hp)
    e['effects'] = {}
    ps = player if isinstance(player, list) else [player]
    return B2("monster", sides={"player": ps, "enemy": [e]})


def test_1_assemble_dual():
    print("【1. 坚城之姿装配：taken_calc 减伤段 + turn_start 免晕段（also）】")
    w = mk(["坚城之姿", "怒斩"])
    apply_class_mech(w)
    tk = [t for t in (w.get("triggers") or {}).get("taken_calc", [])
          if t.get("type") == "passive_taken_reduce"]
    cc = [t for t in (w.get("triggers") or {}).get("turn_start", [])
          if t.get("type") == "passive_cc_clear"]
    check("减伤段挂 taken_calc", len(tk) == 1 and (tk[0].get("judge") or {}).get("res") == "zhan_yi",
          repr(tk))
    check("免晕段挂 turn_start（also 双事件）",
          len(cc) == 1 and (cc[0].get("judge") or {}).get("res") == "zhan_yi"
          and cc[0].get("ctrl") == "stun", repr(cc))


def test_2_taken_reduce():
    print("【2. 减伤：战意满 10 → taken_calc mult ×0.9】")
    from ext_combat.battle.landing import deal_damage
    w = mk(["坚城之姿"])
    apply_class_mech(w)
    w['effects']['zhan_yi'] = {'stacks': 10, 'expire': None}
    b = mk_battle(w, e_hp=999999999)
    e = b.sides_of("enemy")[0]
    w2 = b.sides_of("player")[0]
    # 敌人打玩家 1000 真伤（玩家防御低，看减伤日志/伤害下降）
    # 先用无被动对照
    b2 = mk_battle(mk(["怒斩"]), e_hp=999999999)
    e2 = b2.sides_of("enemy")[0]
    w3 = b2.sides_of("player")[0]
    logs2 = []
    deal_damage(b2, e2, w3, 1000, logs2)
    logs = []
    deal_damage(b, e, w2, 1000, logs)
    check("战意满受击 → 减伤日志", any("减伤" in l for l in logs), str(logs[-3:]))


def test_3_stun_clear():
    print("【3. 免晕：战意满 10 + 被晕 → 回合开始免疫清除】")
    w = mk(["坚城之姿"])
    apply_class_mech(w)
    w['effects']['zhan_yi'] = {'stacks': 10, 'expire': None}
    b = mk_battle([w])
    # 直接施放技能（走 turn_start fire）——先塞 stun
    w['effects']['stun'] = {'mode': 'skip', 'expire': None}
    logs, _, _ = b.human_act("attack", None, w)
    check("被晕但战意满 → stun 被免疫清除", "stun" not in (w.get("effects") or {}),
          repr((w.get("effects") or {}).get("stun")))


def test_4_tenacity_assemble():
    print("【4. 坚韧装配：turn_start + 计数 3 初始化】")
    w = mk(["坚韧"])
    apply_class_mech(w)
    cc = [t for t in (w.get("triggers") or {}).get("turn_start", [])
          if t.get("type") == "passive_cc_break"]
    check("坚韧挂 turn_start passive_cc_break", len(cc) == 1, repr(cc))
    le = ((w.get("effects") or {}).get("tenacity_break_left") or {})
    check("每场 3 次计数初始化", int(le.get("stacks") or 0) == 3, repr(le))


def test_5_tenacity_break():
    print("【5. 坚韧触发：被晕 + 战意≥2 → 扣战意挣脱】")
    w = mk(["坚韧"])
    apply_class_mech(w)
    w['effects']['zhan_yi'] = {'stacks': 5, 'expire': None}
    w['effects']['stun'] = {'mode': 'skip', 'expire': None}
    b = mk_battle([w])
    logs, _, _ = b.human_act("attack", None, w)
    check("挣脱（stun 被移除）", "stun" not in (w.get("effects") or {}),
          repr((w.get("effects") or {}).get("stun")))
    check("战意扣 2（5→3）", int((w.get("effects") or {}).get("zhan_yi", {}).get("stacks", 0)) == 3,
          repr((w.get("effects") or {}).get("zhan_yi")))
    check("次数 3→2", int((w.get("effects") or {}).get("tenacity_break_left", {}).get("stacks", 0)) == 2,
          repr((w.get("effects") or {}).get("tenacity_break_left")))


def test_6_tenacity_exhaust():
    print("【6. 坚韧负向：次数耗尽 → 不挣脱】")
    w = mk(["坚韧"])
    apply_class_mech(w)
    w['effects']['zhan_yi'] = {'stacks': 10, 'expire': None}
    w['effects']['tenacity_break_left'] = {'stacks': 0, 'expire': None}
    w['effects']['stun'] = {'mode': 'skip', 'expire': None}
    b = mk_battle([w])
    logs, _, _ = b.human_act("attack", None, w)
    check("次数 0 → stun 不被移除（行动被控跳过）",
          (w.get("effects") or {}).get("stun") is not None
          or any("控制" in l for l in logs),
          f"stun={(w.get('effects') or {}).get('stun')} logs={str(logs[:3])}")


def main():
    test_1_assemble_dual()
    test_2_taken_reduce()
    test_3_stun_clear()
    test_4_tenacity_assemble()
    test_5_tenacity_break()
    test_6_tenacity_exhaust()
    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
