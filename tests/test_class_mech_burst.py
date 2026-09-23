# -*- coding: utf-8 -*-
"""职业机制装配层 R1b 测试（v181.M）——burst 引爆族 target 方向兑现。

跑法：python tests/test_class_mech_burst.py（exit=0 全绿）
覆盖（B2 target 方向：声明 mode=dmg_mult_clear_target → 装配效果 dict 写 owner=target，
执行器读/清 fire ctx 的 target effects）：
  1. 装配：元素迸发/荆棘爆/毒爆 → dmg_calc/skill_hit 条目 owner=target + 多印记 key 列表
  2. 元素迸发 dmg_calc：target fire/ice/thunder 印记按各 key 之和乘区（每层 +12%）
  3. 元素迸发 skill_hit：target 三系印记清零；非结算 key（poison）不受影响
  4. 零印记 / mech 不匹配 → 乘区不动（零噪音）
  5. 荆棘爆：target poison 每层 +15%，5 层 = ×1.75（desc 最高值，封顶核对）
  6. 毒爆（poison_burst_finisher）：target 毒引爆主清 + clear_extra 并列清 caster 连段
     （desc"结算后连段归零"）
  7. owner 方向隔离：caster 模式(finisher)只读 caster 连段（target 印记/毒不掺和）；
     target 模式(element_burst_all)只读 target 印记（caster arcane 层不掺和）
"""
import sys, os
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_mech_burst.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)

from saintess_engine import config as _b2c
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # ★ P5C-REPOINT：宿主装配壳已删 → 测试侧引擎通道装配口
from ext_combat import Battle as B2, make_actor
from ext_combat.battle.effect_triggers import fire
from content.mech.class_mech import apply_class_mech  # ★ P5C-REPOINT：直取包内真源

PASS = 0
FAIL = 0


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL")


def mk_player(uid, name, cls, learned):
    a = make_actor(uid=uid, name=name, side="player", kind="player",
                   human_controlled=True, class_name=cls, level=60,
                   hp=3000, max_hp=3000, mp=300, max_mp=300,
                   atk=200, matk=100, spd=15, crit=0.05,
                   skills=[], learned_skills=list(learned),
                   race=None, evolve_path=0, class_tier=0, attributes={},
                   **{"def": 60, "mdef": 40})
    apply_class_mech(a)
    return a


def mk_enemy(uid="e1"):
    return make_actor(uid=uid, name="木桩", side="enemy", kind="monster",
                      hp=99999, max_hp=99999, atk=1, matk=1, spd=5, crit=0.0,
                      level=60, exp=0, gold=0, **{"def": 5, "mdef": 5})


def _battle(p, e):
    return B2(btype="monster", sides={"player": [p], "enemy": [e]})


def _set(actor, key, n):
    actor.setdefault("effects", {})[key] = {"stacks": n, "expire": 99999}


def _mult_of(b, p, e, info):
    logs = []
    fire(b, "dmg_calc", {"actor": p, "target": e, "dmg": 100, "is_crit": False,
                         "info": info, "mult": 1.0}, logs)
    return float(getattr(b, "_fire_ctx", {}).get("mult", 1.0)), logs


def _trig_of(actor, event, action):
    return [x for x in (actor.get("triggers") or {}).get(event, [])
            if x.get("action") == action]


def t_assemble_target():
    print("【1. 装配：burst 技能 → owner=target + 多印记 key 列表（声明驱动参数化）】")
    mage = mk_player("p1", "元素使", "cls_fa_shi", ["元素迸发"])
    dm = _trig_of(mage, "dmg_calc", "mech_cash_dmg_mult")
    cl = _trig_of(mage, "skill_hit", "mech_cash_clear")
    ok_dm = (len(dm) == 1 and dm[0].get("mech") == "element_burst_all"
             and dm[0].get("owner") == "target"
             and dm[0].get("key") == ["fire_mark", "ice_mark", "thunder_mark"]
             and abs(float(dm[0].get("per_layer")) - 0.12) < 1e-6
             and dm[0].get("label") == "元素迸发")
    check("元素迸发 dmg_calc 条目（owner=target/key 三系列表/per=0.12）", ok_dm, repr(dm))
    ok_cl = (len(cl) == 1 and cl[0].get("mech") == "element_burst_all"
             and cl[0].get("owner") == "target"
             and cl[0].get("key") == ["fire_mark", "ice_mark", "thunder_mark"])
    check("元素迸发 skill_hit 清层条目（owner=target/三系列表）", ok_cl, repr(cl))

    ci = mk_player("p2", "毒刃者", "cls_ci_ke", ["毒爆"])
    dm2 = _trig_of(ci, "dmg_calc", "mech_cash_dmg_mult")
    cl2 = _trig_of(ci, "skill_hit", "mech_cash_clear")
    ok_dm2 = (len(dm2) == 1 and dm2[0].get("mech") == "poison_burst_finisher"
              and dm2[0].get("owner") == "target"
              and dm2[0].get("key") == "poison"
              and abs(float(dm2[0].get("per_layer")) - 0.14) < 1e-6)
    check("毒爆 dmg_calc 条目（owner=target/key=poison/per=0.14）", ok_dm2, repr(dm2))
    ok_cl2 = (len(cl2) == 1 and cl2[0].get("mech") == "poison_burst_finisher"
              and cl2[0].get("owner") == "target"
              and cl2[0].get("clear_extra") == [{"owner": "caster", "key": "lian_duan"}])
    check("毒爆 skill_hit 清层 + clear_extra 清 caster 连段", ok_cl2, repr(cl2))


def t_element_burst_mult():
    print("【2. 元素迸发 dmg_calc：target 多印记按各 key 之和乘区（每层 +12%）】")
    p = mk_player("p1", "元素使", "cls_fa_shi", ["元素迸发"])
    e = mk_enemy()
    b = _battle(p, e)
    _set(e, "fire_mark", 2)
    _set(e, "ice_mark", 1)
    _set(e, "poison", 3)  # 非结算 key：既不该计入乘区也不该被清
    info = {"mech": "element_burst_all", "name": "元素迸发", "kind": "魔法"}
    m, logs = _mult_of(b, p, e, info)
    check("印记 2+1=3 层 → mult == 1.36", abs(m - 1.36) < 1e-6, f"mult={m}")
    check("文案含元素迸发", any("元素迸发" in str(x) for x in logs), repr(logs))


def t_element_burst_clear():
    print("【3. 元素迸发 skill_hit：三系印记清零；非结算 key 保留】")
    p = mk_player("p1", "元素使", "cls_fa_shi", ["元素迸发"])
    e = mk_enemy()
    b = _battle(p, e)
    _set(e, "fire_mark", 2)
    _set(e, "ice_mark", 1)
    _set(e, "thunder_mark", 1)
    _set(e, "poison", 3)
    _set(p, "arcane", 10)  # caster 侧层不受 target 清层影响
    logs = []
    fire(b, "skill_hit", {"actor": p, "target": e, "dmg": 200,
                          "info": {"mech": "element_burst_all", "name": "元素迸发"}}, logs)
    ef = e.get("effects") or {}
    ok = (ef.get("fire_mark", {}).get("stacks") == 0
          and ef.get("ice_mark", {}).get("stacks") == 0
          and ef.get("thunder_mark", {}).get("stacks") == 0
          and ef.get("poison", {}).get("stacks") == 3)
    check("三系印记全清零、poison 保留", ok, repr(ef))
    check("caster arcane 层不动", (p.get("effects") or {}).get("arcane", {}).get("stacks") == 10)


def t_zero_noise():
    print("【4. 零印记 / mech 不匹配 → 乘区不动（零噪音）】")
    p = mk_player("p1", "元素使", "cls_fa_shi", ["元素迸发"])
    e = mk_enemy()
    b = _battle(p, e)
    m, _ = _mult_of(b, p, e, {"mech": "element_burst_all", "name": "元素迸发"})
    check("target 无印记 → mult == 1.0", abs(m - 1.0) < 1e-6, f"mult={m}")
    _set(e, "fire_mark", 3)
    m2, _ = _mult_of(b, p, e, {"mech": "fire_mark", "name": "火球术"})
    check("mech 不匹配（火球挂印）→ 不触发引爆乘区", abs(m2 - 1.0) < 1e-6, f"mult={m2}")


def t_poison_burst():
    print("【5. 荆棘爆：target poison 每层 +15%；5 层 ×1.75 封顶】")
    p = mk_player("p1", "森语者", "cls_you_xia", ["荆棘爆"])
    e = mk_enemy()
    b = _battle(p, e)
    _set(e, "poison", 4)
    info = {"mech": "poison_burst", "name": "荆棘爆", "kind": "魔法"}
    m, logs = _mult_of(b, p, e, info)
    check("毒 4 层 → mult == 1.60", abs(m - 1.6) < 1e-6, f"mult={m}")
    fire(b, "skill_hit", {"actor": p, "target": e, "dmg": 200,
                          "info": {"mech": "poison_burst", "name": "荆棘爆"}}, logs)
    check("skill_hit 后 target 毒清零", (e.get("effects") or {}).get("poison", {}).get("stacks", 99) == 0)
    _set(e, "poison", 5)
    m5, _ = _mult_of(b, p, e, info)
    check("毒 5 层封顶 → mult == 1.75（desc 最高 ×1.75）",
          abs(m5 - 1.75) < 1e-6, f"mult={m5}")


def t_poison_burst_finisher():
    print("【6. 毒爆：target 毒引爆主清 + clear_extra 并列清 caster 连段】")
    p = mk_player("p1", "毒刃者", "cls_ci_ke", ["毒爆"])
    e = mk_enemy()
    b = _battle(p, e)
    _set(p, "lian_duan", 6)
    _set(e, "poison", 3)
    info = {"mech": "poison_burst_finisher", "name": "毒爆", "kind": "魔法"}
    m, logs = _mult_of(b, p, e, info)
    check("毒 3 层 → mult == 1.42（读 target，非 caster 连段）",
          abs(m - 1.42) < 1e-6, f"mult={m}")
    check("文案含毒爆", any("毒爆" in str(x) for x in logs), repr(logs))
    fire(b, "skill_hit", {"actor": p, "target": e, "dmg": 200, "info": info}, logs)
    ok = ((e.get("effects") or {}).get("poison", {}).get("stacks", 99) == 0
          and (p.get("effects") or {}).get("lian_duan", {}).get("stacks", 99) == 0)
    check("target 毒清零 + caster 连段归零（desc 结算后连段归零）", ok)


def t_owner_isolation():
    print("【7. owner 方向隔离：caster 模式不被 target 层干扰，反之亦然】")
    # caster 模式（finisher）：target 挂满印记/毒不掺和 caster 连段乘区
    p = mk_player("p1", "影舞", "cls_ci_ke", ["终结·割喉"])
    e = mk_enemy()
    b = _battle(p, e)
    _set(p, "lian_duan", 5)
    _set(e, "fire_mark", 5)
    _set(e, "poison", 5)
    m, _ = _mult_of(b, p, e, {"mech": "finisher", "name": "终结·割喉"})
    check("finisher 只读 caster 连段 5 → mult == 1.50（target 10 层不掺和）",
          abs(m - 1.5) < 1e-6, f"mult={m}")
    # target 模式（element_burst_all）：caster 侧 arcane 层不掺和 target 印记结算
    p2 = mk_player("p2", "元素使", "cls_fa_shi", ["元素迸发"])
    e2 = mk_enemy(uid="e2")
    b2 = _battle(p2, e2)
    _set(p2, "arcane", 10)
    _set(e2, "fire_mark", 1)
    m2, _ = _mult_of(b2, p2, e2, {"mech": "element_burst_all", "name": "元素迸发"})
    check("element_burst_all 只读 target 印记 1 → mult == 1.12（caster arcane 10 不掺和）",
          abs(m2 - 1.12) < 1e-6, f"mult={m2}")


def main():
    print("== 职业机制装配 R1b burst 引爆族 target 方向兑现 ==")
    t_assemble_target()
    t_element_burst_mult()
    t_element_burst_clear()
    t_zero_noise()
    t_poison_burst()
    t_poison_burst_finisher()
    t_owner_isolation()
    print(f"\n结果: {PASS} 通过, {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
