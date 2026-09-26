# -*- coding: utf-8 -*-
"""v181.M-passive P5 测试——吸血 + 治疗溢出转盾（淬血/圣光回响）。

跑法：python tests/test_passive_p5.py（exit=0 全绿）
覆盖（旧语义源 = passive_procs._h_lifesteal_add 挂点5 + NO_OLD desc 推演）：
  1. 淬血装配：战士 act_cast passive_lifesteal_buff
  2. 淬血触发：战意 5 → 行动写 lifesteal buff +0.075 → 面板 +0.075
  3. 淬血吸血生效：血不满打木桩 → hp 回升
  4. 圣光回响装配：牧师 heal_calc passive_heal_overflow_shield
  5. 溢出转盾：治疗接近满血目标 → shields.heal_overflow 出现
  6. 无溢出：治疗重伤目标 → 不转盾
"""
import sys, os
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_passive_p5.db"))
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


def mk(skills, cls, atk=200, matk=100, spd=40, hp=5000, mp=500):
    a = make_actor(uid="p_1", name="测试", side="player", kind="player",
                   human_controlled=True, class_name=cls, level=95,
                   learned_skills=list(skills), skills=list(skills),
                   atk=atk, matk=matk, spd=spd, hp=hp, max_hp=hp, mp=mp, max_mp=mp)
    a['effects'] = {}
    a['bonus'] = {'panel': {}, 'cap': {}, 'cost': {}}
    return a


def mk_battle(player, e_hp=999999, e_atk=1):
    e = make_actor(uid="e_1", name="木桩", side="enemy", kind="monster",
                   atk=e_atk, matk=1, spd=1, hp=e_hp, max_hp=e_hp)
    e['effects'] = {}
    ps = player if isinstance(player, list) else [player]
    return B2("monster", sides={"player": ps, "enemy": [e]})


def lifesteal_buff_of(actor):
    e = (actor.get("effects") or {}).get("passive_lifesteal_zhan_yi")
    if isinstance(e, dict) and e.get("stat") == "lifesteal":
        return float(e.get("mult") or 0)
    return 0.0


def test_1_quench_assemble():
    print("【1. 淬血装配：战士 act_cast lifesteal buff】")
    w = mk(["淬血", "怒斩"], cls="cls_zhan_shi")
    apply_class_mech(w)
    acts = [t for t in (w.get("triggers") or {}).get("act_cast", [])
            if t.get("type") == "passive_lifesteal_buff"]
    check("淬血挂 act_cast", len(acts) == 1, repr(acts))


def test_2_quench_buff():
    print("【2. 淬血触发：战意 5 → lifesteal buff +0.075】")
    from ext_combat.battle.stats import actor_stats as _as
    w = mk(["淬血", "怒斩"], cls="cls_zhan_shi", hp=5000)
    apply_class_mech(w)
    w['effects']['zhan_yi'] = {'stacks': 5, 'expire': None}
    base_ls = float((_as(None, w) or {}).get("lifesteal", 0) or 0)
    b = mk_battle(w)
    logs, _, _ = b.human_act("skill", "怒斩", w)
    check("lifesteal buff +0.075（0.015×5）",
          abs(lifesteal_buff_of(w) - 0.075) < 1e-9, repr(lifesteal_buff_of(w)))
    after_ls = float((_as(b, w) or {}).get("lifesteal", 0) or 0)
    check("面板 lifesteal +0.075 加算", abs(after_ls - base_ls - 0.075) < 1e-6,
          f"base={base_ls} after={after_ls}")


def test_3_quench_heal():
    print("【3. 淬血吸血生效：血不满打木桩 → hp 回升】")
    w = mk(["淬血", "怒斩"], cls="cls_zhan_shi", hp=5000)
    apply_class_mech(w)
    w['effects']['zhan_yi'] = {'stacks': 5, 'expire': None}
    b = mk_battle(w)
    w2 = b.sides_of("player")[0]
    w2['hp'] = 3000  # 掉血 2000
    logs, _, _ = b.human_act("skill", "怒斩", w2)
    check("怒斩造成伤害且吸血回复",
          int(w2.get("hp", 0) or 0) > 3000,
          f"hp={w2.get('hp')}")


def test_4_holy_assemble():
    print("【4. 圣光回响装配：牧师 heal_calc overflow shield】")
    m = mk(["圣光回响", "圣言术"], cls="cls_mu_shi")
    apply_class_mech(m)
    hc = [t for t in (m.get("triggers") or {}).get("heal_calc", [])
          if t.get("type") == "passive_heal_overflow_shield"]
    check("圣光回响挂 heal_calc", len(hc) == 1, repr(hc))


def test_5_overflow_shield():
    print("【5. 溢出转盾：治疗接近满血 → shields.heal_overflow】")
    m = mk(["圣光回响", "圣言术"], cls="cls_mu_shi", hp=5000)
    apply_class_mech(m)
    b = mk_battle(m)
    m2 = b.sides_of("player")[0]
    m2['hp'] = 4900  # 缺口 100，治疗大概率溢出
    logs, _, _ = b.human_act("skill", "圣言术", m2)
    sh = (m2.get("shields") or {}).get("heal_overflow")
    check("治疗溢出 → 转盾出现", isinstance(sh, dict) and int(sh.get("value") or 0) > 0,
          f"shields={m2.get('shields')} logs={[l for l in logs if '护盾' in l or '治愈' in l][-2:]}")


def test_6_no_overflow():
    print("【6. 无溢出：治疗重伤目标 → 不转盾】")
    m = mk(["圣光回响", "圣言术"], cls="cls_mu_shi", hp=5000)
    apply_class_mech(m)
    b = mk_battle(m)
    m2 = b.sides_of("player")[0]
    m2['hp'] = 500  # 重伤，缺口大
    logs, _, _ = b.human_act("skill", "圣言术", m2)
    sh = (m2.get("shields") or {}).get("heal_overflow")
    check("无溢出 → 无转盾", not (isinstance(sh, dict) and int(sh.get("value") or 0) > 0),
          f"shields={m2.get('shields')}")


def main():
    test_1_quench_assemble()
    test_2_quench_buff()
    test_3_quench_heal()
    test_4_holy_assemble()
    test_5_overflow_shield()
    test_6_no_overflow()
    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
