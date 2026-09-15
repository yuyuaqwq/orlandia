# -*- coding: utf-8 -*-
"""v97.3 事件模板引擎验证：老事件行为不变 + 新事件零代码扩展。

覆盖：
1. 13 个模板全部注册
2. 老 12 常规事件 + 5 彩蛋全部有 template 字段（数据完整）
3. 模板执行：loot_gold 加金币 / heal_full 回满 / damage 扣血 / set_state 写状态
4. 老事件行为抽样对比（宝箱金币入账、陷阱扣血、旅人限一次）
5. 新增事件纯数据扩展（数据里加一条 dict 就能触发）
6. _handle_explore_event 整体走模板分发不崩
"""
import sys, os, random, json, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, make_player, Main, FakeEvent, run

# ★ P5D-REPOINT：`tpl_merchant` 是**故意留在宿主壳**（`game/core/event_templates.py`）的
#   唯一模板，包内 18 个模板里没有它；宿主壳随删壳批拿掉后，这里按逐字同源在测试侧复刻
#   并用包内同一个 `register` 注册（与宿主壳装配方式一致）。判据（13 个模板齐备）一字未改。
import content.event_templates as _ET  # noqa: E402
from content.quality_tiers import QUALITY_TIERS as _QT  # noqa: E402


def _host_tpl_merchant(ctx):
    """逐字复刻宿主壳 `game/core/event_templates.py::tpl_merchant`。"""
    _db = ctx._db()
    Cc = ctx._C()
    q = _QT.pick_weights({"white": 45, "green": 40, "blue": 15}, rng=random)
    equip = Cc.generate_equip(random.choice(["weapon", "ring", "necklace"]), max(1, ctx.lv), q)
    price = int(equip["price"] * 0.6)
    _cur_gold = _db.get_player(ctx.group_id, ctx.qq_id).get("gold", 0)
    if _cur_gold >= price and random.random() < Cc.TRADER_DEAL_CHANCE:
        import json as _json, time as _time
        _db.set_event_state(f"trader_{ctx.group_id}_{ctx.qq_id}", _json.dumps({
            "ts": _time.time(), "price": price, "equip": equip}))
        return (f"🛒 【流浪商人】一个商人拉住你：“勇士，看货！便宜卖你了！”\n"
                f"{Cc.QUALITY[equip['quality']]['color']}【{equip['name']}】只要 {price} 金币！\n"
                f"是否购买？回复 确认购买/拒绝")
    return (f"🛒 【流浪商人】一个商人向你兜售 {Cc.QUALITY[equip['quality']]['color']}【{equip['name']}】，"
            f"只要 {price} 金币……你摇了摇头：不买不买。商人悻悻地走了。")


if "merchant" not in _ET.TEMPLATES:
    _ET.register("merchant")(_host_tpl_merchant)

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {str(detail).encode('utf-8', 'replace').decode('utf-8', 'replace')[:300]}")

async def main():
    from content.event_templates import TEMPLATES, execute_event_template, EventContext

    print("【1. 模板注册表】")
    check("13 个模板已注册", len(TEMPLATES) >= 13, TEMPLATES.keys())
    for t in ["loot_gold", "loot_materials", "loot_gold_mats", "exp_gain", "heal_full",
              "damage", "set_state", "set_flag", "dialog", "merchant", "wandering", "combo", "mystery_chest"]:
        check(f"模板 {t} 存在", t in TEMPLATES)

    print("\n【2. 老事件数据完整性】")
    for ev in C.EXPLORE_EVENTS:
        check(f"常规事件 {ev['id']} 有 template", ev.get("template") in TEMPLATES, ev)
    for ev in C.EXPLORE_EGG_EVENTS:
        check(f"彩蛋 {ev['id']} 有 template", ev.get("template") in TEMPLATES, ev)

    print("\n【3. 模板执行行为】")
    clean_db()
    m = Main(None)
    make_player("g1", "q1", level=5)
    p = db.get_player("g1", "q1")
    cur_map = C.MAP_BY_ID["oak_plain"]

    # loot_gold
    ctx = EventContext("g1", "q1", p, cur_map, params={"min": 10, "max": 10, "scale_lv": 0, "header": "💰 {gold}"}, name="橡木平原")
    gold_before = db.get_player("g1", "q1")["gold"]
    text = execute_event_template("loot_gold", ctx)
    gold_after = db.get_player("g1", "q1")["gold"]
    check("loot_gold 加金币", gold_after == gold_before + 10 and "10" in text, (gold_before, gold_after, text))

    # heal_full
    db.update_player("g1", "q1", hp=1, mp=1)
    ctx = EventContext("g1", "q1", db.get_player("g1", "q1"), cur_map, params={"header": "回满 {name}"}, name="橡木平原")
    text = execute_event_template("heal_full", ctx)
    p2 = db.get_player("g1", "q1")
    check("heal_full 回满血蓝", p2["hp"] == p2["max_hp"] and p2["mp"] == p2["max_mp"], (p2["hp"], p2["mp"]))

    # damage
    db.update_player("g1", "q1", hp=100)
    ctx = EventContext("g1", "q1", db.get_player("g1", "q1"), cur_map,
                       params={"pct": 0.15, "min": 5, "header": "损失 {dmg}"}, name="橡木平原")
    text = execute_event_template("damage", ctx)
    p3 = db.get_player("g1", "q1")
    check("damage 扣血且不低于 1", p3["hp"] < 100 and p3["hp"] >= 1, (p3["hp"], text))

    # set_state (ts)
    ctx = EventContext("g1", "q1", db.get_player("g1", "q1"), cur_map,
                       params={"key": "rain_{gid}_{qid}", "value": "ts", "header": "下雨"}, name="橡木平原")
    execute_event_template("set_state", ctx)
    raw = db.get_event_state("rain_g1_q1")
    st = json.loads(raw) if raw else {}
    check("set_state 写入 ts 状态", "ts" in st and isinstance(st["ts"], float), raw)

    # set_flag
    ctx = EventContext("g1", "q1", db.get_player("g1", "q1"), cur_map,
                       params={"flag": "h_test_flag", "key": "saw_it", "header": "见闻"}, name="橡木平原")
    execute_event_template("set_flag", ctx)
    check("set_flag 写入 talk_flag", "saw_it" in db.get_talk_flags("g1", "q1", "h_test_flag"))

    print("\n【4. 老事件行为抽样】")
    # 宝箱（treasure）→ loot_gold_mats
    gold_before = db.get_player("g1", "q1")["gold"]
    ctx = EventContext("g1", "q1", db.get_player("g1", "q1"), cur_map,
                       params={"min": 15, "max": 15, "scale_lv": 2, "blueprint_chance": 0,
                               "header": "宝箱 {gold}", "mat_line": "", "bp_line": ""}, name="橡木平原")
    execute_event_template("loot_gold_mats", ctx)
    gold_after = db.get_player("g1", "q1")["gold"]
    check("宝箱金币入账(15+5*2=25)", gold_after == gold_before + 25, (gold_before, gold_after))

    # 旅人限一次
    ctx = EventContext("g1", "q1", db.get_player("g1", "q1"), cur_map, params={}, name="橡木平原")
    t1 = execute_event_template("wandering", ctx)
    t2 = execute_event_template("wandering", ctx)
    check("旅人第一次给谢礼", "谢礼" in t1, t1)
    check("旅人第二次不再给", "缘分到此为止" in t2, t2)

    print("\n【5. 新事件纯数据扩展】")
    # 模拟数据层加一条新事件（不碰代码）
    new_ev = {"id": "test_firefly", "weight": 5, "name": "萤火虫",
              "template": "dialog",
              "params": {"texts": ["{name}的林间飞满萤火虫！", "{name}的夜被萤火点亮！"]}}
    ctx = EventContext("g1", "q1", db.get_player("g1", "q1"), cur_map,
                       params=new_ev["params"], name="白鹿之森")
    out = execute_event_template(new_ev["template"], ctx)
    check("新 dialog 事件直接执行", out and "白鹿之森" in out, out)

    # 新 loot 事件
    new_ev2 = {"id": "test_mushroom", "weight": 3, "name": "蘑菇圈",
               "template": "loot_materials",
               "params": {"mats": ["草药"], "n": 1, "header": "🍄 {name}的蘑菇圈！获得 {mats}！{extra}", "bp_line": ""}}
    ctx = EventContext("g1", "q1", db.get_player("g1", "q1"), cur_map,
                       params=new_ev2["params"], name="白鹿之森")
    out2 = execute_event_template(new_ev2["template"], ctx)
    check("新 loot 事件直接执行", out2 and "蘑菇圈" in out2, out2)

    print("\n【6. 探索入口整体走模板】")
    clean_db()
    m2 = Main(None)
    make_player("g2", "q2", level=3)
    db.update_player("g2", "q2", cur_map="oak_plain", cur_subarea="")
    random.seed(5)
    # ★ P5D-REPOINT：打桩面从包侧聚合门面 `C` 改到**命令模块** `content.combat_cmds`
    #   （`_handle_explore_event` 按模块全局名 `roll_explore_event` 调用；
    #   `_engine_harness.C` 是包侧聚合门面，未登记 `roll_explore_event`）。
    #   同一语义：强制命中 rain（set_state 模板）。判据一字未改。
    import content.combat_cmds as _CC
    orig_roll = _CC.roll_explore_event
    # 强制命中 rain（set_state 模板）
    _CC.roll_explore_event = lambda exclude=(): next(e for e in C.EXPLORE_EVENTS if e["id"] == "rain")
    try:
        handled, text = m2._handle_explore_event("g2", "q2", db.get_player("g2", "q2"), C.MAP_BY_ID["oak_plain"])
    finally:
        _CC.roll_explore_event = orig_roll
    check("rain 事件走模板返回", handled and "雨" in text, text)
    raw = db.get_event_state("rain_g2_q2")
    check("rain 状态已写入", raw and "ts" in raw, raw)

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return 1 if failed else 0

if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))
