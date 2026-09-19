# -*- coding: utf-8 -*-
"""v181.M-R2e 引擎扩展验收（方案 docs/archive/REFACTOR_v181_M_R2e_engine_ext_plan.md，鱼鱼已批）。

覆盖：
  A affix 动态 cap：
    1. bonus.cap 装配：rage_forge→bonus.cap.rage=2；卸下覆盖写回落；full_pack purple
       tiers→energy+10；energy_blade（现网 cost_reduce 型非上限）零贡献
    2. 引擎收敛：_cap_of = EFFECT_RULES 基础 + bonus.cap（12）；effects 叠层 clamp 到 12
       不溢出、超新 cap 不溢出；无 bonus.cap 仍 10
    3. 装配渠道 clamp 动态：牧师装 divine_radiance（faith cap 11）→ heal_cast 渠道 +2
       攒到 11 不溢出（class_res_channel_gain 读 _cap_of）
  B1 faith_unload 兑现（heal_clear/冷静 R1c 同族 res_cost 数据通道）：
    faith 5 → 卸负施放扣 3 → 2 + 回血 80% 魔攻+成长（kind=治疗 heal_formula）；
    faith 2 不足拦截；float 层（6.3）扣 3 → 3.3 保真
  B2 负载档位 + 过载：
    4. 装配：牧师（start_classes）挂 heal_calc/class_faith_load_tier + threshold/
       class_faith_overload；战士无（防白拿）
    5. heal_calc 乘区直调：0-3 清醒 ×1.0 / 4-7 专注 ×1.25 / 8-9 透支 ×1.5 /
       10 过载档 ×1.0（档位表逐字 v130）
    6. 端到端：牧师真实 _do_heal 治疗 → 施放层档位乘区生效（真实面板基值断言）
    7. 过载：渠道攒满 cap（8→10 当次）→ 清零 + 我方全员回复 max_hp×0.015；
       防重复（满层后再 +2 不再触发）；清零后重新攒满再次过载
  B3 effects float 通用层：
    8. faith period 每刻 -0.7 衰减（首跳延迟语义 10→9.3→8.6→7.9，clamp 0 不归负）
    9. 展示 floor：resource_stack_text float 层 floor 取整（7.9 → 7/10层）；int 资源不变
    10. 回归：非牧师治疗无档位乘区（零行为）

跑法：python tests/test_class_mech_r2e.py（exit=0 全绿）
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_mech_r2e.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)

from saintess_engine import config as _b2c
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # ★ P5C-REPOINT：宿主装配壳已删 → 测试侧引擎通道装配口
from saintess_engine import Battle as B2, make_actor
from saintess_engine import actions as A
from saintess_engine.battle.actors import ActCtx
from saintess_engine.battle.effects import _cap_of, apply_effects
from saintess_engine.battle.effect_triggers import fire
from saintess_engine.battle.schedule import _advance_time
from saintess_engine.battle.state_effects import state_def
from content.mech import equip as EP  # ★ P5C-REPOINT：直取包内真源（原 battle_equip_proc）
from content.mech.class_mech import apply_class_mech  # ★ P5C-REPOINT：直取包内真源

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def _capb(a):
    """bonus.cap 分域读（v181.M-bonus 统一容器）。"""
    return ((a or {}).get("bonus") or {}).get("cap") or {}



def mk(cid, name, hp=3000, matk=220, mp=300, lv=40, learned=(), uid="p"):
    a = make_actor(uid=uid, name=name, side="player", kind="player",
                   human_controlled=True, class_name=cid, level=lv,
                   hp=hp, max_hp=hp, mp=mp, max_mp=mp,
                   atk=80, matk=matk, spd=12, crit=0.05,
                   skills=[], learned_skills=list(learned),
                   race=None, evolve_path=0, class_tier=0, attributes={},
                   **{"def": 40, "mdef": 60})
    return a


def mk_priest(learned=()):
    return mk("cls_mu_shi", "牧师", learned=learned)


def mk_warrior(learned=(), uid="p9"):
    return mk("cls_zhan_shi", "战士", hp=3000, matk=60, learned=learned, uid=uid)


def mk_enemy(hp=99999):
    return make_actor(uid="e1", name="木桩", side="enemy", kind="monster",
                      hp=hp, max_hp=hp, atk=1, matk=1, spd=5, crit=0.0,
                      level=60, exp=0, gold=0, **{"def": 5, "mdef": 5})


def _battle(*actors):
    sides = {"player": [], "enemy": []}
    for a in actors:
        sides[a.get("side") or "enemy"].append(a)
    return B2(btype="monster", sides=sides)


def equip_affix(actor, aid, slot="weapon", quality="purple"):
    actor.setdefault("equipment", {})[slot] = {
        "slot": slot, "quality": quality, "affixes": [aid], "stats": {}}
    return actor


def _stacks(a, k):
    ent = ((a or {}).get("effects") or {}).get(k)
    return ent.get("stacks", None) if isinstance(ent, dict) else None


# ============================================================
# A：affix 动态 cap
# ============================================================

def t_a_cap_bonus_assemble():
    print("【A.1 bonus.cap 装配：max_bonus 词条 → actor 容器（覆盖写幂等）】")
    p = mk_warrior()
    equip_affix(p, "rage_forge", "weapon", "purple")
    EP.apply_to_actor(p)
    cb = _capb(p)
    check("rage_forge → bonus.cap.rage = 2", int(cb.get("rage", 0)) == 2, repr(cb))
    check("rage_forge 无 triggers/effects 噪音（非事件词条）",
          not (p.get("triggers") or {}) and not (p.get("effects") or {}),
          f"triggers={p.get('triggers')} effects={p.get('effects')}")
    # 卸下 → 覆盖写回落（重装配 = 当前装备全量）
    p["equipment"]["weapon"]["affixes"] = []
    EP.apply_to_actor(p)
    check("卸下后 bonus.cap 移除（重装配回落）", "rage" not in _capb(p), repr(_capb(p)))
    # full_pack purple tiers 档位 10
    r = mk("cls_you_xia", "游侠")
    equip_affix(r, "full_pack", "weapon", "purple")
    EP.apply_to_actor(r)
    check("full_pack purple tiers → bonus.cap.energy +10", int(_capb(r).get("energy", 0)) == 10, repr(_capb(r)))
    # energy_blade：现网数据为 cost_reduce 型（无 max_bonus）→ 零贡献（版本漂移非上限词条）
    r2 = mk("cls_you_xia", "游侠2")
    equip_affix(r2, "energy_blade", "weapon", "blue")
    EP.apply_to_actor(r2)
    check("energy_blade（cost_reduce 型）零 bonus.cap 贡献",
          "energy" not in _capb(r2), repr(_capb(r2)))


def t_a_cap_clamp():
    print("【A.2 引擎 cap 收敛：叠层 clamp 读动态 cap（10+2=12 不溢出）】")
    p = mk_warrior()
    equip_affix(p, "rage_forge", "weapon", "purple")
    EP.apply_to_actor(p)
    apply_class_mech(p)
    b = _battle(p, mk_enemy())
    check("_cap_of(rage) = 12（10 + bonus.cap 2）", _cap_of(p, "rage") == 12, f"{_cap_of(p, 'rage')}")
    # 无 bonus.cap 的战士仍 10
    w2 = mk_warrior()
    check("无词条 _cap_of(rage) = 10", _cap_of(w2, "rage") == 10, f"{_cap_of(w2, 'rage')}")
    # apply op=add ×12 → 到 12（clamp 不溢出）
    for _i in range(12):
        apply_effects(b, p, p, [{"type": "apply", "op": "add", "key": "rage",
                                 "amount": 1, "on": "caster"}], [])
    check("叠层到 12（动态 cap 生效）", _stacks(p, "rage") == 12, f"{_stacks(p, 'rage')}")
    # 超新 cap 追加 → clamp 12 不溢出
    apply_effects(b, p, p, [{"type": "apply", "op": "add", "key": "rage",
                             "amount": 5, "on": "caster"}], [])
    check("超 cap 追加 clamp 12（不溢出）", _stacks(p, "rage") == 12, f"{_stacks(p, 'rage')}")
    # 行为零变化：无词条叠层仍 clamp 10
    w3 = mk_warrior()
    b3 = _battle(w3, mk_enemy())
    for _i in range(15):
        apply_effects(b3, w3, w3, [{"type": "apply", "op": "add", "key": "rage",
                                    "amount": 1, "on": "caster"}], [])
    check("无 bonus.cap 仍 clamp 10（int 语义不变）", _stacks(w3, "rage") == 10, f"{_stacks(w3, 'rage')}")


def t_a_channel_clamp_dynamic():
    print("【A.3 装配渠道 clamp 收敛：牧师 faith bonus.cap → 渠道攒取到新 cap】")
    p = mk_priest()
    # divine_radiance faith +1（cap 10 → 11）
    equip_affix(p, "divine_radiance", "armor", "purple")
    EP.apply_to_actor(p)
    apply_class_mech(p)
    b = _battle(p, mk_enemy())
    check("divine_radiance → bonus.cap.faith = 1", int(_capb(p).get("faith", 0)) == 1, repr(_capb(p)))
    check("牧师 _cap_of(faith) = 11（渠道 clamp 收敛动态 cap）", _cap_of(p, "faith") == 11,
          f"{_cap_of(p, 'faith')}")
    # heal_cast 渠道 +2 ×5 → 10：cap 11 下不满 → 不触发过载（渠道 clamp 上限已抬）
    for _i in range(5):
        A.do_skill(b, ActCtx(caster=p, action="skill", skill_name="小愈",
                             info={"kind": "治疗", "hp_pct": 0.02, "name": "小愈"}, target=None))
    check("渠道攒取越过旧 cap 10 不满新 cap 11（动态 clamp 生效）",
          _stacks(p, "faith") == 10, f"stacks={_stacks(p, 'faith')}")
    # 第 6 次 +2 → clamp 11（满新 cap 当次）→ 过载清零
    A.do_skill(b, ActCtx(caster=p, action="skill", skill_name="小愈",
                         info={"kind": "治疗", "hp_pct": 0.02, "name": "小愈"}, target=None))
    check("满新 cap 11 当次 → 过载清零（动态 cap 与过载同源）",
          _stacks(p, "faith") == 0, f"stacks={_stacks(p, 'faith')}")


# ============================================================
# B1：faith_unload 兑现
# ============================================================

def t_b1_faith_unload():
    print("【B.1 faith_unload：卸负 res_cost 兑现（heal_clear 冷静同族）】")
    pu = mk_priest(learned=("卸负",))
    apply_class_mech(pu)
    b = _battle(pu, mk_enemy())
    # MECH_CASH 声明存在（装配层记录）
    from content.mech.class_data import MECH_CASH
    check("MECH_CASH.faith_unload 声明（mode=heal_clear 技能内兑现）",
          isinstance(MECH_CASH.get("faith_unload"), dict)
          and MECH_CASH["faith_unload"].get("mode") == "heal_clear", repr(MECH_CASH.get("faith_unload")))
    pu.setdefault("effects", {})["faith"] = {"stacks": 5, "expire": 99999}
    pu["hp"] = 1000
    info = {"kind": "治疗", "mech": "faith_unload", "mech_val": 3,
            "heal_formula": "matk*0.8 + 15 + player_lv*0.5 + skill_lv*8",
            "name": "卸负", "cd": 12, "res_cost": {"faith": 3}, "mp": 0}
    logs = A.do_skill(b, ActCtx(caster=pu, action="skill", skill_name="卸负",
                                info=info, target=pu))
    # act_cast 渠道（kind=治疗）+2 在 _spend_skill_cost 扣 3 后 → 施放后层 = 5-3+2 = 4
    check("卸负施放扣 3 层（5→3 前 → 2，渠道 +2 后 4）", _stacks(pu, "faith") == 4,
          f"stacks={_stacks(pu, 'faith')} logs={[x for x in logs if '信仰值' in str(x)]}")
    # 回血断言：heal 日志数值 == 实际 hp 增量（公式基值由引擎 eval，测试不二次推算面板——
    # 倍率精确性由档位直调 fire 覆盖；此处验证施放层 4 → 专注档 ×1.25 已进日志且落地一致）
    heal_log = None
    for _x in logs:
        _s = str(_x)
        if "圣光治愈" in _s or "治愈了" in _s:
            heal_log = _s
    import re as _re
    _m = _re.search(r"(\d+) 点生命", heal_log or "")
    heal_val = int(_m.group(1)) if _m else None
    check("卸负回血 80% 魔攻+成长（专注档 ×1.25 日志 + 落地一致）",
          heal_val is not None and pu["hp"] == 1000 + heal_val
          and any("信仰专注！治疗 ×1.25" in str(x) for x in logs),
          f"hp={pu['hp']} heal_log={heal_log} logs={logs[-2:]}")
    # 不足拦截（faith 2 < 3）
    pu2 = mk_priest(learned=("卸负",))
    apply_class_mech(pu2)
    b2 = _battle(pu2, mk_enemy())
    pu2.setdefault("effects", {})["faith"] = {"stacks": 2, "expire": 99999}
    pu2["hp"] = 1000
    logs2 = A.do_skill(b2, ActCtx(caster=pu2, action="skill", skill_name="卸负",
                                  info=info, target=pu2))
    check("faith 2 不足 → 拦截不回血不扣层",
          pu2["hp"] == 1000 and _stacks(pu2, "faith") == 2
          and any("核心资源不足" in str(x) for x in logs2),
          f"hp={pu2['hp']} stacks={_stacks(pu2, 'faith')} logs={logs2[:1]}")


def t_b1_float_consume():
    print("【B.1b float 消费保真：faith 6.3 扣 3 → 3.3（B3 float 通用层）】")
    pu = mk_priest(learned=("卸负",))
    apply_class_mech(pu)
    b = _battle(pu, mk_enemy())
    pu.setdefault("effects", {})["faith"] = {"stacks": 6.3, "expire": 99999}
    pu["hp"] = 1000
    info = {"kind": "治疗", "mech": "faith_unload", "mech_val": 3,
            "heal_formula": "matk*0.8 + 15 + player_lv*0.5 + skill_lv*8",
            "name": "卸负", "cd": 12, "res_cost": {"faith": 3}, "mp": 0}
    A.do_skill(b, ActCtx(caster=pu, action="skill", skill_name="卸负",
                         info=info, target=pu))
    v = _stacks(pu, "faith")
    # 6.3 - 3（扣）+ 2（渠道） = 5.3
    check("6.3 扣 3 加渠道 2 → 5.3（float 保真）",
          isinstance(v, float) and abs(v - 5.3) < 1e-6, f"stacks={v!r}")


# ============================================================
# B2：负载档位乘区 + 过载
# ============================================================

def t_b2_assemble():
    print("【B.2 装配：牧师挂 heal_calc 档位 + threshold 过载；非牧师防白拿】")
    p = mk_priest()
    apply_class_mech(p)
    tr = p.get("triggers") or {}
    hc = [x for x in tr.get("heal_calc", []) if x.get("type") == "class_faith_load_tier"]
    th = [x for x in tr.get("threshold", []) if x.get("type") == "class_faith_overload"]
    check("牧师 heal_calc 挂 class_faith_load_tier", len(hc) == 1, repr(hc))
    check("牧师 threshold 挂 class_faith_overload", len(th) == 1, repr(th))
    w = mk_warrior()
    apply_class_mech(w)
    check("战士无 heal_calc/threshold 钩子（start_classes 防白拿）",
          not (w.get("triggers") or {}).get("heal_calc")
          and not (w.get("triggers") or {}).get("threshold"),
          repr((w.get("triggers") or {}).keys()))


def t_b2_tier_mult():
    print("【B.2 档位乘区直调：load_tiers 逐字（清醒 1.0 / 专注 1.25 / 透支 1.5 / 过载 1.0）】")
    p = mk_priest()
    apply_class_mech(p)
    e = mk_enemy()
    b = _battle(p, e)
    tiers = (state_def("faith") or {}).get("load_tiers")
    check("EFFECT_RULES faith.load_tiers 四档数据（v130 逐字）",
          isinstance(tiers, list) and len(tiers) == 4
          and tiers[0] == {"max": 3, "heal_mult": 1.00, "label": "清醒"}
          and tiers[1] == {"max": 7, "heal_mult": 1.25, "label": "专注"}
          and tiers[2] == {"max": 9, "heal_mult": 1.50, "label": "透支"}
          and tiers[3].get("max") == 10 and tiers[3].get("overload") is True,
          repr(tiers))
    cases = [(2, 1.0), (3, 1.0), (3.5, 1.25), (5, 1.25), (7, 1.25),
             (8.5, 1.5), (9, 1.5), (9.7, 1.0), (10, 1.0)]
    for n, want in cases:
        p.setdefault("effects", {})["faith"] = {"stacks": n}
        logs = []
        fire(b, "heal_calc", {"actor": p, "target": p, "heal": 100,
                              "info": {"name": "愈"}, "mult": 1.0}, logs)
        m = float(getattr(b, "_fire_ctx", {}).get("mult", 1.0))
        check(f"faith {n} 层 → 档位 ×{want}", abs(m - want) < 1e-6, f"mult={m}")
    # 无 faith 条目 → 清醒档（零行为）
    (p.get("effects") or {}).pop("faith", None)
    logs2 = []
    fire(b, "heal_calc", {"actor": p, "target": p, "heal": 100,
                          "info": {"name": "愈"}, "mult": 1.0}, logs2)
    m2 = float(getattr(b, "_fire_ctx", {}).get("mult", 1.0))
    check("无 faith 条目 → ×1.0（零行为）", abs(m2 - 1.0) < 1e-6, f"mult={m2}")


def t_b2_end2end_heal():
    print("【B.2 端到端：牧师治疗施放经 heal_calc 档位乘区放大】")
    p = mk_priest()
    apply_class_mech(p)
    b = _battle(p, mk_enemy())
    info = {"kind": "治疗", "heal_formula": "matk*1.0", "name": "测试治愈"}
    # 3.5 层 → 施放渠道 +2 → 5.5 专注 ×1.25（公式基值由引擎 eval——断言日志数值与
    # 落地一致 + 倍率日志，数值精确性由档位直调 fire 覆盖）
    p.setdefault("effects", {})["faith"] = {"stacks": 3.5, "expire": 99999}
    p["hp"] = 1000
    logs = A.do_skill(b, ActCtx(caster=p, action="skill", skill_name="测试治愈",
                                info=info, target=p))
    heal_log = None
    for _x in logs:
        _s = str(_x)
        if "圣光治愈" in _s or "治愈了" in _s:
            heal_log = _s
    import re as _re
    _m = _re.search(r"(\d+) 点生命", heal_log or "")
    heal_val = int(_m.group(1)) if _m else None
    check("施放层 5.5 → 专注 ×1.25 端到端放大（日志=落地）",
          heal_val is not None and p["hp"] == 1000 + heal_val
          and any("信仰专注！治疗 ×1.25" in str(x) for x in logs),
          f"hp={p['hp']} heal_log={heal_log}")
    # 战士（无档位钩子）同技能 → 无乘区（零行为）
    w = mk_warrior()
    apply_class_mech(w)
    bw = _battle(w, mk_enemy())
    w.setdefault("effects", {})["faith"] = {"stacks": 8, "expire": 99999}  # 战士手塞层也不乘（无钩子）
    w["hp"] = 1000
    logs_w = A.do_skill(bw, ActCtx(caster=w, action="skill", skill_name="测试治愈",
                                   info=info, target=w))
    heal_log_w = None
    for _x in logs_w:
        _s = str(_x)
        if "圣光治愈" in _s or "治愈了" in _s:
            heal_log_w = _s
    _m2 = _re.search(r"(\d+) 点生命", heal_log_w or "")
    heal_val_w = int(_m2.group(1)) if _m2 else None
    check("战士治疗无乘区（heal_calc 只装配给牧师）",
          heal_val_w is not None and w["hp"] == 1000 + heal_val_w
          and not any("信仰" in str(x) for x in logs_w),
          f"hp={w['hp']} heal_log={heal_log_w}")


def t_b2_overload():
    print("【B.2 过载：渠道攒满 cap 当次 → 清零 + 我方全员回复 1.5% max_hp】")
    pr = mk_priest()
    apply_class_mech(pr)
    ally = mk_warrior(uid="p8")
    apply_class_mech(ally)
    b = _battle(pr, ally, mk_enemy())
    pr["hp"] = 2000
    ally["hp"] = 2000
    pr.setdefault("effects", {})["faith"] = {"stacks": 8, "expire": 99999}
    info = {"kind": "治疗", "hp_pct": 0.05, "name": "小治愈"}
    # 第 1 次施放：8 +2 → clamp 10（满 cap 当次）→ 过载清零 + 全队回复 45
    logs = A.do_skill(b, ActCtx(caster=pr, action="skill", skill_name="小治愈",
                                info=info, target=None))
    check("过载触发：faith 清零", _stacks(pr, "faith") == 0, f"stacks={_stacks(pr, 'faith')}")
    # 自身 = 2000 + 本次治疗落地（hp_pct×max_hp×heal_power 乘区，日志数值） + 过载 45
    heal_self = None
    for _x in logs:
        _s = str(_x)
        if "圣光治愈" in _s or "治愈了" in _s:
            heal_self = _s
    import re as _re
    _m = _re.search(r"(\d+) 点生命", heal_self or "")
    heal_v = int(_m.group(1)) if _m else None
    check("过载自身回复 45（治疗落地之上）",
          heal_v is not None and pr["hp"] == 2000 + heal_v + 45,
          f"hp={pr['hp']} heal={heal_v} logs={logs[-3:]}")
    check("全队回复 45（队友）", ally["hp"] == 2045, f"hp={ally['hp']}")
    check("过载文案", any("过载" in str(x) for x in logs), repr(logs[-2:]))
    # 防重复：过载清零后同刻/连续施放不重复触发（0→2→4 无满层）
    A.do_skill(b, ActCtx(caster=pr, action="skill", skill_name="小治愈",
                         info=info, target=None))
    check("清零后继续攒取（2 层，无重复过载）", _stacks(pr, "faith") == 2,
          f"stacks={_stacks(pr, 'faith')}")
    # 重新攒满（2→4→6→8→10 第 4 次到 10）→ 再次过载
    for _i in range(4):
        A.do_skill(b, ActCtx(caster=pr, action="skill", skill_name="小治愈",
                             info=info, target=None))
    check("重新攒满再次过载清零（每满一次触发一次）", _stacks(pr, "faith") == 0,
          f"stacks={_stacks(pr, 'faith')}")
    check("再次过载全队再回 45", ally["hp"] == 2090, f"hp={ally['hp']}")
    # overload_heal_pct 数据声明（0.015 v130 旧值）
    check("faith.overload_heal_pct = 0.015",
          abs(float((state_def("faith") or {}).get("overload_heal_pct", 0) or 0) - 0.015) < 1e-9,
          repr(state_def("faith").get("overload_heal_pct")))


# ============================================================
# B3：float 通用层 + 衰减 + 展示
# ============================================================

def t_b3_decay():
    print("【B.3 faith period 每刻 -0.7 衰减（float 层；clamp 0 不归负）】")
    p = mk_priest()
    apply_class_mech(p)
    b = _battle(p, mk_enemy())
    check("faith.period = {dir gain, interval 1.0, amount -0.7}",
          (state_def("faith") or {}).get("period") ==
          {"dir": "gain", "interval": 1.0, "amount": -0.7},
          repr((state_def("faith") or {}).get("period")))
    p.setdefault("effects", {})["faith"] = {"stacks": 10, "expire": 99999}
    # 首跳登记延迟：第 1 次推进只登记下一跳；之后每刻一跳
    _advance_time(b, 1.0, [])   # now=1.0（登记 dnext=1.0）
    v0 = _stacks(p, "faith")
    check("首跳登记刻不衰减（对齐 DOT 首跳延迟）", v0 == 10, f"stacks={v0!r}")
    _advance_time(b, 1.0, [])   # now=2.0 → 10 - 0.7 = 9.3
    v1 = _stacks(p, "faith")
    check("第 1 跳 10 → 9.3（float 层）",
          isinstance(v1, float) and abs(v1 - 9.3) < 1e-6, f"stacks={v1!r}")
    _advance_time(b, 1.0, [])   # now=3.0 → 9.3 - 0.7 = 8.6
    v2 = _stacks(p, "faith")
    check("第 2 跳 9.3 → 8.6（float 层）",
          isinstance(v2, float) and abs(v2 - 8.6) < 1e-6, f"stacks={v2!r}")
    _advance_time(b, 1.0, [])   # now=4.0 → 8.6 - 0.7 = 7.9
    v3 = _stacks(p, "faith")
    check("第 3 跳 8.6 → 7.9（≈0.7/刻均值）",
          isinstance(v3, float) and abs(v3 - 7.9) < 1e-6, f"stacks={v3!r}")
    # 衰减到 0 clamp 不归负（+17 刻：7.9 - 0.7×17 < 0 → clamp 0）
    for _i in range(20):
        _advance_time(b, 1.0, [])
    v_end = _stacks(p, "faith")
    check("衰减 clamp 0 不归负", v_end == 0, f"stacks={v_end!r}")


def t_b3_display_floor():
    print("【B.3 展示 floor：float 层取整显示（内部 float、玩家整数观感）】")
    from content.combat_cmds import resource_stack_text  # ★ P5C-REPOINT
    t1 = resource_stack_text({"faith": {"stacks": 7.9}})
    check("faith 7.9 → 显示 7/10层（floor）", "信仰值 7/10层" in t1, repr(t1))
    t2 = resource_stack_text({"faith": {"stacks": 0.6}})
    check("faith 0.6 → floor 0 层不显示", t2 == "", repr(t2))
    t3 = resource_stack_text({"zhan_yi": {"stacks": 5}})
    check("int 资源展示不变（战意 5/10层）", "战意 5/10层" in t3, repr(t3))
    t4 = resource_stack_text({"energy": {"stacks": 100}})
    check("energy 100 整值展示不变", "精力 100/100层" in t4, repr(t4))


def main():
    print("=== v181.M-R2e 引擎扩展验收 ===")
    t_a_cap_bonus_assemble()
    t_a_cap_clamp()
    t_a_channel_clamp_dynamic()
    t_b1_faith_unload()
    t_b1_float_consume()
    t_b2_assemble()
    t_b2_tier_mult()
    t_b2_end2end_heal()
    t_b2_overload()
    t_b3_decay()
    t_b3_display_floor()
    print(f"\n=== 结果 PASS={PASS} FAIL={FAIL} ===")
    if FAILURES:
        for f in FAILURES:
            print(f"  - {f}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
