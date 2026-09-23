# -*- coding: utf-8 -*-
"""职业机制装配层 R2d 测试（v181.M）——职业基底资源攒取渠道（事件型）。

跑法：python tests/test_class_mech_r2d.py（exit=0 全绿）
覆盖（现网核实结论见 docs/archive/REFACTOR_v181_CLASS_MECH_ASSEMBLY.md『M-R2d 渠道装配设计』§1）：
  1. 装配：牧师 apply_class_mech → triggers.act_cast（heal_cast kind=治疗 gain2）+
     triggers.on_taken（taken gain1）；非牧师（战士/游侠）无 faith 渠道（start_classes 防白拿）
  2. 治疗施放攒：牧师 do_skill kind=治疗 → effects.faith 0→2（真实 do_skill 全链）
  3. 连续治疗 clamp cap：+2×N 堆到 cap 10 封顶不再涨（溢出安全，防刷资源）
  4. 受击攒：敌方真实打牧师（landing 承伤 on_taken）→ faith +1
  5. 负向：普攻（物理 basic 经 do_skill 的 act_cast）不增 faith（kind 过滤防误攒）
  6. 负向：攻击技能命中（skill_hit）不增（牧师渠道无该事件——攻击攒信念 = per-skill
     res_gain 数据语义缺口，数据未回填前不接，防「圣光惩戒不增信念」类技能被误喂）
  7. 负向：非牧师（战士）受击/治疗无 faith 条目（无渠道装配 + 零副作用）
  8. 回归：energy start_full 游侠仍满 100、牧师开局无 faith 条目（faith 无 start_full/period）
"""
import sys, os, random
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_mech_r2d.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)

from saintess_engine import config as _b2c
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # ★ P5C-REPOINT：宿主装配壳已删 → 测试侧引擎通道装配口
from ext_combat import Battle as B2, make_actor
from ext_combat.battle import actions as A
from ext_combat.battle.actors import ActCtx
from content.mech.class_mech import apply_class_mech  # ★ P5C-REPOINT：直取包内真源

PASS = 0
FAIL = 0


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL")


def _mk(cid, name, hp, mp, atk, matk, d, mdef, lv=40, uid="p"):
    a = make_actor(uid=uid, name=name, side="player", kind="player",
                   human_controlled=True, class_name=cid, level=lv,
                   hp=hp, max_hp=hp, mp=mp, max_mp=mp,
                   atk=atk, matk=matk, spd=12, crit=0.05,
                   skills=[], learned_skills=[],
                   race=None, evolve_path=0, class_tier=0, attributes={},
                   **{"def": d, "mdef": mdef})
    apply_class_mech(a)
    return a


def mk_priest():
    return _mk("cls_mu_shi", "牧师", 2500, 300, 80, 220, 40, 60)


def mk_warrior():
    return _mk("cls_zhan_shi", "战士", 3000, 100, 200, 40, 60, 30, lv=35, uid="p9")


def mk_ranger():
    return _mk("cls_you_xia", "游侠", 2500, 200, 180, 60, 40, 30, uid="p8")


def mk_enemy(atk=400, hp=99999):
    return make_actor(uid="e1", name="木桩", side="enemy", kind="monster",
                      hp=hp, max_hp=hp, atk=atk, matk=atk, spd=5, crit=0.0,
                      level=60, exp=0, gold=0, **{"def": 5, "mdef": 5})


def _battle(*actors):
    sides = {"player": [], "enemy": []}
    for a in actors:
        sides[a.get("side") or "enemy"].append(a)
    return B2(btype="monster", sides=sides)


def _faith_stacks(a):
    ef = a.get("effects") or {}
    entry = ef.get("faith")
    return int(entry.get("stacks", 0) or 0) if isinstance(entry, dict) else None


def _channel_dicts(a, ev):
    """actor.triggers[ev] 里 type=class_res_channel_gain 的效果 dict 列表。"""
    out = []
    for x in (a.get("triggers") or {}).get(ev, []):
        if isinstance(x, dict) and x.get("type") == "class_res_channel_gain":
            out.append(x)
    return out


def t_assemble():
    print("【1. 装配：牧师渠道钩子 + 非牧师防白拿】")
    p = mk_priest()
    ac = _channel_dicts(p, "act_cast")
    tk = _channel_dicts(p, "on_taken")
    heal = [x for x in ac if x.get("res") == "faith"]
    check("act_cast 挂 heal_cast 渠道（faith gain2 kind=治疗）",
          len(heal) == 1 and int(heal[0].get("gain")) == 2
          and heal[0].get("kind") == "治疗", repr(heal))
    check("on_taken 挂 taken 渠道（faith gain1）",
          len(tk) == 1 and tk[0].get("res") == "faith" and int(tk[0].get("gain")) == 1,
          repr(tk))
    w = mk_warrior()
    check("战士无 act_cast faith 渠道", not [x for x in _channel_dicts(w, "act_cast")
                                              if x.get("res") == "faith"], repr(_channel_dicts(w, "act_cast")))
    check("战士无 on_taken faith 渠道", not [x for x in _channel_dicts(w, "on_taken")
                                              if x.get("res") == "faith"], repr(_channel_dicts(w, "on_taken")))
    r = mk_ranger()
    check("游侠无 faith 渠道（start_classes 归属过滤）",
          not [x for x in _channel_dicts(r, "act_cast") + _channel_dicts(r, "on_taken")
               if x.get("res") == "faith"], "ranger 有 faith 渠道")


def t_heal_cast():
    print("【2. 治疗施放攒：do_skill kind=治疗 → faith 0→2】")
    p = mk_priest()
    e = mk_enemy()
    b = _battle(p, e)
    info = {"kind": "治疗", "hp_pct": 0.15, "name": "治愈术"}
    logs = A.do_skill(b, ActCtx(caster=p, action="skill", skill_name="治愈术",
                                info=info, target=None))
    st = _faith_stacks(p)
    check("faith == 2", st == 2, f"stacks={st}")
    check("文案含信仰值 +2", any("信仰值 +2" in str(x) for x in logs), repr(logs))


def t_clamp_cap():
    print("【3. 连续治疗 clamp cap + 过载复位：+2 堆到 10 封顶不溢出，满即过载清零（R2e）】")
    p = mk_priest()
    e = mk_enemy()
    b = _battle(p, e)
    info = {"kind": "治疗", "hp_pct": 0.05, "name": "小治愈"}
    seen = []
    for _i in range(7):  # +2 × 7：2,4,6,8 后第 5 次到 10 → 过载清零（0）→ 2,4
        A.do_skill(b, ActCtx(caster=p, action="skill", skill_name="小治愈",
                             info=info, target=None))
        seen.append(_faith_stacks(p))
    check("序列 2,4,6,8,0,2,4（cap10 clamp 不溢出；v181.M-R2e 满 10 过载清零复位）",
          seen == [2, 4, 6, 8, 0, 2, 4], f"seen={seen}")


def t_taken():
    print("【4. 受击攒：敌方真实承伤 → faith +1】")
    p = mk_priest()
    e = mk_enemy(atk=400)
    b = _battle(p, e)
    hp0 = p["hp"]
    info = {"kind": "物理", "exprs": ["atk*1.0"], "name": "重击", "_basic": False}
    logs = A.do_skill(b, ActCtx(caster=e, action="skill", skill_name="重击",
                                info=info, target=p))
    check("牧师确被扣血（承伤真实发生）", p["hp"] < hp0, f"hp {hp0}→{p['hp']}")
    st = _faith_stacks(p)
    check("faith == 1（受击 +1）", st == 1, f"stacks={st}")
    # 再受击一次 → 2
    A.do_skill(b, ActCtx(caster=e, action="skill", skill_name="重击",
                         info=info, target=p))
    check("再次受击 faith == 2", _faith_stacks(p) == 2, f"stacks={_faith_stacks(p)}")


def t_no_basic_no_skillhit():
    print("【5/6. 负向：普攻 act_cast 与攻击技能命中不攒 faith】")
    p = mk_priest()
    e = mk_enemy()
    b = _battle(p, e)
    # 普攻（basic 经 do_skill：act_cast kind=物理/魔法 → 渠道 kind=治疗 过滤排除）
    logs = A.do_attack(b, ActCtx(caster=p, action="attack", skill_name="",
                                 info=None, target=e))
    check("普攻后 faith 仍无条目（act_cast 非治疗不触发）",
          _faith_stacks(p) is None, f"stacks={_faith_stacks(p)}")
    # 攻击技能命中（skill_hit 事件——牧师无该渠道，技能 mech 攒层语义也不含 faith）
    info = {"kind": "魔法", "exprs": ["matk*1.0"], "name": "圣光弹"}
    A.do_skill(b, ActCtx(caster=p, action="skill", skill_name="圣光弹",
                         info=info, target=e))
    check("攻击技能命中后 faith 仍无条目", _faith_stacks(p) is None,
          f"stacks={_faith_stacks(p)}")


def t_other_class_no_side_effect():
    print("【7. 负向：战士受击/治疗无 faith 副作用】")
    w = mk_warrior()
    e = mk_enemy(atk=400)
    b = _battle(w, e)
    info = {"kind": "物理", "exprs": ["atk*1.0"], "name": "重击"}
    A.do_skill(b, ActCtx(caster=e, action="skill", skill_name="重击",
                         info=info, target=w))
    check("战士受击后无 faith 条目", _faith_stacks(w) is None, f"stacks={_faith_stacks(w)}")
    hinfo = {"kind": "治疗", "hp_pct": 0.10, "name": "自愈"}
    A.do_skill(b, ActCtx(caster=w, action="skill", skill_name="自愈",
                         info=hinfo, target=None))
    check("战士治疗施放后仍无 faith 条目", _faith_stacks(w) is None,
          f"stacks={_faith_stacks(w)}")


def t_regress():
    print("【8. 回归：energy start_full 不回退 / 牧师开局无 faith 条目】")
    r = mk_ranger()
    ef = (r.get("effects") or {}).get("energy")
    check("游侠 energy 开局满 100（R2a 不回退）",
          isinstance(ef, dict) and int(ef.get("stacks", 0)) == 100, repr(ef))
    p = mk_priest()
    check("牧师开局无 faith 条目（faith 无 start_full——事件渠道驱动；period 衰减只作用于已有条目）",
          "faith" not in (p.get("effects") or {}), repr(p.get("effects")))
    w = mk_warrior()
    check("战士无 energy 条目（start_classes 归属仍防白拿）",
          "energy" not in (w.get("effects") or {}), repr(w.get("effects")))


def main():
    # v181 flaky 修复：玩家（牧师）真实面板含 ~3% 基础闪避（职业成长，走
    # E.player_final_stats 公式，actor["dodge"] 无法覆盖）——t_taken 的「承伤真实发生」
    # 断言偶发被闪避打成假红。固定随机种子保证「怪打玩家」必命中。同 n10_b2 做法。
    random.seed(20260910)
    print("== 职业机制装配 R2d 资源攒取渠道 ==")
    t_assemble()
    t_heal_cast()
    t_clamp_cap()
    t_taken()
    t_no_basic_no_skillhit()
    t_other_class_no_side_effect()
    t_regress()
    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
