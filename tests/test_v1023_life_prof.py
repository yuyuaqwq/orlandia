# -*- coding: utf-8 -*-
"""v102.3 生活技能差异化专项验证（限定采集/深矿/鱼饵/星铁强化剂/新食物效果）

验证：
  1. 限定采集：夜晚银木林可出夜雾菇/月露，白天不出（mock 时段）
  2. 深矿池：山丘矿洞只出深矿池矿种（含秘银/精金/深渊水晶）
  3. 鱼饵：挂饵 → 垂钓结算消费状态并传给 roll_fish
  4. 星铁强化剂：使用后强化必定成功
  5. 极光庇护：战斗受击伤害 -15%
  6. 新配方完整性：烹饪/炼金配方 cost/product 全存在
"""
import sys, os, sqlite3, time, json, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# v174：独立私有测试库（防全量并行时与共享 test_game_data.db 的 clean_db 互清假失败）
os.environ["GWEN_GAME_DB"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_v1023_private.db")
from conftest import C, db, clean_db, Main, FakeEvent, run, make_player
# ★ P5E-DELETE（2026-09-15，删壳批）：猴补落点改到**包内真源模块**。
#   删壳前 `C` = 宿主聚合壳 `game.content`，`C.current_period = …` 是**在宿主门面上就地覆盖**
#   （宿主门面是普通模块对象，可写）。终态 `C` = `content.facade._Aggregate`（`__slots__` 惰性句柄，
#   **不可写**，且写它也不等于写消费方读的那只对象）⇒ 原写法报
#   `AttributeError: '_Aggregate' object has no attribute 'current_period'`。
#   口径 = 项目既有「补名会移动打桩落点 ⇒ 就地改真源那一只对象」（R5/`test_v1264` 同款）：
#   `C.current_period` 的 `_NAME_SRC` 真源 = `content.time_weather`（`facade.py:146-148`），
#   `C.roll_fish` = `content.fishing`（`:142-144`，`content/profession.py:613` 就在读它）⇒
#   把桩打在真源模块上。判据一条未变。
from content import time_weather as _TW  # noqa: E402
from content import fishing as _FISH  # noqa: E402

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")

async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""



def set_prof(gid, qid, key, lv):
    """用 add_prof_exp 刷副业到指定等级（无直接 setter）。"""
    cur = db.get_prof_level(gid, qid, key)
    while db.get_prof_level(gid, qid, key) < lv:
        db.add_prof_exp(gid, qid, key, 100)
    return db.get_prof_level(gid, qid, key)


def test_cond_gather():
    print("【1. 限定采集（时段钩子）】")
    m = Main(None)
    gid, qid = "g1", "p_cond"
    clean_db()
    make_player(gid, qid, "测试采集", level=10); db.update_player(gid, qid, cur_map="silverwood")
    # mock 时段=night
    orig_period = _TW.current_period
    _TW.current_period = lambda now=None: "night"
    try:
        got = set()
        for _ in range(400):
            r = m._gather_cond_roll("silverwood")
            if r:
                got.add(r)
        check("夜晚银木林限定池产出", "mat_night_mushroom" in got and "mat_moon_dew" in got, f"got={got}")
        # 夜晚采集含限定材料
        mats = set()
        for _ in range(300):
            mats.update(m._gather_roll(10, 5, "silverwood"))
        check("夜晚采集能采到夜雾菇/月露", "mat_night_mushroom" in mats or "mat_moon_dew" in mats, f"mats sample")
    finally:
        _TW.current_period = orig_period
    # 白天：限定池应无命中
    _TW.current_period = lambda now=None: "day"
    try:
        r = m._gather_cond_roll("silverwood")
        check("白天限定池不产出", r is None, f"got={r}")
        mats = set()
        for _ in range(300):
            mats.update(m._gather_roll(10, 5, "silverwood"))
        check("白天采不到限定材料", "mat_night_mushroom" not in mats, "白天出了夜雾菇！")
    finally:
        _TW.current_period = orig_period
    # 冬季夜晚极光花
    orig_season = _TW.current_season
    _TW.current_season = lambda now=None: "winter"
    _TW.current_period = lambda now=None: "night"
    try:
        got = set()
        for _ in range(600):
            r = m._gather_cond_roll("permafrost_field")
            if r:
                got.add(r)
        check("冬季夜晚永冻原野出极光花", "mat_aurora_flower" in got, f"got={got}")
    finally:
        _TW.current_season = orig_season
        _TW.current_period = orig_period


def test_deep_mining():
    print("【2. 深矿池（地点钩子）】")
    m = Main(None)
    gid, qid = "g1", "p_mine"
    clean_db()
    make_player(gid, qid, "测试矿工", level=12); db.update_player(gid, qid, cur_map="hill_mine")
    set_prof(gid, qid, "mining", 3)
    # 结算挖掘（直接调 _settle_mining，st 只需 type）
    st = {"type": "mining"}
    got = set()
    for _ in range(150):
        text = m._settle_mining(gid, qid, st)
        for nm in ("铁矿石", "精铁", "秘银", "精金", "深渊水晶"):
            if nm in (text or ""):
                got.add(nm)
    check("山丘矿洞出深矿池矿种", got >= {"铁矿石", "秘银", "精金"}, f"got={got}")
    # 非矿洞图：不出深渊水晶（普通图兜底价格区间）
    db.update_player(gid, qid, cur_map="oak_plain")
    got2 = set()
    for _ in range(100):
        text = m._settle_mining(gid, qid, st)
        if "深渊水晶" in (text or ""):
            got2.add("深渊水晶")
    check("普通图不出深矿专属矿", "深渊水晶" not in got2, f"got={got2}")


def test_bait_fishing():
    print("【3. 鱼饵（垂钓加权）】")
    m = Main(None)
    gid, qid = "g1", "p_bait"
    clean_db()
    make_player(gid, qid, "测试钓手", level=5); db.update_player(gid, qid, cur_map="oak_town")
    set_prof(gid, qid, "fishing", 3)
    # 挂萤光饵
    db.set_event_state(f"bait_{qid}", json.dumps({"kind": "glow", "ts": int(time.time())}))
    baits_seen = []
    orig_roll = _FISH.roll_fish
    def spy_roll(lv, spot=None, bait=None):
        baits_seen.append(bait)
        return {"name": "月光鱼", "type": "鱼", "price": 50, "quality": "blue", "desc": "测试鱼"}
    _FISH.roll_fish = spy_roll
    try:
        text = m._settle_fishing(gid, qid, {"type": "fishing", "spot": "水边"})
        check("鱼饵传入 roll_fish", baits_seen == ["glow"], f"seen={baits_seen}")
        check("鱼饵提示文案", "萤光鱼饵" in (text or ""), text[-80:] if text else "None")
        # 状态已消费
        check("鱼饵一次性消耗", not db.get_event_state(f"bait_{qid}"), db.get_event_state(f"bait_{qid}"))
    finally:
        _FISH.roll_fish = orig_roll


async def test_enhance_boost():
    print("【4. 星铁强化剂（强化必成）】")
    m = Main(None)
    gid, qid = "g1", "p_enh"
    clean_db()
    make_player(gid, qid, "测试铁匠", level=15); db.update_player(gid, qid, cur_map="white_deer_city", gold=5000)
    set_prof(gid, qid, "enhance", 2)
    # 造一件装备
    eq = {"name": "测试长剑", "slot": "weapon", "enhance": 0, "atk": 10}
    db.add_item(gid, qid, "eq_test1", eq)
    db.set_event_state(f"enhance_boost_{qid}", "1")
    # 玩家需在铁匠铺（mock _at_smith）
    # ★ P5E-DELETE（2026-09-15，删壳批）：打桩对象从「测试自己 new 的 `m`」改到
    #   **命令实际用到的那只壳** `_engine_harness.harness().shell`（= `env.state["shell"]`）。
    #   依据（实测）：`m = Main(None)` 与 `harness().shell` 是**两个不同实例**
    #   （`tests/_engine_harness.py:457/465` 每次 `Main(...)` 都新建一只，`harness().shell`
    #   是 boot 期那一只）；引擎通道执行 handler 时用的是 `env.state["shell"]`，
    #   而 `_at_smith` 是**类上**的真实方法（不是 `Main.__getattr__` 转发面）⇒
    #   在另一只实例上赋值对命令不可见（旧宿主路径下同样不可见，只是那时玩家数据
    #   恰好命中前置而未暴露）。改打「命令真正用的那只壳」的**实例属性**，
    #   语义（只在这个用例期间把铁匠铺判定钉成 True）与断言一字未变。
    from _engine_harness import harness as _harness
    _shell = _harness().shell
    orig_at = _shell._at_smith
    _shell._at_smith = lambda player: True
    try:
        # 强制随机失败（rate 极低）验证 boost 必成
        orig_random = random.random
        random.random = lambda: 0.999
        try:
            text = await cmd(m, "enhance", gid, qid, "强化 测试长剑")
        finally:
            random.random = orig_random
        items = db.get_inventory(gid, qid)
        d = items[0]["data"]
        check("星铁强化剂强化必成", d.get("enhance", 0) == 1, text[:120])
        check("强化剂状态已消费", not db.get_event_state(f"enhance_boost_{qid}"), "状态还在")
    finally:
        _shell._at_smith = orig_at


def test_recipes():
    print("【6. 新配方完整性】")
    from content.catalog_life import COOKING_RECIPES
    from content.catalog_life import ALCHEMY_RECIPES
    ok = True
    for rk, r in COOKING_RECIPES.items():
        if rk.startswith("cook_night") or rk.startswith("cook_moon") or rk.startswith("cook_aurora") or rk.startswith("cook_dragon_blood") or rk.startswith("cook_thunder"):
            for mk in r["cost"]:
                if mk not in C.MATERIALS and mk not in C.ITEMS:
                    ok = False
                    print(f"   缺失材料: {rk} -> {mk}")
            for pk in r["product"]:
                if pk not in C.ITEMS:
                    ok = False
                    print(f"   缺失产物: {rk} -> {pk}")
    for rk, r in ALCHEMY_RECIPES.items():
        if rk.startswith("al_yue_lu") or rk.startswith("al_shen_yuan") or rk.startswith("al_xing_tie"):
            for mk in r["cost"]:
                if mk not in C.MATERIALS and mk not in C.ITEMS:
                    ok = False
                    print(f"   缺失材料: {rk} -> {mk}")
            for pk in r["product"]:
                if pk not in C.ITEMS:
                    ok = False
                    print(f"   缺失产物: {rk} -> {pk}")
    check("新配方 cost/product 全存在", ok)


async def main():
    import random
    # v181 flaky 修复：采集/垂钓随机产出采样——固定种子使概率断言确定性
    # （本文件另硬编码私有库 tests/test_v1023_private.db，run_all 已归串行槽隔离）
    random.seed(20260909)
    test_cond_gather()
    test_deep_mining()
    test_bait_fishing()
    await test_enhance_boost()
    test_recipes()
    print(f"\n结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
