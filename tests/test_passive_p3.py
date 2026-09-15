# -*- coding: utf-8 -*-
"""v181.M-passive P3 测试——条件暴击族（act_cast crit buff）。

跑法：python tests/test_passive_p3.py（exit=0 全绿）
覆盖（旧语义源 = passive_procs._h_crit_cond_add 挂点1 逐字 + desc）：
  1. 狂热（战士）：战意 ≥8 → 施放技能写 crit +15% buff；<8 清
  2. 真知（法师）：奥术充能满 5 + 奥术系技能 → crit +20%；非奥术技清
  3. 疾风之心（游侠）：结余 energy ≥40 技能 → crit +20%；普攻不吃
  4. 面板折算：buff 条目 → actor_stats crit 面板加算
"""
import sys, os
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_passive_p3.db"))
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


def mk(skills, cls, atk=200, matk=20, spd=40, hp=3000, mp=300):
    a = make_actor(uid="p_1", name="测试", side="player", kind="player",
                   human_controlled=True, class_name=cls, level=95,
                   learned_skills=list(skills), skills=list(skills),
                   atk=atk, matk=matk, spd=spd, hp=hp, max_hp=hp, mp=mp, max_mp=mp)
    a['effects'] = {}
    a['bonus'] = {'panel': {}, 'cap': {}, 'cost': {}}
    return a


def mk_battle(player):
    e = make_actor(uid="e_1", name="木桩", side="enemy", kind="monster",
                   atk=1, matk=1, spd=1, hp=999999, max_hp=999999)
    e['effects'] = {}
    return B2("monster", sides={"player": [player], "enemy": [e]}, title_bonus={})


def crit_buff_of(actor, key):
    e = (actor.get("effects") or {}).get(key)
    if isinstance(e, dict) and e.get("stat") == "crit" and e.get("op") == "add":
        return float(e.get("mult") or 0)
    return 0.0


def test_1_zhan_yi_crit():
    print("【1. 狂热（战士）：战意 ≥8 → 施放技能 crit +15% buff】")
    w = mk(["狂热", "怒斩"], cls="cls_zhan_shi")
    apply_class_mech(w)
    acts = [t for t in (w.get("triggers") or {}).get("act_cast", [])
            if t.get("type") == "passive_cond_crit"]
    check("狂热挂 act_cast（judge res zhan_yi）",
          len(acts) == 1 and (acts[0].get("judge") or {}).get("res") == "zhan_yi",
          repr(acts))
    # 战意 8 层 → 施放
    w['effects']['zhan_yi'] = {'stacks': 8, 'expire': None}
    b = mk_battle(w)
    logs, _, _ = b.human_act("skill", "怒斩", w)
    check("命中写 crit buff（+0.15）", crit_buff_of(w, "passive_crit_zhan_yi") == 0.15,
          repr((w.get("effects") or {}).get("passive_crit_zhan_yi")))
    # 战意掉到 4 → 下次行动清除
    w['effects']['zhan_yi']['stacks'] = 4
    b2 = mk_battle(w)
    # 新战斗 = 新时间轴：冷却表是绝对时刻（actions._cd_left_of 比 battle._now），
    # 生产路径 build_battle 每次从快照重建 actor（快照无 cooldown 键，见
    # instance.py 玩家快照构造）→ 换场冷却天然归零；此处复用同一 actor dict，
    # 必须显式清（否则上一场的 '怒斩' 冷却被 b2._now=0 的旧时刻卡住）。
    w['cooldown'] = {}
    logs2, _, _ = b2.human_act("skill", "怒斩", w)
    check("战意不足 → 清 buff", crit_buff_of(w, "passive_crit_zhan_yi") == 0.0,
          repr((w.get("effects") or {}).get("passive_crit_zhan_yi")))


def test_2_arcane_wisdom():
    print("【2. 真知（法师）：奥术满 5 + 奥术技 → crit +20%；非奥术清】")
    m = mk(["真知", "奥术弹幕", "火球术"], cls="cls_fa_shi", matk=220)
    apply_class_mech(m)
    m['effects']['arcane'] = {'stacks': 5, 'expire': None}
    b = mk_battle(m)
    logs, _, _ = b.human_act("skill", "奥术弹幕", m)
    check("奥术技命中写 crit buff（+0.20）", crit_buff_of(m, "passive_crit_arcane") == 0.20,
          repr((m.get("effects") or {}).get("passive_crit_arcane")))
    # 火球术（无 mech）→ 清
    b2 = mk_battle(m)
    logs2, _, _ = b2.human_act("skill", "火球术", m)
    check("非奥术技 → 清 buff", crit_buff_of(m, "passive_crit_arcane") == 0.0,
          repr((m.get("effects") or {}).get("passive_crit_arcane")))
    # 奥术 3 层 + 奥术技 → 不触发
    m['effects']['arcane'] = {'stacks': 3, 'expire': None}
    b3 = mk_battle(m)
    logs3, _, _ = b3.human_act("skill", "奥术弹幕", m)
    check("奥术不足 5 → 无 buff", crit_buff_of(m, "passive_crit_arcane") == 0.0, "")


def test_3_focus_surplus():
    print("【3. 疾风之心（游侠）：结余 energy ≥40 技能 → crit +20%；普攻不吃】")
    r = mk(["疾风之心", "疾风射击"], cls="cls_you_xia", atk=150, spd=120)
    apply_class_mech(r)
    r['effects']['energy'] = {'stacks': 60, 'expire': None}
    b = mk_battle(r)
    logs, _, _ = b.human_act("skill", "疾风射击", r)
    check("energy≥40 技能命中写 crit buff（+0.20）",
          crit_buff_of(r, "passive_crit_focus") == 0.20,
          repr((r.get("effects") or {}).get("passive_crit_focus")))
    # 普攻（basic）→ 清
    b2 = mk_battle(r)
    logs2, _, _ = b2.human_act("attack", None, r)
    check("普攻不吃（清 buff）", crit_buff_of(r, "passive_crit_focus") == 0.0,
          repr((r.get("effects") or {}).get("passive_crit_focus")))


def test_4_panel_apply():
    print("【4. 面板折算：crit buff → actor_stats crit 面板加算】")
    from saintess_engine.battle.stats import actor_stats as _as
    w = mk(["狂热", "怒斩"], cls="cls_zhan_shi")
    apply_class_mech(w)
    base = float((_as(None, w) or {}).get("crit", 0) or 0)
    w['effects']['zhan_yi'] = {'stacks': 8, 'expire': None}
    b = mk_battle(w)
    logs, _, _ = b.human_act("skill", "怒斩", w)
    after = float((_as(b, w) or {}).get("crit", 0) or 0)
    check("crit 面板 +0.15 加算", abs(after - base - 0.15) < 1e-6,
          f"base={base} after={after}")


def main():
    test_1_zhan_yi_crit()
    test_2_arcane_wisdom()
    test_3_focus_surplus()
    test_4_panel_apply()
    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
