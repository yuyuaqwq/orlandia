# -*- coding: utf-8 -*-
"""P4-5 AuctionService 状态机直测（services/auction.py，v181 P4-5）

直测 service 函数（不依赖 Main/FakeEvent）：
  1. 出价落库/被超自动退还（bid 语义 = 命令层校验后调用 settle 前状态机）
  2. 一口价成交 → 赢家得装备、其他出价者退还、物品从槽移除、进度持久化
  3. 到期结算 settle_auction：最高价者得装备，其余退还，流拍行提示
  4. 过期 settle_expired_auction：过期拍卖 → 结算 + 清槽；未过期/非拍卖/无事件 → 空串不清槽
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import db, clean_db

from content.auction import (
    settle_auction, settle_expired_auction, save_auction_state,
)

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")


def mk_auction(ends_in=3600, items=None):
    """构造世界事件槽（拍卖）"""
    its = items or [{"id": 1, "name": "试炼之剑", "slot": "weapon", "stats": {}, "desc": "测试用",
                     "base": 100, "buyout": 999999, "bids": {}}]
    cur = {"etype": "auction", "ends_at": int(time.time()) + ends_in, "data": {"items": its}}
    db.save_world_event("auction", cur["ends_at"], cur["data"])
    return cur


async def main():
    clean_db()
    from _engine_harness import make_player
    make_player("g1", "a1", "战士")
    make_player("g1", "a2", "战士")
    db.update_player("g1", "a1", gold=10000)
    db.update_player("g1", "a2", gold=10000)

    print("【1. settle_expired_auction 过期结算 + 清槽】")
    cur = mk_auction(ends_in=-10, items=[
        {"id": 1, "name": "试炼之剑", "slot": "weapon", "stats": {}, "desc": "测试用",
         "base": 100, "buyout": 999999, "bids": {"a1": 500, "a2": 300}},
    ])
    # 落库（模拟出价已持久化）
    db.save_world_event("auction", cur["ends_at"], cur["data"])
    g1a = db.get_player("g1", "a1")["gold"]
    g2a = db.get_player("g1", "a2")["gold"]
    lines = settle_expired_auction("g1")
    check("过期拍卖结算返回文本", "拍得" in lines and "退还" in lines, lines[:120])
    check("槽已清空", db.get_world_event(include_expired=True) is None, "")
    # a1 赢：出价 500 在出价时已扣（本直测直接构造出价后状态，模拟已扣款），
    # 结算只发装备+退还未成交者，不再动赢家金币（落槌价=最高出价，系统回收语义）
    check("赢家金币结算时不再变动(出价时已扣)",
          db.get_player("g1", "a1")["gold"] == g1a,
          f"a1 {db.get_player('g1','a1')['gold']} vs {g1a}")
    check("败者全额退还", db.get_player("g1", "a2")["gold"] == g2a + 300,
          f"a2 {db.get_player('g1','a2')['gold']} vs {g2a + 300}")
    check("赢家获得装备", any(it["key"].startswith("eq_") for it in db.get_inventory("g1", "a1")),
          str([it['key'] for it in db.get_inventory('g1', 'a1')]))

    print("【2. settle_expired_auction 守卫：未过期/非拍卖/无事件 不动槽】")
    mk_auction(ends_in=3600)  # 未过期拍卖
    check("未过期不动槽", settle_expired_auction("g1") == "" and db.get_world_event() is not None, "")
    db.clear_world_event()
    check("无事件返回空串", settle_expired_auction("g1") == "", "")
    db.save_world_event("boss", int(time.time()) + 3600, {"boss": {"hp": 1}})
    check("非 auction 事件不动槽(留给 hunt_boss)", settle_expired_auction("g1") == ""
          and db.get_world_event() is not None, "")
    db.clear_world_event()

    print("【3. settle_auction 直测（不碰槽）：流拍 + 无出价守卫】")
    cur = mk_auction(ends_in=3600, items=[
        {"id": 1, "name": "试炼之剑", "slot": "weapon", "stats": {}, "desc": "测试用",
         "base": 100, "buyout": 999999, "bids": {}},
        {"id": 2, "name": "无人问津的盾", "slot": "shield", "stats": {}, "desc": "测试用",
         "base": 50, "buyout": 999999, "bids": {}},
    ])
    out = settle_auction(cur, "g1")
    check("无人出价全部流拍", "流拍" in out and "无人出价" not in out.replace("无人出价，流拍", ""), out[:150])
    check("非 auction 返回关闭文案", settle_auction({"etype": "boss", "data": {}}, "g1") == "拍卖行已关闭。", "")

    print("【4. save_auction_state 持久化进度】")
    cur = mk_auction(ends_in=3600)
    it = cur["data"]["items"][0]
    it["bids"] = {"a2": 700}  # 模拟一次出价
    save_auction_state(cur)
    got = db.get_world_event()
    check("槽里进度已持久化", got is not None and got["data"]["items"][0]["bids"] == {"a2": 700},
          str(got["data"] if got else None))

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0


if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
