# -*- coding: utf-8 -*-
"""v181.M-passive P13 测试——战士守护姿态铁誓批（姿态态+反击+铁誓·不动）。

跑法：python tests/test_passive_p13.py（exit=0 全绿）
覆盖（v153 铁誓线）：
  1. 守护姿态施放 → stance_guard 态进（8 刻）+ on_taken 反击 trigger 挂
  2. 姿态受击反击（态在 roll 40% → 反打攻击者 atk×100%）
  3. 姿态过期 → 不反击
  4. 铁誓·不动：姿态下致死 → 致命免疫满血 + 清战意（一次性）
"""
import sys, os
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_passive_p13.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)

from saintess_engine import config as _b2c
from _engine_harness import boot as _eng_cfg; _eng_cfg()
from saintess_engine import Battle as B2, make_actor
from content.mech.class_mech import apply_class_mech

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {detail}")


def mk_warrior(skills, hp=5000):
    a = make_actor(uid="p_1", name="战士", side="player", kind="player",
                   human_controlled=True, class_name="cls_zhan_shi", level=98,
                   learned_skills=list(skills), skills=list(skills),
                   atk=200, matk=20, spd=40, hp=hp, max_hp=hp, mp=200, max_mp=200)
    a['effects'] = {}
    a['bonus'] = {'panel': {}, 'cap': {}, 'cost': {}}
    return a


def mk_battle(w, e_spd=1):
    e = make_actor(uid="e_1", name="木桩", side="enemy", kind="monster",
                   atk=1, matk=1, spd=e_spd, hp=999999, max_hp=999999)
    e['effects'] = {}
    e['dodge'] = 0.0
    return B2("monster", sides={"player": [w], "enemy": [e]}, title_bonus={})


def test_1_guard_enter():
    print("【1. 守护姿态施放 → 态进 + 反击 trigger】")
    w = mk_warrior(["守护姿态"])
    apply_class_mech(w)
    b = mk_battle(w)
    w2 = b.sides_of("player")[0]
    logs, _, _ = b.human_act("skill", "守护姿态", w2)
    sg = (w2.get("effects") or {}).get("stance_guard")
    check("stance_guard 态进（expire 8 刻）", isinstance(sg, dict)
          and float(sg.get("expire") or 0) > 0.0, repr(sg))
    ct = [t for t in (w2.get("triggers") or {}).get("on_taken", [])
          if t.get("type") == "class_stance_counter"]
    check("on_taken 反击 trigger 挂上", len(ct) == 1, repr(ct))


def test_2_counter():
    print("【2. 姿态受击反击】")
    from saintess_engine.battle.landing import deal_damage
    w = mk_warrior(["守护姿态"])
    apply_class_mech(w)
    w['effects']['stance_guard'] = {'stacks': 1, 'expire': 9999.0}
    # trigger 需挂（模拟开姿态）
    w.setdefault("triggers", {}).setdefault("on_taken", []).append(
        {"type": "class_stance_counter", "chance": 1.0, "atk_pct": 1.0, "label": "守护姿态"})
    b = mk_battle(w)
    w2 = b.sides_of("player")[0]
    e = b.sides_of("enemy")[0]
    logs = []
    deal_damage(b, e, w2, 100, logs)  # 敌方打玩家
    check("姿态反击发生（敌被反打掉血）",
          int(e.get("hp", 0)) < 999999, f"enemy_hp={e.get('hp')}")
    check("反击日志", any("守护反击" in l for l in logs), str(logs[-3:]))


def test_3_expired():
    print("【3. 姿态过期 → 不反击】")
    from saintess_engine.battle.landing import deal_damage
    w = mk_warrior(["守护姿态"])
    apply_class_mech(w)
    # 态不存在（过期）但 trigger 残留
    w.setdefault("triggers", {}).setdefault("on_taken", []).append(
        {"type": "class_stance_counter", "chance": 1.0, "atk_pct": 1.0, "label": "守护姿态"})
    b = mk_battle(w)
    w2 = b.sides_of("player")[0]
    e = b.sides_of("enemy")[0]
    logs = []
    deal_damage(b, e, w2, 100, logs)
    check("无态不反击", int(e.get("hp", 0)) == 999999,
          f"enemy_hp={e.get('hp')}")


def test_4_immortal():
    print("【4. 铁誓·不动：姿态下致死免疫满血】")
    from saintess_engine.battle.landing import deal_damage
    w = mk_warrior(["铁誓·不动"], hp=5000)
    apply_class_mech(w)
    w['effects']['stance_guard'] = {'stacks': 1, 'expire': 9999.0}
    w['effects']['zhan_yi'] = {'stacks': 7, 'expire': None}
    b = mk_battle(w)
    w2 = b.sides_of("player")[0]
    e = b.sides_of("enemy")[0]
    logs = []
    deal_damage(b, e, w2, 99999, logs)
    check("致命免疫回满 hp 5000", int(w2.get("hp", 0)) == 5000,
          f"hp={w2.get('hp')} logs={[l for l in logs if '铁' in l or '免疫' in l][-2:]}")
    zy = (w2.get("effects") or {}).get("zhan_yi", {})
    check("战意清空", float(zy.get("stacks", 0) or 0) == 0, repr(zy))
    # 二次致死（已用）不免疫
    logs2 = []
    deal_damage(b, e, w2, 99999, logs2)
    check("一次性：二次致死不免疫", int(w2.get("hp", 0)) == 0, f"hp={w2.get('hp')}")


def test_5_no_guard():
    print("【5. 负向：非姿态致死不免疫】")
    from saintess_engine.battle.landing import deal_damage
    w = mk_warrior(["铁誓·不动"], hp=5000)
    apply_class_mech(w)
    w['effects']['zhan_yi'] = {'stacks': 7, 'expire': None}  # 战意但不姿态
    b = mk_battle(w)
    w2 = b.sides_of("player")[0]
    e = b.sides_of("enemy")[0]
    logs = []
    deal_damage(b, e, w2, 99999, logs)
    check("非姿态致死 → 不免疫", int(w2.get("hp", 0)) == 0, f"hp={w2.get('hp')}")


def main():
    test_1_guard_enter()
    test_2_counter()
    test_3_expired()
    test_4_immortal()
    test_5_no_guard()
    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    # v181 flaky 修复：玩家真实面板含 ~3% 基础闪避（职业成长走 E.player_final_stats
    # 公式，actor["dodge"] 覆盖不了）——铁誓致死免疫/二次致死断言偶发被闪避打成假红。
    import random as _r
    _r.seed(20260910)
    main()
