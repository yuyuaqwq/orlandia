# -*- coding: utf-8 -*-
"""v104 修复回归：商店 / 拍卖 / 坐骑（M08/M09/M15/M17 等批次2+3 修复项）

覆盖断言：
  1. 商店购买 hot 字段：橡木镇橡木桶旅店买黑面包 → 背包物品带 hot/hot_turns（infer_template 判 food）
  2. 商店武器等级：扫描 SHOP_WEAPONS 全部 wlv 与 EQUIP_ROSTER 同名装备 lv 一致（0 失配）
  3. 拍卖防刷：自己出价 2000 后再出价 100 → 拒绝且金币无净收益（先退旧价再扣新价=刷差价）
  4. 上架 0 价格被拒：『上架 狼皮 0』→ 拒绝不入库、物品仍在背包
  5. 商店坐骑：橡木镇商店面板显示老马/小毛驴；『购买 <序号>』能买坐骑；重复购买拦截
  6. 狮鹫渠道：MOUNT_DROP_BOSS 含 mount_griffin；roll_mount_drop("boss") 可掷出
  7. 镇公所配货：ironshield_town_2 商店有货（v104 M09 修复空商店）
  8. 任务道具批量出售保护：背包放任务道具 → 『出售 全部』→ 任务道具保留
"""
import sys, os, time, re, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, Main, FakeEvent, run
from content import item_templates as IT
from content import mounts as M

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


async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "e1", "注册 战士 铁匠 男")
    db.update_player("g1", "e1", cur_map="oak_town", cur_subarea="oak_town_4",
                     level=5, gold=10000, stamina=999999)

    # ============ 1. 商店购买 hot 字段（v104 M09-P0：店售食物全量拷贝 ITEMS 定义字段） ============
    print("【1. 商店购买 hot 字段】")
    out = await cmd(m, "buy", "g1", "e1", "购买 黑面包")
    check("买黑面包成功", "黑面包" in out, out[:150])
    inv = db.get_inventory("g1", "e1")
    bread = next((it for it in inv if it["key"] == "i_bread"), None)
    check("背包已入库黑面包(i_bread)", bread is not None,
          str([(it['key'], it['data'].get('name')) for it in inv]))
    d = bread["data"]
    check("物品带 hot 字段(0.03)", d.get("hot") == 0.03, str(d))
    check("物品带 hot_turns 字段(3)", d.get("hot_turns") == 3, str(d))
    check("infer_template 判为 food", IT.infer_template(d) == "food", IT.infer_template(d))

    # ============ 2. 商店武器等级与名册一致（v104 M07：44 处等级错位修复） ============
    print("【2. 商店武器等级扫描】")
    mism = []
    nomat = 0
    total = 0
    for area, ws in C.SHOP_WEAPONS.items():
        for wname, wtype, wlv, wq in ws:
            total += 1
            ids = C.EQUIP_ROSTER_BY_NAME.get(wname, [])
            if not ids:
                nomat += 1  # 无名册条目走随机生成（兜底），不算失配
                continue
            r = C.EQUIP_ROSTER[ids[0]]
            if r["lv"] != wlv:
                mism.append((area, wname, f"shop={wlv}", f"roster={r['lv']}"))
    check(f"SHOP_WEAPONS 共 {total} 条 0 失配", len(mism) == 0, str(mism[:5]))
    print(f"   （无名册兜底 {nomat} 条；失配 {len(mism)} 条）")

    # ============ 3. 拍卖防刷：自己降价被拒且金币无净收益（v104 M07 P0） ============
    print("【3. 拍卖防刷】")
    db.update_player("g1", "e1", gold=10000)
    db.save_world_event("auction", int(time.time()) + 3600, {"items": [
        {"id": 1, "name": "试炼之剑", "slot": "weapon", "stats": {}, "desc": "测试用",
         "base": 100, "buyout": 999999, "bids": {}},
    ]})
    gold0 = db.get_player("g1", "e1")["gold"]
    out = await cmd(m, "bid", "g1", "e1", "竞拍 1 2000")
    check("出价 2000 成功", "出价成功" in out, out[:150])
    p = db.get_player("g1", "e1")
    check("扣款 2000", p["gold"] == gold0 - 2000, f"gold={p['gold']} 期望 {gold0-2000}")
    out = await cmd(m, "bid", "g1", "e1", "竞拍 1 100")
    check("自己降价被拒", "不能低于自己当前出价" in out, out[:150])
    p2 = db.get_player("g1", "e1")
    check("金币无净收益(未被退旧扣新套利)", p2["gold"] == gold0 - 2000,
          f"gold={p2['gold']} 期望 {gold0-2000}")
    db.clear_world_event()

    # ============ 4. 上架 0 价格被拒（v104 M07：价格至少 1 金币） ============
    print("【4. 上架 0 价被拒】")
    db.add_item("g1", "e1", "mat_lang_pi", {"name": "狼皮", "type": "材料",
                                            "stackable": True, "price": 8}, 5)
    out = await cmd(m, "market_sell", "g1", "e1", "上架 狼皮 0")
    check("上架 0 价被拒", "价格至少 1 金币" in out, out[:150])
    check("市场未入库", len(db.market_list("g1")) == 0, str(db.market_list("g1")))
    inv = db.get_inventory("g1", "e1")
    check("狼皮仍在背包", any(it["key"] == "mat_lang_pi" for it in inv),
          str([it['key'] for it in inv]))
    out = await cmd(m, "market_sell", "g1", "e1", "上架 狼皮 100")
    check("正常价格上架成功", "已上架" in out, out[:150])

    # ============ 5. 商店坐骑（v130.7 意见#23：仅 smith/general 店铺售卖） ============
    print("【5. 商店坐骑】")
    # 旅店（tavern）不再卖坐骑
    db.update_player("g1", "e1", gold=10000, cur_map="oak_town", cur_subarea="oak_town_4")
    out = await cmd(m, "shop", "g1", "e1", "商店")
    check("旅店面板不显示老马", "老马" not in out, out[:250])
    check("旅店面板不显示小毛驴", "小毛驴" not in out, out[:250])
    # 铁匠铺（smith）卖坐骑：名称购买 + 重复购买拦截（序号链路已由 test_v1307_mount_shop 覆盖）
    db.update_player("g1", "e1", cur_map="oak_town", cur_subarea="oak_town_3")
    out = await cmd(m, "buy", "g1", "e1", "购买 老马")
    check("铁匠铺名称购买老马成功", "你买了老马" in out, out[:200])
    p = db.get_player("g1", "e1")
    owned = (p.get("mounts") or {}).get("owned") or []
    check("mounts.owned 含 mount_horse", "mount_horse" in owned, str(p.get("mounts")))
    out = await cmd(m, "buy", "g1", "e1", "购买 老马")
    check("重复购买被拦截", "你已经拥有老马" in out, out[:200])

    # ============ 6. 狮鹫渠道（v104 M06 P2-3：世界 Boss 掉落池） ============
    print("【6. 狮鹫渠道】")
    check("MOUNT_DROP_BOSS 含 mount_griffin", "mount_griffin" in C.MOUNT_DROP_BOSS,
          str(C.MOUNT_DROP_BOSS))
    orig_rnd = random.random
    random.random = lambda: 0.99
    r1 = C.roll_mount_drop("boss")
    check("boss 全不中返回 None", r1 is None, str(r1))
    # q7-3 单次分档随机：一次抽签按累计区间分摊（wolf[0,.10) ghost[.10,.14)
    # warhorse[.14,.16) griffin[.16,.17)），r=0.165 落在狮鹫区间 → 直接命中
    random.random = lambda: 0.165
    r2 = C.roll_mount_drop("boss")
    check("boss 可掷出狮鹫", r2 == "mount_griffin", str(r2))
    random.random = lambda: 0.05
    r3 = C.roll_mount_drop("boss")
    check("boss 掷出灰狼（累计区间首段）", r3 == "mount_wolf", str(r3))
    random.random = orig_rnd
    check("狮鹫=传说坐骑 Lv.60", C.MOUNT_BY_KEY["mount_griffin"]["quality"] == "orange"
          and C.MOUNT_BY_KEY["mount_griffin"]["lv"] == 60,
          str(C.MOUNT_BY_KEY.get("mount_griffin")))

    # ============ 7. 镇公所配货（v104 M09：ironshield_town_2 空商店修复） ============
    print("【7. 镇公所配货】")
    items = C.SHOP_SUBAREA_ITEMS.get("ironshield_town_2") or []
    check("ironshield_town_2 配货非空", len(items) >= 4, str(items))
    check("配货含黑面包/麦酒/药水", "i_bread" in items and "i_ale" in items
          and "i_treat_s" in items, str(items))
    db.update_player("g1", "e1", cur_map="ironshield_town", cur_subarea="ironshield_town_2")
    out = await cmd(m, "shop", "g1", "e1", "商店")
    check("镇公所商店面板有货", "黑面包" in out and "麦酒" in out, out[:250])

    # ============ 8. 任务道具批量出售保护（v104 M08 P1-1） ============
    print("【8. 任务道具批量出售保护】")
    db.update_player("g1", "e1", gold=10000, cur_map="oak_town", cur_subarea="oak_town_4")
    db.add_item("g1", "e1", "q_ember_beacon", {"name": "烬火信标", "type": "任务道具",
                                               "stackable": True, "price": 1})
    db.add_item("g1", "e1", "mat_shi_lai_mu_nian_ye", {"name": "史莱姆黏液", "type": "材料",
                                                       "stackable": True, "price": 5}, 3)
    out = await cmd(m, "sell", "g1", "e1", "出售 全部")
    check("批量出售有返回", "批量出售" in out or "没有可出售" in out, out[:250])
    inv = db.get_inventory("g1", "e1")
    check("任务道具仍在背包", any(it["key"] == "q_ember_beacon" for it in inv),
          str([(it['key'], it['count']) for it in inv]))
    check("提示跳过任务道具", "任务道具" in out and "烬火信标" in out, out[:300])

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0


if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
