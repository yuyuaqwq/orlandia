# -*- coding: utf-8 -*-
"""v181 元素机制 + 奥术力场/减伤升档 验收（2026-09-11）。

## 覆盖

A. **印记反应轴**（CLASS_MECHANICS_v153 §2）：蒸发 / 超载 / 冻结 / 感电（含层数门槛）
   + 反应清印 + 无元素技能不触发
B. **克制轴**（§9.1 三角循环）：火克冰（解冻）/ 冰克雷（打断）/ 雷克火（灼烧）+ ×1.25
C. **元素流转**：主系轮转 + **只影响下一次**挂印（element/mech 改写）+ 用后即清
D. **配置缺陷修正**：冻结原写 `water`（不存在）→ 应为 `thunder`；感电需雷印 ≥3 层
E. **不破壁垒升档**：战意 ≥8 → 减伤 30%→50%（`reduce_alt`）
F. **奥术力场两档**：盾档（按充能层数转魔攻盾）/ 刃档（下次奥术技 ×1.3，一次性）
   + 充能消耗

跑法：python tests/test_v181_element_and_field.py
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_b2_elem.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from ext_combat import Battle as B2, make_actor  # noqa: E402
from ext_combat.battle.landing import deal_damage  # noqa: E402
from ext_combat.battle.effects import apply_effects  # noqa: E402
from ext_combat.battle.effect_triggers import fire  # noqa: E402
from _engine_harness import boot as ensure_engine_configured  # noqa: E402

# 测试稳定性：屏蔽承伤侧的**闪避随机**（角色面板自带 ~3% dodge；本文件断言的是
# 减伤/护盾乘区数值，闪避未命中会让断言偶发失败）。格挡同理（block=0 时本就不 roll）。
import ext_combat.battle.landing as _LD  # noqa: E402
_LD._roll_dodge = lambda *a, **k: False  # noqa: E731


ensure_engine_configured()
from content.mech import element_procs as EP  # noqa: E402,F401  ★ B18-REPOINT：直取包内实现本体
from content.mech import team_procs as TP  # noqa: E402,F401  ★ B18-REPOINT：直取包内实现本体
from content.mech.element_data import ELEMENT_REACTIONS  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []


from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "PASS", "FAIL", "FAILURES")


def mk(uid, side="player", hp=2000, matk=150, cls="cls_fa_shi"):
    a = make_actor(uid=uid, name=uid, side=side,
                   kind="player" if side == "player" else "monster",
                   human_controlled=(side == "player"),
                   class_name=cls if side == "player" else None,
                   level=20, hp=hp, max_hp=hp, mp=300, max_mp=300,
                   atk=200, matk=matk, spd=50, crit=0.05,
                   equipment={}, skills=[],
                   learned_skills=([] if side != "player" else ["sk_bing_zhui", "元素流转"]),
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


def setup():
    p = mk("p1")
    e = mk_boss()
    b = B2(btype="monster", sides={"player": [p], "enemy": [e]})
    EP.apply_element_procs(p)      # 元素两轴装配
    return b, p, e


def load_skill(p, name, effect, element=None, **extra):
    """把技能 dict 塞进 actor 的 _skill_index（模拟数据桥），返回 info。"""
    info = {"name": name, "effect": effect, "kind": "魔法", "power": 1.2}
    if element:
        info["element"] = element
    info.update(extra)
    p.setdefault("_skill_index", {})[name] = info
    return info


def cast_dmg(b, p, e, info, amount=1000):
    """按技能施放走一遍伤害管线（含 dmg_calc 事件）。返回实际扣血。"""
    from ext_combat.battle.actions import _single_target_pipeline
    e["hp"] = e["max_hp"]
    logs = []
    p.setdefault("_skill_index", {})[info["name"]] = info
    _single_target_pipeline(b, p, e, info, 1)
    return e["max_hp"] - e["hp"], logs


def dmg_calc_only(b, p, e, info, amount=1000):
    """只跑 dmg_calc 事件链（不起完整技能管线），用于精确验证乘区。"""
    e["hp"] = e["max_hp"]
    logs = []
    ctx = {"actor": p, "target": e, "dmg": amount, "info": info, "mult": 1.0}
    fire(b, "dmg_calc", ctx, logs)
    # 读**本次事件的 ctx 对象**（引擎 fire 现在栈式恢复 `battle._fire_ctx`，嵌套安全）
    m = float(ctx.get("mult", 1.0) or 1.0)
    return m, logs


# ============================================================
# A. 印记反应轴
# ============================================================

def test_reaction():
    print("【A. 印记反应轴（CLASS_MECHANICS §2）】")
    b, p, e = setup()

    # 蒸发：冰打火印 ×1.30 + 清印
    e["effects"]["fire_mark"] = {"stacks": 2}
    m, logs = dmg_calc_only(b, p, e, {"name": "冰锥", "element": "ice", "kind": "魔法"})
    check("冰打火印 → 蒸发 ×1.30", abs(m - 1.30) < 1e-9, f"m={m} logs={logs}")
    check("蒸发日志出现", any("蒸发" in str(x) for x in logs), f"logs={logs}")
    check("蒸发清印（fire_mark 被消耗）", not (e.get("effects") or {}).get("fire_mark"),
          f"ef={list((e.get('effects') or {}).keys())}")

    # 超载：火打雷印（转 AOE，倍率 1.00）
    b2, p2, e2 = setup()
    e2["effects"]["thunder_mark"] = {"stacks": 1}
    m2, logs2 = dmg_calc_only(b2, p2, e2, {"name": "火球术", "element": "fire", "kind": "魔法"})
    check("火打雷印 → 超载（触发、倍率 1.0）", any("超载" in str(x) for x in logs2), f"logs={logs2}")
    check("超载清印", not (e2.get("effects") or {}).get("thunder_mark"))

    # 冻结：雷打冰印（**修正后的配置**）→ 目标被冻结
    b3, p3, e3 = setup()
    e3["effects"]["ice_mark"] = {"stacks": 1}
    m3, logs3 = dmg_calc_only(b3, p3, e3, {"name": "雷击", "element": "thunder", "kind": "魔法"})
    check("雷打冰印 → 冻结（配置已由 water 修正为 thunder）",
          any("冻结" in str(x) for x in logs3), f"logs={logs3}")
    fz = (e3.get("effects") or {}).get("freeze")
    check("冻结态落地（mode=skip）", isinstance(fz, dict) and fz.get("mode") == "skip",
          f"freeze={fz}")

    # 感电：雷打雷印，需 ≥3 层
    b4, p4, e4 = setup()
    e4["effects"]["thunder_mark"] = {"stacks": 2}
    m4, logs4 = dmg_calc_only(b4, p4, e4, {"name": "雷击", "element": "thunder", "kind": "魔法"})
    check("雷印 2 层 → 不触发感电（门槛 3）", not any("感电" in str(x) for x in logs4),
          f"logs={logs4}")
    e4["effects"]["thunder_mark"] = {"stacks": 3}
    m5, logs5 = dmg_calc_only(b4, p4, e4, {"name": "雷击", "element": "thunder", "kind": "魔法"})
    check("雷印 3 层 → 感电（连击 +1）", any("感电" in str(x) for x in logs5), f"logs={logs5}")
    check("感电**不清印**（印记保留）", (e4.get("effects") or {}).get("thunder_mark"),
          f"ef={list((e4.get('effects') or {}).keys())}")
    check("感电连击计数落地", isinstance((e4.get("effects") or {}).get("elem_chain"), dict))

    # 无元素技能 / 无印记 → 零行为
    b5, p5, e5 = setup()
    m6, _ = dmg_calc_only(b5, p5, e5, {"name": "奥术飞弹", "kind": "魔法"})
    check("无 element 技能不触发反应", abs(m6 - 1.0) < 1e-9, f"m={m6}")
    m7, _ = dmg_calc_only(b5, p5, e5, {"name": "火球术", "element": "fire", "kind": "魔法"})
    check("有 element 但目标无印 → 不触发", abs(m7 - 1.0) < 1e-9, f"m={m7}")

    # 配置自查
    check("ELEMENT_REACTIONS 无 water 残留（配置缺陷已修）",
          not [k for k in ELEMENT_REACTIONS if k[0] == "water"],
          f"keys={list(ELEMENT_REACTIONS.keys())}")


# ============================================================
# B. 克制轴
# ============================================================

def test_counter():
    print("【B. 克制轴（§9.1 三角循环）】")
    # 火克冰：对冰冻目标 ×1.25 + 解冻
    b, p, e = setup()
    e["effects"]["freeze"] = {"stacks": 1, "mode": "skip"}
    m, logs = dmg_calc_only(b, p, e, {"name": "火球术", "element": "fire", "kind": "魔法"})
    check("火打冰冻目标 → ×1.25", abs(m - 1.25) < 1e-9, f"m={m} logs={logs}")
    check("附带解冻（freeze 被清）", not (e.get("effects") or {}).get("freeze"),
          f"ef={list((e.get('effects') or {}).keys())}")

    # 冰克雷：对雷印目标 ×1.25 + 打断
    b2, p2, e2 = setup()
    e2["effects"]["thunder_mark"] = {"stacks": 1}
    e2["charging"] = {"skill": "蓄力斩"}
    m2, logs2 = dmg_calc_only(b2, p2, e2, {"name": "冰锥", "element": "ice", "kind": "魔法"})
    check("冰打雷印目标 → ×1.25", abs(m2 - 1.25) < 1e-9, f"m={m2} logs={logs2}")

    # 雷克火：对灼烧目标 ×1.25
    b3, p3, e3 = setup()
    e3["effects"]["burn"] = {"stacks": 1}
    m3, logs3 = dmg_calc_only(b3, p3, e3, {"name": "雷击", "element": "thunder", "kind": "魔法"})
    check("雷打灼烧目标 → ×1.25", abs(m3 - 1.25) < 1e-9, f"m={m3} logs={logs3}")

    # 反向（非克制）不触发
    b4, p4, e4 = setup()
    e4["effects"]["burn"] = {"stacks": 1}
    m4, _ = dmg_calc_only(b4, p4, e4, {"name": "火球术", "element": "fire", "kind": "魔法"})
    check("火打灼烧目标 → 无克制加成", abs(m4 - 1.0) < 1e-9, f"m={m4}")

    # 双轴叠加：冰打火印（蒸发 ×1.30）+ 同时目标冰冻（克制 ×1.25）→ ×1.625
    # 双轴同时命中：冰技能 打「火印（→蒸发 1.30）」且目标带雷印（→冰克雷 1.25）
    b5, p5, e5 = setup()
    e5["effects"]["fire_mark"] = {"stacks": 1}
    e5["effects"]["thunder_mark"] = {"stacks": 1}
    m5, logs5 = dmg_calc_only(b5, p5, e5, {"name": "冰锥", "element": "ice", "kind": "魔法"})
    check("双轴叠加（蒸发 1.30 × 克制 1.25 = 1.625）", abs(m5 - 1.625) < 1e-9,
          f"m={m5} logs={logs5}")


# ============================================================
# C. 元素流转
# ============================================================

def test_element_switch():
    print("【C. 元素流转（主系 → 下次挂印）】")
    b, p, e = setup()
    logs = []
    apply_effects(b, p, p, [{"type": "class_element_switch", "turns": 4,
                             "info": {"name": "元素流转"}}], logs)
    check("主系切换为 fire（首个）", p.get("cur_element") == "fire", f"cur={p.get('cur_element')}")
    check("一次性转换标记已置", p.get("_elem_conv") == "fire", f"conv={p.get('_elem_conv')}")
    apply_effects(b, p, p, [{"type": "class_element_switch", "turns": 4,
                             "info": {"name": "元素流转"}}], logs)
    check("再切轮转 → ice", p.get("cur_element") == "ice", f"cur={p.get('cur_element')}")

    # 下次挂印转换：act_cast 触发 elem_conv_apply 改写 info
    info = {"name": "雷击", "element": "thunder", "mech": "thunder_mark", "kind": "魔法"}
    ctx = {"actor": p, "target": e, "info": info}
    fire(b, "act_cast", ctx, [])
    check("下一次技能元素被改写为主系 ice", info.get("element") == "ice", f"info={info}")
    check("下一次挂印被改写为 ice_mark", info.get("mech") == "ice_mark", f"info={info}")
    check("转换标记用后即清（只影响一次）", not p.get("_elem_conv"), f"conv={p.get('_elem_conv')}")

    # 第二次不再转换
    info2 = {"name": "雷击", "element": "thunder", "mech": "thunder_mark", "kind": "魔法"}
    fire(b, "act_cast", {"actor": p, "target": e, "info": info2}, [])
    check("第二次施放不再转换", info2.get("mech") == "thunder_mark", f"info2={info2}")

    # 非元素印技能只改 element，不动 mech
    apply_effects(b, p, p, [{"type": "class_element_switch", "turns": 4,
                             "info": {"name": "元素流转"}}], logs)   # cur → thunder
    info3 = {"name": "奥术飞弹", "mech": "arcane", "kind": "魔法"}
    fire(b, "act_cast", {"actor": p, "target": e, "info": info3}, [])
    check("非元素印技能：element 改写、mech 不动",
          info3.get("element") == "thunder" and info3.get("mech") == "arcane", f"info3={info3}")


# ============================================================
# D. 不破壁垒升档
# ============================================================

def test_reduce_alt():
    print("【D. 减伤条件升档（不破壁垒：战意 ≥8 → 30%→50%）】")
    b, p, e = setup()
    info = {"name": "不破壁垒", "reduce": 0.30, "reduce_alt": 0.50,
            "reduce_alt_res": "zhan_yi", "reduce_alt_ge": 8}
    # 战意 5（不足）→ 基础 30%
    p["effects"]["zhan_yi"] = {"stacks": 5}
    apply_effects(b, p, p, [{"type": "reduce_all", "turns": 12, "info": info}], [])
    st = [k for k in (p.get("effects") or {}) if k.startswith("team:reduce:")]
    r = (p["effects"][st[0]].get("reduce") if st else None)
    check("战意 5 → 减伤 30%（基础档）", r == 0.30, f"r={r}")

    # 战意 8（达标）→ 升档 50%
    b2, p2, e2 = setup()
    p2["effects"]["zhan_yi"] = {"stacks": 8}
    apply_effects(b2, p2, p2, [{"type": "reduce_all", "turns": 12, "info": info}], [])
    st2 = [k for k in (p2.get("effects") or {}) if k.startswith("team:reduce:")]
    r2 = (p2["effects"][st2[0]].get("reduce") if st2 else None)
    check("战意 8 → 升档 50%", r2 == 0.50, f"r2={r2}")

    # 端到端：50% 减伤真的生效
    b3, p3, e3 = setup()
    p3["effects"]["zhan_yi"] = {"stacks": 8}
    apply_effects(b3, p3, p3, [{"type": "reduce_all", "turns": 12, "info": info}], [])
    p3["hp"] = p3["max_hp"]
    d = deal_damage(b3, e3, p3, 1000, [], dmg_kind="phys")
    check("升档后端到端：1000 → 500", d == 500, f"d={d}")


# ============================================================
# E. 奥术力场两档
# ============================================================

def test_arcane_field():
    print("【E. 奥术力场两档（盾 / 刃）】")
    from ext_combat.battle import stats as _S

    # 盾档（默认）
    b, p, e = setup()
    p["effects"]["arcane"] = {"stacks": 5}
    p["battle_prefs"] = {"arcane_field": "盾"}
    apply_effects(b, p, p, [{"type": "arcane_field", "turns": 10,
                            "info": {"name": "奥术力场", "shield_per_stack": 0.08,
                                     "shield_res_key": "arcane", "shield_base_stat": "matk"}}], [])
    # 盾值按**消耗后**的当前面板魔攻 × 剩余层数×8%（消耗会实时改面板，故现算）
    _left = float((p["effects"].get("arcane") or {}).get("stacks", 0) or 0)
    _matk = float((_S.actor_stats(b, p) or {}).get("matk", 0) or 0)
    _expect = int(_matk * (_left * 0.08))
    shields = sum(int(v.get("value", 0) or 0) for v in (p.get("shields") or {}).values())
    check(f"盾档：面板魔攻 {_matk:.0f} × {_left:g}层×8% = {_expect} 护盾", shields == _expect,
          f"got={shields} expect={_expect}")
    check("盾档消耗 2 点充能（5 → 3）",
          float((p["effects"].get("arcane") or {}).get("stacks", 0) or 0) == 3.0,
          f"arcane={p['effects'].get('arcane')}")

    # 刃档
    b2, p2, e2 = setup()
    p2["effects"]["arcane"] = {"stacks": 5}
    p2["battle_prefs"] = {"arcane_field": "刃"}
    apply_effects(b2, p2, p2, [{"type": "arcane_field", "turns": 10,
                               "info": {"name": "奥术力场"}}], [])
    check("刃档：写利刃态", any(k.startswith("team:edge:") for k in (p2.get("effects") or {})),
          f"ef={list((p2.get('effects') or {}).keys())}")
    check("刃档消耗 2 点充能", float((p2["effects"].get("arcane") or {}).get("stacks", 0) or 0) == 3.0)
    # 奥术技吃加成（一次性）
    m, logs = dmg_calc_only(b2, p2, e2, {"name": "奥术脉冲", "mech": "arcane", "kind": "魔法"})
    check("奥术技 → ×1.3", abs(m - 1.3) < 1e-9, f"m={m} logs={logs}")
    check("利刃态用后即清（一次性）",
          not any(k.startswith("team:edge:") for k in (p2.get("effects") or {})),
          f"ef={list((p2.get('effects') or {}).keys())}")
    # 非奥术技不吃、也不消耗
    b3, p3, e3 = setup()
    p3["effects"]["arcane"] = {"stacks": 5}
    p3["battle_prefs"] = {"arcane_field": "刃"}
    apply_effects(b3, p3, p3, [{"type": "arcane_field", "turns": 10,
                               "info": {"name": "奥术力场"}}], [])
    m3, _ = dmg_calc_only(b3, p3, e3, {"name": "火球术", "element": "fire", "kind": "魔法"})
    check("非奥术技不吃利刃加成（也不消耗）",
          abs(m3 - 1.0) < 1e-9 and any(k.startswith("team:edge:") for k in (p3.get("effects") or {})),
          f"m={m3} ef={list((p3.get('effects') or {}).keys())}")


if __name__ == "__main__":
    test_reaction()
    test_counter()
    test_element_switch()
    test_reduce_alt()
    test_arcane_field()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")
