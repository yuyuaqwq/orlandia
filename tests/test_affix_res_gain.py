# -*- coding: utf-8 -*-
"""R4 验收：affix 资源型词条装配（N9.7e——事件 gain 型 + 怒气满减伤）。

覆盖：
- 统一翻译规则：effect {res, gain, on} → actor.triggers[事件] 挂 we_affix_res_gain
  （on 单值/列表展开；war_spirit on=[on_attack,on_skill] → attack_hit+skill_hit）
- 端到端：war_spirit 普攻/技能命中攒怒、opening_stance 开局一次性 +1 气、
  blood_bath/rock_rest 受击攒怒/气、crit_charge 暴击攒精（cap clamp 100）
- boiling_blood：怒气满（rage 10/10）taken_calc 减伤 8%（92/100），未满不触发
- holy_echo tiers 档位（purple gain=2）act_cast kind=治疗 过滤；warcry_echo
  kind=增益 过滤；crit_return tiers 档位作用于 chance（_AFFIX_TIER_KEY）
- 缺口词条：上限型（rage_forge/full_pack → bonus.cap）与 cost_reduce 型（energy_blade →
  bonus.cost）走容器**不进事件通道**（零 triggers）；
  **D3 收口（2026-09-13）**：ember_brand（cond: hp_lt_30 → cond_hp_lt 门槛，挂 命中/技能/受击
  三个观测点）与 combo_recover（on: combo_skill → skill_hit）**已装**，见 T7 后两条断言。

跑法：python tests/test_affix_res_gain.py
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
TEST_DB = os.path.join(PLUGIN_DIR, "test_affix_res_gain.db")
os.environ.setdefault("GWEN_GAME_DB", TEST_DB)
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import Battle as BT_NEW, make_actor  # noqa: E402
from saintess_engine import config as _b2config  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # noqa: E402  ★ P5C-REPOINT：宿主装配壳已删
from _engine_harness import act_land  # noqa: E402  T15 两段化：落地推进（一次出手 = 落地后返回）
from saintess_engine.battle.actors import ActCtx          # noqa: E402
from saintess_engine.battle.effect_triggers import fire as _fire  # noqa: E402
from saintess_engine.battle.landing import deal_damage as _dd     # noqa: E402
from saintess_engine.battle.state_effects import state_def        # noqa: E402
from content.mech import equip as EP      # noqa: E402  ★ P5C-REPOINT：直取包内真源
from content.mech.we_procs import we_affix_res_gain  # noqa: E402  ★ B18-REPOINT：直取包内实现本体

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def _capb(a):
    """bonus.cap 分域读（v181.M-bonus 统一容器）。"""
    return ((a or {}).get("bonus") or {}).get("cap") or {}



def mk_a(uid, side, hp=800, atk=40, **kw):
    base = dict(hp=hp, max_hp=hp, atk=atk, matk=15, mdef=8,
                spd=50, crit=0.05, level=10)
    base["def"] = 8
    base.update(kw)
    return make_actor(uid=uid, name=uid, side=side,
                      kind="player" if side == "player" else "monster",
                      human_controlled=(side == "player"), **base)


def new_battle(*actors):
    sides = {}
    for a in actors:
        sides.setdefault(a["side"], []).append(a)
    return BT_NEW(btype="monster", sides=sides)


def equip_affix(actor, aid, slot, quality="blue", stats=None):
    """给 actor 某槽位装带词条装备（词条装配只读 affixes+quality）。"""
    actor.setdefault("equipment", {})[slot] = {
        "slot": slot, "quality": quality, "affixes": [aid],
        "stats": stats or {},
    }
    return actor


def stk(a, k, d=0):
    """读效果叠层数 effects[key].stacks。"""
    e = (a or {}).get("effects") or {}
    ent = e.get(k)
    return int(ent.get("stacks", 0) or 0) if isinstance(ent, dict) else int(d)


def trig_effs(p, ev):
    """actor triggers[ev] 列表（无则 []）。"""
    return (p.get("triggers") or {}).get(ev) or []


# ============================================================
# T1 统一翻译规则：res+gain+on → 事件 → we_affix_res_gain
# ============================================================

def test_translate_gain_rule():
    print("【R4.1 统一翻译：on 单值/列表 → 事件挂 we_affix_res_gain】")
    p = mk_a("p1", "player")
    # war_spirit：on=[on_attack, on_skill] → attack_hit + skill_hit 双事件
    equip_affix(p, "war_spirit", "weapon", quality="purple")
    # boiling_blood：怒气满减伤（taken_calc state_full）
    equip_affix(p, "boiling_blood", "armor", quality="orange")
    # opening_stance：开局 +1 气（battle_start）
    equip_affix(p, "opening_stance", "ring", quality="blue")
    # crit_charge：暴击 energy+3（crit）
    equip_affix(p, "crit_charge", "helm", quality="purple")
    # rock_rest：受击 chi+1（on_taken）
    equip_affix(p, "rock_rest", "boots", quality="blue")
    EP.apply_to_actor(p)
    tr = p.get("triggers") or {}
    for ev in ("attack_hit", "skill_hit", "crit", "on_taken", "battle_start", "taken_calc"):
        check(f"装配事件 {ev}", ev in tr, f"triggers={list(tr.keys())}")
    # war_spirit 双事件：同一 res/gain 参数
    for ev in ("attack_hit", "skill_hit"):
        ws = [e for e in trig_effs(p, ev) if e.get("type") == "we_affix_res_gain"]
        check(f"war_spirit@{ev} 参数", len(ws) == 1 and ws[0].get("res") == "rage"
              and ws[0].get("gain") == 1 and ws[0].get("label") == "战意",
              f"{ws}")
    bb = [e for e in trig_effs(p, "taken_calc") if e.get("type") == "we_taken_mult_cond"]
    check("boiling_blood state_full/state_key=rage/mult 0.92",
          len(bb) == 1 and bb[0].get("cond") == "state_full"
          and bb[0].get("state_key") == "rage"
          and abs(float(bb[0].get("mult", 1)) - 0.92) < 1e-9, f"{bb}")
    cc = [e for e in trig_effs(p, "crit") if e.get("type") == "we_affix_res_gain"]
    check("crit_charge@crit res=energy gain=3",
          len(cc) == 1 and cc[0].get("res") == "energy" and cc[0].get("gain") == 3,
          f"{cc}")


# ============================================================
# T2 war_spirit 端到端：普攻/技能命中攒怒 + cap clamp
# ============================================================

def test_war_spirit_end2end():
    print("【R4.2 war_spirit：普攻/技能命中怒+1，cap 10 clamp】")
    p = mk_a("p2", "player")
    m = mk_a("e2", "enemy", hp=100000, atk=1)
    equip_affix(p, "war_spirit", "weapon", quality="purple")
    EP.apply_to_actor(p)
    b = new_battle(p, m)
    act_land(b, ActCtx(caster=p, action="attack", target=m))  # battle_start + 普攻命中
    check("普攻命中怒+1", stk(p, "rage") == 1, f"rage={stk(p, 'rage')}")
    # 技能（伤害类）命中 → skill_hit → 怒再 +1
    info = {"name": "斩击", "kind": "物理", "exprs": ["atk*1.0"]}
    act_land(b, ActCtx(caster=p, action="skill", skill_name="斩击", info=info, target=m))
    check("技能命中怒+1", stk(p, "rage") == 2, f"rage={stk(p, 'rage')}")
    # cap clamp：直 fire 12 次 attack_hit → 怒封顶 10
    for _ in range(12):
        _fire(b, "attack_hit", {"actor": p, "target": m}, [])
    check("cap clamp 怒气 10/10", stk(p, "rage") == 10, f"rage={stk(p, 'rage')}")
    # EFFECT_RULES rage cap 声明 10（state_full 判据同源）
    check("EFFECT_RULES rage cap=10", int((state_def("rage") or {}).get("cap") or 0) == 10,
          f"{state_def('rage')}")


# ============================================================
# T3 opening_stance：开局一次性 +1 气
# ============================================================

def test_opening_stance():
    print("【R4.3 opening_stance：开战 +1 气（只一次）】")
    p = mk_a("p3", "player")
    m = mk_a("e3", "enemy", hp=100000, atk=1)
    equip_affix(p, "opening_stance", "ring", quality="blue")
    EP.apply_to_actor(p)
    b = new_battle(p, m)
    check("开局前无气", stk(p, "chi") == 0)
    act_land(b, ActCtx(caster=p, action="attack", target=m))  # 触发 battle_start
    check("开局气+1", stk(p, "chi") == 1, f"chi={stk(p, 'chi')}")
    act_land(b, ActCtx(caster=p, action="attack", target=m))
    act_land(b, ActCtx(caster=p, action="attack", target=m))
    check("battle_start 不重复触发", stk(p, "chi") == 1, f"chi={stk(p, 'chi')}")


# ============================================================
# T4 boiling_blood：怒气满（10/10）受击减伤 8%，未满不减
# ============================================================

def test_boiling_blood():
    print("【R4.4 boiling_blood：怒气满全减伤 8%（92/100）】")
    p = mk_a("p4", "player")
    m = mk_a("e4", "enemy", hp=100000, atk=1)
    equip_affix(p, "boiling_blood", "armor", quality="orange")
    EP.apply_to_actor(p)
    b = new_battle(p, m)
    # 怒气未满（5/10）→ 不减伤
    p.setdefault("effects", {})["rage"] = {"stacks": 5}
    hp0 = p["hp"]
    _dd(b, m, p, 100, [])
    check("怒气未满不减伤（100）", hp0 - p["hp"] == 100, f"real={hp0 - p['hp']}")
    # 怒气满（10/10）→ ×0.92 = 92
    (p.get("effects") or {})["rage"] = {"stacks": 10}
    hp0 = p["hp"]
    _dd(b, m, p, 100, [])
    check("怒气满减伤 8%（92）", hp0 - p["hp"] == 92, f"real={hp0 - p['hp']}")
    # 怒气来源闭环：war_spirit 攒满后同场生效（装配 war_spirit + boiling_blood）
    p2 = mk_a("p5", "player")
    m2 = mk_a("e5", "enemy", hp=100000, atk=1)
    equip_affix(p2, "war_spirit", "weapon", quality="purple")
    equip_affix(p2, "boiling_blood", "armor", quality="orange")
    EP.apply_to_actor(p2)
    b2 = new_battle(p2, m2)
    for _ in range(12):  # 普攻 12 次攒满（attack_hit 每次 +1，cap 10）
        act_land(b2, ActCtx(caster=p2, action="attack", target=m2))
    check("攒怒闭环满 10", stk(p2, "rage") == 10, f"rage={stk(p2, 'rage')}")
    hp0 = p2["hp"]
    _dd(b2, m2, p2, 100, [])
    check("装配闭环减伤生效（92）", hp0 - p2["hp"] == 92, f"real={hp0 - p2['hp']}")


# ============================================================
# T5 受击攒怒/气：blood_bath（rage）+ rock_rest（chi）+ 职业 kind 过滤词条
# ============================================================

def test_taken_and_kind_filters():
    print("【R4.5 受击攒 + act_cast kind 过滤（治疗/增益/普攻排除）】")
    # blood_bath + rock_rest：受击怒/气各 +1
    p = mk_a("p6", "player")
    m = mk_a("e6", "enemy", hp=100000, atk=1)
    equip_affix(p, "blood_bath", "armor", quality="purple")
    equip_affix(p, "rock_rest", "boots", quality="blue")
    EP.apply_to_actor(p)
    b = new_battle(p, m)
    _dd(b, m, p, 30, [])
    check("受击怒+1", stk(p, "rage") == 1, f"rage={stk(p, 'rage')}")
    check("受击气+1", stk(p, "chi") == 1, f"chi={stk(p, 'chi')}")
    # holy_echo（purple tier：gain 2）：只认 kind=治疗 的施放
    p2 = mk_a("p7", "player")
    m2 = mk_a("e7", "enemy", hp=100000, atk=1)
    equip_affix(p2, "holy_echo", "armor", quality="purple")
    EP.apply_to_actor(p2)
    tr = p2.get("triggers") or {}
    he = [e for e in tr.get("act_cast", []) if e.get("type") == "we_affix_res_gain"]
    check("holy_echo 装配 act_cast+kind=治疗+tier gain=2",
          len(he) == 1 and he[0].get("kind") == "治疗" and he[0].get("res") == "faith"
          and he[0].get("gain") == 2, f"{he}")
    b2 = new_battle(p2, m2)
    # 物理普攻（act_cast 也会 fire，kind=物理）→ 不触发
    act_land(b2, ActCtx(caster=p2, action="attack", target=m2))
    check("物理行动不加信仰", stk(p2, "faith") == 0, f"faith={stk(p2, 'faith')}")
    # 治疗技能施放 → faith +2
    _fire(b2, "act_cast", {"actor": p2, "target": m2,
                           "info": {"name": "愈", "kind": "治疗"}}, [])
    check("治疗施放信仰+2", stk(p2, "faith") == 2, f"faith={stk(p2, 'faith')}")
    # 增益技能施放不加信仰（kind 过滤互斥）
    _fire(b2, "act_cast", {"actor": p2, "target": m2,
                           "info": {"name": "祝", "kind": "增益"}}, [])
    check("增益行动不加信仰", stk(p2, "faith") == 2, f"faith={stk(p2, 'faith')}")
    # warcry_echo：只认 kind=增益
    p3 = mk_a("p8", "player")
    m3 = mk_a("e8", "enemy", hp=100000, atk=1)
    equip_affix(p3, "warcry_echo", "helm", quality="purple")
    EP.apply_to_actor(p3)
    b3 = new_battle(p3, m3)
    _fire(b3, "act_cast", {"actor": p3, "target": m3,
                           "info": {"name": "斩", "kind": "物理"}}, [])
    check("非增益不加怒", stk(p3, "rage") == 0, f"rage={stk(p3, 'rage')}")
    _fire(b3, "act_cast", {"actor": p3, "target": m3,
                           "info": {"name": "战吼", "kind": "增益"}}, [])
    check("增益技怒+1", stk(p3, "rage") == 1, f"rage={stk(p3, 'rage')}")
    # arcana_flux：on_cast = 技能施放（排除普攻 basic）
    p4 = mk_a("p9", "player")
    m4 = mk_a("e9", "enemy", hp=100000, atk=1)
    equip_affix(p4, "arcana_flux", "weapon", quality="blue")
    EP.apply_to_actor(p4)
    b4 = new_battle(p4, m4)
    act_land(b4, ActCtx(caster=p4, action="attack", target=m4))  # 普攻 act_cast(_basic)
    check("普攻施放不攒充能", stk(p4, "element") == 0, f"element={stk(p4, 'element')}")
    _fire(b4, "act_cast", {"actor": p4, "target": m4,
                           "info": {"name": "火球", "kind": "魔法"}}, [])
    check("技能施放充能+1", stk(p4, "element") == 1, f"element={stk(p4, 'element')}")


# ============================================================
# T6 crit 族：crit_charge（energy+3 cap 100）/ crit_return（chance+tier 档）
# ============================================================

def test_crit_res_gain():
    print("【R4.6 crit 族：暴击攒精/连击点（chance/tier 档位）】")
    # crit_charge：crit 事件 energy+3，cap 100 clamp
    p = mk_a("pa", "player")
    m = mk_a("ea", "enemy", hp=100000, atk=1)
    equip_affix(p, "crit_charge", "weapon", quality="purple")
    EP.apply_to_actor(p)
    b = new_battle(p, m)
    for _ in range(40):  # 40×3 = 120 > cap 100
        _fire(b, "crit", {"actor": p, "target": m, "dmg": 100}, [])
    check("暴击攒精 cap 100 clamp", stk(p, "energy") == 100,
          f"energy={stk(p, 'energy')}")
    check("EFFECT_RULES energy cap=100", int((state_def("energy") or {}).get("cap") or 0) == 100,
          f"{state_def('energy')}")
    # crit_return：装配参数 chance=tier 档（purple 0.25）gain 保持 1
    p2 = mk_a("pb", "player")
    m2 = mk_a("eb", "enemy", hp=100000, atk=1)
    equip_affix(p2, "crit_return", "ring", quality="purple")
    EP.apply_to_actor(p2)
    tr = p2.get("triggers") or {}
    cr = [e for e in tr.get("crit", []) if e.get("type") == "we_affix_res_gain"]
    check("crit_return 装配 chance=0.25 gain=1",
          len(cr) == 1 and abs(float(cr[0].get("chance") or 0) - 0.25) < 1e-9
          and cr[0].get("gain") == 1 and cr[0].get("res") == "cp", f"{cr}")
    # 行为：直调动作恒触发（chance 覆盖 1.0）→ cp+1 cap 5；chance 0 → 不加
    b2 = new_battle(p2, m2)
    we_affix_res_gain(b2, p2, m2, {"key": "crit_return", "res": "cp", "gain": 1,
                                   "chance": 1.0}, [])
    check("暴击回点 cp+1", stk(p2, "cp") == 1, f"cp={stk(p2, 'cp')}")
    we_affix_res_gain(b2, p2, m2, {"key": "crit_return", "res": "cp", "gain": 1,
                                   "chance": 0.0}, [])
    check("chance 0 不加点", stk(p2, "cp") == 1, f"cp={stk(p2, 'cp')}")
    for _ in range(10):
        we_affix_res_gain(b2, p2, m2, {"key": "crit_return", "res": "cp", "gain": 1,
                                       "chance": 1.0}, [])
    check("cp cap 5 clamp", stk(p2, "cp") == 5, f"cp={stk(p2, 'cp')}")


# ============================================================
# T7 缺口词条零噪音（上限型/cost_reduce/cond 修正/combo；regen 型 m_affixtail 已装）
# ============================================================

def test_gap_affixes_no_noise():
    print("【R4.7 非事件通道词条零 triggers + D3 收口的两个 event 型词条已挂】")
    p = mk_a("pc", "player")
    # 一件装备混合五类词条：上限型（rage_forge/full_pack → bonus.cap）/ cost_reduce
    # （energy_blade → bonus.cost）**必须不进事件通道**；cond 修正型（ember_brand）与
    # 连招技型（combo_recover）已由 D3 2026-09-13 收口挂上观测点（见 battle_equip_proc.py
    # 「D3 已装」注 + we_affix_res_gain 的 cond_hp_lt 门槛）。
    p.setdefault("equipment", {})["weapon"] = {
        "slot": "weapon", "quality": "purple",
        "affixes": ["rage_forge", "full_pack", "energy_blade", "ember_brand",
                    "combo_recover"],
        "stats": {},
    }
    EP.apply_to_actor(p)
    tr = p.get("triggers") or {}

    def _keys(*evs):
        return {e.get("key") for ev in evs for e in (tr.get(ev) or [])}

    _all = _keys("attack_hit", "skill_hit", "on_taken", "turn_start", "act_cast")
    check("上限型零 triggers（bonus.cap 通道）",
          not (_all & {"rage_forge", "full_pack"}), f"triggers={tr}")
    check("cost_reduce 型零 triggers（bonus.cost 通道）",
          "energy_blade" not in _all, f"triggers={tr}")
    check("缺口词条零 effects 条目", not (p.get("effects") or {}),
          f"effects={p.get('effects')}")
    check("上限词条 bonus.cap 容器（非事件通道）", _capb(p).get("energy") == 10, f"bonus.cap={_capb(p)}")

    # ---- D3 收口（反证位：把候选事件全摘掉后下面两条必须红）----
    eb = [e for ev in ("attack_hit", "skill_hit", "on_taken") for e in (tr.get(ev) or [])
          if e.get("key") == "ember_brand"]
    check("D3 ember_brand 命中/技能/受击三观测点各挂一次", len(eb) == 3, f"{eb}")
    check("D3 ember_brand 参数（res=rage gain=1 cond_hp_lt=0.30）",
          len(eb) == 3 and all(
              e.get("res") == "rage" and e.get("gain") == 1
              and abs(float(e.get("cond_hp_lt") or 0) - 0.30) < 1e-9 for e in eb),
          f"{eb}")
    cr = [e for e in (tr.get("skill_hit") or []) if e.get("key") == "combo_recover"]
    check("D3 combo_recover 挂 skill_hit（res=chi gain=1）",
          len(cr) == 1 and cr[0].get("res") == "chi" and cr[0].get("gain") == 1, f"{cr}")


# ============================================================
# T8 m_affixtail：we_affix_res_gain cap 收敛 _cap_of（上限词条抬 cap 后可攒满）
# ============================================================

def test_affix_gain_dynamic_cap():
    print("【R4.8 affix 附赠通道 cap 收敛：full_pack 抬 cap 后暴击蓄能可攒满 110】")
    from saintess_engine.battle.effects import _cap_of
    # full_pack（purple +10 bonus.cap）+ crit_charge：crit 事件 energy+3 → cap 110
    p = mk_a("pd", "player")
    m = mk_a("ed", "enemy", hp=100000, atk=1)
    equip_affix(p, "full_pack", "armor", quality="purple")
    equip_affix(p, "crit_charge", "weapon", quality="purple")
    EP.apply_to_actor(p)
    check("full_pack bonus.cap.energy=10", _capb(p).get("energy") == 10, f"bonus.cap={_capb(p)}")
    check("_cap_of 动态 cap=110", _cap_of(p, "energy") == 110, f"cap={_cap_of(p, 'energy')}")
    b = new_battle(p, m)
    for _ in range(40):  # 40×3 = 120 > 动态 cap 110
        _fire(b, "crit", {"actor": p, "target": m, "dmg": 100}, [])
    check("词条附赠通道攒满动态 cap（110 而非旧静态 100）",
          stk(p, "energy") == 110, f"energy={stk(p, 'energy')}")
    # 对照：无 full_pack → 静态 cap 100 clamp（行为不变）
    p2 = mk_a("pe", "player")
    m2 = mk_a("ee", "enemy", hp=100000, atk=1)
    equip_affix(p2, "crit_charge", "weapon", quality="purple")
    EP.apply_to_actor(p2)
    b2 = new_battle(p2, m2)
    for _ in range(40):
        _fire(b2, "crit", {"actor": p2, "target": m2, "dmg": 100}, [])
    check("无上限词条仍静态 cap 100", stk(p2, "energy") == 100,
          f"energy={stk(p2, 'energy')}")
    # divine_radiance（faith cap+1）：holy_echo 治疗施放 faith+1 → 可攒 11
    p3 = mk_a("pf", "player")
    m3 = mk_a("ef", "enemy", hp=100000, atk=1)
    equip_affix(p3, "divine_radiance", "armor", quality="purple")
    equip_affix(p3, "holy_echo", "weapon", quality="blue")  # gain 1
    EP.apply_to_actor(p3)
    b3 = new_battle(p3, m3)
    check("divine_radiance bonus.cap.faith=1", _capb(p3).get("faith") == 1, f"bonus.cap={_capb(p3)}")
    for _ in range(12):  # 12 次治疗施放 → 超过基础 10
        _fire(b3, "act_cast", {"actor": p3, "target": m3,
                               "info": {"name": "愈", "kind": "治疗"}}, [])
    check("faith 附赠通道攒满动态 cap 11", stk(p3, "faith") == 11,
          f"faith={stk(p3, 'faith')}")


# ============================================================
# T9 m_affixtail：regen 型 turn_start 回能（energy_tide/swift_tailwind）
# ============================================================

def test_regen_type_turn_start():
    print("【R4.9 regen 型装配：energy_tide 每刻 +5（tier）/swift_tailwind 精力≥80 下刻 +10】")
    # energy_tide purple：turn_start energy +5（tier 取档）
    p = mk_a("pg", "player")
    m = mk_a("eg", "enemy", hp=100000, atk=1)
    equip_affix(p, "energy_tide", "armor", quality="purple")
    EP.apply_to_actor(p)
    tr = p.get("triggers") or {}
    ts = [e for e in tr.get("turn_start", []) if e.get("type") == "we_affix_res_gain"]
    check("energy_tide 装配 turn_start gain=5",
          len(ts) == 1 and ts[0].get("res") == "energy" and ts[0].get("gain") == 5
          and ts[0].get("cond_ge") is None, f"{ts}")
    b = new_battle(p, m)
    p.setdefault("effects", {})["energy"] = {"stacks": 50}
    act_land(b, ActCtx(caster=p, action="attack", target=m))  # turn_start 回能
    check("energy_tide 每刻精力+5（50→55）", stk(p, "energy") == 55,
          f"energy={stk(p, 'energy')}")
    # orange tier：+10
    p2 = mk_a("ph", "player")
    m2 = mk_a("eh", "enemy", hp=100000, atk=1)
    equip_affix(p2, "energy_tide", "armor", quality="orange")
    EP.apply_to_actor(p2)
    ts2 = [e for e in ((p2.get("triggers") or {}).get("turn_start", [])
                       if p2.get("triggers") else [])
           if e.get("type") == "we_affix_res_gain"]
    check("energy_tide 传说 tier gain=10", len(ts2) == 1 and ts2[0].get("gain") == 10,
          f"{ts2}")
    # swift_tailwind：energy<80 不触发；≥80 触发 +10（cap 100 clamp）
    p3 = mk_a("pi", "player")
    m3 = mk_a("ei", "enemy", hp=100000, atk=1)
    equip_affix(p3, "swift_tailwind", "armor", quality="orange")
    EP.apply_to_actor(p3)
    ts3 = [e for e in ((p3.get("triggers") or {}).get("turn_start", [])
                       if p3.get("triggers") else [])
           if e.get("type") == "we_affix_res_gain"]
    check("swift_tailwind 装配 cond_key=energy/cond_ge=80/gain=10",
          len(ts3) == 1 and ts3[0].get("cond_key") == "energy"
          and ts3[0].get("cond_ge") == 80 and ts3[0].get("gain") == 10, f"{ts3}")
    # ★ T15 两段化跟账：一次出手 = 登记 + 落地（真时钟推进到 T0+出招）⇒ 同一场战斗里
    #   连打 3 手会让「资源每刻自然回（time_advance 周期）」顺路叠进来（实测 +5/周期），
    #   这 3 条判据各是**独立场景**（只看那一次 turn_start 的触发）⇒ 每场景独立一场战斗。
    for _start, _want, _label in ((75, 75, "精力 75 <80 疾风余韵不触发"),
                                  (85, 95, "精力 85 ≥80 疾风余韵 +10（85→95）"),
                                  (95, 100, "疾风余韵 cap 100 clamp（95→100）")):
        _p3 = mk_a("pi%d" % _start, "player")
        _m3 = mk_a("ei%d" % _start, "enemy", hp=100000, atk=1)
        equip_affix(_p3, "swift_tailwind", "armor", quality="orange")
        EP.apply_to_actor(_p3)
        _b3 = new_battle(_p3, _m3)
        _p3.setdefault("effects", {})["energy"] = {"stacks": _start}
        act_land(_b3, ActCtx(caster=_p3, action="attack", target=_m3))
        check(_label, stk(_p3, "energy") == _want, f"energy={stk(_p3, 'energy')}")
    # 与上限词条联动：full_pack（purple bonus.cap+10）+ swift_tailwind 满 110
    p4 = mk_a("pj", "player")
    m4 = mk_a("ej", "enemy", hp=100000, atk=1)
    equip_affix(p4, "swift_tailwind", "armor", quality="orange")
    equip_affix(p4, "full_pack", "ring", quality="purple")
    EP.apply_to_actor(p4)
    b4 = new_battle(p4, m4)
    p4.setdefault("effects", {})["energy"] = {"stacks": 100}
    act_land(b4, ActCtx(caster=p4, action="attack", target=m4))  # 100 ≥80 → +10 → 110
    check("full_pack 抬 cap 后疾风余韵攒满 110", stk(p4, "energy") == 110,
          f"energy={stk(p4, 'energy')}")


def main():
    print("=== R4 affix 资源型词条装配测试 ===")
    test_translate_gain_rule()
    test_war_spirit_end2end()
    test_opening_stance()
    test_boiling_blood()
    test_taken_and_kind_filters()
    test_crit_res_gain()
    test_gap_affixes_no_noise()
    test_affix_gain_dynamic_cap()
    test_regen_type_turn_start()
    print(f"\n=== 结果 PASS={PASS} FAIL={FAIL} ===")
    if FAILURES:
        for f in FAILURES:
            print(f"  - {f}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
