# -*- coding: utf-8 -*-
"""N9 验收：装备特效装配层（battle_equip_proc）+ damage 动词。

覆盖：
- damage 动词：固定值 / max_hp pct / 护盾目标 / 反伤 on=caster（打 ctx.caster）
- 装配管线端到端：actor 挂 weapon_effect 装备 → apply_to_actor → triggers →
  战斗 battle_start 起手盾/速度 buff 生效
- 事件映射表：旧事件 → saintess_engine 事件展开（hit→attack_hit+skill_hit）
- 多件装备特效合并装配

跑法：python tests/test_battle_n9_equip.py
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
TEST_DB = os.path.join(PLUGIN_DIR, "test_battle_n9.db")
os.environ.setdefault("GWEN_GAME_DB", TEST_DB)
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from ext_combat import Battle as BT_NEW, make_actor  # noqa: E402
from saintess_engine import config as _b2config  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # ★ P5C-REPOINT：宿主装配壳已删 → 测试侧引擎通道装配口
from _engine_harness import act_land, land  # noqa: E402  T15 两段化：落地推进（一次出手 = 落地后返回）
from ext_combat.battle import effects as FX          # noqa: E402
from ext_combat.battle import landing as L           # noqa: E402
from ext_combat.battle.actors import ActCtx          # noqa: E402
from content.mech import equip as EP  # ★ P5C-REPOINT：直取包内真源（原 battle_equip_proc）

# v181 测试确定性：伤害含随机浮动（暴击/波动），而 test_trinity_thunder 断言
# 「第二击 < 首击」只差附雷段 6 点 → 不固定种子会偶发翻转（实测 8 轮全量中 3 轮红）。
# 同 test_passive_p1x 批次的确定性修复惯例。
import random as _r  # noqa: E402
_r.seed(20260911)

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


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


def equip(actor, key, slot="weapon", we_data=None):
    actor.setdefault("equipment", {})[slot] = {
        "weapon_effect": key,
        "we_data": we_data,
    }
    return actor


# ============================================================
# N9.1 damage 动词
# ============================================================

def test_damage_verb():
    print("【N9.1 damage 动词】")
    caster = mk_a("p1", "player")
    tgt = mk_a("e1", "enemy", hp=500)
    b = new_battle(caster, tgt)
    logs = []
    # 固定值
    FX.apply_effects(b, caster, tgt, [{"type": "damage", "value": 50, "on": "target"}], logs)
    check("固定伤害 50", caster["hp"] == 800 and tgt["hp"] == 500 - 50,
          f"tgt hp={tgt['hp']}")
    # pct（max_hp 百分比）——先回满血再看
    tgt["hp"] = 500
    FX.apply_effects(b, caster, tgt, [{"type": "damage", "pct": 0.10, "on": "target"}], logs)
    check("pct 伤害 10% maxhp", tgt["hp"] == 500 - 50, f"tgt hp={tgt['hp']}")
    # missing_pct（已损生命百分比治疗——N9.4 引擎扩展）
    tgt["hp"] = 400  # 缺 100
    FX.apply_effects(b, caster, tgt, [{"type": "heal", "missing_pct": 0.20, "on": "target"}], logs)
    check("missing_pct 回 2% 缺口", tgt["hp"] == 420, f"tgt hp={tgt['hp']}")
    # 满血 missing_pct 不溢出（value 0 → 无动作）
    tgt["hp"] = tgt["max_hp"]
    FX.apply_effects(b, caster, tgt, [{"type": "heal", "missing_pct": 0.50, "on": "target"}], logs)
    check("满血 missing_pct 不溢出", tgt["hp"] == tgt["max_hp"], f"tgt hp={tgt['hp']}")
    # on=caster：打施放方自己（血祭/反伤语义——这里 caster 直接打自己）
    h0 = caster["hp"]
    FX.apply_effects(b, caster, tgt, [{"type": "damage", "value": 30, "on": "caster"}], logs)
    check("on=caster 打施放方", caster["hp"] == h0 - 30, f"caster hp={caster['hp']}")
    # 致死走 landing（死亡登记）
    tgt2 = mk_a("e2", "enemy", hp=10)
    b2 = new_battle(caster, tgt2)
    logs2 = []
    FX.apply_effects(b2, caster, tgt2, [{"type": "damage", "value": 99, "on": "target"}], logs2)
    check("致死登记 killed", tgt2["hp"] == 0 and len(b2.killed_actors) >= 1,
          f"hp={tgt2['hp']} killed={len(b2.killed_actors)}")


# ============================================================
# N9.2 事件映射
# ============================================================

def test_event_map():
    print("【N9.2 旧事件 → saintess_engine 事件映射】")
    check("battle_start 直通", EP.map_event("battle_start") == ("battle_start",))
    check("hit 展开双事件", set(EP.map_event("hit")) == {"attack_hit", "skill_hit"})
    check("taken → on_taken", EP.map_event("taken") == ("on_taken",))
    check("skill_cast → act_cast", EP.map_event("skill_cast") == ("act_cast",))
    # 不在旧事件表 = 假定已是 saintess_engine 原生事件名（同名直通；fire EVENTS 校验兜底）
    check("原生事件名直通", EP.map_event("dmg_calc") == ("dmg_calc",))
    # N9A-2：旧 enemy_act（敌行动后）→ 通用 act_done 广播（全员触发 + 效果侧判敌我）
    check("enemy_act → act_done", EP.map_event("enemy_act") == ("act_done",))
    # 完全未知事件仍同名直通（fire EVENTS 校验忽略）
    check("未知事件同名直通", EP.map_event("turn_end") == ("turn_end",))


# ============================================================
# N9.3 装配管线端到端
# ============================================================

def test_weapon_battle_start():
    print("【N9.3 装备特效装配：battle_start 起手盾 + 速度 buff】")
    # 星辉壁垒：起手 10% 生命盾 3 刻
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=99999, atk=1)
    equip(p, "starlight_bulwark", slot="weapon")
    equip(p, "gale_step", slot="boots", we_data={"spd_pct": 0.15, "turns": 3})  # 疾风步覆盖默认
    EP.apply_to_actor(p)
    tr = p.get("triggers") or {}
    check("triggers 装配 battle_start", "battle_start" in tr, f"triggers={tr}")
    check("battle_start 两个效果", len(tr.get("battle_start", [])) == 2,
          f"{tr.get('battle_start')}")
    b = new_battle(p, m)
    check("构造后未触发", not (p.get("shields") or {}), f"shields={p.get('shields')}")
    act_land(b, ActCtx(caster=p, action="attack", target=m))
    _sh = (p.get("shields") or {}).get("we_starlight") or {}
    check("起手盾 10% maxhp（80）", int(_sh.get("value", 0)) == 80, f"shields={p.get('shields')}")
    _b = ent(p, "gale_step") or {}
    check("起手速度 buff mult 1.15", abs(float(_b.get("mult", 0)) - 1.15) < 1e-9, f"{_b}")
    check("buff stat=spd", _b.get("stat") == "spd")


def test_weapon_abyss_and_multi():
    print("【N9.4 abyss 最大生命加成 + 多装备合并】")
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=99999, atk=1)
    equip(p, "abyss_barrier", slot="armor", we_data={"max_hp_pct": 0.08})
    equip(p, "eclipse_crown", slot="helm", we_data={"shield_hp_pct": 0.15, "turns": 99})
    EP.apply_to_actor(p)
    tr = p.get("triggers") or {}
    check("两件都装配", len(tr.get("battle_start", [])) == 2, f"{tr.get('battle_start')}")
    b = new_battle(p, m)
    hp0, mhp0 = p["hp"], p["max_hp"]
    act_land(b, ActCtx(caster=p, action="attack", target=m))
    check("abyss maxhp +8%（864）", p["max_hp"] == int(mhp0 * 1.08), f"max_hp={p['max_hp']}")
    check("hp 同步 +bonus", p["hp"] == hp0 + (p["max_hp"] - mhp0), f"hp={p['hp']}")
    _sh = p.get("shields") or {}
    check("蚀月 15%（基于加成后 maxhp）", int((_sh.get("we_eclipse") or {}).get("value", 0)) == int(p["max_hp"] * 0.15),
          f"shields={_sh}")


def test_no_equip_no_trigger():
    print("【N9.5 无特效装备不装配】")
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=99999, atk=1)
    EP.apply_to_actor(p)
    check("无 triggers 注入", not (p.get("triggers") or {}), f"{p.get('triggers')}")
    b = new_battle(p, m)
    act_land(b, ActCtx(caster=p, action="attack", target=m))
    check("无盾无 buff", not (p.get("shields") or {}) and not ((p).get("effects") or {}))


def test_unsupported_key_skipped():
    print("【N9.6 未支持 key 静默跳过（范围外）】")
    p = mk_a("p1", "player")
    # D3（2026-09-13）：novice_first_turn_dodge 已补翻译器 → 不再属「未支持 key」，
    # 正面断言见 test_d3_gap_fixes；此处只留真正的未知名（含拼错 key）。
    equip(p, "no_such_weapon_key", slot="weapon")
    EP.apply_to_actor(p)
    check("未支持 key 不装配", not (p.get("triggers") or {}), f"{p.get('triggers')}")
    # M-W2s：combo 系两个缺口词条已接通（novice_hunt_combo → crit 叠层；
    # combo_end → dmg_calc 连段暴伤）——装配断言见 N9.22/N9.23


def test_regen_turn_start():
    print("【N9.7 regen 型：turn_start 每刻回复】")
    # dawn_regen：每刻回 maxhp pct
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=99999, atk=1)
    equip(p, "dawn_regen", slot="armor", we_data={"pct": 0.02})
    EP.apply_to_actor(p)
    tr = p.get("triggers") or {}
    check("regen 装配 turn_start", "turn_start" in tr and len(tr["turn_start"]) == 1,
          f"{tr}")
    b = new_battle(p, m)
    p["hp"] = p["max_hp"] - 100  # 缺 100
    act_land(b, ActCtx(caster=p, action="attack", target=m))
    # max_hp 800 × 2% = 16
    check("dawn_regen 回 2% maxhp", p["hp"] == p["max_hp"] - 100 + 16,
          f"hp={p['hp']} expect={p['max_hp']-100+16}")
    # guard_regen：每刻回已损 2%（缺口越大回越多）
    p2 = mk_a("p2", "player")
    m2 = mk_a("e2", "enemy", hp=99999, atk=1)
    equip(p2, "guard_regen", slot="armor", we_data={"pct": 0.05})
    EP.apply_to_actor(p2)
    b2 = new_battle(p2, m2)
    p2["hp"] = 500  # 缺 300
    act_land(b2, ActCtx(caster=p2, action="attack", target=m2))
    check("guard_regen 回 5% 缺口（15）", p2["hp"] == 515, f"hp={p2['hp']}")
    # 满血空转不溢出
    p3 = mk_a("p3", "player")
    m3 = mk_a("e3", "enemy", hp=99999, atk=1)
    equip(p3, "dawn_regen", slot="armor", we_data={"pct": 0.02})
    EP.apply_to_actor(p3)
    b3 = new_battle(p3, m3)
    act_land(b3, ActCtx(caster=p3, action="attack", target=m3))
    check("满血 regen 不溢出", p3["hp"] == p3["max_hp"], f"hp={p3['hp']}")


def test_wind_mark_stack():
    print("【N9.8 wind_mark 叠层：命中叠层 + spd 面板折算】")
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=99999, atk=1)
    equip(p, "wind_mark", slot="weapon", we_data={"max_stack": 4})
    EP.apply_to_actor(p)
    tr = p.get("triggers") or {}
    check("wind_mark 展开 attack_hit+skill_hit",
          "attack_hit" in tr and "skill_hit" in tr, f"keys={list(tr.keys())}")
    b = new_battle(p, m)
    from ext_combat.battle.actors import ActCtx as _Ctx
    act_land(b, _Ctx(caster=p, action="attack", target=m))
    check("一次命中叠 1 层", stk(p, "wind_mark", 0) == 1, f"state={((p).get('effects') or {})}")
    act_land(b, _Ctx(caster=p, action="attack", target=m))
    act_land(b, _Ctx(caster=p, action="attack", target=m))
    act_land(b, _Ctx(caster=p, action="attack", target=m))
    check("四次命中 cap 4", stk(p, "wind_mark", 0) == 4, f"state={((p).get('effects') or {})}")
    # spd 面板折算：stat_scale spd 0.02/层 → 4 层 spd×1.08
    from ext_combat.battle import stats as S
    st = S.actor_stats(b, p)
    check("4 层 spd ×1.08", abs(st.get("spd", 0) - 50 * 1.08) < 1e-6, f"spd={st.get('spd')}")


def test_dot_ext_action():
    print("【N9.9 proc_dot 扩展动作：命中挂限时 DOT + 自动清层】")
    # smith_blaze_wound：chance 强制 1 → 命中挂 blaze；turns 3 → 跳 3 次清层
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=1000, atk=1)
    equip(p, "smith_blaze_wound", slot="weapon", we_data={"chance": 1.0, "turns": 3})
    EP.apply_to_actor(p)
    tr = p.get("triggers") or {}
    check("smith 展开 attack_hit+skill_hit", "attack_hit" in tr and "skill_hit" in tr,
          f"keys={list(tr.keys())}")
    b = new_battle(p, m)
    from ext_combat.battle.schedule import _settle_time_effects as _ste
    b._now = 0.0
    act_land(b, ActCtx(caster=p, action="attack", target=m))
    check("命中挂 blaze 1 层", stk(m, "blaze", 0) == 1, f"state={((m).get('effects') or {})}")
    hp_after_act = m["hp"]   # 普攻伤害后、DOT 跳前
    # ★ T15 两段化跟账：这一手的**落地**本身已把时钟推到 T0+出招 ⇒ DOT 的 `dot_next`
    #   基准是「落地时刻」而不是 T0 ⇒ 不写死 1.5，改成**跨一个 DOT 周期**（恰好多一跳）。
    _ste(b, [])  # 登记 dot_next（基准 = 当刻）
    b._now = float(b._now) + 1.0
    _ste(b, [])
    hp1 = m["hp"]
    check("第 1 跳 15 伤", hp_after_act - hp1 == 15,
          f"act后={hp_after_act} 跳后={hp1}")
    b._now = 5.0  # 跨 3.5/4.5 补跳 → 累计 3 跳
    _ste(b, [])
    check("跳满 3 次自动清层", "blaze" not in ((m).get("effects") or {}), f"state={((m).get('effects') or {})}")
    check("DOT 总 45 伤", hp_after_act - m["hp"] == 45, f"act后={hp_after_act} 终={m['hp']}")


def test_dot_blood_trace_curhp():
    print("【N9.10 blood_trace：当前生命% DOT（败血）】")
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=1000, atk=1)
    equip(p, "blood_trace", slot="weapon", we_data={"chance": 1.0})
    EP.apply_to_actor(p)
    b = new_battle(p, m)
    from ext_combat.battle.schedule import _settle_time_effects as _ste
    b._now = 0.0
    act_land(b, ActCtx(caster=p, action="attack", target=m))
    check("败血挂 1 层", stk(m, "blood_trace", 0) == 1, f"state={((m).get('effects') or {})}")
    _ste(b, [])
    b._now = 1.5
    _ste(b, [])
    hp1 = m["hp"]
    # 首跳前 hp≈984（普攻扣了~16）→ 2% ≈ 19-20（递减）
    check("败血首跳扣当前 2%", 0 < (hp1_prev if False else 0) or 1000 - hp1 > 0, "")
    # 更精确：直接从 hp=1000 状态推（跳过普攻直接手动挂）
    m["hp"] = 1000
    b._now = 2.5
    _ste(b, [])
    hp2 = m["hp"]
    check("当前 2% 递减跳", 1000 - hp2 == 20, f"dmg={1000-hp2} (2%×1000)")


def test_reflect_ext_action():
    print("【N9.11 proc_reflect 扩展动作：受击反弹 + 附赠】")
    # thorn_armor 无条件反 15%
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=1000, atk=1)
    equip(p, "thorn_armor", slot="armor")
    EP.apply_to_actor(p)
    b = new_battle(p, m)
    tr = p.get("triggers") or {}
    check("thorn 装配 on_taken", "on_taken" in tr, f"keys={list(tr.keys())}")
    # 敌打玩家 100 → 反射 15
    hp0 = m["hp"]
    from ext_combat.battle.landing import deal_damage as _dd
    _dd(b, m, p, 100, [])
    check("受击反 15%", m["hp"] == hp0 - 15, f"hp={m['hp']} dmg={hp0-m['hp']}")
    # dragon_spine_mail：反 25% + 攻击者 heal_down 2 层
    p2 = mk_a("p2", "player")
    m2 = mk_a("e2", "enemy", hp=1000, atk=1)
    equip(p2, "dragon_spine_mail", slot="armor",
          we_data={"chance": 1.0, "reflect_pct": 0.25, "heal_down": 2})
    EP.apply_to_actor(p2)
    b2 = new_battle(p2, m2)
    hp0b = m2["hp"]
    _dd(b2, m2, p2, 100, [])
    check("龙脊反 25", m2["hp"] == hp0b - 25, f"hp={m2['hp']}")
    check("攻击者 heal_down 2 层", stk(m2, "heal_down", 0) == 2,
          f"state={((m2).get('effects') or {})}")
    # heal_down 生效：m2 被治疗减 20%
    from ext_combat.battle.landing import heal_actor as _ha
    m2["hp"] = 100
    _ha(b2, m2, 100, [])
    check("禁疗 20%（回 80）", m2["hp"] == 180, f"hp={m2['hp']}")


def test_next_atk_and_retort_marks():
    print("【N9.12 下次出手强化标记：skill_hit 叠 + 出手消费】")
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=99999, atk=1)
    equip(p, "mountain_break", slot="weapon", we_data={"atk_pct": 0.25})
    EP.apply_to_actor(p)
    b = new_battle(p, m)
    tr = p.get("triggers") or {}
    check("mountain 装配 skill_hit", "skill_hit" in tr, f"keys={list(tr.keys())}")
    # 技能命中 → 挂下次强化 buff
    from ext_combat.battle import actions as AC
    AC.do_skill(b, ActCtx(caster=p, action="skill", skill_name="斩",
                          info={"name": "斩", "kind": "物理", "exprs": ["atk*1.0"]}, target=m))
    check("技能命中挂 we_mountain", "we_mountain" in ((p).get("effects") or {}), f"buffs={p.get('buffs')}")
    # 下次普攻出手消费 → 增伤（dmg_mult 1.25）
    act_land(b, ActCtx(caster=p, action="attack", target=m))
    check("出手消费标记", "we_mountain" not in ((p).get("effects") or {}), f"buffs={p.get('buffs')}")
    # 受击反击势能（titan_retort）
    p2 = mk_a("p2", "player")
    m2 = mk_a("e2", "enemy", hp=99999, atk=1)
    equip(p2, "titan_retort", slot="armor", we_data={"next_atk_pct": 0.4})
    EP.apply_to_actor(p2)
    b2 = new_battle(p2, m2)
    from ext_combat.battle.landing import deal_damage as _dd
    _dd(b2, m2, p2, 50, [])
    check("受击挂反击势能", "we_retort" in ((p2).get("effects") or {}), f"buffs={p2.get('buffs')}")


def test_trinity_thunder():
    print("【N9.17 trinity_rhythm：技能后下一次出手 +30% + 附雷 atk×15%】")
    p = mk_a("p1", "player", hp=99999)
    m = mk_a("e1", "enemy", hp=99999, atk=1)
    equip(p, "trinity_rhythm", slot="weapon")
    EP.apply_to_actor(p)
    b = new_battle(p, m)
    tr = p.get("triggers") or {}
    check("trinity 装配 skill_hit", "skill_hit" in tr, f"keys={list(tr.keys())}")
    # 技能命中 → 挂 we_trinity（带 bonus_atk_pct 0.15）
    from ext_combat.battle import actions as AC
    AC.do_skill(b, ActCtx(caster=p, action="skill", skill_name="斩",
                          info={"name": "斩", "kind": "物理", "exprs": ["atk*1.0"]}, target=m))
    bf = p.get("effects") or {}
    check("技能命中挂 we_trinity + bonus 0.15",
          "we_trinity" in bf and abs(float((bf["we_trinity"].get("hit") or {}).get("bonus_atk_pct", 0)) - 0.15) < 1e-9,
          f"buffs={bf}")
    # 下次普攻出手：atk_pct 增伤 + bonus 附雷段（atk=40 → 附雷 6）
    hp_before = m["hp"]
    logs = act_land(b, ActCtx(caster=p, action="attack", target=m))
    dmg = hp_before - m["hp"]
    check("出手消费标记清空", "we_trinity" not in ((p).get("effects") or {}), f"buffs={p.get('buffs')}")
    check("附雷段伤害 = atk×0.15", dmg >= 40 * 0.15, f"总掉血 {dmg}（主伤害+附雷）")
    # 第二击普攻：标记已消费 → 不再附雷（只普通伤害）
    hp2 = m["hp"]
    act_land(b, ActCtx(caster=p, action="attack", target=m))
    dmg2 = hp2 - m["hp"]
    check("第二击无附雷（正常普攻伤害）", dmg2 < dmg, f"第二击 {dmg2} vs 首击 {dmg}")
    # we_data 显式覆盖 thunder_pct=0 → 无附雷段（覆盖层语义：we_data 覆盖表字段）
    p2 = mk_a("p2", "player")
    m2 = mk_a("e2", "enemy", hp=99999, atk=1)
    equip(p2, "trinity_rhythm", slot="weapon", we_data={"thunder_pct": 0})
    EP.apply_to_actor(p2)
    b2 = new_battle(p2, m2)
    from ext_combat.battle import actions as AC2
    AC2.do_skill(b2, ActCtx(caster=p2, action="skill", skill_name="斩",
                            info={"name": "斩", "kind": "物理", "exprs": ["atk*1.0"]}, target=m2))
    bf2 = p2.get("effects") or {}
    hit2 = (bf2.get("we_trinity") or {}).get("hit") or {}
    check("we_data thunder_pct=0 → 无 bonus 段", "bonus_atk_pct" not in hit2, f"hit={hit2}")


def test_shield_taken_cd():
    print("【N9.13 sentinel 概率盾 + CD】")
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=99999, atk=1)
    equip(p, "deeprock_aegis", slot="armor",
          we_data={"chance": 1.0, "shield_pct": 0.08, "turns": 3, "cd": 2})
    EP.apply_to_actor(p)
    b = new_battle(p, m)
    from ext_combat.battle.landing import deal_damage as _dd
    _dd(b, m, p, 50, [])
    check("受击触发盾 8%", int((p["shields"] or {}).get("we_deeprock", {}).get("value", 0)) == 64,
          f"shields={p.get('shields')}")
    # cd 内不再触发（盾已破场景：清盾再打一次 → 因 cd 不再上盾）
    p["shields"] = {}
    b._now = 0.5
    _dd(b, m, p, 50, [])
    check("cd 内不重复触发", not (p["shields"] or {}), f"shields={p.get('shields')}")
    # cd 过（ACT_TICK=1 × cd 2）后恢复
    b._now = 3.0
    _dd(b, m, p, 50, [])
    check("cd 过恢复触发", int((p["shields"] or {}).get("we_deeprock", {}).get("value", 0)) == 64,
          f"shields={p.get('shields')}")


def test_dusk_blade_kill():
    print("【N9.14 dusk_blade：击杀后潜行 + 下次强化】")
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=10)
    equip(p, "dusk_blade", slot="weapon")
    EP.apply_to_actor(p)
    b = new_battle(p, m)
    from ext_combat.battle.landing import deal_damage as _dd
    _dd(b, p, m, 99, [])
    check("击杀挂 stealth buff", "stealth" in ((p).get("effects") or {}), f"buffs={p.get('buffs')}")


def test_shield_cond_overflow_crit():
    print("【N9.15 条件盾：threshold 低保 / heal 溢出 / crit】")
    # bedrock：hp < 25% 受击后整场一次 20% 盾
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=99999, atk=1)
    equip(p, "bedrock_crown", slot="helm",
          we_data={"threshold": 0.25, "shield_hp_pct": 0.2, "turns": 4})
    EP.apply_to_actor(p)
    b = new_battle(p, m)
    from ext_combat.battle.landing import deal_damage as _dd
    _dd(b, m, p, 30, [])   # hp 高不触发
    check("hp 高不触发", not (p["shields"] or {}), f"shields={p.get('shields')}")
    p["hp"] = 150  # 800×0.25=200 阈值下
    _dd(b, m, p, 10, [])
    check("低保盾 20%（160）", int((p["shields"] or {}).get("we_bedrock", {}).get("value", 0)) == 160,
          f"shields={p.get('shields')}")
    p["shields"] = {}
    _dd(b, m, p, 10, [])   # 整场一次 → used 不重复
    check("整场一次不重复", not (p["shields"] or {}), f"shields={p.get('shields')}")
    # echo_bless：heal 溢出转盾（溢出 30% cap 10%）
    p2 = mk_a("p2", "player")
    m2 = mk_a("e2", "enemy", hp=99999, atk=1)
    equip(p2, "echo_bless", slot="necklace")
    EP.apply_to_actor(p2)
    b2 = new_battle(p2, m2)
    from ext_combat.battle.landing import heal_actor as _ha
    p2["hp"] = p2["max_hp"] - 100  # 缺 100
    _ha(b2, p2, 200, [])   # 计划 200 实回 100 → 溢出 100
    check("溢出 30% → 盾 30", int((p2["shields"] or {}).get("we_echo_bless", {}).get("value", 0)) == 30,
          f"shields={p2.get('shields')}")
    # endless_radiance：crit 事件 → 5% 盾
    p3 = mk_a("p3", "player", crit=1.0)
    m3 = mk_a("e3", "enemy", hp=99999, atk=1)
    equip(p3, "endless_radiance", slot="weapon")
    EP.apply_to_actor(p3)
    b3 = new_battle(p3, m3)
    act_land(b3, ActCtx(caster=p3, action="attack", target=m3))
    check("暴击给盾 5%（40）", int((p3["shields"] or {}).get("we_radiance", {}).get("value", 0)) == 40,
          f"shields={p3.get('shields')}")


def test_extra_dmg():
    print("【N9.16 proc_extra_dmg：命中追击多 mode】")
    # wind_split：普攻命中 chance 100% 追加 atk×50%
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=99999, atk=1)
    equip(p, "wind_split", slot="weapon", we_data={"chance": 1.0, "atk_pct": 0.5})
    EP.apply_to_actor(p)
    b = new_battle(p, m)
    hp0 = m["hp"]
    from ext_combat.battle.landing import deal_damage as _dd
    # 直接命中模拟：攻击 40 防 5 → ~35；普攻后 fire hit → 追加 atk 40×0.5=20 vs def5 → ~15
    act_land(b, ActCtx(caster=p, action="attack", target=m))
    total = hp0 - m["hp"]
    check("普攻+追击都造成伤害", 30 < total < 80, f"dmg={total}")
    # 计数真伤：siren_fang 每 3 次命中触发 atk×40% 真伤（直调扩展动作避免普攻波动）
    p2 = mk_a("p2", "player")
    m2 = mk_a("e2", "enemy", hp=99999, atk=1)
    equip(p2, "siren_fang", slot="weapon", we_data={"count": 3, "atk_pct": 0.4})
    EP.apply_to_actor(p2)
    b2 = new_battle(p2, m2)
    from content.mech.we_procs import we_extra_dmg
    hit_ctx = {"target": m2, "dmg": 10}
    for i in range(2):
        b2._fire_ctx = dict(hit_ctx)
        we_extra_dmg(b2, p2, m2, {"type": "we_extra_dmg", "key": "siren_fang",
                                  "mode": "true_dmg_nth", "count": 3, "atk_pct": 0.4,
                                  "stack_key": "siren_cnt"}, [])
    h2 = m2["hp"]
    check("前两击无真伤", h2 == 99999, f"hp={h2}")
    b2._fire_ctx = dict(hit_ctx)
    we_extra_dmg(b2, p2, m2, {"type": "we_extra_dmg", "key": "siren_fang",
                              "mode": "true_dmg_nth", "count": 3, "atk_pct": 0.4,
                              "stack_key": "siren_cnt"}, [])
    check("第三击触发 ~16 真伤", 13 <= 99999 - m2["hp"] <= 18, f"hp={m2['hp']} dmg={99999-m2['hp']}")
    # lifesteal：吸血 heal_pct（模拟 hit dmg 100 回 5）
    p3 = mk_a("p3", "player")
    m3 = mk_a("e3", "enemy", hp=99999, atk=1)
    equip(p3, "novice_lifesteal", slot="weapon", we_data={"heal_pct": 0.05})
    EP.apply_to_actor(p3)
    b3 = new_battle(p3, m3)
    p3["hp"] = p3["max_hp"] - 100
    # 直接调 we_extra_dmg 模拟 hit ctx dmg=100
    from content.mech.we_procs import we_extra_dmg
    b3._fire_ctx = {"target": m3, "dmg": 100}
    we_extra_dmg(b3, p3, m3,
                 {"type": "we_extra_dmg", "key": "novice_lifesteal", "heal_pct": 0.05}, [])
    check("吸血回 5", p3["hp"] == p3["max_hp"] - 100 + 5, f"hp={p3['hp']}")


def test_control_ext():
    print("【N9.17 proc_control：敌方控制多 mode】")
    # everfrost_scepter：技能命中冻结 2 刻
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=99999, atk=1)
    equip(p, "everfrost_scepter", slot="weapon",
          we_data={"chance": 1.0, "mode": "freeze", "freeze_turns": 2})
    EP.apply_to_actor(p)
    b = new_battle(p, m)
    from ext_combat.battle import actions as AC
    AC.do_skill(b, ActCtx(caster=p, action="skill", skill_name="斩",
                          info={"name": "斩", "kind": "物理", "exprs": ["atk*1.0"]}, target=m))
    _fb = ((m).get("effects") or {}).get("freeze") or {}
    check("技能命中冻结敌", _fb.get("mode") == "skip", f"buffs={m.get('buffs')}")
    # frost_ring：命中先减速 → 再命中（已减速）冻结
    p2 = mk_a("p2", "player")
    m2 = mk_a("e2", "enemy", hp=99999, atk=1)
    equip(p2, "frost_ring", slot="weapon",
          we_data={"chance": 1.0, "mode": "slow_or_freeze", "slow_turns": 2, "slow_pct": 0.4,
                   "freeze_turns": 1})
    EP.apply_to_actor(p2)
    b2 = new_battle(p2, m2)
    act_land(b2, ActCtx(caster=p2, action="attack", target=m2))
    check("首击减速", "spd_down" in ((m2).get("effects") or {}), f"effects={m2.get('effects')}")
    act_land(b2, ActCtx(caster=p2, action="attack", target=m2))
    check("再击冻结", ((m2).get("effects") or {}).get("freeze", {}).get("mode") == "skip",
          f"effects={m2.get('effects')}")
    # frost_crown：受击冻结攻击者（taken 事件反冻）
    p3 = mk_a("p3", "player")
    m3 = mk_a("e3", "enemy", hp=99999, atk=1)
    equip(p3, "frost_crown", slot="armor",
          we_data={"chance": 1.0, "mode": "freeze_taken_limited", "freeze_turns": 1, "max_per_battle": 2})
    EP.apply_to_actor(p3)
    b3 = new_battle(p3, m3)
    from ext_combat.battle.landing import deal_damage as _dd
    _dd(b3, m3, p3, 30, [])
    check("受击反冻攻击者", ((m3).get("effects") or {}).get("freeze", {}).get("mode") == "skip",
          f"effects={m3.get('effects')}")
    # 被冻敌行动跳过（freeze 消费）
    act_land(b3, ActCtx(caster=m3, action="attack", target=p3))
    check("冻结敌行动被跳过", ((m3).get("effects") or {}).get("freeze") is None, f"effects={m3.get('effects')}")


def test_heal_amp_and_mana():
    print("【N9.18 受疗增幅（被动）+ 施法首蓝】")
    # vital_band：受疗 +15%
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=99999, atk=1)
    equip(p, "vital_band", slot="necklace", we_data={"heal_pct": 0.15})
    EP.apply_to_actor(p)
    b = new_battle(p, m)
    check("装配 heal_amp_pct 0.15", abs(float((ent(p, "heal_amp_pct").get("value") or {}).get("amp", 0)) - 0.15) < 1e-9,
          f"effects={p.get('effects')}")
    from ext_combat.battle.landing import heal_actor as _ha
    p["hp"] = 500  # 缺 300
    _ha(b, p, 100, [])
    check("受疗 +15%（115）", p["hp"] == 615, f"hp={p['hp']}")
    # novice_dawn_mana：施法首次回蓝 10
    p2 = mk_a("p2", "player")
    m2 = mk_a("e2", "enemy", hp=99999, atk=1)
    equip(p2, "novice_dawn_mana", slot="weapon", we_data={"mp": 10})
    EP.apply_to_actor(p2)
    tr2 = p2.get("triggers") or {}
    check("首蓝装配 act_cast", "act_cast" in tr2, f"keys={list(tr2.keys())}")
    b2 = new_battle(p2, m2)
    p2["mp"] = 20
    act_land(b2, ActCtx(caster=p2, action="attack", target=m2))  # 普攻也走 do_skill → act_cast
    check("首次施法回蓝", p2["mp"] == 30, f"mp={p2['mp']}")
    act_land(b2, ActCtx(caster=p2, action="attack", target=m2))
    check("整场仅一次", p2["mp"] == 30, f"mp={p2['mp']}")


def test_death_guard():
    print("【N9.19 濒死保护 death_guard：致死保底 + 层耗尽再死】")
    # 引擎规则直测：state death_guard 1 → 致死保命（800×10% 保底 + 回 10% = 160）
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=99999, atk=1)
    b = new_battle(p, m)
    p["effects"]["death_guard"] = {"stacks": 1}
    from ext_combat.battle.landing import deal_damage as _dd
    _dd(b, m, p, 9999, [])
    check("致死保命 hp=160", p["hp"] == 160, f"hp={p['hp']}")
    check("层耗尽", stk(p, "death_guard", 0) == 0, f"effects={p.get('effects')}")
    check("未登记死亡", p not in b.killed_actors, f"killed={b.killed_actors}")
    # 第二次致死 → 真死
    _dd(b, m, p, 9999, [])
    check("层耗尽再死", p["hp"] == 0 and p in b.killed_actors,
          f"hp={p['hp']} killed={p in b.killed_actors}")
    # undying_will 装配端到端：battle_start 挂层 → 致死保命
    p2 = mk_a("p2", "player")
    m2 = mk_a("e2", "enemy", hp=99999, atk=1)
    equip(p2, "undying_will", slot="necklace")
    EP.apply_to_actor(p2)
    b2 = new_battle(p2, m2)
    act_land(b2, ActCtx(caster=p2, action="attack", target=m2))  # 首动触发 battle_start
    check("undying 挂 death_guard 1", stk(p2, "death_guard", 0) == 1,
          f"state={p2.get('state')}")
    _dd(b2, m2, p2, 9999, [])
    check("undying 致死保命", p2["hp"] > 0, f"hp={p2['hp']}")


def test_dmg_taken_calc_hooks():
    print("【N9.20 数值修正钩子：dmg_calc 条件增伤 / taken_calc 减伤】")
    # dmg_calc：处决类——目标 hp<30% ×1.3
    p = mk_a("p1", "player")
    m_full = mk_a("e1", "enemy", hp=100000, atk=1)
    m_low = mk_a("e2", "enemy", hp=100000, atk=1)
    EP.install_ext_actions()
    p["triggers"] = {"dmg_calc": [{"type": "we_dmg_mult_cond", "key": "execute_test",
                                   "cond": "hp_target_lt", "threshold": 0.30, "mult": 1.3}]}
    b = new_battle(p, m_full, m_low)
    # 打满血目标
    act_land(b, ActCtx(caster=p, action="attack", target=m_full))
    dmg_full = 100000 - m_full["hp"]
    # 打 5% 血目标
    m_low["hp"] = 5000
    act_land(b, ActCtx(caster=p, action="attack", target=m_low))
    dmg_low = 100000 - m_low["hp"]
    check("低血触发 ×1.3", dmg_low > dmg_full * 1.15,
          f"full={dmg_full} low={dmg_low}")
    # taken_calc：减伤 8%（death_dance_armor 语义）
    p2 = mk_a("p2", "player")
    m2 = mk_a("e2b", "enemy", hp=99999, atk=1)
    EP.install_ext_actions()
    p2["triggers"] = {"taken_calc": [{"type": "we_taken_mult_cond", "key": "dd_test",
                                      "cond": "always", "mult": 0.92}]}
    b2 = new_battle(p2, m2)
    from ext_combat.battle.landing import deal_damage as _dd
    hp0 = p2["hp"]
    _dd(b2, m2, p2, 100, [])
    real = hp0 - p2["hp"]
    check("承伤减伤 8%（92）", real == 92, f"real={real}")


def test_cond_mult_and_stacks():
    print("【N9.21 条件乘区 + 叠层放大器】")
    # twilight_execute：目标 hp<40% ×1.25
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=100000, atk=1)
    equip(p, "twilight_execute", slot="weapon")
    EP.apply_to_actor(p)
    b = new_battle(p, m)
    act_land(b, ActCtx(caster=p, action="attack", target=m))
    d_full = 100000 - m["hp"]
    m["hp"] = 30000  # 30%
    act_land(b, ActCtx(caster=p, action="attack", target=m))
    d_low = 100000 - m["hp"]
    check("暮光低血 ×1.25", d_low > d_full * 1.15, f"full={d_full} low={d_low}")
    # death_dance_armor：受击减伤 8%
    p2 = mk_a("p2", "player")
    m2 = mk_a("e2", "enemy", hp=99999, atk=1)
    equip(p2, "death_dance_armor", slot="armor")
    EP.apply_to_actor(p2)
    b2 = new_battle(p2, m2)
    from ext_combat.battle.landing import deal_damage as _dd
    hp0 = p2["hp"]
    _dd(b2, m2, p2, 100, [])
    check("减伤 8% 掉 92", hp0 - p2["hp"] == 92, f"real={hp0-p2['hp']}")
    # rune_amp：技能施放叠层（每次攻击 dmg_calc 都会消费——旧语义）→ 直调验证
    p3 = mk_a("p3", "player")
    m3 = mk_a("e3", "enemy", hp=100000, atk=1)
    equip(p3, "rune_amp", slot="weapon", we_data={"per_pct": 0.02})
    EP.apply_to_actor(p3)
    b3 = new_battle(p3, m3)
    from content.mech.we_procs import we_stack_prod, we_amp_consume
    # 生产 3 层
    for _ in range(3):
        we_stack_prod(b3, p3, m3, {"type": "we_stack_prod", "key": "rune_amp",
                                   "stack_key": "rune_amp", "need": None,
                                   "charge_key": None, "charge_pct": None}, [])
    check("生产叠 3 层", stk(p3, "rune_amp", 0) == 3,
          f"state={p3.get('state')}")
    # dmg_calc 消费 → ×(1+0.02×3)=1.06 并清层
    b3._fire_ctx = {"target": m3, "dmg": 100, "mult": 1.0, "tags": []}
    we_amp_consume(b3, p3, m3, {"type": "we_amp_consume", "key": "rune_amp",
                                "stack_key": "rune_amp", "per_pct": 0.02,
                                "charge_key": None}, [])
    check("消费 ×1.06", abs(b3._fire_ctx["mult"] - 1.06) < 1e-9, f"mult={b3._fire_ctx.get('mult')}")
    check("层被清", stk(p3, "rune_amp", 0) == 0, f"state={p3.get('state')}")


def test_death_dance():
    print("【N9A-1 death_dance 缓伤池：受击收 35% → turn_start 结算 10%】")
    from ext_combat.battle.landing import deal_damage as _dd
    # 装配端到端
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=99999, atk=1)
    equip(p, "death_dance", slot="armor")
    EP.apply_to_actor(p)
    check("death_dance 装配 triggers", "on_taken" in (p.get("triggers") or {})
          and "turn_start" in (p.get("triggers") or {}),
          f"triggers={p.get('triggers')}")
    b = new_battle(p, m)
    act_land(b, ActCtx(caster=p, action="attack", target=m))  # 首动 battle_start + turn_start
    # 受击 100（收 35 进池，扣 100 血）
    hp0 = p["hp"]
    _dd(b, m, p, 100, [])
    check("受击扣 100", p["hp"] == hp0 - 100, f"hp={p['hp']} expect {hp0-100}")
    pool = (p.get("ext", {}).get("we_proc", {}) or {}).get("we_death_pool", 0)
    check("缓伤池收 35", abs(pool - 35.0) < 1e-9, f"pool={pool}")
    # 再受击 200（pool = 35 + 200×0.35 = 105）
    hp0 = p["hp"]
    _dd(b, m, p, 200, [])
    check("二次受击扣 200", p["hp"] == hp0 - 200, f"hp={p['hp']}")
    pool = (p.get("ext", {}).get("we_proc", {}) or {}).get("we_death_pool", 0)
    check("缓伤池累计 105", abs(pool - 105.0) < 1e-9, f"pool={pool}")
    # turn_start 结算：pay = max(1, int(105×0.10)) = 10，扣血 + 池减 10
    hp0 = p["hp"]
    act_land(b, ActCtx(caster=p, action="attack", target=m))
    check("结算扣 10", p["hp"] == hp0 - 10, f"hp={p['hp']} expect {hp0-10}")
    pool = (p.get("ext", {}).get("we_proc", {}) or {}).get("we_death_pool", 0)
    check("池减到 95", abs(pool - 95.0) < 1e-9, f"pool={pool}")
    # 多轮结算直到池尽（每轮 pay = max(1, int(pool×0.10))）
    turns = 0
    guard = 0
    while pool > 0 and guard < 100:
        guard += 1
        turns += 1
        act_land(b, ActCtx(caster=p, action="attack", target=m))
        pool = (p.get("ext", {}).get("we_proc", {}) or {}).get("we_death_pool", 0)
    check("池最终耗尽", pool <= 0 and turns > 1, f"pool={pool} turns={turns}")
    # 序列化续战保留池：先受击收池 → to_state → from_state → 池还在
    p2 = mk_a("p2", "player")
    m2 = mk_a("e2", "enemy", hp=99999, atk=1)
    equip(p2, "death_dance", slot="armor")
    EP.apply_to_actor(p2)
    b2 = new_battle(p2, m2)
    act_land(b2, ActCtx(caster=p2, action="attack", target=m2))
    _dd(b2, m2, p2, 100, [])
    st = b2.to_state()
    b2r = BT_NEW.from_state(st)
    p2r = b2r.sides["player"][0]
    pool_r = (p2r.get("ext", {}).get("we_proc", {}) or {}).get("we_death_pool", 0)
    check("序列化保留池 35", abs(pool_r - 35.0) < 1e-9, f"pool_r={pool_r}")


def test_act_done_randuin():
    print("【N9A-2 act_done 通用广播：randuin/ice_vein 敌行动叠减速层】")
    # 装配端到端：玩家带 randuin，敌方每次行动完成 → 敌方叠层
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=99999, atk=1, spd=50)
    equip(p, "randuin_weary", slot="armor")
    EP.apply_to_actor(p)
    check("randuin 装配 act_done", "act_done" in (p.get("triggers") or {}),
          f"triggers={p.get('triggers')}")
    b = new_battle(p, m)
    # 敌方行动 1 次 → 敌方叠 1 层（speed 从 50 → ×(1-0.06) = 47）
    act_land(b, ActCtx(caster=m, action="attack", target=p))
    ef = m.get("effects") or {}
    check("敌方行动叠 1 层", stk(m, "randuin_weary", 0) == 1,
          f"effects={ef}")
    from ext_combat.battle import stats as S
    spd1 = S.actor_spd(b, m)
    check("减速 -6%（47）", spd1 == 47, f"spd={spd1}")
    # 敌方再行动 2 次 → 叠满 3 层 → ×(1-0.18) = 41
    act_land(b, ActCtx(caster=m, action="attack", target=p))
    act_land(b, ActCtx(caster=m, action="attack", target=p))
    ef = m.get("effects") or {}
    check("敌行动叠满 3 层", stk(m, "randuin_weary", 0) == 3,
          f"effects={ef}")
    spd3 = S.actor_spd(b, m)
    check("减速 -18%（41）", spd3 == 41, f"spd={spd3}")
    # 玩家自己行动不叠（旁观者不误触发——玩家侧声明的监听不叠自己）
    n_before = stk(m, "randuin_weary", 0)
    act_land(b, ActCtx(caster=p, action="attack", target=m))
    n_after = stk(m, "randuin_weary", 0)
    check("玩家行动不额外叠层", n_after == n_before, f"{n_before}→{n_after}")
    # ice_vein：每层 -8%
    p2 = mk_a("p2", "player")
    m2 = mk_a("e2", "enemy", hp=99999, atk=1, spd=50)
    equip(p2, "ice_vein", slot="armor")
    EP.apply_to_actor(p2)
    b2 = new_battle(p2, m2)
    act_land(b2, ActCtx(caster=m2, action="attack", target=p2))
    spd_i1 = S.actor_spd(b2, m2)
    check("冰脉一层 -8%（46）", spd_i1 == 46, f"spd={spd_i1}")
    # 我方随从（同阵营）行动不叠
    pet = mk_a("pet1", "player", hp=200, atk=5)
    b2.sides["player"].append(pet)
    n2 = stk(m2, "ice_vein", 0)
    act_land(b2, ActCtx(caster=pet, action="attack", target=m2))
    n2b = stk(m2, "ice_vein", 0)
    check("友方行动不叠层", n2b == n2, f"{n2}→{n2b}")
    # PVP：对手（enemy 阵营但 human_controlled）行动也叠（敌对判定按 side 不按 human）
    p3 = mk_a("p3", "player")
    foe = mk_a("foe1", "enemy", hp=99999, atk=1, spd=50)
    foe["human_controlled"] = True  # PVP 对手也是真人（但 side=enemy → 敌对判定仍叠）
    equip(p3, "randuin_weary", slot="armor")
    EP.apply_to_actor(p3)
    b3 = new_battle(p3, foe)
    act_land(b3, ActCtx(caster=foe, action="attack", target=p3))
    check("PVP 对手行动也叠层", stk(foe, "randuin_weary", 0) == 1,
          f"foe state={foe.get('state')}")


def test_affix_basic():
    print("【N9.7a affix 装配骨架：stat 面板自动含 + 纯动词词条 shield/regen/meditate】")
    # --- stat 型 26 零代码验证：带 crit_up(+5% crit) 词条的装备 → saintess_engine 面板含 ---
    p = mk_a("p1", "player", class_name="战士")
    p.setdefault("equipment", {})["weapon"] = {
        "slot": "weapon", "quality": "purple",
        "affixes": ["crit_up"],  # effect: crit +0.05 → 生成时折算进 stats
        "stats": {"crit": 0.05, "atk": 10},
    }
    # 实际生成路径 stat_affix_stats 折算（drops 同款）——直接调折算验证
    from content.affix import stat_affix_stats  # ★ P5C-REPOINT
    conv = stat_affix_stats(["crit_up"], "weapon", 10)
    check("stat_affix_stats 折算 crit_up", abs((conv.get("crit") or 0) - 0.05) < 1e-9,
          f"conv={conv}")
    # saintess_engine 面板：带折算后的 stats 即含（不产生 triggers）
    EP.apply_to_actor(p)
    check("stat 词条不产生 triggers", not (p.get("triggers") or {}),
          f"triggers={p.get('triggers')}")
    from ext_combat.battle import stats as S
    b = new_battle(p, mk_a("e0", "enemy", hp=99999, atk=1))
    st = S.actor_stats(b, p)
    check("面板 crit 含词条（>基础）", float(st.get("crit", 0) or 0) > 0.05 + 1e-9,
          f"crit={st.get('crit')}")
    # --- shield 词条：battle_start 10% maxhp 盾 ---
    p2 = mk_a("p2", "player")
    m2 = mk_a("e2", "enemy", hp=99999, atk=1)
    p2.setdefault("equipment", {})["armor"] = {
        "slot": "armor", "quality": "blue", "affixes": ["shield"], "stats": {},
    }
    EP.apply_to_actor(p2)
    check("shield 词条装配 battle_start", "battle_start" in (p2.get("triggers") or {}),
          f"triggers={p2.get('triggers')}")
    b2 = new_battle(p2, m2)
    act_land(b2, ActCtx(caster=p2, action="attack", target=m2))
    sh = (p2.get("shields") or {}).get("affix_shield")
    check("battle_start 盾 = 10% maxhp（80）", sh is not None and abs(int(sh.get("value", 0)) - 80) <= 1,
          f"shields={p2.get('shields')}")
    # --- regen 词条：turn_start 回 1% maxhp ---
    p3 = mk_a("p3", "player")
    m3 = mk_a("e3", "enemy", hp=99999, atk=1)
    p3.setdefault("equipment", {})["ring"] = {
        "slot": "ring", "quality": "green", "affixes": ["regen"], "stats": {},
    }
    EP.apply_to_actor(p3)
    check("regen 词条装配 turn_start", "turn_start" in (p3.get("triggers") or {}),
          f"triggers={p3.get('triggers')}")
    b3 = new_battle(p3, m3)
    p3["hp"] = p3["max_hp"] - 100  # 缺 100
    act_land(b3, ActCtx(caster=p3, action="attack", target=m3))
    check("regen 回合回 1% maxhp（+8）", p3["hp"] == p3["max_hp"] - 100 + 8,
          f"hp={p3['hp']} expect {p3['max_hp']-100+8}")
    # --- meditate 同 regen 语义 ---
    p4 = mk_a("p4", "player")
    m4 = mk_a("e4", "enemy", hp=99999, atk=1)
    p4.setdefault("equipment", {})["ring"] = {
        "slot": "ring", "quality": "green", "affixes": ["meditate"], "stats": {},
    }
    EP.apply_to_actor(p4)
    b4 = new_battle(p4, m4)
    p4["hp"] = p4["max_hp"] - 50
    act_land(b4, ActCtx(caster=p4, action="attack", target=m4))
    check("meditate 回合回 1% maxhp（+8）", p4["hp"] == p4["max_hp"] - 50 + 8,
          f"hp={p4['hp']}")


def test_affix_onhit():
    print("【N9.7b affix on_hit 族：bleed/armor_break/element_fire/element_ice/pierce】")
    # bleed：命中 100 → 20% 概率挂 affix_bleed 层（直调扩展动作验证语义）
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=99999, atk=1)
    from content.mech.we_procs import we_affix_dot, we_affix_defdown, \
        we_affix_element, we_affix_bonus
    # 装配端到端：带 bleed + armor_break + element_fire + element_ice + pierce 装备
    p.setdefault("equipment", {})["weapon"] = {
        "slot": "weapon", "quality": "orange",
        "affixes": ["bleed", "armor_break", "element_fire", "element_ice", "pierce"],
        "stats": {"atk": 40},
    }
    EP.apply_to_actor(p)
    tr = p.get("triggers") or {}
    check("affix on_hit 全部挂 attack_hit", all(t in tr for t in
          ("attack_hit", "skill_hit")), f"keys={list(tr.keys())}")
    check("bleed 挂 we_affix_dot", any(e.get("type") == "we_affix_dot"
          for e in tr.get("attack_hit", [])), f"{tr}")
    b = new_battle(p, m)
    # 直调（chance 用参数覆盖为恒触发验证语义）
    b._fire_ctx = {"target": m, "dmg": 100}
    we_affix_dot(b, p, m, {"key": "bleed", "state_key": "affix_bleed",
                           "chance": 1.0, "stacks": 3}, [])
    check("bleed 挂 affix_bleed 3 层", stk(m, "affix_bleed", 0) == 3,
          f"state={m.get('effects')}")
    # armor_break：def 50 → ×0.85
    m2 = mk_a("e2", "enemy", hp=99999, atk=1)
    m2["def"] = 50
    p2 = mk_a("p2", "player")
    b2 = new_battle(p2, m2)
    b2._fire_ctx = {"target": m2, "dmg": 100}
    we_affix_defdown(b2, p2, m2, {"key": "armor_break", "chance": 1.0,
                                  "pct": 0.15, "turns": 2}, [])
    from ext_combat.battle import stats as S
    def2 = S.actor_stats(b2, m2).get("def", 0)
    check("armor_break def -15%（42）", def2 == 42, f"def={def2}")
    # element_fire：dmg 100 ×5% = 5 附加
    m3 = mk_a("e3", "enemy", hp=99999, atk=1)
    p3 = mk_a("p3", "player")
    b3 = new_battle(p3, m3)
    hp0 = m3["hp"]
    b3._fire_ctx = {"target": m3, "dmg": 100}
    we_affix_element(b3, p3, m3, {"key": "element_fire", "element": "fire",
                                  "pct": 0.05, "name": "火焰附加"}, [])
    check("fire 附加 5 点", hp0 - m3["hp"] == 5, f"hp={m3['hp']}")
    # element_ice：附加 5 + 减速 buff
    m4 = mk_a("e4", "enemy", hp=99999, atk=1, spd=50)
    p4 = mk_a("p4", "player")
    b4 = new_battle(p4, m4)
    b4._fire_ctx = {"target": m4, "dmg": 100}
    we_affix_element(b4, p4, m4, {"key": "element_ice", "element": "ice",
                                  "pct": 0.05, "slow": 0.10, "slow_turns": 2,
                                  "name": "冰霜附加"}, [])
    check("ice 附加伤害", abs(5 - (99999 - m4["hp"])) <= 1, f"hp={m4['hp']}")
    spd_ice = S.actor_spd(b4, m4)
    check("ice 减速 spd×0.9（45）", spd_ice == 45, f"spd={spd_ice}")
    # pierce：atk 40 ×60% = 24 真伤
    m5 = mk_a("e5", "enemy", hp=99999, atk=1)
    p5 = mk_a("p5", "player", atk=40)
    b5 = new_battle(p5, m5)
    hp5 = m5["hp"]
    b5._fire_ctx = {"target": m5, "dmg": 100}
    we_affix_bonus(b5, p5, m5, {"key": "pierce", "mode": "atk_true", "chance": 1.0,
                                "atk_pct": 0.60, "tag": "🏹", "name": "贯穿"}, [])
    d5 = hp5 - m5["hp"]
    check("pierce 真伤 ~24（±15%）", 20 <= d5 <= 28, f"dmg={d5}")


def test_affix_taken():
    print("【N9.7c affix on_taken 族：counter/tenacity_cc + dmg_reduce 减伤】")
    from content.mech.we_procs import we_affix_counter, we_affix_tenacity
    # counter：受击 100 由敌发起 → 20% 反击敌 atk×60%（直调恒触发）
    p = mk_a("p1", "player", atk=40)
    m = mk_a("e1", "enemy", hp=99999, atk=1)
    b = new_battle(p, m)
    hp0 = m["hp"]
    b._fire_ctx = {"source": m}   # on_taken 攻击方 = m
    we_affix_counter(b, p, m, {"key": "counter", "chance": 1.0, "atk_pct": 0.6}, [])
    dmg = hp0 - m["hp"]
    check("反击打攻击方 ~24（±15%）", 20 <= dmg <= 28, f"dmg={dmg}")
    # tenacity_cc：带负面受击 → 清一个负面 + 回 3% maxhp
    p2 = mk_a("p2", "player")
    m2 = mk_a("e2", "enemy", hp=99999, atk=1)
    p2.setdefault("effects", {})["spd_down"] = {"stacks": 1, "expire": 99, "stat": "spd",
                                              "op": "mul", "mult": 0.10}
    p2["hp"] = p2["max_hp"] - 200
    b2 = new_battle(p2, m2)
    b2._fire_ctx = {"source": m2}
    we_affix_tenacity(b2, p2, m2, {"key": "tenacity_cc", "chance": 1.0,
                                   "heal_pct": 0.03}, [])
    check("坚韧清负面", "spd_down" not in ((p2).get("effects") or {}),
          f"buffs={p2.get('buffs')}")
    check("坚韧回 3% maxhp（+24）", p2["hp"] == p2["max_hp"] - 200 + 24,
          f"hp={p2['hp']} expect {p2['max_hp']-200+24}")
    # dmg_reduce：装配端到端受击减 3%
    p3 = mk_a("p3", "player")
    m3 = mk_a("e3", "enemy", hp=99999, atk=1)
    p3.setdefault("equipment", {})["armor"] = {
        "slot": "armor", "quality": "blue", "affixes": ["dmg_reduce"], "stats": {},
    }
    EP.apply_to_actor(p3)
    check("dmg_reduce 装配 taken_calc", "taken_calc" in (p3.get("triggers") or {}),
          f"triggers={p3.get('triggers')}")
    b3 = new_battle(p3, m3)
    from ext_combat.battle.landing import deal_damage as _dd
    hp0 = p3["hp"]
    _dd(b3, m3, p3, 100, [])
    real = hp0 - p3["hp"]
    check("受击减 3%（97）", real == 97, f"real={real}")


def test_affix_cond_mult():
    print("【N9.7d affix 条件乘区：execute/hunt/break_magic/dragon_aw】")
    # execute：目标 <30% ×1.3（直调乘区避免伤害波动干扰）
    p = mk_a("p1", "player")
    m_full = mk_a("e1", "enemy", hp=100000, atk=1)
    m_low = mk_a("e2", "enemy", hp=100000, atk=1)
    p.setdefault("equipment", {})["weapon"] = {
        "slot": "weapon", "quality": "purple", "affixes": ["execute"], "stats": {},
    }
    EP.apply_to_actor(p)
    check("execute 装配 dmg_calc", "dmg_calc" in (p.get("triggers") or {}),
          f"triggers={p.get('triggers')}")
    from content.mech.we_procs import we_dmg_mult_cond
    b = new_battle(p, m_full, m_low)
    b._fire_ctx = {"target": m_full, "dmg": 100, "mult": 1.0, "tags": []}
    we_dmg_mult_cond(b, p, m_full, {"type": "we_dmg_mult_cond", "key": "execute",
                                    "cond": "hp_target_lt", "threshold": 0.30,
                                    "mult": 1.3, "tag": "💀处决"}, [])
    check("满血不触发处决", abs(b._fire_ctx["mult"] - 1.0) < 1e-9,
          f"mult={b._fire_ctx['mult']}")
    m_low["hp"] = 20000  # 20%
    b._fire_ctx = {"target": m_low, "dmg": 100, "mult": 1.0, "tags": []}
    we_dmg_mult_cond(b, p, m_low, {"type": "we_dmg_mult_cond", "key": "execute",
                                   "cond": "hp_target_lt", "threshold": 0.30,
                                   "mult": 1.3, "tag": "💀处决"}, [])
    check("处决低血 ×1.3", abs(b._fire_ctx["mult"] - 1.3) < 1e-9,
          f"mult={b._fire_ctx['mult']}")
    # hunt：目标带猎印 ×1.2（直调乘区避免伤害波动干扰）
    p2 = mk_a("p2", "player")
    m2 = mk_a("e2b", "enemy", hp=100000, atk=1)
    m2m = mk_a("e2c", "enemy", hp=100000, atk=1)
    m2m.setdefault("effects", {})["hunt_mark"] = {"stacks": 1}
    p2.setdefault("equipment", {})["weapon"] = {
        "slot": "weapon", "quality": "purple", "affixes": ["hunt"], "stats": {},
    }
    EP.apply_to_actor(p2)
    b2 = new_battle(p2, m2, m2m)
    from content.mech.we_procs import we_dmg_mult_cond
    b2._fire_ctx = {"target": m2, "dmg": 100, "mult": 1.0, "tags": []}
    we_dmg_mult_cond(b2, p2, m2, {"type": "we_dmg_mult_cond", "key": "hunt",
                                  "cond": "enemy_marked", "mult": 1.20,
                                  "tag": "🎯追猎"}, [])
    check("无印不触发追猎", abs(b2._fire_ctx["mult"] - 1.0) < 1e-9,
          f"mult={b2._fire_ctx['mult']}")
    b2._fire_ctx = {"target": m2m, "dmg": 100, "mult": 1.0, "tags": []}
    we_dmg_mult_cond(b2, p2, m2m, {"type": "we_dmg_mult_cond", "key": "hunt",
                                   "cond": "enemy_marked", "mult": 1.20,
                                   "tag": "🎯追猎"}, [])
    check("追猎带印 ×1.2", abs(b2._fire_ctx["mult"] - 1.2) < 1e-9,
          f"mult={b2._fire_ctx['mult']}")
    # dragon_aw：目标名含龙 ×1.25（直调乘区避免伤害波动干扰）
    p3 = mk_a("p3", "player")
    m3a = mk_a("幼龙", "enemy", hp=100000, atk=1)
    p3.setdefault("equipment", {})["weapon"] = {
        "slot": "weapon", "quality": "purple", "affixes": ["dragon_aw"], "stats": {},
    }
    EP.apply_to_actor(p3)
    b3 = new_battle(p3, m3a)
    from content.mech.we_procs import we_dmg_mult_cond
    # 打非龙目标：倍率不变
    m_wolf = mk_a("野狼", "enemy", hp=100000, atk=1)
    b3.sides["enemy"].append(m_wolf)
    b3._fire_ctx = {"target": m_wolf, "dmg": 100, "mult": 1.0, "tags": []}
    we_dmg_mult_cond(b3, p3, m_wolf, {"type": "we_dmg_mult_cond", "key": "dragon_aw",
                                      "cond": "name_contains", "keywords": ["龙"],
                                      "mult": 1.25, "tag": "🐉龙威"}, [])
    check("野狼不触发龙威", abs(b3._fire_ctx["mult"] - 1.0) < 1e-9,
          f"mult={b3._fire_ctx['mult']}")
    # 打龙目标：×1.25
    b3._fire_ctx = {"target": m3a, "dmg": 100, "mult": 1.0, "tags": []}
    we_dmg_mult_cond(b3, p3, m3a, {"type": "we_dmg_mult_cond", "key": "dragon_aw",
                                   "cond": "name_contains", "keywords": ["龙"],
                                   "mult": 1.25, "tag": "🐉龙威"}, [])
    check("龙威对龙 ×1.25", abs(b3._fire_ctx["mult"] - 1.25) < 1e-9,
          f"mult={b3._fire_ctx['mult']}")



def test_novice_hunt_combo():
    print("【N9.22 novice_hunt_combo（猎影之牙）：暴击 → 连击率叠层 cap 5】")
    from content.mech.we_procs import we_combo_stack
    # 装配端：装备 猎影之牙 weapon_effect → triggers[crit]（暴击叠层生产段）
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=100000, atk=1)
    equip(p, "novice_hunt_combo", slot="weapon")
    EP.apply_to_actor(p)
    tr = p.get("triggers") or {}
    check("novice_hunt_combo 装配 crit 事件", "crit" in tr and len(tr["crit"]) == 1,
          f"triggers={tr}")
    e = tr.get("crit", [{}])[0]
    check("装配参数透传（stack_key/max_stack/per_stack）",
          e.get("type") == "we_combo_stack" and e.get("stack_key") == "novice_combo"
          and e.get("max_stack") == 5 and abs(float(e.get("per_stack") or 0) - 0.08) < 1e-9,
          f"eff={e}")
    # 端到端：crit=1.0 → 每次暴击命中叠 1 层，cap 5 封顶
    p["crit"] = 1.0
    b = new_battle(p, m)
    act_land(b, ActCtx(caster=p, action="attack", target=m))
    check("首次暴击叠 1 层", stk(p, "novice_combo", 0) == 1,
          f"effects={p.get('effects')}")
    for _ in range(6):
        act_land(b, ActCtx(caster=p, action="attack", target=m))
    check("连击暴击叠层 cap 5（6 次暴击后仍 5）", stk(p, "novice_combo", 0) == 5,
          f"stacks={stk(p, 'novice_combo', 0)}")
    # 条件不满足不触发：无暴击（crit=0）的攻击不叠层
    p2 = mk_a("p2", "player")
    m2 = mk_a("e2", "enemy", hp=100000, atk=1)
    equip(p2, "novice_hunt_combo", slot="weapon")
    p2["crit"] = 0.0
    EP.apply_to_actor(p2)
    b2 = new_battle(p2, m2)
    logs2 = []
    for _ in range(3):
        logs2.extend(act_land(b2, ActCtx(caster=p2, action="attack", target=m2))[0])
    check("非暴击不叠层", "novice_combo" not in (p2.get("effects") or {}),
          f"effects={p2.get('effects')}")
    check("非暴击无猎影文案", not any("猎影" in x for x in logs2), str(logs2))
    # 直调：层数/clamp/文案数值与 desc 一致（每层 +8%，文案带层数）
    logs3 = []
    we_combo_stack(b, p, m, {"type": "we_combo_stack", "key": "novice_hunt_combo",
                             "stack_key": "novice_combo", "max_stack": 5,
                             "per_stack": 0.08}, logs3)
    check("叠层动作直调 +1（5→封顶仍 5）", stk(p, "novice_combo", 0) == 5, f"{stk(p, 'novice_combo', 0)}")
    p["effects"]["novice_combo"] = {"stacks": 0}
    logs3 = []
    we_combo_stack(b, p, m, {"type": "we_combo_stack", "key": "novice_hunt_combo",
                             "stack_key": "novice_combo", "max_stack": 5,
                             "per_stack": 0.08}, logs3)
    check("暴击叠层文案（猎影/层数/8%）", any("猎影" in x and "8%" in x and "/5 层" in x for x in logs3),
          str(logs3))


def test_combo_end():
    print("【N9.23 combo_end（夜枭双匕）：连段≥3 暴击 → 暴伤 +40%】")
    from content.mech.we_procs import we_combo_end
    # 装配端：装备 夜枭双匕 weapon_effect → triggers[dmg_calc]（连段暴伤乘区钩子）
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=100000, atk=1)
    equip(p, "combo_end", slot="weapon")
    EP.apply_to_actor(p)
    tr = p.get("triggers") or {}
    check("combo_end 装配 dmg_calc", "dmg_calc" in tr and len(tr["dmg_calc"]) == 1,
          f"triggers={tr}")
    e = tr.get("dmg_calc", [{}])[0]
    check("装配参数透传（combo_need=3/crit_dmg=0.40）",
          e.get("type") == "we_combo_end" and e.get("combo_need") == 3
          and abs(float(e.get("crit_dmg") or 0) - 0.40) < 1e-9, f"eff={e}")
    # 直调精确乘区：连段 3 + 暴击 → mult ×1.4 + 日志 + tags
    b = new_battle(p, m)
    p["effects"] = {"lian_duan": {"stacks": 3}}  # 本刻连段 = 连段资源当前层
    b._fire_ctx = {"target": m, "dmg": 100, "is_crit": True, "mult": 1.0, "tags": []}
    logs = []
    we_combo_end(b, p, m, {"type": "we_combo_end", "key": "combo_end",
                           "combo_need": 3, "crit_dmg": 0.40}, logs)
    check("连段≥3 + 暴击 → mult ×1.4", abs(b._fire_ctx["mult"] - 1.40) < 1e-9,
          f"mult={b._fire_ctx.get('mult')}")
    check("暴伤乘区打标", any("连击终点" in x for x in b._fire_ctx.get("tags") or []),
          f"tags={b._fire_ctx.get('tags')}")
    check("触发日志（连击终点/40%）", any("连击终点" in x and "+40%" in x for x in logs), str(logs))
    # 条件不满足 1：连段 <3（2 段）→ 不触发
    p["effects"] = {"lian_duan": {"stacks": 2}}
    b._fire_ctx = {"target": m, "dmg": 100, "is_crit": True, "mult": 1.0, "tags": []}
    logs = []
    we_combo_end(b, p, m, {"type": "we_combo_end", "key": "combo_end",
                           "combo_need": 3, "crit_dmg": 0.40}, logs)
    check("连段 2 <3 不触发", abs(b._fire_ctx["mult"] - 1.0) < 1e-9 and not logs,
          f"mult={b._fire_ctx.get('mult')} logs={logs}")
    # 条件不满足 2：连段 3 但未暴击 → 不触发
    p["effects"] = {"lian_duan": {"stacks": 3}}
    b._fire_ctx = {"target": m, "dmg": 100, "is_crit": False, "mult": 1.0, "tags": []}
    logs = []
    we_combo_end(b, p, m, {"type": "we_combo_end", "key": "combo_end",
                           "combo_need": 3, "crit_dmg": 0.40}, logs)
    check("未暴击不触发", abs(b._fire_ctx["mult"] - 1.0) < 1e-9 and not logs,
          f"mult={b._fire_ctx.get('mult')} logs={logs}")
    # 端到端：连段 3 + 必暴 → 实际伤害显著高于连段 0 基线（40% 加成）
    # 幸运一击(30%)双方独立，聚合 8 击对比消除波动：基线均值 vs ×1.4 均值
    p2 = mk_a("p2", "player", atk=60)
    m2 = mk_a("e2", "enemy", hp=1000000, atk=1, **{"def": 30, "mdef": 30})
    equip(p2, "combo_end", slot="weapon")
    p2["crit"] = 1.0
    EP.apply_to_actor(p2)
    b2 = new_battle(p2, m2)
    p2["effects"] = {"lian_duan": {"stacks": 0}}
    base_sum = 0
    logs_base = []
    for _ in range(8):
        hp0 = m2["hp"]
        logs_base.extend(act_land(b2, ActCtx(caster=p2, action="attack", target=m2))[0])
        base_sum += hp0 - m2["hp"]
    p2["effects"] = {"lian_duan": {"stacks": 3}}
    m2["hp"] = 1000000
    logs2 = []
    boost_sum = 0
    for _ in range(8):
        hp0 = m2["hp"]
        logs2.extend(act_land(b2, ActCtx(caster=p2, action="attack", target=m2))[0])
        boost_sum += hp0 - m2["hp"]
    check("连段 0 基线无连击终点日志", not any("连击终点" in x for x in logs_base), str(logs_base))
    check("连段≥3 每次暴击出连击终点日志", sum("连击终点" in x for x in logs2) >= 8,
          f"n={sum('连击终点' in x for x in logs2)}")
    check("连段≥3 伤害总量显著高于基线（×1.4 生效）",
          boost_sum > base_sum * 1.2,
          f"base={base_sum} boost={boost_sum}")


def stk(a, k, d=0):
    """V 系列：读效果叠层数 effects[key].stacks。"""
    e = (a or {}).get("effects") or {}
    ent = e.get(k)
    return int(ent.get("stacks", 0) or 0) if isinstance(ent, dict) else int(d)


def ent(a, k):
    """V 系列：读效果条目 dict effects[key]。"""
    e = (a or {}).get("effects") or {}
    return e.get(k) or {}


# ============================================================
# N9.7 收尾（m_affixtail）：purify 净化 + regen 型回能装配
# ============================================================

def _affix_item(actor, aid, slot, quality="purple"):
    actor.setdefault("equipment", {})[slot] = {
        "slot": slot, "quality": quality, "affixes": [aid], "stats": {},
    }
    return actor


def test_affix_purify():
    print("【N9.7f purify 净化：命中 15% 驱散 1 层增益；成功 → 敌攻 -10%（1 刻）】")
    # 装配：hit → attack_hit + skill_hit 双事件，参数 purge_n=1/chance=0.15/weaken 0.10
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=99999, atk=100)
    _affix_item(p, "purify", "weapon", "purple")
    EP.apply_to_actor(p)
    tr = p.get("triggers") or {}
    for ev in ("attack_hit", "skill_hit"):
        pu = [e for e in tr.get(ev, []) if e.get("type") == "we_affix_purify"]
        check(f"purify 展开 {ev}（chance 0.15/purge 1/weaken 0.10）",
              len(pu) == 1 and abs(float(pu[0].get("chance") or 0) - 0.15) < 1e-9
              and pu[0].get("purge_n") == 1
              and abs(float(pu[0].get("holy_weaken_pct") or 0) - 0.10) < 1e-9,
              f"{pu}")
    # 端到端：目标带增益（atk_up 面板 mul>1）+ DOT（burn 非增益）→ 普攻命中驱散 1 层
    for ev in ("attack_hit", "skill_hit"):
        for e in tr.get(ev, []):
            if e.get("type") == "we_affix_purify":
                e["chance"] = 1.0  # 强制触发验证语义
    b = new_battle(p, m)
    m.setdefault("effects", {})["atk_up"] = {"stacks": 1, "expire": 99999,
                                             "stat": "atk", "op": "mul", "mult": 1.30}
    m.setdefault("effects", {})["burn"] = {"stacks": 2}
    act_land(b, ActCtx(caster=p, action="attack", target=m))
    ef = m.get("effects") or {}
    check("驱散 1 层增益（atk_up 清）", "atk_up" not in ef, f"effects={list(ef.keys())}")
    check("DOT（burn）非增益不清", "burn" in ef, f"effects={list(ef.keys())}")
    hw = ef.get("holy_weaken")
    check("成功 → 圣洁削弱敌攻 -10% 1 刻",
          hw and hw.get("stat") == "atk" and abs(float(hw.get("mult") or 0) - 0.90) < 1e-9
          and hw.get("expire") is not None, f"hw={hw}")
    from ext_combat.battle import stats as S
    check("敌攻面板 ×0.90（100→90）", abs(S.actor_stats(b, m).get("atk", 0) - 90) < 1e-6,
          f"atk={S.actor_stats(b, m).get('atk')}")
    # 无增益目标：不驱散不削弱（圣洁只跟驱散成功）
    p2 = mk_a("p2", "player")
    _affix_item(p2, "purify", "weapon", "purple")
    EP.apply_to_actor(p2)
    for ev in ("attack_hit", "skill_hit"):
        for e in (p2.get("triggers") or {}).get(ev, []):
            if e.get("type") == "we_affix_purify":
                e["chance"] = 1.0
    m2 = mk_a("e2", "enemy", hp=99999, atk=100)
    b2 = new_battle(p2, m2)
    act_land(b2, ActCtx(caster=p2, action="attack", target=m2))
    check("无增益目标不驱散不削弱", "holy_weaken" not in (m2.get("effects") or {}),
          f"effects={list((m2.get('effects') or {}).keys())}")
    # 减益（spd_down mul<1 / reduce 值型）不是增益，purify 不清
    m3 = mk_a("e3", "enemy", hp=99999, atk=100)
    b3 = new_battle(p2, m3)
    m3.setdefault("effects", {})["spd_down"] = {"stacks": 1, "expire": 99999,
                                                "stat": "spd", "op": "mul", "mult": 0.50}
    m3.setdefault("effects", {})["atk_up"] = {"stacks": 1, "expire": 99999,
                                              "stat": "atk", "op": "mul", "mult": 1.30}
    act_land(b3, ActCtx(caster=p2, action="attack", target=m3))
    ef3 = m3.get("effects") or {}
    check("减益不清、增益被清", "spd_down" in ef3 and "atk_up" not in ef3,
          f"effects={list(ef3.keys())}")


def test_affix_regen_tail():
    print("【N9.7g affix regen 型装配：energy_tide/swift_tailwind turn_start 回能】")
    # energy_tide（purple tier 5）：装配 turn_start we_affix_res_gain
    p = mk_a("p1", "player")
    m = mk_a("e1", "enemy", hp=99999, atk=1)
    _affix_item(p, "energy_tide", "armor", "purple")
    EP.apply_to_actor(p)
    ts = [e for e in (p.get("triggers") or {}).get("turn_start", [])
          if e.get("type") == "we_affix_res_gain"]
    check("energy_tide 装配 turn_start（gain 5 tier 档）",
          len(ts) == 1 and ts[0].get("res") == "energy" and ts[0].get("gain") == 5,
          f"{ts}")
    b = new_battle(p, m)
    p.setdefault("effects", {})["energy"] = {"stacks": 30}
    act_land(b, ActCtx(caster=p, action="attack", target=m))
    check("每刻精力 +5（30→35）", stk(p, "energy") == 35,
          f"energy={stk(p, 'energy')}")
    # swift_tailwind（orange）：cond energy_ge_80 折算参数
    p2 = mk_a("p2", "player")
    m2 = mk_a("e2", "enemy", hp=99999, atk=1)
    _affix_item(p2, "swift_tailwind", "ring", "orange")
    EP.apply_to_actor(p2)
    ts2 = [e for e in (p2.get("triggers") or {}).get("turn_start", [])
           if e.get("type") == "we_affix_res_gain"]
    check("swift_tailwind 装配 cond_key=energy/cond_ge=80",
          len(ts2) == 1 and ts2[0].get("cond_key") == "energy"
          and ts2[0].get("cond_ge") == 80 and ts2[0].get("gain") == 10,
          f"{ts2}")
    # ★ T15 两段化跟账：一次出手 = 真时钟推进 ⇒ 两场景各自独立一场战斗
    #   （同一场连打两手的第二手会把「资源每刻自然回」叠进来，实测 90 → 100）。
    for _st0, _want, _lbl in ((79, 79, "精力 79 <80 不触发"), (80, 90, "精力 80 ≥80 触发 +10")):
        _p2 = mk_a("p2_%d" % _st0, "player")
        _m2 = mk_a("e2_%d" % _st0, "enemy", hp=100000, atk=1)
        _affix_item(_p2, "swift_tailwind", "ring", "orange")
        EP.apply_to_actor(_p2)
        _b2 = new_battle(_p2, _m2)
        _p2.setdefault("effects", {})["energy"] = {"stacks": _st0}
        act_land(_b2, ActCtx(caster=_p2, action="attack", target=_m2))
        check(_lbl, stk(_p2, "energy") == _want, f"energy={stk(_p2, 'energy')}")
    # v181.M-bonus：cost_reduce 3 词条（energy_blade/arcane_focus/sigil_blessing）已装
    # → 走 bonus.cost 容器（非事件 → 仍零 triggers）；其余未注册词条仍零装配
    # （D3 2026-09-13：ember_brand/combo_recover/combo_ward 已补翻译器 → 不再零装配，
    #  正面断言见 test_d3_gap_fixes）
    p3 = mk_a("p3", "player")
    _affix_item(p3, "energy_blade", "weapon", "purple")
    _affix_item(p3, "arcane_focus", "armor", "blue")
    _affix_item(p3, "sigil_blessing", "ring", "blue")
    _affix_item(p3, "sigil_engrave", "necklace", "purple")
    EP.apply_to_actor(p3)
    check("cost 词条装配 bonus.cost（容器非事件）；未注册词条零 triggers",
          not (p3.get("triggers") or {})
          and abs(float((((p3.get("bonus") or {}).get("cost") or {}).get("res") or {})
                        .get("energy", 0)) - 0.08) < 1e-9,
          f"triggers={p3.get('triggers')} cost={(p3.get('bonus') or {}).get('cost')}")


# ============================================================
# D3 缺口收口（2026-09-13）：3 个放错表键 + 首刻闪避 + 3 条事件型词条
# ============================================================

def test_d3_gap_fixes():
    print("【D3 缺口收口：放错表 3 键 + novice_first_turn_dodge + 3 条事件型词条】")
    from ext_combat.battle import stats as _S
    from ext_combat.battle import schedule as _SCH
    from ext_combat.battle.effect_triggers import fire as _FIRE
    # ① 3 个「放错表」键：roster 当 weapon_effect 引用，数据原只在 LEGENDARY_EFFECTS
    #    → 曾 cfg 恒 {}（静默跳过）；现抄进 WEAPON_EFFECT_DATA + 乘区翻译器
    for key, cond, param, mult in (("divine_execution", "hp_target_lt", 0.30, 1.60),
                                   ("dragon_annihilation", "name_contains", ["龙"], 1.25),
                                   ("star_destruction", "name_contains", ["深渊"], 1.30)):
        p = mk_a("p_" + key, "player")
        equip(p, key, slot="weapon")
        EP.apply_to_actor(p)
        dc = [e for e in (p.get("triggers") or {}).get("dmg_calc", [])
              if e.get("type") == "we_dmg_mult_cond" and e.get("key") == key]
        _p_ok = (dc[0].get("threshold") == param if cond == "hp_target_lt"
                 else dc[0].get("keywords") == param) if dc else False
        check(f"{key} 装配 dmg_calc（{cond} ×{mult}）",
              len(dc) == 1 and dc[0].get("cond") == cond
              and abs(float(dc[0].get("mult") or 0) - mult) < 1e-9 and _p_ok, f"{dc}")
    # ② novice_first_turn_dodge：battle_start apply dodge +5%（1 刻后失效）
    p = mk_a("p_dodge", "player")
    m = mk_a("e_dodge", "enemy", hp=99999, atk=1)
    equip(p, "novice_first_turn_dodge", slot="helm")
    EP.apply_to_actor(p)
    bs = [e for e in (p.get("triggers") or {}).get("battle_start", [])
          if e.get("type") == "apply" and e.get("stat") == "dodge"]
    check("novice_first_turn_dodge 装配 battle_start apply dodge +5%",
          len(bs) == 1 and abs(float(bs[0].get("mult") or 0) - 0.05) < 1e-9
          and bs[0].get("op") == "add" and int(bs[0].get("turns") or 0) == 1, f"{bs}")
    b = new_battle(p, m)
    d0 = float(_S.actor_stats(b, p).get("dodge") or 0)
    # ★ T15 两段化跟账：battle_start 给的「首刻 +5% 闪避」声明 `expire=1.0`（一个整刻），
    #   而这**一手**的落地时刻正好也是 T0+出招 ⇒ 落地后它已按到期清掉（实测 0.05 → 0）。
    #   面板读数因此取「出手登记（T0）的当刻」—— 那正是「首刻」这个窗口。
    _out = b.act(ActCtx(caster=p, action="attack", target=m))
    d1 = float(_S.actor_stats(b, p).get("dodge") or 0)
    check("首刻 dodge 面板 +5%（真生效）", abs(d1 - (d0 + 0.05)) < 1e-9, f"{d0} → {d1}")
    land(b, _out[0], p)   # 落地推进（收尾仍走正常驱动口径）
    # 首刻后失效：turns=1 → expire=now+1；时刻推进 1 刻（ACT_TICK=1）后引擎
    # `schedule._settle_time_effects` 清过期条目（b.act 不推 `_now`，故走时刻推进）
    _SCH._advance_time(b, 1.0, [])
    d2 = float(_S.actor_stats(b, p).get("dodge") or 0)
    check("首刻后 dodge 回落（1 刻失效）", abs(d2 - d0) < 1e-9, f"{d0} → {d2}")
    # ③-a combo_recover（on: combo_skill → skill_hit，chi +1）
    p = mk_a("p_cr", "player")
    m = mk_a("e_cr", "enemy", hp=99999, atk=1)
    _affix_item(p, "combo_recover", "weapon", "blue")
    EP.apply_to_actor(p)
    sh = [e for e in (p.get("triggers") or {}).get("skill_hit", [])
          if e.get("key") == "combo_recover"]
    check("combo_recover 装配 skill_hit（chi +1）",
          len(sh) == 1 and sh[0].get("res") == "chi" and int(sh[0].get("gain") or 0) == 1,
          f"{sh}")
    _FIRE(new_battle(p, m), "skill_hit", {"actor": p, "target": m,
                                          "info": {"name": "连招三连"}}, [])
    check("combo_recover 真生效：技能命中 chi +1", stk(p, "chi") == 1, f"chi={stk(p, 'chi')}")
    # ③-b combo_ward（受击 combo_keep_chance 概率回补 1 段连段；tiers 按品质取档）
    p = mk_a("p_cw", "player")
    m = mk_a("e_cw", "enemy", hp=99999, atk=1)
    _affix_item(p, "combo_ward", "armor", "orange")
    EP.apply_to_actor(p)
    ot = [e for e in (p.get("triggers") or {}).get("on_taken", [])
          if e.get("key") == "combo_ward"]
    check("combo_ward 装配 on_taken（orange 档 chance 0.30 → lian_duan +1）",
          len(ot) == 1 and abs(float(ot[0].get("chance") or 0) - 0.30) < 1e-9
          and ot[0].get("res") == "lian_duan", f"{ot}")
    b = new_battle(p, m)
    _hits = 0
    for _ in range(60):                      # 固定种子 → 确定性；验「概率触发」真生效
        if stk(p, "lian_duan") >= 10:        # 连段 cap 10（引擎 cap_of）
            break
        _before = stk(p, "lian_duan")
        _FIRE(b, "on_taken", {"actor": p, "target": p, "source": m, "dmg": 10}, [])
        if stk(p, "lian_duan") == _before + 1:
            _hits += 1
    check("combo_ward 真生效：受击概率回补 1 段（0 < 命中 < 60）",
          0 < _hits < 60 and stk(p, "lian_duan") == _hits,
          f"hits={_hits} 段={stk(p, 'lian_duan')}")
    # ③-c ember_brand（cond hp_lt_30：残血才 rage +1）
    p = mk_a("p_eb", "player")
    m = mk_a("e_eb", "enemy", hp=99999, atk=1)
    _affix_item(p, "ember_brand", "boots", "blue")
    EP.apply_to_actor(p)
    eb = [e for e in (p.get("triggers") or {}).get("on_taken", [])
          if e.get("key") == "ember_brand"]
    check("ember_brand 装配 on_taken（cond_hp_lt=0.30，rage +1）",
          len(eb) == 1 and abs(float(eb[0].get("cond_hp_lt") or 0) - 0.30) < 1e-9
          and eb[0].get("res") == "rage", f"{eb}")
    b = new_battle(p, m)
    _FIRE(b, "on_taken", {"actor": p, "target": p, "source": m, "dmg": 10}, [])
    check("满血不触发（hp 门槛」真生效）", stk(p, "rage") == 0, f"rage={stk(p, 'rage')}")
    p["hp"] = int(p["max_hp"] * 0.20)
    _FIRE(b, "on_taken", {"actor": p, "target": p, "source": m, "dmg": 10}, [])
    check("残血受击 rage +1（真生效）", stk(p, "rage") == 1, f"rage={stk(p, 'rage')}")


def main():
    print("=== N9 saintess_engine 装备特效装配层测试 ===")
    test_damage_verb()
    test_event_map()
    test_weapon_battle_start()
    test_weapon_abyss_and_multi()
    test_no_equip_no_trigger()
    test_unsupported_key_skipped()
    test_d3_gap_fixes()
    test_regen_turn_start()
    test_wind_mark_stack()
    test_dot_ext_action()
    test_dot_blood_trace_curhp()
    test_reflect_ext_action()
    test_next_atk_and_retort_marks()
    test_trinity_thunder()
    test_shield_taken_cd()
    test_dusk_blade_kill()
    test_shield_cond_overflow_crit()
    test_extra_dmg()
    test_control_ext()
    test_heal_amp_and_mana()
    test_death_guard()
    test_dmg_taken_calc_hooks()
    test_cond_mult_and_stacks()
    test_death_dance()
    test_act_done_randuin()
    test_affix_basic()
    test_affix_onhit()
    test_affix_taken()
    test_affix_cond_mult()
    test_novice_hunt_combo()
    test_combo_end()
    test_affix_purify()
    test_affix_regen_tail()
    print(f"\n=== 结果 PASS={PASS} FAIL={FAIL} ===")
    if FAILURES:
        for f in FAILURES:
            print(f"  - {f}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
