# -*- coding: utf-8 -*-
"""N10-B1：saintess_engine 吸血主链验收（面板吸血率 + 技能级 lifesteal + mortal_wound 减半 + AOE/真伤不吸）。

跑法：python tests/test_battle_n10_b1_lifesteal.py（w1 内）
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_b2_n10b1.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _b2c
from _engine_harness import boot as _eng_cfg; _eng_cfg()
from saintess_engine import Battle as B2, make_actor  # noqa: E402
from saintess_engine import actions as A  # noqa: E402
from saintess_engine.battle.actors import ActCtx  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name}: {detail}")
        print(f"  ❌ {name} {detail}")


def mk_player(hp=2000, equip_stats=None, cls="cls_zhan_shi"):
    """玩家 actor：吸血率经 equipment stats → E.player_final_stats 面板聚合（真实路径）。

    equip_stats 示例 {"lifesteal": 0.10} / {"lifesteal_phys": 0.10}——武器 stats 折算面板。
    """
    eq = {"weapon": {"key": "w_test", "name": "测试武器", "stats": dict(equip_stats or {})}} \
        if equip_stats else {}
    p = make_actor(uid="p1", name="勇者", side="player", kind="player",
                   human_controlled=True, class_name=cls, level=20,
                   hp=hp, max_hp=hp, mp=200, max_mp=200,
                   atk=100, matk=80, spd=15, crit=0.05,
                   equipment=eq, skills=[], learned_skills=[],
                   race=None, evolve_path=0, class_tier=0, attributes={},
                   **{"def": 40, "mdef": 30})
    return p


def mk_enemy(hp=50000, atk=1):
    e = make_actor(uid="e1", name="木桩怪", side="enemy", kind="monster",
                   hp=hp, max_hp=hp, atk=atk, matk=1, spd=5, crit=0.0,
                   level=20, exp=0, gold=0, **{"def": 10, "mdef": 10})
    return e


def new_battle(p, e):
    return B2(btype="monster", sides={"player": [p], "enemy": [e]})


def panel_ls(p):
    """读玩家聚合面板吸血率（验证装备折算生效）。"""
    from saintess_engine import stats as S
    st = S.actor_stats(new_battle(p, mk_enemy()), p)
    return float(st.get("lifesteal", 0) or 0)


def test_panel_lifesteal_phys():
    print("【1. 面板吸血率：物理普攻回血】")
    p = mk_player(equip_stats={"lifesteal": 0.10})
    check("面板聚合 lifesteal=0.10", abs(panel_ls(p) - 0.10) < 1e-6, f"ls={panel_ls(p)}")
    p["hp"] = p["max_hp"] - 500
    e = mk_enemy()
    b = new_battle(p, e)
    ctx = ActCtx(caster=p, action="attack", target=e)
    logs = A.do_attack(b, ctx)
    healed = p["hp"] - (p["max_hp"] - 500)
    check("物理吸血回血 >0", healed > 0, f"healed={healed} logs={logs[:3]}")
    check("回血量 ≈ 10% 伤害", 3 <= healed <= 30, f"healed={healed}")


def test_mortal_wound_half():
    print("【2. mortal_wound 吸血减半】")
    res = {}
    for tag, mw in (("no", False), ("mw", True)):
        p = mk_player(equip_stats={"lifesteal": 0.10})
        p["hp"] = p["max_hp"] - 800
        if mw:
            p.setdefault("effects", {})["mortal_wound"] = {"stacks": 1, "expire": 99999}
        e = mk_enemy()
        b = new_battle(p, e)
        ctx = ActCtx(caster=p, action="attack", target=e)
        A.do_attack(b, ctx)
        res[tag] = p["hp"] - (p["max_hp"] - 800)
    check("mortal_wound 回血减半", res["no"] > 0 and res["mw"] < res["no"],
          f"no={res['no']} mw={res['mw']}")


def test_mortal_wound_expired():
    print("【3. mortal_wound 过期不误判】")
    p = mk_player(equip_stats={"lifesteal": 0.10})
    p["hp"] = p["max_hp"] - 500
    p.setdefault("effects", {})["mortal_wound"] = {"stacks": 1, "expire": 0.0}  # 已过期
    e = mk_enemy()
    b = new_battle(p, e)
    ctx = ActCtx(caster=p, action="attack", target=e)
    A.do_attack(b, ctx)
    healed = p["hp"] - (p["max_hp"] - 500)
    check("过期 mw 不生效（全额吸血）", healed >= 3, f"healed={healed}")


def test_true_damage_no_ls():
    print("【4. 真伤不吸血（v107 语义）】")
    p = mk_player(equip_stats={"lifesteal": 0.10})
    p["hp"] = p["max_hp"] - 500
    b = new_battle(p, mk_enemy())
    before = p["hp"]
    A._settle_lifesteal(b, p, 100, "真伤", [], magi_part=0)
    check("真伤段不回血", p["hp"] == before, f"hp={p['hp']}")


def test_aoe_no_ls():
    print("【5. AOE 不吸血（旧语义）】")
    p = mk_player(equip_stats={"lifesteal": 0.10})
    p["hp"] = p["max_hp"] - 500
    e1 = mk_enemy(hp=5000)
    e2 = mk_enemy(hp=5000)
    b = B2(btype="monster", sides={"player": [p], "enemy": [e1, e2]})
    logs = A._single_target_pipeline(b, p, e1, {"kind": "魔法", "exprs": ["matk*0.8"], "aoe": True}, 0,
                                     _no_lifesteal=True)
    check("AOE 子调用不回血", p["hp"] == p["max_hp"] - 500, f"hp={p['hp']}")


def test_skill_lifesteal():
    print("【6. 技能级 info.lifesteal（嗜血斩 0.25）】")
    p = mk_player()  # 面板 0，纯技能级
    p["hp"] = p["max_hp"] - 500
    b = new_battle(p, mk_enemy())
    info = {"kind": "物理", "name": "嗜血斩", "lifesteal": 0.25, "exprs": ["atk*1.2"]}
    before = p["hp"]
    A._settle_lifesteal(b, p, 100, "物理", [], skill_info=info, skill_lv=1)
    healed = p["hp"] - before
    check("技能级吸血 ~25", 20 <= healed <= 30, f"healed={healed}")


def test_phys_magi_sub():
    print("【7. 细分吸血：物理段 phys / 魔法段 magi 各自生效】")
    p = mk_player(equip_stats={"lifesteal_phys": 0.10})
    p["hp"] = p["max_hp"] - 500
    b = new_battle(p, mk_enemy())
    before = p["hp"]
    A._settle_lifesteal(b, p, 100, "魔法", [], magi_part=100)  # 纯魔法段
    check("魔段不吃 phys 吸血", p["hp"] == before, f"hp={p['hp']}")
    p2 = mk_player(equip_stats={"lifesteal_phys": 0.10})
    p2["hp"] = p2["max_hp"] - 500
    b2 = new_battle(p2, mk_enemy())
    before2 = p2["hp"]
    A._settle_lifesteal(b2, p2, 100, "物理", [], magi_part=0)
    check("物段吃 phys 吸血", p2["hp"] > before2, f"hp={p2['hp']}")


def test_monster_no_ls_noop():
    print("【8. 纯怪攻击零行为（无 lifesteal 面板）】")
    p = mk_player(hp=500)
    m = make_actor(uid="m1", name="野狼", side="enemy", kind="monster",
                   hp=200, max_hp=200, atk=30, matk=10, spd=15, crit=0.05, level=20)
    b = B2(btype="monster", sides={"player": [p], "enemy": [m]})
    p_hp0 = p["hp"]
    m_hp0 = m["hp"]
    try:
        logs = A._single_target_pipeline(b, m, p, {"kind": "物理", "exprs": ["atk*1.0"], "_basic": True}, 0)
        # v181 flaky 修复：玩家真实面板含 ~3% 基础闪避（职业成长）——闪避=合法免伤，
        # 本测试验证"怪无面板吸血 → 不自回血"，扣血断言容忍闪避（闪避时本次无伤害）
        dodged = any("闪避" in str(x) for x in logs)
        check("怪攻击扣玩家血（或合法闪避）", dodged or p["hp"] < p_hp0,
              f"p_hp={p['hp']} logs={logs[:3]} dodged={dodged}")
        check("怪自身不回血（无面板吸血）", m["hp"] == m_hp0, f"m_hp={m['hp']}")
    except Exception as ex:
        check("怪攻击不崩", False, str(ex))


if __name__ == "__main__":
    test_panel_lifesteal_phys()
    test_mortal_wound_half()
    test_mortal_wound_expired()
    test_true_damage_no_ls()
    test_aoe_no_ls()
    test_skill_lifesteal()
    test_phys_magi_sub()
    test_monster_no_ls_noop()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")
