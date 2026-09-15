# -*- coding: utf-8 -*-
"""v116 阵营国战最小闭环：四阵营选择 + 每日收集任务 + 贡献 + 阵营商店 + 成就解锁

验证链路（全部在命令层闭环，不依赖 combat 击杀挂钩）：
  1. Lv.20 注册 → 加入阵营（ach_faction1 选择阵营解锁）
  2. 每日阵营任务：跨天分配 + 交付扣材料 + 加贡献
  3. 阵营商店：扣贡献换物品入包
  4. 成就：faction_top（贡献≥100）/ faction_rank1（贡献≥500）

独立运行：python tests/test_v116_faction_camp.py
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _engine_harness import C, db, clean_db, Main, FakeEvent, run
from content.achievements import cond_met, check_achievements

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


def _seed_mat(gid, qid, item_id, name, count):
    db.add_item(gid, qid, item_id, {"name": name, "type": "材料", "stackable": True, "price": 5}, count)


def _camp_data(gid, qid):
    raw = db.get_event_state(f"faction_camp_{gid}_{qid}")
    return json.loads(raw) if raw else {}


async def main():
    clean_db()
    m = Main(None)
    gid, qid = "g1", "fc1"

    print("【1. 加入阵营（Lv.20 门槛 + 成就解锁）】")
    await cmd(m, "register", gid, qid, "注册 战士 旅人 男")
    db.update_player(gid, qid, level=20, gold=1000)
    # 未加入前：faction 条件 False（ach_faction1 不解锁）
    check("未加入：players.faction 为空", db.get_player(gid, qid).get("faction", "") == "")
    # 等级不足拦截
    db.update_player(gid, qid, level=15)
    out = await cmd(m, "camp_join", gid, qid, "加入阵营 1")
    check("Lv.15 加入被拦", "20" in out, out[:120])
    db.update_player(gid, qid, level=20)
    # 加入第 1 阵营
    out = await cmd(m, "camp_join", gid, qid, "加入阵营 1")
    check("加入成功提示阵营名", "圣辉王国" in out, out[:120])
    camp = db.get_player(gid, qid).get("faction", "")
    check("players.faction 已写入", camp in ("holy", "dragon", "elf", "shadow"), camp)
    # 重复加入
    out = await cmd(m, "camp_join", gid, qid, "加入阵营 1")
    check("重复加入提示已是成员", "已是" in out, out[:120])
    # 成就：选择阵营（faction 非空 → cond 通过；写入 achievements）
    new = check_achievements(gid, qid)
    rows = {r["ach_key"] for r in db.get_achievements(gid, qid)}
    check("ach_faction1 选择阵营已解锁", "ach_faction1" in rows, str(rows))

    print("【2. 每日阵营任务：分配 + 交付加贡献】")
    out = await cmd(m, "camp_task", gid, qid, "阵营任务")
    check("今日任务已分配", "今日阵营任务" in out, out[:120])
    data = _camp_data(gid, qid)
    check("分配了每日任务(1~2 个)", 1 <= len(data.get("tasks", [])) <= 2, str(data))
    check("初始贡献为 0", data.get("contrib", 0) == 0)
    # 挑第一个任务交付
    t = data["tasks"][0]
    item_id, need = t["item"], t["count"]
    _seed_mat(gid, qid, item_id, item_id, need)
    out = await cmd(m, "camp_task", gid, qid, "阵营任务 1")
    check("交付成功带贡献", "贡献" in out and "+" in out, out[:120])
    data = _camp_data(gid, qid)
    check("交付后贡献增加", data.get("contrib", 0) >= t["reward"], str(data.get("contrib", 0)))
    check("背包材料被扣除", db.count_item(gid, qid, item_id) == 0)
    check("完成数 +1（done_total）", data.get("done_total", 0) >= 1)

    print("【3. 阵营商店：贡献兑换物资】")
    out = await cmd(m, "camp_shop", gid, qid, "阵营商店")
    check("商店列表可展示", "阵营商店" in out, out[:120])
    # 充足贡献以实际走通购买链路（先攒足贡献）
    d = _camp_data(gid, qid)
    d["contrib"] = 200
    db.set_event_state(f"faction_camp_{gid}_{qid}", json.dumps(d, ensure_ascii=False))
    out = await cmd(m, "camp_shop", gid, qid, "阵营商店")
    check("贡献 200 可购商品可展示", "✅" in out, out[:120])
    before = _camp_data(gid, qid).get("contrib", 0)
    out = await cmd(m, "camp_shop", gid, qid, "阵营商店 1")
    check("购买成功提示", "兑换" in out or "买" in out, out[:120])
    data = _camp_data(gid, qid)
    check("购买后贡献减少", data.get("contrib", 0) < before, f"{before}->{data.get('contrib',0)}")
    check("物品入包 i_treat_l", db.count_item(gid, qid, "i_treat_l") >= 1)

    print("【4. 成就阈值（阵营先锋 ≥100 / 大陆之柱 ≥500）】")
    # 直接模拟贡献数据，验证 cond_met 对各阈值判定
    player = db.get_player(gid, qid)
    stats = db.get_stats(gid, qid) or {}
    # 用同一 event_state 键写贡献，模拟累计到 120
    d = _camp_data(gid, qid)
    d["contrib"] = 120
    db.set_event_state(f"faction_camp_{gid}_{qid}", json.dumps(d, ensure_ascii=False))
    check("faction_top(value=100)：贡献 120 ≥100",
          cond_met(db.get_player(gid, qid), stats, {}, {"_group_id": gid}, {"type": "faction_top"}, gid) is True)
    check("faction_top：贡献 120 < 500 时 rank1 不满足",
          cond_met(db.get_player(gid, qid), stats, {}, {"_group_id": gid}, {"type": "faction_rank1"}, gid) is False)
    d["contrib"] = 500
    db.set_event_state(f"faction_camp_{gid}_{qid}", json.dumps(d, ensure_ascii=False))
    check("faction_rank1(value=500)：贡献 500 ≥500",
          cond_met(db.get_player(gid, qid), stats, {}, {"_group_id": gid}, {"type": "faction_rank1"}, gid) is True)
    # 通过 check_achievements 完整触发两种成就解锁
    new = check_achievements(gid, qid)
    rows = {r["ach_key"] for r in db.get_achievements(gid, qid)}
    check("ach_faction_top 阵营先锋已解锁（贡献达标）", "ach_faction_top" in rows, str(rows))
    check("ach_faction_rank1 大陆之柱已解锁（贡献达标）", "ach_faction_rank1" in rows, str(rows))

    print("【5. 阵营排行】")
    out = await cmd(m, "camp_rank", gid, qid, "阵营排行")
    check("排行输出含阵营", "排行" in out and ("圣辉王国" in out or "成员" in out), out[:160])

    print()
    print(f"结果: {passed} 通过, {failed} 失败")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
