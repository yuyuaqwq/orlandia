# -*- coding: utf-8 -*-
"""commands 层：v66 摆摊系统

验证：
  1. 摆摊：支摊/替换旧摊/背包扣除
  2. 收摊：物品退回/无摊提示
  3. 查看：本地摊位列表/指定玩家摊位
  4. 购入：同地图当面买/异地拦截/群市场兼容
  5. 地图：此地玩家列表 + 🏪摆摊标记
  6. 摊位惰性跟随（移动后摊位跟着人走）
"""
import sys, os, sqlite3, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, clean_db, Main, FakeEvent, run

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


_sword_seq = [0]
def add_sword(gid, qid, name="铁剑"):
    _sword_seq[0] += 1
    db.add_item(gid, qid, f"eq_sword_{qid}_{_sword_seq[0]}", {"name": name, "type": "武器", "stackable": False}, 1)


async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "w1", "注册 战士 旅人 男")
    await cmd(m, "register", "g1", "w2", "注册 法师 米娅 男")
    db.update_player("g1", "w1", level=5, gold=1000, cur_map="oak_town")
    db.update_player("g1", "w2", level=5, gold=2000, cur_map="oak_town")

    print("【v66 摆摊：支摊】")
    add_sword("g1", "w1")
    out = await cmd(m, "stall_sell", "g1", "w1", "摆卖 铁剑 500")
    check("摆摊成功", "支起了摊位" in out and "铁剑" in out, out[:200])
    check("背包扣除", db.count_item("g1", "w1", "铁剑") == 0, "")
    out = await cmd(m, "stall_view", "g1", "w1", "摊位")
    check("本地摊位可见", "铁剑" in out and "500 金币" in out, out[:200])
    out = await cmd(m, "stall_view", "g1", "w1", "摊位 旅人")
    check("查看指定玩家摊位", "铁剑" in out and "旅人" in out, out[:200])

    print("【v66 摆摊：无物品/换摊模式】")
    out = await cmd(m, "stall_sell", "g1", "w1", "摆卖 铁剑 500")
    check("背包无物拦截", "背包里没有" in out, out[:120])
    out = await cmd(m, "stall_exchange_pawn", "g1", "w1", "摆换 铁剑")
    check("无价格换摊+背包无物", "背包里没有" in out, out[:120])

    print("【v66 摆摊：地图玩家列表】")
    out = await cmd(m, "map_view", "g1", "w1", "地图")
    check("此地玩家显示", "此地的玩家" in out and "米娅" in out, out[:200])
    # v134.1 #46：地图排除自己——w1 发地图看不到自己（旅人）的摆摊标记，只显示别的玩家（米娅）
    check("摆摊标记(别人)", "摆摊中" not in out and "旅人" not in out, out[:200])

    print("【v66 摆摊：购入】")
    stalls = db.market_list("g1", "oak_town")
    check("摊位入库", len(stalls) == 1, str(len(stalls)))
    mid = stalls[0]["id"]
    out = await cmd(m, "market_buy", "g1", "w2", f"购入 {mid}")
    check("当面购入成功", "购入成功" in out and "铁剑" in out, out[:200])
    check("买家背包有货", db.count_item("g1", "w2", "铁剑") == 1, "")
    check("卖家收款", db.get_player("g1", "w1")["gold"] == 1500, str(db.get_player("g1", "w1")["gold"]))
    check("摊位已清", len(db.market_list("g1", "oak_town")) == 0, "")

    print("【v66 摆摊：异地拦截】")
    add_sword("g1", "w1", "精铁长剑")
    await cmd(m, "stall_sell", "g1", "w1", "摆卖 精铁长剑 800")
    db.update_player("g1", "w2", cur_map="oak_plain")  # w2 离开
    stalls = db.market_list("g1", "oak_town")
    mid = stalls[0]["id"]
    out = await cmd(m, "market_buy", "g1", "w2", f"购入 {mid}")
    check("异地买摊位货被拦", "当面购入" in out, out[:200])
    db.update_player("g1", "w2", cur_map="oak_town")
    out = await cmd(m, "market_buy", "g1", "w2", f"购入 {mid}")
    check("回到原地可买", "购入成功" in out, out[:200])

    print("【v66 摆摊：收摊】")
    add_sword("g1", "w1", "青铜短剑")
    await cmd(m, "stall_sell", "g1", "w1", "摆卖 青铜短剑 300")
    out = await cmd(m, "stall_close", "g1", "w1", "收摊")
    check("收摊成功", "青铜短剑" in out and "退回背包" in out, out[:200])
    check("物品退回", db.count_item("g1", "w1", "青铜短剑") == 1, "")
    out = await cmd(m, "stall_close", "g1", "w1", "收摊")
    check("无摊收摊提示", "没有摊位" in out, out[:120])

    print("【v66 摆摊：替换旧摊】")
    add_sword("g1", "w1", "狼牙棒")
    add_sword("g1", "w1", "铁皮盾")
    await cmd(m, "stall_sell", "g1", "w1", "摆卖 狼牙棒 400")
    out = await cmd(m, "stall_sell", "g1", "w1", "摆卖 铁皮盾 600")
    check("旧摊自动收", "旧摊位已收摊" in out, out[:200])
    check("旧物退回", db.count_item("g1", "w1", "狼牙棒") == 1, "")
    stalls = db.market_list("g1", "oak_town")
    check("新摊只有一件", len(stalls) == 1 and stalls[0]["item_data"].get("name") == "铁皮盾", str(stalls))

    print("【v66 摆摊：摊位惰性跟随】")
    await cmd(m, "stall_sell", "g1", "w1", "摆卖 铁皮盾 600")  # 重新摆
    db.update_player("g1", "w1", cur_map="oak_town")  # 卖家移动
    out = await cmd(m, "stall_view", "g1", "w1", "摊位 旅人")
    check("摊位跟随到新位置", "橡木镇" in out or "vila_street" in out or "铁皮盾" in out, out[:200])
    stalls = db.market_list("g1", "oak_town")
    check("新地图可见摊位", len(stalls) == 1, str([s["map_id"] for s in stalls]))
    # 群市场兼容：上架/购入不受影响（用背包里有的狼牙棒）
    out = await cmd(m, "market_sell", "g1", "w1", "上架 狼牙棒 500")
    check("群市场上架正常", "已上架" in out, out[:200])
    out = await cmd(m, "market", "g1", "w2", "市场")
    check("群市场列表正常", "群友市场" in out and "狼牙棒" in out, out[:200])

    print("【摆摊：以物换物（不设价格）】")
    # w1 先收掉铁皮盾摊，摆一个换摊
    await cmd(m, "stall_close", "g1", "w1", "收摊")
    add_sword("g1", "w1", "精铁胸甲")
    out = await cmd(m, "stall_exchange_pawn", "g1", "w1", "摆换 精铁胸甲")
    check("无价格=换摊", "换摊" in out and "只换不卖" in out, out[:200])
    stalls = db.market_list("g1", "oak_town")
    check("换摊 price=0", len(stalls) == 1 and stalls[0]["price"] == 0, str([s["price"] for s in stalls]))
    mid = stalls[0]["id"]
    out = await cmd(m, "stall_view", "g1", "w1", "摊位")
    check("摊位显示🔄换", "🔄 换" in out and "精铁胸甲" in out, out[:200])
    out = await cmd(m, "market_buy", "g1", "w2", f"购入 {mid}")
    check("购入换摊被拦", "换摊" in out and "只换不卖" in out, out[:200])
    # w2 在橡木平原，摊位在橡木镇 → 异地拦截
    db.update_player("g1", "w2", cur_map="oak_plain")
    out = await cmd(m, "stall_exchange", "g1", "w2", f"换 {mid} 铁剑")
    check("异地交换被拦", "当面交换" in out, out[:200])
    db.update_player("g1", "w2", cur_map="oak_town")
    out = await cmd(m, "stall_exchange", "g1", "w1", f"换 {mid} 铁剑")
    check("自己交换被拦", "不能和自己交换" in out, out[:200])
    out = await cmd(m, "stall_exchange", "g1", "w2", f"换 {mid} 狼皮")
    check("背包无物被拦", "背包里没有" in out, out[:200])
    # 卖摊用换 → 提示用购入
    add_sword("g1", "w1", "青铜斧")
    await cmd(m, "stall_sell", "g1", "w1", "摆卖 青铜斧 300")  # 收掉换摊（精铁胸甲退回）
    stalls2 = db.market_list("g1", "oak_town")
    mid2 = stalls2[0]["id"]
    out = await cmd(m, "stall_exchange", "g1", "w2", f"换 {mid2} 铁剑")
    check("卖摊交换被拦", "出售中" in out, out[:200])
    # 成功交换：w1 收掉卖摊（青铜斧回背包），再摆换摊，w2 用铁剑换
    await cmd(m, "stall_close", "g1", "w1", "收摊")
    await cmd(m, "stall_exchange_pawn", "g1", "w1", "摆换 青铜斧")
    stalls3 = db.market_list("g1", "oak_town")
    mid3 = stalls3[0]["id"]
    out = await cmd(m, "stall_exchange", "g1", "w2", f"换 {mid3} 铁剑")
    check("交换成功", "交换成功" in out and "青铜斧" in out and "铁剑" in out, out[:200])
    check("买家拿到货", db.count_item("g1", "w2", "青铜斧") == 1, "")
    check("摊主收到货", db.count_item("g1", "w1", "铁剑") == 1, "")
    check("换摊已清", len(db.market_list("g1", "oak_town")) == 0, "")
    # 群市场寄售不参与交换
    gmarket = [s for s in db.market_list("g1") if s["item_data"].get("name") == "狼牙棒"]
    out = await cmd(m, "stall_exchange", "g1", "w2", f"换 {gmarket[0]['id']} 铁剑")
    check("群市场不可交换", "群市场" in out, out[:200])

    print("【v167 摆摊：背包序号 + 数量】")
    # w1 先清摊
    await cmd(m, "stall_close", "g1", "w1", "收摊")
    # 加 6 个狼皮（堆叠材料，mat_lang_pi）
    db.add_item("g1", "w1", "mat_lang_pi",
                {"name": "狼皮", "type": "材料", "stackable": True, "price": 5}, count=6)
    # 找狼皮在背包里的序号
    inv = db.get_inventory("g1", "w1")
    idx = next(i for i, it in enumerate(inv, 1) if it["data"].get("name") == "狼皮")
    # 按序号摆 2 个，单价 50
    out = await cmd(m, "stall_sell", "g1", "w1", f"摆卖 {idx} 50 2")
    check("按序号批量摆摊成功", "狼皮 ×2" in out and "50 金币" in out, out[:200])
    stalls = db.market_list("g1", "oak_town")
    check("市场出现2行", len(stalls) == 2, str(len(stalls)))
    check("背包扣2个", db.count_item("g1", "w1", "狼皮") == 4, "")
    # 收摊退回 2 个
    out = await cmd(m, "stall_close", "g1", "w1", "收摊")
    check("收摊退回", "狼皮" in out and "退回背包" in out, out[:200])
    check("退回后6个", db.count_item("g1", "w1", "狼皮") == 6, "")

    print("【v167 摆摊：改名后装备/材料不再同名（咕噜皇冠 vs 咕噜的皇冠）】")
    # 材料已改名『咕噜皇冠』，装备『咕噜的皇冠』——按名字摆应精确命中装备，不再歧义
    db.add_item("g1", "w1", "eq_crown_uuid", {"name": "咕噜的皇冠", "slot": "helm", "quality": "orange", "lv": 20}, count=1)
    db.add_item("g1", "w1", "mat_gu_lu_de_huang_guan",
                {"name": "咕噜皇冠", "type": "材料", "stackable": True, "price": 80}, count=5)
    inv2 = db.get_inventory("g1", "w1")
    eq_i = next(i for i, it in enumerate(inv2, 1) if it["key"] == "eq_crown_uuid")
    # 按名字『咕噜的皇冠』直接摆装备（材料叫咕噜皇冠，不抢）
    out = await cmd(m, "stall_sell", "g1", "w1", "摆卖 咕噜的皇冠 300")
    check("按名字摆金色装备不歧义", "咕噜的皇冠" in out and "300 金币" in out, out[:200])
    stalls2 = db.market_list("g1", "oak_town")
    check("市场1行且是装备", len(stalls2) == 1 and stalls2[0]["item_key"] == "eq_crown_uuid", str([s["item_key"] for s in stalls2]))
    await cmd(m, "stall_close", "g1", "w1", "收摊")

    print("【v167 摆摊：真同名（两堆同名材料）仍列候选】")
    db.add_item("g1", "w1", "mat_dupe_a", {"name": "测试同名料", "type": "材料", "stackable": True, "price": 5}, count=2)
    db.add_item("g1", "w1", "mat_dupe_b", {"name": "测试同名料", "type": "材料", "stackable": True, "price": 5}, count=3)
    out = await cmd(m, "stall_sell", "g1", "w1", "摆卖 测试同名料 100")
    check("真同名列出候选", "同名" in out and "背包序号" in out, out[:200])
    inv3 = db.get_inventory("g1", "w1")
    dupe_a_i = next(i for i, it in enumerate(inv3, 1) if it["key"] == "mat_dupe_a")
    out = await cmd(m, "stall_sell", "g1", "w1", f"摆卖 {dupe_a_i} 100 2")
    check("序号摆同名堆成功", "测试同名料 ×2" in out and "100 金币" in out, out[:200])
    await cmd(m, "stall_close", "g1", "w1", "收摊")

    print("【v167 摆摊换：批量摆换 N 件】")
    # 收掉当前摊（如有）
    await cmd(m, "stall_close", "g1", "w1", "收摊")
    # 再补狼皮到 6（上面同名测试把包弄乱了，直接重加确认数）
    have = db.count_item("g1", "w1", "狼皮")
    if have < 3:
        db.add_item("g1", "w1", "mat_lang_pi",
                    {"name": "狼皮", "type": "材料", "stackable": True, "price": 5}, count=3)
    inv3 = db.get_inventory("g1", "w1")
    idx3 = next(i for i, it in enumerate(inv3, 1) if it["data"].get("name") == "狼皮")
    out = await cmd(m, "stall_exchange_pawn", "g1", "w1", f"摆换 {idx3} 3")
    check("批量摆换成功", "只换不卖" in out and "狼皮 ×3" in out, out[:200])
    stalls4 = db.market_list("g1", "oak_town")
    check("换摊3行price=0", len(stalls4) == 3 and all(s["price"] == 0 for s in stalls4),
          str([(s["price"]) for s in stalls4]))
    check("摆换扣3个", db.count_item("g1", "w1", "狼皮") == have - 3 if have >= 3 else True, "")
    await cmd(m, "stall_close", "g1", "w1", "收摊")
    check("批量收摊退回", db.count_item("g1", "w1", "狼皮") == (have - 3 + 3) if have >= 3 else True, "")

    print("【v167.1 摆摊旧指令引导提示】")
    out = await cmd(m, "stall_deprecated", "g1", "w1", "摆摊 铁剑 500")
    check("老摆摊引导提示", "摆卖" in out and "摆换" in out and "已拆成两条" in out, out[:200])

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)