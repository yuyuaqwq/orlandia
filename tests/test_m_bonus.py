# -*- coding: utf-8 -*-
"""v181.M-bonus 验收：actor 统一数值容器 actor["bonus"] = {panel, cap, cost}。

覆盖（鱼鱼 2026-09-09 拍板方案 2）：
  A 容器迁移：
    1. 开战播种形状三域（panel 外部增幅 / cap 资源上限 / cost 消耗修正）；
       engine 读源全走 bonus 分域（stats 面板合成 / effects._cap_of / actions cost）
    2. 旧 actor 键 stat_bonus/cap_bonus 全清（装配后 actor 上无残留）
  B cost 域引擎折算（actions._skill_pay_of——预检/扣费同源）：
    3. mp_pct floor 取整 / mp_flat 平减 / res 折扣 / 保底 1（0 消耗不许白嫖）
    4. when 判据（element / mech_prefix / name_contains，OR）——非命中技能不减
    5. 无折扣零变化（行为回归：pay == 声明）
  C 三词条装配端到端（EP.apply_to_actor → bonus.cost → do_skill 扣费）：
    6. energy_blade：res.energy 折扣 tier 0.05/0.08/0.12；精力 20 消耗扣 19（blue）
    7. arcane_focus：when mp_pct 0.10 元素/奥术判据——织焰类元素技/奥术技减、非元素不减
    8. sigil_blessing：when mp_flat 5/10 神迹判据——神迹 mp35→25（purple 10）、光愈不减
    9. 预检足额边界：energy 打折后 19 够 20 声明可施放；18 拦截（预检=扣费同源）
  D finisher（终结技伤害乘区）：
    10. 装配声明 dmg_calc we_dmg_mult_cond mech_any（mechs finisher / names 终结）
    11. mech_any 谓词：终结技 ×(1+tier)；非终结技不乘；purple tier 0.15

跑法：python tests/test_m_bonus.py（exit=0 全绿）
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_m_bonus.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)

from saintess_engine import config as _b2c
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # ★ P5C-REPOINT：宿主装配壳已删 → 测试侧引擎通道装配口
from ext_combat import Battle as B2, make_actor
from ext_combat.battle import actions as A
from ext_combat.battle.actors import ActCtx
from ext_combat.battle.effects import _cap_of
from content.mech import equip as EP  # ★ P5C-REPOINT：直取包内真源（原 battle_equip_proc）
from content import stat_bonus as SB  # ★ P5C-REPOINT：直取包内真源（原 game.core.stat_bonus）

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def mk(cid, name, hp=5000, mp=300, lv=40, uid="p"):
    a = make_actor(uid=uid, name=name, side="player", kind="player",
                   human_controlled=True, class_name=cid, level=lv,
                   hp=hp, max_hp=hp, mp=mp, max_mp=mp,
                   atk=80, matk=80, spd=12, crit=0.05,
                   skills=[], learned_skills=[],
                   race=None, evolve_path=0, class_tier=0, attributes={},
                   **{"def": 40, "mdef": 60})
    return a


def mk_mage(uid="p"):
    return mk("cls_fa_shi", "法师", uid=uid)


def mk_ranger(uid="p"):
    return mk("cls_you_xia", "游侠", uid=uid)


def mk_priest(uid="p"):
    return mk("cls_mu_shi", "牧师", uid=uid)


def mk_rogue(uid="p"):
    return mk("cls_ci_ke", "刺客", uid=uid)


def mk_enemy(hp=999999):
    return make_actor(uid="e1", name="木桩", side="enemy", kind="monster",
                      hp=hp, max_hp=hp, atk=1, matk=1, spd=5, crit=0.0,
                      level=60, exp=0, gold=0, **{"def": 5, "mdef": 5})


def _battle(*actors):
    sides = {"player": [], "enemy": []}
    for a in actors:
        sides[a.get("side") or "enemy"].append(a)
    return B2(btype="monster", sides=sides)


def equip_affix(actor, aid, slot="weapon", quality="blue"):
    actor.setdefault("equipment", {})[slot] = {
        "slot": slot, "quality": quality, "affixes": [aid], "stats": {}}
    return actor


def _cost_of(a):
    return ((a or {}).get("bonus") or {}).get("cost") or {}


def _stacks(a, k):
    ent = ((a or {}).get("effects") or {}).get(k)
    return ent.get("stacks", None) if isinstance(ent, dict) else None


def _heal_cast(b, p, info):
    """治疗技施放（扣费走引擎 do_skill 全链；hp 不满防满血早退）。"""
    if p.get("hp", 0) >= p.get("max_hp", 1):
        p["hp"] = int(p.get("max_hp", 1) * 0.8)
    return A.do_skill(b, ActCtx(caster=p, action="skill",
                                skill_name=info.get("name", "?") or "?",
                                info=info, target=None))


# ============================================================
# A：容器迁移（播种形状 / 引擎读源 / 旧键全清）
# ============================================================

def t_a_container():
    print("【A.1 bonus 容器播种形状 + 旧键全清】")
    a = mk_mage()
    SB.bonus_seed(a, {"atk": 15})
    check("seed 后三域容器", isinstance(a.get("bonus"), dict)
          and a["bonus"].get("panel") == {"atk": 15}
          and a["bonus"].get("cap") == {}
          and a["bonus"].get("cost") == {}, repr(a.get("bonus")))
    check("bonus_domain 读分域", SB.bonus_domain(a, "panel") == {"atk": 15}
          and SB.bonus_domain(a, "cap") == {}, repr(a.get("bonus")))
    check("无容器 actor bonus_domain 兜底 {}",
          SB.bonus_domain({}, "panel") == {} and SB.bonus_domain(None, "cost") == {})
    # 装配后旧键全清：装 cap/cost 词条 → bonus.cap/cost 写入、actor 无 stat_bonus/cap_bonus 键
    p = mk_ranger()
    equip_affix(p, "full_pack", "armor", "purple")     # cap.energy +10
    equip_affix(p, "energy_blade", "weapon", "blue")   # cost.res.energy 0.05
    EP.apply_to_actor(p)
    check("装配写 bonus.cap.energy=10", _cap_of(p, "energy") == 110
          and ((p.get("bonus") or {}).get("cap") or {}).get("energy") == 10,
          repr(p.get("bonus")))
    check("装配写 bonus.cost.res.energy=0.05",
          abs(float((_cost_of(p).get("res") or {}).get("energy", 0)) - 0.05) < 1e-9,
          repr(_cost_of(p)))
    check("旧键 stat_bonus/cap_bonus 全清（无残留）",
          "stat_bonus" not in p and "cap_bonus" not in p, repr(list(p.keys())[:8]))
    check("panel 分域不受装配覆盖（装备装配不动外部增幅）",
          (p.get("bonus") or {}).get("panel") == {}, repr(p.get("bonus")))
    # from_state 旧档 actor 一次性迁移（旧 stat_bonus 键 → bonus.panel）
    from ext_combat.battle.serialize import _deserialize_actor as _da
    old = {"uid": "x", "class_name": "战士", "hp": 10, "stat_bonus": {"atk": 5},
           "cap_bonus": {"rage": 2}}
    mig = _da(old)
    check("旧档 actor 迁移：stat_bonus → bonus.panel、cap_bonus → bonus.cap",
          (mig.get("bonus") or {}).get("panel") == {"atk": 5}
          and (mig.get("bonus") or {}).get("cap") == {"rage": 2}
          and "stat_bonus" not in mig and "cap_bonus" not in mig,
          repr(mig.get("bonus")))


def t_a_panel_read():
    print("【A.2 面板读源 bonus.panel（actor 优先 / battle.title_bonus 兜底）】")
    from ext_combat.battle.stats import actor_stats
    a0 = mk_mage("b0")
    e0 = mk_enemy()
    b0 = _battle(a0, e0)
    s0 = actor_stats(b0, a0)
    a1 = mk_mage("b1")
    b1 = _battle(a1, mk_enemy())
    SB.bonus_seed(a1, {"atk": 33})
    s1 = actor_stats(b1, a1)
    check("bonus.panel atk+33 生效", int(s1.get("atk", 0)) == int(s0.get("atk", 0)) + 33,
          f"A={s1.get('atk')} 基础={s0.get('atk')}")
    # 无容器 actor → 回落 battle.title_bonus（N10 前过渡语义保持）
    a2 = mk_mage("b2")
    b2 = B2(btype="monster", sides={"player": [a2], "enemy": [mk_enemy()]},
            title_bonus={"spd": 7})
    s2 = actor_stats(b2, a2)
    check("无 bonus 容器回落 battle.title_bonus（spd+7）",
          int(s2.get("spd", 0)) == int(s0.get("spd", 0)) + 7,
          f"S={s2.get('spd')} 基础={s0.get('spd')}")


# ============================================================
# B：cost 域引擎折算（_skill_pay_of 预检/扣费同源）
# ============================================================

def _pay_of(actor, mp=0, res_cost=None, name="技", mech="", element=""):
    info = {"name": name, "mp": mp}
    if res_cost:
        info["res_cost"] = dict(res_cost)
    if mech:
        info["mech"] = mech
    if element:
        info["element"] = element
    return A._skill_pay_of(actor, info)


def t_b_pay_math():
    print("【B.1 折算数学：mp_pct floor / mp_flat / res 折扣 / 保底 1】")
    a = mk_mage()
    # mp_pct 0.10：15 → 13.5 → floor 13
    SB.bonus_seed(a, {})
    a["bonus"]["cost"] = {"mp_pct": 0.10}
    check("mp_pct 0.10：mp15 → 13（floor 13.5）", _pay_of(a, mp=15)["mp"] == 13,
          f"{_pay_of(a, mp=15)}")
    # mp_flat 5：35 → 30
    a["bonus"]["cost"] = {"mp_flat": 5}
    check("mp_flat 5：mp35 → 30", _pay_of(a, mp=35)["mp"] == 30, f"{_pay_of(a, mp=35)}")
    # 保底：flat > 声明 → 扣 1（0 消耗不许白嫖）
    check("mp_flat 5 保底：mp4 → 1", _pay_of(a, mp=4)["mp"] == 1, f"{_pay_of(a, mp=4)}")
    # 保底：pct 折到 0 → 1
    a["bonus"]["cost"] = {"mp_pct": 0.5}
    check("mp_pct 0.5 保底：mp1 → 1", _pay_of(a, mp=1)["mp"] == 1, f"{_pay_of(a, mp=1)}")
    # 无消耗技能不折算（声明 0 → 0，不吃保底）
    check("mp0 无消耗不折算", _pay_of(a, mp=0)["mp"] == 0, f"{_pay_of(a, mp=0)}")
    # res 折扣：energy 0.05 → 20 → 19
    a["bonus"]["cost"] = {"res": {"energy": 0.05}}
    pay = _pay_of(a, res_cost={"energy": 20})
    check("res 折扣 0.05：energy20 → 19", pay["res"].get("energy") == 19, f"{pay}")
    # res 保底：energy 1 ×0.95 → 0.95 → floor 0 → 保底 1
    pay1 = _pay_of(a, res_cost={"energy": 1})
    check("res 保底：energy1 ×0.95 → 1", pay1["res"].get("energy") == 1, f"{pay1}")
    # 折扣只作用于同名资源 key（rage 不受 energy 折扣影响）
    pay2 = _pay_of(a, res_cost={"rage": 10})
    check("res 折扣按 key 隔离（rage 不折）", pay2["res"].get("rage") == 10, f"{pay2}")
    # 无折扣零变化（行为回归：mp/faith 声明值直通）
    b = mk_priest("nob")
    SB.bonus_seed(b, {})
    pay3 = _pay_of(b, mp=15, res_cost={"faith": 3})
    check("无 bonus.cost 零变化：mp15→15 / faith3→3",
          pay3["mp"] == 15 and pay3["res"].get("faith") == 3, f"{pay3}")
    # 无 bonus 容器 actor 也零变化（引擎读源兜底）
    c = mk_mage("noc")
    pay4 = _pay_of(c, mp=8, res_cost={"energy": 2})
    check("无 bonus 容器零变化（读源兜底 {}）",
          pay4["mp"] == 8 and pay4["res"].get("energy") == 2, f"{pay4}")


def t_b_when_judge():
    print("【B.2 when 判据：element / mech_prefix / name_contains（OR），非命中不减】")
    a = mk_mage()
    SB.bonus_seed(a, {})
    a["bonus"]["cost"] = {"when": [{"mp_pct": 0.10, "judge": {
        "element": True, "mech_prefix": ["fire", "ice", "thunder", "element", "arcane"],
        "name_contains": ["元素", "奥术"]}}]}
    check("judge 元素技（element=fire）命中：mp15 → 13",
          _pay_of(a, mp=15, element="fire")["mp"] == 13, f"{_pay_of(a, mp=15, element='fire')}")
    check("judge 奥术技（mech=arcane）命中：mp15 → 13",
          _pay_of(a, mp=15, mech="arcane")["mp"] == 13, f"{_pay_of(a, mp=15, mech='arcane')}")
    check("judge 名族（name 含奥术）命中：mp20 → 18",
          _pay_of(a, mp=20, name="奥术洪流")["mp"] == 18, f"{_pay_of(a, mp=20, name='奥术洪流')}")
    check("judge 非命中（增益技无标记）不减：mp20 → 20",
          _pay_of(a, mp=20, name="深度冥想")["mp"] == 20, f"{_pay_of(a, mp=20, name='深度冥想')}")
    check("judge 非命中（普通名/无 mech/element）不减：mp12 → 12",
          _pay_of(a, mp=12, name="圣光术")["mp"] == 12, f"{_pay_of(a, mp=12, name='圣光术')}")
    # 神迹判据（sigil_blessing 形态）
    b = mk_priest("sb")
    SB.bonus_seed(b, {})
    b["bonus"]["cost"] = {"when": [{"mp_flat": 10, "judge": {"name_contains": ["神迹"]}}]}
    check("神迹判据命中：神迹 mp35 → 25", _pay_of(b, mp=35, name="神迹")["mp"] == 25,
          f"{_pay_of(b, mp=35, name='神迹')}")
    check("神迹·重生 mp50 → 40", _pay_of(b, mp=50, name="神迹·重生")["mp"] == 40,
          f"{_pay_of(b, mp=50, name='神迹·重生')}")
    check("非神迹技能不减：光愈 mp14 → 14", _pay_of(b, mp=14, name="光愈")["mp"] == 14,
          f"{_pay_of(b, mp=14, name='光愈')}")


# ============================================================
# C：三词条装配端到端
# ============================================================

def t_c_energy_blade():
    print("【C.1 energy_blade：res.energy 折扣 tier 生效 + 施放扣费端到端】")
    for q, expect in (("blue", 0.05), ("purple", 0.08), ("orange", 0.12)):
        r = mk_ranger(f"eb_{q}")
        equip_affix(r, "energy_blade", "weapon", q)
        EP.apply_to_actor(r)
        got = float((_cost_of(r).get("res") or {}).get("energy", 0))
        check(f"energy_blade {q} → cost.res.energy={expect}", abs(got - expect) < 1e-9,
              f"got={got} cost={_cost_of(r)}")
    # 端到端：blue 游侠施放 energy 20 消耗技能 → 扣 19（预检=扣费同源都按 19）
    r = mk_ranger("eb_e2e")
    equip_affix(r, "energy_blade", "weapon", "blue")
    EP.apply_to_actor(r)
    e = mk_enemy()
    b = _battle(r, e)
    r.setdefault("effects", {})["energy"] = {"stacks": 20, "expire": 99999}
    info = {"kind": "魔法", "name": "贯穿连射", "res_cost": {"energy": 20},
            "exprs": ["atk*0.1"]}
    logs = A.do_skill(b, ActCtx(caster=r, action="skill", skill_name="贯穿连射",
                                info=info, target=e))
    check("energy 20 消耗 ×0.95 → 扣 19（20→1）",
          _stacks(r, "energy") == 1, f"stacks={_stacks(r, 'energy')} logs={logs[:1]}")
    # 预检足额边界（同源）：19 层够（pay=19）放行；18 层拦截
    r2 = mk_ranger("eb_chk")
    equip_affix(r2, "energy_blade", "weapon", "blue")
    EP.apply_to_actor(r2)
    b2 = _battle(r2, mk_enemy())
    r2.setdefault("effects", {})["energy"] = {"stacks": 19, "expire": 99999}
    info2 = {"kind": "魔法", "name": "贯穿连射", "res_cost": {"energy": 20},
             "exprs": ["atk*0.1"]}
    logs2 = A.do_skill(b2, ActCtx(caster=r2, action="skill", skill_name="贯穿连射",
                                  info=info2, target=e))
    check("边界：19 层（≥pay 19）放行施放",
          _stacks(r2, "energy") == 0 and not any("核心资源不足" in str(x) for x in logs2),
          f"stacks={_stacks(r2, 'energy')} logs={logs2[:1]}")
    r3 = mk_ranger("eb_blk")
    equip_affix(r3, "energy_blade", "weapon", "blue")
    EP.apply_to_actor(r3)
    b3 = _battle(r3, mk_enemy())
    r3.setdefault("effects", {})["energy"] = {"stacks": 18, "expire": 99999}
    logs3 = A.do_skill(b3, ActCtx(caster=r3, action="skill", skill_name="贯穿连射",
                                  info=info2, target=e))
    check("边界：18 层（<pay 19）拦截（不足文案、不扣费）",
          _stacks(r3, "energy") == 18 and any("核心资源不足" in str(x) for x in logs3),
          f"stacks={_stacks(r3, 'energy')} logs={logs3[:1]}")
    # 卸下 → 覆盖写回落（cost 分域清空）
    r["equipment"]["weapon"]["affixes"] = []
    EP.apply_to_actor(r)
    check("卸下后 cost.res 空（覆盖写幂等回落）",
          not (_cost_of(r).get("res") or {}), repr(_cost_of(r)))


def t_c_arcane_focus():
    print("【C.2 arcane_focus：when mp_pct 0.10 元素/奥术判据端到端】")
    p = mk_mage("af1")
    equip_affix(p, "arcane_focus", "armor", "blue")
    EP.apply_to_actor(p)
    cost = _cost_of(p)
    whens = cost.get("when") or []
    check("装配 when 条目（mp_pct 0.10 + judge 元素/奥术）",
          len(whens) == 1 and abs(float(whens[0].get("mp_pct") or 0) - 0.10) < 1e-9
          and (whens[0].get("judge") or {}).get("mech_prefix"),
          repr(cost))
    e = mk_enemy()
    b = _battle(p, e)
    # 元素技（element=fire 织焰形态 mp12）：扣 12×0.9=10.8 → floor 10
    p["mp"] = 300
    info_f = {"kind": "魔法", "name": "织焰", "element": "fire", "mp": 12,
              "mech": "fire_mark", "exprs": ["matk*0.1"]}
    A.do_skill(b, ActCtx(caster=p, action="skill", skill_name="织焰", info=info_f, target=e))
    check("元素技织焰 mp12 → 扣 10（300→290）", int(p.get("mp", 0)) == 290,
          f"mp={p.get('mp')}")
    # 奥术技（mech=arcane 奥术飞弹形态 mp15）：扣 15×0.9=13.5 → floor 13
    p["mp"] = 300
    info_a = {"kind": "魔法", "name": "奥术飞弹", "mech": "arcane", "mp": 15,
              "exprs": ["matk*0.1"]}
    A.do_skill(b, ActCtx(caster=p, action="skill", skill_name="奥术飞弹", info=info_a, target=e))
    check("奥术技奥术飞弹 mp15 → 扣 13（300→287）", int(p.get("mp", 0)) == 287,
          f"mp={p.get('mp')}")
    # 非元素技能（增益·深度冥想形态 mp20）：不减（判据不命中）
    p["mp"] = 300
    info_b = {"kind": "增益", "name": "深度冥想", "mp": 20, "cd": 12}
    _heal_cast(b, p, info_b)  # 增益 kind 走 buff 分派（扣费在分派前，mp 足够即可）
    check("非元素增益技深度冥想 mp20 → 不减扣 20（300→280）", int(p.get("mp", 0)) == 280,
          f"mp={p.get('mp')}")
    # 无词条法师对照：同元素技 mp12 扣 12（零变化）
    p2 = mk_mage("af0")
    EP.apply_to_actor(p2)
    b2 = _battle(p2, mk_enemy())
    p2["mp"] = 300
    A.do_skill(b2, ActCtx(caster=p2, action="skill", skill_name="织焰", info=info_f, target=e))
    check("无词条对照：织焰 mp12 扣 12（300→288）", int(p2.get("mp", 0)) == 288,
          f"mp={p2.get('mp')}")


def t_c_sigil_blessing():
    print("【C.3 sigil_blessing：when mp_flat 5/10 神迹判据端到端】")
    for q, flat in (("blue", 5), ("purple", 10)):
        pr = mk_priest(f"sgb_{q}")
        equip_affix(pr, "sigil_blessing", "armor", q)
        EP.apply_to_actor(pr)
        whens = (_cost_of(pr).get("when") or [])
        w0 = whens[0] if whens else {}
        check(f"sigil_blessing {q} → when mp_flat {flat} 神迹判据",
              len(whens) == 1 and int(w0.get("mp_flat") or 0) == flat
              and (w0.get("judge") or {}).get("name_contains") == ["神迹"],
              repr(_cost_of(pr)))
    # 端到端 purple（-10）：神迹 mp35 → 扣 25；光愈 mp14 → 不减（扣 14）
    pr = mk_priest("sgb_e2e")
    equip_affix(pr, "sigil_blessing", "armor", "purple")
    EP.apply_to_actor(pr)
    b = _battle(pr, mk_enemy())
    pr["mp"] = 300
    _heal_cast(b, pr, {"kind": "治疗", "name": "神迹", "mp": 35, "hp_pct": 0.02})
    check("神迹 mp35 -10 → 扣 25（300→275）", int(pr.get("mp", 0)) == 275,
          f"mp={pr.get('mp')}")
    pr["mp"] = 300
    _heal_cast(b, pr, {"kind": "治疗", "name": "神迹·重生", "mp": 50, "hp_pct": 0.02})
    check("神迹·重生 mp50 -10 → 扣 40（300→260）", int(pr.get("mp", 0)) == 260,
          f"mp={pr.get('mp')}")
    pr["mp"] = 300
    _heal_cast(b, pr, {"kind": "治疗", "name": "光愈", "mp": 14, "hp_pct": 0.02})
    check("非神迹光愈 mp14 不减 → 扣 14（300→286）", int(pr.get("mp", 0)) == 286,
          f"mp={pr.get('mp')}")


def t_c_mp_spend_floor_floor():
    print("【C.4 施放扣费保底 1 点端到端（低耗技能 + 大 flat 词条）】")
    # 手工构造 cost：mp_flat 30 挂 actor（模拟多件/极端词条）→ mp4 技能保底扣 1
    pr = mk_priest("floor1")
    SB.bonus_seed(pr, {})
    pr["bonus"]["cost"] = {"when": [{"mp_flat": 30, "judge": {"name_contains": ["小术"]}}]}
    b = _battle(pr, mk_enemy())
    pr["mp"] = 50
    _heal_cast(b, pr, {"kind": "治疗", "name": "小术", "mp": 4, "hp_pct": 0.02})
    check("mp4 flat30 → 保底扣 1（50→49）", int(pr.get("mp", 0)) == 49,
          f"mp={pr.get('mp')}")


# ============================================================
# D：finisher（终结技伤害乘区）
# ============================================================

def t_d_finisher():
    print("【D.1 finisher 装配：dmg_calc we_dmg_mult_cond mech_any + tier 乘区】")
    from content.mech.we_procs import we_dmg_mult_cond  # ★ B18-REPOINT：直取包内实现本体
    for q, mult in (("blue", 1.10), ("purple", 1.15), ("orange", 1.20)):
        k = mk_rogue(f"fin_{q}")
        equip_affix(k, "finisher", "weapon", q)
        EP.apply_to_actor(k)
        dmg = (k.get("triggers") or {}).get("dmg_calc") or []
        w0 = dmg[0] if dmg else {}
        check(f"finisher {q} 装配声明 mult={mult}",
              len(dmg) == 1 and w0.get("cond") == "mech_any"
              and w0.get("mechs") == ["finisher"]
              and abs(float(w0.get("mult") or 0) - mult) < 1e-9
              and w0.get("names_any") == ["终结"],
              repr(dmg))
        # mech_any 谓词直调：终结技（mech=finisher）命中 → ctx.mult ×= mult
        k2 = mk_rogue(f"fin_e2e_{q}")
        equip_affix(k2, "finisher", "weapon", q)
        EP.apply_to_actor(k2)
        b = _battle(k2, mk_enemy())
        from ext_combat.battle.effect_triggers import fire as _fire
        ctx = {"actor": k2, "target": b.sides_of("enemy")[0], "dmg": 100,
               "is_crit": False, "info": {"mech": "finisher", "name": "终结·割喉"},
               "mult": 1.0}
        _fire(b, "dmg_calc", ctx, [])
        got = float((getattr(b, "_fire_ctx", {}) or {}).get("mult", 1.0) or 1.0)
        check(f"终结技（mech=finisher）dmg_calc ×{mult}", abs(got - mult) < 1e-9,
              f"mult={got}")
        # 名字含终结也命中（终结·处刑 mech 同族兜底）
        ctx2 = {"actor": k2, "target": b.sides_of("enemy")[0], "dmg": 100,
                "is_crit": False, "info": {"mech": "", "name": "终结·处刑"},
                "mult": 1.0}
        b._fire_ctx = None
        _fire(b, "dmg_calc", ctx2, [])
        got2 = float((getattr(b, "_fire_ctx", {}) or {}).get("mult", 1.0) or 1.0)
        check(f"终结技（名含终结）dmg_calc ×{mult}", abs(got2 - mult) < 1e-9,
              f"mult={got2}")
        # 非终结技（毒爆 poison_burst_finisher / 普通技）不乘
        ctx3 = {"actor": k2, "target": b.sides_of("enemy")[0], "dmg": 100,
                "is_crit": False,
                "info": {"mech": "poison_burst_finisher", "name": "毒爆"},
                "mult": 1.0}
        b._fire_ctx = None
        _fire(b, "dmg_calc", ctx3, [])
        got3 = float((getattr(b, "_fire_ctx", {}) or {}).get("mult", 1.0) or 1.0)
        check("非终结技（毒爆 mech 无 finisher 前缀/名无终结）不乘",
              abs(got3 - 1.0) < 1e-9, f"mult={got3}")
        ctx4 = {"actor": k2, "target": b.sides_of("enemy")[0], "dmg": 100,
                "is_crit": False, "info": {"mech": "bleed", "name": "淬毒"},
                "mult": 1.0}
        b._fire_ctx = None
        _fire(b, "dmg_calc", ctx4, [])
        got4 = float((getattr(b, "_fire_ctx", {}) or {}).get("mult", 1.0) or 1.0)
        check("普通技能不乘（mech=bleed）", abs(got4 - 1.0) < 1e-9, f"mult={got4}")


# ============================================================
# main
# ============================================================

def main():
    t_a_container()
    t_a_panel_read()
    t_b_pay_math()
    t_b_when_judge()
    t_c_energy_blade()
    t_c_arcane_focus()
    t_c_sigil_blessing()
    t_c_mp_spend_floor_floor()
    t_d_finisher()
    print(f"\n=== 结果 PASS={PASS} FAIL={FAIL} ===")
    if FAILURES:
        print("失败明细：")
        for f in FAILURES:
            print(" -", f)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
