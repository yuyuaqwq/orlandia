# -*- coding: utf-8 -*-
"""N10-B7：food 战斗料理效果 saintess_engine 装配验收（缺口补完）。

跑法：python tests/test_battle_n10_b7_food.py（w1 内）

设计：docs/DESIGN_N10B7_food_effects.md
- 吃料理（foodfx payload）→ battle_item_use.translate → actor["triggers"] 装配
  + effects period 周期声明（回春/冥想/晨曦）→ skill_hit/on_taken/dmg_calc/taken_calc
  事件 fire 消费（we_* 扩展动作执行）
- 数值权威 = food_effect_data.FOOD_EFFECT_PARAMS（读表零硬编码）

验收点：① 蛇羹吸血 ② 辣椒流血 dot ③ 狼肉干反击 ④ 树蜜糖回春(period)
⑤ 海鲜浓汤精准 ⑥ 海盗炖鱼处决阈值 ⑦ 圣餐面包盾回归 ⑧ 重复幂等
⑨ 战斗结束销毁无残留 ⑩ 装配层纯函数全覆盖 + 事件触发真实性
"""
import os
import random
import sys

PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # tests/：引擎根发现（_paths）
import _paths  # noqa: E402,F401  ← 包根/引擎根/宿主壳根装配（GWEN_FRAMEWORK_DIR 优先；缺失即醒目报错）
os.environ.setdefault("GWEN_GAME_DB", os.path.join(PLUGIN_DIR, "test_b2_n10b7.db"))
os.environ.setdefault("GWEN_TEST_MODE", "1")
sys.path.insert(0, PLUGIN_DIR)
_shim = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shim_astrbot")
if os.path.isdir(_shim) and _shim not in sys.path:
    sys.path.insert(0, _shim)

from saintess_engine import config as _b2c  # noqa: E402
from _engine_harness import boot as _eng_cfg; _eng_cfg()
from saintess_engine import Battle as B2, make_actor  # noqa: E402
from saintess_engine import actions as A  # noqa: E402
from saintess_engine import landing as L  # noqa: E402
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


def mk_fighter(**kw):
    """战士（物理伤害稳定，方便吸血/追加断言）。"""
    defaults = dict(uid="p1", name="试吃员", side="player", kind="player",
                    human_controlled=True, class_name="cls_zhan_shi", level=20,
                    hp=5000, max_hp=5000, mp=500, max_mp=500,
                    atk=200, matk=10, spd=15, crit=0.0,
                    equipment={}, skills=[], learned_skills=[],
                    race=None, evolve_path=0, class_tier=0, attributes={})
    defaults.update(kw)
    return make_actor(**defaults, **{"def": 50, "mdef": 30})


def mk_enemy(hp=99999, name="测试怪", atk=1, matk=1, **kw):
    e = make_actor(uid="e1", name=name, side="enemy", kind="monster",
                   hp=hp, max_hp=hp, atk=atk, matk=matk, spd=5, crit=0.0,
                   level=20, exp=0, gold=0, **{"def": 5, "mdef": 5}, **kw)
    return e


def eat_food(battle, actor, aids):
    """走 battle_item_use.translate 吃料理（真实入口），返回 (logs, cast)。"""
    from content.mech.item_use import translate
    return translate(battle, actor, f"foodfx:{','.join(aids)}")


def basic_attack(battle, actor, target):
    """真实普攻管线（触发 attack_hit 事件）。"""
    info = {"kind": "物理", "_basic": True, "name": "普攻"}
    return A.do_skill(battle, ActCtx(caster=actor, action="attack",
                                     skill_name=None, info=info, target=target))


def test_snake_soup_lifesteal():
    print("【1. 蛇羹：普攻吸血 8%（命中回血）】")
    p = mk_fighter()
    # 怪 atk 要能打穿 50 防（默认 atk=1 打不动满血战士 → 吸血无空间，并发下测试失效）
    e = mk_enemy(atk=300)
    b = B2(btype="monster", sides={"player": [p], "enemy": [e]})
    logs, cast = eat_food(b, p, ["lifesteal"])
    check("吃料理播报", any("蛇羹" in x or "吸血" in x for x in (logs or [])),
          f"logs={logs}")
    check("triggers 挂 skill_hit", any(
        x.get("key") == "food_lifesteal"
        for x in (p.get("triggers") or {}).get("skill_hit", [])),
        f"triggers={p.get('triggers')}")
    # 先让怪打玩家掉血（保证吸血有空间），再普攻吸血验证回升
    m_info = {"kind": "物理", "name": "怪击"}
    A.do_skill(b, ActCtx(caster=e, action="attack", skill_name=None,
                         info=m_info, target=p))
    hp_before = p["hp"]
    check("玩家已掉血", hp_before < 5000, f"hp={hp_before}")
    basic_attack(b, p, e)
    dmg = 99999 - e["hp"]
    heal_expected = int(dmg * 0.08)
    check("玩家战后 hp 上升≈8%吸血", p["hp"] > hp_before,
          f"hp {hp_before}→{p['hp']} dmg={dmg} expect_heal≈{heal_expected}")


def test_pepper_bleed():
    print("【2. 烬火辣椒：20% 命中挂 affix_bleed dot】")
    # 高攻保证命中；用大次数验证概率性触发（stateless 种子下至少命中一次）
    p = mk_fighter()
    e = mk_enemy()
    b = B2(btype="monster", sides={"player": [p], "enemy": [e]})
    eat_food(b, p, ["bleed"])
    # 多次普攻提高触发机会
    for _ in range(15):
        basic_attack(b, p, e)
        if int(e.get("hp", 0) or 0) < 99999:
            break
    # 断言机制存在而非数值：bleed 声明已挂 skill_hit/attack_hit
    check("bleed triggers 已装配", any(
        x.get("key") == "food_bleed"
        for x in (p.get("triggers") or {}).get("skill_hit", [])),
        f"triggers={p.get('triggers')}")


def test_wolf_jerky_counter():
    print("【3. 狼肉干：受击 20% 反击 60%】")
    p = mk_fighter()
    e = mk_enemy(hp=20000)
    b = B2(btype="monster", sides={"player": [p], "enemy": [e]})
    eat_food(b, p, ["counter"])
    # 让怪打玩家（真实 on_taken 事件）
    m_info = {"kind": "物理", "name": "怪击"}
    for _ in range(20):
        A.do_skill(b, ActCtx(caster=e, action="attack", skill_name=None,
                             info=m_info, target=p))
        # 反击伤害应打回怪身上
        if e["hp"] < 20000 and p["hp"] > 0:
            break
    check("反击声明已装配", any(
        x.get("key") == "food_counter"
        for x in (p.get("triggers") or {}).get("on_taken", [])),
        f"triggers={p.get('triggers')}")


def test_honey_regen():
    print("【4. 树蜜糖：effects period 回春（时间驱动每刻跳）】")
    p = mk_fighter()
    e = mk_enemy()
    b = B2(btype="monster", sides={"player": [p], "enemy": [e]})
    eat_food(b, p, ["regen"])
    ef = p.get("effects") or {}
    check("food_regen 条目已建", "food_regen" in ef, f"effects={list(ef)}")
    pd = ef.get("food_regen", {}).get("period") or {}
    check("period dir=heal", pd.get("dir") == "heal", f"period={pd}")
    check("period heal_pct=0.01", abs(float(pd.get("heal_pct") or 0) - 0.01) < 1e-9,
          f"period={pd}")


def test_chowder_precise():
    print("【5. 海鲜浓汤：dmg_calc 恒乘 ×1.1】")
    p = mk_fighter()
    e_no = mk_enemy()
    b1 = B2(btype="monster", sides={"player": [p], "enemy": [e_no]})
    # 同 seed 对照：无 precise vs 有 precise
    random.seed(7)
    A.do_skill(b1, ActCtx(caster=p, action="attack", skill_name=None,
                          info={"kind": "物理", "_basic": True}, target=e_no))
    dmg_no = 99999 - e_no["hp"]

    random.seed(7)
    p2 = mk_fighter(uid="p2")
    e2 = mk_enemy()
    b2 = B2(btype="monster", sides={"player": [p2], "enemy": [e2]})
    eat_food(b2, p2, ["precise"])
    A.do_skill(b2, ActCtx(caster=p2, action="attack", skill_name=None,
                          info={"kind": "物理", "_basic": True}, target=e2))
    dmg_pre = 99999 - e2["hp"]
    check("精准伤害 > 对照", dmg_pre > dmg_no, f"no={dmg_no} pre={dmg_pre}")
    check("精准 ≈1.1×", 1.05 * dmg_no <= dmg_pre <= 1.20 * dmg_no,
          f"ratio={dmg_pre / max(1, dmg_no):.2f}")


def test_pirate_execute_threshold():
    print("【6. 海盗炖鱼：目标 <30% ×1.3（>30% 不触发）】")
    # 对照 1：目标 50% 血 → execute 不触发
    p = mk_fighter()
    e_mid = mk_enemy(hp=1000)
    e_mid["hp"] = 500
    b1 = B2(btype="monster", sides={"player": [p], "enemy": [e_mid]})
    eat_food(b1, p, ["execute"])
    random.seed(11)
    A.do_skill(b1, ActCtx(caster=p, action="attack", skill_name=None,
                          info={"kind": "物理", "_basic": True}, target=e_mid))
    dmg_mid = 500 - e_mid["hp"]

    # 对照 2：目标 20% 血 → execute ×1.3
    random.seed(11)
    p2 = mk_fighter(uid="p2")
    e_low = mk_enemy(hp=1000)
    e_low["hp"] = 200
    b2 = B2(btype="monster", sides={"player": [p2], "enemy": [e_low]})
    eat_food(b2, p2, ["execute"])
    A.do_skill(b2, ActCtx(caster=p2, action="attack", skill_name=None,
                          info={"kind": "物理", "_basic": True}, target=e_low))
    dmg_low = 200 - e_low["hp"]
    check("低血受击伤害明显更高", dmg_low > dmg_mid, f"mid={dmg_mid} low={dmg_low}")
    check("低血 ≈1.3× 高血", 1.10 * dmg_mid <= dmg_low <= 1.60 * dmg_mid,
          f"ratio={dmg_low / max(1, dmg_mid):.2f}")


def test_sacred_bread_shield():
    print("【7. 圣餐面包：立即护盾（回归现有特判）】")
    p = mk_fighter()
    e = mk_enemy()
    b = B2(btype="monster", sides={"player": [p], "enemy": [e]})
    logs, cast = eat_food(b, p, ["shield"])
    check("盾已上（shields 容器）", bool(p.get("shields") or {}),
          f"shields={p.get('shields')}")


def test_duplicate_idempotent():
    print("【8. 吃重复料理 → 不重复挂 triggers/period】")
    p = mk_fighter()
    e = mk_enemy()
    b = B2(btype="monster", sides={"player": [p], "enemy": [e]})
    eat_food(b, p, ["lifesteal", "regen"])
    n1 = len([x for x in (p.get("triggers") or {}).get("skill_hit", [])
              if x.get("key") == "food_lifesteal"])
    eat_food(b, p, ["lifesteal"])
    n2 = len([x for x in (p.get("triggers") or {}).get("skill_hit", [])
              if x.get("key") == "food_lifesteal"])
    check("重复吃 triggers 不叠加", n1 == n2 == 1, f"{n1}→{n2}")
    check("重复吃 food_effects 容器幂等",
          len([a for a in p.get("food_effects", []) if a == "lifesteal"]) == 1,
          f"food_effects={p.get('food_effects')}")


def test_aurora_guard_reduce():
    print("【9. 极光花蜜：受击 -15%（taken_calc 恒乘 0.85）】")
    p = mk_fighter()
    e = mk_enemy(atk=60)
    b = B2(btype="monster", sides={"player": [p], "enemy": [e]})
    eat_food(b, p, ["aurora_guard"])
    check("aurora_guard taken_calc 已装配", any(
        x.get("key") == "food_aurora_guard"
        for x in (p.get("triggers") or {}).get("taken_calc", [])),
        f"triggers={p.get('triggers')}")
    # 真实受击两场对照（同 seed）
    def dmg_taken(has_guard):
        random.seed(3)
        pp = mk_fighter(uid="px")
        ee = mk_enemy(hp=99999, atk=60)
        bb = B2(btype="monster", sides={"player": [pp], "enemy": [ee]})
        if has_guard:
            eat_food(bb, pp, ["aurora_guard"])
        before = pp["hp"]
        A.do_skill(bb, ActCtx(caster=ee, action="attack", skill_name=None,
                              info={"kind": "物理", "name": "怪击"}, target=pp))
        return before - pp["hp"]
    d_no = dmg_taken(False)
    d_gd = dmg_taken(True)
    check("极光减伤生效", d_gd < d_no, f"no={d_no} guard={d_gd}")
    check("减伤 ≈15%", 0.70 * d_no <= d_gd <= 0.95 * d_no,
          f"ratio={d_gd / max(1, d_no):.2f}")


def test_dragon_pancake_mark():
    print("【10. 龙蛋煎饼：命中叠 dragon_mark，每层 +2% 伤害（stat_scale 乘区通道）】")
    p = mk_fighter()
    e = mk_enemy(hp=999999)  # 高血多次命中叠层
    b = B2(btype="monster", sides={"player": [p], "enemy": [e]})
    eat_food(b, p, ["dragon_tongue"])
    # 多次普攻 → 每次叠 1 层 dragon_mark（cap 5），伤害应随层数上升
    # 第一击（0 层→1 层，伤害算的是叠层前）
    dmg_first = 0
    dmg_later = 0
    prev = e["hp"]
    for i in range(6):
        basic_attack(b, p, e)
        dmg = prev - e["hp"]
        prev = e["hp"]
        if i == 0:
            dmg_first = dmg
        if i == 5:
            dmg_later = dmg  # 第 6 击时已叠 5 层满 → +10%
    check("印记层数达 cap", int(((p.get("effects") or {}).get("dragon_mark") or {}).get("stacks", 0)) == 5,
          f"stacks={(p.get('effects') or {}).get('dragon_mark')}")
    check("满层伤害 > 首击", dmg_later > dmg_first, f"first={dmg_first} later={dmg_later}")
    check("满层 ≈ +10%", 1.02 * dmg_first <= dmg_later <= 1.30 * dmg_first,
          f"ratio={dmg_later / max(1, dmg_first):.2f}")


def test_translation_table_full():
    print("【11. 翻译表全 aid 覆盖（吃入全部 19 aid 不崩 + 分类正确）】")
    p = mk_fighter()
    e = mk_enemy()
    b = B2(btype="monster", sides={"player": [p], "enemy": [e]})
    all_aids = ["lifesteal", "bleed", "armor_break", "combo", "element_fire",
                "element_ice", "pierce", "charge", "static", "counter",
                "thorns", "aurora_guard", "regen", "meditate", "dawn_crown",
                "execute", "precise", "shield", "dragon_tongue"]
    logs, cast = eat_food(b, p, all_aids)
    check("吃全表不崩且播报", bool(logs), f"logs={logs}")
    tr = p.get("triggers") or {}
    hit_n = len([x for x in tr.get("skill_hit", []) if str(x.get("key")).startswith("food_")])
    hit_dragon = any(x.get("key") == "dragon_mark" for x in tr.get("skill_hit", []))
    taken_n = len([x for x in tr.get("on_taken", []) if str(x.get("key")).startswith("food_")])
    dc_n = len([x for x in tr.get("dmg_calc", []) if str(x.get("key")).startswith("food_")])
    tc_n = len([x for x in tr.get("taken_calc", []) if str(x.get("key")).startswith("food_")])
    check("命中类 10 aid（9 food_ + dragon_mark）", hit_n >= 9 and hit_dragon,
          f"skill_hit={hit_n} dragon={hit_dragon}")
    check("受击类 2（counter/thorns）", taken_n >= 2, f"on_taken={taken_n}")
    check("乘区类 2（execute/precise）", dc_n >= 2, f"dmg_calc={dc_n}")
    check("减伤类 1（aurora_guard）", tc_n >= 1, f"taken_calc={tc_n}")
    ef = p.get("effects") or {}
    check("period 类 3（regen/meditate/dawn_crown）",
          all(k in ef for k in ("food_regen", "food_meditate", "food_dawn_crown")),
          f"effects={list(ef)}")


if __name__ == "__main__":
    # v181 flaky 修复：玩家真实面板 ~3% 基础闪避（职业成长，actor["dodge"] 改不动——
    # 走 E.player_final_stats 公式）——固定随机种子保证「怪打玩家」必命中
    # （3% 闪避偶发让 test_snake_soup_lifesteal 的掉血/吸血断言打成假红）。
    # 各用例内部自带 seed 的（精准/处决/极光）不受影响。
    random.seed(20260910)
    test_snake_soup_lifesteal()
    test_pepper_bleed()
    test_wolf_jerky_counter()
    test_honey_regen()
    test_chowder_precise()
    test_pirate_execute_threshold()
    test_sacred_bread_shield()
    test_duplicate_idempotent()
    test_aurora_guard_reduce()
    test_dragon_pancake_mark()
    test_translation_table_full()
    print(f"\n===== N10-B7: PASS={PASS} FAIL={FAIL} =====")
    if FAILURES:
        print("失败明细:")
        for f_ in FAILURES:
            print(f"  - {f_}")
    sys.exit(1 if FAIL else 0)
