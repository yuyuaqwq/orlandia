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

from ext_combat import Battle as B2, make_actor  # noqa: E402
from ext_combat.battle.landing import deal_damage  # noqa: E402
from ext_combat.battle.effects import apply_effects  # noqa: E402
from _engine_harness import boot as ensure_engine_configured  # noqa: E402

# 测试稳定性：屏蔽承伤侧的**闪避随机**（角色面板自带 ~3% dodge；本文件断言的是
# 减伤/护盾乘区数值，闪避未命中会让断言偶发失败）。格挡同理（block=0 时本就不 roll）。
import ext_combat.battle.landing as _LD  # noqa: E402
_LD._roll_dodge = lambda *a, **k: False  # noqa: E731


ensure_engine_configured()
from content.mech import team_procs as TP  # noqa: E402,F401  (import 即注册)  ★ B18-REPOINT：直取包内实现本体

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py
# ★ 收口第 2 批（2026-09-28）：护盾读口 = 容器条目（`effects` 里带 value 的那一条）。
from _container_shape import (sh_value_of, sh_of, shield_total,  # noqa: E402
                            shield_names, arm_shield, clear_shields)
from ext_combat.battle.state_effects import state_def  # noqa: E402

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")

EPS = 1e-6


def near(a, b, tol=EPS):
    try:
        return abs(float(a) - float(b)) <= tol
    except Exception:
        return False


def mk(uid, hp=2000, atk=200, spd=50, side="player", cls="cls_zhan_shi", lv=20):
    a = make_actor(uid=uid, name=uid, side=side, kind="player" if side == "player" else "monster",
                   human_controlled=(side == "player"), class_name=cls if side == "player" else None,
                   level=lv, hp=hp, max_hp=hp, mp=200, max_mp=200,
                   atk=atk, matk=150, spd=spd, crit=0.05,
                   equipment={}, skills=[], learned_skills=[],
                   race=None, evolve_path=0, class_tier=0, attributes={},
                   **{"def": 20, "mdef": 20})
    a["effects"] = {}
    # ★ 收口第 2 批：独立容器 `shields` 已删（护盾 = effects 容器里带 value 的条目）
    return a


def mk_boss(hp=99999):
    e = make_actor(uid="boss", name="木桩", side="enemy", kind="monster",
                   hp=hp, max_hp=hp, atk=100, matk=100, spd=50, crit=0.0,
                   level=20, exp=0, gold=0, **{"def": 0, "mdef": 0})
    e["effects"] = {}
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
    """★ 收口第 2 批：护盾总和改读**容器条目**（absorb 族 value 之和）。"""
    return shield_total(a)


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
    # 更严：条目形状 + 到期 + 可吸收（原版只判 sums 数字）
    check("全队都拿到容器条目 shield（带 value + expire=12）",
          all(sh_of(a, "shield").get("value") == 500
              and near(sh_of(a, "shield").get("expire"), 12.0) for a in allies),
          f"efs={[ {k: v for k, v in (a.get('effects') or {}).items()} for a in allies ]}")
    check("全队盾都在吸收族里（absorb_keys 查得到）",
          all(shield_names(a) == ["shield"] for a in allies),
          f"names={[shield_names(a) for a in allies]}")
    check("★ 护盾不再写独立容器 shields",
          all("shields" not in a for a in allies), f"keys={[sorted(a) for a in allies]}")

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
    # 更严：不是「有条目但 value=0」，而是容器里连条目都没有
    check("缺字段 → 容器里无盾条目（非 value=0 空壳）",
          all("shield" not in (a.get("effects") or {}) for a in allies5),
          f"efs={[a.get('effects') for a in allies5]}")

    # 按属性基数（相位偏折：每层 8% 魔攻）——期望值从引擎聚合面板现算（勿手算）
    from ext_combat.battle import stats as _S
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
    # 更严：self_shield 走的是**自带 key** arcane_shield（不是通用 shield），到期 10
    check("self_shield 落在自带 key arcane_shield（expire=10）",
          sh_of(p6, "arcane_shield").get("value") == expect
          and near(sh_of(p6, "arcane_shield").get("expire"), 10.0)
          and shield_names(p6) == ["arcane_shield"],
          f"sh={sh_of(p6, 'arcane_shield')} names={shield_names(p6)}")

    # 怪物盾回归：技能完全没声明 shield_* 时，仍用引擎传入的默认 20%（旧行为不破）
    # ★ 收口第 2 批：这条同时钉「**没声明 absorb 的条目不会吸**」——
    #   引擎 `act_shield` 的缺省 key 是 `buff`，若 `effect_rules.json` 没给
    #   `buff` 声明 `absorb: true`，这条盾就是「不掉的血」（值写得对、机制没跑）。
    b7, p7, _, e7 = team_battle(1)
    cast(b7, e7, "shield", {"name": "潮涌领域"}, turns=10, pct=0.20, halve=True)
    _want = int(99999 * 0.20)
    _ef = (e7.get("effects") or {})
    check("怪物盾（无 shield_* 声明）仍得 20% 生命护盾（值写进容器条目）",
          _want in [int(v.get("value") or 0) for v in _ef.values() if isinstance(v, dict)],
          f"want={_want} ef={_ef}")
    check("★ 怪物盾真吸收（200 全被盾吸走）——absorb 声明缺失会让盾变成不掉的血",
          deal_damage(b7, None, e7, 200, [], dmg_kind="true", no_dodge=True) == 0,
          f"ef={e7.get('effects')} absorb={shield_names(e7)}"
          f" state_def({sorted(_ef)})={[state_def(k) for k in _ef]}")


def test_shield_strict():
    print("【2b. 护盾真吸收 + 同源叠厚 + 容器到期（收口第 2 批新形状）】")
    from ext_combat.battle import schedule as SC
    # ---- 真吸收：盾真的挡伤害、值真递减、归零即从容器删 ----
    b, p, allies, e = team_battle(2)
    cast(b, p, "shield_all", {"name": "固定盾", "shield_value": 500}, turns=12)
    a1 = allies[1]
    a1["hp"] = a1["max_hp"]
    d = deal_damage(b, e, a1, 300, [], dmg_kind="true", no_dodge=True)
    check("打 300 → 全被盾吸收（0 扣血）", d == 0 and a1["hp"] == a1["max_hp"],
          f"d={d} hp={a1['hp']}")
    check("吸收后盾值精确递减 500 → 200", sh_value_of(a1, "shield") == 200,
          f"sh={sh_of(a1, 'shield')}")
    d = deal_damage(b, e, a1, 300, [], dmg_kind="true", no_dodge=True)
    check("打穿：200 吸满 + 100 落血", d == 100 and a1["hp"] == a1["max_hp"] - 100,
          f"d={d} hp={a1['hp']}")
    check("★ 归零即从容器删（不留 value=0 空壳）",
          "shield" not in (a1.get("effects") or {}) and shield_total(a1) == 0,
          f"ef={a1.get('effects')}")
    check("同源两队友各自独立（各扣各的）",
          sh_value_of(allies[0], "shield") == 500 and shield_total(a1) == 0,
          f"p={sh_of(allies[0], 'shield')} a1={a1.get('effects')}")

    # ---- 同源叠厚：同 key 再敲一次 = value 累加 + expire 取 max（不是覆盖）----
    b2, p2, allies2, _ = team_battle(1)
    cast(b2, p2, "shield_all", {"name": "固定盾", "shield_value": 500}, turns=12)
    cast(b2, p2, "shield_all", {"name": "固定盾", "shield_value": 500}, turns=4)
    sh = sh_of(p2, "shield")
    check("同源叠厚：500+500=1000（value 累加，不是覆盖）", sh_value_of(p2, "shield") == 1000,
          f"sh={sh}")
    check("叠厚时 expire 取 max（12 刻那次更晚 ⇒ 仍 12，不被 4 刻那次拉低）",
          near(sh.get("expire"), 12.0), f"expire={sh.get('expire')}")
    check("叠厚不叠层数（stacks 仍 1）", sh.get("stacks") == 1, f"sh={sh}")

    # ---- 到期：走容器 expire 那一条通路（旧容器已无独立到期段）----
    b3, p3, allies3, _ = team_battle(1)
    cast(b3, p3, "shield_all", {"name": "固定盾", "shield_value": 500}, turns=3)
    exp = float(sh_of(p3, "shield").get("expire") or 0)
    check("先决：到期刻存在（turns 3 → expire=3）", near(exp, 3.0), f"expire={exp}")
    b3._now = exp + 0.1
    SC._settle_time_effects(b3, [])
    check("★ 过期后容器自动清理（到期走容器 expire，不靠旧容器独立到期段）",
          "shield" not in (p3.get("effects") or {}) and shield_total(p3) == 0,
          f"ef={p3.get('effects')}")

    # ---- 反证：absorb 声明摘掉 ⇒ 同一条目不再被吸收（吸收与否只由内容侧声明决定）----
    from _container_shape import _absorb_off
    b4, p4, allies4, e4 = team_battle(1)
    cast(b4, p4, "shield_all", {"name": "固定盾", "shield_value": 500}, turns=12)
    a4 = allies4[0]
    a4["hp"] = a4["max_hp"]
    with _absorb_off("shield"):
        d = deal_damage(b4, None, a4, 200, [], dmg_kind="true", no_dodge=True)
    check("反证：摘掉 absorb 声明 → 200 全落血、盾值分毫不动",
          d == 200 and a4["hp"] == a4["max_hp"] - 200 and sh_value_of(a4, "shield") == 500,
          f"d={d} hp={a4['hp']} sh={sh_of(a4, 'shield')}")
    check("反证期间条目仍在容器里（不吸收 ≠ 删条目）",
          "shield" in (a4.get("effects") or {}), f"ef={a4.get('effects')}")
    d = deal_damage(b4, None, a4, 200, [], dmg_kind="true", no_dodge=True)
    check("声明恢复 → 同一笔又被吸收（500 吸满 + 0 落血）",
          d == 0 and a4["hp"] == a4["max_hp"] - 200 and sh_value_of(a4, "shield") == 300,
          f"d={d} hp={a4['hp']} sh={sh_of(a4, 'shield')}")


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
    from ext_combat.battle import schedule as SC
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
    from ext_combat.battle import schedule as SC
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

    from ext_combat.battle import schedule as SC
    b._now = 100.0
    SC._settle_time_effects(b, [])
    apply_effects(b, e, p, [{"type": "apply", "key": "stun", "mode": "skip", "turns": 3,
                             "on": "target"}], [])
    check("免疫过期后控制恢复落地", bool((p.get("effects") or {}).get("stun")))


def test_do_buff_e2e():
    print("【8. 端到端：引擎增益管线 _do_buff 真跑】")
    from ext_combat.battle.actions import _do_buff
    from ext_combat.battle.actors import ActCtx

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
    from ext_combat.battle import schedule as SC
    from ext_combat.battle.effect_triggers import fire as _fire
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
    from ext_combat.battle import stats as _S
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
    test_shield_strict()
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
