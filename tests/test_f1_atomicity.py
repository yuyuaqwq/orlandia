# -*- coding: utf-8 -*-
"""F1 经济与存储安全域修复：原子性/数量校验/签到幂等 专项测试

覆盖：
  1. update_item_data：背包格单条原子 UPDATE（强化/附魔写回），非 remove+add 两步
  2. add_item/remove_item 数量校验：count<=0 / 超大 / 非 int 拒绝
  3. 市场购入 market_buy_atomic：单事务 扣买家→加卖家→删单→发货；重复购第二次无效
  4. 摆摊上新 market_stall_sell_atomic：旧摊退包+上新+扣货 单事务
  5. 换摊 market_exchange_atomic：单事务交换，重复交换第二次无效
  6. 出售 sell_item_atomic：加钱+扣包 单事务；重复卖出第二次无效
  7. 签到 signin_claim：条件更新幂等（同日第二次调用无效）
  8. 每日元素 props_use_claim_atomic：重复认领第二次无效
  9. 仓库原子存取 home_storage_deposit/take_atomic
"""
import sys, os, sqlite3, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conftest import C, db, clean_db, Main, FakeEvent, run, make_player

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name} {detail}")

def _q(sql, args=()):
    """直接查询测试库（返回 list of dict）"""
    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

async def main():
    clean_db()
    m = Main(None)
    # 创建测试玩家（store 级测试需要真实 players 行才能读写 gold）
    for gid, qid in [("g1","u1"),("g1","buyer"),("g1","seller1"),("g1","w1"),("g1","w2"),
                     ("g1","w3"),("g1","v1"),("g1","h1"),("g1","signer"),("g1","signer2"),
                     ("g1","p1")]:
        make_player(gid, qid, name="测试", cls="战士", level=5)

    print("【1. update_item_data：背包格单条原子 UPDATE】")
    # 强化/附魔写回：更新某格 item_data，保留原格 count/rowid，不增不删
    key = "eq_sword_x"
    db.add_item("g1", "u1", key, {"name": "铁剑", "slot": "weapon", "enhance": 0, "stackable": False}, 1)
    rows = _q("SELECT item_key, item_data, count, rowid AS rid FROM inventory WHERE qq_id='u1'")
    before_rid = rows[0]["rid"]
    ok = db.update_item_data("g1", "u1", key, {"name": "铁剑", "slot": "weapon", "enhance": 3, "stackable": False})
    rows = _q("SELECT item_key, item_data, count, rowid AS rid FROM inventory WHERE qq_id='u1'")
    check("update_item_data 返回 True", ok is True)
    check("写回后 enhance=3", json.loads(rows[0]["item_data"]).get("enhance") == 3, rows[0]["item_data"])
    check("仍是同一格(1 行,rowid 不变)", len(rows) == 1 and rows[0]["rid"] == before_rid, f"{rows}")
    check("count 未被破坏", rows[0]["count"] == 1, str(rows[0]["count"]))

    print("【1b. update_item_data：不存在的格返回 False】")
    ok = db.update_item_data("g1", "u1", "eq_nonexist", {"name": "无"})
    check("不存在格返回 False", ok is False, str(ok))

    print("【2. add_item/remove_item 数量校验】")
    db.add_item("g1", "u1", "mat_temp", {"name": "测试材料", "stackable": True, "price": 1}, 5)
    r = db.add_item("g1", "u1", "mat_temp", {"name": "测试材料", "stackable": True, "price": 1}, 0)
    check("add count=0 拒绝返回 False", r is False, str(r))
    r = db.add_item("g1", "u1", "mat_temp", {"name": "测试材料", "stackable": True, "price": 1}, -3)
    check("add count<0 拒绝", r is False, str(r))
    r = db.add_item("g1", "u1", "mat_temp", {"name": "测试材料", "stackable": True, "price": 1}, 10_000_000)
    check("add 超大 count 拒绝", r is False, str(r))
    r = db.add_item("g1", "u1", "mat_temp", {"name": "测试材料", "stackable": True, "price": 1}, 1.5)
    check("add 非 int count 拒绝", r is False, str(r))
    check("count 仍为 5 未变", len(_q("SELECT count FROM inventory WHERE qq_id='u1' AND item_key='mat_temp'")) and
          _q("SELECT count FROM inventory WHERE qq_id='u1' AND item_key='mat_temp'")[0]["count"] == 5, "")
    r = db.remove_item("g1", "u1", "mat_temp", 0)
    check("remove count=0 拒绝", r is False, str(r))
    r = db.remove_item("g1", "u1", "mat_temp", 10_000_000)
    check("remove 超大 count 拒绝", r is False, str(r))
    check("remove 拒绝后 count 仍 5", _q("SELECT count FROM inventory WHERE qq_id='u1' AND item_key='mat_temp'")[0]["count"] == 5, "")
    db.remove_item("g1", "u1", "mat_temp", 5)
    check("正常 remove 生效", _q("SELECT count FROM inventory WHERE qq_id='u1' AND item_key='mat_temp'") == [], "")

    print("【3. 市场购入 market_buy_atomic：单事务】")
    db.update_player("g1", "buyer", gold=1000, level=5, cur_map="oak_town")
    db.update_player("g1", "seller1", gold=100, level=5)
    db.market_add("g1", "seller1", "eq_sword_s", {"name": "商人货", "slot": "weapon", "stackable": False}, 300)
    mid = db.market_list("g1")[0]["id"]
    ok, err, name = db.market_buy_atomic("g1", "buyer", mid)
    check("购入成功 ok=True", ok is True, f"{ok} {err}")
    check("买家扣款 1000-300=700", _q("SELECT gold FROM players WHERE qq_id='buyer'")[0]["gold"] == 700, "")
    check("卖家加款 100+300=400", _q("SELECT gold FROM players WHERE qq_id='seller1'")[0]["gold"] == 400, "")
    check("买家收到货", _q("SELECT count FROM inventory WHERE qq_id='buyer' AND item_key='eq_sword_s'")[0]["count"] == 1, "")
    check("市场单已删", db.market_get(mid) is None, "")
    # 重复购买（并发后手场景）：单已删，第二次应失败，金额不变
    ok2, err2, _ = db.market_buy_atomic("g1", "buyer", mid)
    check("重复购入第二次无效", ok2 is False and "已被买走" in err2, f"{ok2} {err2}")
    check("第二次未再扣款", _q("SELECT gold FROM players WHERE qq_id='buyer'")[0]["gold"] == 700, "")

    print("【3b. 购入金币不足】")
    db.market_add("g1", "seller1", "eq_sword_s2", {"name": "贵货", "slot": "weapon", "stackable": False}, 99999)
    mid2 = db.market_list("g1")[-1]["id"]
    ok, err, _ = db.market_buy_atomic("g1", "buyer", mid2)
    check("金币不足拒绝", ok is False and "金币不足" in err, f"{ok} {err}")
    check("不扣款", _q("SELECT gold FROM players WHERE qq_id='buyer'")[0]["gold"] == 700, "")

    print("【4. 摆摊上新 market_stall_sell_atomic】")
    # 真实流程：旧货已在摊位上（from inventory 中被扣出），模拟替换旧摊 → 旧货退回背包
    db.market_add("g1", "w1", "eq_old_s", {"name": "旧货", "slot": "weapon", "stackable": False}, 100, map_id="oak_town")
    old_id = db.market_list("g1", "oak_town")[0]["id"]
    db.add_item("g1", "w1", "eq_new_s", {"name": "新货", "slot": "weapon", "stackable": False}, 1)
    old_items = [{"id": old_id, "item_key": "eq_old_s", "item_data": {"name": "旧货", "slot": "weapon", "stackable": False}}]
    ok = db.market_stall_sell_atomic("g1", "w1", "eq_new_s", {"name": "新货", "slot": "weapon", "stackable": False}, 200, "oak_town", old_items)
    check("摆摊上新成功", ok is True, str(ok))
    # 旧货退回背包（旧货不在包内 → 退回后 count=1）
    check("旧货退回背包", _q("SELECT count FROM inventory WHERE qq_id='w1' AND item_key='eq_old_s'")[0]["count"] == 1, "")
    # 新货扣出背包
    check("新货扣出背包", _q("SELECT count FROM inventory WHERE qq_id='w1' AND item_key='eq_new_s'") == [], "")
    # 市场只剩新摊
    lst = db.market_list("g1", "oak_town")
    check("市场只剩新摊", len(lst) == 1 and lst[0]["item_key"] == "eq_new_s" and lst[0]["price"] == 200, str(lst))

    print("【5. 换摊 market_exchange_atomic】")
    # w2 给 w1 的东西=刀, 摊主货=斧
    db.add_item("g1", "w2", "eq_dao", {"name": "小刀", "slot": "weapon", "stackable": False}, 1)
    exchange_mid = db.market_list("g1", "oak_town")[0]["id"]  # w1 的新货摊(斧换摊? 实际 price=200 是卖摊)
    # 改为换摊：price=0
    _q("UPDATE market SET price=0 WHERE id=?", (exchange_mid,))
    ok, _name = db.market_exchange_atomic("g1", "w2", exchange_mid, "eq_dao", {"name": "小刀", "slot": "weapon", "stackable": False})
    check("换摊成功", ok is True, f"{ok} {_name}")
    check("买家拿到摊主货", _q("SELECT count FROM inventory WHERE qq_id='w2' AND item_key=?",
                            ("eq_new_s",))[0]["count"] == 1, "")
    check("摊主收到小刀", _q("SELECT count FROM inventory WHERE qq_id='w1' AND item_key='eq_dao'")[0]["count"] == 1, "")
    check("换摊单已清", db.market_get(exchange_mid) is None, "")
    # 重复换（第二次单已删 → 失败）
    db.add_item("g1", "w3", "eq_dao2", {"name": "小刀2", "slot": "weapon", "stackable": False}, 1)
    ok, _ = db.market_exchange_atomic("g1", "w3", exchange_mid, "eq_dao2", {"name": "小刀2", "slot": "weapon", "stackable": False})
    check("重复换摊第二次无效", ok is False, str(ok))

    print("【6. 出售 sell_item_atomic】")
    db.add_item("g1", "v1", "mat_pawn", {"name": "可卖材料", "stackable": True, "price": 10}, 3)
    db.update_player("g1", "v1", gold=50)
    ok = db.sell_item_atomic("g1", "v1", "mat_pawn", 3, 24)
    check("出售成功", ok is True, str(ok))
    check("金币加 24", _q("SELECT gold FROM players WHERE qq_id='v1'")[0]["gold"] == 74, "")
    check("货已扣", _q("SELECT count FROM inventory WHERE qq_id='v1' AND item_key='mat_pawn'") == [], "")
    # 重复卖（货已无 → false，不再加钱）
    ok = db.sell_item_atomic("g1", "v1", "mat_pawn", 3, 24)
    check("重复出售第二次失败不加钱", ok is False and _q("SELECT gold FROM players WHERE qq_id='v1'")[0]["gold"] == 74,
          f"{ok} gold={_q('SELECT gold FROM players WHERE qq_id=?', ('v1',))[0]['gold']}")

    print("【7. 签到 signin_claim：条件更新幂等】")
    import datetime
    today = datetime.date.today().isoformat()
    yest = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    claimed, streak, total = db.signin_claim("g1", "signer", today, yest)
    check("首次签到成功", claimed is True and streak == 1 and total == 1, f"{claimed} {streak} {total}")
    # 同日第二次 → 无效
    claimed2, _, _2 = db.signin_claim("g1", "signer", today, yest)
    check("同日二次签到无效", claimed2 is False, str(claimed2))
    # streak/total 未变
    si = db.get_signin("g1", "signer")
    check("streak/total 未被污染", si["streak"] == 1 and si["total"] == 1, str(si))

    print("【7b. 签到：连续两天算连续】")
    yesterday2 = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    # 先模拟昨天已签，第二天再签 → streak=2
    db.save_signin("g1", "signer2", yesterday2, 1, 1)
    claimed3, streak3, total3 = db.signin_claim("g1", "signer2", today, yesterday2)
    check("连续签到 streak=2", claimed3 is True and streak3 == 2 and total3 == 2, f"{claimed3} {streak3} {total3}")

    print("【8. 每日元素 props_use_claim_atomic 幂等】")
    first = db.props_use_claim_atomic("p1", "map:sa:prop", "2026-01-01")
    second = db.props_use_claim_atomic("p1", "map:sa:prop", "2026-01-01")
    check("首次认领 True", first is True, str(first))
    check("重复认领 False", second is False, str(second))
    # 同 key 不同日期可再次
    third = db.props_use_claim_atomic("p1", "map:sa:prop", "2026-01-02")
    check("次日可再认领", third is True, str(third))

    print("【9. 仓库原子存取】")
    key = "home_storage_g1_h1"
    db.add_item("g1", "h1", "eq_sa", {"name": "存物", "slot": "weapon", "stackable": False}, 1)
    ok, _n = db.home_storage_deposit_atomic("g1", "h1", key, "eq_sa", {"name": "存物", "slot": "weapon", "stackable": False}, 5)
    check("原子存仓成功", ok is True, str(ok))
    check("背包已扣", _q("SELECT count FROM inventory WHERE qq_id='h1' AND item_key='eq_sa'") == [], "")
    ok, it = db.home_storage_take_atomic("g1", "h1", key, 1)
    check("原子取出成功", ok is True and it["key"] == "eq_sa", f"{ok} {it}")
    check("取出后回背包", _q("SELECT count FROM inventory WHERE qq_id='h1' AND item_key='eq_sa'")[0]["count"] == 1, "")
    # 重复取第 1 格（已空）→ 失败
    ok, it = db.home_storage_take_atomic("g1", "h1", key, 1)
    check("空仓取出第二次失败", ok is False, str(ok))

    print("【10. 强化强化写回命令层走原子路径（弱断言：函数存在且可调用）】")
    check("update_item_data 已导出至 db 命名空间", hasattr(db, "update_item_data"), "")
    check("market_buy_atomic 已导出", hasattr(db, "market_buy_atomic"), "")
    check("market_stall_sell_atomic 已导出", hasattr(db, "market_stall_sell_atomic"), "")
    check("market_exchange_atomic 已导出", hasattr(db, "market_exchange_atomic"), "")
    check("sell_item_atomic 已导出", hasattr(db, "sell_item_atomic"), "")
    check("signin_claim 已导出", hasattr(db, "signin_claim"), "")
    check("props_use_claim_atomic 已导出", hasattr(db, "props_use_claim_atomic"), "")
    check("home_storage_deposit/take_atomic 已导出",
          hasattr(db, "home_storage_deposit_atomic") and hasattr(db, "home_storage_take_atomic"), "")

    print(f"\n结果: {passed} 通过, {failed} 失败")
    return failed == 0

if __name__ == "__main__":
    import asyncio
    sys.exit(0 if asyncio.run(main()) else 1)
