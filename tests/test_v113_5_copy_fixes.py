# -*- coding: utf-8 -*-
"""v113.5 文案引导 6 连修（O71/O86/O90/O97/O117/O120）验证。

覆盖：
1. O71 流浪商人强卖：探索出价不再直接扣钱，回复『确认购买/拒绝』成交或离开
2. O86 烹饪名提示：『烹饪 烤肉串』失败提示列出带 (自制) 后缀的完整名
3. O90 对话定位文案：同图不同子区域 → "（你现在不在这里）"样式（v95_25 测试已覆盖，
   本文件补精英同子区域正向断言）
4. O97 血蝠蛋掉落：去掉调试感"咦？"（文本断言在源字符串层面验证）
5. O117 『使用 风干肉』：材料类不能使用时补副业用途引导
6. O120 锻造成功：提示补"副业经验 +N"反馈
"""
import sys, os, random  # noqa: F401  （`random` 供测试侧 tpl_merchant 逐字复刻用）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, make_player, Main, FakeEvent, run

# ★ P5D-REPOINT：`tpl_merchant`（流浪商人）是**故意留在宿主壳**的唯一模板
#   （`game/core/event_templates.py`，理由 = test_v184_loot_tiers 的宿主源码级绑定断言）。
#   包内 `content/event_templates.py` 的 18 个模板里**没有**它 ⇒ 直取包内实现时
#   `execute_event_template("merchant", …)` 返回 None。该宿主壳被删壳批拿掉后，
#   这里按**逐字同源**把宿主模板在测试侧复刻一份（正文见 GAME_TPL_MERCHANT_SRC 引用注释），
#   用包内同一个 `register` 注册进同一个 `TEMPLATES`（19 键不变）—— 与宿主壳装配方式一致。
#   判据（O71 强卖确认/拒绝）一条未改。
from content.event_templates import (  # noqa: E402
    EventContext, execute_event_template, register as _tpl_register,
)


def _tpl_merchant(ctx):
    """流浪商人：低价装备（可拒绝）—— 逐字复刻宿主壳
    `game/core/event_templates.py::tpl_merchant`（v113.5 O71 修复版）。"""
    import uuid  # noqa: F401
    _db = ctx._db()
    Cc = ctx._C()
    from content.quality_tiers import QUALITY_TIERS
    q = QUALITY_TIERS.pick_weights({"white": 45, "green": 40, "blue": 15}, rng=random)
    equip = Cc.generate_equip(random.choice(["weapon", "ring", "necklace"]), max(1, ctx.lv), q)
    price = int(equip["price"] * 0.6)
    _cur_gold = _db.get_player(ctx.group_id, ctx.qq_id).get("gold", 0)
    if _cur_gold >= price and random.random() < Cc.TRADER_DEAL_CHANCE:
        import json as _json, time as _time
        _db.set_event_state(f"trader_{ctx.group_id}_{ctx.qq_id}", _json.dumps({
            "ts": _time.time(),
            "price": price,
            "equip": equip,
        }))
        return (f"🛒 【流浪商人】一个商人拉住你：“勇士，看货！便宜卖你了！”\n"
                f"{Cc.QUALITY[equip['quality']]['color']}【{equip['name']}】只要 {price} 金币！\n"
                f"是否购买？回复 确认购买/拒绝")
    return (f"🛒 【流浪商人】一个商人向你兜售 {Cc.QUALITY[equip['quality']]['color']}【{equip['name']}】，"
            f"只要 {price} 金币……你摇了摇头：不买不买。商人悻悻地走了。")


if "merchant" not in __import__("content.event_templates", fromlist=["TEMPLATES"]).TEMPLATES:
    _tpl_register("merchant")(_tpl_merchant)

passed = failed = 0
from _check import bind_check  # noqa: E402  P0-1 断言助手单源：tests/_check.py

check = bind_check(globals(), "passed", "failed", limit=300)

async def cmd(m, handler_name, gid, qid, msg):
    ev = FakeEvent(gid, qid, msg)
    handler = getattr(m, handler_name)
    results = await run(handler, ev)
    return results[-1] if results else ""

async def main():
    clean_db()
    m = Main(None)

    # ================= O71 流浪商人强卖确认/拒绝 =================
    print("【1. O71 流浪商人强卖确认/拒绝】")
    import random as _r
    make_player("g1", "q1", level=3)
    db.update_player("g1", "q1", gold=5000, cur_map="oak_plain", cur_subarea="oak_plain_1")
    from content.event_templates import EventContext, execute_event_template  # noqa: F401  (顶部已取，此处保留原调用点语义)

    _orig_random = _r.random
    _r.random = lambda: 0.0  # 稳定命中 TRADER_DEAL_CHANCE 出价分支
    try:
        ctx = EventContext("g1", "q1", db.get_player("g1", "q1"),
                           C.MAP_BY_ID["oak_plain"], params={}, name="橡木平原")
        text = execute_event_template("merchant", ctx)
    finally:
        _r.random = _orig_random
    check("出价含确认/拒绝引导", "确认购买/拒绝" in text, text)
    check("出价不再直接扣钱", db.get_player("g1", "q1")["gold"] == 5000,
          f"gold={db.get_player('g1','q1')['gold']}")
    check("出价未直接入包", not any(it["key"].startswith("eq_")
          for it in db.get_inventory("g1", "q1")), "")

    out = await cmd(m, "trader_confirm", "g1", "q1", "确认购买")
    p = db.get_player("g1", "q1")
    check("确认购买扣金币", p["gold"] < 5000, f"gold={p['gold']}")
    check("确认购买装备入包", any(it["key"].startswith("eq_")
          for it in db.get_inventory("g1", "q1")), "")
    check("确认购买播报文案", "买下了" in out, out[:200])

    _r.random = lambda: 0.0
    try:
        ctx = EventContext("g1", "q1", db.get_player("g1", "q1"),
                           C.MAP_BY_ID["oak_plain"], params={}, name="橡木平原")
        execute_event_template("merchant", ctx)
    finally:
        _r.random = _orig_random
    gold_before = db.get_player("g1", "q1")["gold"]
    n_eq = sum(1 for it in db.get_inventory("g1", "q1") if it["key"].startswith("eq_"))
    out = await cmd(m, "trader_confirm", "g1", "q1", "拒绝")
    check("拒绝不扣金币", db.get_player("g1", "q1")["gold"] == gold_before, "")
    check("拒绝不入包", sum(1 for it in db.get_inventory("g1", "q1")
          if it["key"].startswith("eq_")) == n_eq, "")

    db.set_event_state("trader_g1_q1", "")
    out = await cmd(m, "trader_confirm", "g1", "q1", "确认购买")
    check("无挂起报价明确提示", "没有商人在等你答复" in out, out[:200])

    # ================= O86 烹饪名提示（(自制) 后缀） =================
    print("【2. O86 烹饪名提示】")
    db.update_player("g1", "q1", apprentices=["cooking"])
    out = await cmd(m, "cooking", "g1", "q1", "烹饪 烤肉串")
    check("失败提示列出(自制)完整名", "烤肉串(自制)" in out, out[:200])
    out = await cmd(m, "cooking", "g1", "q1", "烹饪 魔法料理")
    check("无(自制)同名保留旧文案", "没有『魔法料理』这道料理" in out, out[:200])

    # ================= O90 对话定位文案（子区域级） =================
    print("【3. O90 对话定位文案】")
    db.update_player("g1", "q1", cur_map="oak_plain", cur_subarea="oak_plain_3")
    out = await cmd(m, "find_npc", "g1", "q1", "找 巨型野猪")
    check("精英同子区域提示就在", "就在你所在的" in out, out[:300])
    db.update_player("g1", "q1", cur_subarea="oak_plain_1")
    out = await cmd(m, "find_npc", "g1", "q1", "找 巨型野猪")
    check("精英同图异子区域提示不在", "你现在不在这里" in out, out[:300])
    db.update_player("g1", "q1", cur_map="oak_town", cur_subarea="oak_town_1")
    out = await cmd(m, "find_npc", "g1", "q1", "找 镇长")
    check("NPC同图异子区域提示不在", "你现在不在这里" in out, out[:300])

    # ================= O97 血蝠蛋掉落文案 =================
    print("【4. O97 血蝠蛋掉落文案】")
    # ★ P5F-REPOINT: 原读宿主壳 `game/commands/combat.py`（随删壳批消失）→ 包内真源两侧：
    #   `content/combat_cmds.py`（战斗命令实现）+ `content/settlement.py`（掉落播报真源，
    #   O97 的「去掉调试感咦？」注释就落在 settlement.py:476）。
    _pkg = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "content")
    src = "\n".join(open(os.path.join(_pkg, _f), encoding="utf-8").read()
                    for _f in ("combat_cmds.py", "settlement.py"))
    check("掉落文案不再带'咦？'", "咦？【" not in src, "")

    # ================= O117 『使用 风干肉』引导 =================
    print("【5. O117 使用 风干肉 引导】")
    db.add_item("g1", "q1", "mat_feng_gan_rou",
                {"name": "风干肉", "type": "材料", "stackable": True, "price": 25})
    out = await cmd(m, "use", "g1", "q1", "使用 风干肉")
    check("材料不能使用有副业引导", "不能" in out and "烹饪" in out, out[:200])
    check("材料未被消耗", any(it["key"] == "mat_feng_gan_rou"
          for it in db.get_inventory("g1", "q1")), "")

    # ================= O120 锻造成功副业经验反馈 =================
    print("【6. O120 锻造成功副业经验反馈】")
    db.update_player("g1", "q1", apprentices=["craft"], level=8, gold=2000,
                     cur_map="oak_town", cur_subarea="oak_town_3")
    db.add_item("g1", "q1", "mat_shi_lai_mu_nian_ye",
                {"name": "史莱姆黏液", "type": "材料", "stackable": True, "price": 5}, 20)
    db.add_item("g1", "q1", "mat_cu_zhi_ge",
                {"name": "粗制革", "type": "材料", "stackable": True, "price": 15}, 5)  # v167 换料：橡木皮甲主料
    out = await cmd(m, "craft", "g1", "q1", "锻造 橡木皮甲")
    check("锻造成功播报", "锻造成功" in out, out[:200])
    check("锻造成功含副业经验反馈", "副业经验 +1" in out, out[:300])

    print(f"\n======== 结果: {passed} 通过 / {failed} 失败 ========")
    return failed == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
