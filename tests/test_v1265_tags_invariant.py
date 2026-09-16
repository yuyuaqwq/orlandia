# -*- coding: utf-8 -*-
"""v126.4 审计修复回归（tests/test_v1265_tags_invariant.py）

覆盖 8-agent 审计（v126 系列）发现的核心问题修复：
  1. P1 快照回流不变量：市场/摆摊/仓库/交换 单件流转只带 1 条个体 tags，
     len(tags)<=count 恒成立（修复前整堆快照回流 count=1/tags=5 幻影）
  2. roll_fish_size_weight：珍珠类 <0.1kg 品种保留 3 位小数（修复前 round(1位) 全变 0.0kg）
  3. _sell_one 损坏 tag 缺 weight → 不 KeyError（t.get("weight",0) 防御）
  4. FISH_TAGS_MAX=500 合并截断丢最旧
  5. _snapshot_one 纯函数行为
  6. v126.1/v126.2 核心功能直接测试补位：波动区间 + 出售加权（真实区间桩）
"""
import sys, os, json, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, Main, FakeEvent, run
from content.persistence.inventory import _snapshot_one
from content.persistence.social import (
    market_sell_atomic, market_buy_atomic, market_stall_sell_atomic,
    market_exchange_atomic,
)
from content.persistence.world import home_storage_deposit_atomic, home_storage_take_atomic

# 包内产出池展开口（REPOINT_MAP: game.drop_engine → content.loot）。
# `content.profession` 的 `bind_host(expand_pool=…)` 槽在旧宿主薄壳
# `game/services/profession.py` 里注入；终态无该薄壳（其 `_resolve_host("drop_engine")`
# 只认 `sys.modules` 里已加载的宿主模块），故在测试侧补回同一注入（公开注入槽，非自造映射）。
from content.loot import expand_pool as _expand_pool
from content import profession as _profession_mod
_profession_mod.bind_host(expand_pool=_expand_pool)

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


def fish_key(name):
    return C.resolve("materials", name)


def add_fish(gid, qid, name, size, weight, n=1):
    """入包 n 条个体鱼（等价垂钓 add_item(tag=...)）"""
    key = fish_key(name)
    tags = []
    for i in range(n):
        tags.append({"size": size + i, "weight": weight + i * 0.1})
    return db.add_item(gid, qid, key,
                       {"name": name, "type": "鱼", "stackable": True,
                        "price": 6, "quality": "white"},
                       count=n if not tags else 1) or key


def inv_count_tags(gid, qid, key):
    inv = db.get_inventory(gid, qid)
    for it in inv:
        if it["key"] == key:
            d = it["data"]
            return it["count"], len(d.get("tags") or [])
    return None, None


def clear_fish(gid, qid, key):
    """清空该角色鱼格（场景隔离，消除跨场景累计）"""
    inv = db.get_inventory(gid, qid)
    for it in inv:
        if it["key"] == key:
            db.remove_item(gid, qid, key, it["count"])


async def main():
    clean_db()
    m = Main(None)
    await cmd(m, "register", "g1", "w1", "注册 战士 旅人 男")
    await cmd(m, "register", "g1", "w2", "注册 法师 新手 女")

    print("【1 _snapshot_one 纯函数】")
    s1 = _snapshot_one({"name": "银鳞鱼", "tags": [{"size": 1, "weight": 1},
                                                  {"size": 2, "weight": 2}]})
    check("整堆 tags 裁剪为 1 条", s1["tags"] == [{"size": 1, "weight": 1}], s1)
    s2 = _snapshot_one({"name": "铁矿石", "tags": None})
    check("无 tags 原样返回", s2.get("tags") is None, s2)
    s3 = _snapshot_one({"name": "铁矿石"})
    check("无 tags 键原样返回", "tags" not in s3, s3)
    s4 = _snapshot_one([1, 2, 3])
    check("非 dict 原样返回", s4 == [1, 2, 3], s4)

    print("【2 市场上架→购入 快照回流不变量（P1）】")
    key = fish_key("银鳞鱼")
    for i in range(5):
        db.add_item("g1", "w1", key, {"name": "银鳞鱼", "type": "鱼",
                                      "stackable": True, "price": 6, "quality": "white"},
                    tag={"size": 20 + i, "weight": 0.5 + i * 0.1})
    c0, t0 = inv_count_tags("g1", "w1", key)
    check("卖家初始 5 条 5 tags", c0 == 5 and t0 == 5, f"count={c0} tags={t0}")
    # 上架 1 件（带整堆水合快照，模拟命令层传 data）
    inv = db.get_inventory("g1", "w1")
    it = next(x for x in inv if x["key"] == key)
    ok = market_sell_atomic("g1", "w1", key, it["data"], 30)
    check("上架成功", ok, "")
    c1, t1 = inv_count_tags("g1", "w1", key)
    check("上架后卖家剩 4 条 4 tags", c1 == 4 and t1 == 4, f"count={c1} tags={t1}")
    # 买家购入
    mids = [r["id"] for r in db.market_list("g1")]
    check("市场有 1 单", len(mids) == 1, mids)
    ok2, err, _ = market_buy_atomic("g1", "w2", mids[0])
    check("购入成功", ok2 and not err, f"ok={ok2} err={err}")
    c2, t2 = inv_count_tags("g1", "w2", key)
    check("买家 1 条 1 tags（不变量恢复）", c2 == 1 and t2 == 1, f"count={c2} tags={t2}")

    print("【3 家具仓库存取 快照回流不变量（P1）】")
    clear_fish("g1", "w1", key)
    for i in range(4):
        db.add_item("g1", "w1", key, {"name": "银鳞鱼", "type": "鱼",
                                      "stackable": True, "price": 6, "quality": "white"},
                    tag={"size": 30 + i, "weight": 1.0 + i * 0.1})
    c3, t3 = inv_count_tags("g1", "w1", key)
    check("仓库前卖家 4 条 4 tags", c3 == 4 and t3 == 4, f"count={c3} tags={t3}")
    st_key = "storage_w1_main"
    okd, _ = home_storage_deposit_atomic("g1", "w1", st_key, key, it["data"], 20)
    check("存仓成功", okd, "")
    c4, t4 = inv_count_tags("g1", "w1", key)
    check("存仓后卖家 3 条 3 tags", c4 == 3 and t4 == 3, f"count={c4} tags={t4}")
    okt, it2 = home_storage_take_atomic("g1", "w1", st_key, 1)
    check("取出成功", okt, "")
    c5, t5 = inv_count_tags("g1", "w1", key)
    check("取出后 4 条 4 tags（回流不破坏）", c5 == 4 and t5 == 4, f"count={c5} tags={t5}")

    print("【4 摆摊/收摊 快照回流不变量（P1）】")
    clear_fish("g1", "w2", key)
    for i in range(3):
        db.add_item("g1", "w2", key, {"name": "银鳞鱼", "type": "鱼",
                                      "stackable": True, "price": 6, "quality": "white"},
                    tag={"size": 40 + i, "weight": 2.0 + i * 0.1})
    inv2 = db.get_inventory("g1", "w2")
    it2_ = next(x for x in inv2 if x["key"] == key)
    okst = market_stall_sell_atomic("g1", "w2", key, it2_["data"], 20, "oak_plain", [])
    check("摆摊成功", okst, "")
    check("摊位有 1 单", len(db.market_list("g1", "oak_plain")) == 1, "")
    c6, t6 = inv_count_tags("g1", "w2", key)
    check("摆摊后卖家 2 条 2 tags", c6 == 2 and t6 == 2, f"count={c6} tags={t6}")
    removed = db.market_remove_by_seller("g1", "w2")
    import content.persistence.inventory as _inv
    for s in removed:
        db.add_item("g1", "w2", s["item_key"], _snapshot_one(s["item_data"]), count=1)
    c7, t7 = inv_count_tags("g1", "w2", key)
    check("收摊后 3 条 3 tags（回流不破坏）", c7 == 3 and t7 == 3, f"count={c7} tags={t7}")

    print("【5 换摊 双方各 1 件】")
    clear_fish("g1", "w1", key)
    clear_fish("g1", "w2", key)
    # w1 摆摊 1 条鱼，w2 拿 1 件铁矿石换
    inv1 = db.get_inventory("g1", "w1")
    db.add_item("g1", "w1", key, {"name": "银鳞鱼", "type": "鱼",
                                  "stackable": True, "price": 6, "quality": "white"},
                tag={"size": 50.0, "weight": 1.5})
    inv1 = db.get_inventory("g1", "w1")
    it1 = next(x for x in inv1 if x["key"] == key)
    market_stall_sell_atomic("g1", "w1", key, it1["data"], 0, "oak_plain", [])
    mids2 = [r["id"] for r in db.market_list("g1", "oak_plain")]
    check("摊位有 1 单（换摊用）", len(mids2) == 1, mids2)
    ore_key = C.resolve("materials", "铁矿石")
    db.add_item("g1", "w2", ore_key, {"name": "铁矿石", "type": "矿石",
                                      "stackable": True, "price": 5, "quality": "green"})
    orev = db.get_inventory("g1", "w2")
    oreit = next(x for x in orev if x["key"] == ore_key)
    okx, _ = market_exchange_atomic("g1", "w2", mids2[0], ore_key, oreit["data"])
    check("换摊成功", okx, "")
    co, to = inv_count_tags("g1", "w2", key)
    check("换摊后买家 1 条 1 tags", co == 1 and to == 1, f"count={co} tags={to}")

    print("【6 roll_fish_size_weight 珍珠类精度（P2）】")
    for f in C.FISH_POOL:
        wr = f.get("weight_range") or []
        if wr and wr[0] < 0.1:
            random.seed(1)
            z = 0
            for _ in range(200):
                sw = C.roll_fish_size_weight(f)
                if sw and sw["weight"] == 0.0:
                    z += 1
            check(f"{f['name']} 永不产出 0.0kg", z == 0, f"200 次中 {z} 次 0.0")
            sw = C.roll_fish_size_weight(f)
            if sw and sw["weight"]:
                check(f"{f['name']} 重量在区间内", wr[0] <= sw["weight"] <= wr[1], sw)
    # 普通鱼仍 1 位小数
    yl = next(f for f in C.FISH_POOL if f["name"] == "银鳞鱼")
    random.seed(2)
    sw = C.roll_fish_size_weight(yl)
    check("普通鱼 weight 1 位小数", sw and sw["weight"] == round(sw["weight"], 1), sw)

    print("【7 出售加权 + 损坏 tag 防御（P2）】")
    # w1 现有 4 条银鳞鱼 + 1 个 tag（来自上面流水）；直接构造 2 条不同大小的鱼测试 _sell_one
    # 大条 1.8kg vs 小条 0.3kg（银鳞鱼 weight_range [0.3,1.8]，wmax=1.8）
    for w in (1.8, 0.3):
        db.add_item("g1", "w1", key, {"name": "银鳞鱼", "type": "鱼",
                                      "stackable": True, "price": 6, "quality": "white"},
                    tag={"size": 30.0, "weight": w})
    inv5 = db.get_inventory("g1", "w1")
    big = next(x for x in inv5 if x["key"] == key)
    # 直接调用 _sell_one（返回 name,count,gold）
    g0 = db.get_player("g1", "w1")["gold"]
    r_big = m._sell_one("g1", "w1", db.get_player("g1", "w1"), big, 0.8)
    check("大鱼实收 > 原价", r_big and r_big[2] > 6, r_big)
    # 损坏 tag（缺 weight）→ 不崩，按 0 权重兜底
    db.add_item("g1", "w1", key, {"name": "银鳞鱼", "type": "鱼",
                                  "stackable": True, "price": 6, "quality": "white"},
                tag={"size": 30.0, "weight": 1.0})
    db.add_item("g1", "w1", key, {"name": "银鳞鱼", "type": "鱼",
                                  "stackable": True, "price": 6, "quality": "white"},
                tag={"size": 31.0})   # 缺 weight
    inv6 = db.get_inventory("g1", "w1")
    bad = next(x for x in inv6 if x["key"] == key)
    try:
        r_bad = m._sell_one("g1", "w1", db.get_player("g1", "w1"), bad, 0.8)
        check("损坏 tag 出售不崩", r_bad is not None, r_bad)
    except Exception as e:
        check("损坏 tag 出售不崩", False, repr(e))

    print("【8 FISH_TAGS_MAX 500 截断】")
    clear_fish("g1", "w2", key)
    for i in range(501):
        db.add_item("g1", "w2", key, {"name": "银鳞鱼", "type": "鱼",
                                      "stackable": True, "price": 6, "quality": "white"},
                    tag={"size": float(i), "weight": 0.5})
    c8, t8 = inv_count_tags("g1", "w2", key)
    check("501 条合并截断到 500", t8 == 500 and c8 >= 500, f"count={c8} tags={t8}")

    print("【9 鱼专属渲染器（拍板项 3）】")
    clear_fish("g1", "w1", key)
    db.add_item("g1", "w1", key, {"name": "银鳞鱼", "type": "鱼",
                                  "stackable": True, "price": 6, "quality": "white"},
                tag={"size": 30.0, "weight": 1.0})
    out9 = await cmd(m, "item_detail", "g1", "w1", "物品详情 银鳞鱼")
    check("鱼标题用 🐟 图标", "🐟 【银鳞鱼】" in out9, out9)
    check("不再用默认 📦 图标", "📦 【银鳞鱼】" not in out9, out9)
    check("显示类型+品质", "类型：鱼 ｜ 品质：" in out9, out9)
    check("显示 FISH_POOL 描述", "描述：" in out9 and "淡水鱼" in out9, out9)
    check("大鱼按重量加价提示", "大鱼按重量加价" in out9, out9)
    check("个体区仍在", "个体：" in out9 and "30.0cm / 1.0kg" in out9, out9)

    print("【10 渔获材料不加权（拍板项 1）】")
    clear_fish("g1", "w2", key)
    hc_key = fish_key("海藻")
    # 海藻 type=材料（FISH_POOL 登记），带满重 tag（旧行为会加权 1.5×）
    db.add_item("g1", "w2", hc_key, {"name": "海藻", "type": "材料",
                                     "stackable": True, "price": 15, "quality": "green"},
                tag={"size": 30.0, "weight": 1.9})
    invh = db.get_inventory("g1", "w2")
    hc = next(x for x in invh if x["key"] == hc_key)
    r_hc = m._sell_one("g1", "w2", db.get_player("g1", "w2"), hc, 0.8)
    check("海藻（材料）卖价 = 原价 12 不加权", r_hc and r_hc[2] == 12, r_hc)
    # 对照：银鳞鱼（type=鱼）同价位仍加权
    db.add_item("g1", "w2", key, {"name": "银鳞鱼", "type": "鱼",
                                  "stackable": True, "price": 6, "quality": "white"},
                tag={"size": 40.0, "weight": 1.8})
    invf = db.get_inventory("g1", "w2")
    ff = next(x for x in invf if x["key"] == key)
    r_f = m._sell_one("g1", "w2", db.get_player("g1", "w2"), ff, 0.8)
    check("银鳞鱼（鱼）满重加权 > 原价", r_f and r_f[2] > 4, r_f)

    print("【11 体力不足带旧轮结算播报（拍板项 4）】")
    # w3：采集等待已到期 + 体力 0 → 发『采集』应同时看到结算播报和体力不足
    await cmd(m, "register", "g1", "w3", "注册 游侠 野行 女")
    db.update_player("g1", "w3", apprentices=["gather"], cur_map="oak_plain",
                     cur_subarea="oak_plain_3", stamina=0)
    db.activate_prof("g1", "w3", "gather")
    # 旧轮 = 到点未收取的引擎作业（`prof_jobs_{qq}` 作业表，到点仍留在队列里）
    _past = int(__import__("time").time()) - 1
    db.set_event_state("prof_jobs_w3", json.dumps(
        [{"kind": "gather", "started_at": _past - 1, "ends_at": _past,
          "payload": {"spot_map": "oak_plain"}}], ensure_ascii=False))
    out11 = await cmd(m, "gather", "g1", "w3", "采集")
    check("输出含旧轮结算播报", "采集完成" in out11, out11)
    check("输出含体力不足提示", "体力不足" in out11, out11)

    print(f"\n结果：{passed} 通过 / {failed} 失败")
    if failed:
        sys.exit(1)

if __name__ == "__main__":
    asyncio = __import__("asyncio")
    asyncio.run(main())