# -*- coding: utf-8 -*-
"""职业机制装配层 R1c 测试（v181.M）——res_cost 数据通道 + curse 效果 + per_system 兑现。

跑法：python tests/test_class_mech_r1c.py（exit=0 全绿）
覆盖：
  1. _skill_usable res_cost 前置拦截：zhan_yi 条目 3 < 5 → 拦 + 文案；无条目 → 不拦
  2. 冷静（治疗 hp_pct=0.20 res_cost zhan_yi5）：层足 → 扣 5 + 回 20% max hp
  3. curse 效果声明：技能挂诅咒 → target effects curse 层（承伤 +20% debuff）
  4. per_system（element_burst_3 元素裁决）：火/冰印各乘 ×1.2（无雷不乘）+ 清全
"""
import sys, os
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_mech_r1c.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)

from saintess_engine import config as _b2c
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # ★ P5C-REPOINT：宿主装配壳已删 → 测试侧引擎通道装配口
from saintess_engine import Battle as B2, make_actor
from saintess_engine import actions as A
from saintess_engine.battle.actors import ActCtx
from saintess_engine.battle.effect_triggers import fire
from content.mech.class_mech import apply_class_mech  # ★ P5C-REPOINT：直取包内真源

PASS = 0
FAIL = 0


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL")


def mk_warrior(learned=()):
    a = make_actor(uid="p1", name="战士", side="player", kind="player",
                   human_controlled=True, class_name="cls_zhan_shi", level=30,
                   hp=1500, max_hp=3000, mp=100, max_mp=200,
                   atk=150, matk=50, spd=10, crit=0.05,
                   skills=[], learned_skills=list(learned),
                   race=None, evolve_path=0, class_tier=0, attributes={},
                   **{"def": 50, "mdef": 30})
    apply_class_mech(a)
    return a


def mk_mage(learned=()):
    a = make_actor(uid="p2", name="法师", side="player", kind="player",
                   human_controlled=True, class_name="cls_fa_shi", level=60,
                   hp=2000, max_hp=2000, mp=500, max_mp=500,
                   atk=60, matk=300, spd=12, crit=0.05,
                   skills=[], learned_skills=list(learned),
                   race=None, evolve_path=0, class_tier=0, attributes={},
                   **{"def": 30, "mdef": 60})
    apply_class_mech(a)
    return a


def mk_enemy():
    return make_actor(uid="e1", name="木桩", side="enemy", kind="monster",
                      hp=99999, max_hp=99999, atk=1, matk=1, spd=5, crit=0.0,
                      level=60, exp=0, gold=0, **{"def": 5, "mdef": 5})


def _battle(*actors):
    sides = {"player": [], "enemy": []}
    for a in actors:
        sides[a.get("side") or "enemy"].append(a)
    return B2(btype="monster", sides=sides)


def t_r1c_usable_block():
    print("【1. _skill_usable res_cost 前置拦截】")
    p = mk_warrior()
    e = mk_enemy()
    b = _battle(p, e)
    info = {"kind": "治疗", "hp_pct": 0.20, "res_cost": {"zhan_yi": 5}, "name": "冷静", "cd": 16}
    # 有条目但不足 → 拦
    p.setdefault("effects", {})["zhan_yi"] = {"stacks": 3, "expire": 99999}
    logs = []
    ok = A._skill_usable(b, p, info, logs)
    check("3/5 拦截", not ok and any("核心资源不足" in str(x) for x in logs), f"ok={ok} logs={logs}")
    # 无条目（渠道未接）→ 不拦（历史行为）
    p["effects"].pop("zhan_yi", None)
    logs2 = []
    ok2 = A._skill_usable(b, p, info, logs2)
    check("无条目不拦", ok2 and logs2 == [], f"ok={ok2} logs={logs2}")
    # 条目足 → 不拦
    p.setdefault("effects", {})["zhan_yi"] = {"stacks": 7, "expire": 99999}
    ok3 = A._skill_usable(b, p, info, [])
    check("7/5 不拦", ok3, f"ok={ok3}")


def t_calm_heal():
    print("【2. 冷静：层足 → 扣 5 战意 + 回 20% max hp】")
    p = mk_warrior()
    e = mk_enemy()
    b = _battle(p, e)
    p.setdefault("effects", {})["zhan_yi"] = {"stacks": 7, "expire": 99999}
    info = {"kind": "治疗", "hp_pct": 0.20, "res_cost": {"zhan_yi": 5}, "name": "冷静", "cd": 16}
    hp0 = p["hp"]  # 1500 / 3000
    logs = A.do_skill(b, ActCtx(caster=p, action="skill", skill_name="冷静", info=info, target=None))
    hp1 = p["hp"]
    check("回血 20% max（+600）", hp1 == hp0 + 600, f"hp {hp0}→{hp1}")
    st = (p.get("effects") or {}).get("zhan_yi", {}).get("stacks", 99)
    check("扣 5 层（7→2）", st == 2, f"stacks={st}")
    check("文案含施展", any("冷静" in str(x) for x in logs), repr(logs[:2]))
    # 不足拦截路径走 do_skill 全链：3 层 → 拦 + 不回血
    p2 = mk_warrior()
    b2 = _battle(p2, e)
    p2.setdefault("effects", {})["zhan_yi"] = {"stacks": 3, "expire": 99999}
    logs2 = A.do_skill(b2, ActCtx(caster=p2, action="skill", skill_name="冷静", info=info, target=None))
    check("层不足 do_skill 拦截", p2["hp"] == 1500 and any("核心资源不足" in str(x) for x in logs2),
          f"hp={p2['hp']} logs={logs2[:2]}")


def t_curse_debuff():
    print("【3. curse 效果声明：挂诅咒层 → target effects curse】")
    p = mk_mage(learned=("墓穴低语",))
    e = mk_enemy()
    b = _battle(p, e)
    # 手构 curse 技能（mech curse mech_val 1，kind 攻击）——effects._mech_to_effect 翻译
    info = {"kind": "魔法", "mech": "curse", "mech_val": 1, "name": "骨噬诅咒",
            "exprs": ["matk*0.5"]}
    logs = A.do_skill(b, ActCtx(caster=p, action="skill", skill_name="骨噬诅咒", info=info, target=e))
    ef = (e.get("effects") or {}).get("curse")
    check("target 挂 curse 层 1", isinstance(ef, dict) and int(ef.get("stacks", 0)) == 1, repr(ef))


def t_per_system():
    print("【4. per_system（element_burst_3 元素裁决）：火/冰各 ×1.2，无雷不乘】")
    p = mk_mage(learned=("元素裁决",))
    e = mk_enemy()
    b = _battle(p, e)
    # 学裁决 → 装配挂 per_system 执行器
    tr = p.get("triggers") or {}
    check("装配挂 mech_cash_per_system_mult",
          any(x.get("action") == "mech_cash_per_system_mult" for x in tr.get("dmg_calc", [])),
          repr(tr.get("dmg_calc")))
    # 目标带火 2 层 + 冰 1 层（无雷）
    ef = e.setdefault("effects", {})
    ef["fire_mark"] = {"stacks": 2, "expire": 99999}
    ef["ice_mark"] = {"stacks": 1, "expire": 99999}
    logs = []
    fire(b, "dmg_calc", {"actor": p, "target": e, "dmg": 100, "is_crit": False,
                         "info": {"mech": "element_burst_3", "name": "元素裁决"},
                         "mult": 1.0}, logs)
    m = float(getattr(b, "_fire_ctx", {}).get("mult", 1.0))
    check("mult = 1.2×1.2 = 1.44（雷无层不乘）", abs(m - 1.44) < 1e-6, f"mult={m}")
    # 命中后清全（三系都清 0）
    logs2 = []
    fire(b, "skill_hit", {"actor": p, "target": e, "dmg": 200,
                          "info": {"mech": "element_burst_3", "name": "元素裁决"}}, logs2)
    e_ef = e.get("effects") or {}
    check("三系印记清空", int((e_ef.get("fire_mark") or {}).get("stacks", 9)) == 0
          and int((e_ef.get("ice_mark") or {}).get("stacks", 9)) == 0, repr(e_ef))
    # 无任何印记 → 不触发
    b2 = _battle(p, mk_enemy())
    e2 = b2.sides_of("enemy")[0]
    fire(b2, "dmg_calc", {"actor": p, "target": e2, "dmg": 100, "is_crit": False,
                          "info": {"mech": "element_burst_3", "name": "元素裁决"}, "mult": 1.0}, [])
    m2 = float(getattr(b2, "_fire_ctx", {}).get("mult", 1.0))
    check("无印记不乘（mult 1.0）", abs(m2 - 1.0) < 1e-6, f"mult={m2}")


def main():
    print("== 职业机制装配 R1c ==")
    t_r1c_usable_block()
    t_calm_heal()
    t_curse_debuff()
    t_per_system()
    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
