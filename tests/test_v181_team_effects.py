# -*- coding: utf-8 -*-
"""v181 团队/全队效果实装验收（2026-09-11）：content/mech/team_procs.py（★ B18-REPOINT 后
宿主同名壳已退役，本测试的观测对象 = 包内实现本体）。

## 覆盖

1. **团队面幅**：多人同侧 → 全队生效（修复前只作用施法者）；单人 = 自己
2. **护盾三形态**：固定值 / 生命上限百分比 / 按资源层数递增（按**施法者**生命算）
3. **减伤乘算叠加**（鱼鱼拍板「叠加」）：不同技能各自一条态 → ×0.8×0.85 = 68%
   （同一技能重复施放 = 刷新刻数，不重复叠乘）
4. **减伤刻数过期**：态到期后不再减伤（引擎 effects 自动清理）
5. **易伤**：目标受到伤害 ×1.25（含过期）
6. **全队伤害乘区**：按伤害类型过滤（魔法） / 按目标标记过滤（猎印）
7. **免疫控制**：引擎控制落地前查询 `cc_immune` 态（含过期）
8. **零默认值铁律**：缺字段 = 无行为
9. **端到端**：走 `actions._do_buff`（引擎增益管线）真跑一个全队护盾技能

跑法：python tests/test_v181_team_effects.py
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_b2_team.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import Battle as B2, make_actor  # noqa: E402
from saintess_engine.battle.landing import deal_damage  # noqa: E402
from saintess_engine.battle.effects import apply_effects  # noqa: E402
from _engine_harness import boot as ensure_engine_configured  # noqa: E402

# 测试稳定性：屏蔽承伤侧的**闪避随机**（角色面板自带 ~3% dodge；本文件断言的是
# 减伤/护盾乘区数值，闪避未命中会让断言偶发失败）。格挡同理（block=0 时本就不 roll）。
import saintess_engine.battle.landing as _LD  # noqa: E402
_LD._roll_dodge = lambda *a, **k: False  # noqa: E731


ensure_engine_configured()
from content.mech import team_procs as TP  # noqa: E402,F401  (import 即注册)  ★ B18-REPOINT：直取包内实现本体

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


def mk(uid, hp=2000, atk=200, spd=50, side="player", cls="cls_zhan_shi", lv=20):
    a = make_actor(uid=uid, name=uid, side=side, kind="player" if side == "player" else "monster",
                   human_controlled=(side == "player"), class_name=cls if side == "player" else None,
                   level=lv, hp=hp, max_hp=hp, mp=200, max_mp=200,
                   atk=atk, matk=150, spd=spd, crit=0.05,
                   equipment={}, skills=[], learned_skills=[],
                   race=None, evolve_path=0, class_tier=0, attributes={},
                   **{"def": 20, "mdef": 20})
    a["effects"] = {}
    a["shields"] = {}
    return a


def mk_boss(hp=99999):
    e = make_actor(uid="boss", name="木桩", side="enemy", kind="monster",
                   hp=hp, max_hp=hp, atk=100, matk=100, spd=50, crit=0.0,
                   level=20, exp=0, gold=0, **{"def": 0, "mdef": 0})
    e["effects"] = {}
    e["shields"] = {}
    return e


def team_battle(n_ally=2):
    p = mk("p1")
    allies = [p] + [mk(f"a{i}") for i in range(1, n_ally)]
    e = mk_boss()
    b = B2(btype="monster", sides={"player": allies, "enemy": [e]})
    return b, p, allies, e


def cast(b, caster, effect, info=None, turns=12, **extra):
    """模拟引擎增益管线调起一个 effect 名词（等价 _do_buff 的调用形态）。"""
    logs = []
    eff = {"type": effect, "turns": turns, "info": dict(info or {})}
    eff.update(extra)
    apply_effects(b, caster, caster, [eff], logs)
    return logs


def hit(b, source, target, amount=1000):
    """打一下（打前补满血——否则实际扣血被 hp 截断，断言失真）。"""
    try:
        target["hp"] = int(target.get("max_hp", 1) or 1)
    except Exception:
        pass
    return deal_damage(b, source, target, amount, [], dmg_kind="phys")


def shield_sum(a):
    tot = 0
    for v in (a.get("shields") or {}).values():
        tot += int((v or {}).get("value", 0) or 0)
    return tot


# ------------------------------------------------------------
def test_team_scope():
    print("【1. 团队面幅（修复前只作用施法者）】")
    b, p, allies, e = team_battle(3)
    cast(b, p, "atk_all", {"name": "战意激荡"}, turns=10)
    has = [bool((a.get("effects") or {}).get("atk_up")) for a in allies]
    check("3 人同侧 → 3 人都拿到 atk_up（含施法者）", all(has), f"has={has}")
    check("面幅不越阵营（敌方无增益）", not (e.get("effects") or {}).get("atk_up"))

    b2, p2, _, _ = team_battle(1)
    cast(b2, p2, "atk_all", {"name": "战意激荡"}, turns=10)
    check("单人 = 自己（旧行为不破）", bool((p2.get("effects") or {}).get("atk_up")))

    b3, p3, allies3, _ = team_battle(2)
    cast(b3, p3, "all_stat_cc", {"name": "永恒赞歌"}, turns=8)
    keys = ["all_up_atk", "all_up_def", "all_up_matk", "all_up_spd", "all_up_crit", "cc_immune"]
    ok3 = all(all((a.get("effects") or {}).get(k) for k in keys) for a in allies3)
    check("永恒赞歌：全队 5 维增益 + 免疫控制（6 键齐）", ok3)


def test_shield():
    print("【2. 护盾三形态】")
    b, p, allies, _ = team_battle(2)
    cast(b, p, "shield_all", {"name": "固定盾", "shield_value": 500}, turns=12)
    check("固定值 500 → 全队各 500", all(shield_sum(a) == 500 for a in allies),
          f"sums={[shield_sum(a) for a in allies]}")

    b2, p2, allies2, _ = team_battle(2)
    allies2[1]["max_hp"] = 4000
    allies2[1]["hp"] = 4000
    cast(b2, p2, "shield_all", {"name": "百分比盾", "shield_pct": 0.20}, turns=12)
    check("施法者 hp=2000 ×20% = 400 → 全队都 400（含 hp 4000 的队友）",
          all(shield_sum(a) == 400 for a in allies2),
          f"sums={[shield_sum(a) for a in allies2]}")

    b3, p3, allies3, _ = team_battle(2)
    cast(b3, p3, "shield_all",
         {"name": "坚盾壁垒", "shield_per_stack": 0.06, "shield_stacks": 5}, turns=12)
    check("5 层 × 6% × 2000 = 600", all(shield_sum(a) == 600 for a in allies3),
          f"sums={[shield_sum(a) for a in allies3]}")

    b4, p4, allies4, _ = team_battle(2)
    p4["effects"]["zhan_yi"] = {"stacks": 10}
    cast(b4, p4, "shield_all",
         {"name": "圣盾", "shield_per_stack": 0.06, "shield_res_key": "zhan_yi"}, turns=12)
    check("战意 10 层 × 6% × 2000 = 1200（读资源现值）",
          all(shield_sum(a) == 1200 for a in allies4), f"sums={[shield_sum(a) for a in allies4]}")

    b5, p5, allies5, _ = team_battle(2)
    cast(b5, p5, "shield_all", {"name": "无参数盾"}, turns=12)
    check("缺字段 = 无行为（不给默认盾）", all(shield_sum(a) == 0 for a in allies5))

    # 按属性基数（相位偏折：每层 8% 魔攻）——期望值从引擎聚合面板现算（勿手算）
    from saintess_engine import stats as _S
    b6, p6, allies6, _ = team_battle(2)
    for a in allies6:
        a["effects"]["arcane"] = {"stacks": 5}
    _matk = float((_S.actor_stats(b6, p6) or {}).get("matk", 0) or 0)
    expect = int(_matk * 0.40)      # 5 层 × 8% = 40% 魔攻
    cast(b6, p6, "arcane_shield",
         {"name": "相位偏折", "shield_per_stack": 0.08, "shield_res_key": "arcane",
          "shield_base_stat": "matk"}, turns=10)
    check(f"自身盾按魔攻：{_matk:.0f} × 40% = {expect}（self_shield 只作用自己）",
          shield_sum(p6) == expect and shield_sum(allies6[1]) == 0,
          f"self={shield_sum(p6)} expect={expect} ally={shield_sum(allies6[1])}")

    # 怪物盾回归：技能完全没声明 shield_* 时，仍用引擎传入的默认 20%（旧行为不破）
    b7, p7, _, e7 = team_battle(1)
    cast(b7, e7, "shield", {"name": "潮涌领域"}, turns=10, pct=0.20, halve=True)
    check("怪物盾（无 shield_* 声明）仍得 20% 生命护盾（旧行为不破）",
          shield_sum(e7) == int(99999 * 0.20), f"got={shield_sum(e7)}")


def test_reduce_stack():
    print("【3. 全队减伤：乘算叠加（鱼鱼拍板）】")
    b, p, allies, e = team_battle(2)
    check("无减伤基线 = 1000", hit(b, e, p) == 1000)

    cast(b, p, "reduce_all", {"name": "战吼·守", "reduce": 0.20}, turns=10)
    check("单来源 20% → 800", hit(b, e, p) == 800, f"got={hit(b, e, p)}")
    check("全队都吃到（队友同样减伤）", hit(b, e, allies[1]) == 800)

    # 第二个来源 = 不同技能（不同标签）→ 叠加
    cast(b, p, "reduce_all", {"name": "死歌·悼", "reduce": 0.15}, turns=12)
    both = hit(b, e, p)
    check("20% + 15%（不同技能）乘算 → 1000×0.8×0.85 = 680", both == 680, f"got={both}")
    check("两条态并存（各自一条）",
          len([k for k in (p.get("effects") or {}) if k.startswith("team:reduce:")]) == 2,
          f"keys={list((p.get('effects') or {}).keys())}")

    # 同一技能重复施放 = 刷新，不重复叠乘
    cast(b, p, "reduce_all", {"name": "战吼·守", "reduce": 0.20}, turns=10)
    check("同技能重复施放不叠乘（刷新刻数）", hit(b, e, p) == 680, f"got={hit(b, e, p)}")


def test_reduce_expire():
    print("【4. 减伤刻数过期】")
    b, p, allies, e = team_battle(2)
    cast(b, p, "reduce_all", {"name": "战吼·守", "reduce": 0.50}, turns=3)
    check("生效期 1000→500", hit(b, e, p) == 500)
    from saintess_engine.battle import schedule as SC
    b._now = 10.0
    SC._settle_time_effects(b, [])
    check("态已被引擎清理（effects 无 team:reduce:*）",
          not [k for k in (p.get("effects") or {}) if k.startswith("team:reduce:")],
          f"ef={list((p.get('effects') or {}).keys())}")
    check("过期后伤害回到 1000", hit(b, e, p) == 1000)


def test_vuln():
    print("【5. 目标易伤】")
    b, p, allies, e = team_battle(2)
    apply_effects(b, p, e, [{"type": "vuln", "turns": 8,
                             "info": {"name": "死亡标记", "vuln_amp": 0.25}}], [])
    check("写态 team:vuln:死亡标记（挂在目标身上）",
          any(k.startswith("team:vuln:") for k in (e.get("effects") or {})),
          f"ef={list((e.get('effects') or {}).keys())}")
    check("目标受到伤害 ×1.25 → 1250", hit(b, p, e) == 1250, f"got={hit(b, p, e)}")
    from saintess_engine.battle import schedule as SC
    b._now = 100.0
    SC._settle_time_effects(b, [])
    check("过期后回到 1000", hit(b, p, e) == 1000)


def test_dmg_aura():
    print("【6. 全队伤害乘区（按类型 / 按标记过滤）】")
    b, p, allies, e = team_battle(2)
    cast(b, p, "arcane_matrix",
         {"name": "奥术矩阵", "aura_kind": ["魔法"], "aura_add": 0.20}, turns=12)
    check("全队都挂了 aura 触发器（面幅）",
          all(any(t.get("action") == "team_dmg_aura_apply"
                  for t in ((a.get("triggers") or {}).get("dmg_calc") or [])) for a in allies))
    check("态在（aura key）", any(k.startswith("team:aura:") for k in (p.get("effects") or {})))

    # 条件过滤：只对目标带标记时生效（猎印）
    b2, p2, allies2, e2 = team_battle(2)
    cast(b2, p2, "hunt_team_dmg",
         {"name": "猎杀时刻", "aura_mark": "hunt_mark", "aura_add": 0.30}, turns=12)
    trig = ((p2.get("triggers") or {}).get("dmg_calc") or [])
    t0 = next((t for t in trig if t.get("action") == "team_dmg_aura_apply"), {})
    check("触发器带足条件（aura_mark + add）", t0.get("aura_mark") == "hunt_mark" and t0.get("add") == 0.30,
          f"t={t0}")


def test_cc_immune():
    print("【7. 免疫控制（引擎控制落地查询点）】")
    b, p, allies, e = team_battle(2)
    apply_effects(b, e, p, [{"type": "apply", "key": "stun", "mode": "skip", "turns": 3,
                             "on": "target"}], [])
    check("无免疫：stun 落地", bool((p.get("effects") or {}).get("stun")),
          f"ef={list((p.get('effects') or {}).keys())}")
    p["effects"].pop("stun", None)

    cast(b, p, "all_stat_cc", {"name": "永恒赞歌"}, turns=8)
    logs = []
    apply_effects(b, e, p, [{"type": "apply", "key": "stun", "mode": "skip", "turns": 3,
                             "on": "target"}], logs)
    check("有免疫：stun 被拦下（不写态）", not (p.get("effects") or {}).get("stun"),
          f"ef={list((p.get('effects') or {}).keys())} logs={logs}")
    check("队友同样免疫", not (allies[1].get("effects") or {}).get("stun"))

    from saintess_engine.battle import schedule as SC
    b._now = 100.0
    SC._settle_time_effects(b, [])
    apply_effects(b, e, p, [{"type": "apply", "key": "stun", "mode": "skip", "turns": 3,
                             "on": "target"}], [])
    check("免疫过期后控制恢复落地", bool((p.get("effects") or {}).get("stun")))


def test_do_buff_e2e():
    print("【8. 端到端：引擎增益管线 _do_buff 真跑】")
    from saintess_engine.battle.actions import _do_buff
    from saintess_engine.battle.actors import ActCtx

    b, p, allies, _ = team_battle(2)
    info = {"name": "坚盾壁垒", "effect": "shield_all", "kind": "增益",
            "buff_turns": 12, "shield_per_stack": 0.06, "shield_stacks": 5}
    ctx = ActCtx(caster=p, action="skill", skill_name="坚盾壁垒", info=info)
    logs = []
    _do_buff(b, ctx, p, info, logs)
    check("_do_buff 调起 team_shield → 全队各 600 盾",
          all(shield_sum(a) == 600 for a in allies),
          f"sums={[shield_sum(a) for a in allies]} logs={logs}")




def test_guard():
    print("【9. 挡刀（protect：承伤转移 + 反伤 + 到期清）】")
    b, p, allies, e = team_battle(2)
    a1 = allies[1]
    cast(b, p, "protect", {"name": "誓约之盾", "reflect_pct": 0.30}, turns=12)
    check("队友身上写了 guard_uid（指向施法者）", a1.get("guard_uid") == p.get("uid"),
          f"guard={a1.get('guard_uid')} p={p.get('uid')}")
    check("施法者自身不被自己挡（无 guard_uid）", not p.get("guard_uid"))

    before_p, before_a = p["hp"], a1["hp"]
    d = hit(b, e, a1, 1000)          # 打被保护的队友
    check("伤害转移到保护者：队友不掉血", a1["hp"] == before_a, f"a1 {before_a}->{a1['hp']}")
    check("保护者承受 1000（含 AOE 前的等级压制同口径）", p["hp"] == before_p - 1000,
          f"p {before_p}->{p['hp']} d={d}")

    # 反伤：保护者受击（挡刀期间）→ 攻击者掉血
    ehp = e["hp"]
    hit_ret = deal_damage(b, e, p, 500, [], dmg_kind="phys")
    check("保护者受击触发反伤（攻击者掉血）", e["hp"] < ehp,
          f"boss {ehp}->{e['hp']}")

    # 到期清理 guard_uid
    from saintess_engine.battle import schedule as SC
    from saintess_engine.battle.effect_triggers import fire as _fire
    b._now = 100.0
    SC._settle_time_effects(b, [])
    _fire(b, "time_advance", {"actor": a1, "dt": 1.0, "now": 100.0}, [])
    check("挡刀到期：guard_uid 被清除", not a1.get("guard_uid"), f"guard={a1.get('guard_uid')}")
    # 到期后伤害回到队友身上（独立战场，避免同场累计状态干扰）
    b2, p2, allies2, e2 = team_battle(2)
    a2 = allies2[1]
    cast(b2, p2, "protect", {"name": "誓约之盾", "reflect_pct": 0.30}, turns=1)
    b2._now = 50.0
    SC._settle_time_effects(b2, [])
    _fire(b2, "time_advance", {"actor": a2, "dt": 1.0, "now": 50.0}, [])
    check("挡刀到期：自己承伤（无转移）", not a2.get("guard_uid"))
    d2 = hit(b2, e2, a2, 1000)
    check("到期后伤害回到队友身上（2000 - 1000 = 1000）", a2["hp"] == 1000 and d2 == 1000,
          f"a2.hp={a2['hp']} d2={d2}")


def test_block():
    print("【10. 格挡 1 次 + 反伤（block_reflect：铁山靠）】")
    b, p, allies, e = team_battle(2)
    cast(b, p, "block_reflect", {"name": "铁山靠", "reflect_pct": 0.40}, turns=8)
    check("格挡态写入", any(k.startswith("team:block:") for k in (p.get("effects") or {})),
          f"ef={list((p.get('effects') or {}).keys())}")
    ehp = e["hp"]
    d = deal_damage(b, e, p, 1000, [], dmg_kind="phys")
    check("格挡：本次承伤归零（引擎 clamp 到 1）", d == 1, f"d={d}")
    check("反伤 40% → 攻击者掉 400", e["hp"] == ehp - 400, f"boss {ehp}->{e['hp']}")
    check("格挡态被消耗（1 次性）",
          not any(k.startswith("team:block:") for k in (p.get("effects") or {})),
          f"ef={list((p.get('effects') or {}).keys())}")
    # 第二次不再格挡
    ehp2 = e["hp"]
    d2 = deal_damage(b, e, p, 1000, [], dmg_kind="phys")
    check("第二次不格挡（正常吃 1000）", d2 == 1000, f"d2={d2}")


def test_element_and_field():
    print("【11. 元素流转 / 奥术力场】")
    b, p, allies, e = team_battle(2)
    cast(b, p, "element_switch", {"name": "元素流转"}, turns=4)
    check("主系落到 actor（首个 = cycle[0]）", p.get("cur_element") == "fire",
          f"cur={p.get('cur_element')}")
    cast(b, p, "element_switch", {"name": "元素流转"}, turns=4)
    check("再次切换轮转 → ice", p.get("cur_element") == "ice", f"cur={p.get('cur_element')}")

    # 奥术力场（护盾档）
    b2, p2, allies2, _ = team_battle(2)
    p2["effects"]["arcane"] = {"stacks": 5}
    from saintess_engine import stats as _S
    cast(b2, p2, "arcane_field",
         {"name": "奥术力场", "shield_per_stack": 0.08, "shield_res_key": "arcane",
          "shield_base_stat": "matk"}, turns=10)
    # 2026-09-11 行为变更：奥术力场现在**消耗 2 点充能**（desc「消耗 2 点充能」），
    #   盾值按消耗后剩余层数 × 8% × 当前面板魔攻（消耗会实时改面板，故现算）
    _left = float((p2["effects"].get("arcane") or {}).get("stacks", 0) or 0)
    _matk = float((_S.actor_stats(b2, p2) or {}).get("matk", 0) or 0)
    _expect = int(_matk * (_left * 0.08))
    check(f"奥术力场 → 护盾档（{_matk:.0f} × {_left:g}层×8% = {_expect}）",
          shield_sum(p2) == _expect, f"got={shield_sum(p2)} expect={_expect}")


if __name__ == "__main__":
    test_team_scope()
    test_shield()
    test_reduce_stack()
    test_reduce_expire()
    test_vuln()
    test_dmg_aura()
    test_cc_immune()
    test_do_buff_e2e()
    test_guard()
    test_block()
    test_element_and_field()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")
