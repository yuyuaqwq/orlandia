# -*- coding: utf-8 -*-
"""批 D 验收（2026-09-11）：DOT 混合公式统一 + 连段必暴接线 + 总抗（dot_res）。

权威 = 游戏仓 `design/new_world/32_数值设计.md` §DOT_DEFS / 27 章 §七：

    每层每刻 = (atk×a + matk×m + max_hp×h×boss折扣) × 层数 × mult × (1−总抗)

本次把这条公式在**新引擎**里补齐（原新引擎只读 period.pct_max_hp，丢了 atk/matk 段与总抗段），
并让 4 个 DOT 的系数**生成自 DOT_DEFS**（单一字面源，杜绝「引擎/模拟器双源」再漂移）。

覆盖（任意一条变红 = 公式被改坏 / 双源复活 / 必暴接线失效）：
  1. 系数与 DOT_DEFS 一致（单一数值源）
  2. 施法者强度快照：毒=atk×0.8、灼烧=matk×0.6+0.5%、流血=atk×0.05+1.5%、腐蚀=atk×0.3+matk×0.2+1%
  3. 快照语义：伤害跟「挂毒的人」（换结算者不变）
  4. boss/精英折扣：pct 段 ×0.5；条目级 pct_boss 优先且不叠乘
  5. 单层上限 pct_cap
  6. 流血处决线（<30% 生命 ×2）
  7. 总抗 = min(resist_cap, dot_res + adapt) → ×(1−总抗)
  8. 真伤 DOT 不吃物免/魔免/格挡
  9. 零变化：无系数、无 resist_cap 的既有条目（如裂伤）行为不变
 10. `crit_at`：连段 ≥4 → 终结技必暴出手态（act_cast 先于伤害管线）

跑法：python tests/test_v181_batch_d_dot_formula.py（exit=0 全绿）
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_batch_d.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _b2c  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # noqa: E402
from ext_combat import Battle as B2, make_actor  # noqa: E402
from ext_combat.battle import game_config as EC  # noqa: E402   # 游戏配置取件面（第 7 批从引擎 config 搬来）
from ext_combat.battle.effects import apply_action  # noqa: E402
from ext_combat.battle.schedule import _settle_time_effects  # noqa: E402
from ext_combat.battle.actions import _consume_hit_buffs  # noqa: E402
from ext_combat.battle.stats import actor_stats  # noqa: E402
from ext_combat.battle.effect_triggers import fire  # noqa: E402
from content.mech.params import EFFECT_RULES  # noqa: E402
from content.catalog_legacy import DOT_DEFS  # ★ B16-W11d

PASS = 0
FAIL = 0
FAILURES = []
_TPL = {}


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def mk_pair(atk=100, matk=200, max_hp=10000, role="dps", hp=None):
    p = make_actor(uid="p1", name="施法者", side="player", kind="player",
                   human_controlled=True, class_name="cls_ci_ke", level=40,
                   hp=3000, max_hp=3000, mp=300, max_mp=300,
                   atk=atk, matk=matk, spd=20, crit=0.0, equipment={}, skills=[],
                   learned_skills=[], **{"def": 30, "mdef": 30})
    e = make_actor(uid="e1", name="木桩", side="enemy", kind="monster",
                   hp=hp if hp is not None else max_hp, max_hp=max_hp,
                   atk=10, matk=10, spd=10, crit=0.0, level=40, role=role,
                   **{"def": 10, "mdef": 10})
    e["effects"] = {}
    e["dodge"] = 0.0
    e["block"] = 0.0
    # ★ 2026-09-25（引擎审计 E3）：引擎**不再读** `is_boss` / `is_elite` 这些游戏字段，
    #   改读内容侧标签 `traits`，且「谁吃折扣」由数据声明（period.trait_tags ⇒ 本测试的
    #   夹具直接给标签）；`is_boss` / `is_elite` 仍照写（内容侧其它逻辑还在读它们）。
    if role == "boss":
        e["is_boss"] = True
        e["traits"] = ["boss"]
    elif role == "elite":
        e["is_elite"] = True
        e["traits"] = ["elite"]
    return p, e, B2(btype="monster", sides={"player": [p], "enemy": [e]})


def dot_tick(b, e):
    """跑一次 DOT 结算（首次登记下一跳，再推进 1 刻触发）→ 返回本刻伤害。"""
    hp0 = e["hp"]
    b._now = float(b._now or 0.0)
    _settle_time_effects(b, [])
    b._now = float(b._now) + 1.0
    _settle_time_effects(b, [])
    return hp0 - e["hp"]


def apply_dot(b, p, e, key, n=1, **entry_extra):
    apply_action(b, p, e, "apply", {"key": key, "op": "add", "amount": n, "on": "target"}, [])
    if entry_extra:
        e["effects"][key].update(entry_extra)


# ============================================================

def test_1_single_source():
    print("【1. 单一数值源：EFFECT_RULES 的 4 个 DOT 系数 = DOT_DEFS】")
    for k in ("poison", "burn", "bleed", "corros"):
        per = (EFFECT_RULES.get(k) or {}).get("period") or {}
        dd = DOT_DEFS.get(k) or {}
        ok = (abs(float(per.get("atk", 0)) - float(dd.get("atk", 0) or 0)) < 1e-9
              and abs(float(per.get("matk", 0)) - float(dd.get("matk", 0) or 0)) < 1e-9
              and abs(float(per.get("pct_max_hp", 0)) - float(dd.get("hp", 0) or 0)) < 1e-9)
        check(f"{k} period 系数 = DOT_DEFS（atk/matk/hp）", ok, f"period={per} defs={dd}")
    check("corros period 带 dmg_type=true（真伤）",
          ((EFFECT_RULES.get("corros") or {}).get("period") or {}).get("dmg_type") == "true", "")
    check("bleed period 带 double_low_hp_pct（处决线）",
          float(((EFFECT_RULES.get("bleed") or {}).get("period") or {})
                .get("double_low_hp_pct", 0)) == 0.30, "")


def test_2_coefficients():
    print("【2. 混合公式：系数段 × 施法者快照 + 百分比段】")
    # 快照取的是 **actor_stats 计算后的真实面板**（含职业成长/装备），不是裸字段——
    #   与旧引擎 `_actor_stats_of(source)` 同源。因此期望值 = 快照值 × 系数。
    p, e, b = mk_pair(atk=100, matk=200, max_hp=10000)
    apply_dot(b, p, e, "poison", 2)
    snap = (e["effects"].get("poison") or {}).get("src") or {}
    st = actor_stats(b, p)
    check("快照 = actor_stats 计算面板（非裸字段）",
          snap.get("atk") == int(st.get("atk", 0)), f"src={snap} st.atk={st.get('atk')}")
    d = dot_tick(b, e)
    check(f"毒 2 层：int({snap.get('atk')}×0.8×2) = {int(snap.get('atk',0)*0.8*2)}",
          d == int(snap.get("atk", 0) * 0.8 * 2), f"d={d}")

    # 灼烧 = matk×0.6 + max_hp×0.5%（pct 部分不受 pct_cap 影响：0.005 < 0.01）
    p, e, b = mk_pair(atk=100, matk=200, max_hp=10000)
    apply_dot(b, p, e, "burn", 2)
    snap = (e["effects"].get("burn") or {}).get("src") or {}
    exp = int(10000 * 0.005 * 2) + int(snap.get("matk", 0) * 0.6 * 2)
    d = dot_tick(b, e)
    check(f"灼烧 2 层：pct 段 100 + 系数段 int(matk×0.6×2) = {exp}", d == exp, f"d={d}")

    # 流血 = atk×0.05 + max_hp×1.5% → 但 pct 系数被 pct_cap 1% 压住（权威自身口径）
    p, e, b = mk_pair(atk=100, matk=200, max_hp=10000)
    apply_dot(b, p, e, "bleed", 2)
    snap = (e["effects"].get("bleed") or {}).get("src") or {}
    exp = int(10000 * 0.01 * 2) + int(snap.get("atk", 0) * 0.05 * 2)
    d = dot_tick(b, e)
    check(f"流血 2 层（pct 1.5% 被 pct_cap 1% 压住）：{exp}", d == exp, f"d={d}")

    # 腐蚀 = atk×0.3 + matk×0.2 + max_hp×1%
    p, e, b = mk_pair(atk=100, matk=200, max_hp=10000)
    apply_dot(b, p, e, "corros", 1)
    snap = (e["effects"].get("corros") or {}).get("src") or {}
    exp = int(10000 * 0.01) + int(snap.get("atk", 0) * 0.3 + snap.get("matk", 0) * 0.2)
    d = dot_tick(b, e)
    check(f"腐蚀 1 层：{exp}", d == exp, f"d={d}")


def test_3_snapshot_semantics():
    print("【3. 快照语义：伤害跟「挂毒的人」，不跟当前结算者】")
    p, e, b = mk_pair(atk=100, matk=200)
    apply_dot(b, p, e, "poison", 1)
    snap1 = dict(((e["effects"].get("poison") or {}).get("src") or {}))
    check("挂毒时写入快照", bool(snap1.get("atk")), f"src={snap1}")

    d1 = dot_tick(b, e)
    # 事后改变施法者面板 + 换一个"结算者"视角：已挂的 DOT 伤害不变（读快照）
    p["atk"] = 9999
    apply_dot(b, p, e, "poison", 0)      # 不加层（amount=0 直接返回）
    d2 = dot_tick(b, e)
    check("事后改施法者面板：已挂 DOT 伤害不变（读快照，非实时面板）",
          d1 == d2 and d1 == int(snap1.get("atk", 0) * 0.8), f"d1={d1} d2={d2}")

    # 新挂一层 → 快照刷新（换一个**面板不同**的施法者：裸字段无效，actor_stats 走职业成长）
    p2 = make_actor(uid="p2", name="另一施法者", side="player", kind="player",
                    human_controlled=True, class_name="cls_ci_ke", level=60,
                    hp=3000, max_hp=3000, mp=300, max_mp=300,
                    atk=100, matk=200, spd=20, crit=0.0, equipment={}, skills=[],
                    learned_skills=[], **{"def": 30, "mdef": 30})
    b2 = B2(btype="monster", sides={"player": [p2], "enemy": [e]})
    apply_dot(b2, p2, e, "poison", 1)
    snap2 = (e["effects"].get("poison") or {}).get("src") or {}
    check("换施法者新挂 → 快照刷新为新施法者面板",
          snap2.get("atk") != snap1.get("atk") and snap2.get("atk") == int(actor_stats(b2, p2).get("atk", 0)),
          f"before={snap1} after={snap2} st={actor_stats(b2, p2).get('atk')}")


def test_4_boss_discount():
    print("【4. boss/精英：pct 段折扣 + 条目级优先不叠乘】")
    # 同构建：普通怪 vs boss，只差 pct 段折半
    p, e, b = mk_pair(atk=100, matk=200, max_hp=10000)
    apply_dot(b, p, e, "burn", 2)
    snap = (e["effects"].get("burn") or {}).get("src") or {}
    d_norm = dot_tick(b, e)
    flat = int(snap.get("matk", 0) * 0.6 * 2)
    check("普通怪：pct 0.005 全额", d_norm == int(10000 * 0.005 * 2) + flat, f"d={d_norm}")

    p, e, b = mk_pair(atk=100, matk=200, max_hp=10000, role="boss")
    apply_dot(b, p, e, "burn", 2)
    d_boss = dot_tick(b, e)
    check("boss：pct 段 ×0.5（100→50）", d_boss == int(10000 * 0.005 * 0.5 * 2) + flat,
          f"d={d_boss}（普通 {d_norm}）")

    p, e, b = mk_pair(atk=100, matk=200, max_hp=10000, role="elite")
    apply_dot(b, p, e, "burn", 2)
    d_el = dot_tick(b, e)
    check("精英同 boss 档（is_elite 并入判据）", d_el == d_boss, f"d={d_el} vs {d_boss}")

    # 条目级 pct_boss 优先且不叠乘
    tpl = "_t_cap_test"
    EC.get_effect_rules()[tpl] = {"cap": 9, "on": "target",
                                  "period": {"dir": "damage", "interval": 1.0,
                                             "pct_max_hp": 0.10, "pct_boss": 0.02,
                                             "boss_pct_mult": 0.5, "pct_cap": 0.05}}
    try:
        p, e, b = mk_pair(max_hp=10000, role="boss")
        apply_dot(b, p, e, tpl, 1)
        d = dot_tick(b, e)
        check("条目级 pct_boss=0.02 优先（非 0.10×0.5=0.05）→ 200", d == 200, f"d={d}")
    finally:
        EC.get_effect_rules().pop(tpl, None)


def test_5_pct_cap_and_execute():
    print("【5. 单层上限 pct_cap + 流血处决线】")
    tpl = "_t_cap2"
    EC.get_effect_rules()[tpl] = {"cap": 9, "on": "target",
                                  "period": {"dir": "damage", "interval": 1.0,
                                             "pct_max_hp": 0.50, "pct_cap": 0.01}}
    try:
        p, e, b = mk_pair(max_hp=10000)
        apply_dot(b, p, e, tpl, 3)
        d = dot_tick(b, e)
        check("pct 0.50 被单层上限压到 0.01 → int(10000×0.01×3)=300", d == 300, f"d={d}")
    finally:
        EC.get_effect_rules().pop(tpl, None)

    # 流血处决线：同构建下 hp<30% 的伤害 = 非处决线的 2 倍
    p, e, b = mk_pair(atk=100, max_hp=10000, hp=2000)   # 20% → 触发
    apply_dot(b, p, e, "bleed", 1)
    d_low = dot_tick(b, e)
    p, e, b = mk_pair(atk=100, max_hp=10000, hp=9000)   # 90% → 不触发
    apply_dot(b, p, e, "bleed", 1)
    d_hi = dot_tick(b, e)
    check(f"流血处决线：低血 {d_low} = 非低血 {d_hi} × 2", d_low == d_hi * 2,
          f"d_low={d_low} d_hi={d_hi}")


def test_6_total_resist():
    print("【6. 总抗 = min(resist_cap, dot_res + adapt) → ×(1−总抗)】")
    p, e, b = mk_pair(atk=100, max_hp=10000)
    apply_dot(b, p, e, "poison", 1)
    d0 = dot_tick(b, e)

    p, e, b = mk_pair(atk=100, max_hp=10000)
    apply_dot(b, p, e, "poison", 1)
    e["dot_res"] = 0.50
    d1 = dot_tick(b, e)
    check(f"dot_res 0.5 → 伤害减半（{d0} → {d1}）", d1 == int(d0 * 0.5), f"d0={d0} d1={d1}")

    p, e, b = mk_pair(atk=100, max_hp=10000)
    apply_dot(b, p, e, "poison", 1)
    e["dot_res"] = 0.50
    e["adapt"] = {"poison": 0.20}
    d2 = dot_tick(b, e)
    check(f"dot_res 0.5 + adapt 0.2 → 总抗 0.7 → ×0.3（{d2}）", d2 == int(d0 * 0.3), f"d2={d2}")

    p, e, b = mk_pair(atk=100, max_hp=10000)
    apply_dot(b, p, e, "poison", 1)
    e["dot_res"] = 0.98
    d3 = dot_tick(b, e)
    check(f"dot_res 0.98 被 resist_cap 0.95 压住 → ×0.05（{d3}）", d3 == int(d0 * 0.05), f"d3={d3}")

    # adapt 只按 key 匹配（别的 DOT 的适应不影响本 DOT）
    p, e, b = mk_pair(atk=100, max_hp=10000)
    apply_dot(b, p, e, "poison", 1)
    e["adapt"] = {"burn": 0.50}
    d4 = dot_tick(b, e)
    check("adapt 按 DOT key 匹配（burn 的适应不影响 poison）", d4 == d0, f"d4={d4}")

    # 无 resist_cap 声明的条目不受 dot_res 影响（零变化）
    tpl = "_t_nores"
    EC.get_effect_rules()[tpl] = {"cap": 9, "on": "target",
                                  "period": {"dir": "damage", "interval": 1.0,
                                             "pct_max_hp": 0.01}}
    try:
        p, e, b = mk_pair(max_hp=10000)
        apply_dot(b, p, e, tpl, 1)
        e["dot_res"] = 0.9
        d = dot_tick(b, e)
        check("未声明 resist_cap 的条目：dot_res 不参与 → 100", d == 100, f"d={d}")
    finally:
        EC.get_effect_rules().pop(tpl, None)


def test_7_true_damage():
    print("【7. 真伤 DOT（腐蚀）不吃物免/魔免/格挡】")
    p, e, b = mk_pair(atk=100, matk=200, max_hp=10000)
    apply_dot(b, p, e, "corros", 1)
    d_clean = dot_tick(b, e)

    p, e, b = mk_pair(atk=100, matk=200, max_hp=10000)
    e["phys_reduce"] = 0.40
    e["magic_reduce"] = 0.40
    e["block"] = 1.0        # 必格挡
    apply_dot(b, p, e, "corros", 1)
    d_true = dot_tick(b, e)
    check(f"腐蚀（真伤）：有物免/魔免/必格挡时伤害不变（{d_clean}）",
          d_true == d_clean, f"d_true={d_true} d_clean={d_clean}")

    p, e, b = mk_pair(atk=100, matk=200, max_hp=10000)
    apply_dot(b, p, e, "burn", 1)
    d_b_clean = dot_tick(b, e)
    p, e, b = mk_pair(atk=100, matk=200, max_hp=10000)
    e["magic_reduce"] = 0.40
    e["block"] = 1.0
    apply_dot(b, p, e, "burn", 1)
    d_b = dot_tick(b, e)
    check(f"灼烧（非真伤，空 dmg_kind）：同样不走类型减免（{d_b_clean}）",
          d_b == d_b_clean, f"d_b={d_b}")


def test_8_zero_change():
    print("【8. 零变化：既有无系数条目（如裂伤）行为不变】")
    tpl = "_t_old"
    EC.get_effect_rules()[tpl] = {"cap": 9, "on": "target",
                                  "period": {"dir": "damage", "interval": 1.0,
                                             "pct_max_hp": 0.015, "pct_boss": 0.01,
                                             "turns": 3}}
    try:
        p, e, b = mk_pair(max_hp=10000)
        apply_dot(b, p, e, tpl, 2)
        d = dot_tick(b, e)
        check("普通怪：int(10000×0.015×2) = 300", d == 300, f"d={d}")
        p, e, b = mk_pair(max_hp=10000, role="boss")
        apply_dot(b, p, e, tpl, 2)
        d = dot_tick(b, e)
        check("boss：pct_boss 0.01 → int(10000×0.01×2) = 200", d == 200, f"d={d}")
    finally:
        EC.get_effect_rules().pop(tpl, None)

    # 无快照的系数型 DOT：本刻 0 伤害（不造假值），不崩
    tpl2 = "_t_nosrc"
    EC.get_effect_rules()[tpl2] = {"cap": 9, "on": "target",
                                   "period": {"dir": "damage", "interval": 1.0,
                                              "atk": 1.0}}
    try:
        p, e, b = mk_pair(atk=100, max_hp=10000)
        e["effects"][tpl2] = {"stacks": 2}      # 手工塞条目（无 src）
        d = dot_tick(b, e)
        check("系数型无快照：本刻 0 伤害（不造假值）", d == 0, f"d={d}")
    finally:
        EC.get_effect_rules().pop(tpl2, None)


def test_9_crit_at():
    print("【9. crit_at：连段 ≥4 → 终结技必暴出手态】")
    from content.mech import class_mech as CMP
    p, e, b = mk_pair()
    p["learned_skills"] = ["终结·割喉"]          # mech=finisher 的刺客终结技
    p["effects"] = {}
    CMP.apply_class_mech(p)
    acts = (p.get("triggers") or {}).get("act_cast") or []
    check("装配器已挂 act_cast 钩子（mech_cash_finisher_crit）",
          any(isinstance(x, dict) and x.get("action") == "mech_cash_finisher_crit"
              for x in acts), f"act_cast={acts}")

    # 连段 3（不足）→ 不写必暴态
    p["effects"] = {"lian_duan": {"stacks": 3}}
    fire(b, "act_cast", {"actor": p, "target": e, "info": {"mech": "finisher"}}, [])
    check("连段 3 < 4：不写必暴态", "finisher_crit_ready" not in (p.get("effects") or {}),
          f"effects={list((p.get('effects') or {}).keys())}")

    # 连段 4 → 写必暴态，且被出手消费
    p["effects"] = {"lian_duan": {"stacks": 4}}
    fire(b, "act_cast", {"actor": p, "target": e, "info": {"mech": "finisher"}}, [])
    ent = (p.get("effects") or {}).get("finisher_crit_ready")
    check("连段 4 ≥ 4：写入一次性必暴出手态",
          isinstance(ent, dict) and (ent.get("hit") or {}).get("guaranteed_crit") is True,
          f"entry={ent}")
    hb = _consume_hit_buffs(b, p, [])
    check("出手消费：guaranteed_crit = True", hb.get("guaranteed_crit") is True, f"hb={hb}")

    # 非终结技（mech 不匹配）→ 不写
    p["effects"] = {"lian_duan": {"stacks": 5}}
    fire(b, "act_cast", {"actor": p, "target": e, "info": {"mech": "poison"}}, [])
    check("非终结技（mech=poison）：不写必暴态",
          "finisher_crit_ready" not in (p.get("effects") or {}), "")


def main():
    test_1_single_source()
    test_2_coefficients()
    test_3_snapshot_semantics()
    test_4_boss_discount()
    test_5_pct_cap_and_execute()
    test_6_total_resist()
    test_7_true_damage()
    test_8_zero_change()
    test_9_crit_at()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")


if __name__ == "__main__":
    main()
