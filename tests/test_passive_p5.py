# -*- coding: utf-8 -*-
"""v181.M-passive P5 测试——吸血 + 治疗溢出转盾（淬血/圣光回响）。

跑法：python tests/test_passive_p5.py（exit=0 全绿）
覆盖（旧语义源 = passive_procs._h_lifesteal_add 挂点5 + NO_OLD desc 推演）：
  1. 淬血装配：战士 act_cast passive_lifesteal_buff
  2. 淬血触发：战意 5 → 行动写 lifesteal buff +0.075 → 面板 +0.075
  3. 淬血吸血生效：血不满打木桩 → hp 回升
  4. 圣光回响装配：牧师 heal_calc passive_heal_overflow_shield
  5. 溢出转盾：治疗接近满血目标 → effects.heal_overflow 出现（带 value 的容器条目）
  6. 无溢出：治疗重伤目标 → 不转盾
  7. 溢出转盾**精确数值**（直发 heal_calc 控输入）：溢出量 ×50% = 盾值 + 到期 + 叠厚
  8. 溢出转盾**真吸收**（deal_damage 真打）+ 归零即从容器删
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
# ★ 收口第 2 批（2026-09-28）：护盾读口 = 容器条目（`effects` 里带 value 的那一条）。
from _container_shape import (sh_value_of, sh_of, shield_total,  # noqa: E402
                            shield_names, arm_shield, clear_shields)
from ext_combat.battle.state_effects import state_def  # noqa: E402

check = bind_check(globals(), "PASS", "FAIL")

EPS = 1e-6


def near(a, b, tol=EPS):
    try:
        return abs(float(a) - float(b)) <= tol
    except Exception:
        return False


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
    print("【5. 溢出转盾：治疗接近满血 → effects.heal_overflow（容器条目）】")
    m = mk(["圣光回响", "圣言术"], cls="cls_mu_shi", hp=5000)
    apply_class_mech(m)
    b = mk_battle(m)
    m2 = b.sides_of("player")[0]
    m2['hp'] = 4900  # 缺口 100，治疗大概率溢出
    logs, _, _ = b.human_act("skill", "圣言术", m2)
    # ★ 收口第 2 批（2026-09-28）：转盾写口改走容器（`class_mech.py` 原先
    #   `setdefault("shields")` 那几行**完全不生效** —— 引擎已删该独立容器）。
    #   现在护盾 = `effects` 容器里一条带 value 的条目（key `heal_overflow`，
    #   包内 `effect_rules.json` 声明了 `absorb: true`）。
    sh = sh_of(m2, "heal_overflow")
    check("治疗溢出 → 转盾出现（容器条目）", sh_value_of(m2, "heal_overflow") > 0,
          f"effects={m2.get('effects')} logs={[l for l in logs if '护盾' in l or '治愈' in l][-2:]}")
    check("★ 转盾不再写独立容器 shields", "shields" not in m2, str(sorted(m2)))
    # 比原版更严：条目形状本身要判（带 value + 走容器 expire 到期 + 声明可吸收）
    check("转盾是容器里**带 value 的条目**（不是别的形态）",
          isinstance(sh.get("value"), int) and sh["value"] > 0, str(sh))
    check("转盾到期走容器 expire（无旧 expire_at/halve 死字段）",
          sh.get("expire") is not None and "expire_at" not in sh and "halve" not in sh, str(sh))
    check("转盾被声明为吸收族（absorb_keys 能查到）",
          "heal_overflow" in shield_names(m2),
          f"names={shield_names(m2)} state_def={state_def('heal_overflow')}")


def test_6_no_overflow():
    print("【6. 无溢出：治疗重伤目标 → 不转盾】")
    m = mk(["圣光回响", "圣言术"], cls="cls_mu_shi", hp=5000)
    apply_class_mech(m)
    b = mk_battle(m)
    m2 = b.sides_of("player")[0]
    m2['hp'] = 500  # 重伤，缺口大
    logs, _, _ = b.human_act("skill", "圣言术", m2)
    sh = sh_of(m2, "heal_overflow")
    check("无溢出 → 无转盾", sh_value_of(m2, "heal_overflow") == 0,
          f"effects={m2.get('effects')}")
    # 更严：不是「有条目但 value=0」，而是**容器里根本没有这条**（吸收族空）
    check("无溢出 → 容器里无该条目（非 value=0 的空壳）", sh == {} and shield_names(m2) == [],
          f"sh={sh} names={shield_names(m2)}")


# ---------- 7. 溢出转盾精确数值（直发 heal_calc，把输入钉死）----------

def test_7_overflow_exact():
    print("【7. 溢出转盾精确数值（heal=1000 / 缺口100 → 溢出900 → 盾 450）】")
    from ext_combat.battle.effect_triggers import fire
    m = mk(["圣光回响", "圣言术"], cls="cls_mu_shi", hp=5000)
    apply_class_mech(m)
    b = mk_battle(m)
    m2 = b.sides_of("player")[0]
    m2['hp'] = 4900                       # 缺口 100
    now = float(getattr(b, "_now", 0.0) or 0.0)
    # 直发 heal_calc：heal 1000 ⇒ 溢出 = 1000-100 = 900 ⇒ ×50% = 450（desc 权威 50%）
    fire(b, "heal_calc", {"actor": m2, "target": m2, "heal": 1000,
                          "info": {}, "mult": 1.0}, [])
    sh = sh_of(m2, "heal_overflow")
    check("盾值 = 溢出 900 × 50% = 450（精确值，非 >0）",
          sh_value_of(m2, "heal_overflow") == 450, f"sh={sh}")
    check("stacks = 1（盾是单条资源，不按治疗次数叠层）",
          sh.get("stacks") == 1, str(sh))
    check("到期 = now + 3 刻（容器 expire；旧容器 expire_at 已删）",
          near(float(sh.get("expire") or -1), now + 3), f"expire={sh.get('expire')} now={now}")
    # 更严：再溢出一次 = 同源**叠厚**（value 累加 + expire 取 max），不是覆盖
    fire(b, "heal_calc", {"actor": m2, "target": m2, "heal": 500,
                          "info": {}, "mult": 1.0}, [])
    sh2 = sh_of(m2, "heal_overflow")
    # 第二次 heal 500、缺口仍是 100 ⇒ 溢出 400 ⇒ +200 ⇒ 650（hp 未动，缺口仍按读数算）
    check("同源叠厚：450 + 溢出400×50% = 650（value 累加，不是覆盖）",
          sh_value_of(m2, "heal_overflow") == 650, f"sh2={sh2}")
    check("叠厚后 stacks 仍为 1（叠的是 value 不是层数）", sh2.get("stacks") == 1, str(sh2))

    # 反例钉死：无溢出时容器里连条目都不该有
    m3 = mk(["圣光回响", "圣言术"], cls="cls_mu_shi", hp=5000)
    apply_class_mech(m3)
    b3 = mk_battle(m3)
    m4 = b3.sides_of("player")[0]
    m4['hp'] = 1000
    fire(b3, "heal_calc", {"actor": m4, "target": m4, "heal": 100,
                           "info": {}, "mult": 1.0}, [])
    check("无溢出（heal100 < 缺口4000）→ 零写入", shield_total(m4) == 0
          and "heal_overflow" not in (m4.get("effects") or {}),
          f"ef={m4.get('effects')}")


def test_8_overflow_absorb():
    print("【8. 溢出转盾真吸收（deal_damage）+ 归零即从容器删】")
    from ext_combat.battle.effect_triggers import fire
    from ext_combat.battle.landing import deal_damage
    from ext_combat.battle import schedule as SC
    m = mk(["圣光回响", "圣言术"], cls="cls_mu_shi", hp=5000)
    apply_class_mech(m)
    b = mk_battle(m)
    m2 = b.sides_of("player")[0]
    m2['hp'] = 4900
    fire(b, "heal_calc", {"actor": m2, "target": m2, "heal": 1000,
                          "info": {}, "mult": 1.0}, [])
    check("先决：转盾 450 在容器里", sh_value_of(m2, "heal_overflow") == 450,
          str(m2.get("effects")))
    # ★ 真吸收：只断 value 写对并不能证明机制在跑（引擎只认「声明了 absorb」那条）
    m2['hp'] = 5000
    d = deal_damage(b, m2, m2, 200, [], dmg_kind="true")
    check("打 200 → 完全被盾吸收（0 扣血）", d == 0 and m2['hp'] == 5000,
          f"d={d} hp={m2['hp']}")
    check("吸收后盾值精确递减 450 → 250", sh_value_of(m2, "heal_overflow") == 250,
          str(sh_of(m2, "heal_overflow")))
    # 打穿：只剩 250 盾，再打 400 → 250 吸满 + 150 落到血上
    d = deal_damage(b, m2, m2, 400, [], dmg_kind="true")
    check("打穿：250 吸满 + 150 落血（4900）", d == 150 and m2['hp'] == 4850,
          f"d={d} hp={m2['hp']}")
    check("★ 归零即从容器删（不留 value=0 空壳）",
          "heal_overflow" not in (m2.get("effects") or {}) and shield_total(m2) == 0,
          f"ef={m2.get('effects')}")
    # 到期：容器 expire 那一条通路（引擎不再有护盾自己的到期段）
    m3 = mk(["圣光回响", "圣言术"], cls="cls_mu_shi", hp=5000)
    apply_class_mech(m3)
    b3 = mk_battle(m3)
    m4 = b3.sides_of("player")[0]
    m4['hp'] = 4900
    fire(b3, "heal_calc", {"actor": m4, "target": m4, "heal": 1000,
                           "info": {}, "mult": 1.0}, [])
    exp = float(sh_of(m4, "heal_overflow").get("expire") or 0)
    check("先决：到期刻存在", exp > 0, f"expire={exp}")
    b3._now = exp + 0.1
    SC._settle_time_effects(b3, [])
    check("★ 过期后容器自动清理（到期走容器 expire，不靠旧容器独立到期段）",
          "heal_overflow" not in (m4.get("effects") or {}) and shield_total(m4) == 0,
          f"ef={m4.get('effects')}")


def main():
    test_1_quench_assemble()
    test_2_quench_buff()
    test_3_quench_heal()
    test_4_holy_assemble()
    test_5_overflow_shield()
    test_6_no_overflow()
    test_7_overflow_exact()
    test_8_overflow_absorb()
    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
