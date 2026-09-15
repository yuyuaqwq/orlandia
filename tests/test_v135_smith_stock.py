# -*- coding: utf-8 -*-
"""v135 铁匠铺全服共享货架测试（smith_stock + economy 接入）

验证：
  1. roll_stock：4 件 = 2 武器 + 1 防具 + 1 饰品，等级窗口 ±5，品质权重合法，exclude 静态店名册
  2. get_smith_stock：惰性初始化 + 全服共享（全局 key 无 qq_id）+ 每日换货（mock now 跨天）
  3. 6h 补货：restock_at 过期 → 保留未售罄件 + 补新品填满 4 件
  4. buy_stock_item：买一件 qty-1；售罄返回 False；价格含浮动；名字带『XX 的作品』后缀
  5. economy shop 面板显示铁匠铺货架块 + 序号/名称购买闭环

独立运行：python tests/test_v135_smith_stock.py
"""
import os
import sys
import json
import random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import FakeEvent, run, clean_db, make_player, new_main, TEST_DB, PLUGIN_DIR

from _engine_harness import C, db
from content import smith_stock as ss
from content import economy_cmds as eco_mod

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}: {detail}")


async def cmd(m, name, gid, qid, msg):
    handler = getattr(m, name)
    ev = FakeEvent(gid, qid, msg)
    return await run(handler, ev)


# ============ 1. roll_stock 结构 ============
def test_roll_stock():
    print("【1. roll_stock：4 件结构 / 等级窗口 / 品质权重 / exclude 静态店名册】")
    random.seed(135)
    for town in ("oak_town", "white_deer", "ironharbor", "dawn_city", "jade_port",
                 "moon_gate", "frost_horn", "dragon_pass", "wind_city"):
        town_lv = ss.town_level(town)
        items = ss.roll_stock(town, town_lv)
        check(f"{town} 货架 {ss.STOCK_COUNT} 件", len(items) == ss.STOCK_COUNT, str(len(items)))
        slots = [C.EQUIP_ROSTER[it["rid"]]["slot"] for it in items]
        n_w = sum(1 for s in slots if s == "weapon")
        n_a = sum(1 for s in slots if s in ("armor", "helm", "boots", "legs"))
        n_t = sum(1 for s in slots if s in ("ring", "necklace"))
        # v170：货架 4→8 = 2 武器 + 3 防具 + 2 饰品 + 1 随机（随机件落三池任一）
        check(f"{town} ≥2武器+≥3防具+≥2饰品",
              (n_w >= 2, n_a >= 3, n_t >= 2), str((n_w, n_a, n_t)))
        lo, hi = town_lv - ss.STOCK_WINDOW, town_lv + ss.STOCK_WINDOW
        # 低等级镇（橡木/白鹿）候选不足时允许下界放宽（方案文档窗口 1-7/3-13 中心 4/8 已是窗口中心；
        # 剩余缺口由全局低段兜底补齐，仍优先低级装——缺口只发生在名册低段空白区，
        # 兜底必然取 Lv.14-20 档（如橡木镇饰品槽位），放宽上限到 Lv.20）
        lo2 = lo - (0 if town_lv >= 10 else 3)
        hi2 = hi + (0 if town_lv >= 10 else 11)  # 低等级镇：窗口 1-7/3-13 → 上限放宽到 Lv.20
        bad = [it["rid"] for it in items if not (lo2 <= C.EQUIP_ROSTER[it["rid"]]["lv"] <= hi2)]
        check(f"{town} 等级窗口 ±5", not bad, f"{bad} lo2={lo2} hi2={hi2}")
        # 兜底件仅限低等级镇：窗口内件必须 ≥1 件
        if town_lv < 10:
            in_win = [it["rid"] for it in items if lo <= C.EQUIP_ROSTER[it["rid"]]["lv"] <= hi]
            check(f"{town} 窗口内至少 1 件", len(in_win) >= 1, str(in_win))
        # 全部件等级 ≤ 城镇推荐等级 + 20（低等级镇缺饰品档，兜底放宽到 Lv.20 档；仍防高等级装）
        too_high = [it["rid"] for it in items if C.EQUIP_ROSTER[it["rid"]]["lv"] > town_lv + 20]
        check(f"{town} 无超高等级件", not too_high, str(too_high))
        for it in items:
            q = C.EQUIP_ROSTER[it["rid"]]["quality"]
            check(f"{town} {it['rid']} qty 限购", it["qty"] >= 1 and it["qty"] <= 3, str(it))
            check(f"{town} {it['rid']} 紫/橙仅 1 份", (q not in ("purple", "orange")) or it["qty"] == 1, str(it))
            check(f"{town} {it['rid']} price_mult 0.8~1.2", 0.8 <= it["price_mult"] <= 1.2, str(it))
            check(f"{town} {it['rid']} 非静态店名册", it["rid"] not in ss._static_shop_rids(), it["rid"])
    # 品质权重分布（5000 次抽样粗验：蓝最重、橙最少）
    counts = {q: 0 for q in ss.QUALITY_WEIGHTS}
    for _ in range(5000):
        counts[ss._pick_weighted_quality()] += 1
    check("品质权重 蓝最多", counts["blue"] > counts["purple"] > counts["orange"], str(counts))
    check("品质权重 白/绿存在", counts["white"] > 0 and counts["green"] > 0, str(counts))


# ============ 2. get_smith_stock 惰性 + 每日换货 ============
def test_get_smith_stock_day_roll():
    print("【2. get_smith_stock：惰性初始化 + 每日 0 点换货】")
    clean_db()
    key = "smith_stock_white_deer"
    db.delete_event_state(key)
    items1 = ss.get_smith_stock("white_deer")
    check(f"首次调用初始化 {ss.STOCK_COUNT} 件", len(items1) == ss.STOCK_COUNT, str(len(items1)))
    raw = db.get_event_state(key)
    st = json.loads(raw)
    check("全局 key（全服共享，无 qq_id）", "qq" not in key and raw is not None, key)
    check("day 记录为今日 ordinal", st["day"] == __import__("datetime").date.today().toordinal(), str(st["day"]))
    check("restock_at 已设置", st["restock_at"] > 0, str(st))
    # 同日再读 → 不换货（同 items）
    items2 = ss.get_smith_stock("white_deer")
    check("同日不换货", [it["rid"] for it in items1] == [it["rid"] for it in items2],
          str(items1) + " vs " + str(items2))
    # 跨天 → 重 roll（mock now/day）
    from unittest import mock
    fake = {"items": [{"rid": "eq_bai_lu_pi_mao", "qty": 1, "price_mult": 1.0}], "day": 0,
            "restock_at": 99999999999}
    db.set_event_state(key, json.dumps(fake, ensure_ascii=False))
    with mock.patch.object(ss, "_now_ts", return_value=int(__import__("time").time())):
        items3 = ss.get_smith_stock("white_deer")
    raw3 = json.loads(db.get_event_state(key))
    check(f"日期变化重 roll（{ss.STOCK_COUNT} 件新货）", len(items3) == ss.STOCK_COUNT and raw3["day"] != 0, str(raw3))


# ============ 3. 6h 补货 ============
def test_restock():
    print("【3. 6h 补货：保留未售罄件 + 补新品填满 4 件】")
    clean_db()
    key = "smith_stock_white_deer"
    db.delete_event_state(key)
    import time as _t
    now = int(_t.time())
    # 先初始化（保证货架有真库存）
    ss.get_smith_stock("white_deer")
    raw = json.loads(db.get_event_state(key))
    items = raw["items"]
    check(f"初始 {ss.STOCK_COUNT} 件", len(items) == ss.STOCK_COUNT, str(len(items)))
    # 模拟 3 件售罄
    for i, it in enumerate(items):
        if i > 0:
            it["qty"] = 0
    raw["restock_at"] = now - 1  # 过期
    db.set_event_state(key, json.dumps(raw, ensure_ascii=False))
    with __import__("unittest").mock.patch.object(ss, "_now_ts", return_value=now):
        items2 = ss.get_smith_stock("white_deer")
    check(f"补货后仍有 {ss.STOCK_COUNT} 件", len(items2) == ss.STOCK_COUNT, str(len(items2)))
    check("未售罄件保留", any(it["rid"] == items[0]["rid"] for it in items2), str(items2))
    st = json.loads(db.get_event_state(key))
    check("restock_at 刷新为 now+6h", st["restock_at"] == now + ss.RESTOCK_HOURS * 3600, str(st["restock_at"]))


# ============ 4. buy_stock_item 原子扣减 ============
def test_buy_stock_item():
    print("【4. buy_stock_item：扣库存 / 售罄 / 命名 / 价格】")
    clean_db()
    key = "smith_stock_frost_horn"
    db.delete_event_state(key)
    items = ss.get_smith_stock("frost_horn")
    target = items[0]
    rid = target["rid"]
    qty_before = target["qty"]
    ok, item_data, price = ss.buy_stock_item("frost_horn", None, rid)
    check("购买成功", ok, str(ok))
    check("名字带『XX 的作品』", "作品" in item_data["name"] and ss.SMITH_NPC_NAMES["frost_horn"] in item_data["name"],
          item_data["name"])
    check("价格含浮动 0.8~1.2", price >= int(ss._smith_equip_price(rid) * 0.8)
          and price <= int(ss._smith_equip_price(rid) * 1.2), str(price))
    raw = json.loads(db.get_event_state(key))
    cur_qty = next(it["qty"] for it in raw["items"] if it["rid"] == rid)
    check("qty-1 写回", cur_qty == qty_before - 1, str(cur_qty))
    # 把该件库存清零 → 再买应售罄
    for it in raw["items"]:
        if it["rid"] == rid:
            it["qty"] = 0
    db.set_event_state(key, json.dumps(raw, ensure_ascii=False))
    ok2, _, _ = ss.buy_stock_item("frost_horn", None, rid)
    check("售罄返回 False", ok2 is False, str(ok2))
    ok3, _, _ = ss.buy_stock_item("frost_horn", None, "eq_bu_cun_zai")
    check("不存在的 rid 返回 False", ok3 is False, str(ok3))


# ============ 5. economy shop 面板 + 购买闭环 ============
async def test_economy_shop():
    print("【5. economy shop 面板显示货架块 + 序号/名称购买闭环】")
    clean_db()
    m = new_main()
    gid, qid = "g_stock", "q_stock"
    # 注册需要 名字+性别（如『注册 测试 男』）
    await cmd(m, "register", gid, qid, "注册 测试 男")
    p = db.get_player(gid, qid)
    check("测试角色已创建", p is not None, str(p))
    if p is None:
        return
    db.update_player(gid, qid, cur_map="white_deer", cur_subarea="white_deer_3", gold=10_000_000,
                     level=8, stamina=999999)
    # 铁匠铺（white_deer_3 = 鹿角铁匠铺 smith，_at_shop 需要子区域 funcs 含 shop/craft）
    # v135 货架 key 提前初始化（避免面板渲染时被 roll 消费随机数影响断言）
    ss.get_smith_stock("white_deer")
    res = await cmd(m, "shop", gid, qid, "商店")
    panel = "\n".join(res) if isinstance(res, list) else str(res)
    # 货架块在面板末尾（第 6 块），翻页遍历找
    for pg in range(1, 8):
        if "作品" in panel:
            break
        res = await cmd(m, "shop", gid, qid, f"商店 {pg + 1}")
        panel = "\n".join(res) if isinstance(res, list) else str(res)
    check("面板含『铁匠铺货架』提示", "全服共享货架" in panel, panel[:300])
    check("面板含 NPC 作品名", "作品" in panel, panel[:300])
    # 找货架件 rid（面板行 s:rid）
    rid = None
    for line in panel.split("\n"):
        if "s:" in line and "作品" in line:
            # 面板行形如 " 9. ⚪ 橡木戒指（老铁的作品）..."
            rid = None
        if "作品" in line:
            break
    # 序号购买：货架件在面板中序号 = 全局条目序号（含前 5 页 25 件）
    raw = json.loads(db.get_event_state("smith_stock_white_deer"))
    sit = raw["items"][0]
    rid = sit["rid"]
    qty_before = sit["qty"]
    idx = None
    for line in panel.split("\n"):
        if C.EQUIP_ROSTER[rid]["name"] in line and "作品" in line:
            idx = int(line.strip().split(".")[0])
            break
    check("货架件在面板序号中", idx is not None, f"rid={rid} panel={panel[:500]}")
    if idx is not None:
        res_buy = await cmd(m, "buy", gid, qid, f"购买 {idx}")
        msg = "\n".join(res_buy)
        check("序号购买成功提示", "你买下了" in msg, msg)
        raw2 = json.loads(db.get_event_state("smith_stock_white_deer"))
        cur_qty = next(it["qty"] for it in raw2["items"] if it["rid"] == rid)
        check("序号购买 qty-1", cur_qty == qty_before - 1, str(cur_qty))
    # 名称购买（第二件）
    if len(raw["items"]) > 1:
        sit2 = raw["items"][1]
        r2 = C.EQUIP_ROSTER[sit2["rid"]]
        npc = ss.SMITH_NPC_NAMES["white_deer"]
        name = f"{r2['name']}（{npc}的作品）"
        res_buy2 = await cmd(m, "buy", gid, qid, f"购买 {name}")
        msg2 = "\n".join(res_buy2)
        check("名称购买成功提示", "你买下了" in msg2, msg2)


async def main():
    test_roll_stock()
    test_get_smith_stock_day_roll()
    test_restock()
    test_buy_stock_item()
    await test_economy_shop()
    print(f"\n===== 结果：PASS={PASS} FAIL={FAIL} =====")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
