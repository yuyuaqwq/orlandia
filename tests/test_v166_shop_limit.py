# -*- coding: utf-8 -*-
"""v166 商店限购测试（店内共享库存 + 每日个人限购 + 补货 + economy buy 接入）

验证：
  1. shop_limit 数据层 SHOP_LIMIT 已挂进 content，配置合法
  2. check_and_consume：未配置放行 / 配置限购按库存+日限扣 / 售罄 / 店独立
  3. 补货：restock_hours 到点恢复满额（mock now）
  4. economy buy 接入：序号购买 & 名称购买限购拦截 / 库存共享扣减
  5. 面板标注：限购商品带『库存 x/y · 今日限 z』

独立运行：python tests/test_v166_shop_limit.py
"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import FakeEvent, run, clean_db, make_player, new_main, TEST_DB, PLUGIN_DIR

from _engine_harness import C, db
from content import shop_stock as SS

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


# ============ 1. 数据层 ============
def test_data_layer():
    print("【1. SHOP_LIMIT 挂进 content + 配置合法】")
    check("SHOP_LIMIT 已导出", hasattr(C, "SHOP_LIMIT"), "")
    check("SHOP_LIMIT 非空", len(C.SHOP_LIMIT) > 0, str(len(C.SHOP_LIMIT) if hasattr(C, "SHOP_LIMIT") else "?"))
    # 关键商品必须配置
    check("双倍金币符有限购", "item:i_shuang_bei_jin_bi_fu" in C.SHOP_LIMIT, "")
    # 配置结构合法（import 时已自检，这里抽查）
    for k, cfg in C.SHOP_LIMIT.items():
        check(f"{k} stock/per_day 合法",
              cfg.get("stock") is None or cfg["stock"] >= 0,
              str(cfg))
        break


# ============ 2. 核心 check_and_consume ============
def test_check_consume():
    print("【2. check_and_consume：放行/限购/日限/售罄/店独立】")
    clean_db()
    # 未配置 → 放行
    ok, reason, can = SS.check_and_consume("g1", "q1", "oak_town_5", "item:i_treat_s", 5)
    check("未配置商品放行", ok is True, str((ok, reason)))
    # 双倍金币符 stock5 per_day2
    k = "item:i_shuang_bei_jin_bi_fu"
    ok, reason, can = SS.check_and_consume("g1", "q1", "ironharbor_6", k, 2)
    check("买2件成功", ok is True and can == 2, str((ok, can)))
    ok, reason, can = SS.check_and_consume("g1", "q1", "ironharbor_6", k, 1)
    check("同日再买被日限拦", ok is False and "今日限购" in reason, str((ok, reason)))
    # 另一玩家买（库存剩 3，日限 2 → 买 2 成功）
    ok, reason, can = SS.check_and_consume("g2", "q2", "ironharbor_6", k, 2)
    check("另一玩家买2成功", ok is True and can == 2, str((ok, can)))
    # 库存剩 1 → 第三玩家买 2 失败
    ok, reason, can = SS.check_and_consume("g3", "q3", "ironharbor_6", k, 2)
    check("库存不足拒绝", ok is False and "库存只剩" in reason, str((ok, reason)))
    # 不同子区域独立库存
    ok, reason, can = SS.check_and_consume("g1", "q1", "dawn_city_3", k, 2)
    check("另一家店库存独立可买", ok is True, str((ok, reason)))


# ============ 3. 补货 ============
def test_restock():
    print("【3. restock_hours 补货恢复满额】")
    clean_db()
    k = "item:i_shuang_bei_jin_bi_fu"
    # 买空（库存5，per_day2：3人各买2→第3人只买1）
    SS.check_and_consume("g1", "qa", "ironharbor_6", k, 2)
    SS.check_and_consume("g1", "qb", "ironharbor_6", k, 2)
    SS.check_and_consume("g1", "qc", "ironharbor_6", k, 1)  # 库存剩0
    st = SS.stock_state("ironharbor_6", k, SS.get_limit(k))
    check("库存为0", st["left"] == 0, str(st))
    # mock 时间推进 7h → 补货满额
    from unittest import mock
    now = int(time.time())
    with mock.patch.object(SS, "_now_ts", return_value=now + 7 * 3600):
        st2 = SS.stock_state("ironharbor_6", k, SS.get_limit(k))
        check("7h后恢复满额5", st2["left"] == 5, str(st2))
        # 但个人日限仍拦（qa 今日已买 2）
        ok, reason, can = SS.check_and_consume("g1", "qa", "ironharbor_6", k, 1)
        check("补货后个人日限仍生效", ok is False and "今日限购" in reason, str((ok, reason)))
        # 新玩家可买
        ok, reason, can = SS.check_and_consume("g1", "qd", "ironharbor_6", k, 2)
        check("补货后新玩家可买", ok is True, str((ok, reason)))


# ============ 4. economy buy 接入 ============
async def test_buy_e2e():
    print("【4. buy 命令限购拦截 + 库存共享】")
    clean_db()
    m = new_main()
    gid, qid = "g_v166", "q_v166"
    await cmd(m, "register", gid, qid, "注册 测试 男")
    p = db.get_player(gid, qid)
    check("角色创建", p is not None, "")
    if p is None:
        return
    # 到铁港补给店（ironharbor_6 有双倍金币符 + 传送卷轴等）
    db.update_player(gid, qid, cur_map="ironharbor", cur_subarea="ironharbor_6",
                     gold=1_000_000, level=20, stamina=999999)
    # 双倍金币符：stock5 per_day2。买 3 → 应被日限拦（库存够5但 per_day 只有2）
    res = await cmd(m, "buy", gid, qid, "购买 双倍金币符 3")
    out = "\n".join(res) if isinstance(res, list) else str(res)
    check("买3个被日限拦", "限购" in out or "明日" in out, out[:200])
    # 买 2 → 成功
    res = await cmd(m, "buy", gid, qid, "购买 双倍金币符 2")
    out = "\n".join(res) if isinstance(res, list) else str(res)
    check("买2个成功", "购买" in out and "双倍金币符" in out, out[:200])
    # 背包有 2 张
    n = db.count_item(gid, qid, "双倍金币符")
    check("背包2张", n == 2, str(n))
    # 同日再买 1 → 日限拦
    res = await cmd(m, "buy", gid, qid, "购买 双倍金币符 1")
    out = "\n".join(res) if isinstance(res, list) else str(res)
    check("再买1被日限拦", "限购" in out, out[:200])
    # 普通未限购商品照常买（铁港补给店有 治疗药水 等未限购品——i_treat_m/i_mana_m 在铁港10，但铁港6卖鱼饵）
    res = await cmd(m, "buy", gid, qid, "购买 萤光鱼饵 3")
    out = "\n".join(res) if isinstance(res, list) else str(res)
    check("未限购商品批量购买不受影响", "萤光鱼饵" in out and "×3" in out, out[:200])


# ============ 5. 面板标注 ============
async def test_shop_panel():
    print("【5. 商店面板限购标注】")
    clean_db()
    m = new_main()
    gid, qid = "g_v166b", "q_v166b"
    await cmd(m, "register", gid, qid, "注册 测试2 男")
    db.update_player(gid, qid, cur_map="ironharbor", cur_subarea="ironharbor_6",
                     gold=1_000_000, level=20, stamina=999999)
    res = await cmd(m, "shop", gid, qid, "商店")
    panel = "\n".join(res) if isinstance(res, list) else str(res)
    # 双倍金币符可能不在第一页 → 翻页遍历找
    for pg in range(2, 6):
        if "双倍金币符" in panel and "今日限 2" in panel:
            break
        res = await cmd(m, "shop", gid, qid, f"商店 {pg}")
        panel = "\n".join(res) if isinstance(res, list) else str(res)
    check("面板含双倍金币符", "双倍金币符" in panel, panel[:200])
    check("面板含限购标注", "今日限 2" in panel and "库存" in panel, panel[:400])


if __name__ == "__main__":
    import asyncio
    print("v166 商店限购测试")
    test_data_layer()
    test_check_consume()
    test_restock()
    asyncio.run(test_buy_e2e())
    asyncio.run(test_shop_panel())
    print(f"\n结果: PASS {PASS} / FAIL {FAIL}")
    sys.exit(1 if FAIL else 0)