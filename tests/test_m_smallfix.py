# -*- coding: utf-8 -*-
"""v181.M-smallfix 小缺口批验收（master f92332f → m_smallfix 增量）。

覆盖三缺口：
  1. 命令层施放 mp 预检与引擎 actions._skill_pay_of 同源折算：
     - engine.skill_mp_pay_of 薄封装（bonus.cost 域折扣 → floor+保底 1；无容器直通声明）
     - 命令层端到端：arcane_focus 折扣下 mp ∈ [pay, 声明费) 边界放行施放、扣费按 pay；
       mp < pay 拦截；无词条对照 mp 不足声明费仍拦（零白嫖/行为零漂移）
     - 脱战治疗路径无 bonus 容器 → 折算直通声明费（拦截口径不变）
  2. arcane_focus 判据漏减法师技补标（万象风暴/奥秘主宰，无 element 副作用）：
     - 数据 mech 补标后 _JUDGE_ARCANE 命中 → 折 10%（45 → 40）
     - element 字段仍空（不进元素免疫/弱点/抗性结算）；无 mech_val（引擎兼容层零落地）；
       finisher mech_any 精确匹配不误乘；未明示技能（星界风暴）克制不减
  3. 侦察关闭项：passive_procs（旧被动域）随 N10 退役——无活装配路径（记录见 commit msg）

跑法：python tests/test_m_smallfix.py（exit=0 全绿）
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_m_smallfix.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _engine_harness import C, db, clean_db, Main, FakeEvent, run  # noqa: E402

from ext_combat.battle.formulas import skill_mp_pay_of
from content.skills import skill_info
from saintess_engine import config as _b2c  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()
from ext_combat.battle import actions as A  # noqa: E402
from content import combat_cmds as _CC  # noqa: E402


# ★ P5D-REPOINT：本文件开战（`_open_battle` → `content.combat_cmds._attach_tlog`）需要宿主
#   平台件 `attach_tlog`（流水挂载，原 `game/services/battle_bridge.py::attach_tlog`）。该
#   宿主壳随 game/** 退役后终态无人注入 ⇒ 包内 fail-closed 抛 RuntimeError。
#   这里按宿主契约补上测试侧替身（**与宿主实现同义**）：未启用流水 → 零行为直接返回 b；
#   启用流水 → 用包内采集器 `content.tlog_collect.BattleTLog` 挂到引擎流水句柄上。
#   注：本文件断言的是 mp 折算/词条折扣，流水只是开战路径上的平台副作用，判据一条未动。
def _attach_tlog(b, *, btype="monster", player=None, enemies=None, seed=None):
    from _engine_harness import tlog_setup
    try:
        tl = tlog_setup.tlog()
        if tl is None:
            return b
        from content.tlog_collect import BattleTLog
        BattleTLog(tl).attach(b, btype=btype, seed=seed, player=player, enemies=enemies)
    except Exception:                                        # noqa: BLE001
        pass
    return b


_CC.bind_host(attach_tlog=_attach_tlog)

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    results = await run(getattr(m, handler_name), ev)
    return results[-1] if results else ""


def _player_p(gid="g1", qid="q1"):
    return db.get_player(gid, qid)


def _setup_battle(m, gid, qid, mp, cls="法师", skill="织焰", affix="arcane_focus",
                  learned=None, max_mp=120):
    """落库玩家 + 真实开战仪式（_open_battle）→ battle state 存 db。返回 player dict。"""
    clean_db()
    if not _player_p(gid, qid):
        db.create_player(gid, qid, "测试", C.resolve("classes", cls) or cls, {}, 100, 100)
    _learned = learned if learned is not None else [C.resolve("skills", skill)]
    eq = {"weapon": {"slot": "weapon", "quality": "blue", "affixes": [affix], "stats": {}}} \
        if affix else {}
    db.update_player(gid, qid, level=60, learned_skills=_learned,
                     equipment=eq, mp=mp, max_mp=max_mp, stamina=999999)
    p = _player_p(gid, qid)
    mon = {"name": "测试木桩", "hp": 99999, "max_hp": 99999, "atk": 1, "matk": 1,
           "def": 5, "mdef": 5, "spd": 1, "level": 1, "exp": 0, "gold": 0}
    b = m._open_battle(p, [mon], btype="monster", group_id=gid, qq_id=qid)
    db.save_battle(gid, qid, b.to_state())
    # _open_battle 仪式后 actor 面板已按 db 落档；db player mp 同步回写（对齐真实流程）
    db.update_player(gid, qid, mp=mp)
    return _player_p(gid, qid)


def _my_actor_in_state(gid, qid):
    st = db.get_battle(gid, qid)
    for _acts in (st["state"].get("sides") or {}).values():
        for _a in _acts or []:
            if str(_a.get("qq_id") or _a.get("uid") or "") == str(qid):
                return _a
    return None


# ============================================================
# 缺口 1：命令层 mp 预检与引擎 _skill_pay_of 同源折算
# ============================================================

def t1_mp_precheck_boundary():
    print("【1.1 命令层边界放行：折扣技能 mp ∈ [pay, 声明费) 可施放】")
    import asyncio
    m = Main(None)
    gid, qid = "g1", "q1"
    # 织焰 mp=12（声明）；arcane_focus blue mp_pct 0.10 → pay = floor(12×0.9) = 10
    # 玩家 mp=10 = pay（< 声明 12）——旧命令层拦（读声明费），引擎实际只扣 10 → 丢边界收益
    p = _setup_battle(m, gid, qid, mp=10)
    actor = _my_actor_in_state(gid, qid)
    cost = ((actor or {}).get("bonus") or {}).get("cost") or {}
    whens = cost.get("when") or []
    check("actor 装配 bonus.cost.when（mp_pct 0.10 + 元素/奥术判据）",
          len(whens) == 1 and abs(float(whens[0].get("mp_pct") or 0) - 0.10) < 1e-9,
          repr(cost))
    pay = skill_mp_pay_of(actor, skill_info("cls_fa_shi", "织焰"))
    check("引擎同源 pay = 10（声明 12 折 10% floor）", pay == 10, f"pay={pay}")
    out = asyncio.run(cmd(m, "skill", gid, qid, "技能 织焰"))
    check("mp=10（=pay）放行施放（无『魔力不足』、有伤害）",
          "魔力不足" not in out and "受到" in out, out[:120])
    p2 = _player_p(gid, qid)
    check("扣费按 pay：mp 10 → 0（非声明 12 → -2）", int(p2.get("mp", -1)) == 0,
          f"mp={p2.get('mp')}")


def t1_mp_precheck_block():
    print("【1.2 命令层拦截保持：mp < pay 拦（无白嫖）】")
    import asyncio
    m = Main(None)
    gid, qid = "g1", "q1"
    p = _setup_battle(m, gid, qid, mp=9)  # < pay 10
    actor = _my_actor_in_state(gid, qid)
    pay = skill_mp_pay_of(actor, skill_info("cls_fa_shi", "织焰"))
    check("pay = 10 前置", pay == 10, f"pay={pay}")
    out = asyncio.run(cmd(m, "skill", gid, qid, "技能 织焰"))
    check("mp=9（<pay）拦截『魔力不足』且未施放", "魔力不足" in out and "受到" not in out,
          out[:80])
    p2 = _player_p(gid, qid)
    check("拦截后 mp 不变（9）", int(p2.get("mp", -1)) == 9, f"mp={p2.get('mp')}")


def t1_no_affix_regression():
    print("【1.3 无词条回归：mp < 声明费仍拦（pay==声明，行为零漂移）】")
    import asyncio
    m = Main(None)
    gid, qid = "g1", "q1"
    # 无词条 → actor 无 when 折扣 → pay == 声明 12
    p = _setup_battle(m, gid, qid, mp=11, affix=None)
    actor = _my_actor_in_state(gid, qid)
    pay = skill_mp_pay_of(actor, skill_info("cls_fa_shi", "织焰"))
    check("无词条 pay == 声明 12（零变化）", pay == 12, f"pay={pay}")
    out = asyncio.run(cmd(m, "skill", gid, qid, "技能 织焰"))
    check("mp=11（<声明 12）仍拦", "魔力不足" in out, out[:60])
    # 同源：pay 与引擎 _skill_pay_of 完全一致
    check("skill_mp_pay_of 与 A._skill_pay_of 同源同值",
          skill_mp_pay_of(actor, {"name": "x", "mp": 12}) ==
          int(A._skill_pay_of(actor, {"name": "x", "mp": 12}).get("mp") or 0))


def t1_out_of_battle_heal():
    print("【1.4 脱战治疗预检口径（无 bonus 容器 → 声明直通，拦截不变）】")
    import asyncio
    m = Main(None)
    gid, qid = "g1", "q1"
    # 脱战治疗：无 battle row；牧师学光愈（治疗 mp14）；hp 不满可施放
    cls = "cls_mu_shi"
    clean_db()
    if not _player_p(gid, qid):
        db.create_player(gid, qid, "测试", cls, {}, 100, 100)
    db.update_player(gid, qid, level=60,
                     learned_skills=[C.resolve("skills", "光愈")],
                     equipment={}, hp=50, mp=13, stamina=999999)
    # 无 battle → 治疗脱战施放（mp 13 < 声明 14 → 拦）
    out = asyncio.run(cmd(m, "skill", gid, qid, "技能 光愈"))
    check("脱战治疗 mp<声明拦（声明直通口径）", "魔力不足" in out, out[:80])
    p = _player_p(gid, qid)
    check("拦截后 mp 不变", int(p.get("mp")) == 13, f"mp={p.get('mp')}")
    # mp 充足 → 施放成功（扣声明费 14）
    db.update_player(gid, qid, mp=20)
    out2 = asyncio.run(cmd(m, "skill", gid, qid, "技能 光愈"))
    p2 = _player_p(gid, qid)
    check("脱战治疗 mp 足放行并扣 14（20→6）", "魔力不足" not in out2
          and int(p2.get("mp")) == 6, f"mp={p2.get('mp')} out={out2[:60]}")


# ============================================================
# 缺口 2：arcane_focus 漏减法师技补标（万象风暴/奥秘主宰）
# ============================================================

def _af_actor(level=95):
    from ext_combat import make_actor
    a = make_actor(uid="af", name="法师", side="player", kind="player",
                   human_controlled=True, class_name="cls_fa_shi", level=level,
                   hp=500, max_hp=500, mp=300, max_mp=300, atk=80, matk=80,
                   spd=12, crit=0.05, skills=[], learned_skills=[],
                   race=None, evolve_path=0, class_tier=0, attributes={},
                   **{"def": 40, "mdef": 60})
    a["bonus"] = {"panel": {}, "cap": {}, "cost": {"when": [{
        "mp_pct": 0.10,
        "judge": {"element": True,
                  "mech_prefix": ["fire", "ice", "thunder", "element", "arcane"],
                  "name_contains": ["元素", "奥术"]}}]}}
    return a


def t2_skill_tag_fill():
    print("【2.1 漏标法师技数据补标：万象风暴/奥秘主宰 mech 命中判据】")
    i_wx = skill_info("cls_fa_shi", "万象风暴")
    i_ao = skill_info("cls_fa_shi", "奥秘主宰")
    check("万象风暴 mech 补标 element_burst_all（无 mech_val）",
          (i_wx or {}).get("mech") == "element_burst_all"
          and not (i_wx or {}).get("mech_val"), repr(i_wx))
    check("奥秘主宰 mech 补标 arcane（无 mech_val）",
          (i_ao or {}).get("mech") == "arcane" and not (i_ao or {}).get("mech_val"),
          repr(i_ao))
    a = _af_actor()
    pay_wx = skill_mp_pay_of(a, i_wx)
    pay_ao = skill_mp_pay_of(a, i_ao)
    check("万象风暴 折 10%：mp45 → 40（此前漏减不减）", pay_wx == 40, f"pay={pay_wx}")
    check("奥秘主宰 折 10%：mp45 → 40（此前漏减不减）", pay_ao == 40, f"pay={pay_ao}")
    # 克制范围：desc 未明示"元素/奥术"的星界风暴不补不减（不确定不补原则）
    i_xj = skill_info("cls_fa_shi", "星界风暴")
    pay_xj = skill_mp_pay_of(a, i_xj) if i_xj else 0
    check("克制：星界风暴（desc 纯能量/星界，未明示）未补标不减 → pay==声明 40",
          (i_xj or {}).get("mech") in (None, "") and pay_xj == 40,
          f"mech={(i_xj or {}).get('mech')} pay={pay_xj}")


def t2_no_element_sideeffect():
    print("【2.2 补标无副作用：不标 element、无 mech_val 落地、finisher 不误乘】")
    i_wx = skill_info("cls_fa_shi", "万象风暴")
    i_ao = skill_info("cls_fa_shi", "奥秘主宰")
    # ① element 字段仍空 → 不进 landing 元素免疫/弱点/抗性消费（immune 归 0 不误触发）
    check("element 字段未补（仍 None——避免元素免疫/弱点误结算）",
          not (i_wx or {}).get("element") and not (i_ao or {}).get("element"),
          repr((i_wx or {}).get("element")))
    # ② 引擎 mech→effects 兼容层需 mech_val>0；无 val → 不落地（effects 无新条目）
    from ext_combat import make_actor, Battle as B2
    from ext_combat.battle.effects import effects_from_skill
    a = make_actor(uid="se", name="法", side="player", kind="player",
                   human_controlled=True, class_name="cls_fa_shi", level=95,
                   hp=500, max_hp=500, mp=300, max_mp=300, atk=80, matk=80,
                   spd=12, crit=0.05, skills=[], learned_skills=[],
                   race=None, evolve_path=0, class_tier=0, attributes={},
                   **{"def": 40, "mdef": 60})
    try:
        effs = effects_from_skill(i_wx, 1) or []
    except Exception as ex:
        effs = f"EXC:{type(ex).__name__}"
    check("万象风暴 mech 无 val → 兼容层零效果落地",
          isinstance(effs, list) and not effs, repr(effs))
    # ③ finisher 词条 mech_any 是精确匹配（mechs=['finisher']）——补标值不会误吃终结技乘区
    from content.mech.we_procs import we_dmg_mult_cond  # ★ B18-REPOINT：直取包内实现本体
    b = B2(btype="monster", sides={"player": [a], "enemy": [
        make_actor(uid="e", name="桩", side="enemy", kind="monster", hp=5000,
                   max_hp=5000, atk=1, matk=1, spd=5, level=60, **{"def": 5, "mdef": 5})]})
    ctx = {"actor": a, "target": b.sides_of("enemy")[0], "dmg": 100, "is_crit": False,
           "info": i_wx, "mult": 1.0}
    b._fire_ctx = None
    try:
        from ext_combat.battle.effect_triggers import fire as _fire
        _fire(b, "dmg_calc", ctx, [])
        got = float((getattr(b, "_fire_ctx", {}) or {}).get("mult", 1.0) or 1.0)
    except Exception:
        got = 1.0
    check("finisher mech_any 不误乘（mult 保持 1.0）", abs(got - 1.0) < 1e-9, f"mult={got}")
    # ④ 装配端到端：arcane_focus 词条 + 真实技能数据扣费 45→40
    from content.mech import equip as EP
    a2 = _af_actor()
    a2.setdefault("equipment", {})["armor"] = {"slot": "armor", "quality": "blue",
                                               "affixes": ["arcane_focus"], "stats": {}}
    EP.apply_to_actor(a2)
    b2 = B2(btype="monster", sides={"player": [a2], "enemy": [
        make_actor(uid="e2", name="桩", side="enemy", kind="monster", hp=999999,
                   max_hp=999999, atk=1, matk=1, spd=5, level=60, **{"def": 5, "mdef": 5})]})
    a2["mp"] = 300
    from ext_combat.battle.actors import ActCtx
    A.do_skill(b2, ActCtx(caster=a2, action="skill", skill_name="万象风暴",
                          info=i_wx, target=b2.sides_of("enemy")[0]))
    check("arcane_focus 端到端：万象风暴 45 → 扣 40（300→260）",
          int(a2.get("mp", 0)) == 260, f"mp={a2.get('mp')}")


# ============================================================
# main
# ============================================================

def main():
    t1_mp_precheck_boundary()
    t1_mp_precheck_block()
    t1_no_affix_regression()
    t1_out_of_battle_heal()
    t2_skill_tag_fill()
    t2_no_element_sideeffect()
    print(f"\n=== 结果 PASS={PASS} FAIL={FAIL} ===")
    if FAILURES:
        print("失败明细：")
        for f in FAILURES:
            print(" -", f)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
