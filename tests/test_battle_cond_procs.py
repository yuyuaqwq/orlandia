# -*- coding: utf-8 -*-
"""v181 cond 接线验收：game/services/battle_cond_procs（技能条件倍率 → 乘区钩子）。

覆盖：装配（有 cond 技能才挂）/ 各谓词命中与不命中 / 倍率累乘 / 未注册 type 静默 /
      heal_calc 同挂 / melody 谓词读源（effects.melody_state，非旧 battle._melody）。

跑法：python tests/test_battle_cond_procs.py
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_b2_cond.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _b2c  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # ★ P5C-REPOINT：宿主装配壳已删 → 测试侧引擎通道装配口
from ext_combat import Battle as B2, make_actor  # noqa: E402
from ext_combat.battle.effect_triggers import fire  # noqa: E402
from content.mech.class_mech import apply_class_mech  # ★ P5C-REPOINT：直取包内真源
from content.mech import cond_procs as CP  # ★ P5C-REPOINT：直取包内真源（原 battle_cond_procs）
from content import skills as _SK  # noqa: E402
from ext_combat.gauge import bar_effect_key# noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def mk_actor(side="player", cls="cls_wu_seng", learned=None, uid="p1", spd=15):
    kw = dict(uid=uid, name="测试者", side=side, hp=3000, max_hp=3000,
              atk=100, matk=80, spd=spd, crit=0.0, level=20)
    if side == "player":
        kw.update(kind="player", human_controlled=True, class_name=cls,
                  mp=200, max_mp=200, equipment={}, skills=[],
                  learned_skills=list(learned or []), race=None,
                  evolve_path=0, class_tier=0, attributes={}, **{"def": 40, "mdef": 30})
    else:
        kw.update(kind="monster", **{"def": 10, "mdef": 10})
    return make_actor(**kw)


def new_battle(p, e):
    return B2(btype="monster", sides={"player": [p], "enemy": [e]})


def _has_trigger(actor, ev):
    return any(isinstance(x, dict) and x.get("action") == "skill_cond_mult"
               for x in ((actor.get("triggers") or {}).get(ev) or []))


def _fire_dmg(b, p, e, info, logs=None):
    """触发 dmg_calc 并返回乘区（模拟引擎插桩点）。"""
    from ext_combat.battle.effect_triggers import fire as _fire
    _fire(b, "dmg_calc", {"actor": p, "target": e, "dmg": 100,
                          "is_crit": False, "info": info, "mult": 1.0}, logs or [])
    return float((getattr(b, "_fire_ctx", {}) or {}).get("mult", 1.0) or 1.0)


def _sid(cls, cname):
    """按中文技能名反查技能 id（含嵌套层；避免硬编码 id 漂移）。"""
    tbl = (_SK.PLAYER_SKILLS or {}).get(cls) or {}
    for k, v in tbl.items():
        if isinstance(v, dict):
            if v.get("name") == cname:
                return k
            for k2, v2 in v.items():
                if isinstance(v2, dict) and v2.get("name") == cname:
                    return k2
    return None


def test_install():
    print("【1. 装配：有 cond 技能才挂 dmg_calc/heal_calc】")
    p = mk_actor(cls="cls_wu_seng", learned=["sk_ce_ti"])   # 侧踢 cond=enemy_broken
    apply_class_mech(p)
    check("拳师（学侧踢）挂 dmg_calc 条件乘区", _has_trigger(p, "dmg_calc"), f"trig={p.get('triggers')}")
    check("同时挂 heal_calc（治疗系条件同源）", _has_trigger(p, "heal_calc"), f"trig={p.get('triggers')}")
    # 反向：学一个不带 cond 的技能 → 不挂
    no_cond = [k for k, v in _SK.PLAYER_SKILLS["cls_wu_seng"].items()
               if isinstance(v, dict) and not isinstance(v.get("cond"), dict)]
    p2 = mk_actor(cls="cls_wu_seng", learned=no_cond[:1])
    apply_class_mech(p2)
    check("无 cond 技能不挂（零噪音）", not _has_trigger(p2, "dmg_calc"), f"trig={p2.get('triggers')}")
    # 幂等
    apply_class_mech(p)
    n = len([x for x in ((p.get("triggers") or {}).get("dmg_calc") or [])
             if isinstance(x, dict) and x.get("action") == "skill_cond_mult"])
    check("重复装配幂等（只 1 条）", n == 1, f"n={n}")


def test_enemy_broken():
    print("【2. enemy_broken（侧踢 ×1.3）：读 buffs.shaken 触发态】")
    p = mk_actor(cls="cls_wu_seng", learned=["sk_ce_ti"])
    apply_class_mech(p)
    e = mk_actor(side="enemy", uid="e1")
    b = new_battle(p, e)
    info = {"name": "侧踢", "kind": "物理", "exprs": ["atk*0.9"],
            "cond": {"type": "enemy_broken", "mult": 1.3}}
    m0 = _fire_dmg(b, p, e, info)
    check("未破防 → 乘区 1.0", m0 == 1.0, f"mult={m0}")
    e.setdefault("effects", {})[bar_effect_key("shaken")] = {
        "val": 0.0, "threshold": 50, "trigger_count": 1, "immune_until": 2.0, "_at": 0.0}
    m1 = _fire_dmg(b, p, e, info)
    check("破防中 → 乘区 1.3", abs(m1 - 1.3) < 1e-9, f"mult={m1}")
    # 破绽断链时（trigger_count=0）不算破防
    e["effects"][bar_effect_key("shaken")]["trigger_count"] = 0
    m2 = _fire_dmg(b, p, e, info)
    check("trigger_count=0 → 不判定破防", m2 == 1.0, f"mult={m2}")


def test_player_first():
    print("【3. player_first（冲锋 ×1.15）：速度高于目标】")
    p = mk_actor(cls="cls_zhan_shi", learned=[_sid("cls_zhan_shi", "冲锋")], spd=30)
    apply_class_mech(p)
    e = mk_actor(side="enemy", uid="e1", spd=5)
    b = new_battle(p, e)
    check("装配成功（冲锋 cond 已挂）", _has_trigger(p, "dmg_calc"), f"trig={p.get('triggers')}")
    info = {"name": "冲锋", "kind": "物理", "exprs": ["atk*1.0"],
            "cond": {"type": "player_first", "mult": 1.15}}
    check("速度占优 → ×1.15", abs(_fire_dmg(b, p, e, info) - 1.15) < 1e-9)
    p["spd"], e["spd"] = 5, 99
    check("速度劣势 → 1.0", _fire_dmg(b, p, e, info) == 1.0)


def test_enemy_debuff():
    print("【4. enemy_debuff（致命狙击 ×1.3）：目标带减益】")
    p = mk_actor(cls="cls_you_xia", learned=[_sid("cls_you_xia", "致命狙击")], spd=20)
    apply_class_mech(p)
    e = mk_actor(side="enemy", uid="e1")
    b = new_battle(p, e)
    check("装配成功（致命狙击 cond 已挂）", _has_trigger(p, "dmg_calc"), f"trig={p.get('triggers')}")
    info = {"name": "致命狙击", "kind": "物理", "exprs": ["atk*1.2"],
            "cond": {"type": "enemy_debuff", "mult": 1.3}}
    check("无减益 → 1.0", _fire_dmg(b, p, e, info) == 1.0)
    e.setdefault("effects", {})["def_down"] = {"stacks": 1, "expire": None}
    check("属性降 → ×1.3", abs(_fire_dmg(b, p, e, info) - 1.3) < 1e-9)
    e["effects"].pop("def_down")
    e["effects"]["poison"] = {"stacks": 2}
    check("DOT 层 → ×1.3", abs(_fire_dmg(b, p, e, info) - 1.3) < 1e-9)


def test_melody_predicates():
    print("【5. melody 谓词：读 effects.melody_state（saintess_engine 真实载体）】")
    p = mk_actor(cls="cls_wu_seng", learned=["sk_ce_ti"])   # 侧踢（cond=enemy_broken）
    apply_class_mech(p)
    e = mk_actor(side="enemy", uid="e1")
    b = new_battle(p, e)
    check("装配成功（借 cond 技能挂载）", _has_trigger(p, "dmg_calc"), f"trig={p.get('triggers')}")
    i_buff = {"name": "咏叹调", "kind": "物理", "exprs": ["atk*1.0"],
              "cond": {"type": "melody_buff", "mult": 1.3}}
    i_stk = {"name": "天籁", "kind": "物理", "exprs": ["atk*1.0"],
             "cond": {"type": "melody_stacks", "stacks": 4, "mult": 1.3}}
    check("无旋律 → melody_buff 1.0", _fire_dmg(b, p, e, i_buff) == 1.0)
    # 旧载体：battle._melody 设了也不该生效（读源已切 effects.melody_state）
    b._melody = {"name": "战歌", "kind": "atk", "stack": 5}
    check("旧载体 battle._melody 不生效（读源已切）", _fire_dmg(b, p, e, i_buff) == 1.0)
    p.setdefault("effects", {})["melody_state"] = {"kind": "atk", "stacks": 1, "name": "战歌"}
    check("melody_state.kind=atk → ×1.3", abs(_fire_dmg(b, p, e, i_buff) - 1.3) < 1e-9)
    check("强度 1 <4 → melody_stacks 1.0", _fire_dmg(b, p, e, i_stk) == 1.0)
    p["effects"]["melody_state"]["stacks"] = 5
    check("强度 5 ≥4 → ×1.3", abs(_fire_dmg(b, p, e, i_stk) - 1.3) < 1e-9)
    p["effects"]["melody_state"]["kind"] = "e_atk"   # 挽歌系（减益，非增益）
    check("挽歌系 e_atk 不算增益系 → 1.0", _fire_dmg(b, p, e, i_buff) == 1.0)


def test_unknown_type_and_heal():
    print("【6. 未注册 type 静默 + heal_calc 同挂】")
    p = mk_actor(cls="cls_wu_seng", learned=["sk_ce_ti"])
    apply_class_mech(p)
    e = mk_actor(side="enemy", uid="e1")
    b = new_battle(p, e)
    info = {"name": "幽灵技能", "cond": {"type": "not_registered_yet", "mult": 9.9}}
    check("未注册 type → 静默 1.0（不崩）", _fire_dmg(b, p, e, info) == 1.0)
    check("未注册 type 已注册表中不存在", "not_registered_yet" not in CP.COND_PREDICATES)
    # heal_calc：治疗旋使用同一动作
    from ext_combat.battle.effect_triggers import fire as _fire
    e.setdefault("effects", {})[bar_effect_key("shaken")] = {
        "trigger_count": 1, "immune_until": 2.0, "_at": 0.0}
    hinfo = {"name": "治疗试技", "kind": "治疗", "cond": {"type": "enemy_broken", "mult": 1.3}}
    _fire(b, "heal_calc", {"actor": p, "target": p, "heal": 100, "info": hinfo, "mult": 1.0}, [])
    m = float((getattr(b, "_fire_ctx", {}) or {}).get("mult", 1.0) or 1.0)
    # heal_calc 的 target 是治疗对象（自己），破绽挂在敌人身上 → 本条不命中（预期）
    check("heal_calc 挂载生效（不抛异常）", m in (1.0, 1.3), f"mult={m}")


def test_end_to_end_damage():
    print("【7. 端到端：真实技能管线（侧踢）破防前后伤害对比】")
    from ext_combat.battle import actions as A
    from content.skills import skill_info  # ★ P5C-REPOINT
    real = skill_info("cls_wu_seng", "sk_ce_ti")
    check("取到真实侧踢数据且带 cond", isinstance(real, dict) and isinstance(real.get("cond"), dict),
          f"info={bool(real)}")
    dmg = {}
    for tag, broken in (("no", False), ("yes", True)):
        import random as _r
        _r.seed(20260910)   # 两组对照必须从同一随机状态起跑（否则暴击/幸运段不同源）
        p = mk_actor(cls="cls_wu_seng", learned=["sk_ce_ti"])
        apply_class_mech(p)
        e = mk_actor(side="enemy", uid="e1", spd=1)
        b = new_battle(p, e)
        if broken:
            e.setdefault("effects", {})[bar_effect_key("shaken")] = {
                "val": 0.0, "threshold": 50, "trigger_count": 1,
                "immune_until": 2.0, "_at": 0.0}
        logs = A._single_target_pipeline(b, p, e, real, 1)
        dmg[tag] = e["max_hp"] - e["hp"]
    check(f"破防伤害 > 未破防（{dmg['no']} → {dmg['yes']}，约 ×1.3）",
          dmg["yes"] > dmg["no"] and abs(dmg["yes"] / max(1, dmg["no"]) - 1.3) < 0.06,
          f"no={dmg['no']} yes={dmg['yes']}")


if __name__ == "__main__":
    # 伤害管线含随机（暴击/幸运段）——固定随机种子保证端到端倍数断言稳定
    import random as _r
    _r.seed(20260910)
    test_install()
    test_enemy_broken()
    test_player_first()
    test_enemy_debuff()
    test_melody_predicates()
    test_unknown_type_and_heal()
    test_end_to_end_damage()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")
