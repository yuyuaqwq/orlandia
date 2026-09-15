# -*- coding: utf-8 -*-
"""批 B 验收（2026-09-11）：怪物元素抗性 / 弱点 / 异常免疫**数据 + 通道**。

背景：§9.2 要的「怪物侧 elem_res / dot_res / immune_dots 补录」在动手前核实出三处偏差，
本批按核实结果落地（不照旧清单干）：

  · `elem_res` 是**标量**（`landing.py` 用 `float()` 读）= 对全部元素统一的抗性 →
    「火焰怪火抗 0.5、冰 0」这种**分系**需求它表达不了；且它对「逼玩家换系」是反效果
    （全抗 = 所有系都打不动）。→ 改用**已实装**的 `element_weak` / `element_immune`
    （v178 E5 数据驱动，`landing.py:73-88`）：分系、且方向正确。
  · `immune_dots` 引擎侧此前无消费方（本批已接线），**且** `drops.build_monster` 的
    mod→实例白名单里没有它 → 光接线数据仍进不来。本批补白名单（多通道坑）。
  · `dot_res` 结算端**零读点**（`stats.py` 只按档赋值 + 战报展示读）→ 本批**不配**
    （配了不生效，且 Boss 档 0.9 一旦接线会把 DOT 流对 Boss 砍到 1/10 —— 属设计裁定项）。

跑法：python tests/test_v181_batch_b_resist_data.py（exit=0 全绿）
"""
import os
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_batch_b.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _b2c  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()  # noqa: E402
from saintess_engine import Battle as B2, make_actor  # noqa: E402
from saintess_engine.battle.landing import deal_damage  # noqa: E402
from saintess_engine.battle.effects import apply_action  # noqa: E402
from content import drops as D  # noqa: E402

PASS = 0
FAIL = 0
FAILURES = []

# 本批落地的 9 个主题怪（§9.2 最小集）
WEAK_CFG = {
    "b_ember_lord":       {"thunder": 1.4},
    "e_lava_golem":       {"ice": 1.4},
    "e_molten_lord":      {"ice": 1.4},
    "e_lake_lord":        {"fire": 1.4},
    "m_ice_elemental":    {"fire": 1.4},
    "e_storm_lord":       {"ice": 1.4},
    "e_red_dragon_lord":  {"thunder": 1.4},
}
IMMUNE_CFG = {
    "b_ember_lord":    ["burn"],
    "e_lava_golem":    ["burn"],
    "e_molten_lord":   ["burn"],
    "m_obsidian_golem": ["poison"],
    "m_meteor_golem":   ["poison"],
}


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name}: {detail}")
        print(f"  ❌ {name} {detail}")


def build(uid, lv=40, role="elite"):
    return D.build_monster((uid, uid, role, lv, [], {}),
                           {"id": "t", "name": "t", "area": "field"})


# ============================================================
# 1. 数据通道：MONSTER_MODS → 实例（白名单透传）
# ============================================================

def test_1_channel():
    print("【1. 数据通道：mod → 怪物实例透传（drops.build_monster 白名单）】")
    for uid, w in WEAK_CFG.items():
        e = build(uid)
        check(f"{uid} 实例带 element_weak={w}", e.get("element_weak") == w,
              f"got={e.get('element_weak')}")
    for uid, im in IMMUNE_CFG.items():
        e = build(uid)
        check(f"{uid} 实例带 immune_dots={im}", list(e.get("immune_dots") or []) == im,
              f"got={e.get('immune_dots')}")

    # 零变化：未配置的怪仍是空值（不引入意外免疫）
    e = build("m_giant_rat", role="dps")
    check("未配置怪：immune_dots = []（零变化）", list(e.get("immune_dots") or []) == [],
          f"got={e.get('immune_dots')}")
    check("未配置怪：element_weak = {}（零变化）", dict(e.get("element_weak") or {}) == {},
          f"got={e.get('element_weak')}")

    # 白名单确实新增了 immune_dots（防被回退）
    # ★ P5F-REPOINT: 原读宿主壳 `game/core/drops.py`（随删壳批消失）→ 包内真源 `content/drops.py`。
    src = open(os.path.join(PLUGIN_DIR, "content", "drops.py"),
               encoding="utf-8").read()
    check("drops.py 白名单含 immune_dots 透传",
          '"immune_dots": list(mod.get("immune_dots") or [])' in src, "未找到透传行")


# ============================================================
# 2. 机制端到端：弱点增伤 / 抗性 / 免疫拦截
# ============================================================

def test_2_end_to_end():
    print("【2. 端到端：弱点增伤 + 免疫拦截（真实 build_monster 实例）】")
    p = make_actor(uid="p1", name="法师", side="player", kind="player",
                   human_controlled=True, class_name="cls_fa_shi", level=40,
                   hp=3000, max_hp=3000, mp=300, max_mp=300,
                   atk=100, matk=200, spd=20, crit=0.0, equipment={}, skills=[],
                   learned_skills=[], **{"def": 30, "mdef": 30})

    def mk_enemy_from(uid):
        e = build(uid)
        e["effects"] = {}
        e["dodge"] = 0.0
        e["block"] = 0.0
        return e

    b = B2(btype="monster", sides={"player": [p], "enemy": [mk_enemy_from("m_giant_rat")]})

    # 弱点增伤：永冬湖主弱火 → 火系伤害 ×1.4
    e_ice = mk_enemy_from("e_lake_lord")
    b1 = B2(btype="monster", sides={"player": [p], "enemy": [e_ice]})
    fire_hit = deal_damage(b1, p, e_ice, 100, [], element="fire")
    check("永冬湖主 弱火：100 → 140（×1.4）", fire_hit == 140, f"={fire_hit}")
    ice_hit = deal_damage(b1, p, e_ice, 100, [], element="ice")
    check("永冬湖主 非弱点（冰）：100 → 100", ice_hit == 100, f"={ice_hit}")

    # 雷暴领主弱冰：冰系 ×1.4、火系不增
    e_storm = mk_enemy_from("e_storm_lord")
    b2 = B2(btype="monster", sides={"player": [p], "enemy": [e_storm]})
    check("雷暴领主 弱冰：100 → 140",
          deal_damage(b2, p, e_storm, 100, [], element="ice") == 140, "")
    check("雷暴领主 非弱点（火）：100 → 100",
          deal_damage(b2, p, e_storm, 100, [], element="fire") == 100, "")

    # 火 Boss 弱雷
    e_emb = mk_enemy_from("b_ember_lord")
    b3 = B2(btype="monster", sides={"player": [p], "enemy": [e_emb]})
    check("烬火领主 弱雷：100 → 140",
          deal_damage(b3, p, e_emb, 100, [], element="thunder") == 140, "")

    # 免疫拦截：熔岩魔像免灼烧 → burn 不施加；但毒可施加（只免指定类型）
    e_lava = mk_enemy_from("e_lava_golem")
    b4 = B2(btype="monster", sides={"player": [p], "enemy": [e_lava]})
    apply_action(b4, p, e_lava, "apply",
                 {"key": "burn", "op": "add", "amount": 3, "on": "target"}, [])
    check("熔岩魔像 免灼烧：burn 未被施加",
          int((e_lava["effects"].get("burn") or {}).get("stacks", 0)) == 0,
          f"ef={e_lava['effects'].get('burn')}")
    apply_action(b4, p, e_lava, "apply",
                 {"key": "poison", "op": "add", "amount": 3, "on": "target"}, [])
    check("熔岩魔像 只免指定类型：毒正常施加",
          int((e_lava["effects"].get("poison") or {}).get("stacks", 0)) == 3,
          f"ef={e_lava['effects'].get('poison')}")

    # 高防魔像免毒：毒被拦，腐蚀（真伤轴）仍可用 = §9.2 的设计出口
    e_golem = mk_enemy_from("m_meteor_golem")
    b5 = B2(btype="monster", sides={"player": [p], "enemy": [e_golem]})
    apply_action(b5, p, e_golem, "apply",
                 {"key": "poison", "op": "add", "amount": 3, "on": "target"}, [])
    check("陨星魔像 免毒：poison 未被施加",
          int((e_golem["effects"].get("poison") or {}).get("stacks", 0)) == 0,
          f"ef={e_golem['effects'].get('poison')}")
    apply_action(b5, p, e_golem, "apply",
                 {"key": "corros", "op": "add", "amount": 2, "on": "target"}, [])
    check("陨星魔像 腐蚀（真伤轴）仍可施加 = §9.2 设计出口",
          int((e_golem["effects"].get("corros") or {}).get("stacks", 0)) == 2,
          f"ef={e_golem['effects'].get('corros')}")

    # 未配置怪：DOT 照旧（零变化）
    e_rat = mk_enemy_from("m_giant_rat")
    b6 = B2(btype="monster", sides={"player": [p], "enemy": [e_rat]})
    apply_action(b6, p, e_rat, "apply",
                 {"key": "burn", "op": "add", "amount": 3, "on": "target"}, [])
    check("未配置怪：灼烧正常施加（零变化）",
          int((e_rat["effects"].get("burn") or {}).get("stacks", 0)) == 3,
          f"ef={e_rat['effects'].get('burn')}")


# ============================================================
# 3. 克制轴一致性
# ============================================================

def test_3_counter_axis():
    print("【3. 与 §9.1 克制轴三角一致（火→冰→雷→火 ⇒ 火克冰/冰克雷/雷克火）】")
    from content.mech.element_procs import COUNTER_RULES  # ★ B18-REPOINT：直取包内实现本体
    # 克制轴：攻击方元素 → 克制的目标态（freeze=冰系态 / ...）
    check("克制表存在且 fire 段带解冻语义",
          "fire" in COUNTER_RULES and COUNTER_RULES["fire"].get("victim_state") == "freeze",
          f"={COUNTER_RULES.get('fire')}")
    # 数据侧弱点方向 = 克制轴的反向（被克者露弱点）
    pairs = [("e_lake_lord", "fire"), ("m_ice_elemental", "fire"),      # 冰怪弱火
             ("e_storm_lord", "ice"),                                    # 雷怪弱冰
             ("b_ember_lord", "thunder"), ("e_red_dragon_lord", "thunder")]  # 火怪弱雷
    for uid, el in pairs:
        e = build(uid)
        w = dict(e.get("element_weak") or {})
        check(f"{uid} 弱点 {el}（克制轴方向一致）", list(w.keys()) == [el], f"={w}")


# ============================================================
# 4. 未落地项现状（防被误当已完成）
# ============================================================

def test_4_open_items():
    print("【4. 未落地项现状（登记，防误判为已完成）】")
    # ★ P5F-REPOINT: 原读宿主壳 `game/core/drops.py`（随删壳批消失）→ 包内真源 `content/drops.py`。
    src = open(os.path.join(PLUGIN_DIR, "content", "drops.py"),
               encoding="utf-8").read()
    check("dot_res 仍**不在** mod→实例白名单（结算端无读点，本批有意不配）",
          '"dot_res": ' not in src, "意外出现在白名单")
    from saintess_engine.battle import landing as L
    check("elem_res 仍为标量读法（分系抗性需求未支持——本批改用 element_weak 走通）",
          "elem_res" in open(L.__file__, encoding="utf-8").read(), "")


def main():
    test_1_channel()
    test_2_end_to_end()
    test_3_counter_axis()
    test_4_open_items()
    print(f"\n== 结果：通过 {PASS} / 共 {PASS + FAIL} ==")
    if FAILURES:
        for f in FAILURES:
            print("  FAIL:", f)
        sys.exit(1)
    print("全绿 ✅")


if __name__ == "__main__":
    main()
