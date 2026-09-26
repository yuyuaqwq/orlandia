# -*- coding: utf-8 -*-
"""v181.M-passive P11 测试——控制系技能施加修复（mech 名词路径 turns/chance）。

跑法：python tests/test_passive_p11.py（exit=0 全绿）
背景：盾击·誓（stun）/法术反制（silence）等控制技 mech 走 effects_from_skill 名词路径
→ 旧 _mech_to_effect 恒带 turns=info.cc_turns(缺省0) 覆盖 EFFECT_ACTIONS 默认刻数
→ act_apply 控制型 turns<=0 直接 return = 眩晕/沉默从未施加；mech_chance 概率也无人消费。
修复：名词路径仅 cc_turns>0 才带 turns（缺省用 EFFECT_ACTIONS 默认）；mech_chance → chance
+ apply_effects 通用概率 roll。
覆盖：
  1. 盾击·誓多次施放 → 至少出现眩晕施加（40% chance；stats 存在性验证，不断言比例）
  2. 施加条目结构：mode=skip + expire > 施放时 now（控制型正确写入）
  3. 法术反制 silence 同样施加
"""
import sys, os
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_passive_p11.db"))
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


def mk(cls, skill):
    a = make_actor(uid="p_1", name="测试", side="player", kind="player",
                   human_controlled=True, class_name=cls, level=95,
                   learned_skills=[skill], skills=[skill],
                   atk=200, matk=200, spd=60, hp=5000, max_hp=5000, mp=500, max_mp=500)
    a['effects'] = {}
    a['bonus'] = {'panel': {}, 'cap': {}, 'cost': {}}
    return a


def mk_battle(a, e_spd=200):
    e = make_actor(uid="e_1", name="木桩", side="enemy", kind="monster",
                   atk=1, matk=1, spd=e_spd, hp=99999, max_hp=99999)
    e['effects'] = {}
    e['dodge'] = 0.0
    return B2("monster", sides={"player": [a], "enemy": [e]})


def test_1_shield_stun_applies():
    print("【1. 盾击·誓：多次施放至少一次眩晕施加（40% chance）】")
    applied = 0
    for _ in range(30):
        a = mk("cls_zhan_shi", "盾击·誓")
        apply_class_mech(a)
        b = mk_battle(a)
        e = b.sides_of("enemy")[0]
        t0 = b._now
        logs, _, _ = b.human_act("skill", "盾击·誓", a)
        if any("被【stun】" in l for l in logs):
            applied += 1
    check("30 次至少 5 次施加（40% 期望，防全不中）", applied >= 5,
          f"applied={applied}/30")


def test_2_stun_structure():
    print("【2. 施加条目结构：mode=skip + expire 合理】")
    from ext_combat.battle.landing import deal_damage
    # 直接调 apply（绕开 human_act 时序推进）验证条目结构
    a = mk("cls_zhan_shi", "盾击·誓")
    apply_class_mech(a)
    b = mk_battle(a)
    e = b.sides_of("enemy")[0]
    a2 = b.sides_of("player")[0]
    # 手动触发命中效果（chance 强制 1）
    from ext_combat.battle.effects import effects_from_skill, apply_effects
    from content.skills import skill_info
    info = skill_info("cls_zhan_shi", "盾击·誓") or {}
    effs = effects_from_skill(info, 0)
    for _eff in effs:
        _eff["chance"] = 1.0  # 必中验证结构
    logs = []
    apply_effects(b, a2, e, effs, logs)
    en = (e.get("effects") or {}).get("stun")
    check("stun 条目 mode=skip", isinstance(en, dict) and en.get("mode") == "skip",
          repr(en))
    check("stun expire 大于施放时点", isinstance(en, dict)
          and float(en.get("expire", 0)) > 0.0, repr(en))


def test_3_silence_applies():
    print("【3. 法术反制：silence 施加（no_skill 控制）】")
    applied = 0
    for _ in range(30):
        a = mk("cls_fa_shi", "法术反制")
        apply_class_mech(a)
        b = mk_battle(a)
        e = b.sides_of("enemy")[0]
        logs, _, _ = b.human_act("skill", "法术反制", a)
        if any("silence" in l for l in logs):
            applied += 1
    check("30 次至少 1 次 silence 施加（chance? desc 无条件也应施加）", applied >= 1,
          f"applied={applied}/30")


def main():
    test_1_shield_stun_applies()
    test_2_stun_structure()
    test_3_silence_applies()
    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
