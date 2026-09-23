# -*- coding: utf-8 -*-
"""v181.M-passive P10 测试——战士狂暴批（血祭进狂暴 + 狂暴攻击 + 血怒复活）。

跑法：python tests/test_passive_p10.py（exit=0 全绿）
覆盖（v153 CLASS_MECHANICS 战士血怒线）：
  1. 血祭装配：act_cast mech_cash_fury_enter + 血怒 on_death 复活
  2. 血祭施放（战意≥4）→ 狂暴进入 + 战意 -4
  3. 狂暴中面板 atk +20%（fury stat_scale）
  4. 血怒复活：狂暴中致死 → 复活 30% + 清战意 + 退狂暴
  5. 非狂暴致死不复活 / 一次性（二次致死不复活）
"""
import sys, os
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_passive_p10.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)

from saintess_engine import config as _b2c
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # ★ P5C-REPOINT：宿主装配壳已删 → 测试侧引擎通道装配口
from ext_combat import Battle as B2, make_actor
from content.mech.class_mech import apply_class_mech  # ★ P5C-REPOINT：直取包内真源

PASS = 0
FAIL = 0


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL")


def mk_warrior(skills, hp=5000):
    a = make_actor(uid="p_1", name="战士", side="player", kind="player",
                   human_controlled=True, class_name="cls_zhan_shi", level=97,
                   learned_skills=list(skills), skills=list(skills),
                   atk=200, matk=20, spd=40, hp=hp, max_hp=hp, mp=200, max_mp=200)
    a['effects'] = {}
    a['bonus'] = {'panel': {}, 'cap': {}, 'cost': {}}
    return a


def mk_battle(w, e_hp=999999):
    e = make_actor(uid="e_1", name="木桩", side="enemy", kind="monster",
                   atk=1, matk=1, spd=1, hp=e_hp, max_hp=e_hp)
    e['effects'] = {}
    e['dodge'] = 0.0
    return B2("monster", sides={"player": [w], "enemy": [e]}, title_bonus={})


def zy_of(w):
    en = (w.get("effects") or {}).get("zhan_yi")
    return float(en.get("stacks", 0) or 0) if isinstance(en, dict) else 0.0


def test_1_assemble():
    print("【1. 血祭/血怒装配】")
    w = mk_warrior(["血祭", "血怒·不灭"])
    apply_class_mech(w)
    fe = [t for t in (w.get("triggers") or {}).get("act_cast", [])
          if t.get("action") == "mech_cash_fury_enter"]
    rb = [t for t in (w.get("triggers") or {}).get("on_death", [])
          if t.get("type") == "passive_revive_berserk"]
    check("血祭挂 act_cast fury_enter", len(fe) == 1, repr(fe))
    check("血怒挂 on_death 复活", len(rb) == 1, repr(rb))


def test_2_fury_enter():
    print("【2. 血祭施放：狂暴进入 + 战意 -4】")
    w = mk_warrior(["血祭"])
    apply_class_mech(w)
    w['effects']['zhan_yi'] = {'stacks': 6, 'expire': None}
    b = mk_battle(w)
    w2 = b.sides_of("player")[0]
    logs, _, _ = b.human_act("skill", "血祭", w2)
    check("进入狂暴（effects fury）", (w2.get("effects") or {}).get("fury") is not None,
          repr((w2.get("effects") or {}).get("fury")))
    check("战意 6→2（扣 4）", zy_of(w2) == 2, f"zy={zy_of(w2)}")


def test_3_fury_atk():
    print("【3. 狂暴中面板 atk +20%】")
    from ext_combat.battle.stats import actor_stats as _as
    w = mk_warrior(["血祭"])
    apply_class_mech(w)
    base = float((_as(None, w) or {}).get("atk", 0) or 0)
    w['effects']['fury'] = {'stacks': 1, 'expire': None}
    b = mk_battle(w)
    w2 = b.sides_of("player")[0]
    after = float((_as(b, w2) or {}).get("atk", 0) or 0)
    check("狂暴 atk ×1.2", abs(after - base * 1.2) < 1.0, f"base={base} after={after}")


def test_4_revive():
    print("【4. 血怒复活：狂暴中致死 → 复活 30% + 清战意退狂暴】")
    from ext_combat.battle.landing import deal_damage
    w = mk_warrior(["血怒·不灭"], hp=5000)
    apply_class_mech(w)
    w['effects']['fury'] = {'stacks': 1, 'expire': None}
    w['effects']['zhan_yi'] = {'stacks': 8, 'expire': None}
    b = mk_battle(w)
    w2 = b.sides_of("player")[0]
    e = b.sides_of("enemy")[0]
    logs = []
    deal_damage(b, e, w2, 99999, logs)  # 致死
    check("复活回 30%（hp 1500）", int(w2.get("hp", 0)) == 1500,
          f"hp={w2.get('hp')} logs={[l for l in logs if '怒' in l or '血' in l][-2:]}")
    check("战意清空 + 退狂暴",
          zy_of(w2) == 0 and (w2.get("effects") or {}).get("fury") is None,
          f"zy={zy_of(w2)} fury={(w2.get('effects') or {}).get('fury')}")
    check("标记已用", ((w2.get("effects") or {}).get("_berserk_revive_used") or {}).get("stacks") == 1,
          repr((w2.get("effects") or {}).get("_berserk_revive_used")))


def test_5_no_revive():
    print("【5. 负向：非狂暴致死不复活；已用二次致死不复活】")
    from ext_combat.battle.landing import deal_damage
    # 非狂暴
    w = mk_warrior(["血怒·不灭"], hp=5000)
    apply_class_mech(w)
    w['effects']['zhan_yi'] = {'stacks': 5, 'expire': None}  # 有战意但没狂暴
    b = mk_battle(w)
    w2 = b.sides_of("player")[0]
    e = b.sides_of("enemy")[0]
    logs = []
    deal_damage(b, e, w2, 99999, logs)
    check("非狂暴致死 → 不复活（hp 0）", int(w2.get("hp", 0)) == 0, f"hp={w2.get('hp')}")
    # 已用标记 → 二次狂暴死亡不复活
    w3 = mk_warrior(["血怒·不灭"], hp=5000)
    apply_class_mech(w3)
    w3['effects']['fury'] = {'stacks': 1, 'expire': None}
    w3['effects']['_berserk_revive_used'] = {'stacks': 1, 'expire': None}
    b3 = mk_battle(w3)
    w4 = b3.sides_of("player")[0]
    e3 = b3.sides_of("enemy")[0]
    logs3 = []
    deal_damage(b3, e3, w4, 99999, logs3)
    check("已用标记 → 二次死亡不复活", int(w4.get("hp", 0)) == 0, f"hp={w4.get('hp')}")


def main():
    test_1_assemble()
    test_2_fury_enter()
    test_3_fury_atk()
    test_4_revive()
    test_5_no_revive()
    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    # v181 flaky 修复：玩家真实面板含 ~3% 基础闪避（职业成长走 E.player_final_stats
    # 公式，actor["dodge"] 覆盖不了）——「二次死亡不复活」等致死断言偶发被闪避打成假红。
    import random as _r
    _r.seed(20260910)
    main()
